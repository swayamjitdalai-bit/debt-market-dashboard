#!/bin/zsh
# Smart background market data ingestion and automated Vercel publisher.
# Runs locally on macOS via LaunchAgent (~/Library/LaunchAgents/com.swayamjitdalai.debt-market-dashboard.plist)
# Acts as a primary high-speed updater alongside GitHub Actions.

set -uo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

PROJECT_DIR="/Users/swayamjitdalai/Documents/debt-market-dashboard-main"
PYTHON="$PROJECT_DIR/.venv/bin/python"
LOG="$PROJECT_DIR/data/ingest.log"
LOCK_FILE="/tmp/debt_market_macos_ingest.lock"

cd "$PROJECT_DIR"
mkdir -p data

log() {
  print -r -- "[$(date '+%Y-%m-%d %H:%M:%S %Z')] $*" >> "$LOG"
}

# Ensure single instance runs at a time
if [[ -f "$LOCK_FILE" ]]; then
  LOCK_PID=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
  if [[ -n "$LOCK_PID" ]] && kill -0 "$LOCK_PID" 2>/dev/null; then
    # Another ingestion is currently running
    exit 0
  fi
fi
echo "$$" > "$LOCK_FILE"

cleanup() {
  rm -f "$LOCK_FILE"
}
trap cleanup EXIT INT TERM

FORCE=false
if [[ "${1:-}" == "--force" ]]; then
  FORCE=true
fi

# Time check: Only run between 5:15 PM (17:15) and 11:59 PM (23:59) IST unless --force is given
CURRENT_HOUR=$(date '+%H')
CURRENT_MIN=$(date '+%M')
TIME_VAL=$(( 10#$CURRENT_HOUR * 60 + 10#$CURRENT_MIN ))
TARGET_START=$(( 17 * 60 + 15 )) # 17:15 IST
TARGET_END=$(( 23 * 60 + 59 ))   # 23:59 IST

if [[ "$FORCE" != "true" ]]; then
  if [[ $TIME_VAL -lt $TARGET_START || $TIME_VAL -gt $TARGET_END ]]; then
    exit 0
  fi
fi

log "daily refresh started"

# 1. Cleanly sync with GitHub remote (fetch & rebase to avoid merge conflicts)
git fetch origin main --quiet 2>> "$LOG" || true
git rebase origin/main --quiet 2>> "$LOG" || git rebase --abort 2>/dev/null || true

# 2. Ingest market feeds (F-TRAC, CCIL, FBIL, Brent, CBRICS)
if ! "$PYTHON" -u -m app.ingest --days 7 >> "$LOG" 2>&1; then
  log "WARNING: some feeds had errors during ingest; continuing to publish available data"
fi

# 3. Bake static dashboard pages
if ! "$PYTHON" -u -m app.publish --quiet >> "$LOG" 2>&1; then
  log "ERROR: static publish build failed"
  exit 0
fi

# 4. Commit and push updated database & assets to GitHub
git add -f data/market.db data/cbrics.csv public/ vercel.json 2>/dev/null || true
if ! git diff --staged --quiet; then
  git config user.name "Swayamjit Dalai"
  git config user.email "swayamjitdalai-bit@users.noreply.github.com"
  git commit -m "Auto market data update: $(date '+%Y-%m-%d %H:%M %Z')" >> "$LOG" 2>&1
  
  # Pull rebase in case GitHub Actions pushed concurrently, then push
  git pull --rebase -X theirs origin main >> "$LOG" 2>&1 || true
  if git push origin main >> "$LOG" 2>&1; then
    log "pushed updated market data to GitHub (Vercel deployment triggered automatically)"
  else
    log "WARNING: git push failed; will retry on next interval"
  fi
else
  log "all market data is up to date; no changes to commit"
fi

log "daily refresh completed successfully"
exit 0
