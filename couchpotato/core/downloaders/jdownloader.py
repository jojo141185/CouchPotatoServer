import json
import traceback
from couchpotato.core._base.downloader.main import DownloaderBase
from couchpotato.core.helpers.encoding import tryUrlencode
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
        if not media: media = {}
        if not data: data = {}

        try:
            jd_packagename = self.createFileName(data, filedata, media)
            links = str([x for x in json.loads(data.get('url'))])
            response = self.call("linkgrabberv2/addLinks",{"links":links,"packageName": jd_packagename , "autostart": True})

            packageUUID = self.getUUIDbyPackageName(jd_packagename)
            return self.downloadReturnId(packageUUID)

        except:
            log.error('Something went wrong sending the jDownloader file: %s', traceback.format_exc())
            return False

    def getUUIDbyPackageName(self, name):
        response = self.call("linkgrabberv2/queryPackages")

        if name not in response.data:
            return None

        for data in response.data:
            if data['name'] == name:
                return data['uuid']

        return None


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