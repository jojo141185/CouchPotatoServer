#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

import re
import json
import time
from datetime import date
from bs4 import BeautifulSoup

from couchpotato.core.logger import CPLog
from couchpotato.core.media._base.providers.och.base import OCHProvider
from couchpotato.core.helpers.variable import tryInt


log = CPLog(__name__)


class Base(OCHProvider):

    qualitySearch = False
    urls = {
        'base_url' : 'http://www.nox.to/',
        'login': 'http://www.nox.to/login',
        'login_check': 'http://www.nox.to/profile',
        'search': 'http://www.nox.to/suche',
        'download': u'http://www.nox.to/download2?item_id=%s&item_type=%s&captcha_challange='
    }

    def getLoginParams(self):
        return {'username': self.conf('username'),
                'password': self.conf('password')
        }

    # checks directly after login with login url
    def loginSuccess(self, output):
        dom = BeautifulSoup(output, "html5lib")
        try:
            welcomeString = dom.body.find('div', {'id': 'news-title'}).text
            found = re.search(u'Willkommen\s%s' % self.conf('username'), welcomeString, re.I)
            if found is not None:
                return True
        except Exception, err:
            log.error(u"Could not login.")
            log.error(dom.body.text)
            raise
        return False

    # checks all x minutes if still logged in with login_check url
    def loginCheckSuccess(self, output):
        dom = BeautifulSoup(output, "html5lib")
        try:
            menuBar = dom.body.find('div', {'id':'menubar'})
            menuItems = menuBar.find('ul', {'id':'menu-items-static'})
            found = menuItems.find('a', attrs={'title':re.compile('Ausloggen')})
            if found is not None:
                return True
        except Exception, err:
            log.error(u"Couldn't check if login was successful.")
            import traceback; log.error(traceback.format_exc());
        return False

    # function gets called for every title in possibleTitles
    def _searchOnTitle(self, title, movie, quality, results):
        newResults = []
        log.debug(u"Search for '%s'." % title)
        url = u"%s?query=%s" % (self.urls['search'], title)
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
        data = self.getHTMLData(self.urls['search'], data={'query': title})
        results = []
        # get links for detail page of each search result
        linksToMovieDetails = self.parseSearchResult(data)
        num_results = len(linksToMovieDetails)
        log.info(u"Found %s %s on search for '%s'." %(num_results, 'release' if num_results == 1 else 'releases', title))
        for movieDetailLink in linksToMovieDetails:
            pattern = self.urls['base_url']+u'|^/'
            movieDetailLink = re.sub(pattern,'',movieDetailLink)
            fullMovieDetailLink = self.urls['base_url'] + movieDetailLink
            if not self.hasAlreadyBeenSearched(fullMovieDetailLink):
                log.debug(u"fetching data from Movie's detail page %s" % fullMovieDetailLink)
                data = self.getHTMLData(fullMovieDetailLink)
                result_raw = self.parseMovieDetailPage(data)
                if result_raw:
                    result_raw['id'] = 0
                    for url in json.loads(result_raw['url']):
                        result = result_raw.copy()  #each mirror to a separate result
                        result['url'] = json.dumps([url])
                        results.append(result)
                # add result to search cache
                self.addLastSearchResult(fullMovieDetailLink,results)
            else:
                log.debug(u"Detail page already parsed in the last %d seconds. Get result from cache."
                          % self.conf('time_cached'))
                results = self.getLastSearchResult(fullMovieDetailLink)
        return results

    # ===============================================================================
    # INTERNAL METHODS
    #===============================================================================
    def parseMovieDetailPage(self, data):
        dom = BeautifulSoup(data)
        #content = dom.body.find('div', id='content', recursive=True)

        params = dom.body.find('div', id='item-params', recursive=True)
        #description = dom.find('div', id='item-description', recursive=False) - unused
        downloadTab = dom.body.find('div', id='item-user-bar-downloaded', recursive=True)

        try:
            infoContent = self.parseInfo(params)
            #descContent = self.parseDesc(description) - unused
            dlContent = self.parseDl(downloadTab)
        except:
            dlContent = {}
            infoContent = {}
            log.error(u"something went wrong when parsing post of release.")

        res = {}
        res.update(infoContent)
        res.update(dlContent)
        return res

    def parseSearchResult(self, data):
        #print data
        try:
            urls = []
            linksToMovieDetails = []
            dom = BeautifulSoup(data, "html5lib")
            content = dom.body.find('div', attrs={'id':'content'}, recursive=True)
            sections = content.findAll('div', attrs={'id':re.compile('.+-result-title')}, recursive=False)

            # check if direct landing on detail page (single match)
            items = content.find('div', attrs={'id':'item-params'}, recursive=True)
            if items and len(sections) == 0:
                # add own URL
                ownUrl = dom.head.find('meta', attrs={'property':'og:url'}, recursive=True)
                if ownUrl:
                    urls.append(ownUrl['content'])
                # Extract links to other qualities of this movie
                pattern = 'margin-top: \d+px; margin-left: \d+px; text-align: center'
                otherLinks = content.findAll('p', attrs={'style':re.compile(pattern)}, recursive=True)
                for link in otherLinks:
                    urls.append(link.a['href'])
            else:
                #Suche nur auf Kategorien von nox.to beschränken abhaengig von quality
                acceptedSections = ["movie-result-title", "hd-result-title"]
                for section in sections:
                    if section['id'].lower() in acceptedSections:
                        tblItems = section.findNext('table', attrs={'class': 'result-table-item'})
                        sectLinks = tblItems.findAll('td', attrs={'class': 'result-table-item-cell'})
                        for link in sectLinks:
                            urls.append(link.a['href'])
            return urls
        except:
            log.debug(u'Parsing of search results failed!')
            return []


    def parseInfo(self, info):
        rows = info.table.findAll('tr')
        res = {}

        for row in rows:
            columns = row.findAll('td', attrs={'class': re.compile('item-params-.+')})
            for column in columns:
                try:
                    # REL_DATE
                    keyWords_date = u'(datum|date)'
                    date_Pattern = r"(?P<day>[0-9]{2})\.(?P<month>[0-9]{2})\.(?P<year>[0-9]{4})"
                    if re.search(keyWords_date, column.b.text, re.I):
                        rawDate = column.nextSibling.text
                        match = re.search(date_Pattern, rawDate, re.I)
                        res['age'] = (date.today() - date(tryInt(match.group('year')), tryInt(match.group('month')),
                                                         tryInt(match.group('day')))).days
                        log.debug(u'Found age of release: %s' % res["age"])

                    # YEAR
                    keyWords_year = u'(jahr|year)'
                    if re.search(keyWords_year, column.b.text, re.I):
                        res['year'] = column.nextSibling.text
                        log.debug(u'Found release year of movie: %s' % res["year"])

                    # SIZE
                    keyWords_size = u'(größe:|groeße:|groesse:|size:)'
                    if re.search(keyWords_size, column.b.text, re.I):
                        res['size'] = self.parseSize(column.nextSibling.text)
                        log.debug(u'Found size of release: %s MB' % res['size'])

                    # IMDB
                    keyWords_id = u'auf\sIMdb'
                    imdbUrl_pattern = u'(?P<id>tt[0-9]+)\/'
                    if re.search(keyWords_id, column.b.text, re.I):
                        url = column.nextSibling.a['href']
                        match = re.search(imdbUrl_pattern, url, re.I)
                        res['description'] = match.group('id')
                        log.debug(u'Found imdb-id of release: %s' % res['description'])

                    #REL_Name
                    keyWords_name = u'(releasename:)'
                    if re.search(keyWords_name, column.b.text, re.I):
                        res['name'] = column.nextSibling.a['title']
                        log.debug(u'Found name of release: %s' % res['name'])
                except AttributeError:
                    pass

        for elem in ['year', 'name', 'description', 'size', 'age']:
            if res.get(elem, None) is None:
                log.debug(u'Could not fetch %s of movie release from details website.' % elem)

        return res

    def parseDl(self, post):
        url = []
        pattern = u'\((?P<state>[0-9]+),(?P<dlsetting>[0-9]+),(?P<vtsetting>[0-9]+),(?P<type>[0-9]+),(?P<item_id>[0-9]+)\)'
        match = re.search(pattern, post.a['onmousedown'])
        data = self.getJsonData(self.urls['download'] % (match.group('item_id'), match.group('type')))


        pattern = u'http://(www\.)?(?P<hoster>[^\.]+)\.'
        for link in data['downloadfiles']:
            match = re.search(pattern, link, re.I)
            for acceptedHoster in self.conf('hosters').replace(' ', '').split(','):
                if acceptedHoster in match.group('hoster').lower():
                    url.append(link)

        return {"url": json.dumps(url)}


config = [{
              'name': 'nox',
              'groups': [
                  {
                      'tab': 'searcher',
                      'list': 'och_providers',
                      'name': 'nox',
                      'description': 'See <a href="http://www.nox.to">Nox.to</a>',
                      'wizard': True,
                      'options': [
                          {
                              'name': 'enabled',
                              'type': 'enabler',
                          },
                          {
                              'name': 'username',
                              'default': '',
                              'description': 'Username for login; Required to avoid captchas.'
                          },
                          {
                              'name': 'password',
                              'type': 'password',
                              'description': 'Password for login; Required to avoid captchas.'
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
