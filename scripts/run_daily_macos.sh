#!/bin/zsh
# Debt Market Dashboard — automated background data updater
# Runs via macOS LaunchAgent.

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Resolve this from the script location.  A hard-coded home-directory path
# caused launchd to run a different checkout (or nothing at all) after this
# project was moved into Documents.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"
LOG="$PROJECT_DIR/data/ingest.log"
LOCK_FILE="/tmp/debt_market_macos_ingest.lock"

cd "$PROJECT_DIR" || exit 0
mkdir -p data

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] $*" >> "$LOG"
}

# Prevent overlapping runs
if [[ -f "$LOCK_FILE" ]]; then
  LOCK_PID=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
  if [[ -n "$LOCK_PID" ]] && kill -0 "$LOCK_PID" 2>/dev/null; then
    exit 0
  fi
fi
echo "$$" > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT INT TERM

# Time guard: refresh from 2:00 PM through 5:20 PM local time unless forced.
CURRENT_HOUR=$(date '+%H')
CURRENT_MIN=$(date '+%M')
TIME_VAL=$(( 10#$CURRENT_HOUR * 60 + 10#$CURRENT_MIN ))

# 14:00 = 840 minutes; 17:20 = 1040 minutes.
if [[ "${1:-}" != "--force" ]] && [[ $TIME_VAL -lt 840 || $TIME_VAL -gt 1040 ]]; then
  # Sleep 10 seconds before exit so launchd minimum runtime threshold (>10s) passes cleanly with exit code 0
  sleep 10
  exit 0
fi

log "daily refresh started"

# Ingest market data from FBIL, CCIL, F-TRAC, CBRICS, Brent
"$PYTHON" -u -m app.ingest --days 7 >> "$LOG" 2>&1 || log "WARNING: ingest had errors"

# Bake static site into ./public
"$PYTHON" -u -m app.publish >> "$LOG" 2>&1 || { log "ERROR: publish failed"; sleep 10; exit 0; }

# Commit updated data and push to GitHub (triggers Vercel auto-deploy)
git config user.name  "Swayamjit Dalai"
git config user.email "swayamjitdalai-bit@users.noreply.github.com"
git add -f data/market.db data/cbrics.csv public/ vercel.json 2>/dev/null || true

if git diff --staged --quiet; then
  log "no new data to commit"
else
  git commit -m "Auto market data update: $(date '+%Y-%m-%d %H:%M %Z')" >> "$LOG" 2>&1
  git pull --rebase -X theirs origin main >> "$LOG" 2>&1 || true
  if git push origin main >> "$LOG" 2>&1; then
    log "pushed to GitHub — Vercel deployment triggered automatically"
  else
    log "WARNING: push failed, will retry next run"
  fi
fi

log "daily refresh completed"
sleep 10
exit 0
