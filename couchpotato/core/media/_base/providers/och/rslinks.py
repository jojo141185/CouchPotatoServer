#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

import re
import json
from bs4 import BeautifulSoup
import datetime

from couchpotato.core.logger import CPLog
from couchpotato.core.media._base.providers.och.base import OCHProvider


log = CPLog(__name__)

class Base(OCHProvider):
    qualitySearch = False
    urls = {
        'base_url' : 'http://www.rslinks.org/',
        'search': 'http://www.rslinks.org/search/node/%s',
    }

    def _searchOnTitle(self, title, movie, quality, results):
        newResults = []
        url = "%s?query=%s" % (self.urls['search'], title)
        if not self.hasAlreadyBeenSearched(url):
            newResults = self.do_search(title)

            # add result to search cache
            self.addLastSearchResult(url, newResults)
        else:
            newResults = self.lastSearched.get(url, {})

        # append to results list (triggers event that surveys release quality)
        for result in newResults:
            results.append(result)  # gets cleared if release not matched

        return results

    def do_search(self, title):
        results = []
        searchUrl = self.urls['search'] % title

        log.debug('fetching data from %s' % searchUrl)

        data = self.getHTMLData(searchUrl)

        linksToMovieDetails = self.parseSearchResults(data)
        log.info("Search returned %d result." % len(linksToMovieDetails))

        for movieDetailLink in linksToMovieDetails:
            try:
                data = self.getHTMLData(movieDetailLink)
                result = self.parseMovieDetailPage(data)
                result['id'] = 0
                if len(result['url']) > 0:
                    for r in result['url']:
                        rc = result.copy()
                        rc['url'] = json.dumps(r)
                        results.append(rc)
            except:
                pass

        return results

    def parseSearchResults(self, data):
        #print data
        dom = BeautifulSoup(data, "html5lib")

        content = dom.find('div', id='content')
        try:
            detail_links = content.ol.findAll('li', recursive=True)

            links = []
            for detail_link in detail_links:
                links.append(detail_link.h3.a['href'])
            return links
        except AttributeError:
            return []

    def parseMovieDetailPage(self, data):
        data = BeautifulSoup(data, 'html5lib')
        content = data.find('div', id='content')
        dateSpan = content.find('span', attrs={'property':'dc:date dc:created'})
        imdbDiv = content.find('div', attrs={'class':'field-name-field-info-link'})
        try:
            title = content.div.h1.text.strip()
            date = datetime.datetime.strptime(dateSpan['content'], '%Y-%m-%dT%H:%M:%S+00:00').date()
            imdb = re.search(u'(?P<id>tt[0-9]+)\/?.*', imdbDiv.div.div.a['href'], re.I).group('id')
            mirrorSection = content.find('div', attrs={'class':'field-label'}).find_next_sibling('div').div

            dl = []
            if (mirrorSection.form):
                mirrors = mirrorSection.form.findAll('fieldset')
                for mirror in mirrors:
                    hoster = mirror.span.text.replace(':','')
                    links =  mirror.find('div',attrs={'class':'fieldset-wrapper'}).div.findAll('a')
                    for acceptedHoster in self.conf('hosters').replace(' ', '').split(','):
                        if acceptedHoster in hoster.lower():
                            dl.append([link['href'] for link in links])

            else:
                mirrors = mirrorSection.findAll('p')
                for mirror in mirrors:
                    hoster = mirror.find(text=True).replace(':', '')
                    links = mirror.findAll('a')
                    for acceptedHoster in self.conf('hosters').replace(' ', '').split(','):
                        if acceptedHoster in hoster.lower():
                            dl.append([link['href'] for link in links])

            return {'name': title,
                    'age': (date.today() - date).days,
                    'description': imdb,
                    'url': dl
            }
        except AttributeError:
            log.error('Parsing DetailPage of %s didnt work' % title)
            import traceback; log.error(traceback.format_exc());
        except NotImplementedError:
            log.error("This page can't be parsed at the moment")

        return {}

config = [{
              'name': 'rslinks',
              'groups': [
                  {
                      'tab': 'searcher',
                      'list': 'och_providers',
                      'name': 'RSLinks',
                      'description': 'See <a href="http://www.rslinks.org">rslinks.org</a>',
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
                      ],
                  },
              ],
          }]