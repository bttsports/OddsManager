#!/bin/bash
# Install and start the market-making strategy as a systemd service.
# Run this on your VPS (e.g. DigitalOcean) after copying the strategy script and this installer.
#
# Prerequisites:
#   - Project cloned to PROJECT_ROOT
#   - venv created and deps installed
#   - .env with KALSHI_API_KEY, KALSHI_PRIVATE_KEY_PATH
#
# Usage: ./install_KXTXSENDPRIMARYMOV_26MAR03.sh
# Or:    bash install_KXTXSENDPRIMARYMOV_26MAR03.sh

set -e

# Edit these if your paths differ:
DEPLOY_USER="${DEPLOY_USER:-your_user}"
PROJECT_ROOT="${PROJECT_ROOT:-/home/your_user/projects/OddsManager}"
SCRIPT_NAME="mm_KXTXSENDPRIMARYMOV_26MAR03.py"
SERVICE_NAME="oddsmanager-mm-kxtxsendprimarymov26mar03"

PYTHON="${PROJECT_ROOT}/venv/bin/python"
SCRIPT_PATH="${PROJECT_ROOT}/mm_KXTXSENDPRIMARYMOV_26MAR03.py"

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "Error: Strategy script not found at $SCRIPT_PATH"
  echo "Copy $SCRIPT_NAME to your project root first."
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
Environment=PATH=$PROJECT_ROOT/venv/bin
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
echo "Done. Use: sudo systemctl status $SERVICE_NAME  # check status"
echo "        sudo journalctl -u $SERVICE_NAME -f     # follow logs"
