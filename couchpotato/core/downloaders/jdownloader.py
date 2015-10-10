import hashlib
import hmac
import json
import time
import traceback
import urllib
import base64
from Crypto.Cipher import AES
from couchpotato.api import addApiView
from couchpotato.core._base.downloader.main import DownloaderBase, ReleaseDownloadList
from couchpotato.core.helpers.encoding import sp
from couchpotato.core.logger import CPLog
from libs import requests
from libs.requests.exceptions import ConnectionError

autoload = 'jDownloader'

BS=16
pad = lambda s: s + ((BS - len(s) % BS) * chr(BS - len(s) % BS)).encode()
unpad = lambda s : s[0:-ord(s[-1])]

log = CPLog(__name__)

class jDownloader(DownloaderBase):
    protocol = ['och']
    session_id = None
    API = None

    def __init__(self):
        super(jDownloader, self).__init__()
        addApiView('download.%s.fetchDevices' % self.getName().lower(), self._getDeviceList)

    def _connect(self):
        if self.conf('email') != "" and self.conf('password')!="" and self.API:
            if not self.API.reconnect():
                log.error("Failed to reconnect to your MyJDAccount.")
        elif self.conf('email') != "" and self.conf('password') != "":
            try:
                self.API = jDownloaderAPI(self.conf('email'), self.conf('password'))
            except:
                self.API = None
                log.error("Login to your MyJDAccount failed.")
        else:
            self.API = None

    def _getDevice(self):
        self._connect()
        if self.API and self.conf('deviceID') != "":
            self.API.getDevices()
            return self.API.getDevice(self.conf('deviceID'))
        else:
            log.error("No Device chosen or wrong ID, please go back to JD Settings.")
            return False

    def _getDeviceList(self, **kwargs):
        self._connect()
        self.API.getDevices()
        r = {}
        for dev in self.API.listDevices():
            r[dev['name']] = dev['id']
        return r

    def test(self):
        if self.conf('email') != "" and self.conf('password')!="":
            self.API = jDownloaderAPI(self.conf('email'), self.conf('password'))
            if self.API.reconnect():
                self.API.getDevices()
                self.conf('deviceID', value=[(x['name'],x['id']) for x in self.API.listDevices()])
        else:
            return False


    def download(self, data = None, media = None, filedata = None):
        """ Send a package/links to the downloader

        """
        if not media: media = {}
        if not data: data = {}

        packageName = self.createFileName(data, filedata, media)
        links = ','.join(json.loads(data.get('url')))
        try:
            self._getDevice().addLinks(links, packageName, True)
        except:
            log.error('Something went wrong sending the jDownloader file: %s', traceback.format_exc())
            return False
        return self.downloadReturnId(packageName)

    def getAllDownloadStatus(self, ids):
       """ Get status of all active downloads
       :param ids: list of (mixed) downloader ids
           Used to match the releases for this downloader as there could be
           other downloaders active that it should ignore
       :return: list of releases
       """

       status, raw_statuses = self._getDevice().getDownloadPackages()

       release_downloads = ReleaseDownloadList(self)
       for id in ids:
           packages = raw_statuses.get('data', [])
           package_ids = [x['name'] for x in packages]
           if id in package_ids:
                listIndex = package_ids.index(id)
                # Check status
                status = 'busy'
                if packages[listIndex].get('finished', False):
                   status = 'completed'
               #elif pkg.get('status','') #check for errors
               #    status = 'failed'
                release_downloads.append({
                   'id': packages[listIndex]['uuid'],
                   'name': packages[listIndex]['name'],
                   'status': status,
                   'original_status': packages[listIndex].get('status',None),
                   'timeleft': packages[listIndex].get('eta',-1),
                   'folder': sp(packages[listIndex]['saveTo']),
                })
           else: #id not found in jd - mark as failed
               release_downloads.append({
                   'id': id,
                   'name': '',
                   'status': 'failed',
                   'timeleft': -1,
                   'folder': '',
           })

    def getUUIDbyPackageName(self, name):
        for query in [self._getDevice().getDownloadPackages, self._getDevice().getLinkgrabberPackages]:
            status, response = query()

            packageNames = [x['name'] for x in response['data']]
            for packageName in packageNames:
                if name == packageName:
                    return response['data'][packageNames.index(packageName)]['uuid']
            return None

class jDownloaderDevice:
    """
    Class that represents a JD device and it's functions

    """
    def __init__(self,jd,deviceDict):
        """ This functions initializates the device instance.
        It uses the provided dictionary to create the device.

        :param deviceDict: Device dictionary

        """
        self.name=deviceDict["name"]
        self.dId=deviceDict["id"]
        self.dType=deviceDict["type"]
        self.jd=jd

    def action(self,action=False,params=False,postparams=False):
        """
        Execute any action in the device using the postparams and params.

        All the info of which params are required and what are they default value, type,etc
        can be found in the MY.Jdownloader API Specifications ( https://goo.gl/pkJ9d1 ).

        :param params: Params in the url, in a list of tuples. Example: /example?param1=ex&param2=ex2 [("param1","ex"),("param2","ex2")]
        :param postparams: List of Params that are send in the post.
        """
        if not action:
            return False, False
        httpaction="POST"
        actionurl=self.__actionUrl()
        if not actionurl:
            return False, False
        if postparams:
            post=[]
            for postparam in postparams:
                if type(postparam)==type({}):
                    keys=list(postparam.keys())
                    data="{"
                    for param in keys:
                        if type(postparam[param])==bool:
                            data+='\\"'+param+'\\" : '+str(postparam[param]).lower()+','
                        elif type(postparam[param])==str:
                            data+='\\"'+param+'\\" : \\"'+postparam[param]+'\\",'
                        else:
                            data+='\\"'+param+'\\" : '+str(postparam[param])+','
                    data=data[:-1]+"}"
                else:
                    data=postparam
                post+=[data]
            if not params:
                text=self.jd.call(actionurl,httpaction,rid=False,postparams=post,action=action)
            else:
                text=self.jd.call(actionurl,httpaction,rid=False,params=params,postparams=post,action=action)
        else:
            text=self.jd.call(actionurl,httpaction,rid=False,action=True)
        if not text:
            return False,False
        return True, text

    def addLinks(self, links, packagename="", autostart=True, extractPassword="", downloadPassword=""):
        status, resp=self.action("/linkgrabberv2/addLinks",postparams=[{"autostart" : autostart,
                                                                        "links" : links.encode('ASCII'),
                                                                        "packageName" : packagename.encode('ASCII'),
                                                                        "extractPassword" : extractPassword,
                                                                        "priority" : "DEFAULT",
                                                                        "downloadPassword" : downloadPassword}])
        self.jd.updateRid()
        return resp

    def getDownloadPackages(self, finished=True, status=True, saveTo=True):
        resp=self.action("/downloadsV2/queryPackages", postparams=[{"finished":finished,
                                                                    "status":status,
                                                                    "saveTo":saveTo}])
        self.jd.updateRid()
        return resp

    def getLinkgrabberPackages(self, finished=True, status=True, saveTo=True):
        resp=self.action("/linkgrabberv2/queryPackages", postparams=[{"finished":finished,
                                                                    "status":status,
                                                                    "saveTo":saveTo}])
        self.jd.updateRid()
        return resp

    def __actionUrl(self):
        if not self.jd.sessiontoken:
            return False
        return "/t_"+self.jd.sessiontoken+"_"+self.dId

class jDownloaderAPI:
    """
    Main class for connecting to JD API.

    """

    def __init__(self,email=None,password=None):
        """ This functions initializates the myjdapi object.
        If email and password are given it will also connect try
        with that account.
        If it fails to connect it won't provide any error,
        you can check if it worked by checking if sessiontoken
        is not an empty string.

        :param email: My.Jdownloader User email
        :param password: My.Jdownloader User password

        """
        self.rid=int(time.time())
        self.api_url = "http://api.jdownloader.org"
        self.appkey = "http://git.io/vmcsk"
        self.apiVer = 1
        self.__devices = []
        self.loginSecret = False
        self.deviceSecret = False
        self.sessiontoken = False
        self.regaintoken = False
        self.serverEncryptionToken = False
        self.deviceEncryptionToken = False

        if email!=None and password!=None:
            if not self.connect(email,password):
                raise ConnectionError
    def __secretcreate(self,email,password,domain):
        """Calculates the loginSecret and deviceSecret

        :param email: My.Jdownloader User email
        :param password: My.Jdownloader User password
        :param domain: The domain , if is for Server (loginSecret) or Device (deviceSecret)
        :return: secret hash

        """
        h = hashlib.sha256()
        h.update(email.lower().encode('utf-8')+password.encode('utf-8')+domain.lower().encode('utf-8'))
        secret=h.digest()
        return secret
    def __updateEncryptionTokens(self):
        """
        Updates the serverEncryptionToken and deviceEncryptionToken

        """
        if not self.serverEncryptionToken:
            oldtoken=self.loginSecret
        else:
            oldtoken=self.serverEncryptionToken
        h = hashlib.sha256()
        h.update(oldtoken+bytearray.fromhex(self.sessiontoken))
        self.serverEncryptionToken=h.digest()
        h = hashlib.sha256()
        h.update(self.deviceSecret+bytearray.fromhex(self.sessiontoken))
        self.deviceEncryptionToken=h.digest()
    def __signaturecreate(self,key,data):
        """
        Calculates the signature for the data given a key.

        :param key:
        :param data:

        """
        h = hmac.new(key,data.encode('utf-8'),hashlib.sha256)
        signature=h.hexdigest()
        return signature
    def __decrypt(self,secretServer,data):
        """
        Decrypts the data from the server using the provided token

        :param secretServer:
        :param data:

        """
        iv=secretServer[:len(secretServer)//2]
        key=secretServer[len(secretServer)//2:]
        decryptor = AES.new(key,AES.MODE_CBC,iv)
        decrypted_data = unpad(decryptor.decrypt(base64.b64decode(data)))
        return decrypted_data

    def __encrypt(self,secretServer,data):
        """
        Encrypts the data from the server using the provided token

        :param secretServer:
        :param data:

        """
        data=pad(data.encode('utf-8'))
        iv=secretServer[:len(secretServer)//2]
        key=secretServer[len(secretServer)//2:]
        encryptor = AES.new(key,AES.MODE_CBC,iv)
        encrypted_data = base64.b64encode(encryptor.encrypt(data))
        return encrypted_data.decode('utf-8')

    def updateRid(self):
        """
        Adds 1 to rid
        """
        self.rid=int(time.time())
        #self.rid=self.rid+1

    def connect(self,email,password):
        """Establish connection to api

        :param email: My.Jdownloader User email
        :param password: My.Jdownloader User password
        :returns: boolean -- True if succesful, False if there was any error.

        """
        self.loginSecret=self.__secretcreate(email,password,"server")
        self.deviceSecret=self.__secretcreate(email,password,"device")
        text=self.call("/my/connect","GET",rid=True,params=[("email",email),("appkey",self.appkey)])
        if not text:
            return False
        self.updateRid()
        self.sessiontoken=text["sessiontoken"]
        self.regaintoken=text["regaintoken"]
        self.__updateEncryptionTokens()
        return True

    def reconnect(self):
        """
        Restablish connection to api.

        :returns: boolean -- True if succesful, False if there was any error.

        """
        if not self.sessiontoken:
            return False
        text=self.call("/my/reconnect","GET",rid=True,params=[("sessiontoken",self.sessiontoken),("regaintoken",self.regaintoken)])
        if not text:
            return False
        self.updateRid()
        self.sessiontoken=text["sessiontoken"]
        self.regaintoken=text["regaintoken"]
        self.__updateEncryptionTokens()
        return True

    def disconnect(self):
        """
        Disconnects from  api

        :returns: boolean -- True if succesful, False if there was any error.

        """
        if not self.sessiontoken:
            return False
        text=self.call("/my/disconnect","GET",rid=True,params=[("sessiontoken",self.sessiontoken)])
        if not text:
            return False
        self.updateRid()
        self.loginSecret = ""
        self.deviceSecret = ""
        self.sessiontoken = ""
        self.regaintoken = ""
        self.serverEncryptionToken = False
        self.deviceEncryptionToken = False
        return True

    def getDevices(self):
        """
        Gets available devices. Use listDevices() to get the devices list.

        :returns: boolean -- True if succesful, False if there was any error.

        """
        if not self.sessiontoken:
            return False
        text=self.call("/my/listdevices","GET",rid=True,params=[("sessiontoken",self.sessiontoken)])
        if not text:
            return False
        self.updateRid()
        self.__devices=text["list"]
        return True

    def listDevices(self):
        """
        Returns available devices. Use getDevices() to update the devices list.

        Each device in the list is a dictionary like this example:

        {
            'name': 'Device',

            'id': 'af9d03a21ddb917492dc1af8a6427f11',

            'type': 'jd'

        }

        :returns: list -- list of devices.

        """
        return self.__devices

    def getDevice(self,deviceid=False,name=False):
        """
        Returns a jddevice instance of the device

        :param deviceid:

        """
        if deviceid:
            for device in self.__devices:
                if device["id"]==deviceid:
                    return jDownloaderDevice(self,device)
        elif name:
            for device in self.__devices:
                if device["name"]==name:
                    return jDownloaderDevice(self,device)
        return False

    def call(self,url,httpaction="GET",rid=True,params=False,postparams=False,action=False):
        if not action:
            if (params):
                call=url
                for index,param in enumerate(params):
                    if index==0:
                        call+="?"+param[0]+"="+urllib.quote(param[1])
                    else:
                        call+="&"+param[0]+"="+urllib.quote(param[1])
                        # Todo : Add an exception if the param is loginSecret so it doesn't get url encoded.
                if rid:
                    call+="&rid="+str(self.rid)

                if not self.serverEncryptionToken:
                    call+="&signature="+str(self.__signaturecreate(self.loginSecret,call))
                else:
                    call+="&signature="+str(self.__signaturecreate(self.serverEncryptionToken,call))
            if (postparams):
                pass

        else:
            call=url+action
            if (params):

                for index,param in enumerate(params):
                    if index==0:
                        call+="?"+param[0]+"="+urllib.quote(param[1])
                    else:
                        call+="&"+param[0]+"="+urllib.quote(param[1])
                        # Todo : Add an exception if the param is loginSecret so it doesn't get url encoded.
                if rid:
                    call+="&rid="+str(self.rid)

                if not self.serverEncryptionToken:
                    call+="&signature="+str(self.__signaturecreate(self.loginSecret,call))
                else:
                    call+="&signature="+str(self.__signaturecreate(self.serverEncryptionToken,call))
            if (postparams):
                data='{"url":"'+action+'","params":["'
                for index,param in enumerate(postparams):
                    if index != len(postparams)-1:
                        data+=param+'","'
                    else:
                        data+=param+'"],'
            else:
                data='{"url":"'+action+'",'
            data+='"rid":'+str(self.rid)+',"apiVer":1}'
            print(data)
            encrypteddata=self.__encrypt(self.deviceEncryptionToken,data);

        url=self.api_url+call
        print(url)
        if httpaction=="GET":
            encryptedresp=requests.get(url)
        elif httpaction=="POST":
            encryptedresp=requests.post(url,headers={"Content-Type": "application/aesjson-jd; charset=utf-8"},data=encrypteddata)
        if encryptedresp.status_code != 200:
            return False
        if not action:
            if not self.serverEncryptionToken:
                response=self.__decrypt(self.loginSecret,encryptedresp.text)
            else:
                response=self.__decrypt(self.serverEncryptionToken,encryptedresp.text)
        else:
            response=self.__decrypt(self.deviceEncryptionToken,encryptedresp.text)
        jsondata=json.loads(response.decode('utf-8'))
        if jsondata['rid']!=self.rid:
            return False
        return jsondata

config = [{
    'name': 'jdownloader',
    'groups': [
        {
            'tab': 'downloaders',
            'list': 'download_providers',
            'name': 'jdownloader',
            'label': 'jDownloader',
            'description': 'Use My JDownloader Service to download OCHs.',
            'wizard': True,
            'options': [
                {
                    'name': 'enabled',
                    'default': 0,
                    'type': 'enabler',
                    'radio_group': 'OCH',
                },
                {
                    'name': 'email',
                    'description': 'Credentials for MyJD-Service',
                },
                {
                    'name': 'password',
                    'type': 'password',
                    'description': 'Credentials for MyJD-Service',
                },
                {
                    'name': 'deviceID',
                    'type': 'dropdown',
                },
                {
                    'name': 'delete_failed',
                    'default': True,
                    'advanced': True,
                    'type': 'bool',
                    'description': 'Delete a release after the download has failed.',
                },
            ],
        }
    ],
}]