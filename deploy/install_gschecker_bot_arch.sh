#!/bin/bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <linux-user> <absolute-path-to-GsChecker> [service-name]"
    echo "Example: $0 muzzi /home/muzzi/repos/wow/GsChecker gscheckerbot"
    exit 1
fi

TARGET_USER="$1"
BOT_DIR="$2"
SERVICE_NAME="${3:-gscheckerbot}"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if ! command -v pacman >/dev/null 2>&1; then
    echo "ERROR: This installer is for Arch Linux (pacman) only."
    exit 1
fi

if [[ ! -d "$BOT_DIR" ]]; then
    echo "ERROR: BOT_DIR does not exist: $BOT_DIR"
    exit 1
fi

if [[ ! -f "$BOT_DIR/run.sh" ]]; then
    echo "ERROR: run.sh not found in BOT_DIR: $BOT_DIR"
    exit 1
fi

if [[ ! -f "$BOT_DIR/.env" ]]; then
    if [[ -f "$BOT_DIR/.env.example" ]]; then
        sudo -u "$TARGET_USER" cp "$BOT_DIR/.env.example" "$BOT_DIR/.env"
        echo "Created $BOT_DIR/.env from template. Edit it before using the bot."
    else
        echo "ERROR: Missing $BOT_DIR/.env and .env.example"
        exit 1
    fi
fi

echo "Installing dependencies on Arch (python + pip + venv support)..."
sudo pacman -Sy --noconfirm --needed python python-pip

echo "Preparing bot venv and dependencies..."
sudo -u "$TARGET_USER" bash -lc "cd '$BOT_DIR' && if [[ ! -d venv ]]; then python3 -m venv venv; fi && source venv/bin/activate && pip install -r requirements.txt"

echo "Installing systemd service: ${SERVICE_NAME}.service"
sudo tee "$UNIT_FILE" >/dev/null <<EOF
[Unit]
Description=GsChecker Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${TARGET_USER}
WorkingDirectory=${BOT_DIR}
ExecStart=${BOT_DIR}/run.sh
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}.service"
sudo systemctl restart "${SERVICE_NAME}.service"

echo "Done. Check status with:"
echo "  sudo systemctl status ${SERVICE_NAME}.service"
echo "  sudo journalctl -u ${SERVICE_NAME}.service -f"