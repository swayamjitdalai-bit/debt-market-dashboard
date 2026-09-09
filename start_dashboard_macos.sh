#!/bin/zsh
# Starts the dashboard backend and opens it in your browser on macOS.
# Leave this terminal window open while you use the dashboard.

set -e
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

PYTHON="$PROJECT_DIR/.venv/bin/python"
if [ ! -f "$PYTHON" ]; then
  PYTHON="python3"
fi

"$PYTHON" -c "import flask, requests, docx, openpyxl" 2>/dev/null || {
  echo "Installing dependencies..."
  "$PYTHON" -m pip install -r requirements.txt
}

echo ""
echo "  Fixed Income & Debt Market Dashboard"
echo "  ------------------------------------"
echo "  Closing report    http://127.0.0.1:5000/"
echo "  CD/CP dashboard   http://127.0.0.1:5000/cdcp"
echo ""
echo "  Keep this window open. Press Ctrl+C to stop the server."
echo ""

open "http://127.0.0.1:5000/" 2>/dev/null || true
exec "$PYTHON" -m app.server
