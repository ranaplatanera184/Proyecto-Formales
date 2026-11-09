# ============================================================================
# EMPAQUETAR LA INTERFAZ DE JACE COMO EJECUTABLE
# ----------------------------------------------------------------------------
# Uso:  python empaquetar.py            (compila para el sistema actual)
#       python empaquetar.py --onedir  (carpeta con el ejecutable, más rápido)
#
# En Windows genera "dist/jace-app.exe" y en Linux/macOS "dist/jace-app".
# Un .exe de Windows solo puede generarse en Windows.
# ============================================================================

import os
import shutil
import subprocess
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(RAIZ, "jace_app.spec")
ENTRADA = os.path.join(RAIZ, "jace_app.py")


def ejecutar_comando(comando):
    print(">", " ".join(comando), flush=True)
    resultado = subprocess.run(comando, cwd=RAIZ)
    if resultado.returncode != 0:
        sys.exit(f"Falló el empaquetado (código {resultado.returncode}).")


def limpiar():
    for carpeta in ("build", "dist"):
        ruta = os.path.join(RAIZ, carpeta)
        if os.path.isdir(ruta):
            shutil.rmtree(ruta)


def main():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        sys.exit("Falta PyInstaller. Instálalo con: pip install pyinstaller")

    if not os.path.isdir(os.path.join(RAIZ, "web")):
        sys.exit("Falta la carpeta web/ con la interfaz.")

    onedir = "--onedir" in sys.argv
    if onedir:
        # Carpeta con el ejecutable (arranque más rápido).
        if not os.path.isfile(ENTRADA):
            sys.exit(f"No se encontró el punto de entrada: {ENTRADA}")
        comando = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm",
                   "--onedir", "--name", "jace-app",
                   "--add-data", "reglas.json:.",
                   "--add-data", "web:web",
                   ENTRADA]
    else:
        if not os.path.isfile(SPEC):
            sys.exit(f"No se encontró la spec: {SPEC}")
        # Un solo archivo: la spec ya incluye las rutas de reglas.json y web/.
        comando = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", SPEC]

    limpiar()
    ejecutar_comando(comando)

    ejecutable = "jace-app.exe" if os.name == "nt" else "jace-app"
    ruta = os.path.join(RAIZ, "dist", ejecutable)
    if not os.path.isfile(ruta) and not os.path.isdir(ruta):
        sys.exit("No se encontró el ejecutable generado en dist/.")

    print("\n" + "=" * 60)
    print(f"Aplicación lista: {ruta}")
    if os.name == "nt":
        print("Cópiala a otra máquina Windows y ábrela con doble clic.")
    else:
        print("Ejecútala con: ./dist/jace-app")
    print("=" * 60)


if __name__ == "__main__":
    main()
