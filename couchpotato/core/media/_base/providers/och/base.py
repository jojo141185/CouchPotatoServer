# -*- coding: utf-8 -*-
from couchpotato.core.event import fireEvent
from couchpotato.core.helpers.variable import removeDuplicate
from couchpotato.core.helpers.encoding import stripAccents, handle_special_chars, toSafeString
from couchpotato.core.media._base.providers.base import YarrProvider, ResultList
from couchpotato.core.logger import CPLog
import time
import re

log = CPLog(__name__)

class OCHProvider(YarrProvider):

    protocol = 'och'
    lastSearched = {}       # Dictionary of last searches {URL:[TIME:RESULTS]}
    chacheTimeDefault = 900 # Seconds, block search for same title and quality

    # TODO: set an attribute to specify the main language of this provider. So in a multi-language environment this provider will only be used if the user is searching for this movie language.

    def possibleTitles(self, raw_title):
        titleStr_raw = raw_title.lower()
        # Remove spaces and replace brackets and other special chars with a whitespace
        regPattern_simple = re.compile('\W+|_+',re.UNICODE)
        titleStr_simple = ' '.join(regPattern_simple.split(titleStr_raw)).strip()
        # Replace Umlaute (i.e. ä->ae), remove accents, only ASCII and "-_.()" chars
        titleStr_safe = toSafeString(stripAccents(handle_special_chars(titleStr_simple)))
        # Replace everything after (:,-,|,(,[,{,;)
        titleStr_shortRaw = re.sub(u'[:\-\|\(\[\{\;].*$', '', titleStr_raw).strip()
        titleStr_shortSimple = ' '.join(regPattern_simple.split(titleStr_shortRaw)).strip()
        titleStr_shortSafe = toSafeString(stripAccents(handle_special_chars(titleStr_shortSimple)))

        titles = [
            titleStr_raw,
            titleStr_simple,
            unicode(titleStr_safe),
            titleStr_shortRaw,
            titleStr_shortSimple,
            unicode(titleStr_shortSafe)
        ]

        return removeDuplicate(titles)

    def download(self, url = '', nzb_id = ''):
        return url

    def loginDownload(self, url = '', nzb_id = ''):
        return url

    def addLastSearchResult(self, url, newResult):
        now = time.time()
        results = self.lastSearched.get(url, [])
        try:
            results.extend(newResult)
            self.lastSearched[url] = [now, results]
        except:
            log.error(u"Can't add search result to cache.")

    def getLastSearchResult(self, url):
        try:
            results = self.lastSearched.get(url, [])[1]
            return results
        except:
            log.error(u"Can't get search result for url '%s' from cache." % url)
            return []

    def hasAlreadyBeenSearched(self, url):
        try:
            now = time.time()
            if self.conf('time_cached'):
                chacheTime = self.conf('time_cached')
            else:
                chacheTime = self.chacheTimeDefault
            # clean list from old searches (Default >900 s)
            for entry in self.lastSearched:
                if self.lastSearched[entry][0] < (now - chacheTime):
                    del self.lastSearched[entry]
            if url in self.lastSearched:
                return True
            else:
                return False
        except:
            log.error(u"Could not evaluate search from cache.")
        return False

    def search(self, media, quality):
        if self.isDisabled():
            return []

        # Login if needed
        if self.urls.get('login') and not self.login():
            log.error(u'Failed to login to: %s', self.getName())
            return []

        # Create result container
        imdb_results = hasattr(self, '_search')
        results = ResultList(self, media, quality, imdb_results = imdb_results)

        # Do search based on imdb id
        if imdb_results:
            self._search(media, quality, results)

        # Search possible titles
        else:
            media_title = fireEvent('library.query', media, include_year = False, single = True)
            for title in self.possibleTitles(media_title):
                self._searchOnTitle(title, media, quality, results)

        return results

