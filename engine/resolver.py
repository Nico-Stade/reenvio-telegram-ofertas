"""
engine/resolver.py — Servicio de resolución de enlaces acortados y protegidos por Cloudflare (Ofertas Shark / Nypau).
Utiliza una sesión persistente off-screen con cookies autorizadas (user_token y cf_clearance).
"""
import os
import sys
import json
import time
import asyncio
from pathlib import Path
from typing import Tuple, Optional, Dict
from urllib.parse import urlparse
from loguru import logger

STORE_DOMAIN_MAP = {
    "paris.cl": "Paris",
    "falabella.com": "Falabella",
    "ripley.cl": "Ripley",
    "sodimac.cl": "Sodimac",
    "lider.cl": "Líder",
    "mercadolibre.cl": "Mercado Libre",
    "mercadolibre.com": "Mercado Libre",
    "hites.com": "Hites",
    "easy.cl": "Easy",
    "abcdin.cl": "Abcdin",
    "pcfactory.cl": "PC Factory",
    "spdigital.cl": "SP Digital",
    "zara.com": "Zara",
    "hm.com": "H&M",
    "stretto.cl": "Stretto",
    "lenovo.com": "Lenovo",
    "samsung.com": "Samsung",
    "aliexpress.com": "AliExpress",
    "amazon.com": "Amazon",
    "linio.cl": "Linio",
    "claro.cl": "Claro",
    "entel.cl": "Entel",
    "movistar.cl": "Movistar",
    "wom.cl": "WOM",
}


def detect_store_from_url(url: str) -> Optional[str]:
    """Extrae el nombre comercial de la tienda a partir de la URL real."""
    if not url:
        return None
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if domain.startswith("simple."):
            domain = domain[7:]

        for dom, store in STORE_DOMAIN_MAP.items():
            if dom in domain:
                return store
    except Exception:
        pass
    return None


def _setup_local_libs_env():
    """Configura LD_LIBRARY_PATH si existen librerías de usuario en data/libs."""
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
            logger.debug(f"[Resolver] LD_LIBRARY_PATH configurado con {len(so_dirs)} carpetas de data/libs")


class SharkLinkResolver:
    """
    Resuelve redirecciones de ofertasshark.cl hacia las URLs reales de las tiendas.
    Mantiene un navegador Chrome off-screen con las cookies cargadas desde data/shark_cookies.json.
    """

    def __init__(self, cookies_path: str = "data/shark_cookies.json"):
        self.cookies_path = Path(cookies_path)
        self._driver = None
        self._lock = asyncio.Lock()
        self._cache: Dict[str, Tuple[str, Optional[str]]] = {}

    def _load_cookies(self):
        if not self.cookies_path.exists():
            logger.warning(f"[Resolver] Archivo de cookies no encontrado en {self.cookies_path}")
            return []
        try:
            with open(self.cookies_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[Resolver] Error cargando cookies: {e}")
            return []

    def _ensure_driver(self):
        """Inicia el navegador off-screen con cookies inyectadas si no está corriendo."""
        if self._driver is not None:
            try:
                # Comprobar que sigue respondiendo
                _ = self._driver.title
                return
            except Exception:
                logger.warning("[Resolver] El navegador no responde, reiniciando instancia...")
                self._close_driver_sync()

        # Configurar librerías locales en data/libs si existen
        _setup_local_libs_env()

        import undetected_chromedriver as uc

        logger.info("[Resolver] Inicializando navegador off-screen para resolución de ofertas...")
        options = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")

        # Si corre en Linux sin pantalla (entorno contenedor como bot-hosting), usar headless
        is_linux_headless = sys.platform.startswith("linux") and not os.environ.get("DISPLAY")
        if is_linux_headless:
            options.add_argument("--headless=new")
        else:
            # En Windows / entornos con display, usar off-screen para no interrumpir al usuario
            options.add_argument("--window-position=-2000,-2000")
            options.add_argument("--window-size=600,500")

        # Detección automática de binarios portátiles en data/, contenedor o variables de entorno
        chrome_bin = os.getenv("CHROME_BIN") or os.getenv("CHROME_PATH")
        if not chrome_bin:
            search_roots = [Path("data"), Path("."), Path("/tmp")]
            for sroot in search_roots:
                if not sroot.exists():
                    continue
                for name in ("chrome", "chromium", "chrome-headless-shell"):
                    try:
                        for p in sroot.rglob(name):
                            if p.is_file():
                                try:
                                    os.chmod(p, 0o755)
                                except Exception:
                                    pass
                                chrome_bin = str(p.resolve())
                                logger.info(f"[Resolver] Binario Chrome detectado en: {chrome_bin}")
                                break
                    except Exception as e:
                        logger.debug(f"[Resolver] Error buscando en {sroot}: {e}")
                    if chrome_bin:
                        break
                if chrome_bin:
                    break

        if not chrome_bin and sys.platform.startswith("linux"):
            data_files = [p.name for p in Path("data").glob("*")] if Path("data").exists() else "No existe carpeta data"
            root_files = [p.name for p in Path(".").glob("*")]
            logger.warning(f"[Resolver] No se detectó binario de Chrome. Archivos en data/: {data_files} | Archivos en raíz: {root_files}")

        kwargs = {"options": options}
        if chrome_bin:
            logger.info(f"[Resolver] Usando binario Chrome: {chrome_bin}")
            options.binary_location = str(chrome_bin)
            kwargs["browser_executable_path"] = str(chrome_bin)

        driver = uc.Chrome(**kwargs)

        # Cargar cookies de autorización en el dominio link.ofertasshark.cl
        cookies = self._load_cookies()
        if cookies:
            try:
                driver.get("https://link.ofertasshark.cl")
                for c in cookies:
                    driver.add_cookie(c)
                logger.success(f"[Resolver] Inyectadas {len(cookies)} cookies de sesión autorizada.")
            except Exception as e:
                logger.warning(f"[Resolver] Error al inyectar cookies: {e}")

        self._driver = driver

    def _close_driver_sync(self):
        if self._driver is not None:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None

    def _resolve_sync(self, short_url: str, timeout: int = 8) -> Tuple[str, Optional[str]]:
        """Lógica síncrona de resolución que corre en un hilo de trabajo."""
        try:
            self._ensure_driver()
            self._driver.get(short_url)

            final_url = None
            for _ in range(timeout):
                time.sleep(1)
                curr = self._driver.current_url
                if curr and "ofertasshark.cl" not in curr:
                    final_url = curr
                    break

            if final_url:
                store = detect_store_from_url(final_url)
                logger.success(f"[Resolver] Redirección exitosa: {final_url[:60]}... (Tienda: {store or 'Desconocida'})")
                return final_url, store
            else:
                logger.warning(f"[Resolver] Timeout al resolver {short_url}. URL actual: {self._driver.current_url[:60]}")
                return short_url, None

        except Exception as e:
            logger.error(f"[Resolver] Excepción resolviendo {short_url}: {e}")
            return short_url, None

    async def resolve(self, url: str) -> Tuple[str, Optional[str]]:
        """
        Resuelve una URL acortada de ofertasshark.cl a su enlace genuino de tienda.
        Retorna (url_final, nombre_tienda).
        """
        if not url:
            return url, None

        if "ofertasshark.cl" not in url:
            # Ya es una URL directa
            return url, detect_store_from_url(url)

        if url in self._cache:
            return self._cache[url]

        async with self._lock:
            # Comprobación doble tras adquirir el lock
            if url in self._cache:
                return self._cache[url]

            logger.info(f"[Resolver] Resolviendo redirección protegida: {url[:70]}...")
            result = await asyncio.to_thread(self._resolve_sync, url)
            self._cache[url] = result
            return result

    async def close(self):
        """Cierra el navegador de forma segura."""
        async with self._lock:
            await asyncio.to_thread(self._close_driver_sync)
            logger.info("[Resolver] Navegador cerrado.")
