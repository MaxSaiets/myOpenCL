#!/bin/bash
# Usage: push-project.sh <name> [commit-message]
set -e
NAME="${1:?Usage: push-project.sh <name>}"
MSG="${2:-feat: initial implementation}"
DIR="/root/projects/$NAME"
export GH_TOKEN="YOUR_GITHUB_TOKEN_HERE"

cd "$DIR"
git add -A
git diff --cached --quiet && echo 'Nothing to commit' && exit 0
git commit -m "$MSG"

if ! git remote | grep -q origin; then
    DESC=$(sed -n '3p' README.md 2>/dev/null || echo "$NAME")
    if ! gh repo view "MaxSaiets/$NAME" &>/dev/null; then
        gh repo create "MaxSaiets/$NAME" --public --description "$DESC"
    fi
    git remote add origin "https://${GH_TOKEN}@github.com/MaxSaiets/${NAME}.git"
fi

git push -u origin main
echo "PUSHED: https://github.com/MaxSaiets/$NAME"
