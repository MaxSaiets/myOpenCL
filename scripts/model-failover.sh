#!/bin/bash
# Monitor smart-router and OpenClaw health

HEALTH=$(curl -s --max-time 5 http://127.0.0.1:9000/health 2>/dev/null)
if [ -z "$HEALTH" ]; then
  echo "$(date -u): Smart-router DOWN, restarting..."
  pm2 restart smart-router
  sleep 5
  bash /root/scripts/notify.sh '⚠️ Smart-router перезапущено (не відповідав)' 2>/dev/null
fi

OPENCLAW_UP=$(pm2 list 2>/dev/null | grep openclaw | grep online | wc -l)
if [ "$OPENCLAW_UP" -eq 0 ]; then
  echo "$(date -u): OpenClaw not online, restarting..."
  pm2 restart openclaw
  sleep 5
  bash /root/scripts/notify.sh '⚠️ OpenClaw перезапущено (впав)' 2>/dev/null
fi
