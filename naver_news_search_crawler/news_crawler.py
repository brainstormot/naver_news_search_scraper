import json
import re
import requests
from utils import check_dir
from utils import current_timestamp
from utils import get_path
from utils import get_soup
from bs4 import BeautifulSoup

from config import root
from config import debug
from config import verbose
from config import version
from config import SLEEP


_info_to_crawl = ('sid1', 'sid2', 'oid', 'aid', 'url',
                  'office', 'title', 'contentHtml', 'content',
                  'crawledTime', 'writtenTime', 'crawlerVersion')

def scrap(url):
    try:
        json_dict = _extract_content_as_dict(url)        
        return json_dict
    except Exception as e:
        print(url, e)
        return {}
        # write log

def _extract_content_as_dict(url):
    
    def remove_unnecessary_info_from_json_dict(json_dict):
        trimmed_dict = dict()
        for key, value in json_dict.items():
            if value and key in _info_to_crawl:
                trimmed_dict[key] = value
        return trimmed_dict

    url, attributes = _parse_and_redirect_url(url)
    soup = get_soup(url)
    
    if 'sports' in url:
        json_dict = _parse_sport(soup)
    elif 'entertain' in url:
        json_dict = _parse_entertain(soup)
    else:
        json_dict = _parse_basic(soup)
    
    json_dict.update(attributes)
    json_dict.update({
            'url': url,
            'crawlerVersion': version,
            'crawledTime': current_timestamp()
        })
    json_dict = remove_unnecessary_info_from_json_dict(json_dict)        
    return json_dict

def _parse_and_redirect_url(url):
    
    def redirect(url):
        try:
            response = requests.get(url)
            redirected_url = response.url if response.history else url
            return redirected_url
        except Exception as e:
            raise ValueError('redirection error %s' % str(e))
    
    def parse_attribute_of_url(url):
        url = url.replace('office_id', 'oid')
        url = url.replace('article_id', 'aid')
        if ('?' in url) == False:
            return {}
        parts = url.split('?')[1].split('&')
        parts = {part.split('=')[0]:part.split('=')[1] for part in parts}
        return parts
    
    def masking_sid1(url, sid1):
        if not sid1: return sid1
        if 'sports.news' in url: return 'sport'
        if 'entertain' in url: return 'entertain'
        return sid1
    
    attributes = parse_attribute_of_url(url)
    for key in ['sid1', 'sid2', 'oid', 'aid']:
        if (key in attributes) == False:
            attributes[key] = None
    
    redirected_url = redirect(url)
    attributes['sid1'] = masking_sid1(redirected_url, attributes['sid1'])
    
    return redirected_url, attributes

def _parse_content(html):
    content = []
    html = re.sub('<\\!--[^>]*-->', '', html.decode()) # Remove Comments
    html = re.sub('\n', '<br/>', html) # Preseve Line Change
    html = re.sub('<a.*/a>', '', html) # Remove Ads
    html = re.sub('<em.*/em>','',html)
    html = re.sub('<script.*/script>', '', html) # Remove Java Script
    html = re.sub('</?b>', '<br/>', html)
    html = re.sub('</?p>', '<br/>', html)
    for line in html.split('<br/>'):
        line = re.sub('<[^>]*>','',line).strip()
        if not line:
            continue
        if line[0] not in ['\\','/'] and line[-1] != ';':
            content.append(line)
    content = '\n'.join(content) if content else ''
    return content

def _parse_sport(soup):
    title = soup.select('div[class=news_headline] h4')
    title = title[0].text if title else None

    written_time = soup.select('div[class=news_headline] div[class=info] span')
    written_time = written_time[0].text if written_time else None
    # FIXME: Time should be formatted

    content_html = soup.select('div[id=newsEndContents]')
    content_html = content_html[0] if content_html else None
    
    content = _parse_content(content_html) if content_html else None
    
    return {
            'title': title, 
            'writtenTime': written_time,
            'contentHtml': content_html.decode(),
            'content': content
           }

def _parse_entertain(soup):
    title = soup.select('p[class=end_tit]')
    title = title[0].text if title else None

    written_time = soup.select('div[class=article_info] span')
    written_time = written_time[0].text if written_time else None
    # FIXME: Time should be formatted

    content_html = soup.select('div[class=end_body_wrp]')
    content_html = content_html[0] if content_html else None
            
    content = _parse_content(content_html) if content_html else None

    return {
            'title': title, 
            'writtenTime': written_time,
            'contentHtml': content_html.decode(),
            'content': content
           }

def _parse_basic(soup):
    title = soup.select('h3[id=articleTitle]')
    title = title[0].text if title else None

    written_time = soup.select('span[class=t11]')
    written_time = written_time[0].text if written_time else None

    content_html = soup.select('div[id=articleBodyContents]')
    content_html = content_html[0] if content_html else None

    content = _parse_content(content_html) if content_html else None
    
    return {'title': title, 
            'writtenTime': written_time,
            'contentHtml': content_html.decode(),
            'content': content
           }


class BatchArticleCrawler:

    sid1_list = ['1{}'.format('%02d'%i) for i in range(0, 11)]

    def __init__(self, *, year, month, date, root=root,
                 debug=False, verbose=False, version=None, name=''):
        self.root = root        
        self.year = str(year)
        self.month = '%02d' % month if type(month) == int else month
        self.date = '%02d' % date if type(date) == int else date
        self.debug = debug
        self.verbose = verbose
        self.version = '0.0' if version == None else version
        self._name = name

    def scrap_a_day_as_corpus(self):
        urls = self._get_urls_from_breaking_news()
        n_successes = 0
        
        docs = []
        indexs = []
        oid_aids = []
        
        for i, url in enumerate(urls):
            try:
                json_dict = scrap(url)
                content = json_dict.get('content', '')
                if not content:
                    continue
                index = '{}\t{}\t{}\t{}'.format(
                    get_path(json_dict['oid'], self.year, self.month, self.date, json_dict['aid']),
                    json_dict.get('sid1',''),
                    json_dict.get('writtenTime', ''),
                    json_dict.get('title', '')
                )
                docs.append(content.replace('\n', '  ').replace('\r\n', '  ').strip())
                indexs.append(index)
                oid_aids.append((json_dict['oid'], json_dict['aid']))
                n_successes += 1
            except Exception as e:
                print('Exception: {}\n{}'.format(url, str(e)))
                continue
            finally:
                if i % 1000 == 999:
                    print('\r  - {}scraping {} in {} ({} success) ...'.format(self._name + (': ' if self._name else ''), i+1, len(urls), n_successes), flush=True, end='')
        print('\rScrapped news')
        return docs, indexs, oid_aids

    def _get_urls_from_breaking_news(self):
        import time

        base_url = 'http://news.naver.com/main/list.nhn?mode=LSD&mid=sec&sid1={}&date={}&page={}'
        yymmdd = self.year + self.month + self.date
        links_in_all_sections = set()

        for sid1 in self.sid1_list:            
            links_in_a_section = set()
            last_links = set()
            page = 1
            
            while page < 1000:
                url = base_url.format(sid1, yymmdd, page)
                soup = get_soup(url)
                links = soup.select('div[class^=list] a[href^=http]')
                links = [link.attrs.get('href', '') for link in links]
                links = {link for link in links if 'naver.com' in link and 'read.nhn?' in link}

                if last_links == links:
                    break

                links_in_a_section.update(links)
                last_links = {link for link in links}

                if self.verbose:
                    print('\rpage = {}, links = {}'.format(page, len(links_in_a_section)), flush=True, end='')

                page += 1
                if self.debug and page >= 3:
                    break
                time.sleep(SLEEP)
            
            links_in_all_sections.update(links_in_a_section)
            if self.verbose:
                print('\rsection = {}, links = {}'.format(sid1, len(links_in_a_section)))

        print('date={} has {} news'.format(yymmdd, len(links_in_all_sections)))
        return links_in_all_sections