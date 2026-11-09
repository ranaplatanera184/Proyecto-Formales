# -*- mode: python ; coding: utf-8 -*-
# ============================================================================
# EMPAQUETADO DE JACE COMO APLICACIÓN
# Genera un único ejecutable: jace-app.exe (Windows) o jace-app (Linux/macOS).
#   python -m PyInstaller --clean jace_app.spec
# ============================================================================

import os

# Ruta de la carpeta web (interfaz) y de las reglas del lenguaje.
web = os.path.abspath('web')

a = Analysis(
    ['jace_app.py'],
    pathex=[],
    binaries=[],
    datas=[('reglas.json', '.'), (web, 'web')],
    # schemdraw importa el backend de SVG de matplotlib de forma diferida al
    # guardar el diagrama: sin esto el SVG sale vacío dentro del ejecutable.
    hiddenimports=['matplotlib.backends.backend_svg',
                   'matplotlib.backends.backend_agg'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='jace-app',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
