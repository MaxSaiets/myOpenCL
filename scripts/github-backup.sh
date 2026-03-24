#!/bin/bash
WORKSPACE="/root/.openclaw/workspace"
REPO="https://MaxSaiets:${GH_TOKEN}@github.com/MaxSaiets/myOpenCL.git"
LOG="/var/log/openclaw-backup.log"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $1" >> "$LOG"; }

[ -f "$LOG" ] && [ "$(stat -c%s "$LOG" 2>/dev/null || echo 0)" -gt 524288 ] && tail -200 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"

cd "$WORKSPACE" || { log "ERROR: workspace not found"; exit 1; }

git remote set-url origin "$REPO" 2>/dev/null || git remote add origin "$REPO"

mkdir -p memory

# Strip secrets before staging
SECRET_PATTERNS=(
  's/ghp_[A-Za-z0-9]\{36,\}/\$GH_TOKEN/g'
  's/AIzaSy[A-Za-z0-9_-]\{30,\}/\$GEMINI_KEY/g'
  's/sk-or-v1-[A-Za-z0-9]\{60,\}/\$OPENROUTER_KEY/g'
  's/[0-9]\{10\}:AA[A-Za-z0-9_-]\{30,\}/\$TELEGRAM_BOT_TOKEN/g'
)
for f in *.md memory/*.md 2>/dev/null; do
  [ -f "$f" ] || continue
  for pat in "${SECRET_PATTERNS[@]}"; do
    sed -i "$pat" "$f"
  done
done

git add -A

if git diff --cached --quiet; then
    log "OK: no changes to backup"
    exit 0
fi

git commit -m "backup: $(date -u '+%Y-%m-%d %H:%M UTC')" >> "$LOG" 2>&1

if git push origin main >> "$LOG" 2>&1; then
    log "OK: backup pushed to GitHub"
else
    git push --set-upstream origin main >> "$LOG" 2>&1 && log "OK: first push done" || log "ERROR: push failed"
fi
