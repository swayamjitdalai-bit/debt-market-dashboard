#!/bin/zsh
# Refresh local market data and publish the static Vercel site.
# Invoked by ~/Library/LaunchAgents/com.swayamjitdalai.debt-market-dashboard.plist.

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

log "daily refresh started"

if ! "$PYTHON" -u -m app.ingest --days 7 >> "$LOG" 2>&1; then
  log "ERROR: ingest failed"
  exit 1
fi

if ! "$PYTHON" -u -m app.publish --quiet >> "$LOG" 2>&1; then
  log "ERROR: static publish build failed"
  exit 1
fi

if ! "$NPX" -y vercel deploy --prod --yes >> "$LOG" 2>&1; then
  log "ERROR: Vercel deployment failed"
  exit 1
fi

log "daily refresh and Vercel deployment completed"
