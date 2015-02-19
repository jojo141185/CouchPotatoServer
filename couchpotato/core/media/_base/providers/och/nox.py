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
    lastSearchTime = None
    lastSearchTitle = None
    lastSearchResult = []
    urls = {
        'login': 'http://www.nox.to/login',
        'login_check': 'http://www.nox.to/profile',
        'search': 'http://www.nox.to/suche',
        'download': 'http://www.nox.to/download2?item_id=%s&item_type=%s&captcha_challange='
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
        except:
            log.error("Could not login.")
        return False

    # checks all x minutes if still logged in with login_check url
    def loginCheckSuccess(self, output):
        dom = BeautifulSoup(output, "html5lib")
        menuBar = dom.body.find('div', {'id':'menubar'})
        menuItems = menuBar.find('ul', {'id':'menu-items-static'})
        found = menuItems.find('a', attrs={'title':re.compile('Ausloggen')})
        if found is not None:
            return True
        return False

    def _searchOnTitle(self, title, movie, quality, results):
        # function gets called for every title in possibleTitles
        now = time.time()

        # only search consecutively for same title after 15 mins
        if self.lastSearchTitle != movie['title'] or self.lastSearchTime < (now - 900):
            # save parameters (title, time and results) for next search
            self.lastSearchTitle = movie['title']
            self.lastSearchTime = now
            self.lastSearchResult = []

            # build new title list to search for
            # with original and local(depending on preffered Language Code) title
            titles = []
            titles.append(movie['title'])
            titles.append(movie['info']['original_title'])

            # search for all titles in list
            for title in titles:
                # simplify and clean title string for nox-search engine
                title = re.sub(r'[:\-\+\|_#.*~]', ' ', title)
                title = re.sub(r'[\[\{()\}\],;]', '', title)
                #search for title
                searchResults = self.do_search('%s' % title)
                # append to results list (triggers event that surveys release quality)
                for result in searchResults:
                    results.append(result)  # gets cleared if release not matched
                    self.lastSearchResult.append(result)
        else:
            # copy back results from previous (identical) search
            for result in self.lastSearchResult:
                results.append(result)


    def do_search(self, title):
        data = self.getHTMLData(self.urls['search'], data={'query': title})
        results = []
        # get links for detail page of each search result
        linksToMovieDetails = self.parseSearchResult(data)
        for movieDetailLink in linksToMovieDetails:
            log.debug("fetching data from Movie's detail page %s" % movieDetailLink)
            data = self.getHTMLData('http://www.nox.to/' + movieDetailLink)
            result_raw = self.parseMovieDetailPage(data)
            if result_raw:
                result_raw['id'] = 0
                for url in json.loads(result_raw['url']):
                    result = result_raw.copy()  #each mirror to a separate result
                    result['url'] = json.dumps([url])
                    results.append(result)
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
            log.error("something went wrong when parsing post of release.")

        res = {}
        res.update(infoContent)
        res.update(dlContent)
        return res

    def parseSearchResult(self, data):
        #print data
        try:
            results = []
            linksToMovieDetails = []
            dom = BeautifulSoup(data, "html5lib")
            content = dom.body.find('div', attrs={'id':'content'}, recursive=True)
            sections = content.findAll('div', attrs={'id':re.compile('.+-result-title')}, recursive=False)
            # check if direct landing on detail page (single match)
            if len(sections) == 0:
                # Extract links to other qualities of this movie
                pattern = 'margin-top: \d+px; margin-left: \d+px; text-align: center'
                results.extend(content.findAll('p', attrs={'style':re.compile(pattern)}, recursive=True))
            else:
                #Suche nur auf Kategorien von nox.to beschränken abhaengig von quality
                acceptedSections = ["movie-result-title", "hd-result-title"]
                for section in sections:
                    if section['id'].lower() in acceptedSections:
                        tblItems = section.findNext('table', attrs={'class': 'result-table-item'})
                        results.extend(tblItems.findAll('td', attrs={'class': 'result-table-item-cell'}))
            for result in results:
                linksToMovieDetails.append(result.a['href'])
            num_results = len(linksToMovieDetails)
            log.info('Found %s %s on search.', (num_results, 'release' if num_results == 1 else 'releases'))
            return linksToMovieDetails
        except:
            log.debug('Parsing of search results failed!')
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
                        log.debug('Found age of release: %s' % res["age"])

                    # YEAR
                    keyWords_year = u'(jahr|year)'
                    if re.search(keyWords_year, column.b.text, re.I):
                        res['year'] = column.nextSibling.text
                        log.debug('Found release year of movie: %s' % res["year"])

                    # SIZE
                    keyWords_size = u'(größe:|groeße:|groesse:|size:)'
                    if re.search(keyWords_size, column.b.text, re.I):
                        res['size'] = self.parseSize(column.nextSibling.text)
                        log.debug('Found size of release: %s MB' % res['size'])

                    # IMDB
                    keyWords_id = u'auf\sIMdb'
                    imdbUrl_pattern = u'(?P<id>tt[0-9]+)\/'
                    if re.search(keyWords_id, column.b.text, re.I):
                        url = column.nextSibling.a['href']
                        match = re.search(imdbUrl_pattern, url, re.I)
                        res['description'] = match.group('id')
                        log.debug('Found imdb-id of release: %s' % res['description'])

                    #REL_Name
                    keyWords_name = u'(releasename:)'
                    if re.search(keyWords_name, column.b.text, re.I):
                        res['name'] = column.nextSibling.a['title']
                        log.debug('Found name of release: %s' % res['name'])
                except AttributeError:
                    pass

        for elem in ['year', 'name', 'description', 'size', 'age']:
            if res.get(elem, None) is None:
                log.debug('Could not fetch %s of movie release from details website.' % elem)

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
