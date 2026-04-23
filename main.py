from fastapi import FastAPI, HTTPException, Header, Depends, status, Query
from DrissionPage import ChromiumPage, ChromiumOptions
from typing import Optional
import os
import asyncio

app = FastAPI(title="Warmane HTML Bridge")

# Semáforo para que las peticiones no choquen en el mismo navegador
browser_lock = asyncio.Lock()
_global_browser = None

def get_browser():
    global _global_browser
    if _global_browser is None:
        print("Iniciando instancia persistente de Chromium...")
        co = ChromiumOptions()
        co.set_argument('--disable-gpu')
        co.set_argument('--no-sandbox')
        # Intentar ocultar rastro de automatización
        co.set_argument('--disable-blink-features=AutomationControlled')
        co.set_user_data_path('/tmp/warmane_persistent_session')
        _global_browser = ChromiumPage(co)
    return _global_browser

def resolve_cloudflare(page):
    """Intenta detectar y pulsar el botón de Cloudflare de forma automática."""
    try:
        iframe = page.get_frame('@src^https://challenges.cloudflare.com')
        if iframe:
            btn = iframe('#challenge-stage') or iframe('.mark') or iframe('xpath://input[@type="checkbox"]')
            if btn:
                print("Bypass automático: Pulsando checkbox de Cloudflare...")
                btn.click()
                return True
    except:
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
        try:
            page = get_browser()
            print(f"Navegando a: {url}")
            page.get(url)

            def _is_cloudflare_like(html: str) -> bool:
                if not html:
                    return True
                checks = (
                    "verify you are human",
                    "just a moment",
                    "challenge-platform",
                    "challenges.cloudflare.com",
                    "cf-challenge",
                )
                low = html.lower()
                return any(token in low for token in checks)

            def _looks_like_warmane_content(html: str) -> bool:
                if not html:
                    return False
                low = html.lower()
                patterns = (
                    "armory.warmane.com",
                    "character-sheet",
                    "profile-content",
                    "specialization",
                    "tooltip_enus",
                    "level-race-class",
                    "guild-name",
                )
                return any(token in low for token in patterns)
            
            # Bucle de espera y auto-bypass
            success = False
            for i in range(25): # Hasta 50 segundos total
                # ¿Ya cargó el contenido real?
                if page.ele('text:Achievement points', timeout=0.1) or page.ele('.profile-content', timeout=0.1):
                    print("Contenido detectado satisfactoriamente.")
                    success = True
                    break

                current_html = page.html or ""
                if _looks_like_warmane_content(current_html) and not _is_cloudflare_like(current_html):
                    print("HTML de Warmane detectado, continuando.")
                    success = True
                    break
                
                # ¿Hay captcha?
                if page.ele('text:Verify you are human', timeout=0.1) or page.ele('text:Just a moment', timeout=0.1):
                    print(f"Intento {i+1}: Cloudflare detectado. Intentando bypass automático...")
                    resolve_cloudflare(page)
                
                page.wait(2)

            if not success:
                # Verificación final para Guilds o Logros
                if not page.ele('.guild-name, .achievement-list', timeout=1):
                    final_html = page.html or ""
                    if _is_cloudflare_like(final_html):
                        print("Error: No se pudo cargar el contenido tras la espera.")
                        raise Exception("Scrape timeout or blocked")
                    print("No hubo selectores esperados, pero hay HTML util. Continuando.")

            # Selector opcional solicitado por el usuario
            if wait_selector != "body":
                page.ele(wait_selector, timeout=5)

            # Pausa de renderizado final para asegurar que el JS llene las tablas
            await asyncio.sleep(3)

            return {"html": page.html}

        except Exception as e:
            print(f"Error en scraping: {str(e)}")
            raise HTTPException(status_code=500, detail="scrape failed")


@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/get_char/{realm}/{name}")
async def get_character_profile(
    realm: str, 
    name: str, 
    wait_selector: str = Query("body"), 
    _=Depends(verify_api_key)
):
    url = f"https://armory.warmane.com/character/{name}/{realm}/profile"
    return await scrape_url(url, wait_selector)

@app.get("/get_char_achievements/{realm}/{name}")
async def get_char_achievements(
    realm: str, 
    name: str, 
    wait_selector: str = Query("body"), 
    _=Depends(verify_api_key)
):
    url = f"https://armory.warmane.com/character/{name}/{realm}/achievements"
    return await scrape_url(url, wait_selector)

@app.get("/get_char_statistics/{realm}/{name}")
async def get_char_statistics(
    realm: str, 
    name: str, 
    wait_selector: str = Query("body"), 
    _=Depends(verify_api_key)
):
    url = f"https://armory.warmane.com/character/{name}/{realm}/statistics"
    return await scrape_url(url, wait_selector)

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
    port = int(os.getenv("BRIDGE_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
