# -*- mode: python ; coding: utf-8 -*-
# FKC.spec  –  PyInstaller spec for Finals Kill Counter
#
# Build with:  python build.py
#          or: pyinstaller FKC.spec --noconfirm
#
# Tesseract-OCR must be installed on the build machine.
# The entire Tesseract installation directory is bundled into the EXE so
# the end user does NOT need to install Tesseract separately.

import os
import sys

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# ── Locate Tesseract on the build machine ───────────────────────────────────
_TESS_CANDIDATES = [
    r'C:\Program Files\Tesseract-OCR',
    r'C:\Program Files (x86)\Tesseract-OCR',
]
_tess_dir = None
for _c in _TESS_CANDIDATES:
    if os.path.isdir(_c):
        _tess_dir = _c
        break

if _tess_dir is None:
    print('\n[FKC.spec] WARNING: Tesseract-OCR not found at expected paths.')
    print('           OCR will fail at runtime unless Tesseract is on PATH.')
    print('           Install from https://github.com/UB-Mannheim/tesseract/wiki\n')
else:
    print(f'[FKC.spec] Bundling Tesseract from: {_tess_dir}')

# ── Collect data files ───────────────────────────────────────────────────────
datas = []

# OpenCV data (haarcascades, etc.)
datas += collect_data_files('cv2')

# Bundle the entire Tesseract directory so the EXE is self-contained.
# Layout inside the bundle:
#   tesseract/tesseract.exe
#   tesseract/tessdata/eng.traineddata  (+ other .traineddata you have)
#   tesseract/*.dll
if _tess_dir:
    for _root, _dirs, _files in os.walk(_tess_dir):
        _rel = os.path.relpath(_root, _tess_dir)
        _dest = 'tesseract' if _rel == '.' else 'tesseract/' + _rel.replace('\\', '/')
        for _f in _files:
            datas.append((os.path.join(_root, _f), _dest))

# ── Hidden imports ────────────────────────────────────────────────────────────
hiddenimports = [
    'pynput.keyboard._win32',
    'pynput.mouse._win32',
    'pystray._win32',
    'PIL._tkinter_finder',
]

# ── Analysis ─────────────────────────────────────────────────────────────────
a = Analysis(
    ['screenshot_monitor.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='FinalsKillCounter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,           # compress if UPX is installed; harmless if not
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # no console window – it's a tray app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='icon.ico',  # uncomment and supply an .ico file if you have one
)
