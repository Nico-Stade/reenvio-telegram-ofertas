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


def setup_local_libs_env():
    libs_dir = Path("data/libs")
    if libs_dir.exists() and sys.platform.startswith("linux"):
        so_dirs = set()
        for so_file in libs_dir.rglob("*.so*"):
            if so_file.is_file() or so_file.is_symlink():
                so_dirs.add(str(so_file.parent.resolve()))
        if so_dirs:
            ld_str = ":".join(so_dirs)
            current = os.environ.get("LD_LIBRARY_PATH", "")
            os.environ["LD_LIBRARY_PATH"] = f"{ld_str}:{current}" if current else ld_str
            print(f"• LD_LIBRARY_PATH configurado con {len(so_dirs)} carpetas de data/libs")


async def main():
    print("=" * 65)
    print("🚀 PROBANDO RESOLUCIÓN CON PYDOLL (SIN CHROMEDRIVER)")
    print("=" * 65)

    # 0. Configurar variables de entorno para librerías locales
    setup_local_libs_env()

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
        for p in Path("data").rglob("chrome*"):
            if p.is_file() and not p.suffix and "test" not in p.name:
                binary = str(p.resolve())
                break

    print(f"• Binario detectado: {binary}")

    # Verificar si el binario puede ejecutarse en este Linux
    if binary:
        try:
            os.chmod(binary, 0o755)
            chk = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=5, env=os.environ)
            err_msg = (chk.stderr or chk.stdout).strip()
            print(f"• Ejecución binario: retcode={chk.returncode} | salida={err_msg[:60]}")
            
            # Revisar dependencias faltantes con ldd
            if chk.returncode != 0:
                try:
                    ldd = subprocess.run(["ldd", binary], capture_output=True, text=True, timeout=5, env=os.environ)
                    missing = [line.strip() for line in ldd.stdout.splitlines() if "not found" in line]
                    if missing:
                        print(f"• ⚠️ Librerías Linux faltantes ({len(missing)}):")
                        for m in missing[:10]:
                            print(f"     {m}")
                except Exception:
                    pass
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
    # Evitar fingerprint de headless para no ser bloqueado por Cloudflare
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
    options.add_argument("about:blank")
    options.headless = True

    print("\n• Iniciando Pydoll Chrome con User-Agent de escritorio...")
    try:
        async with Chrome(options=options) as browser:
            try:
                tab = await browser.start()
            except Exception as se:
                print(f"• Aviso en browser.start(): {se}, abriendo con new_tab()...")
                tab = await browser.new_tab()

            print("✓ Pydoll conectado al navegador vía CDP WebSocket!")

            # Navegar a dominio para setear cookies
            print("• Navegando a ofertasshark.cl e inyectando cookies...")
            await tab.go_to("https://link.ofertasshark.cl")

            all_cookies = []
            for c in raw_cookies:
                for domain in [".ofertasshark.cl", "link.ofertasshark.cl"]:
                    cd = {
                        "name": c["name"],
                        "value": c["value"],
                        "domain": domain,
                        "path": "/",
                        "secure": True,
                        "httpOnly": c.get("httpOnly", True),
                    }
                    all_cookies.append(cd)

            for cookie in all_cookies:
                try:
                    await browser.set_cookies([cookie])
                except Exception:
                    try:
                        await tab.set_cookies([cookie])
                    except Exception:
                        pass

            try:
                stored = await browser.get_cookies() if hasattr(browser, "get_cookies") else []
                print(f"✓ Cookies en memoria del navegador: {[c.get('name') for c in stored]}")
            except Exception:
                pass

            print(f"• Navegando a la oferta...")
            await tab.go_to(TEST_SHORT_URL)

            for i in range(12):
                await asyncio.sleep(1)
                try:
                    curr = await tab.current_url()
                except Exception:
                    curr = getattr(tab, "url", None)

                print(f"  [{i+1}s] URL: {str(curr)[:70]}")
                if curr and "ofertasshark.cl" not in str(curr):
                    print("\n" + "🎉" * 25)
                    print("¡EXITO TOTAL CON PYDOLL!")
                    print("URL FINAL:", curr)
                    print("🎉" * 25)
                    return

            # Si después de 12s no redirigió, extraer diagnóstico del DOM
            print("\n--- 🔍 DIAGNÓSTICO DEL CONTENIDO DE LA PÁGINA ---")
            try:
                title = await tab.evaluate("document.title")
                print(f"• Título de la página: {title}")
            except Exception as e:
                print(f"• No se pudo obtener título: {e}")

            try:
                text = await tab.evaluate("document.body.innerText")
                print(f"• Texto visible en pantalla:\n{text.strip()[:400]}")
            except Exception as e:
                print(f"• No se pudo obtener texto: {e}")

            try:
                links = await tab.evaluate("Array.from(document.querySelectorAll('a')).map(a => a.href)")
                print(f"• Enlaces encontrados en la página ({len(links)}): {links[:5]}")
            except Exception:
                pass

    except Exception as e:
        print(f"\n❌ Error en Pydoll: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
