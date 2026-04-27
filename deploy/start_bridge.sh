#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

if [[ -f .env ]]; then
    set -a
    source .env
    set +a
fi

if [[ ! -d venv ]]; then
    python3 -m venv venv
fi

source venv/bin/activate
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt >/dev/null

export API_SECRET="${BRIDGE_SHARED_SECRET:-${API_SECRET:-secreto123}}"
export BRIDGE_PORT="${BRIDGE_PORT:-8000}"
export BRIDGE_HEADLESS="${BRIDGE_HEADLESS:-true}"
export USE_XVFB="${USE_XVFB:-false}"

if [[ "${USE_XVFB,,}" == "true" || "${USE_XVFB}" == "1" ]]; then
    if command -v xvfb-run >/dev/null 2>&1; then
        export BRIDGE_HEADLESS=false
        exec xvfb-run -a -s "-screen 0 1920x1080x24" python main.py
    else
        export BRIDGE_HEADLESS=true
    fi
fi

exec python main.py
