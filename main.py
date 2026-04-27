from fastapi import FastAPI, HTTPException, Header, Depends, status, Query
from DrissionPage import ChromiumPage, ChromiumOptions
from typing import Optional
import os
import asyncio
import logging
import sys
import atexit
from logging.handlers import RotatingFileHandler

app = FastAPI(title="Warmane HTML Bridge")


def configure_logging() -> logging.Logger:
    os.makedirs("logs", exist_ok=True)
    logger = logging.getLogger("gscheckerbridge")
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    info_handler = RotatingFileHandler(
        "logs/bridge.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    info_handler.setLevel(logging.INFO)
    info_handler.setFormatter(formatter)

    error_handler = RotatingFileHandler(
        "logs/bridge-errors.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    logger.handlers.clear()
    logger.addHandler(info_handler)
    logger.addHandler(error_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False

    return logger


logger = configure_logging()

LOCK_PATH = "/tmp/gscheckerbridge.lock"


def acquire_lock(lock_path: str) -> None:
    if os.path.exists(lock_path):
        try:
            with open(lock_path, "r", encoding="utf-8") as f:
                pid_str = f.read().strip()
            if pid_str:
                pid = int(pid_str)
                os.kill(pid, 0)
                logger.error("Otro proceso del bridge ya está corriendo (PID %s).", pid)
                sys.exit(1)
        except ProcessLookupError:
            pass
        except Exception:
            pass

    with open(lock_path, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))

    def _cleanup() -> None:
        try:
            if os.path.exists(lock_path):
                os.remove(lock_path)
        except Exception:
            pass

    atexit.register(_cleanup)

# Semáforo para que las peticiones no choquen en el mismo navegador
browser_lock = asyncio.Lock()
_global_browser = None


def reset_browser(reason: str = ""):
    global _global_browser
    if reason:
        logger.warning("Reiniciando navegador: %s", reason)

    if _global_browser is not None:
        try:
            _global_browser.quit()
        except Exception:
            logger.exception("Error cerrando instancia previa de Chromium")
    _global_browser = None

def get_browser():
    global _global_browser
    if _global_browser is None:
        logger.info("Iniciando instancia persistente de Chromium...")
        co = ChromiumOptions()
        co.set_argument('--disable-gpu')
        co.set_argument('--no-sandbox')
        # Intentar ocultar rastro de automatización
        co.set_argument('--disable-blink-features=AutomationControlled')
        co.set_user_data_path('/tmp/warmane_persistent_session')
        
        # Configurar modo headless/headed
        headless = os.getenv("BRIDGE_HEADLESS", "true").lower() in ("true", "1", "yes")
        co.headless(headless)
        if not headless:
            logger.warning("Modo HEADED activado - se abrirá ventana de navegador visible")
        else:
            logger.info("Modo HEADLESS activado - navegador en segundo plano")
        
        _global_browser = ChromiumPage(co)
    return _global_browser

def resolve_cloudflare(page):
    """Intenta detectar y pulsar el botón de Cloudflare de forma automática."""
    try:
        # Buscar iframes explícitamente evita LocatorError cuando el método espera
        # un único frame y recibe un selector ambiguo.
        iframe_elements = page.eles(
            'xpath://iframe[contains(@src,"challenges.cloudflare.com")]', timeout=0.4
        ) or []

        for iframe in iframe_elements:
            try:
                frame = page.get_frame(iframe, timeout=0.4)
            except Exception:
                continue

            btn = (
                frame.ele('#challenge-stage', timeout=0.3)
                or frame.ele('.mark', timeout=0.3)
                or frame.ele('xpath://input[@type="checkbox"]', timeout=0.3)
                or frame.ele('xpath://div[@role="checkbox"]', timeout=0.3)
            )
            if btn:
                logger.info("Bypass automático: Pulsando checkbox de Cloudflare...")
                btn.click()
                return True

        # Fallback por si Cloudflare renderiza el control fuera del frame esperado.
        btn = (
            page.ele('xpath://input[@type="checkbox"]', timeout=0.3)
            or page.ele('xpath://div[@role="checkbox"]', timeout=0.3)
        )
        if btn:
            logger.info("Bypass automático: Pulsando checkbox Cloudflare (fallback)...")
            btn.click()
            return True
    except Exception:
        logger.exception("Error intentando resolver challenge de Cloudflare")
        pass
    return False

# Configuración de seguridad.
# Compatibilidad: GsChecker envía API_SECRET como X-API-KEY.
API_KEY_CREDENTIAL = (
    os.getenv("API_SECRET")
    or os.getenv("X_API_KEY")
    or os.getenv("SCRAPER_API_KEY")
    or ""
).strip()

def verify_api_key(x_api_key: Optional[str] = Header(None)):
    # Si no hay clave configurada, permitimos acceso para entornos locales.
    if not API_KEY_CREDENTIAL:
        return x_api_key

    if (x_api_key or "").strip() != API_KEY_CREDENTIAL:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid api key",
        )
    return x_api_key

async def scrape_url(url: str, wait_selector: str):
    async with browser_lock:
        for attempt in range(2):
            try:
                page = get_browser()
                logger.info("Navegando a: %s (intento %s/2)", url, attempt + 1)
                page.get(url)

                section = "profile"
                if "/talents" in url:
                    section = "talents"
                elif "/statistics" in url:
                    section = "statistics"
                elif "/achievements" in url:
                    section = "achievements"
                elif "/guild/" in url and "/summary/" in url:
                    section = "guild"

                section_markers = {
                    "profile": (
                        "id=\"character-sheet\"",
                        "character-sheet",
                        "level-race-class",
                        "profile-content",
                    ),
                    "talents": (
                        "data-spec",
                        "specialization",
                        "talent",
                    ),
                    "statistics": (
                        "data-table-list",
                        "statistics",
                        "tooltip_enus",
                    ),
                    "achievements": (
                        "achievement-list",
                        "achievement points",
                        "class=\"achievement",
                    ),
                    "guild": (
                        "data-table-list",
                        "guild-name",
                        "guild",
                    ),
                }

                def _looks_like_warmane_content(html: str) -> bool:
                    if not html:
                        return False
                    low = html.lower()
                    patterns = section_markers.get(section, section_markers["profile"])
                    return any(token in low for token in patterns)

                def _is_cloudflare_like(html: str) -> bool:
                    if not html:
                        return True

                    # If we can already see real Warmane content, do not treat it
                    # as Cloudflare even if challenge scripts are present in the page.
                    if _looks_like_warmane_content(html):
                        return False

                    checks = (
                        "verify you are human",
                        "just a moment",
                        "un momento",
                        "verifique que es humano",
                        "challenges.cloudflare.com",
                        "cf-challenge",
                        "cf-turnstile",
                    )
                    low = html.lower()
                    return any(token in low for token in checks)

                # Bucle de espera y auto-bypass
                success = False
                for i in range(15):  # Hasta 30 segundos total por intento
                    # ¿Ya cargó el contenido real?
                    if page.ele('text:Achievement points', timeout=0.1) or page.ele('.profile-content', timeout=0.1) or page.ele('#character-sheet', timeout=0.1):
                        logger.info("Contenido detectado satisfactoriamente.")
                        success = True
                        break

                    current_html = page.html or ""
                    if _looks_like_warmane_content(current_html) and not _is_cloudflare_like(current_html):
                        logger.info("HTML de Warmane detectado, continuando.")
                        success = True
                        break

                    # ¿Hay captcha? Intentar bypass tanto por texto visible como por HTML del challenge.
                    if (
                        _is_cloudflare_like(current_html)
                        or page.ele('text:Verify you are human', timeout=0.1)
                        or page.ele('text:Just a moment', timeout=0.1)
                        or page.ele('text:Un momento', timeout=0.1)
                    ):
                        logger.warning("Intento %s: Cloudflare detectado. Intentando bypass automático...", i + 1)
                        resolve_cloudflare(page)

                    page.wait(2)

                if not success:
                    # Verificación final para Guilds o Logros
                    if not page.ele('.guild-name, .achievement-list', timeout=1):
                        final_html = page.html or ""
                        if _is_cloudflare_like(final_html):
                            logger.error("No se pudo cargar el contenido tras la espera.")
                            raise Exception("Scrape timeout or blocked")
                        logger.warning("No hubo selectores esperados, pero hay HTML util. Continuando.")

                # Selector opcional solicitado por el usuario
                if wait_selector != "body":
                    page.ele(wait_selector, timeout=5)

                # Pausa de renderizado final para asegurar que el JS llene las tablas
                await asyncio.sleep(3)

                return {"html": page.html}
            except Exception:
                logger.exception("Error en scraping (intento %s/2)", attempt + 1)
                reset_browser("scrape fallido o página desconectada")
                if attempt == 0:
                    await asyncio.sleep(1)
                    continue
                raise HTTPException(status_code=500, detail="scrape failed")


@app.get("/health")
async def health():
    logger.info("Healthcheck solicitado")
    return {"status": "ok"}

@app.get("/get_char/{realm}/{name}")
async def get_character_profile(
    realm: str, 
    name: str, 
    wait_selector: str = Query("body"), 
    _=Depends(verify_api_key)
):
    primary_url = f"https://armory.warmane.com/character/{name}/{realm}/profile"
    fallback_url = f"https://armory.warmane.com/character/{name}/{realm}"

    try:
        return await scrape_url(primary_url, wait_selector)
    except HTTPException as exc:
        logger.warning(
            "Primary character path failed (%s/%s): %s. Retrying with base character URL.",
            name,
            realm,
            getattr(exc, "detail", "unknown"),
        )
        return await scrape_url(fallback_url, wait_selector)

@app.get("/get_char_achievements/{realm}/{name}")
async def get_char_achievements(
    realm: str,
    name: str,
    category: Optional[int] = Query(None),
    wait_selector: str = Query("body"),
    _=Depends(verify_api_key),
):
    url = f"https://armory.warmane.com/character/{name}/{realm}/achievements"
    await scrape_url(url, wait_selector)

    if category is not None:
        async with browser_lock:
            page = get_browser()
            logger.info(
                "Fetching achievements via XHR: char=%s realm=%s category=%s",
                name,
                realm,
                category,
            )
            script = f"""
var xhr = new XMLHttpRequest();
xhr.open('POST', '/character/{name}/{realm}/achievements', false);
xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8');
xhr.setRequestHeader('Accept', 'application/json, text/javascript, */*; q=0.01');
xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
var csrf = document.querySelector('meta[name="csrf-token"]');
if (csrf) xhr.setRequestHeader('X-CSRF-TOKEN', csrf.getAttribute('content'));
xhr.send('category={category}');
try {{ return JSON.parse(xhr.responseText); }} catch(e) {{ return {{content: xhr.responseText, raw_len: xhr.responseText.length}}; }}
"""
            try:
                result = page.run_js(script)
                if isinstance(result, dict) and result.get("content"):
                    logger.info(
                        "Achievements XHR OK: category=%s content_len=%s",
                        category,
                        len(str(result.get("content", ""))),
                    )
                    return result
                logger.warning("Achievements XHR returned unexpected result: %s", str(result)[:200])
            except Exception:
                logger.exception("Achievements XHR failed for %s/%s cat=%s", name, realm, category)

    async with browser_lock:
        page = get_browser()
        return {"html": page.html}

@app.get("/get_char_statistics/{realm}/{name}")
async def get_char_statistics(
    realm: str,
    name: str,
    category: Optional[int] = Query(None),
    wait_selector: str = Query("body"),
    _=Depends(verify_api_key),
):
    url = f"https://armory.warmane.com/character/{name}/{realm}/statistics"
    # First navigate the browser to get past Cloudflare.
    await scrape_url(url, wait_selector)

    if category is not None:
        # Statistics data is loaded via AJAX. Re-use the existing authenticated
        # browser session to POST the AJAX request synchronously from JS.
        async with browser_lock:
            page = get_browser()
            logger.info(
                "Fetching statistics via XHR: char=%s realm=%s category=%s",
                name, realm, category,
            )
            script = f"""
var xhr = new XMLHttpRequest();
xhr.open('POST', '/character/{name}/{realm}/statistics', false);
xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8');
xhr.setRequestHeader('Accept', 'application/json, text/javascript, */*; q=0.01');
xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
var csrf = document.querySelector('meta[name="csrf-token"]');
if (csrf) xhr.setRequestHeader('X-CSRF-TOKEN', csrf.getAttribute('content'));
xhr.send('category={category}');
try {{ return JSON.parse(xhr.responseText); }} catch(e) {{ return {{content: xhr.responseText, raw_len: xhr.responseText.length}}; }}
"""
            try:
                result = page.run_js(script)
                if isinstance(result, dict) and result.get("content"):
                    logger.info(
                        "Statistics XHR OK: category=%s content_len=%s",
                        category, len(str(result.get("content", ""))),
                    )
                    return result
                logger.warning("Statistics XHR returned unexpected result: %s", str(result)[:200])
            except Exception:
                logger.exception("Statistics XHR failed for %s/%s cat=%s", name, realm, category)

    # Fallback: return the full page HTML (partial data)
    async with browser_lock:
        page = get_browser()
        return {"html": page.html}

@app.get("/get_char_talents/{realm}/{name}")
async def get_char_talents(
    realm: str, 
    name: str, 
    wait_selector: str = Query("body"), 
    _=Depends(verify_api_key)
):
    url = f"https://armory.warmane.com/character/{name}/{realm}/talents"
    return await scrape_url(url, wait_selector)

@app.get("/get_guild_summary/{realm}/{guild_name}/{name}")
async def get_guild_summary(
    realm: str, 
    guild_name: str, 
    name: str, 
    wait_selector: str = Query("body"), 
    _=Depends(verify_api_key)
):
    formatted_guild = guild_name.replace(" ", "+")
    url = f"https://armory.warmane.com/guild/{formatted_guild}/{realm}/summary/{name}"
    return await scrape_url(url, wait_selector)

if __name__ == "__main__":
    import uvicorn
    acquire_lock(LOCK_PATH)
    port = int(os.getenv("BRIDGE_PORT", "8000"))
    logger.info("Iniciando bridge en puerto %s", port)
    uvicorn.run(app, host="0.0.0.0", port=port)
