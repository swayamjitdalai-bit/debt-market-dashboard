#!/bin/zsh
# Smart background market data ingestion and automated Vercel publisher.
# Runs locally on macOS via LaunchAgent (~/Library/LaunchAgents/com.swayamjitdalai.debt-market-dashboard.plist)
# Acts as a high-reliability fallback and auto-sync alongside GitHub Actions.

set -uo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

PROJECT_DIR="/Users/swayamjitdalai/Documents/debt-market-dashboard-main"
PYTHON="$PROJECT_DIR/.venv/bin/python"
NPX="/opt/homebrew/bin/npx"
LOG="$PROJECT_DIR/data/ingest.log"

cd "$PROJECT_DIR"
mkdir -p data

log() {
  print -r -- "[$(date '+%Y-%m-%d %H:%M:%S %Z')] $*" >> "$LOG"
}

FORCE=false
if [[ "${1:-}" == "--force" ]]; then
  FORCE=true
fi

# Time check: Only run after 5:15 PM (17:15) IST unless --force is given
CURRENT_HOUR=$(date '+%H')
CURRENT_MIN=$(date '+%M')
TIME_VAL=$(( 10#$CURRENT_HOUR * 60 + 10#$CURRENT_MIN ))
TARGET_TIME=$(( 17 * 60 + 15 )) # 17:15

if [[ "$FORCE" != "true" && $TIME_VAL -lt $TARGET_TIME ]]; then
  exit 0
fi

# Sync with GitHub first
git pull origin main --quiet 2>/dev/null || true

log "daily refresh started"

# 1. Ingest market feeds
if ! "$PYTHON" -u -m app.ingest --days 7 >> "$LOG" 2>&1; then
  log "ERROR: ingest failed"
  exit 1
fi

# 2. Bake static dashboard pages
if ! "$PYTHON" -u -m app.publish --quiet >> "$LOG" 2>&1; then
  log "ERROR: static publish build failed"
  exit 1
fi

# 3. Commit and push updated database & assets to GitHub
git add -f data/market.db data/cbrics.csv public/ vercel.json 2>/dev/null || true
if ! git diff --staged --quiet; then
  git config user.name "Swayamjit Dalai"
  git config user.email "swayamjitdalai-bit@users.noreply.github.com"
  git commit -m "Auto market data update: $(date '+%Y-%m-%d %H:%M %Z')" >> "$LOG" 2>&1
  git push origin main >> "$LOG" 2>&1 || true
  log "pushed updated market data to GitHub"
fi

# 4. Deploy directly to Vercel production
if ! "$NPX" -y vercel deploy --prod --yes >> "$LOG" 2>&1; then
  log "ERROR: Vercel deployment failed"
  exit 1
fi

log "daily refresh and Vercel deployment completed successfully"
