# -*- coding: utf-8 -*-

import re
from datetime import date
import urllib
import json

from couchpotato.core.helpers.encoding import simplifyString, handle_special_chars
from couchpotato.core.logger import CPLog
from couchpotato.core.media._base.providers.och.base import OCHProvider
from couchpotato.core.helpers.variable import tryInt
from bs4 import BeautifulSoup, NavigableString


log = CPLog(__name__)

class Base(OCHProvider):

    qualitySearch = True
    urls = {
        'search': 'http://www.flower-blog.org/',
    }

    def _searchOnTitle(self, title, movie, quality, results):
        newResults = []
        log.debug(u"Search for '%s'." % title)
        url = u"%s?s=%s" % (self.urls['search'], title)
        if not self.hasAlreadyBeenSearched(url):
            newResults = self.do_search(title)
            # add result to search cache
            self.addLastSearchResult(url, newResults)
        else:
            log.debug(u"Already searched for '%s' in the last %d seconds. Get result from cache."
                      % (title, self.conf('time_cached')))
            newResults = self.getLastSearchResult(url)

        # append to results list (triggers event that surveys release quality)
        for result in newResults:
            results.append(result)  # gets cleared if release not matched
        return results

    def do_search(self, title):
        # TODO: Search result has more than one page <vorwaerts> link
        data = self.getHTMLData(self.urls['search'], data={'s': title})
        results = []
        linksToMovieDetails = self.parseSearchResult(data)
        num_results = len(linksToMovieDetails)
        log.info(u"Found %s %s on search for '%s'." %(num_results, 'release' if num_results == 1 else 'releases', title))
        for movieDetailLink in linksToMovieDetails:
            if not self.hasAlreadyBeenSearched(movieDetailLink):
                log.debug("fetching data from Movie's detail page %s" % movieDetailLink)
                data = self.getHTMLData(movieDetailLink)
                result = self.parseMovieDetailPage(data)
                if result:
                    result['id'] = 0
                    for url in json.loads(result['url']):
                        r = result.copy()  #each mirror to a separate result
                        r['url'] = json.dumps([url])
                        results.append(r)
            else:
                log.debug(u"Detail page already parsed in the last %d seconds. Get result from cache."
                          % self.conf('time_cached'))
                results = self.getLastSearchResult(movieDetailLink)
        return results


    # ===============================================================================
    # INTERNAL METHODS
    #===============================================================================
    def parseContent(self, content):
        res = {}
        res["year"] = []
        res["size"] = []
        res["url"] = []
        res["pwd"] = []
        try:
            log.debug("Look for release info and dl-links on Movie's detail page.")
            try:
                matches = content.findAll('p', recursive=True)
                for match in matches:
                    # YEAR
                    keyWords_date = u'(start|release)'
                    if re.search(keyWords_date, match.text, re.I):
                        try:
                            regPattern = r".*%s\:\s*(((?P<day>[0-9]{2})\.)?(?P<month>[0-9]{2})\.)?(?P<year>[0-9]{4})" % (
                                keyWords_date)
                            match_relDate = re.search(regPattern, match.text, re.I)
                            res["year"] = match_relDate.group('year')
                            log.debug('Found release year of movie: %s' % res["year"])
                        except (AttributeError, TypeError):
                            log.debug('Could not fetch year of movie release from details website.')
                    # SIZE
                    keyWords_size = u'(größe|groeße|groesse|size)'
                    if re.search(keyWords_size, match.text, re.I):
                        try:
                            regPattern = r".*%s\:\s*(?P<size>[0-9,\.]+)\s?(?P<unit>(TB|GB|MB|kB))" % (keyWords_size)
                            match_relSize = re.search(regPattern, match.text, re.I)
                            res["size"] = self.parseSize(match_relSize.group('size') + ' ' + match_relSize.group('unit'))
                            log.debug(u'Found size of release: %s MB' % res['size'])
                        except (AttributeError, TypeError):
                            log.debug('Could not fetch size of release from details website.')

                    # DOWNLOAD Links
                    keyWords_dl = u'(download|mirror)'
                    if re.search(keyWords_dl, match.text, re.I):
                        try:
                            link = match.a
                            url = link["href"]
                            hoster = link.text
                            # check for accapted hoster list in config
                            acceptedHosters = self.conf('hosters')
                            if not acceptedHosters or acceptedHosters == '':
                                log.error('Hosterlist seems to be empty, please check settings.')
                                return None
                            # filter accepted hosters
                            for acceptedHoster in acceptedHosters.replace(' ', '').split(','):
                                if acceptedHoster in hoster.lower() and url not in res["url"]:
                                    res["url"].append(url)
                                    log.debug('Found new DL-Link %s on Hoster %s' % (url, hoster))
                        except (AttributeError, TypeError):
                            log.debug('Could not fetch URL or hoster from details website.')

                    # UNRAR PASSWORD
                    keyWords_pwd = u'(passwort|password)'
                    if re.search(keyWords_pwd, match.text, re.I):
                        try:
                            regPattern = r".*%s\:\s*(?P<pwd>[^\s]+)\s?" % (keyWords_pwd)
                            match_relSize = re.search(regPattern, match.text, re.I)
                            res["pwd"] = match_relSize.group('pwd')
                            log.debug("Found password '%s' to unzip downloaded files." % (res["pwd"]))
                        except (AttributeError, TypeError):
                            log.debug('Could not fetch password from details website.')

            except (AttributeError, TypeError, KeyError):
                log.error('Could not fetch detailed Release info from Website.')

            if res["url"] != []:
                res["url"] = json.dumps(res["url"])  #List 2 string for db-compatibility
                return res
            else:
                log.debug('No DL-Links on Hoster(s) [%s] found :(' % (self.conf('hosters')))
                return None

        except (AttributeError, TypeError, KeyError):
            return None

    def parseSubHeader(self, subHeader):
        res = {}
        res["age"] = []
        try:
            categories = subHeader.findAll('a')
            #res["categories"] = []
            #for category in categories:
            #res["categories"].append(category.text)

            releaseDate = subHeader.text
            match = re.search(r"[\|]\s+(?P<date>[^\s]*)\s\-\s(?P<time>[^\s]*)\s+", subHeader.text)
            relDate = match.group('date').split('.')
            res["age"] = (date.today() - date(tryInt(relDate[2]), tryInt(relDate[1]),
                                              tryInt(relDate[0]))).days

        except AttributeError:
            log.error("error parsing subHeader")
        except (TypeError, KeyError, IndexError):
            pass
        return res

    def parseHeader(self, header):
        res = {}
        res['name'] = []
        res['name'] = header.h2.a.text
        return res


    def parseMovieDetailPage(self, data):
        dom = BeautifulSoup(data, "html5lib")
        pageCenter = dom.find('div', attrs={"class": "main_cent"})

        header = pageCenter.find('div', attrs={"class": "head"})
        subHeader = pageCenter.find('div', attrs={"class": "alignlefttt"})
        content = pageCenter.find('div', attrs={"class": "content_txt"})

        res = {}
        if header and content and subHeader:
            try:
                res.update(self.parseHeader(header))
                res.update(self.parseSubHeader(subHeader))
                res.update(self.parseContent(content))
            except TypeError:
                #ignore release if content,header or subHeader couldn't be parsed correctly
                return
        return res

    def parseSearchResult(self, data):
        #print data
        try:
            dom = BeautifulSoup(data, "html5lib")

            #content = dom.find('div', attrs={"class": "main_cent"})
            movieEntries = dom.findAll('div', attrs={"class": "table2"})
            linksToMovieDetails = []
            for movieEntrie in movieEntries:
                headers = movieEntrie.findAll('div', attrs={"class": "head"})
                for head in headers:
                    link = head.a
                    linksToMovieDetails.append(link['href'])
            num_results = len(linksToMovieDetails)
            log.info('Found %s %s on search.', (num_results, 'release' if num_results == 1 else 'releases'))
            return linksToMovieDetails
        except:
            log.debug('There are no search results to parse!')
            return []


config = [{
              'name': 'flowerblog',
              'groups': [
                  {
                      'tab': 'searcher',
                      'list': 'och_providers',
                      'name': 'Flower-Blog',
                      'description': 'See <a href="http://www.flower-blog.org">Flower-Blog.org</a>',
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
                              'default': '',
                              'placeholder': 'Example: uploaded,share-online',
                              'description': 'List of Hosters separated by ",". Should be at least one!'
                          },
                      ],
                  },
              ],
          }]