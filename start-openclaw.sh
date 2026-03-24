#!/bin/bash
export NODE_OPTIONS="--max-old-space-size=4096"
export NODE_COMPILE_CACHE="/var/tmp/openclaw-compile-cache"
export OPENAI_API_KEY="smart-router"
export OPENAI_BASE_URL="http://127.0.0.1:9000/v1/"
export OPENCLAW_NO_RESPAWN=1
export GH_TOKEN="YOUR_GITHUB_TOKEN_HERE"
export GITHUB_TOKEN="YOUR_GITHUB_TOKEN_HERE"
export GITHUB_USER="MaxSaiets"
export TELEGRAM_BOT_TOKEN="8697044933:AAEjLpqcCKIotwoLa69zdRYfaFyh44KY4tE"
export TELEGRAM_CHAT_ID="1311004971"
cd /root/openclaw
exec node openclaw.mjs gateway
