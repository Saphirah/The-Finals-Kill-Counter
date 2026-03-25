"""
Region & OCR Tester
===================
Live tool for testing screen regions, color masks, and Tesseract OCR together.

Features
--------
- Choose a region from config.json OR enter custom relative bounds (0.0–1.0).
- Select one or more color-range sets from config.json; ranges are OR-combined.
- Add/remove ad-hoc HSV ranges on top of the selected config sets.
- Live preview at ~2 fps: original crop, processed B/W mask, and OCR output.
- Configurable Tesseract PSM mode and optional character whitelist.

Usage
-----
    python region_tester.py

Dependencies: opencv-python, pillow, numpy, pytesseract
"""

import tkinter as tk
from tkinter import ttk, messagebox
import cv2
import numpy as np
import threading
import time

from config_utils import _load_app_config, _cfg_to_ranges, init_tesseract
from image_utils import (apply_color_mask, sanitize_ocr_lines, capture_region,
                         apply_contrast, run_ocr, bgr_to_photo, load_ocr_replacements)

init_tesseract()
load_ocr_replacements(_load_app_config())

# ── PSM options ───────────────────────────────────────────────────────────────
PSM_OPTIONS = [
    '0 – Orientation/script detect',
    '3 – Fully automatic (default)',
    '4 – Single column',
    '6 – Uniform block',
    '7 – Single line',
    '8 – Single word',
    '10 – Single character',
    '11 – Sparse text',
    '13 – Raw line',
]
PSM_VALUES = [0, 3, 4, 6, 7, 8, 10, 11, 13]





# ── Main application ──────────────────────────────────────────────────────────

class RegionTester(tk.Tk):
    _BG  = '#1e1e1e'
    _FG  = '#eeeeee'
    _ACC = '#4fc3f7'

    def __init__(self):
        super().__init__()
        self.title('Region & OCR Tester — FKC')
        self.configure(bg=self._BG)
        self.geometry('900x700')
        self.minsize(820, 600)

        self._cfg = _load_app_config()
        self._running = False
        self._thread: threading.Thread | None = None

        # PhotoImage refs (prevent GC blanking)
        self._photo_orig = None
        self._photo_proc = None

        # Extra ad-hoc ranges added by the user at runtime
        self._extra_ranges: list[tuple] = []  # list of (np.array lo, np.array hi)

        self._build_ui()
        self.protocol('WM_DELETE_WINDOW', self._on_close)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Left control panel ─────────────────────────────────────────────
        ctrl = tk.Frame(self, bg=self._BG, width=260)
        ctrl.pack(side='left', fill='y', padx=(8, 4), pady=8)
        ctrl.pack_propagate(False)

        def section(text):
            tk.Label(ctrl, text=text, bg=self._BG, fg=self._ACC,
                     font=('Consolas', 9, 'bold')).pack(anchor='w', pady=(10, 2))
            ttk.Separator(ctrl, orient='horizontal').pack(fill='x', pady=(0, 4))

        def entry_row(parent, label, default=''):
            row = tk.Frame(parent, bg=self._BG)
            row.pack(fill='x', pady=1)
            tk.Label(row, text=label, width=4, bg=self._BG, fg=self._FG,
                     font=('Consolas', 9)).pack(side='left')
            v = tk.StringVar(value=default)
            e = tk.Entry(row, textvariable=v, width=12, bg='#2d2d2d', fg=self._FG,
                         insertbackground='white', font=('Consolas', 9))
            e.pack(side='left', fill='x', expand=True, padx=(2, 0))
            return v

        # ── Region ────────────────────────────────────────────────────────
        section('REGION')

        regions = list(self._cfg.get('regions', {}).keys())
        tk.Label(ctrl, text='From config:', bg=self._BG, fg=self._FG,
                 font=('Consolas', 9)).pack(anchor='w')
        self._region_var = tk.StringVar(value=regions[0] if regions else '')
        rgn_cb = ttk.Combobox(ctrl, textvariable=self._region_var, values=regions,
                               state='readonly', width=28)
        rgn_cb.pack(fill='x', pady=(0, 4))
        rgn_cb.bind('<<ComboboxSelected>>', lambda _e: self._load_region_from_config())

        tk.Label(ctrl, text='Custom bounds (0.0–1.0) — overrides selection:',
                 bg=self._BG, fg='#aaaaaa', font=('Consolas', 8),
                 wraplength=240, justify='left').pack(anchor='w')

        self._rx1 = entry_row(ctrl, 'x1', '')
        self._ry1 = entry_row(ctrl, 'y1', '')
        self._rx2 = entry_row(ctrl, 'x2', '')
        self._ry2 = entry_row(ctrl, 'y2', '')

        tk.Button(ctrl, text='Load selected region →', command=self._load_region_from_config,
                  bg='#333', fg=self._FG, font=('Consolas', 8)).pack(fill='x', pady=(2, 0))

        # ── Color ranges ──────────────────────────────────────────────────
        section('COLOR RANGES')

        color_sets = list(self._cfg.get('color_ranges', {}).keys())
        tk.Label(ctrl, text='Active sets (ctrl+click = multi-select):',
                 bg=self._BG, fg=self._FG, font=('Consolas', 8),
                 wraplength=240, justify='left').pack(anchor='w')
        self._sets_listbox = tk.Listbox(ctrl, selectmode='multiple', height=5,
                                         bg='#2d2d2d', fg=self._FG,
                                         selectbackground='#4fc3f7',
                                         selectforeground='#000',
                                         font=('Consolas', 9))
        for s in color_sets:
            self._sets_listbox.insert('end', s)
        self._sets_listbox.pack(fill='x', pady=(2, 4))

        # Option: invert final output (after contrast)
        self._invert_output_var = tk.BooleanVar(value=False)
        tk.Checkbutton(ctrl, text='Invert output (dark ↔ light after contrast)',
                   variable=self._invert_output_var, bg=self._BG, fg=self._FG,
                   selectcolor='#333', activebackground=self._BG,
                   font=('Consolas', 8)).pack(anchor='w')

        # Extra ad-hoc range
        section('ADD EXTRA RANGE  (HSV: H 0-179, S/V 0-255)')
        self._elo = [entry_row(ctrl, f'lo{c}', d) for c, d in zip('HSV', ['0', '0', '0'])]
        self._ehi = [entry_row(ctrl, f'hi{c}', d) for c, d in zip('HSV', ['179', '255', '255'])]
        extra_row = tk.Frame(ctrl, bg=self._BG)
        extra_row.pack(fill='x', pady=4)
        tk.Button(extra_row, text='+ Add Range', command=self._add_extra_range,
                  bg='#2d5a2d', fg='#a5d6a7', font=('Consolas', 8), width=12).pack(side='left')
        tk.Button(extra_row, text='Clear Extras', command=self._clear_extra_ranges,
                  bg='#5a2d2d', fg='#ef9a9a', font=('Consolas', 8), width=12).pack(side='left', padx=4)
        self._extra_label = tk.Label(ctrl, text='Extra ranges: 0', bg=self._BG,
                                      fg='#aaaaaa', font=('Consolas', 8))
        self._extra_label.pack(anchor='w')

        # ── OCR settings ──────────────────────────────────────────────────
        section('OCR SETTINGS')

        tk.Label(ctrl, text='PSM mode:', bg=self._BG, fg=self._FG,
                 font=('Consolas', 9)).pack(anchor='w')
        self._psm_var = tk.StringVar(value=PSM_OPTIONS[1])  # default 3 (fully automatic)
        psm_cb = ttk.Combobox(ctrl, textvariable=self._psm_var, values=PSM_OPTIONS,
                               state='readonly', width=28)
        psm_cb.pack(fill='x', pady=(0, 4))

        tk.Label(ctrl, text='Char whitelist (blank = none):',
                 bg=self._BG, fg=self._FG, font=('Consolas', 9)).pack(anchor='w')
        self._whitelist_var = tk.StringVar(value='')
        tk.Entry(ctrl, textvariable=self._whitelist_var, bg='#2d2d2d', fg=self._FG,
                 insertbackground='white', font=('Consolas', 9)).pack(fill='x', pady=(0, 6))

        # Option: sanitize OCR output
        self._sanitize_var = tk.BooleanVar(value=True)
        tk.Checkbutton(ctrl, text='Sanitize OCR output (keep last tokens)',
                   variable=self._sanitize_var, bg=self._BG, fg=self._FG,
                   selectcolor='#333', activebackground=self._BG,
                   font=('Consolas', 8)).pack(anchor='w', pady=(0, 6))

        # Contrast slider for final OCR image
        tk.Label(ctrl, text='Contrast (applied before OCR):', bg=self._BG, fg=self._FG,
             font=('Consolas', 9)).pack(anchor='w')
        self._contrast_var = tk.DoubleVar(value=1.0)
        contrast_scale = tk.Scale(ctrl, variable=self._contrast_var, from_=0.5, to=3.0,
                      resolution=0.1, orient='horizontal', length=220,
                      bg=self._BG, fg=self._FG, troughcolor='#333')
        contrast_scale.pack(anchor='w', pady=(0, 6))

        # Brightness pivot for contrast (0-255)
        tk.Label(ctrl, text='Brightness pivot (contrast revolves around):', bg=self._BG, fg=self._FG,
             font=('Consolas', 9)).pack(anchor='w')
        self._brightness_var = tk.IntVar(value=128)
        brightness_scale = tk.Scale(ctrl, variable=self._brightness_var, from_=0, to=255,
                        resolution=1, orient='horizontal', length=220,
                        bg=self._BG, fg=self._FG, troughcolor='#333')
        brightness_scale.pack(anchor='w', pady=(0, 6))

        # ── Start/Stop ────────────────────────────────────────────────────
        self._toggle_btn = tk.Button(ctrl, text='▶  Start (2 fps)',
                                      command=self._toggle,
                                      bg='#2d5a2d', fg='#a5d6a7',
                                      font=('Consolas', 9, 'bold'))
        self._toggle_btn.pack(fill='x', pady=4)
        self._status_lbl = tk.Label(ctrl, text='● Idle', bg=self._BG, fg='#888',
                                     font=('Consolas', 8))
        self._status_lbl.pack(anchor='w')

        # ── Right preview area ─────────────────────────────────────────────
        right = tk.Frame(self, bg=self._BG)
        right.pack(side='right', fill='both', expand=True, padx=(4, 8), pady=8)

        def preview_block(parent, title):
            tk.Label(parent, text=title, bg=self._BG, fg=self._ACC,
                     font=('Consolas', 9, 'bold')).pack(anchor='w')
            lbl = tk.Label(parent, bg='#111', bd=1, relief='sunken')
            lbl.pack(fill='x', pady=(0, 6))
            return lbl

        self._lbl_orig = preview_block(right, 'Original crop')
        self._lbl_proc = preview_block(right, 'Processed (B/W mask)')

        tk.Label(right, text='OCR output', bg=self._BG, fg=self._ACC,
                 font=('Consolas', 9, 'bold')).pack(anchor='w')
        ocr_frame = tk.Frame(right, bg=self._BG)
        ocr_frame.pack(fill='both', expand=True)
        self._ocr_text = tk.Text(ocr_frame, height=8, bg='#111', fg='#a5d6a7',
                                  font=('Consolas', 10), wrap='word',
                                  state='disabled')
        ocr_scroll = ttk.Scrollbar(ocr_frame, command=self._ocr_text.yview)
        self._ocr_text.configure(yscrollcommand=ocr_scroll.set)
        ocr_scroll.pack(side='right', fill='y')
        self._ocr_text.pack(fill='both', expand=True)

        # Load first region from config into the fields
        self._load_region_from_config()

    # ── Region helpers ────────────────────────────────────────────────────────

    def _load_region_from_config(self):
        key = self._region_var.get()
        r = self._cfg.get('regions', {}).get(key, {})
        if r:
            self._rx1.set(str(round(r.get('x1', 0.0), 6)))
            self._ry1.set(str(round(r.get('y1', 0.0), 6)))
            self._rx2.set(str(round(r.get('x2', 1.0), 6)))
            self._ry2.set(str(round(r.get('y2', 1.0), 6)))

    def _get_region(self) -> dict | None:
        try:
            return {
                'x1': float(self._rx1.get()),
                'y1': float(self._ry1.get()),
                'x2': float(self._rx2.get()),
                'y2': float(self._ry2.get()),
            }
        except ValueError:
            return None

    # ── Extra range helpers ───────────────────────────────────────────────────

    def _add_extra_range(self):
        try:
            lo = np.array([int(v.get()) for v in self._elo], dtype=np.uint8)
            hi = np.array([int(v.get()) for v in self._ehi], dtype=np.uint8)
        except ValueError:
            messagebox.showerror('Invalid', 'HSV values must be integers (0-255).')
            return
        self._extra_ranges.append((lo, hi))
        self._extra_label.config(text=f'Extra ranges: {len(self._extra_ranges)}')

    def _clear_extra_ranges(self):
        self._extra_ranges.clear()
        self._extra_label.config(text='Extra ranges: 0')

    # ── Color range assembly ──────────────────────────────────────────────────

    def _build_ranges(self) -> list:
        """Combine selected config sets + extra ad-hoc ranges into one list."""
        ranges = []
        selected_indices = self._sets_listbox.curselection()
        color_sets = list(self._cfg.get('color_ranges', {}).keys())
        for i in selected_indices:
            if i < len(color_sets):
                raw = self._cfg['color_ranges'][color_sets[i]]
                ranges.extend(_cfg_to_ranges(raw))
        ranges.extend(self._extra_ranges)
        return ranges

    # ── OCR helpers ───────────────────────────────────────────────────────────

    def _get_psm(self) -> int:
        label = self._psm_var.get()
        idx = PSM_OPTIONS.index(label) if label in PSM_OPTIONS else 5
        return PSM_VALUES[idx]

    # ── Live loop ──────────────────────────────────────────────────────────────

    def _toggle(self):
        if self._running:
            self._running = False
            self._toggle_btn.config(text='▶  Start (2 fps)', bg='#2d5a2d', fg='#a5d6a7')
            self._status_lbl.config(text='● Idle', fg='#888')
        else:
            region = self._get_region()
            if region is None:
                messagebox.showerror('Invalid region', 'All four bounds must be decimal numbers.')
                return
            self._running = True
            self._toggle_btn.config(text='■  Stop', bg='#5a2d2d', fg='#ef9a9a')
            self._status_lbl.config(text='● Running…', fg='#44cc44')
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def _loop(self):
        while self._running:
            t0 = time.monotonic()
            try:
                self._tick()
            except Exception as exc:
                self.after(0, self._set_status, f'⚠ {exc}')
            elapsed = time.monotonic() - t0
            sleep_for = max(0.0, 0.5 - elapsed)
            time.sleep(sleep_for)

    def _tick(self):
        region = self._get_region()
        if region is None:
            return

        orig = capture_region(region)
        ranges = self._build_ranges()

        if ranges:
            proc = apply_color_mask(orig, ranges, invert=False)
        else:
            grey = cv2.cvtColor(orig, cv2.COLOR_BGR2GRAY)
            proc = cv2.cvtColor(grey, cv2.COLOR_GRAY2BGR)

        try:
            contrast = float(self._contrast_var.get())
        except Exception:
            contrast = 1.0
        try:
            pivot = int(self._brightness_var.get())
        except Exception:
            pivot = 128

        proc_for_ocr = apply_contrast(proc, contrast, pivot)

        if self._invert_output_var.get():
            proc_for_ocr = cv2.bitwise_not(proc_for_ocr)

        raw = run_ocr(proc_for_ocr, psm=self._get_psm(),
                      whitelist=self._whitelist_var.get().strip())
        if self._sanitize_var.get():
            tokens = sanitize_ocr_lines(raw, self._region_var.get())
            ocr_text = '\n'.join(tokens) if tokens else ''
        else:
            ocr_text = raw

        self.after(0, self._update_ui, orig, proc_for_ocr, ocr_text)

    def _update_ui(self, orig_bgr, proc_bgr, ocr_text: str):
        try:
            p = bgr_to_photo(orig_bgr)
            self._photo_orig = p
            self._lbl_orig.config(image=p)
        except Exception:
            pass
        try:
            p = bgr_to_photo(proc_bgr)
            self._photo_proc = p
            self._lbl_proc.config(image=p)
        except Exception:
            pass
        self._ocr_text.config(state='normal')
        self._ocr_text.delete('1.0', 'end')
        self._ocr_text.insert('end', ocr_text if ocr_text else '(no text detected)')
        self._ocr_text.config(state='disabled')
        self._status_lbl.config(text=f'● Running  ({len(ocr_text)} chars)', fg='#44cc44')

    def _set_status(self, msg: str):
        self._status_lbl.config(text=msg, fg='#ef9a9a')

    def _on_close(self):
        self._running = False
        self.destroy()


if __name__ == '__main__':
    app = RegionTester()
    app.mainloop()
