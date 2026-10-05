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
    "libnspr4",
    "libnss3",
    "libatk1.0-0",
    "libatk-bridge2.0-0",
    "libxcomposite1",
    "libxdamage1",
    "libatspi0",
    "libcups2",
    "libasound2",
    "libdrm2",
    "libgbm1",
    "libxkbcommon0",
    "libxrandr2",
]


def setup_libs():
    print("=" * 65)
    print("📦 INSTALANDO LIBRERÍAS DE LINUX EN MODO USUARIO (SIN ROOT)")
    print("=" * 65)

    base_dir = Path("data/libs").resolve()
    temp_deb_dir = Path("data/deb_temp").resolve()

    base_dir.mkdir(parents=True, exist_ok=True)
    temp_deb_dir.mkdir(parents=True, exist_ok=True)

    print(f"1. Descargando {len(PACKAGES)} paquetes .deb desde Debian...")
    cmd_download = ["apt-get", "download"] + PACKAGES
    try:
        res = subprocess.run(cmd_download, cwd=str(temp_deb_dir), capture_output=True, text=True)
        if res.returncode != 0:
            print("Aviso apt-get download:", res.stderr.strip()[:200])
        else:
            print("✓ Paquetes descargados con éxito.")
    except Exception as e:
        print("Error descargando:", e)
        return

    deb_files = list(temp_deb_dir.glob("*.deb"))
    print(f"\n2. Extrayendo {len(deb_files)} archivos .deb en {base_dir}...")
    for deb in deb_files:
        try:
            subprocess.run(["dpkg", "-x", str(deb), str(base_dir)], check=True, capture_output=True)
        except Exception as e:
            print(f"Error extrayendo {deb.name}: {e}")

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

    # Encontrar todas las carpetas con archivos .so
    so_dirs = set()
    for so_file in base_dir.rglob("*.so*"):
        if so_file.is_file():
            so_dirs.add(str(so_file.parent))

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
                # Revisar si aún falta alguna librería
                ldd = subprocess.run(["ldd", chrome_bin], capture_output=True, text=True, env=env, timeout=5)
                still_missing = [line.strip() for line in ldd.stdout.splitlines() if "not found" in line]
                if still_missing:
                    print(f"⚠️ Aún faltan estas librerías ({len(still_missing)}):")
                    for m in still_missing:
                        print(f"   {m}")
        except Exception as e:
            print("Error al probar:", e)


if __name__ == "__main__":
    setup_libs()
