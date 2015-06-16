from couchpotato.core._base.downloader.main import DownloaderBase
from couchpotato.core.logger import CPLog

log = CPLog(__name__)

autoload = 'jDownloader'


class NZBVortex(DownloaderBase):
    protocol = ['och']

# class jdownloaderAPI(object):



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
                    'radio_group': 'nzb',
                },
                {
                    'name': 'host',
                    'default': 'https://localhost:4321',
                    'description': 'Hostname with port. Usually <strong>https://localhost:4321</strong>',
                },
                {
                    'name': 'api_key',
                    'label': 'Api Key',
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