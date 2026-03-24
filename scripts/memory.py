#!/usr/bin/env python3
"""
memory.py — SQLite persistent memory for Claw agent
Usage:
  python3 /root/scripts/memory.py save "key" "value" [--tags tag1,tag2]
  python3 /root/scripts/memory.py get "key"
  python3 /root/scripts/memory.py search "query"
  python3 /root/scripts/memory.py list [--tag tag]
  python3 /root/scripts/memory.py delete "key"
  python3 /root/scripts/memory.py dump

DB: /root/.openclaw/memory.db
"""
import sys
import sqlite3
import argparse
import json
from datetime import datetime

DB = '/root/.openclaw/memory.db'

def get_conn():
    conn = sqlite3.connect(DB)
    conn.execute('''CREATE TABLE IF NOT EXISTS memory (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        tags TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_tags ON memory(tags)')
    conn.commit()
    return conn

def save(key: str, value: str, tags: str = ''):
    conn = get_conn()
    now = datetime.utcnow().isoformat()
    conn.execute('''INSERT INTO memory (key, value, tags, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                      value=excluded.value, tags=excluded.tags, updated_at=excluded.updated_at''',
                 (key, value, tags, now, now))
    conn.commit()
    print(f'Saved: {key}')

def get(key: str):
    conn = get_conn()
    row = conn.execute('SELECT key, value, tags, updated_at FROM memory WHERE key=?', (key,)).fetchone()
    if row:
        print(f'[{row[0]}] ({row[3]})\n{row[1]}')
        if row[2]:
            print(f'tags: {row[2]}')
    else:
        print(f'Not found: {key}')

def search(query: str):
    conn = get_conn()
    q = f'%{query}%'
    rows = conn.execute(
        'SELECT key, value, updated_at FROM memory WHERE key LIKE ? OR value LIKE ? OR tags LIKE ? ORDER BY updated_at DESC LIMIT 20',
        (q, q, q)
    ).fetchall()
    if not rows:
        print('No results')
        return
    for row in rows:
        preview = row[1][:120].replace('\n', ' ')
        print(f'[{row[0]}] {preview}  ({row[2][:10]})')

def list_all(tag: str = None):
    conn = get_conn()
    if tag:
        rows = conn.execute(
            'SELECT key, value, tags, updated_at FROM memory WHERE tags LIKE ? ORDER BY updated_at DESC',
            (f'%{tag}%',)
        ).fetchall()
    else:
        rows = conn.execute('SELECT key, value, tags, updated_at FROM memory ORDER BY updated_at DESC').fetchall()
    for row in rows:
        preview = row[1][:80].replace('\n', ' ')
        tags_str = f' [{row[2]}]' if row[2] else ''
        print(f'{row[0]}{tags_str}: {preview}  ({row[3][:10]})')

def delete(key: str):
    conn = get_conn()
    conn.execute('DELETE FROM memory WHERE key=?', (key,))
    conn.commit()
    print(f'Deleted: {key}')

def dump():
    conn = get_conn()
    rows = conn.execute('SELECT key, value, tags, created_at, updated_at FROM memory ORDER BY updated_at DESC').fetchall()
    data = [{'key': r[0], 'value': r[1], 'tags': r[2], 'created': r[3], 'updated': r[4]} for r in rows]
    print(json.dumps(data, ensure_ascii=False, indent=2))

def main():
    parser = argparse.ArgumentParser(description='Claw persistent memory (SQLite)')
    sub = parser.add_subparsers(dest='cmd')

    p_save = sub.add_parser('save', help='Save a memory')
    p_save.add_argument('key')
    p_save.add_argument('value')
    p_save.add_argument('--tags', default='')

    p_get = sub.add_parser('get', help='Get a memory by key')
    p_get.add_argument('key')

    p_search = sub.add_parser('search', help='Search memories')
    p_search.add_argument('query')

    p_list = sub.add_parser('list', help='List all memories')
    p_list.add_argument('--tag', default=None)

    p_del = sub.add_parser('delete', help='Delete a memory')
    p_del.add_argument('key')

    sub.add_parser('dump', help='Dump all as JSON')

    args = parser.parse_args()
    if args.cmd == 'save':
        save(args.key, args.value, args.tags)
    elif args.cmd == 'get':
        get(args.key)
    elif args.cmd == 'search':
        search(args.query)
    elif args.cmd == 'list':
        list_all(args.tag)
    elif args.cmd == 'delete':
        delete(args.key)
    elif args.cmd == 'dump':
        dump()
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
