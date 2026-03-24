#!/usr/bin/env python3
"""
readfile.py — Read files/repos/logs for Claw agent
Usage:
  python3 /root/scripts/readfile.py <path>                    # read local file
  python3 /root/scripts/readfile.py --repo MaxSaiets/myrepo   # clone & show structure
  python3 /root/scripts/readfile.py --log openclaw            # show pm2 log
  python3 /root/scripts/readfile.py --env /root/projects/x    # show .env (masked secrets)
"""
import sys
import os
import argparse
import subprocess

MAX_CHARS = 8000

def read_local(path: str):
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        print(f'ERROR: not found: {path}')
        sys.exit(1)
    if os.path.isdir(path):
        # Show tree
        result = subprocess.run(['find', path, '-maxdepth', '3', '-not', '-path', '*/venv/*',
                                  '-not', '-path', '*/.git/*', '-not', '-name', '*.pyc'],
                                 capture_output=True, text=True)
        print(result.stdout[:MAX_CHARS])
        return
    with open(path, 'r', errors='replace') as f:
        content = f.read(MAX_CHARS)
    print(content)
    if len(content) == MAX_CHARS:
        print('\n...[file truncated at 8000 chars]')

def read_repo(repo: str):
    """Clone GitHub repo to /tmp, show structure + key files."""
    tmp = f'/tmp/claw-repo-{repo.replace("/", "-")}'
    token = os.environ.get('GH_TOKEN', '')
    url = f'https://{token}@github.com/{repo}.git' if token else f'https://github.com/{repo}.git'

    if not os.path.exists(tmp):
        print(f'Cloning {repo}...')
        subprocess.run(['git', 'clone', '--depth=1', url, tmp], check=True,
                       capture_output=True)

    # Show file tree
    result = subprocess.run(
        ['find', tmp, '-maxdepth', '3', '-not', '-path', '*/.git/*',
         '-not', '-path', '*/node_modules/*', '-not', '-path', '*/venv/*',
         '-not', '-name', '*.pyc'],
        capture_output=True, text=True
    )
    print('=== STRUCTURE ===')
    print(result.stdout[:2000])

    # Read key files
    for fname in ['README.md', 'main.py', 'index.js', 'index.ts', 'app.py',
                  'requirements.txt', 'package.json', '.env.example']:
        fpath = os.path.join(tmp, fname)
        if os.path.exists(fpath):
            with open(fpath) as f:
                content = f.read(2000)
            print(f'\n=== {fname} ===\n{content}')

def read_log(service: str):
    """Read pm2 logs for a service."""
    result = subprocess.run(
        ['pm2', 'logs', service, '--lines', '50', '--nostream'],
        capture_output=True, text=True
    )
    output = (result.stdout + result.stderr)[-MAX_CHARS:]
    print(output)

def read_env(project_dir: str):
    """Read .env file with masked secret values."""
    env_path = os.path.join(project_dir, '.env')
    if not os.path.exists(env_path):
        print(f'No .env at {env_path}')
        return
    secret_keys = {'token', 'key', 'secret', 'password', 'pass', 'api'}
    with open(env_path) as f:
        for line in f:
            line = line.rstrip()
            if '=' in line and not line.startswith('#'):
                k, _, v = line.partition('=')
                if any(s in k.lower() for s in secret_keys):
                    print(f'{k}=***{v[-4:] if len(v) > 4 else "***"}')
                else:
                    print(line)
            else:
                print(line)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('path', nargs='?', help='Local file or directory path')
    parser.add_argument('--repo', help='GitHub repo (user/name)')
    parser.add_argument('--log', help='PM2 service name')
    parser.add_argument('--env', help='Project directory with .env')
    args = parser.parse_args()

    if args.repo:
        read_repo(args.repo)
    elif args.log:
        read_log(args.log)
    elif args.env:
        read_env(args.env)
    elif args.path:
        read_local(args.path)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
