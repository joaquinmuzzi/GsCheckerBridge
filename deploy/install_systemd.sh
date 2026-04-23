#!/bin/bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <linux-user>"
    exit 1
fi

TARGET_USER="$1"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_DIR="/opt/gscheckerbridge"

install_deps() {
    echo "Installing dependencies (nodejs/npm + localtunnel) ..."

    if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update
        sudo apt-get install -y nodejs npm python3-venv rsync
        sudo npm i -g localtunnel
        return
    fi

    if command -v pacman >/dev/null 2>&1; then
        sudo pacman -Sy --noconfirm --needed nodejs npm python rsync
        sudo npm i -g localtunnel
        return
    fi

    if command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y nodejs npm python3 rsync
        sudo npm i -g localtunnel
        return
    fi

    echo "ERROR: unsupported distro/package manager."
    echo "Install manually: nodejs npm python(venv) rsync + npm i -g localtunnel"
    exit 1
}

install_deps

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
