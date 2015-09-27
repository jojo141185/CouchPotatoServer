import json
import traceback
import os
import time
from couchpotato.core._base.downloader.main import DownloaderBase, ReleaseDownloadList
from couchpotato.core.helpers.encoding import tryUrlencode, sp
from couchpotato.core.helpers.variable import cleanHost
from couchpotato.core.logger import CPLog
from couchpotato.environment import Env
from libs.requests.exceptions import HTTPError

log = CPLog(__name__)

autoload = 'jDownloader'


class jDownloader(DownloaderBase):
    protocol = ['och']
    session_id = None

    def download(self, data = None, media = None, filedata = None):
        """ Send a package/links to the downloader

        :param data: dict returned from provider
            Contains the release information
        :param media: media dict with information
            Used for creating the filename when possible
        :param filedata: downloaded .dlc filedata
            regularly used for sending dlc files or something else,... until now not supported!
        :return: boolean
            One failed returns false, but the downloader should log his own errors
        """
        if not media: media = {}
        if not data: data = {}

        try:
            jd_packagename = self.createFileName(data, filedata, media)
            links = str([x for x in json.loads(data.get('url'))])
            response = self.call("linkgrabberv2/addLinks",{"links":links,"packageName": jd_packagename , "autostart": True})

            time.sleep(120) # wait 10 seconds for adding links to JD
            packageUUID = self.getUUIDbyPackageName(jd_packagename)
            if packageUUID:
                return self.downloadReturnId(packageUUID)
            else:
                return False
        except:
            log.error('Something went wrong sending the jDownloader file: %s', traceback.format_exc())
            return False

    def test(self):
        """ Check if connection works
        :return: bool
        """

        try:
            r = self.call("help")
        except:
            return False

        return True

    def getAllDownloadStatus(self, ids):
        """ Get status of all active downloads

        :param ids: list of (mixed) downloader ids
            Used to match the releases for this downloader as there could be
            other downloaders active that it should ignore
        :return: list of releases
        """

        raw_statuses = json.loads(self.call('downloadsV2/queryPackages',{"finished":"true", "status":"true","saveTo":"true"}))

        release_downloads = ReleaseDownloadList(self)
        for id in ids:
            packages = raw_statuses.get('data', [])
            package_ids = [x['uuid'] for x in packages]
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

        return release_downloads

    def getUUIDbyPackageName(self, name):
        for query in ("linkgrabberv2/queryPackages","downloadsV2/queryPackages"):
            response = json.loads(self.call(query, {}))

            packageNames = [x['name'] for x in response['data']]
            for packageName in packageNames:
                if name == packageName:
                    return response['data'][packageNames.index(packageName)]['uuid']


    def call(self, call, parameters = None, is_repeat = False, auth = False, **kwargs):
        # Always add session id to request
        if self.session_id:
            parameters['sessionid'] = self.session_id

        url = cleanHost(self.conf('host')) + call

        try:
            data = self.urlopen(url + '?' + json.dumps(parameters), timeout = 60, show_error = False, headers = {'User-Agent': Env.getIdentifier()}, **kwargs)

            if data:
                return data
        except HTTPError as e:
            sc = e.response.status_code
            if sc == 403:
                # Try login and do again
                if not is_repeat:
                    self.login()
                    return self.call(call, parameters = parameters, is_repeat = True, **kwargs)

            log.error('Failed to parsing %s: %s', (self.getName(), traceback.format_exc()))
        except:
            log.error('Failed to parsing %s: %s', (self.getName(), traceback.format_exc()))

        return {}

config = [{
    'name': 'jdownloader',
    'groups': [
        {
            'tab': 'downloaders',
            'list': 'download_providers',
            'name': 'jdownloader',
            'label': 'jDownloader',
            'description': 'Use <a href="http://www.nzbvortex.com/landing/" target="_blank">NZBVortex</a> to download NZBs.',
            'wizard': True,
            'options': [
                {
                    'name': 'enabled',
                    'default': 0,
                    'type': 'enabler',
                    'radio_group': 'OCH',
                },
                {
                    'name': 'host',
                    'default': 'http://localhost:3128',
                    'description': 'Hostname with port. Usually <strong>https://localhost:3128</strong>',
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