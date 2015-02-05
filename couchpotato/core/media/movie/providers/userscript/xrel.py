import json
import traceback
from couchpotato.core.event import addEvent
from couchpotato.core.helpers.encoding import tryUrlencode
from couchpotato.core.helpers.variable import md5
from couchpotato.core.logger import CPLog
from couchpotato.core.media.movie.providers.base import MovieProvider

log = CPLog(__name__)

__author__ = 'Sebastian'

autoload = 'xrelApi'

class xrelApi(MovieProvider):

    def __init__(self):
        addEvent('movie.verify', self.verify, priority = 1)

    def verify(self, relName, id):
        release = self.getInfo(relName)
        if release != None:
            for uri in release['payload']['ext_info']['uris']:
                if 'imdb' in uri and id == uri.split(':')[1]:
                    log.debug('%s verified by %s' & (relName, release['payload']['link_href']))
                    return True
        return False

    def getInfo(self, relName):
        return self.request('info', {'dirname': relName})

    def request(self, call = '', params = {}, return_key = None):

        params = dict((k, v) for k, v in params.items() if v)
        params = tryUrlencode(params)

        try:
            url = 'http://api.xrel.to/api/release/%s.json?%s' % (call, '%s&' % params if params else '')
            data = self.getJsonData(url, show_error = False)
        except:
            log.debug('Movie not found: %s, %s', (call, params))
            data = None

        if data and return_key and return_key in data:
            data = data.get(return_key)

        return data

    def getJsonData(self, url, decode_from = None, **kwargs):

        cache_key = md5(url)
        data = self.getCache(cache_key, url, **kwargs)

        if data:
            try:
                data = data.strip()[11:-3]
                if decode_from:
                    data = data.decode(decode_from)

                return json.loads(data)
            except:
                log.error('Failed to parsing %s: %s', (self.getName(), traceback.format_exc()))

        return []