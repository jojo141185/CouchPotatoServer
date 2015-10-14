#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

import re
import json
import time
from datetime import date
from bs4 import BeautifulSoup
import itertools

from couchpotato.core.logger import CPLog
from couchpotato.core.media._base.providers.och.base import OCHProvider
from couchpotato.core.helpers.variable import tryInt


log = CPLog(__name__)


class Base(OCHProvider):

    qualitySearch = False
    urls = {
        'base_url' : 'http://www.movie-blog.org/',
        'search': 'http://www.movie-blog.org/index.php',
    }

    # function gets called for every title in possibleTitles
    def _searchOnTitle(self, title, movie, quality, results):
        newResults = []
        log.debug(u"Search for '%s'." % title)
        url = u"%s?s=%s" % (self.urls['search'], title)
        if not self.hasAlreadyBeenSearched(url):
            newResults = self.do_search(title)
            # add result to search cache
            self.addLastSearchResult(url,newResults)
        else:
            log.debug(u"Already searched for '%s' in the last %d seconds. Get result from cache."
                      % (title, self.conf('time_cached')))
            newResults = self.getLastSearchResult(url)

        # append to results list (triggers event that surveys release quality)
        for result in newResults:
            results.append(result)  # gets cleared if release not matched
        return results

    def do_search(self, title):
        data = self.getHTMLData(self.urls['search'], data={'s': title})
        results = []
        # get links for detail page of each search result
        linksToMovieDetails = self.parseSearchResult(data, title, [])
        num_results = len(linksToMovieDetails)
        log.info(u"Found %s %s on search for '%s'." %(num_results, 'release' if num_results == 1 else 'releases', title))
        for movieDetailLink in linksToMovieDetails:
            if not self.hasAlreadyBeenSearched(movieDetailLink):
                log.debug(u"fetching data from Movie's detail page %s" % movieDetailLink)
                data = self.getHTMLData(movieDetailLink)
                result_raw = self.parseMovieDetailPage(data)
                if result_raw.has_key('url'):
                    for url in json.loads(result_raw['url']):
                        result = result_raw.copy()  #each mirror to a separate result
                        result['url'] = json.dumps([url])
                        results.append(result)
                # add result to search cache
                self.addLastSearchResult(movieDetailLink, results)
            else:
                log.debug(u"Detail page already parsed in the last %d seconds. Get result from cache."
                          % self.conf('time_cached'))
                results = self.getLastSearchResult(movieDetailLink)
        return results

    # ===============================================================================
    # INTERNAL METHODS
    #===============================================================================
    def parseMovieDetailPage(self, data):
        res = {}
        dom = BeautifulSoup(data)
        content = dom.body.find('div', id='content', recursive=True)

        # TITLE & ID
        titleObject = content.find('h1', recursive=True)
        res['name'] = titleObject.a.span.text
        res['id'] = titleObject['id'].split('-')[1]
        log.debug(u'Found title of release: %s' % res['name'])

        try:
            infoContent = self._parseDateUploaded(content.find('div', id='info').p)
            dlContent = self._parseEntry(content.find('div', attrs={'class':'eintrag2'}))
        except:
            dlContent = {}
            infoContent = {}
            log.error(u"something went wrong when parsing post of release %s." % res['name'])
            import traceback; log.error(traceback.format_exc())

        res.update(infoContent)
        res.update(dlContent)
        return res

    def getNextPage(self, data):
        pagenavi = data.find('div', attrs={'class': 'wp-pagenavi'}, recursive=True)
        if pagenavi and (pagenavi.findAll()[-1].attrs['class'][0] != 'current'):
            currentPageLink = pagenavi.find('span', attrs={'class': 'current'})
            nextPageLink = currentPageLink.nextSibling['href']
            return nextPageLink if re.match('.+page/[0-9]{1}/',nextPageLink) else None # stop when on page 10
        else:
            return None

    def parseSearchResult(self, data, title, linksToMovieDetails):
        try:
            dom = BeautifulSoup(data, "html5lib")
            content = dom.body.find('div', attrs={'id':'archiv'}, recursive=True)
            moviePosts = content.findAll('div', attrs={'class':'post'}, recursive=False)
            for moviePost in moviePosts:
                linksToMovieDetails.append(moviePost.h1.a['href'])

            linkToNextPage = self.getNextPage(content)
            if linkToNextPage:
                return self.parseSearchResult(self.getHTMLData(linkToNextPage, data={'s': title}), title, linksToMovieDetails)
            else:
                return linksToMovieDetails

        except:
            log.debug(u'Parsing of search results failed!')
            return []


    def _parseDateUploaded(self, info):
        def _getMonth(month):
            months = [u"januar", u"februar", u"märz", u"april", u"mai", u"juni", u"juli", u"august", u"september", u"oktober", u"november", u"dezember"]
            try:
                month = months.index(month.lower()) + 1
                return month
            except:
                raise

        res = {}

        # REL_DATE
        keyWords_date = u'(datum|date)'
        date_Pattern = r"(?P<day>[0-9]{1,2})\.\s?(?P<month>\S+)\s(?P<year>[0-9]{4})"
        for line in info.strings:
            if re.search(keyWords_date, line, re.I):
                match = re.search(date_Pattern, line, re.I)
                res['age'] = (date.today() - date(tryInt(match.group('year')), _getMonth(match.group('month')),
                                             tryInt(match.group('day')))).days
                log.debug(u'Found age of release: %s' % res["age"])
                break

        return res

    def _parseEntry(self, post):
        def recursiveSearch(sibling):
            try:
                return sibling['href']
            except (KeyError,TypeError):
                return None
        res = {}
        dlLinks = []
        # take the cover image as reference for finding next elements
        anchor = post.find('img', recursive=True)

        for paragraph in itertools.chain([anchor.parent], anchor.parent.next_siblings):
            if getattr(paragraph, 'text', False):
                for sibling in paragraph.children:
                    if getattr(sibling, 'text', False): # checks if text existent
                        #SIZE
                        keyWords_size = u'(größe:|groeße:|groesse:|size:)'
                        if re.search(keyWords_size, sibling.text, re.I):
                            res['size'] = self.parseSize(sibling.nextSibling.replace(",", "."))
                            log.debug(u'Found size of release: %s MB' % res['size'])

                         # IMDB
                        keyWords_id = u'IMDb'
                        imdbUrl_pattern = u'(?P<id>tt[0-9]+)\/?'
                        if re.search(keyWords_id, sibling.text, re.I):
                            i = 0
                            url = recursiveSearch(sibling)
                            while not url and i < 5:
                                sibling = sibling.nextSibling
                                url = recursiveSearch(sibling)
                                i+=1
                            match = re.search(imdbUrl_pattern, url, re.I)
                            try:
                                res['description'] = match.group('id')
                                log.debug(u'Found imdb-id of release: %s' % res['description'])
                            except:
                                log.debug(u'Could not parse imdb-id %s' % url)

                        # DOWNLOAD
                        keyWords_dl = u'(download|mirror)(\s#?[1-9])?:'
                        if re.search(keyWords_dl, sibling.text, re.I):
                            hoster = None
                            link = None
                            i = 0
                            while not link and i < 5:
                                sibling = sibling.nextSibling
                                link = recursiveSearch(sibling)
                                i+=1
                            hoster = sibling.text

                            for acceptedHoster in self.conf('hosters').replace(' ', '').split(','):
                                if acceptedHoster in hoster.lower():
                                    dlLinks.append(link)
                                    log.debug('Found new DL-Link %s on Hoster %s' % (link, hoster))

        res['url'] = json.dumps(dlLinks)
        return res

config = [{
              'name': 'movieblog',
              'groups': [
                  {
                      'tab': 'searcher',
                      'list': 'och_providers',
                      'name': 'movieblog',
                      'description': 'See <a href="http://www.movie-blog.org">Movie-Blog.org</a>',
                      'wizard': True,
                      'options': [
                          {
                              'name': 'enabled',
                              'type': 'enabler',
                          },
                          {
                              'name': 'time_cached',
                              'advanced': True,
                              'label': 'Cache Time',
                              'type': 'int',
                              'default': 900,
                              'description': 'Time in seconds, were search results are cached.',
                          },
                          {
                              'name': 'extra_score',
                              'advanced': True,
                              'label': 'Extra Score',
                              'type': 'int',
                              'default': 0,
                              'description': 'Starting score for each release found via this provider.',
                          },
                          {
                              'name': 'hosters',
                              'label': 'accepted Hosters',
                              'default': 'filer',
                              'placeholder': 'Example: filer',
                              'description': 'List of Hosters separated by ",". Should be at least one!'
                          },
                      ],
                  },
              ],
          }]
