#!/usr/bin/env python3
# Scraper template — httpx + BeautifulSoup + cron

import httpx
from bs4 import BeautifulSoup
from datetime import datetime

TARGET_URL = "https://example.com"
HEADERS = {"User-Agent": "Mozilla/5.0 Chrome/120.0"}

def scrape() -> list[dict]:
    resp = httpx.get(TARGET_URL, headers=HEADERS, timeout=15, follow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    items = []
    for el in soup.select("h2, h3, .title")[:20]:
        text = el.get_text(strip=True)
        if len(text) > 10:
            items.append({"title": text, "scraped_at": datetime.utcnow().isoformat()})
    return items

def main():
    print(f"[scraper] {datetime.utcnow().isoformat()}")
    items = scrape()
    for item in items:
        print(f"  • {item['title']}")
    print(f"[scraper] done: {len(items)} items")

if __name__ == "__main__":
    main()
