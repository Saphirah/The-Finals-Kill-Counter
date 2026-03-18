"""App-level configuration and path utilities shared across FKC modules."""

import os
import sys
import json
import numpy as np


def _app_dir() -> str:
    """Return the directory used for config.json, profile.json and detection_logs/.

    When running as a PyInstaller bundle this is the EXE folder; otherwise
    it is the directory containing this script.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _load_app_config() -> dict:
    """Load config.json from the app directory, returning {} on failure."""
    cfg_path = os.path.join(_app_dir(), 'config.json')
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as exc:
        print(f'[config] Could not load config.json: {exc}')
        return {}


def _cfg_to_ranges(raw: list) -> list:
    """Convert list-of-[[lo],[hi]] from JSON into numpy array tuples."""
    return [
        (np.array(lo, dtype=np.uint8), np.array(hi, dtype=np.uint8))
        for lo, hi in raw
    ]


def _get_tesseract_path() -> str:
    """Locate the Tesseract executable.

    Priority:
    1. Bundled inside the PyInstaller package at <_MEIPASS>/tesseract/
    2. Common Windows installation paths
    3. Bare name (relies on PATH)
    """
    if getattr(sys, 'frozen', False):
        bundled = os.path.join(sys._MEIPASS, 'tesseract', 'tesseract.exe')
        if os.path.exists(bundled):
            os.environ['TESSDATA_PREFIX'] = os.path.join(sys._MEIPASS, 'tesseract', 'tessdata')
            return bundled
    for candidate in (
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
    ):
        if os.path.exists(candidate):
            return candidate
    return 'tesseract'  # rely on PATH
