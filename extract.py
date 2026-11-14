"""Fetch one saved Post batch. No NewsAPI calls, publisher bypasses or paid readers."""
import concurrent.futures
import ipaddress
import json
import os
import socket
import threading
import time
from urllib.parse import urljoin, urlsplit, urlencode
from urllib.robotparser import RobotFileParser
import requests
import trafilatura

SITE = 'https://thepost.run.place'
AGENT = 'ThePostArticleReader/1.0 (+https://thepost.run.place)'
LIMIT = 4_000_000
locks = {}
lock_guard = threading.Lock()
robots = {}

def public_url(url):
    u = urlsplit(url)
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password or u.port not in (None, 80, 443):
        raise ValueError('Unsupported URL')
    addresses = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Nonpublic destination')
    return u

def download(url, check_robots=True):
    session = requests.Session()
    session.trust_env = False
    try:
        for _ in range(6):
            u = public_url(url)
            if check_robots and not allowed(url):
                raise ValueError('Publisher robots policy disallows access')
            with session.get(url, headers={'User-Agent': AGENT}, timeout=(8, 20), allow_redirects=False, stream=True) as r:
                if r.status_code in (301, 302, 303, 307, 308):
                    url = urljoin(url, r.headers['Location'])
                    continue
                if not check_robots and r.status_code == 404:
                    return '', url
                r.raise_for_status()
                if check_robots and not any(t in r.headers.get('Content-Type', '').lower() for t in ('text/html', 'application/xhtml')):
                    raise ValueError('Not HTML')
                chunks, size = [], 0
                for chunk in r.iter_content(65536):
                    size += len(chunk)
                    if size > LIMIT:
                        raise ValueError('Page too large')
                    chunks.append(chunk)
                return b''.join(chunks).decode(r.encoding or 'utf-8', errors='replace'), url
        raise ValueError('Too many redirects')
    finally:
        session.close()

def allowed(url):
    u = urlsplit(url)
    origin = u.scheme + '://' + u.netloc
    # Runs serialized per publisher, including robots discovery.
    if origin not in robots:
        text, _ = download(origin + '/robots.txt', check_robots=False)
        parser = RobotFileParser()
        parser.parse(text.splitlines())
        robots[origin] = parser
    return robots[origin].can_fetch(AGENT, url)

def extract(item):
    result = {'id': item['id'], 'url': item['url']}
    try:
        host = urlsplit(item['url']).hostname
        with lock_guard:
            guard = locks.setdefault(host, threading.Lock())
        with guard:
            html, final_url = download(item['url'])
            text = trafilatura.extract(html, url=final_url, favor_precision=True, include_comments=False, include_tables=False, deduplicate=True) or ''
        if len(text) < 600 or len(text.split()) < 100:
            raise ValueError('Insufficient article text')
        if any(x in text[:1500].lower() for x in ('verify you are human', 'enable javascript and cookies to continue', 'checking your browser')):
            raise ValueError('Publisher access check')
        result.update(content=text[:60000], truncated=len(text) > 60000)
    except Exception as error:
        # Never print article bodies, tokens, query strings or request exception details.
        result['error'] = type(error).__name__
    return result

def identity_token():
    url = os.environ['ACTIONS_ID_TOKEN_REQUEST_URL']
    r = requests.get(url + ('&' if '?' in url else '?') + urlencode({'audience': SITE}), headers={'Authorization': 'Bearer ' + os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']}, timeout=20)
    r.raise_for_status()
    return r.json()['value']

def site_request(method, path, **kwargs):
    return requests.request(method, SITE + path, headers={'Authorization': 'Bearer ' + identity_token()}, timeout=40, **kwargs)

def main():
    slot = int(time.time() // 1800)
    deadline = time.monotonic() + 600
    while True:
        r = site_request('GET', '/api/extractor/batch?slot=' + str(slot))
        if r.status_code != 425:
            r.raise_for_status()
            break
        if time.monotonic() > deadline:
            raise RuntimeError('News batch was not saved within ten minutes; previous edition kept')
        time.sleep(15)
    batch = r.json()
    if batch.get('already_claimed'):
        print('Batch already claimed; no publisher requests repeated.')
        return
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(extract, batch['items']))
    r = site_request('POST', '/api/extractor/import', json={'slot': batch['slot'], 'results': results})
    r.raise_for_status()
    print(json.dumps(r.json()))
    print('Skipped publishers:', sum('error' in a for a in results))
    if results and not any('content' in a for a in results):
        raise RuntimeError('No full article text was available; existing reports kept')

if __name__ == '__main__':
    main()
