"""
setup_container_libs.py — Descarga y extrae las librerías compartidas de Linux necesarias
para Chrome en data/libs usando apt-get download y dpkg -x (sin necesidad de permisos root).
"""
import sys
import os
import glob
import subprocess
from pathlib import Path

# Asegurar UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PACKAGES = [
    # NSS & NSPR (Seguridad y SSL requeridos por Chrome)
    "libnspr4",
    "libnss3",
    "libnss3-tools",
    # ATK & Accesibilidad
    "libatk1.0-0",
    "libatk-bridge2.0-0",
    "at-spi2-core",
    "libatspi2.0-0",
    "libatspi0",
    # Ventanas y Compositing X11
    "libxcomposite1",
    "libxdamage1",
    "libxrandr2",
    "libxfixes3",
    "libx11-xcb1",
    "libxcb-dri3-0",
    "libxshmfence1",
    "libx11-6",
    "libxext6",
    # Gráficos de bajo nivel, DRI y Teclado
    "libgbm1",
    "libdrm2",
    "libxkbcommon0",
    # Fuentes y renderizado
    "libpango-1.0-0",
    "libcairo2",
    # Audio y Cups
    "libasound2",
    "libcups2",
]


def setup_libs():
    print("=" * 65)
    print("📦 INSTALANDO LIBRERÍAS DE LINUX EN MODO USUARIO (SIN ROOT)")
    print("=" * 65)

    base_dir = Path("data/libs").resolve()
    temp_deb_dir = Path("data/deb_temp").resolve()

    base_dir.mkdir(parents=True, exist_ok=True)
    temp_deb_dir.mkdir(parents=True, exist_ok=True)

    print(f"1. Descargando paquetes .deb desde Debian (uno a uno)...")
    downloaded = 0
    for pkg in PACKAGES:
        res = subprocess.run(
            ["apt-get", "download", pkg],
            cwd=str(temp_deb_dir),
            capture_output=True,
            text=True
        )
        if res.returncode == 0:
            print(f"   ✓ {pkg}")
            downloaded += 1
        else:
            # Si no existe en esta versión de Debian, se ignora limpiamente
            pass

    print(f"-> {downloaded} paquetes descargados con éxito.")

    deb_files = list(temp_deb_dir.glob("*.deb"))
    print(f"\n2. Extrayendo {len(deb_files)} archivos .deb en {base_dir}...")
    for deb in deb_files:
        try:
            res = subprocess.run(["dpkg", "-x", str(deb), str(base_dir)], capture_output=True, text=True)
            if res.returncode == 0:
                print(f"   ✓ Extraído: {deb.name}")
            else:
                print(f"   ❌ Error extrayendo {deb.name}: {res.stderr.strip()[:80]}")
        except Exception as e:
            print(f"   ❌ Error extrayendo {deb.name}: {e}")

    # Limpiar archivos .deb temporales para ahorrar espacio en disco
    for deb in deb_files:
        try:
            deb.unlink()
        except Exception:
            pass
    try:
        temp_deb_dir.rmdir()
    except Exception:
        pass

    # Encontrar todas las carpetas con archivos .so (incluyendo enlaces simbólicos)
    so_dirs = set()
    for so_file in base_dir.rglob("*.so*"):
        if so_file.is_file() or so_file.is_symlink():
            so_dirs.add(str(so_file.parent.resolve()))

    ld_paths = ":".join(so_dirs)
    print(f"\n✓ Extracción completada. Carpetas de librerías ({len(so_dirs)}):")
    for d in sorted(so_dirs):
        print(f"   -> {d}")

    # Probar el binario de Chrome con LD_LIBRARY_PATH
    chrome_bin = None
    for p in Path("data").rglob("chrome*"):
        if p.is_file() and not p.suffix and "test" not in p.name:
            chrome_bin = str(p.resolve())
            break

    if chrome_bin:
        try:
            os.chmod(chrome_bin, 0o755)
        except Exception:
            pass

        print(f"\n3. Probando Chrome con LD_LIBRARY_PATH configurado:")
        print(f"• Binario: {chrome_bin}")
        env = dict(os.environ)
        current_ld = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = f"{ld_paths}:{current_ld}" if current_ld else ld_paths

        try:
            chk = subprocess.run([chrome_bin, "--version"], capture_output=True, text=True, env=env, timeout=5)
            output = (chk.stdout or chk.stderr).strip()
            print(f"• Retcode: {chk.returncode}")
            print(f"• Salida : {output}")

            if chk.returncode == 0:
                print("\n" + "🎉" * 25)
                print("¡CHROME AHORA FUNCIONA PERFECTAMENTE EN EL CONTENEDOR!")
                print("🎉" * 25)
            else:
                # Revisar si aún falta alguna librería con ldd
                ldd = subprocess.run(["ldd", chrome_bin], capture_output=True, text=True, env=env, timeout=5)
                still_missing = [line.strip() for line in ldd.stdout.splitlines() if "not found" in line]
                if still_missing:
                    print(f"⚠️ Aún faltan estas librerías ({len(still_missing)}):")
                    for m in still_missing:
                        print(f"   {m}")

                    print("\nIntentando resolver dependencias faltantes automáticamente...")
                    temp_deb_dir.mkdir(parents=True, exist_ok=True)
                    auto_dl = 0
                    for m in still_missing:
                        so_name = m.split("=>")[0].strip()
                        clean = so_name.split(".so")[0].lower().replace("_", "-")
                        search = subprocess.run(["apt-cache", "search", clean], capture_output=True, text=True)
                        candidates = []
                        for line in search.stdout.splitlines()[:5]:
                            p_name = line.split()[0].strip() if line else ""
                            if p_name:
                                candidates.append(p_name)
                        for cand in candidates:
                            dl = subprocess.run(["apt-get", "download", cand], cwd=str(temp_deb_dir), capture_output=True, text=True)
                            if dl.returncode == 0:
                                print(f"   ✓ Descargado automáticamente: {cand} (para {so_name})")
                                auto_dl += 1
                                break

                    if auto_dl > 0:
                        for deb in temp_deb_dir.glob("*.deb"):
                            subprocess.run(["dpkg", "-x", str(deb), str(base_dir)], capture_output=True)
                            deb.unlink(missing_ok=True)
                        for so_file in base_dir.rglob("*.so*"):
                            if so_file.is_file() or so_file.is_symlink():
                                so_dirs.add(str(so_file.parent.resolve()))
                        ld_paths = ":".join(so_dirs)
                        env["LD_LIBRARY_PATH"] = f"{ld_paths}:{current_ld}" if current_ld else ld_paths
                        chk2 = subprocess.run([chrome_bin, "--version"], capture_output=True, text=True, env=env, timeout=5)
                        if chk2.returncode == 0:
                            print("\n" + "🎉" * 25)
                            print("¡CHROME FUNCIONA TRAS AUTO-RESOLUCIÓN!")
                            print("🎉" * 25)
                        else:
                            print(f"• Retcode 2: {chk2.returncode} | {(chk2.stdout or chk2.stderr).strip()}")
        except Exception as e:
            print("Error al probar:", e)


if __name__ == "__main__":
    setup_libs()
