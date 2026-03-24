#!/bin/bash
# /root/scripts/health-monitor.sh
# System health monitor for OpenClaw stack
# Run by system cron every 5 minutes

LOG=/var/log/openclaw-health.log
DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
ERRORS=0

log() {
  echo "[$DATE] $1" >> "$LOG"
}

# Keep log under 1MB
if [ -f "$LOG" ] && [ $(stat -c%s "$LOG" 2>/dev/null || echo 0) -gt 1048576 ]; then
  tail -500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

# Check smart-router
if ! curl -sf http://127.0.0.1:9000/health > /dev/null 2>&1; then
  log "ERROR: smart-router not responding — restarting"
  /usr/bin/pm2 restart smart-router >> "$LOG" 2>&1
  sleep 5
  if ! curl -sf http://127.0.0.1:9000/health > /dev/null 2>&1; then
    log "CRITICAL: smart-router failed to restart"
    ERRORS=$((ERRORS+1))
  else
    log "OK: smart-router restarted successfully"
  fi
fi

# Check openclaw gateway
if ! curl -sf http://127.0.0.1:18789/__openclaw__/health > /dev/null 2>&1; then
  log "WARN: OpenClaw gateway health check failed (may be normal)"
fi

# Check PM2 openclaw process
OPENCLAW_STATUS=$(/usr/bin/pm2 jlist 2>/dev/null | python3 -c "import json,sys; procs=json.load(sys.stdin); p=[x for x in procs if x['name']=='openclaw']; print(p[0]['pm2_env']['status'] if p else 'missing')" 2>/dev/null)
if [ "$OPENCLAW_STATUS" != "online" ]; then
  log "ERROR: openclaw status=$OPENCLAW_STATUS — restarting"
  /usr/bin/pm2 restart openclaw --update-env >> "$LOG" 2>&1
  ERRORS=$((ERRORS+1))
fi

if [ $ERRORS -eq 0 ]; then
  log "OK: all services healthy"
fi
