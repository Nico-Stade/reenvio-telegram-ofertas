"""
test_pydoll.py — Prueba de resolución directa con Pydoll (sin chromedriver).
"""
import sys
import os
import asyncio
import json
import subprocess
from pathlib import Path

# Asegurar UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TEST_SHORT_URL = "https://link.ofertasshark.cl/link/v2/redirect?e=a9DMMVTLRG0_UI_D4P3NZ3K5Ra251FiVlp64ekPBlEYlIJ7iBOseUhHlY4B5NkD6AXYJEQYcNnSx9A0FMoYUr3HopBwOD_lu9k0acZWqJ78-WlaheY_iYKITcRLOsBn7beI1ONbJPMRbZvm3w486EIyeyeTKN12Ch4DetYouXFz4BfkGTbsovvAgqKYx93LkajbrDlOltjE4ZM4ACpYJbzQO_ecnvdUD1A4Y7WNSdh0F6sgQ-ZUacnjMGNTNkG_MjYoah-t2gxq8Oy9A-8CPHQ8RWsULgLpMya48aBn2Bx_QxS6c3lNsE9GTiWnxX6iw-XwWsXAG&_tl=ba9988d60521b78d8b912850f7833fd4"


async def main():
    print("=" * 65)
    print("🚀 PROBANDO RESOLUCIÓN CON PYDOLL (SIN CHROMEDRIVER)")
    print("=" * 65)

    # 1. Buscar binario
    candidates = [
        Path("data/chrome-headless-shell-linux64/chrome-headless-shell"),
        Path("data/chrome-linux64/chrome"),
        Path("data/chrome/chrome"),
        Path("data/chromium/chrome"),
    ]
    binary = None
    for c in candidates:
        if c.exists():
            binary = str(c.resolve())
            break

    if not binary:
        # Búsqueda recursiva
        for p in Path("data").rglob("chrome*"):
            if p.is_file():
                binary = str(p.resolve())
                break

    print(f"• Binario detectado: {binary}")

    # Verificar si el binario puede ejecutarse en este Linux
    if binary:
        try:
            os.chmod(binary, 0o755)
            chk = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=5)
            print(f"• Ejecución binario: retcode={chk.returncode} | out={(chk.stdout or chk.stderr).strip()[:80]}")
        except Exception as e:
            print(f"• ❌ Error al invocar binario directamente: {e}")

    # 2. Cargar cookies
    cookies_path = Path("data/shark_cookies.json")
    if not cookies_path.exists():
        print("❌ data/shark_cookies.json no existe!")
        return

    with open(cookies_path, "r", encoding="utf-8") as f:
        raw_cookies = json.load(f)
    print(f"• Cookies cargadas: {len(raw_cookies)} desde {cookies_path}")

    # 3. Iniciar Pydoll
    from pydoll.browser import Chrome
    from pydoll.browser.options import ChromiumOptions

    options = ChromiumOptions()
    if binary:
        options.binary_location = binary
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.headless = True

    print("• Iniciando Pydoll Chrome...")
    try:
        async with Chrome(options=options) as browser:
            page = await browser.get_page()
            print("✓ Pydoll conectado al navegador vía CDP WebSocket!")

            # Navegar a dominio para setear cookies
            await page.go_to("https://link.ofertasshark.cl")
            for c in raw_cookies:
                try:
                    await page.set_cookie(name=c["name"], value=c["value"], domain=c.get("domain", ".ofertasshark.cl"))
                except Exception as ce:
                    pass

            print(f"• Navegando a la oferta...")
            await page.go_to(TEST_SHORT_URL)

            for i in range(10):
                await asyncio.sleep(1)
                curr = await page.current_url
                print(f"  [{i+1}s] URL: {curr[:70]}")
                if curr and "ofertasshark.cl" not in curr:
                    print("\n" + "🎉" * 25)
                    print("¡EXITO TOTAL CON PYDOLL!")
                    print("URL FINAL:", curr)
                    print("🎉" * 25)
                    break
    except Exception as e:
        print(f"\n❌ Error en Pydoll: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
