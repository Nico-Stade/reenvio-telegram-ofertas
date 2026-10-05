"""
test_resolver.py — Script de prueba directa del servicio de resolución de enlaces.
Permite diagnosticar Chrome, cookies, librerías del sistema y redirecciones.
"""
import sys
import os
import asyncio
import subprocess
from pathlib import Path

# Asegurar UTF-8 en salida estándar
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from engine.resolver import SharkLinkResolver, STORE_DOMAIN_MAP

TEST_SHORT_URL = "https://link.ofertasshark.cl/link/v2/redirect?e=a9DMMVTLRG0_UI_D4P3NZ3K5Ra251FiVlp64ekPBlEYlIJ7iBOseUhHlY4B5NkD6AXYJEQYcNnSx9A0FMoYUr3HopBwOD_lu9k0acZWqJ78-WlaheY_iYKITcRLOsBn7beI1ONbJPMRbZvm3w486EIyeyeTKN12Ch4DetYouXFz4BfkGTbsovvAgqKYx93LkajbrDlOltjE4ZM4ACpYJbzQO_ecnvdUD1A4Y7WNSdh0F6sgQ-ZUacnjMGNTNkG_MjYoah-t2gxq8Oy9A-8CPHQ8RWsULgLpMya48aBn2Bx_QxS6c3lNsE9GTiWnxX6iw-XwWsXAG&_tl=ba9988d60521b78d8b912850f7833fd4"


async def run_diagnostics():
    print("=" * 65)
    print("🔍 DIAGNÓSTICO DEL RESOLVER DE OFERTAS")
    print("=" * 65)
    print(f"• Sistema Operativo : {sys.platform}")
    print(f"• Versión de Python : {sys.version.split()[0]}")
    print(f"• Directorio actual : {os.getcwd()}")

    # Verificar distribución Linux
    if Path("/etc/os-release").exists():
        try:
            with open("/etc/os-release") as f:
                lines = [l.strip() for l in f if "PRETTY_NAME" in l]
                if lines:
                    print(f"• Linux Distro      : {lines[0].split('=')[-1].strip('\"')}")
        except Exception:
            pass

    cookies_path = Path("data/shark_cookies.json")
    print(f"• Archivo de cookies: {cookies_path} -> {'✓ EXISTE' if cookies_path.exists() else '❌ NO EXISTE (Copia tu data/shark_cookies.json)'}")

    # Diagnóstico de binarios en el sistema
    print("\n--- 1. Búsqueda y prueba directa de binarios ---")
    search_dirs = [Path("data"), Path("."), Path("/tmp"), Path("/usr/bin")]
    found_binaries = []
    for sroot in search_dirs:
        if sroot.exists():
            for name in ("chrome", "chromium", "google-chrome", "chrome-headless-shell"):
                try:
                    for p in sroot.rglob(name):
                        if p.is_file():
                            found_binaries.append(str(p.resolve()))
                except Exception:
                    pass

    # Buscar también el binario descargado por undetected_chromedriver
    uc_path = Path(os.path.expanduser("~")) / ".local/share/undetected_chromedriver/undetected_chromedriver"
    if uc_path.exists():
        found_binaries.append(str(uc_path.resolve()))

    for b in set(found_binaries):
        try:
            os.chmod(b, 0o755)
            res = subprocess.run([b, "--version"], capture_output=True, text=True, timeout=5)
            out = (res.stdout or res.stderr).strip()
            print(f"  • {b} -> Retcode: {res.returncode} | Output: {out[:60]}")
        except Exception as e:
            print(f"  • {b} -> ❌ Error al ejecutar: {e}")

    # Probar resolución con el resolver
    print("\n--- 2. Probando resolución con SharkLinkResolver ---")
    resolver = SharkLinkResolver()
    start_time = asyncio.get_event_loop().time()
    try:
        final_url, store = await resolver.resolve(TEST_SHORT_URL)
        elapsed = asyncio.get_event_loop().time() - start_time

        print("\n" + "=" * 65)
        if "ofertasshark.cl" not in final_url:
            print("🎉 ¡ÉXITO! Enlace resuelto a la tienda real:")
            print(f"• Tienda detectada : {store or 'Desconocida'}")
            print(f"• URL final        : {final_url}")
            print(f"• Tiempo tomado    : {elapsed:.2f}s")
        else:
            print("⚠️ No se pudo resolver a tienda. Se mantuvo la URL original:")
            print(f"• URL devuelta     : {final_url}")
            print(f"• Tiempo tomado    : {elapsed:.2f}s")
        print("=" * 65)

    except Exception as e:
        print(f"\n❌ Error durante la resolución: {e}")

    finally:
        await resolver.close()
        print("\nNavegador cerrado.")


if __name__ == "__main__":
    asyncio.run(run_diagnostics())
