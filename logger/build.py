#!/usr/bin/env python3
"""
build.py  –  Build FinalsKillCounter.exe as a single self-contained file.

Prerequisites (run once):
    pip install -r requirements.txt
    pip install pyinstaller

Tesseract-OCR must be installed on this machine.
Download the Windows installer from:
    https://github.com/UB-Mannheim/tesseract/wiki
    (recommended: tesseract-ocr-w64-setup-*.exe, install to default path)

Usage:
    python build.py
"""

import os
import shutil
import subprocess
import sys

TESS_CANDIDATES = [
    r'C:\Program Files\Tesseract-OCR',
    r'C:\Program Files (x86)\Tesseract-OCR',
]


def find_tesseract():
    for path in TESS_CANDIDATES:
        if os.path.isdir(path):
            exe = os.path.join(path, 'tesseract.exe')
            if os.path.isfile(exe):
                return path
    return None


def check_pyinstaller():
    result = subprocess.run(
        [sys.executable, '-m', 'PyInstaller', '--version'],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print('✗ PyInstaller not found.')
        print('  Install it with:  pip install pyinstaller')
        sys.exit(1)
    print(f'✓ PyInstaller {result.stdout.strip()}')


def main():
    print('=' * 60)
    print('Finals Kill Counter  –  Build Script')
    print('=' * 60)

    # --- Verify Tesseract ---------------------------------------------------
    tess_dir = find_tesseract()
    if tess_dir:
        print(f'✓ Tesseract found: {tess_dir}')
    else:
        print()
        print('✗ Tesseract-OCR not found.')
        print('  The EXE will be built but OCR will NOT work at runtime.')
        print()
        print('  To fix: install Tesseract from')
        print('    https://github.com/UB-Mannheim/tesseract/wiki')
        print('  then re-run this build script.')
        print()
        if input('  Continue building without Tesseract? [y/N] ').strip().lower() != 'y':
            sys.exit(0)

    # --- Verify PyInstaller -------------------------------------------------
    check_pyinstaller()

    # --- Clean previous output ----------------------------------------------
    for folder in ('build', 'dist'):
        if os.path.isdir(folder):
            shutil.rmtree(folder)
            print(f'✓ Removed old {folder}/')

    # --- Run PyInstaller ----------------------------------------------------
    print()
    print('Running PyInstaller …')
    result = subprocess.run(
        [sys.executable, '-m', 'PyInstaller', 'FKC.spec', '--noconfirm'],
    )

    if result.returncode != 0:
        print()
        print('✗ Build FAILED — check the output above for errors.')
        sys.exit(1)

    exe_path = os.path.join('dist', 'FinalsKillCounter.exe')
    size_mb = os.path.getsize(exe_path) / (1024 * 1024) if os.path.isfile(exe_path) else 0

    print()
    print('=' * 60)
    print('✓  Build successful!')
    print(f'   Output : dist\\FinalsKillCounter.exe  ({size_mb:.1f} MB)')
    print()
    print('   To use the EXE:')
    print('   1. Copy  dist\\FinalsKillCounter.exe  to any folder.')
    print('   2. Place your  reference.png  in the same folder.')
    print('   3. Double-click the EXE.  A tray icon will appear.')
    print('      Right-click it for  "Toggle Overlay"  and  "Quit".')
    print('      Home key also toggles the overlay.')
    print('=' * 60)


if __name__ == '__main__':
    main()
