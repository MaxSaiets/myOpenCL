#!/bin/bash
# Usage: notify.sh <message>
# Sends message to Max's Telegram
MSG="${1:?Usage: notify.sh <message>}"
TOKEN="8697044933:AAEjLpqcCKIotwoLa69zdRYfaFyh44KY4tE"
CHAT="1311004971"

curl -s -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\":\"${CHAT}\",\"text\":\"${MSG}\",\"parse_mode\":\"HTML\"}" \
  | python3 -c "import sys,json; r=json.load(sys.stdin); print('OK' if r.get('ok') else 'ERR:'+str(r))"
