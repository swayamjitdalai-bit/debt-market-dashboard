#!/bin/zsh
# Smart background market data ingestion.
# Runs on macOS via LaunchAgent.
# Simply ingest → publish → commit → push.
# Vercel auto-deploys on every push to main.

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

PROJECT_DIR="/Users/swayamjitdalai/Documents/debt-market-dashboard-main"
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

FORCE=false
if [[ "${1:-}" == "--force" ]]; then
  FORCE=true
fi

# Time guard: only run 5:15 PM – 11:59 PM IST
CURRENT_HOUR=$(date '+%H')
CURRENT_MIN=$(date '+%M')
TIME_VAL=$(( 10#$CURRENT_HOUR * 60 + 10#$CURRENT_MIN ))

if [[ "$FORCE" != "true" ]] && [[ $TIME_VAL -lt $(( 17*60+15 )) || $TIME_VAL -gt $(( 23*60+59 )) ]]; then
  exit 0
fi

log "daily refresh started"

# Sync with remote: stash any local tweaks, pull, then restore
git stash --quiet 2>>"$LOG" || true
git fetch origin main --quiet 2>>"$LOG" || true
git reset --hard origin/main --quiet 2>>"$LOG" || true
git stash pop --quiet 2>>"$LOG" || true

# Ingest
"$PYTHON" -u -m app.ingest --days 7 >> "$LOG" 2>&1 || log "WARNING: ingest had errors"

# Publish static site
"$PYTHON" -u -m app.publish >> "$LOG" 2>&1 || { log "ERROR: publish failed"; exit 0; }

# Commit & push
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
    log "WARNING: push failed, will retry on next run"
  fi
fi

log "daily refresh completed"
exit 0
