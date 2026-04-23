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

# Ejecutar el servidor
python3 main.py
