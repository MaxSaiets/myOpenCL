#!/usr/bin/env python3
"""
digest.py — Morning digest: scrape news + AI summary + send to Telegram
Usage: python3 /root/scripts/digest.py [--dry-run]
Cron:  0 8 * * * python3 /root/scripts/digest.py >> /var/log/claw-digest.log 2>&1
"""
import sys
import argparse
import httpx
from datetime import datetime, timezone
from bs4 import BeautifulSoup

BOT_TOKEN   = '8697044933:AAEjLpqcCKIotwoLa69zdRYfaFyh44KY4tE'
CHAT_ID     = '1311004971'
ROUTER_URL  = 'http://127.0.0.1:9000'

SOURCES = [
    {'name': 'Hacker News', 'url': 'https://hacker-news.firebaseio.com/v0/topstories.json',
     'mode': 'hn_api', 'limit': 8},
    {'name': 'Укрінформ', 'url': 'https://www.ukrinform.ua', 
     'mode': 'html', 'selector': 'h2,h3', 'limit': 6},
    {'name': 'DOU.ua', 'url': 'https://dou.ua/lenta/', 
     'mode': 'html', 'selector': 'h2,h3', 'limit': 5},
]

HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0'}

def fetch_hn(limit=8):
    ids = httpx.get('https://hacker-news.firebaseio.com/v0/topstories.json', timeout=10).json()[:limit*2]
    items = []
    for i in ids[:limit]:
        try:
            item = httpx.get(f'https://hacker-news.firebaseio.com/v0/item/{i}.json', timeout=5).json()
            if item and item.get('title'):
                items.append(item['title'])
        except Exception:
            pass
    return items

def fetch_html(url, selector, limit=6):
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=12, follow_redirects=True)
        soup = BeautifulSoup(resp.text, 'lxml')
        for tag in soup(['script','style','nav','footer']):
            tag.decompose()
        items = []
        for el in soup.select(selector)[:limit*2]:
            text = el.get_text(strip=True)
            if len(text) > 15:
                items.append(text[:150])
        return list(dict.fromkeys(items))[:limit]  # deduplicate
    except Exception as e:
        return [f'(error: {e})']

def ai_summarize(sections: dict) -> str:
    text = '\n\n'.join(
        f'=== {name} ===\n' + '\n'.join(f'• {h}' for h in headlines)
        for name, headlines in sections.items()
    )
    payload = {
        'model': 'gpt-4o',
        'messages': [
            {'role': 'system', 'content': 
             'Ти — Claw, AI-асистент Макса. Зроби короткий ранковий дайджест новин українською мовою. '
             'Формат: короткий вступ, потім 2-3 найважливіших пункти по кожній темі. '
             'Загальний обсяг — до 15 рядків. Будь конкретним.'},
            {'role': 'user', 'content': f'Новини за {datetime.now().strftime("%d.%m.%Y")}:\n\n{text}'}
        ],
        'max_tokens': 600, 'temperature': 0.4
    }
    resp = httpx.post(f'{ROUTER_URL}/v1/chat/completions', json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()['choices'][0]['message']['content'].strip()

def send_telegram(message: str):
    httpx.post(
        f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
        json={'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'HTML',
              'disable_web_page_preview': True},
        timeout=15
    ).raise_for_status()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    print(f'[digest] {datetime.now(timezone.utc).isoformat()} starting')

    sections = {}
    for src in SOURCES:
        print(f'  fetching {src["name"]}...')
        if src['mode'] == 'hn_api':
            items = fetch_hn(src['limit'])
        else:
            items = fetch_html(src['url'], src['selector'], src['limit'])
        sections[src['name']] = items
        print(f'  {src["name"]}: {len(items)} items')

    print('  summarizing...')
    summary = ai_summarize(sections)

    header = f'☀️ <b>Ранковий дайджест — {datetime.now().strftime("%d.%m.%Y")}</b>\n\n'
    message = header + summary

    if args.dry_run:
        print('--- DRY RUN ---')
        print(message)
    else:
        send_telegram(message)
        print('[digest] sent to Telegram')

    # Log stats
    try:
        import subprocess
        subprocess.run(['python3', '/root/scripts/stats.py', 'log',
                        '--model', 'gemini/gemini-2.5-flash',
                        '--tokens-in', '800', '--tokens-out', '400',
                        '--task', 'morning-digest'], capture_output=True)
    except Exception:
        pass

if __name__ == '__main__':
    main()
