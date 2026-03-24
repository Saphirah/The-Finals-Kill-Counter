"""
Screenshot Monitor with OCR Detection
Watches the in-game countdown timer every second, then scans for the
end-screen headline (WINNERS / ELIMINATED) and performs OCR to extract
post-match stats when it is detected.
"""

import time
import cv2
import numpy as np
import pytesseract
import json
import re
import difflib
import threading
from collections import Counter
import tkinter as tk
import ctypes
import signal
import sys
import subprocess
import urllib.request
import urllib.error
from PIL import ImageGrab, Image, ImageTk, ImageDraw
from datetime import datetime
import os
from pynput import keyboard as pynput_keyboard
import pystray
from tkinter import messagebox

from config_utils import _app_dir, _load_app_config, _cfg_to_ranges, _get_tesseract_path
from image_utils import apply_color_mask, sanitize_ocr_lines


_cfg = _load_app_config()

# ── Auto-update settings ────────────────────────────────────────────────────
_GITHUB_REPO = "Saphirah/The-Finals-Kill-Counter"

# SpacetimeDB upload settings
SPACETIMEDB_HOST = 'https://maincloud.spacetimedb.com'
SPACETIMEDB_DB = 'finalskillcounter'

# Known map names in The Finals
KNOWN_MAPS = [
    "Kyoto", "Bernal", "Las Vegas Stadium", "Monaco",
    "Nozomi", "Citadel", "Seoul", "Skyway Stadium", "Sys$Horizon", "Practice Range"
]

# Screen region bounds – loaded from config.json under 'regions'
regions_cfg = _cfg.get('regions', {})
COUNTDOWN_REGION_REL = regions_cfg.get('countdown_region_rel', {
    'x1': 1240 / 2559, 'y1': 70 / 1439, 'x2': 1320 / 2559, 'y2': 110 / 1439,
})
MAP_REGION_REL = regions_cfg.get('map_region_rel', {
    'x1': 2184 / 2559, 'y1': 35 / 1439, 'x2': 2559 / 2559, 'y2': 110 / 1439,
})

# Positional stat key order matching OCR output lines (top-to-bottom)
STAT_KEYS = [
    "combat_score",
    "objective_score",
    "support_score",
    "eliminations",
    "assists",
    "deaths",
    "revives",
    "objectives",
]

# ── HSV color range constants – loaded from config.json ─────────────────────
# Each entry is a (lower, upper) pair of np.arrays in OpenCV HSV space:
#   H: 0-179  S: 0-255  V: 0-255
_DEFAULT_ENDSCREEN = [[[0,0,180],[179,50,255]],[[15,100,100],[35,255,255]]]
_DEFAULT_MAP       = [[[0,0,210],[179,15,255]]]
_DEFAULT_COUNTDOWN = [[[0,0,240],[255,255,255]]]

color_cfg = _cfg.get('color_ranges', {})
COLOR_RANGES_ENDSCREEN = _cfg_to_ranges(color_cfg.get('color_ranges_endscreen', _DEFAULT_ENDSCREEN))
COLOR_RANGES_MAP       = _cfg_to_ranges(color_cfg.get('color_ranges_map',       _DEFAULT_MAP))
COLOR_RANGES_COUNTDOWN = _cfg_to_ranges(color_cfg.get('color_ranges_countdown', _DEFAULT_COUNTDOWN))

# Players scoreboard region – loaded from config.json under 'regions'
PLAYERS_TAB_REGION_REL = regions_cfg.get('players_tab_region', {
    'x1': 0.2, 'y1': 0.19, 'x2': 0.45, 'y2': 0.7,
})

# Region to check for "Winners" / "Eliminated" headline on end screen
ELIMINATED_WON_REGION_REL = regions_cfg.get('eliminated_won_region', {
    'x1': 0.74, 'y1': 0.0, 'x2': 0.86, 'y2': 0.1,
})

# End-screen headline keywords – loaded from config.json (supports multiple languages)
_kw_cfg = _cfg.get('end_screen_keywords', {})
END_SCREEN_WIN_KEYWORDS  = [k.upper() for k in _kw_cfg.get('win',  ['WINNERS'])]
END_SCREEN_LOSS_KEYWORDS = [k.upper() for k in _kw_cfg.get('loss', ['ELIMINATED'])]


def _keyword_match(text_upper: str, keywords: list[str]) -> bool:
    """Return True if any keyword is found in *text_upper* via substring or fuzzy match.

    - Substring: 'WINNERS' matches 'WINNERSQUAD' because WINNERS ⊆ WINNERSQUAD.
    - Fuzzy: OCR typos like 'W1NNERS' are caught when similarity >= 0.80.
    """
    for kw in keywords:
        if kw in text_upper:  # substring covers exact + embedded (e.g. WINNERSQUAD)
            return True
        for word in text_upper.split():
            if difflib.SequenceMatcher(None, kw, word).ratio() >= 0.80:
                return True
    return False


# ── Auto-update helpers ─────────────────────────────────────────────────────

def _version_tuple(ver: str) -> tuple:
    """Convert a version string like '1.2.3' to a comparable tuple (1, 2, 3)."""
    try:
        return tuple(int(x) for x in ver.lstrip('v').split('.'))
    except ValueError:
        return (0,)


def _load_update_state() -> dict:
    path = os.path.join(_app_dir(), 'fkc_update_state.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_update_state(state: dict) -> None:
    path = os.path.join(_app_dir(), 'fkc_update_state.json')
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f'[updater] Could not save update state: {e}')


def check_for_update() -> None:
    """Query GitHub for the latest release and prompt once per new version.

    * If fkc_update_state.json has no 'version' key (fresh install / first run)
      we assume this IS the latest version, persist that tag, and skip the prompt.
    * If a newer tag is found a yes/no dialog is shown once per tag.
    * If the user says **Yes**, ``updater.exe`` is launched then the app exits
      so the updater can replace the EXE and write the new version back.
    """
    try:
        api_url = f'https://api.github.com/repos/{_GITHUB_REPO}/releases'
        req = urllib.request.Request(
            api_url,
            headers={'User-Agent': 'FKC-AutoUpdater/1.0'},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            releases = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f'[updater] Could not reach GitHub: {e}')
        return

    # Pick the most recent non-draft release (pre-releases are included).
    data = next(
        (r for r in releases if not r.get('draft', False)),
        None,
    )
    if not data:
        print('[updater] No releases found on GitHub')
        return

    latest_tag = data.get('tag_name', '').strip().lstrip('v')
    if not latest_tag:
        return

    state = _load_update_state()

    # No version stored → fresh install or first run.
    # Treat as up-to-date and record the latest tag so future runs can
    # detect real updates.
    if 'version' not in state:
        state['version'] = latest_tag
        _save_update_state(state)
        print(f'[updater] First run – recording current version as v{latest_tag}')
        return

    current_version = state['version']
    if _version_tuple(latest_tag) <= _version_tuple(current_version):
        print(f'[updater] Up to date (v{current_version})')
        return

    # New version found – respect a previous "No" for this exact tag.
    if state.get('declined') == latest_tag:
        print(f'[updater] Update v{latest_tag} was previously declined – skipping')
        return

    # Locate the zip asset.
    zip_url: str | None = None
    for asset in data.get('assets', []):
        if asset.get('name', '').lower().endswith('.zip'):
            zip_url = asset.get('browser_download_url')
            break

    if not zip_url:
        print(f'[updater] No zip asset found for release v{latest_tag}')
        return

    answer = messagebox.askyesno(
        'Update Available',
        f'A new version of Finals Kill Counter is available!\n\n'
        f'   Current : {current_version}\n'
        f'   Latest  : {latest_tag}\n\n'
        f'Download and install the update now?',
    )

    if not answer:
        state['declined'] = latest_tag
        _save_update_state(state)
        print(f'[updater] User declined update to v{latest_tag}')
        return

    # Locate updater.exe (must sit next to FinalsKillCounter.exe).
    if getattr(sys, 'frozen', False):
        app_folder = os.path.dirname(sys.executable)
        target_exe = sys.executable
    else:
        app_folder = os.path.dirname(os.path.abspath(__file__))
        target_exe = os.path.join(app_folder, 'dist', 'FinalsKillCounter.exe')

    updater_exe = os.path.join(app_folder, 'updater.exe')

    if not os.path.isfile(updater_exe):
        messagebox.showerror(
            'Updater Not Found',
            'updater.exe was not found next to FinalsKillCounter.exe.\n'
            f'Please update manually:\n{zip_url}',
        )
        return

    # Launch the updater, then exit so it can replace our EXE.
    subprocess.Popen([
        updater_exe,
        '--url',     zip_url,
        '--target',  target_exe,
        '--pid',     str(os.getpid()),
        '--version', latest_tag,
    ])
    sys.exit(0)


# ── Profile persistence ─────────────────────────────────────────────────────
PROFILE_FILE = os.path.join(_app_dir(), 'profile.json')


def get_or_create_profile():
    """Return the saved profile name, prompting with a GUI dialog on first run."""
    if os.path.exists(PROFILE_FILE):
        try:
            with open(PROFILE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            name = data.get('profile_name', '').strip()
            if name:
                print(f'\u2713 Profile loaded: {name}')
                return name
        except Exception:
            pass

    # First run or corrupted profile – show a dialog.
    result = ['']
    dialog_root = tk.Tk()
    dialog_root.withdraw()
    dialog_root.title('Finals Kill Counter')

    win = tk.Toplevel(dialog_root)
    win.title('Finals Kill Counter \u2013 Setup')
    win.geometry('360x130')
    win.resizable(False, False)
    win.configure(bg='#1e1e1e')
    win.attributes('-topmost', True)
    win.grab_set()

    tk.Label(win, text='First run \u2014 enter your profile name:',
             bg='#1e1e1e', fg='#eeeeee', pady=10).pack()
    name_var = tk.StringVar()
    entry = tk.Entry(win, textvariable=name_var, width=28,
                     bg='#333333', fg='#ffffff', insertbackground='white')
    entry.pack(pady=4)
    entry.focus_set()

    def _ok(event=None):
        n = name_var.get().strip()
        if n:
            result[0] = n
            win.destroy()
            dialog_root.destroy()

    def _cancel():
        dialog_root.destroy()
        sys.exit(0)

    tk.Button(win, text='OK', command=_ok, width=10,
              bg='#4fc3f7', fg='#000000').pack(pady=6)
    win.bind('<Return>', _ok)
    win.protocol('WM_DELETE_WINDOW', _cancel)

    dialog_root.mainloop()

    name = result[0]
    if not name:
        sys.exit(0)

    with open(PROFILE_FILE, 'w', encoding='utf-8') as f:
        json.dump({'profile_name': name}, f, indent=2)
    print(f'\u2713 Profile saved: {name}')
    return name


class OverlayWindow:
    """Small always-on-top transparent HUD overlay (non-clickable, click-through)."""

    _BG   = '#111111'
    _FONT = ('Consolas', 9, 'bold')

    def __init__(self):
        self.root = tk.Tk()
        self.root.title('FKC_Overlay')
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.82)
        self.root.geometry('+10+10')
        self.root.configure(bg=self._BG)

        def lbl(text, fg):
            l = tk.Label(self.root, text=text, fg=fg, bg=self._BG,
                         font=self._FONT, anchor='w', padx=7, pady=2)
            l.pack(fill='x')
            return l

        lbl('● Finals Kill Counter', '#4fc3f7')
        self.lbl_profile = lbl('Player: —',          '#ce93d8')
        self.lbl_map   = lbl('Map: —',             '#80deea')
        self.lbl_phase = lbl('Phase: 1 – Watching', '#a5d6a7')
        self.lbl_game  = lbl('Game: Waiting…',      '#eeeeee')
        self.lbl_last  = lbl('Last: —',             '#ffcc80')
        self.lbl_sleep = lbl('',                    '#ef9a9a')

        # Timer region preview
        lbl('Timer region:', '#555555')
        self.lbl_img_timer = tk.Label(self.root, bg=self._BG, bd=0)
        self.lbl_img_timer.pack(fill='x', padx=7, pady=1)

        # Map region preview
        lbl('Map region:', '#555555')
        self.lbl_img_map = tk.Label(self.root, bg=self._BG, bd=0)
        self.lbl_img_map.pack(fill='x', padx=7, pady=1)

        # Players region preview
        lbl('Players region:', '#555555')
        self.lbl_img_players = tk.Label(self.root, bg=self._BG, bd=0)
        self.lbl_img_players.pack(fill='x', padx=7, pady=1)

        # Players list (most likely per-slot)
        self.lbl_players_list = tk.Label(self.root, text='', fg='#eeeeee', bg=self._BG,
                         font=self._FONT, anchor='w', justify='left', padx=7, pady=2)
        self.lbl_players_list.pack(fill='x')

        # PhotoImage refs – must be kept alive to avoid GC blanking the labels
        self._photo_timer = None
        self._photo_map   = None
        self._photo_players = None

        # Track visibility for toggle
        self._visible = True

        # Shared state dict – monitor thread writes, Tk thread reads
        self.state = {
            'profile':        None,
            'map':            None,
            'phase':          1,
            'phase_label':    'Watching',
            'game_running':   False,
            'timer':          '',
            'last_detection': None,
            'sleeping':       False,
            'sleep_until':    '',
            'timer_image_bgr': None,
            'timer_image_bgr_processed': None,
            'map_image_bgr':   None,
            'map_image_bgr_processed': None,
            'players_image_bgr': None,
            'players_image_bgr_processed': None,
            'players_most_likely': None,
            'players_last_raw': None,
        }

        self.root.update_idletasks()
        # Delay click-through setup until the window is fully mapped by DWM
        self.root.after(200, self._make_clickthrough)
        self.root.after(500, self._refresh)
        # Make overlay draggable by holding mouse anywhere
        self.root.bind_all('<ButtonPress-1>', lambda e: self._on_drag_start(e))
        self.root.bind_all('<B1-Motion>', lambda e: self._on_drag_motion(e))

    def _make_clickthrough(self):
        """Add WS_EX_TRANSPARENT so mouse clicks pass through the overlay.

        winfo_id() returns the inner frame HWND on Windows; GetParent gives
        the real top-level window handle.  SWP_FRAMECHANGED forces DWM to
        re-compose the window so labels don't vanish as a black box.
        """
        try:
            inner_hwnd = self.root.winfo_id()
            hwnd = ctypes.windll.user32.GetParent(inner_hwnd) or inner_hwnd
            # Keep window clickable so we can drag it; don't set
            # WS_EX_TRANSPARENT here. Still force DWM to recompose.
            SWP_FLAGS = 0x0001 | 0x0002 | 0x0004 | 0x0020  # NOSIZE|NOMOVE|NOZORDER|FRAMECHANGED
            ctypes.windll.user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP_FLAGS)
        except Exception as e:
            print(f'[Overlay] Could not set click-through: {e}')

    def _on_drag_start(self, event):
        try:
            self._drag_offset_x = event.x
            self._drag_offset_y = event.y
        except Exception:
            self._drag_offset_x = 0
            self._drag_offset_y = 0

    def _on_drag_motion(self, event):
        try:
            new_x = event.x_root - getattr(self, '_drag_offset_x', 0)
            new_y = event.y_root - getattr(self, '_drag_offset_y', 0)
            self.root.geometry(f'+{new_x}+{new_y}')
        except Exception:
            pass

    def toggle(self):
        """Show or hide the overlay window (called from the Home key listener)."""
        if self._visible:
            self.root.withdraw()
            self._visible = False
        else:
            self.root.deiconify()
            self.root.attributes('-topmost', True)
            self._visible = True

    def _refresh(self):
        s = self.state
        self.lbl_profile.config(text=f"Player: {s['profile'] or '—'}")
        self.lbl_map.config(text=f"Map: {s['map'] or 'Unknown'}")

        if s['sleeping']:
            self.lbl_phase.config(text=f"Phase: \U0001f4a4 Sleeping \u2192 {s['sleep_until']}",
                                  fg='#ef9a9a')
            self.lbl_game.config(text='Game: \u2014')
            self.lbl_sleep.config(text='\U0001f4a4 Sleeping\u2026')
        else:
            phase_fg = '#a5d6a7' if s['phase'] == 1 else '#fff176'
            self.lbl_phase.config(
                text=f"Phase: {s['phase']} \u2013 {s['phase_label']}",
                fg=phase_fg)
            if s['game_running']:
                t = f" ({s['timer']})" if s['timer'] else ''
                self.lbl_game.config(text=f'Game: \u2713 Running{t}')
            else:
                self.lbl_game.config(text='Game: \u2717 Not running')
            self.lbl_sleep.config(text='')

        last  = s['last_detection'] or '\u2014'
        lines = [l for l in last.splitlines() if l.strip()]
        preview = '  '.join(lines[:2])
        if len(preview) > 52:
            preview = preview[:49] + '\u2026'
        self.lbl_last.config(text=f'Last: {preview}')

        # Show processed (black & white) previews
        self._update_photo(self.lbl_img_timer, s.get('timer_image_bgr_processed'), '_photo_timer', max_w=180)
        self._update_photo(self.lbl_img_map,   s.get('map_image_bgr_processed'),   '_photo_map',   max_w=180)
        self._update_photo(self.lbl_img_players, s.get('players_image_bgr_processed'), '_photo_players', max_w=180)
        
        # Players most-likely display
        players_most = s.get('players_most_likely')
        if players_most and isinstance(players_most, list):
            friendly = ' | '.join([p if p else '' for p in players_most[:5]])
            enemy = ' | '.join([p if p else '' for p in players_most[5:10]])
            txt = f'Friendly: {friendly}\nEnemy:    {enemy}'
        else:
            # Fallback: show raw last-detected lines
            txt = s.get('players_last_raw') or ''
        self.lbl_players_list.config(text=txt)

        self.root.after(500, self._refresh)

    def _update_photo(self, label, bgr, attr_name, max_w=180):
        """Convert a BGR numpy array to a PhotoImage and show it in label."""
        if bgr is None:
            return
        h, w = bgr.shape[:2]
        scale = max_w / w
        resized = cv2.resize(bgr, (int(w * scale), int(h * scale)))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        photo = ImageTk.PhotoImage(Image.fromarray(rgb))
        setattr(self, attr_name, photo)  # keep reference to prevent GC
        label.config(image=photo)

    def run(self):
        self.root.mainloop()


class ScreenshotMonitor:
    def __init__(self, profile_name=''):
        """
        Initialize the Screenshot Monitor
        
        Args:
            profile_name: Player profile name stored in detections
        """
        self.profile_name = profile_name
        self.crop_bounds = None  # Relative bounds (x1%, y1%, x2%, y2%)
        self.current_map = None
        self.overlay_state = None  # Assigned by main() after OverlayWindow is created
        # Per-match player name samples: 10 slots (0-4 friendly, 5-9 enemy).
        # Accumulated across all tab presses during a match; reset on new game.
        self._player_samples: list[list[str]] = [[] for _ in range(10)]
        # Tracking fields to avoid redundant live-state uploads.
        self._last_live_players: list[str] = [""] * 10
        self._last_live_map: str | None = None
        self.load_mask()
        self.start_tab_listener()

        # Tesseract path is resolved in main() via _get_tesseract_path().
    

    def load_mask(self):
        """Load crop bounds from config.json (key: crop_bounds_rel).

        Falls back to the original hard-coded values if the key is absent.
        """
        default = {
            'x1': 1059 / 2559,
            'y1': 868  / 1439,
            'x2': 1483 / 2559,
            'y2': 1260 / 1439,
        }
        self.crop_bounds = _cfg.get('crop_bounds_rel', default)
        print(f"✓ Crop bounds loaded from config: "
              f"({self.crop_bounds['x1']:.6f}, {self.crop_bounds['y1']:.6f}) to "
              f"({self.crop_bounds['x2']:.6f}, {self.crop_bounds['y2']:.6f})")
    
    def capture_region(self, rel_bounds):
        """Capture a specific relative region from the screen."""
        screen = ImageGrab.grab()
        sw, sh = screen.size
        x1 = int(rel_bounds['x1'] * sw)
        y1 = int(rel_bounds['y1'] * sh)
        x2 = int(rel_bounds['x2'] * sw)
        y2 = int(rel_bounds['y2'] * sh)
        region = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        return cv2.cvtColor(np.array(region), cv2.COLOR_RGB2BGR)

    def is_game_running(self):
        """Check if the in-game countdown timer is visible.

        Grabs only the countdown region, isolates white text (inverted),
        runs OCR, and returns True if a MM:SS pattern is found.
        """
        img = self.capture_region(COUNTDOWN_REGION_REL)
        # push raw capture for optional debugging
        if self.overlay_state is not None:
            self.overlay_state['timer_image_bgr'] = img

        # Isolate white text; invert so text is dark-on-light for Tesseract
        processed = apply_color_mask(img, COLOR_RANGES_COUNTDOWN, invert=True)
        if self.overlay_state is not None:
            self.overlay_state['timer_image_bgr_processed'] = processed
        rgb = cv2.cvtColor(processed, cv2.COLOR_BGR2RGB)

        text = pytesseract.image_to_string(rgb, config='--psm 7 -c tessedit_char_whitelist=0123456789:').strip()
        # Primary: MM:SS format
        match = re.search(r'\d{1,2}:\d{2}', text)
        if match:
            return True, match.group()
        # Fallback: colon stripped by OCR → pure 2-5 digit number (e.g. "545" for "5:45")
        if re.fullmatch(r'\d{2,5}', text):
            return True, text
        return False, text

    def detect_map(self, image):
        """Detect map name from image using OCR + fuzzy matching against known maps."""
        preprocessed = apply_color_mask(image, COLOR_RANGES_MAP, invert=True)
        rgb_image = cv2.cvtColor(preprocessed, cv2.COLOR_BGR2RGB)
        text = pytesseract.image_to_string(rgb_image, config='--psm 7').strip()

        if not text:
            print("[TAB] No text detected in map region")
            return None

        print(f"[TAB] Raw OCR: '{text}'")

        # Require at least 3 characters to avoid single-letter / noise matches
        if len(text.strip()) < 3:
            print(f"[TAB] OCR result too short ('{text}') — ignoring")
            return None

        text_lower = text.lower()

        # Exact / substring match — only allow text_lower as substring if it's
        # at least 4 chars long (prevents 'oo' matching 'Kyoto' etc.)
        for m in KNOWN_MAPS:
            m_lower = m.lower()
            if m_lower in text_lower:
                return m
            if len(text_lower) >= 4 and text_lower in m_lower:
                return m

        # Fuzzy match — raised cutoff to 0.6 to avoid weak partial matches
        matches = difflib.get_close_matches(text, KNOWN_MAPS, n=1, cutoff=0.6)
        if matches:
            return matches[0]

        lower_maps = [m.lower() for m in KNOWN_MAPS]
        matches_lower = difflib.get_close_matches(text_lower, lower_maps, n=1, cutoff=0.6)
        if matches_lower:
            return KNOWN_MAPS[lower_maps.index(matches_lower[0])]

        print(f"[TAB] Could not match '{text}' to any known map — ignoring")
        return None

    # Matches a trailing "number" that may contain OCR '1' misreads (l, I, |).
    # Always anchored to the end of a line because the stat value is the last token.
    _STAT_END_RE  = re.compile(r'[\d,lI|]+\s*$')
    # Characters Tesseract commonly returns instead of the digit '1'.
    _OCR_ONE_RE   = re.compile(r'[lI|]')

    def parse_stats(self, text):
        """Parse OCR text lines positionally into a stats dict.

        Line order is reliable even when Tesseract mis-reads individual words.
        The numeric value is **always the last token** on each line, so we
        anchor the search to the end of the line.  Tesseract frequently
        returns 'l', 'I', or '|' instead of '1'; those are normalised before
        the integer is extracted.
        """
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        stats = {}
        for i, key in enumerate(STAT_KEYS):
            if i < len(lines):
                m = self._STAT_END_RE.search(lines[i])
                if m:
                    # Normalise OCR '1' misreads, then keep only digits and commas.
                    normalised = self._OCR_ONE_RE.sub('1', m.group().strip())
                    digits = re.sub(r'[^0-9]', '', normalised)
                    stats[key] = int(digits) if digits else None
                else:
                    stats[key] = None
            else:
                stats[key] = None
        return stats

    def start_tab_listener(self):
        """Start listeners to run continuous player detection while Tab is held.

        Pressing Tab starts an immediate map detection and then repeatedly
        samples the players region every 0.5s until Tab is released.
        """
        self._tab_pressed = False
        self._tab_thread = None

        def worker():
            # Short delay to let scoreboard render, then detect map once.
            time.sleep(0.1)
            try:
                img = self.capture_region(MAP_REGION_REL)
                processed_map = apply_color_mask(img, COLOR_RANGES_MAP, invert=True)
                if self.overlay_state is not None:
                    self.overlay_state['map_image_bgr'] = img
                    self.overlay_state['map_image_bgr_processed'] = processed_map
                detected = self.detect_map(img)
                if detected:
                    self.current_map = detected
                    print(f"\n[TAB] Map set to: {self.current_map}")
                    if self.overlay_state is not None:
                        self.overlay_state['map'] = self.current_map
                    # Push updated map to live state (players may not be ready yet, that's fine)
                    self.upload_live_state()
            except Exception as e:
                print(f"\n[TAB] Map detection error: {e}")

            # Continuous players sampling loop
            while self._tab_pressed:
                try:
                    player_img = self.capture_region(PLAYERS_TAB_REGION_REL)
                    if self.overlay_state is not None:
                        self.overlay_state['players_image_bgr'] = player_img
                        self.overlay_state['players_image_bgr_processed'] = player_img
                    detected_names = self.detect_players(player_img)
                    for i, name in enumerate(detected_names):
                        if i < 10 and name:
                            self._player_samples[i].append(name)
                    most = self.get_most_detected_players()
                    if self.overlay_state is not None:
                        self.overlay_state['players_most_likely'] = most
                        self.overlay_state['players_last_raw'] = '\n'.join(detected_names)
                    print(f"[TAB] Players ({len(detected_names)} names): {detected_names}")
                    # Upload live state if players or map changed since last upload.
                    if most != self._last_live_players or self.current_map != self._last_live_map:
                        self.upload_live_state()
                except Exception as e:
                    print(f"[TAB] Player detection error: {e}")
                time.sleep(0.5)

        def on_press(key):
            if key == pynput_keyboard.Key.tab and not self._tab_pressed:
                self._tab_pressed = True
                self._tab_thread = threading.Thread(target=worker, daemon=True)
                self._tab_thread.start()

        def on_release(key):
            if key == pynput_keyboard.Key.tab and self._tab_pressed:
                self._tab_pressed = False
                print("[TAB] Released – stopping continuous detection")

        listener = pynput_keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.daemon = True
        listener.start()
        print("✓ Tab held listener active (hold Tab in-game to scan players)")

    def detect_players(self, image):
        """OCR the players tab region and return detected names (one per line, up to 10).

        Applies the full preprocessing pipeline from region_tester:
        1. Color mask with COLOR_RANGES_COUNTDOWN (inverted for white text)
        2. Contrast adjustment around brightness pivot (default: contrast=1.0, pivot=128)
        3. Invert output (for Tesseract preference)
        4. Run OCR with PSM 3 (fully automatic, block of text)
        5. Sanitize to extract player names
        
        Players are listed top-to-bottom: slots 0-4 = friendly team, 5-9 = enemy.
        """
        grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        proc = cv2.cvtColor(grey, cv2.COLOR_GRAY2BGR)
        rgb = cv2.cvtColor(proc, cv2.COLOR_BGR2RGB)
        text = pytesseract.image_to_string(rgb, config='--psm 3').strip()
        lines = sanitize_ocr_lines(text)
        return lines[:10]

    def get_most_detected_players(self):
        """Return the most-detected name per player slot across all tab samples.

        Returns a list of 10 entries (slots 0-9); each is a str or None.
        Slots 0-4 = friendly team (top), 5-9 = enemy team (bottom).
        """
        result = []
        for samples in self._player_samples:
            if not samples:
                result.append(None)
            else:
                most_common = Counter(samples).most_common(1)[0][0]
                result.append(most_common if most_common else None)
        return result

    def crop_to_mask_bounds(self, image):
        """Crop image based on mask bounds using relative dimensions"""
        if self.crop_bounds is None:
            return image
        
        height, width = image.shape[:2]
        
        # Calculate absolute coordinates from relative percentages
        x1 = int(self.crop_bounds['x1'] * width)
        y1 = int(self.crop_bounds['y1'] * height)
        x2 = int(self.crop_bounds['x2'] * width)
        y2 = int(self.crop_bounds['y2'] * height)
        
        # Ensure bounds are within image
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(width, x2)
        y2 = min(height, y2)
        
        # Crop image
        cropped = image[y1:y2, x1:x2]
        return cropped
    
    def take_screenshot(self):
        """Capture current screen"""
        screenshot = ImageGrab.grab()
        # Convert PIL Image to OpenCV format
        screenshot_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        return screenshot_cv
    

    def extract_text(self, image):
        """
        Extract text from image using Tesseract OCR
        
        Returns:
            Tuple of (extracted text, cropped image, preprocessed image)
        """
        # Crop to mask bounds
        cropped_image = self.crop_to_mask_bounds(image)
        
        # Preprocess to isolate white and yellow text
        preprocessed_image = apply_color_mask(cropped_image, COLOR_RANGES_ENDSCREEN, invert=True)
        
        # Convert BGR to RGB for pytesseract
        rgb_image = cv2.cvtColor(preprocessed_image, cv2.COLOR_BGR2RGB)
        
        # Perform OCR with better config for numbers
        # --psm 6 assumes uniform block of text
        # digits for character whitelist
        config = '--psm 6'
        text = pytesseract.image_to_string(rgb_image, config=config)
        return text.strip(), cropped_image, preprocessed_image
    
    def save_log(self, stats, similarity_score, cropped_image, preprocessed_image, won=None):
        """Save detection as a JSON log plus cropped/processed images."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_dir = os.path.join(_app_dir(), "detection_logs")
        os.makedirs(log_dir, exist_ok=True)

        # Compute most-detected name per slot from all tab samples this match.
        player_names = self.get_most_detected_players()
        friendly_players = [{"name": player_names[i]} for i in range(5)]
        enemy_players = [{"name": player_names[i + 5]} for i in range(5)]

        data = {
            "detection_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "profile": self.profile_name or None,
            "similarity_score": round(similarity_score, 4) if similarity_score is not None else None,
            "map": self.current_map,
            "won": bool(won) if won is not None else None,
            "stats": stats,
            "players": {
                "friendly": friendly_players,
                "enemy": enemy_players,
            },
        }

        log_file = os.path.join(log_dir, f"detection_{timestamp}.json")
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

        image_file = os.path.join(log_dir, f"detection_{timestamp}_original.png")
        cv2.imwrite(image_file, cropped_image)

        preprocessed_file = os.path.join(log_dir, f"detection_{timestamp}_processed.png")
        cv2.imwrite(preprocessed_file, preprocessed_image)

        print(f"✓ Log saved: {log_file}")
        print(f"✓ Original image: {image_file}")
        print(f"✓ Processed image: {preprocessed_file}")

        self.upload_to_spacetimedb(stats, data["detection_time"], similarity_score,
                       won=won,
                       friendly_players=friendly_players,
                       enemy_players=enemy_players)
        # Clear live state — match has been recorded in history.
        self.clear_live_state_remote()

    def upload_to_spacetimedb(self, stats, detection_time, similarity_score, won=True, friendly_players=None, enemy_players=None):
        """Upload match stats to SpacetimeDB via HTTP API."""
        url = f"{SPACETIMEDB_HOST}/v1/database/{SPACETIMEDB_DB}/call/submit_match"

        def int_or_neg1(v):
            return v if isinstance(v, int) else -1

        payload = {
            "playerName": self.profile_name or "Unknown",
            "detectionTime": detection_time,
            "map": self.current_map or "",
            "similarityScore": float(round(similarity_score, 6)),
            "combatScore": int_or_neg1(stats.get("combat_score")),
            "objectiveScore": int_or_neg1(stats.get("objective_score")),
            "supportScore": int_or_neg1(stats.get("support_score")),
            "eliminations": int_or_neg1(stats.get("eliminations")),
            "assists": int_or_neg1(stats.get("assists")),
            "deaths": int_or_neg1(stats.get("deaths")),
            "revives": int_or_neg1(stats.get("revives")),
            "objectives": int_or_neg1(stats.get("objectives")),
            "win": bool(won),
            "friendlyPlayers": json.dumps(friendly_players or []),
            "enemyPlayers": json.dumps(enemy_players or []),
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                print(f"✓ Uploaded to SpacetimeDB (HTTP {resp.status})")
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            print(f"✗ SpacetimeDB upload error {e.code}: {body}")
        except Exception as e:
            print(f"✗ SpacetimeDB upload failed: {e}")

    def _post_to_spacetimedb(self, reducer: str, payload: dict, label: str):
        """Fire-and-forget POST to a SpacetimeDB reducer in a daemon thread."""
        import threading
        def _send():
            url = f"{SPACETIMEDB_HOST}/v1/database/{SPACETIMEDB_DB}/call/{reducer}"
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("Accept", "application/json")
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    print(f"✓ {label} (HTTP {resp.status})")
            except urllib.error.HTTPError as e:
                body = e.read().decode(errors="replace")
                print(f"✗ {label} error {e.code}: {body}")
            except Exception as e:
                print(f"✗ {label} failed: {e}")
        threading.Thread(target=_send, daemon=True).start()

    def upload_live_state(self):
        """Send current map + most-likely players to SpacetimeDB live_state table."""
        player_names = self.get_most_detected_players()
        friendly = [{"name": player_names[i]} for i in range(5)]
        enemy    = [{"name": player_names[i + 5]} for i in range(5)]
        payload = {
            "playerName": self.profile_name or "Unknown",
            "map": self.current_map or "",
            "friendlyPlayers": json.dumps(friendly),
            "enemyPlayers": json.dumps(enemy),
        }
        self._last_live_players = list(player_names)
        self._last_live_map = self.current_map
        self._post_to_spacetimedb("update_live_state", payload, "Live state updated")

    def clear_live_state_remote(self):
        """Remove live_state row from SpacetimeDB (called when match ends)."""
        self._last_live_players = [""] * 10
        self._last_live_map = None
        self._post_to_spacetimedb("clear_live_state", {}, "Live state cleared")

    def run(self):
        """Main monitoring loop.

        Phase 1 – lightweight countdown check every second.
          • Countdown visible  → game in progress.
          • 3 consecutive misses → enter Phase 2.
          • waiting_for_game=True → just wait until countdown reappears
            (used after sleep or Phase-2 timeout—don’t start Phase 2 again
            until we actually see a game begin and end).

        Phase 2 – full-frame end-screen hunt.
          • Match found → OCR, save JSON, sleep 5 min, then set
            waiting_for_game=True so we wait for the next game.
          • No match for 2 minutes → give up, set waiting_for_game=True.
        """
        MISS_THRESHOLD  = 8    # Phase-1 misses before Phase 2
        PHASE2_TIMEOUT  = 120  # seconds before Phase 2 gives up

        print("\n" + "=" * 60)
        print("Screenshot Monitor Started")
        print("=" * 60)
        print("Watching countdown timer every second...")
        print("Press Ctrl+C to stop\n")

        def ov(**kw):
            if self.overlay_state is not None:
                self.overlay_state.update(kw)

        misses           = 0
        waiting_for_game = True  # True → wait for countdown, don’t count misses

        try:
            while True:
                ts = datetime.now().strftime("%H:%M:%S")
                running, raw = self.is_game_running()

                # ── waiting for a new game to start ─────────────────────────
                if waiting_for_game:
                    if running:
                        waiting_for_game = False
                        misses = 0
                        self._player_samples = [[] for _ in range(10)]  # Reset for new game
                        self._last_live_players = [""] * 10
                        self._last_live_map = None
                        print(f"[{ts}] ⏵ Countdown found – resuming Phase 1 monitoring")
                        ov(phase=1, phase_label='Watching', game_running=True,
                           timer=raw, sleeping=False)
                    else:
                        print(f"[{ts}] ⏳ Waiting for game countdown… ({raw!r})")
                        ov(phase=1, phase_label='Waiting for game',
                           game_running=False, sleeping=False)
                    time.sleep(1)
                    continue

                # ── Phase 1: cheap countdown check ──────────────────────────
                if running:
                    misses = 0
                    print(f"[{ts}] ✓ Game running – timer: {raw}")
                    ov(phase=1, phase_label='Watching', game_running=True,
                       timer=raw, sleeping=False)
                    time.sleep(1)
                    continue

                misses += 1
                print(f"[{ts}] ✗ No countdown ({raw!r})  [{misses}/{MISS_THRESHOLD}]")
                ov(phase=1, phase_label='Watching', game_running=False, timer='')

                if misses < MISS_THRESHOLD:
                    time.sleep(1)
                    continue

                # ── Phase 2: full-frame end-screen hunt ──────────────────────
                print("\n" + "=" * 60)
                print("Countdown gone – scanning for end screen (2-min window)…")
                print("=" * 60)
                misses        = 0
                phase2_start  = time.time()
                ov(phase=2, phase_label='Scanning', game_running=False, sleeping=False)

                while True:
                    elapsed = time.time() - phase2_start
                    if elapsed > PHASE2_TIMEOUT:
                        print(f"\n[{ts}] ⏱ Phase 2 timed out after 2 min – "
                              f"returning to Phase 1 (watching) and resetting per-match data")
                        # Reset per-match player samples (player left / match aborted)
                        self._player_samples = [[] for _ in range(10)]
                        self._last_live_players = [""] * 10
                        self._last_live_map = None
                        # Clear players preview in overlay
                        if self.overlay_state is not None:
                            self.overlay_state['players_most_likely'] = None
                            self.overlay_state['players_last_raw'] = ''
                            self.overlay_state['players_image_bgr'] = None
                            self.overlay_state['players_image_bgr_processed'] = None
                        # Return to Phase 1 (watching) and continue monitoring
                        misses = 0
                        waiting_for_game = False
                        ov(phase=1, phase_label='Watching', game_running=False, timer='')
                        break

                    # Check the eliminated/winners headline region for the
                    # end-screen marker using OCR + color masking. A fuzzy
                    # match against END_SCREEN_WIN/LOSS_KEYWORDS (config.json)
                    # triggers the final stats capture.
                    try:
                        elim_img = self.capture_region(ELIMINATED_WON_REGION_REL)
                        processed_elim = apply_color_mask(elim_img, COLOR_RANGES_COUNTDOWN, invert=True)
                        rgb_elim = cv2.cvtColor(processed_elim, cv2.COLOR_BGR2RGB)
                        elim_text = pytesseract.image_to_string(rgb_elim, config='--psm 7').strip()
                        ts = datetime.now().strftime("%H:%M:%S")
                        remaining = int(PHASE2_TIMEOUT - elapsed)
                        print(f"[{ts}] Eliminated/Winners OCR: '{elim_text}' (timeout in {remaining}s)")

                        up = elim_text.upper()
                        win_match  = _keyword_match(up, END_SCREEN_WIN_KEYWORDS)
                        loss_match = _keyword_match(up, END_SCREEN_LOSS_KEYWORDS)
                        if win_match or loss_match:
                            won = win_match
                            print("✓ End-screen headline detected -> capturing final stats (win=%s)" % won)

                            # Full screenshot for stats extraction and logging
                            current_screenshot = self.take_screenshot()

                            extracted_text, cropped_image, preprocessed_image = self.extract_text(current_screenshot)
                            if extracted_text:
                                print(f"\n--- Extracted Text ({len(extracted_text)} chars) ---")
                                print(extracted_text)
                                print("-" * 60)
                                ov(last_detection=extracted_text)
                            else:
                                print("No text detected.")

                            stats = self.parse_stats(extracted_text)
                            self.save_log(stats, 1.0, cropped_image, preprocessed_image, won=won)

                            # After handling a detected end-screen: wait for next game
                            waiting_for_game = True
                            misses = 0
                            break
                        else:
                            time.sleep(0.3)
                    except Exception as e:
                        print(f"[Phase2] Elim/headline check error: {e}")
                        time.sleep(0.3)

        except KeyboardInterrupt:
            print("\n\n" + "=" * 60)
            print("Monitoring stopped by user")
            print("=" * 60)


def main():
    """Entry point.

    The overlay runs on the main thread (tkinter requirement).
    The monitor loop runs on a background daemon thread.
    The system tray icon runs in pystray's detached background thread.
    The tray 'Quit' option (or Ctrl-C) destroys the overlay, ending the
    main-thread mainloop so all daemon threads die naturally.
    """
    # When frozen (PyInstaller EXE) there is no console; redirect prints to a
    # log file next to the executable so errors are still inspectable.
    if getattr(sys, 'frozen', False):
        log_path = os.path.join(_app_dir(), 'fkc_debug.log')
        try:
            _lf = open(log_path, 'w', encoding='utf-8', buffering=1)
            sys.stdout = _lf
            sys.stderr = _lf
        except Exception:
            pass

    # Resolve Tesseract before creating the monitor.
    pytesseract.pytesseract.tesseract_cmd = _get_tesseract_path()

    profile_name = get_or_create_profile()

    # Check for updates (non-blocking: silently skips on network failure).
    check_for_update()

    try:
        monitor = ScreenshotMonitor(profile_name=profile_name)
    except Exception as e:
        msg = f'Error initialising monitor:\n{e}'
        print(msg)
        messagebox.showerror('Finals Kill Counter', msg)
        sys.exit(1)

    # Build overlay (main thread) and share its state dict with the monitor.
    overlay = OverlayWindow()
    monitor.overlay_state = overlay.state
    overlay.state['profile'] = profile_name

    # Home key still toggles the overlay (convenient for in-game use).
    def _on_home_press(key):
        if key == pynput_keyboard.Key.home:
            overlay.root.after(0, overlay.toggle)

    home_listener = pynput_keyboard.Listener(on_press=_on_home_press)
    home_listener.daemon = True
    home_listener.start()
    print('\u2713 Home key listener active (Home = toggle overlay)')

    # ── System tray icon ────────────────────────────────────────────────────
    def _make_tray_image():
        """Generate a 64×64 crosshair icon for the system tray."""
        img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, 60, 60], outline=(79, 195, 247, 255), width=5)
        draw.line([32, 4,  32, 22], fill=(79, 195, 247, 255), width=3)
        draw.line([32, 42, 32, 60], fill=(79, 195, 247, 255), width=3)
        draw.line([4,  32, 22, 32], fill=(79, 195, 247, 255), width=3)
        draw.line([42, 32, 60, 32], fill=(79, 195, 247, 255), width=3)
        draw.ellipse([27, 27, 37, 37], fill=(255, 100, 100, 255))
        return img

    tray_ref = [None]

    def _tray_toggle(icon, item):
        overlay.root.after(0, overlay.toggle)

    def _tray_quit(icon, item):
        icon.stop()
        overlay.root.after(0, overlay.root.destroy)

    tray = pystray.Icon(
        'FKC',
        _make_tray_image(),
        'Finals Kill Counter',
        pystray.Menu(
            pystray.MenuItem('Toggle Overlay', _tray_toggle),
            pystray.MenuItem('Quit', _tray_quit),
        ),
    )
    tray_ref[0] = tray
    tray.run_detached()
    print('\u2713 System tray icon active (right-click for options)')
    # ────────────────────────────────────────────────────────────────────────

    # Hook Ctrl-C so it closes everything cleanly.
    def _sigint_handler(sig, frame):
        print('\nCtrl-C received – shutting down…')
        if tray_ref[0]:
            tray_ref[0].stop()
        try:
            overlay.root.destroy()
        except Exception:
            pass
    signal.signal(signal.SIGINT, _sigint_handler)

    # Run monitor in background daemon thread.
    monitor_thread = threading.Thread(target=monitor.run, daemon=True)
    monitor_thread.start()

    # Block main thread in tkinter mainloop.
    overlay.run()

    # Mainloop ended (overlay destroyed) – stop the tray if still running.
    if tray_ref[0]:
        tray_ref[0].stop()


if __name__ == '__main__':
    main()
