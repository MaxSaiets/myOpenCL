#!/bin/bash
# Usage: new-project.sh <name> <description> [python|node|bash] [template: telegram-bot|fastapi-app|scraper]
set -e
NAME="${1:?Usage: new-project.sh <name> <description> [lang] [template]}"
DESC="${2:-Project by Claw}"
LANG="${3:-python}"
TEMPLATE="${4:-}"
DIR="/root/projects/$NAME"
export GH_TOKEN="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"

echo "=== new-project: $NAME (lang=$LANG template=${TEMPLATE:-none}) ==="
mkdir -p "$DIR"
cd "$DIR"

# Copy template if specified
if [ -n "$TEMPLATE" ] && [ -d "/root/templates/$TEMPLATE" ]; then
    cp -r /root/templates/$TEMPLATE/. .
    echo "Template $TEMPLATE applied"
fi

# .gitignore
cat > .gitignore << 'GITEOF'
venv/
__pycache__/
*.pyc
.env
*.log
node_modules/
.env.local
GITEOF

# README
if [ ! -f README.md ]; then
    printf "# %s\n\n%s\n" "$NAME" "$DESC" > README.md
fi

# git
git init -q && git branch -m main

# Python venv
if [ "$LANG" = "python" ]; then
    python3 -m venv venv
    if [ -f requirements.txt ]; then
        echo "Installing requirements..."
        venv/bin/pip install -r requirements.txt -q
    fi
fi

echo "DIR=$DIR — ready."
echo "Next: edit code, then run: /root/scripts/push-project.sh $NAME"
