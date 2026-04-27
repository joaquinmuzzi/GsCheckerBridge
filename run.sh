#!/bin/bash
# Script para ejecutar el scraper de Warmane

# Asegura rutas relativas correctas aunque se invoque desde otro directorio
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -f .env ]]; then
	set -a
	source .env
	set +a
fi

# Verificar si existe el entorno virtual
if [ ! -d "venv" ]; then
	echo "Creando entorno virtual..."
	python3 -m venv venv
fi

source venv/bin/activate

echo "Instalando/actualizando dependencias..."
pip install -r requirements.txt

# Configurar API Key compartida con GsChecker (header X-API-KEY)
export API_SECRET="${BRIDGE_SHARED_SECRET:-${API_SECRET:-secreto123}}"
export BRIDGE_PORT="${BRIDGE_PORT:-8000}"
export BRIDGE_HEADLESS="${BRIDGE_HEADLESS:-true}"
export USE_XVFB="${USE_XVFB:-false}"

# Opcional: navegador real sin ventana visible (mejor contra Cloudflare).
if [[ "${USE_XVFB,,}" == "true" || "${USE_XVFB}" == "1" ]]; then
	if command -v xvfb-run >/dev/null 2>&1; then
		echo "Iniciando bridge con Xvfb (navegador no visible)..."
		export BRIDGE_HEADLESS=false
		exec xvfb-run -a -s "-screen 0 1920x1080x24" python3 main.py
	else
		echo "WARN: USE_XVFB=true pero xvfb-run no está instalado; forzando headless para evitar ventana visible."
		export BRIDGE_HEADLESS=true
	fi
fi

# Ejecutar el servidor
exec python3 main.py
