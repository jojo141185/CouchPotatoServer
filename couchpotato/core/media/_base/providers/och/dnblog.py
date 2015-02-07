# -*- coding: utf-8 -*-


import json
import datetime

from bs4 import BeautifulSoup

from couchpotato.core.helpers.encoding import simplifyString, handle_special_chars
from couchpotato.core.logger import CPLog
from couchpotato.core.media._base.providers.och.base import OCHProvider
from couchpotato.core.helpers.variable import tryInt


log = CPLog(__name__)


class Base(OCHProvider):
    urls = {
        'hd-movies': 'http://dnblog.biz/dn-movie-hd-jr6ke?lcp_page1=%s',
    }

    def _searchOnTitle(self, title, movie, quality, results):
        # Nach Lokalem Titel (abh. vom def. Laendercode) und original Titel suchen
        titles = []
        titles.append(movie['title'])
        titles.append(movie['info']['original_title'])

        for title in titles:
            if self.do_search('%s' % (handle_special_chars(title)), results):
                break


    def do_search(self, title, results):
        foundRel = False
        checkedRel = 0
        page = 1

        # don't search on further pages when Release has been found
        while not foundRel and page < 5:
            log.debug('fetching data from %s' % (self.urls['hd-movies'] % page))
            data = self.getHTMLData(self.urls['hd-movies'] % page)
            dom = BeautifulSoup(data, "html5lib")
            releaseList = dom.find('ul', attrs={"class": "lcp_catlist"})

            checkWord = max(simplifyString(title).split(), key=len)
            for rel in releaseList.findAll('li'):
                #stop immediately when 50 releases checked
                if checkedRel < 50 and checkWord in rel.a.text.lower():
                    checkedRel += 1
                    rel =self.parseMovieDetailPage(rel.a['href'])
                    if rel:
                        results.append(rel)
                        foundRel = True
            page += 1
        return foundRel


    # ===============================================================================
    # INTERNAL METHODS
    #===============================================================================
    def parseContent(self, content):
        res = {}
        res["url"] = []
        res["pwd"] = 'DN'
        try:
            log.debug("Look for release info and dl-links on Movie's detail page.")
            try:
                matches = content.findAll('div', attrs={'class': 'su-spoiler-content'}, recursive=True)
                for match in matches:
                    # DOWNLOAD Links
                    try:
                        url = match.a['href']
                        hoster = match.a.text
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
                            if self.conf('extra_hosters') and 'z.b. mc,' in hoster.lower() and url not in res["url"]:
                                res["url"].append(url)
                                log.debug('Found new DL-Link %s on non-specified Hoster %s' % (url, hoster))
                    except (AttributeError, TypeError):
                        log.debug('Could not fetch URL or hoster from details website.')

            except (AttributeError, TypeError, KeyError):
                log.error('Could not fetch detailed Release info from Website.')

            if res["url"] != []:
                res["url"] = json.dumps(res["url"])  #List 2 string for db-compatibility
                return res
            else:
                log.debug('No DL-Links on Hoster(s) [%s] found :(' % (self.conf('hosters')))

        except (AttributeError, TypeError, KeyError):
            return None
        return None

    def parseHeader(self, header):
        def _getDateObject(day, month, year):
            months = ["jan", "feb", "mar", "apr", "mai", "jun", "jul", "aug", "sep", "okt", "nov", "dez"]
            try:
                month = months.index(month.lower()) + 1
                return datetime.date(tryInt(year), month, tryInt(day))
            except:
                return None

        res = {}
        res['name'] = header.find("div", attrs={"class": "title"}).h1.text

        date = header.find("div", attrs={"class": "date"})
        year = date.find("span", attrs={"class": "year"}).text
        month = date.find("span", attrs={"class": "month"}).text
        day = date.find("span", attrs={"class": "day"}).text
        date = _getDateObject(day, month, year)
        res['age'] = (date.today() - date).days if date is not None else 0
        return res


    def parseMovieDetailPage(self, link):
        log.debug("fetching data from Movie's detail page %s" % link)
        data = self.getHTMLData(link)
        dom = BeautifulSoup(data, "html5lib")
        pageCenter = dom.find('article', attrs={"class": "post"})

        header = pageCenter.find('header')

        res = {}
        if header:
            try:
                res.update(self.parseHeader(header))
                res.update(self.parseContent(pageCenter))
                res['id'] = 0 #match by name
            except TypeError:
                #ignore release if content,header or subHeader couldn't be parsed correctly
                return
        return res


config = [{
              'name': 'dnblog',
              'groups': [
                  {
                      'tab': 'searcher',
                      'list': 'och_providers',
                      'name': 'Daninas-Blog',
                      'description': 'See <a href="http://dnblog.biz/">DNBlog.biz</a>',
                      'wizard': True,
                      'options': [
                          {
                              'name': 'enabled',
                              'type': 'enabler',
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
                          {
                              'name':'extra_hosters',
                              'default': 0,
                              'type': 'bool',
                              'description': 'Accepting non-specified hosters.',
                          },
                      ],
                  },
              ],
          }]