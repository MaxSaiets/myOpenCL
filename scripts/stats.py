#!/usr/bin/env python3
"""
stats.py — Usage statistics for Claw agent (SQLite)
Usage:
  python3 /root/scripts/stats.py log --model gemini/gemini-2.5-flash --tokens-in 500 --tokens-out 200 --task "web scrape"
  python3 /root/scripts/stats.py today
  python3 /root/scripts/stats.py week
  python3 /root/scripts/stats.py models
  python3 /root/scripts/stats.py summary
"""
import sys
import sqlite3
import argparse
from datetime import datetime, timezone

DB = '/root/.openclaw/stats.db'

def get_conn():
    conn = sqlite3.connect(DB)
    conn.execute('''CREATE TABLE IF NOT EXISTS usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        date TEXT NOT NULL,
        model TEXT NOT NULL,
        tokens_in INTEGER DEFAULT 0,
        tokens_out INTEGER DEFAULT 0,
        task TEXT DEFAULT '',
        duration_ms INTEGER DEFAULT 0
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_date ON usage(date)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_model ON usage(model)')
    conn.commit()
    return conn

def log_request(model, tokens_in=0, tokens_out=0, task='', duration_ms=0):
    conn = get_conn()
    now = datetime.now(timezone.utc)
    conn.execute('INSERT INTO usage (ts, date, model, tokens_in, tokens_out, task, duration_ms) VALUES (?,?,?,?,?,?,?)',
                 (now.isoformat(), now.strftime('%Y-%m-%d'), model, tokens_in, tokens_out, task, duration_ms))
    conn.commit()
    print(f'Logged: {model} in={tokens_in} out={tokens_out}')

def report(where_clause='', params=()):
    conn = get_conn()
    rows = conn.execute(f'''
        SELECT date, model,
               COUNT(*) as reqs,
               SUM(tokens_in) as tin,
               SUM(tokens_out) as tout,
               SUM(tokens_in+tokens_out) as total_tokens
        FROM usage {where_clause}
        GROUP BY date, model
        ORDER BY date DESC, reqs DESC
    ''', params).fetchall()
    if not rows:
        print('No data'); return
    print(f"{'Date':<12} {'Model':<35} {'Reqs':>5} {'In':>7} {'Out':>7} {'Total':>8}")
    print('-'*80)
    for r in rows:
        model_short = r[1].replace('openrouter/','').replace('gemini/','gemini/')
        print(f"{r[0]:<12} {model_short:<35} {r[2]:>5} {r[3] or 0:>7} {r[4] or 0:>7} {r[5] or 0:>8}")

def report_models():
    conn = get_conn()
    rows = conn.execute('''
        SELECT model,
               COUNT(*) as reqs,
               SUM(tokens_in+tokens_out) as total_tokens,
               MAX(date) as last_used
        FROM usage
        GROUP BY model
        ORDER BY reqs DESC
    ''').fetchall()
    if not rows:
        print('No data'); return
    print(f"{'Model':<40} {'Reqs':>6} {'Tokens':>10} {'Last used':<12}")
    print('-'*75)
    for r in rows:
        model_short = r[0].replace('openrouter/','')
        print(f"{model_short:<40} {r[1]:>6} {r[2] or 0:>10} {r[3]:<12}")

def summary():
    conn = get_conn()
    total = conn.execute('SELECT COUNT(*), SUM(tokens_in+tokens_out), MIN(date), MAX(date) FROM usage').fetchone()
    today_count = conn.execute("SELECT COUNT(*) FROM usage WHERE date=date('now')").fetchone()[0]
    today_tokens = conn.execute("SELECT SUM(tokens_in+tokens_out) FROM usage WHERE date=date('now')").fetchone()[0] or 0
    print(f"=== Claw Usage Summary ===")
    print(f"Total requests: {total[0]:,}")
    print(f"Total tokens:   {total[1] or 0:,}")
    print(f"Period:         {total[2]} → {total[3]}")
    print(f"Today requests: {today_count:,}")
    print(f"Today tokens:   {today_tokens:,}")

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='cmd')

    p = sub.add_parser('log')
    p.add_argument('--model', required=True)
    p.add_argument('--tokens-in', type=int, default=0)
    p.add_argument('--tokens-out', type=int, default=0)
    p.add_argument('--task', default='')
    p.add_argument('--duration-ms', type=int, default=0)

    sub.add_parser('today')
    sub.add_parser('week')
    sub.add_parser('models')
    sub.add_parser('summary')

    args = parser.parse_args()
    if args.cmd == 'log':
        log_request(args.model, args.tokens_in, args.tokens_out, args.task, args.duration_ms)
    elif args.cmd == 'today':
        report("WHERE date=date('now')")
    elif args.cmd == 'week':
        report("WHERE date >= date('now','-7 days')")
    elif args.cmd == 'models':
        report_models()
    elif args.cmd == 'summary':
        summary()
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
