#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

if [[ -f .env ]]; then
    set -a
    source .env
    set +a
fi

BRIDGE_PORT="${BRIDGE_PORT:-8000}"
LT_REGION="${LT_REGION:-eu}"
LT_SUBDOMAIN="${LT_SUBDOMAIN:-}"

if ! command -v lt >/dev/null 2>&1; then
    echo "ERROR: localtunnel CLI not found. Install with: npm i -g localtunnel"
    exit 1
fi

if [[ -n "$LT_SUBDOMAIN" ]]; then
    exec lt --port "$BRIDGE_PORT" --subdomain "$LT_SUBDOMAIN" --region "$LT_REGION"
fi

exec lt --port "$BRIDGE_PORT" --region "$LT_REGION"
