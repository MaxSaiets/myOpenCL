#!/usr/bin/env python3
"""
scrape.py — Web scraper for Claw agent (httpx + BeautifulSoup + Playwright for JS)
Usage:
  python3 /root/scripts/scrape.py <url> [--selector CSS] [--text-only] [--links] [--js] [--json]

--js    Use Playwright (real browser) for JS-heavy sites (Rozetka, SPA, etc.)
"""
import sys
import argparse
import json as json_mod
import httpx
from bs4 import BeautifulSoup

def _parse(html: str, selector=None, text_only=False, links=False, as_json=False):
    soup = BeautifulSoup(html, 'lxml')
    for tag in soup(['script', 'style', 'nav', 'footer', 'iframe', 'noscript']):
        tag.decompose()

    if links:
        found = [{'text': a.get_text(strip=True), 'url': a['href']}
                 for a in soup.find_all('a', href=True) if a['href'].startswith('http')]
        if as_json:
            print(json_mod.dumps(found[:50], ensure_ascii=False, indent=2))
        else:
            for item in found[:50]:
                print(f"{item['text'][:80]} -> {item['url']}")
        return

    elements = soup.select(selector) if selector else [soup.body or soup]
    results = []
    for el in elements[:20]:
        if text_only:
            lines = [l for l in el.get_text(separator='\n', strip=True).splitlines() if l.strip()]
            results.append('\n'.join(lines))
        else:
            results.append(str(el)[:2000])

    output = '\n---\n'.join(results)
    if len(output) > 8000:
        output = output[:8000] + '\n...[truncated]'
    if as_json:
        print(json_mod.dumps({'content': output}, ensure_ascii=False))
    else:
        print(output)

def scrape_httpx(url, selector=None, text_only=False, links=False, as_json=False, timeout=15):
    headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0 Safari/537.36'}
    resp = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    _parse(resp.text, selector, text_only, links, as_json)

def scrape_playwright(url, selector=None, text_only=False, links=False, as_json=False, timeout=30):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        page = browser.new_page(user_agent='Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0')
        page.goto(url, timeout=timeout*1000, wait_until='networkidle')
        html = page.content()
        browser.close()
    _parse(html, selector, text_only, links, as_json)

def main():
    parser = argparse.ArgumentParser(description='Web scraper for Claw')
    parser.add_argument('url', help='URL to scrape')
    parser.add_argument('--selector', '-s', default=None)
    parser.add_argument('--text-only', '-t', action='store_true')
    parser.add_argument('--links', '-l', action='store_true')
    parser.add_argument('--js', action='store_true', help='Use Playwright (real browser, supports JS)')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--timeout', type=int, default=20)
    args = parser.parse_args()
    try:
        if args.js:
            print(f'[scrape] Using Playwright for {args.url}', file=sys.stderr)
            scrape_playwright(args.url, args.selector, args.text_only, args.links, args.json, args.timeout)
        else:
            scrape_httpx(args.url, args.selector, args.text_only, args.links, args.json, args.timeout)
    except Exception as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
