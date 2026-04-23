# Deploy always-on bridge (local server + localtunnel)

## Objetivo

Mantener `gscheckerbridge` corriendo 24/7 en tu servidor local y exponerlo con `localtunnel`, para que `GsChecker` en Railway consulte este bridge.

## 1) Preparar variables

1. Copiar template:

```bash
cp .env.example .env
```

2. Editar `.env`:

- `BRIDGE_SHARED_SECRET`: clave larga y privada.
- `BRIDGE_PORT`: normalmente `8000`.
- `LT_SUBDOMAIN`: subdominio fijo de localtunnel (si está libre).
- `LT_REGION`: `eu` o `us`.

## 2) Instalar como servicios systemd

Desde el repo `gscheckerbridge`:

```bash
chmod +x deploy/*.sh
./deploy/install_systemd.sh <tu_usuario_linux>
```

Ejemplo:

```bash
./deploy/install_systemd.sh muzzi
```

Esto instala y habilita:

- `gscheckerbridge@<user>.service`
- `gscheckerbridge-localtunnel@<user>.service`

## 3) Ver logs / estado

```bash
sudo systemctl status gscheckerbridge@<user>
sudo systemctl status gscheckerbridge-localtunnel@<user>
sudo journalctl -u gscheckerbridge@<user> -f
sudo journalctl -u gscheckerbridge-localtunnel@<user> -f
```

Healthcheck local:

```bash
curl http://127.0.0.1:8000/health
```

## 4) Configurar Railway (GsChecker)

En variables de entorno de Railway:

- `SCRAPER_BRIDGE_URL=https://<tu-subdominio>.loca.lt`
- `API_SECRET=<mismo valor que BRIDGE_SHARED_SECRET>`
- `BRIDGE_VERIFY_SSL=false`

## 5) Validación rápida desde Railway/GsChecker

Debe poder hacer requests tipo:

- `/get_char/Lordaeron/Frodouwu`
- `/get_char_talents/Lordaeron/Frodouwu`
- `/get_char_statistics/Lordaeron/Frodouwu`
- `/get_char_achievements/Lordaeron/Frodouwu`

## Notas

- Si localtunnel pierde subdominio, cambia `LT_SUBDOMAIN` o deja vacío para URL random.
- Si reinicia el server, systemd levantará ambos servicios automáticamente.
