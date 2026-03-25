"""
HSV Color Range Tester + Live Region Preview

Tab 1 – Image Tester
    Open an image, select a named color-range set from config.json,
    adjust lower/upper HSV values per range-index, preview the B/W mask,
    and save changes back to config.

Tab 2 – Live Preview
    Grab a screenshot every second, crop it to a configurable relative region,
    apply a chosen color-range set, and show the result live.
    Edit region bounds and save them to config.

Usage:
    python color_range_tester.py

Dependencies: opencv-python, pillow, numpy
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import cv2
import numpy as np
import os
import threading
import time

from config_utils import _load_app_config, save_config, init_tesseract
from image_utils import apply_color_mask, capture_region, run_ocr, bgr_to_photo, load_ocr_replacements

init_tesseract()
load_ocr_replacements(_load_app_config())

# Protected keys which should not be deleted because other code depends on them
PROTECTED_COLOR_KEYS = ['color_ranges_endscreen', 'color_ranges_map', 'color_ranges_countdown']
PROTECTED_REGION_KEYS = ['map_region_rel', 'countdown_region_rel', 'crop_bounds_rel']


def _list_color_sets(cfg):
    return list(cfg.get('color_ranges', {}).keys())


def _list_regions(cfg):
    return list(cfg.get('regions', {}).keys())


def simple_input(parent, prompt):
    """Ask the user for a short text input; returns None or string."""
    return simpledialog.askstring('Input', prompt, parent=parent)


# ── Main application ──────────────────────────────────────────────────────────

class ColorRangeTester(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title('HSV Color Range Tester')
        self.geometry('1140x700')
        self.minsize(900, 600)

        self.cfg          = _load_app_config()
        self.cv_image     = None
        self.processed_cv = None
        self._live_running = False

        notebook = ttk.Notebook(self)
        notebook.pack(fill='both', expand=True, padx=4, pady=4)

        self._tab_image = tk.Frame(notebook)
        self._tab_live  = tk.Frame(notebook)
        notebook.add(self._tab_image, text='  Image Tester  ')
        notebook.add(self._tab_live,  text='  Live Preview  ')

        self._build_image_tab()
        self._build_live_tab()

        self.bind('<Control-o>', lambda e: self.open_image())
        self.bind('<Control-s>', lambda e: self.save_to_config())
        self.protocol('WM_DELETE_WINDOW', self._on_close)

    # ── Image tab ─────────────────────────────────────────────────────────────

    def _build_image_tab(self):
        tab = self._tab_image

        ctrl = tk.Frame(tab, width=280)
        ctrl.pack(side='left', fill='y', padx=8, pady=8)
        ctrl.pack_propagate(False)

        tk.Button(ctrl, text='Open Image  (Ctrl+O)', command=self.open_image).pack(fill='x', pady=2)
        tk.Button(ctrl, text='Save Processed',       command=self.save_processed).pack(fill='x', pady=2)

        ttk.Separator(ctrl, orient='horizontal').pack(fill='x', pady=8)

        tk.Label(ctrl, text='Range Set').pack(anchor='w')
        sets = _list_color_sets(self.cfg)
        if not sets:
            self.cfg.setdefault('color_ranges', {})
            sets = _list_color_sets(self.cfg)
        self._set_var = tk.StringVar(value=sets[0] if sets else '')
        set_cb = ttk.Combobox(ctrl, textvariable=self._set_var, values=sets,
                               state='readonly', width=30)
        set_cb.pack(fill='x', pady=2)
        set_cb.bind('<<ComboboxSelected>>', lambda e: self._on_set_changed())

        # Create / delete color set
        row_cd = tk.Frame(ctrl)
        row_cd.pack(fill='x', pady=4)
        tk.Button(row_cd, text='New Set',    width=10, command=self._new_color_set).pack(side='left')
        tk.Button(row_cd, text='Delete Set', width=10, command=self._delete_color_set).pack(side='left', padx=4)

        ttk.Separator(ctrl, orient='horizontal').pack(fill='x', pady=4)

        rng_hdr = tk.Frame(ctrl)
        rng_hdr.pack(fill='x', pady=(0, 2))
        tk.Label(rng_hdr, text='Ranges  (H 0-179, S/V 0-255)', font=('', 8)).pack(side='left')
        tk.Button(rng_hdr, text='+ Add', command=self._add_range).pack(side='right')

        # ── Bottom controls – packed BEFORE canvas so they stay pinned ──────
        bottom = tk.Frame(ctrl)
        bottom.pack(side='bottom', fill='x')

        self._invert_var = tk.BooleanVar(value=False)
        tk.Checkbutton(bottom, text='Invert mask', variable=self._invert_var,
                       command=self.update_preview).pack(anchor='w', pady=(6, 2))

        ttk.Separator(bottom, orient='horizontal').pack(fill='x', pady=4)
        tk.Button(bottom, text='Save to Config  (Ctrl+S)', command=self.save_to_config,
                  bg='#4fc3f7').pack(fill='x', pady=2)
        ttk.Separator(bottom, orient='horizontal').pack(fill='x', pady=6)

        tk.Label(bottom, text='Presets  (appends a new range)').pack(anchor='w')
        tk.Button(bottom, text='White-ish',  command=lambda: self._apply_preset([0,0,200],  [179,50,255])).pack(fill='x', pady=1)
        tk.Button(bottom, text='Yellow-ish', command=lambda: self._apply_preset([10,100,100],[35,255,255])).pack(fill='x', pady=1)
        tk.Button(bottom, text='Orange-ish', command=lambda: self._apply_preset([5,100,150], [30,255,255])).pack(fill='x', pady=1)

        # ── Scrollable multi-range editor ─────────────────────────────────────
        scroll_outer = tk.Frame(ctrl)
        scroll_outer.pack(fill='both', expand=True)

        self._ranges_canvas = tk.Canvas(scroll_outer, highlightthickness=0)
        _rsb = ttk.Scrollbar(scroll_outer, orient='vertical', command=self._ranges_canvas.yview)
        self._ranges_canvas.configure(yscrollcommand=_rsb.set)
        _rsb.pack(side='right', fill='y')
        self._ranges_canvas.pack(side='left', fill='both', expand=True)

        self._ranges_inner = tk.Frame(self._ranges_canvas)
        self._ranges_canvas_win = self._ranges_canvas.create_window(
            (0, 0), window=self._ranges_inner, anchor='nw')
        self._ranges_inner.bind('<Configure>', lambda e: self._ranges_canvas.configure(
            scrollregion=self._ranges_canvas.bbox('all')))
        self._ranges_canvas.bind('<Configure>', lambda e: self._ranges_canvas.itemconfig(
            self._ranges_canvas_win, width=e.width))

        self._range_rows = []  # list of {'lo': [sv]*3, 'hi': [sv]*3}

        right = tk.Frame(tab)
        right.pack(side='right', fill='both', expand=True)
        tk.Label(right, text='Original').pack()
        self._lbl_orig = tk.Label(right, bd=1, relief='sunken', bg='#222')
        self._lbl_orig.pack(fill='both', expand=True, padx=4, pady=2)
        tk.Label(right, text='Processed (B/W)').pack()
        self._lbl_proc = tk.Label(right, bd=1, relief='sunken', bg='#222')
        self._lbl_proc.pack(fill='both', expand=True, padx=4, pady=2)
        self._photo_orig = None
        self._photo_proc = None

        # OCR output
        ocr_header = tk.Frame(right)
        ocr_header.pack(fill='x', padx=4, pady=(4, 0))
        tk.Label(ocr_header, text='OCR Output (Processed Image)').pack(side='left')
        tk.Button(ocr_header, text='Run OCR', command=self._run_ocr).pack(side='right')
        ocr_body = tk.Frame(right)
        ocr_body.pack(fill='x', padx=4, pady=(0, 4))
        self._ocr_text = tk.Text(ocr_body, height=5, wrap='word', state='disabled',
                                  bg='#1e1e1e', fg='#d4d4d4', font=('Consolas', 9))
        ocr_sb = tk.Scrollbar(ocr_body, command=self._ocr_text.yview)
        self._ocr_text.config(yscrollcommand=ocr_sb.set)
        ocr_sb.pack(side='right', fill='y')
        self._ocr_text.pack(side='left', fill='x', expand=True)

        self._rebuild_range_rows()

    # ── Live tab ──────────────────────────────────────────────────────────────

    def _build_live_tab(self):
        tab = self._tab_live

        ctrl = tk.Frame(tab, width=230)
        ctrl.pack(side='left', fill='y', padx=8, pady=8)
        ctrl.pack_propagate(False)

        tk.Label(ctrl, text='Region').pack(anchor='w')
        regions = _list_regions(self.cfg)
        if not regions:
            self.cfg.setdefault('regions', {})
            regions = _list_regions(self.cfg)
        self._live_region_var = tk.StringVar(value=regions[0] if regions else '')
        rgn_cb = ttk.Combobox(ctrl, textvariable=self._live_region_var,
                               values=regions, state='readonly', width=26)
        rgn_cb.pack(fill='x', pady=2)
        rgn_cb.bind('<<ComboboxSelected>>', lambda e: self._on_live_region_changed())

        # Create / delete region
        row_r_cd = tk.Frame(ctrl)
        row_r_cd.pack(fill='x', pady=4)
        tk.Button(row_r_cd, text='New Region', width=12, command=self._new_region).pack(side='left')
        tk.Button(row_r_cd, text='Delete Region', width=12, command=self._delete_region).pack(side='left', padx=4)

        tk.Label(ctrl, text='Relative bounds (0.0 – 1.0)', font=('', 8)).pack(anchor='w', pady=(6, 0))
        self._region_vars = {}
        for key in ('x1', 'y1', 'x2', 'y2'):
            row = tk.Frame(ctrl)
            row.pack(fill='x', pady=1)
            tk.Label(row, text=key, width=3).pack(side='left')
            v = tk.StringVar(value='0.0')
            tk.Entry(row, textvariable=v, width=12).pack(side='left', fill='x', expand=True)
            self._region_vars[key] = v

        tk.Button(ctrl, text='Save Region to Config', command=self._save_region_to_config,
                  bg='#4fc3f7').pack(fill='x', pady=6)

        ttk.Separator(ctrl, orient='horizontal').pack(fill='x', pady=6)

        tk.Label(ctrl, text='Color Range Set').pack(anchor='w')
        sets = _list_color_sets(self.cfg)
        self._live_set_var = tk.StringVar(value=sets[0] if sets else '')
        self._live_set_cb = ttk.Combobox(ctrl, textvariable=self._live_set_var, values=sets,
                 state='readonly', width=26)
        self._live_set_cb.pack(fill='x', pady=2)

        self._live_invert_var = tk.BooleanVar(value=True)
        tk.Checkbutton(ctrl, text='Invert mask (dark-on-light)',
                       variable=self._live_invert_var).pack(anchor='w', pady=4)

        ttk.Separator(ctrl, orient='horizontal').pack(fill='x', pady=6)

        self._live_btn = tk.Button(ctrl, text='▶  Start Live Preview',
                                   command=self._toggle_live, bg='#a5d6a7')
        self._live_btn.pack(fill='x', pady=4)
        self._live_status = tk.Label(ctrl, text='● Stopped', fg='#cc4444')
        self._live_status.pack(anchor='w')

        right = tk.Frame(tab)
        right.pack(side='right', fill='both', expand=True)
        tk.Label(right, text='Live – Original').pack()
        self._lbl_live_orig = tk.Label(right, bd=1, relief='sunken', bg='#222')
        self._lbl_live_orig.pack(fill='both', expand=True, padx=4, pady=2)
        tk.Label(right, text='Live – Processed (B/W)').pack()
        self._lbl_live_proc = tk.Label(right, bd=1, relief='sunken', bg='#222')
        self._lbl_live_proc.pack(fill='both', expand=True, padx=4, pady=2)
        self._photo_live_orig = None
        self._photo_live_proc = None

        self._on_live_region_changed()

    # ── Config helpers ────────────────────────────────────────────────────────

    def _rebuild_range_rows(self):
        """Rebuild the scrollable list of range rows from the current config."""
        for w in self._ranges_inner.winfo_children():
            w.destroy()
        self._range_rows = []

        set_key = self._set_var.get()
        ranges  = self.cfg.get('color_ranges', {}).get(set_key, [])
        if not ranges:
            self.cfg.setdefault('color_ranges', {}).setdefault(set_key, []).append(
                [[0, 0, 0], [179, 255, 255]])
            ranges = self.cfg['color_ranges'][set_key]

        for idx, (lo, hi) in enumerate(ranges):
            self._append_range_row(idx, lo, hi)

        self._ranges_inner.update_idletasks()
        self._ranges_canvas.configure(scrollregion=self._ranges_canvas.bbox('all'))

    def _append_range_row(self, idx: int, lo, hi):
        """Add one range row widget to the scrollable inner frame."""
        row_frame = tk.LabelFrame(self._ranges_inner, text=f'Range {idx}', padx=4, pady=2)
        row_frame.pack(fill='x', padx=2, pady=2)
        tk.Button(row_frame, text='✕', fg='red',
                  command=lambda i=idx: self._remove_range(i)).pack(side='right', anchor='n')

        lo_row = tk.Frame(row_frame)
        lo_row.pack(fill='x', pady=1)
        tk.Label(lo_row, text='Lo', width=3).pack(side='left')
        lo_vars = []
        for ch, val in zip('HSV', lo):
            tk.Label(lo_row, text=ch, width=1).pack(side='left')
            v = tk.StringVar(value=str(val))
            tk.Entry(lo_row, textvariable=v, width=4).pack(side='left', padx=(0, 2))
            v.trace_add('write', lambda *_: self.update_preview())
            lo_vars.append(v)

        hi_row = tk.Frame(row_frame)
        hi_row.pack(fill='x', pady=1)
        tk.Label(hi_row, text='Hi', width=3).pack(side='left')
        hi_vars = []
        for ch, val in zip('HSV', hi):
            tk.Label(hi_row, text=ch, width=1).pack(side='left')
            v = tk.StringVar(value=str(val))
            tk.Entry(hi_row, textvariable=v, width=4).pack(side='left', padx=(0, 2))
            v.trace_add('write', lambda *_: self.update_preview())
            hi_vars.append(v)

        self._range_rows.append({'lo': lo_vars, 'hi': hi_vars})

    def _on_set_changed(self):
        self._rebuild_range_rows()
        self.update_preview()

    def _add_range(self):
        set_key = self._set_var.get()
        cr      = self.cfg.setdefault('color_ranges', {})
        current = self._read_all_ranges() or []
        current.append([[0, 0, 0], [179, 255, 255]])
        cr[set_key] = current
        self._rebuild_range_rows()
        self._ranges_canvas.yview_moveto(1.0)

    def _remove_range(self, idx: int):
        if len(self._range_rows) <= 1:
            messagebox.showinfo('Cannot remove', 'At least one range must remain.')
            return
        set_key = self._set_var.get()
        current = self._read_all_ranges() or []
        if idx < len(current):
            current.pop(idx)
        self.cfg.setdefault('color_ranges', {})[set_key] = current
        self._rebuild_range_rows()
        self.update_preview()

    def _read_all_ranges(self):
        """Read all range rows; returns list of [lo, hi] or None on parse error."""
        result = []
        try:
            for row in self._range_rows:
                lo = [int(v.get()) for v in row['lo']]
                hi = [int(v.get()) for v in row['hi']]
                result.append([lo, hi])
        except ValueError:
            return None
        return result

    def save_to_config(self):
        ranges = self._read_all_ranges()
        if ranges is None:
            messagebox.showerror('Invalid', 'HSV values must be integers.')
            return
        set_key = self._set_var.get()
        self.cfg.setdefault('color_ranges', {})[set_key] = ranges
        save_config(self.cfg)
        messagebox.showinfo('Saved', f'Saved {set_key} ({len(ranges)} range(s)) to config.json')

    def _on_live_region_changed(self):
        key    = self._live_region_var.get()
        region = self.cfg.get('regions', {}).get(key, {'x1': 0.0, 'y1': 0.0, 'x2': 1.0, 'y2': 1.0})
        for k, v in self._region_vars.items():
            v.set(str(round(region.get(k, 0.0), 6)))

    def _save_region_to_config(self):
        try:
            region = {k: float(v.get()) for k, v in self._region_vars.items()}
        except ValueError:
            messagebox.showerror('Invalid', 'Region bounds must be decimal numbers.')
            return
        key = self._live_region_var.get()
        regs = self.cfg.setdefault('regions', {})
        regs[key] = region
        save_config(self.cfg)
        messagebox.showinfo('Saved', f'Saved {key} to config.json')

    # ── Create / Delete sets & regions ───────────────────────────────────────

    def _new_color_set(self):
        name = simple_input(self, 'New color set name')
        if not name:
            return
        cr = self.cfg.setdefault('color_ranges', {})
        if name in cr:
            messagebox.showinfo('Exists', 'A color set with that name already exists.')
            return
        cr[name] = [[[0,0,0],[179,255,255]]]
        save_config(self.cfg)
        self._refresh_color_sets()
        self._set_var.set(name)
        self._rebuild_range_rows()

    def _delete_color_set(self):
        name = self._set_var.get()
        if not name:
            return
        if name in PROTECTED_COLOR_KEYS:
            messagebox.showerror('Protected', 'This color set is protected and cannot be deleted.')
            return
        cr = self.cfg.get('color_ranges', {})
        if name in cr:
            if not messagebox.askyesno('Delete', f'Delete color set "{name}"?'):
                return
            del cr[name]
            save_config(self.cfg)
            self._refresh_color_sets()

    def _refresh_color_sets(self):
        sets = _list_color_sets(self.cfg)
        widget = None
        for child in self.children.values():
            if isinstance(child, ttk.Notebook):
                widget = child
                break
        # update combobox values in UI
        # update comboboxes on both tabs
        for frame in (self._tab_image, self._tab_live):
            for w in frame.winfo_children():
                if isinstance(w, ttk.Combobox) and w.cget('values'):
                    w.config(values=sets)
        if sets:
            self._set_var.set(sets[0])
        else:
            self._set_var.set('')
        if hasattr(self, '_ranges_inner'):
            self._rebuild_range_rows()
            self.update_preview()

    def _new_region(self):
        name = simple_input(self, 'New region name')
        if not name:
            return
        regs = self.cfg.setdefault('regions', {})
        if name in regs:
            messagebox.showinfo('Exists', 'A region with that name already exists.')
            return
        regs[name] = {'x1': 0.0, 'y1': 0.0, 'x2': 1.0, 'y2': 1.0}
        save_config(self.cfg)
        self._refresh_regions()
        self._live_region_var.set(name)
        self._on_live_region_changed()

    def _delete_region(self):
        name = self._live_region_var.get()
        if not name:
            return
        if name in PROTECTED_REGION_KEYS:
            messagebox.showerror('Protected', 'This region is protected and cannot be deleted.')
            return
        regs = self.cfg.get('regions', {})
        if name in regs:
            if not messagebox.askyesno('Delete', f'Delete region "{name}"?'):
                return
            del regs[name]
            save_config(self.cfg)
            self._refresh_regions()

    def _refresh_regions(self):
        regions = _list_regions(self.cfg)
        # update combobox values in UI
        for frame in self._tab_live.winfo_children():
            for w in frame.winfo_children():
                if isinstance(w, ttk.Combobox) and w.cget('values'):
                    w.config(values=regions)
        if regions:
            self._live_region_var.set(regions[0])
        else:
            self._live_region_var.set('')

    # ── Image tab actions ─────────────────────────────────────────────────────

    def open_image(self):
        path = filedialog.askopenfilename(
            filetypes=[('Images', '*.png;*.jpg;*.jpeg;*.bmp;*.tif;*.tiff')])
        if not path:
            return
        img = cv2.imread(path)
        if img is None:
            messagebox.showerror('Error', 'Failed to open image.')
            return
        self.cv_image = img
        self.title(f'HSV Color Range Tester — {os.path.basename(path)}')
        self.update_preview()

    def save_processed(self):
        if self.processed_cv is None:
            messagebox.showinfo('No image', 'No processed image to save.')
            return
        path = filedialog.asksaveasfilename(defaultextension='.png',
                                            filetypes=[('PNG', '*.png')])
        if not path:
            return
        cv2.imwrite(path, self.processed_cv)
        messagebox.showinfo('Saved', f'Saved to:\n{path}')

    def _photo_for_label(self, cv_img, label):
        """Convert BGR image to PhotoImage sized to fit *label*."""
        self.update_idletasks()
        lw = label.winfo_width() or 800
        lh = label.winfo_height() or 300
        return bgr_to_photo(cv_img, max_w=lw, max_h=lh)

    def update_preview(self):
        if self.cv_image is None:
            return
        ranges = self._read_all_ranges()
        if not ranges:
            return
        invert = self._invert_var.get()
        self.processed_cv = apply_color_mask(self.cv_image, ranges, invert=invert)
        try:
            p = self._photo_for_label(self.cv_image, self._lbl_orig)
            self._photo_orig = p
            self._lbl_orig.config(image=p)
        except Exception:
            pass
        try:
            p = self._photo_for_label(self.processed_cv, self._lbl_proc)
            self._photo_proc = p
            self._lbl_proc.config(image=p)
        except Exception:
            pass

    def _apply_preset(self, lo, hi):
        set_key = self._set_var.get()
        current = self._read_all_ranges() or []
        current.append([lo, hi])
        self.cfg.setdefault('color_ranges', {})[set_key] = current
        self._rebuild_range_rows()
        self.update_preview()

    def _run_ocr(self):
        if self.processed_cv is None:
            messagebox.showinfo('No image', 'No processed image to run OCR on.')
            return
        try:
            text = run_ocr(self.processed_cv)
        except Exception as exc:
            text = f'OCR Error: {exc}'
        self._ocr_text.config(state='normal')
        self._ocr_text.delete('1.0', 'end')
        self._ocr_text.insert('end', text.strip() or '(no text detected)')
        self._ocr_text.config(state='disabled')

    # ── Live tab actions ──────────────────────────────────────────────────────

    def _toggle_live(self):
        if self._live_running:
            self._live_running = False
            self._live_btn.config(text='▶  Start Live Preview', bg='#a5d6a7')
            self._live_status.config(text='● Stopped', fg='#cc4444')
        else:
            self._live_running = True
            self._live_btn.config(text='■  Stop Live Preview', bg='#ef9a9a')
            self._live_status.config(text='● Running…', fg='#44aa44')
            threading.Thread(target=self._live_loop, daemon=True).start()

    def _live_loop(self):
        while self._live_running:
            try:
                self._capture_and_update()
            except Exception as exc:
                print(f'[Live] {exc}')
            time.sleep(1)

    def _capture_and_update(self):
        try:
            region = {k: float(v.get()) for k, v in self._region_vars.items()}
        except ValueError:
            return

        cropped = capture_region(region)

        set_key   = self._live_set_var.get()
        ranges    = self.cfg.get('color_ranges', {}).get(set_key, [])
        invert    = self._live_invert_var.get()
        processed = apply_color_mask(cropped, ranges, invert=invert)

        self.after(0, self._update_live_labels, cropped, processed)

    def _update_live_labels(self, orig_bgr, proc_bgr):
        try:
            p = self._photo_for_label(orig_bgr, self._lbl_live_orig)
            self._photo_live_orig = p
            self._lbl_live_orig.config(image=p)
        except Exception:
            pass
        try:
            p = self._photo_for_label(proc_bgr, self._lbl_live_proc)
            self._photo_live_proc = p
            self._lbl_live_proc.config(image=p)
        except Exception:
            pass

    def _on_close(self):
        self._live_running = False
        self.destroy()


if __name__ == '__main__':
    app = ColorRangeTester()
    app.mainloop()
