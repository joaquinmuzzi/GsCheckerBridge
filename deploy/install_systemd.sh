#!/bin/bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <linux-user>"
    exit 1
fi

TARGET_USER="$1"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_DIR="/opt/gscheckerbridge"

echo "Installing dependencies (nodejs/npm + localtunnel) ..."
sudo apt-get update
sudo apt-get install -y nodejs npm python3-venv
sudo npm i -g localtunnel

echo "Syncing repository to $TARGET_DIR ..."
sudo mkdir -p "$TARGET_DIR"
sudo rsync -a --delete "$REPO_DIR/" "$TARGET_DIR/"
sudo chown -R "$TARGET_USER":"$TARGET_USER" "$TARGET_DIR"

if [[ ! -f "$TARGET_DIR/.env" ]]; then
    sudo -u "$TARGET_USER" cp "$TARGET_DIR/.env.example" "$TARGET_DIR/.env"
    echo "Created $TARGET_DIR/.env from template. Edit it before starting services."
fi

echo "Installing systemd units ..."
sudo cp "$TARGET_DIR/deploy/systemd/gscheckerbridge.service" /etc/systemd/system/gscheckerbridge@.service
sudo cp "$TARGET_DIR/deploy/systemd/gscheckerbridge-localtunnel.service" /etc/systemd/system/gscheckerbridge-localtunnel@.service
sudo systemctl daemon-reload

echo "Enabling services ..."
sudo systemctl enable gscheckerbridge@"$TARGET_USER"
sudo systemctl enable gscheckerbridge-localtunnel@"$TARGET_USER"

echo "Starting services ..."
sudo systemctl restart gscheckerbridge@"$TARGET_USER"
sudo systemctl restart gscheckerbridge-localtunnel@"$TARGET_USER"

echo "Done. Check status with:"
echo "  sudo systemctl status gscheckerbridge@${TARGET_USER}"
echo "  sudo systemctl status gscheckerbridge-localtunnel@${TARGET_USER}"
