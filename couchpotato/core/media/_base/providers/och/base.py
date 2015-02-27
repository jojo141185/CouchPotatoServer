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
    qualitySearch = True
    blockRetrySearch = 900  # Seconds, block search for same title and quality
    lastSearched = {}       # Dictionary of last searches {TITLE:{QUALITY:SEARCHTIME}}

    # TODO: set an attribute to specify the main language of this provider. So in a multi-language environment this provider will only be used if the user is searching for this movie language.

    def possibleTitles(self, raw_title):
        # Remove spaces and replace brackets and other special chars with a whitespace
        regPattern = re.compile('\W+|_',re.UNICODE)
        titleStr_simple = ' '.join(regPattern.split(raw_title.lower()))
        # Replace Umlaute (i.e. ä->ae), remove accents, only ASCII and "-_.()" chars
        titleStr_safe = toSafeString(stripAccents(handle_special_chars(titleStr_simple)))
        # Replace everything after (:,-,|,(,[,{,;)
        titleStr_short1 = re.sub(u'[:\-\|\(\[\{\;].*$', '', raw_title)
        titleStr_short2 = stripAccents(handle_special_chars(titleStr_short1))

        titles = [
            titleStr_simple.lower(),
            unicode(titleStr_safe).lower(),
            titleStr_short2.lower()
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
            log.error("Can't add search result to cache.")

    def hasAlreadyBeenSearched(self, url):
        try:
            now = time.time()
            # clean list from old searches (<900 s)
            for entry in self.lastSearched:
                if self.lastSearched[entry][0] < (now - self.blockRetrySearch):
                    del self.lastSearched[entry]

            if url in self.lastSearched:
                return True
            else:
                return False
        except:
            log.error("Could not evaluate search from cache.")
        return False

    def search(self, media, quality):
        if self.isDisabled():
            return []

        # Login if needed
        if self.urls.get('login') and not self.login():
            log.error('Failed to login to: %s', self.getName())
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
            if not self.qualitySearch:
                quality = None
            newResults = []
            for title in self.possibleTitles(media_title):
                self._searchOnTitle(title, media, quality, results)

            # append to results list (triggers event that surveys release quality)
            for result in newResults:
                results.append(result)  # gets cleared if release not matched

        return results

