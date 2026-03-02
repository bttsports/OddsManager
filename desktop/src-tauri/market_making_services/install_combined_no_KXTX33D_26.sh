#!/bin/bash
# Install and start the Combined No Spread bot as a systemd service.
# Run this on your VPS from market_making_services/.

set -e

_SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
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
  echo "Error: Could not find project root. Set PROJECT_ROOT explicitly."
  exit 1
fi
DEPLOY_USER="${DEPLOY_USER:-root}"
SCRIPT_NAME="combined_no_KXTX33D_26.py"
SERVICE_NAME="oddsmanager-combinedno-kxtx33d26"

PYTHON="${PYTHON:-/home/your_user/venvs/myenv1/bin/python}"
SCRIPT_PATH="${PROJECT_ROOT}/market_making/combined_no_KXTX33D_26.py"

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "Error: Strategy script not found at $SCRIPT_PATH"
  exit 1
fi

SVC_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
echo "Creating $SVC_FILE ..."
sudo tee "$SVC_FILE" > /dev/null << EOF
[Unit]
Description=OddsManager Combined No - KXTX33D-26
After=network.target oddsmanager-kalshi-api.service

[Service]
Type=simple
User=$DEPLOY_USER
Group=$DEPLOY_USER
WorkingDirectory=$PROJECT_ROOT
EnvironmentFile=$PROJECT_ROOT/.env
Environment=PATH=$(dirname $PYTHON):/usr/local/bin:/usr/bin:/bin
Environment="KALSHI_ENV=PROD"
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
echo "Done. Use: sudo systemctl status $SERVICE_NAME"
