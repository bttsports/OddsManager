#!/bin/bash
# Install and start the market-making strategy as a systemd service.
# Run this on your VPS (e.g. DigitalOcean) from market_making_services/.
#
# Prerequisites:
#   - Project cloned to PROJECT_ROOT
#   - venv created and deps installed
#   - .env with KALSHI_API_KEY, KALSHI_PRIVATE_KEY_PATH
#   - Strategy script in market_making/, this installer in market_making_services/
#
# Usage (from market_making_services/): ./install_KXTXSENDPRIMARYMOV_26MAR03.sh

set -e

_SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Find project root: walk up until we find a dir containing market_making/
find_project_root() {
  local d="$1"
  while [[ -n "$d" && "$d" != "/" ]]; do
    [[ -d "$d/market_making" ]] && echo "$d" && return
    d="$(dirname "$d")"
  done
  echo ""
}
PROJECT_ROOT="${PROJECT_ROOT:-$(find_project_root "$_SCRIPT_DIR")}"
if [[ -z "$PROJECT_ROOT" ]]; then
  echo "Error: Could not find project root (no parent dir contains market_making/). Set PROJECT_ROOT explicitly."
  exit 1
fi
DEPLOY_USER="${DEPLOY_USER:-root}"
SCRIPT_NAME="mm_KXTXSENDPRIMARYMOV_26MAR03.py"
SERVICE_NAME="oddsmanager-mm-kxtxsendprimarymov26mar03"

# Default: /home/your_user/venvs/myenv1/bin/python. Override: PYTHON=$PROJECT_ROOT/venv/bin/python
PYTHON="${PYTHON:-/home/your_user/venvs/myenv1/bin/python}"
SCRIPT_PATH="${PROJECT_ROOT}/market_making/mm_KXTXSENDPRIMARYMOV_26MAR03.py"

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "Error: Strategy script not found at $SCRIPT_PATH"
  echo "Copy $SCRIPT_NAME to market_making/ first."
  exit 1
fi

SVC_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
echo "Creating $SVC_FILE ..."
sudo tee "$SVC_FILE" > /dev/null << EOF
[Unit]
Description=OddsManager MM - KXTXSENDPRIMARYMOV-26MAR03
After=network.target oddsmanager-kalshi-api.service

[Service]
Type=simple
User=$DEPLOY_USER
Group=$DEPLOY_USER
WorkingDirectory=$PROJECT_ROOT
EnvironmentFile=$PROJECT_ROOT/.env
Environment=PATH=$(dirname $PYTHON):/usr/local/bin:/usr/bin:/bin
Environment="KALSHI_ENV=DEMO"
ExecStart=$PYTHON $SCRIPT_PATH
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "Reloading systemd, enabling and starting $SERVICE_NAME ..."
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl start "$SERVICE_NAME"
sudo systemctl status "$SERVICE_NAME" --no-pager
echo ""
echo "Done. Use: sudo systemctl status $SERVICE_NAME  # check status"
echo "        sudo journalctl -u $SERVICE_NAME -f     # follow logs"
