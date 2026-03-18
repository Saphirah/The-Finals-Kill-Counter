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
from PIL import Image, ImageTk, ImageGrab
import cv2
import numpy as np
import json
import os
import threading
import time

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

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


# ── Config helpers ────────────────────────────────────────────────────────────

def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as exc:
        messagebox.showerror('Config error', f'Could not load config.json:\n{exc}')
        return {}


def save_config(cfg):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)


# ── Image processing helpers ──────────────────────────────────────────────────

def _apply_single(image_bgr, lower_hsv, upper_hsv, invert=False):
    hsv  = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(lower_hsv, np.uint8), np.array(upper_hsv, np.uint8))
    if invert:
        mask = cv2.bitwise_not(mask)
    out = np.zeros_like(image_bgr)
    out[mask > 0] = [255, 255, 255]
    return out


def _apply_all(image_bgr, ranges_list, invert=False):
    """Apply multiple HSV ranges (OR-combined) from a list of [lo, hi] pairs."""
    hsv      = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    combined = np.zeros(image_bgr.shape[:2], dtype=np.uint8)
    for lo, hi in ranges_list:
        combined = cv2.bitwise_or(
            combined,
            cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
        )
    if invert:
        combined = cv2.bitwise_not(combined)
    out = np.zeros_like(image_bgr)
    out[combined > 0] = [255, 255, 255]
    return out


# ── Main application ──────────────────────────────────────────────────────────

class ColorRangeTester(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title('HSV Color Range Tester')
        self.geometry('1140x700')
        self.minsize(900, 600)

        self.cfg          = load_config()
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

        ctrl = tk.Frame(tab, width=210)
        ctrl.pack(side='left', fill='y', padx=8, pady=8)
        ctrl.pack_propagate(False)

        tk.Button(ctrl, text='Open Image  (Ctrl+O)', command=self.open_image).pack(fill='x', pady=2)
        tk.Button(ctrl, text='Save Processed',       command=self.save_processed).pack(fill='x', pady=2)

        ttk.Separator(ctrl, orient='horizontal').pack(fill='x', pady=8)

        tk.Label(ctrl, text='Range Set').pack(anchor='w')
        sets = _list_color_sets(self.cfg)
        if not sets:
            # ensure at least defaults exist in config
            self.cfg.setdefault('color_ranges', {})
            sets = _list_color_sets(self.cfg)
        self._set_var = tk.StringVar(value=sets[0] if sets else '')
        set_cb = ttk.Combobox(ctrl, textvariable=self._set_var, values=sets,
                               state='readonly', width=24)
        set_cb.pack(fill='x', pady=2)
        set_cb.bind('<<ComboboxSelected>>', lambda e: self._on_set_changed())

        # Create / delete color set
        row_cd = tk.Frame(ctrl)
        row_cd.pack(fill='x', pady=4)
        tk.Button(row_cd, text='New Set', width=10, command=self._new_color_set).pack(side='left')
        tk.Button(row_cd, text='Delete Set', width=10, command=self._delete_color_set).pack(side='left', padx=4)

        tk.Label(ctrl, text='Range Index').pack(anchor='w', pady=(6, 0))
        idx_row = tk.Frame(ctrl)
        idx_row.pack(fill='x')
        self._idx_var  = tk.IntVar(value=0)
        self._idx_spin = tk.Spinbox(idx_row, from_=0, to=10, textvariable=self._idx_var,
                         width=4, command=self._on_idx_changed)
        self._idx_spin.pack(side='left')
        tk.Button(idx_row, text='+', width=2, command=self._add_range).pack(side='left', padx=2)
        tk.Button(idx_row, text='−', width=2, command=self._remove_range).pack(side='left')

        ttk.Separator(ctrl, orient='horizontal').pack(fill='x', pady=8)

        tk.Label(ctrl, text='Lower HSV  (H 0-179, S/V 0-255)', font=('', 8)).pack(anchor='w')
        self._lower_vars = []
        for ch in ('H', 'S', 'V'):
            row = tk.Frame(ctrl)
            row.pack(fill='x', pady=1)
            tk.Label(row, text=ch, width=2).pack(side='left')
            v = tk.StringVar(value='0')
            tk.Entry(row, textvariable=v, width=6).pack(side='left', fill='x', expand=True)
            v.trace_add('write', lambda *_: self.update_preview())
            self._lower_vars.append(v)

        tk.Label(ctrl, text='Upper HSV', font=('', 8)).pack(anchor='w', pady=(6, 0))
        self._upper_vars = []
        for ch in ('H', 'S', 'V'):
            row = tk.Frame(ctrl)
            row.pack(fill='x', pady=1)
            tk.Label(row, text=ch, width=2).pack(side='left')
            v = tk.StringVar(value='255')
            tk.Entry(row, textvariable=v, width=6).pack(side='left', fill='x', expand=True)
            v.trace_add('write', lambda *_: self.update_preview())
            self._upper_vars.append(v)

        self._invert_var = tk.BooleanVar(value=False)
        tk.Checkbutton(ctrl, text='Invert mask', variable=self._invert_var,
                       command=self.update_preview).pack(anchor='w', pady=6)

        ttk.Separator(ctrl, orient='horizontal').pack(fill='x', pady=4)

        tk.Button(ctrl, text='Save to Config  (Ctrl+S)', command=self.save_to_config,
              bg='#4fc3f7').pack(fill='x', pady=2)

        ttk.Separator(ctrl, orient='horizontal').pack(fill='x', pady=6)

        tk.Label(ctrl, text='Presets').pack(anchor='w')
        tk.Button(ctrl, text='White-ish',  command=lambda: self._apply_preset([0,0,200],  [179,50,255])).pack(fill='x', pady=1)
        tk.Button(ctrl, text='Yellow-ish', command=lambda: self._apply_preset([10,100,100],[35,255,255])).pack(fill='x', pady=1)
        tk.Button(ctrl, text='Orange-ish', command=lambda: self._apply_preset([5,100,150], [30,255,255])).pack(fill='x', pady=1)

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

        self._load_current_range()

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

    def _load_current_range(self):
        set_key = self._set_var.get()
        idx     = self._idx_var.get()
        ranges  = self.cfg.get('color_ranges', {}).get(set_key, [])
        if not ranges:
            return
        idx = max(0, min(idx, len(ranges) - 1))
        self._idx_var.set(idx)
        self._idx_spin.config(to=max(0, len(ranges) - 1))
        lo, hi = ranges[idx]
        for i in range(3):
            self._lower_vars[i].set(str(lo[i]))
            self._upper_vars[i].set(str(hi[i]))

    def _on_set_changed(self):
        self._idx_var.set(0)
        self._load_current_range()
        self.update_preview()

    def _on_idx_changed(self):
        self._load_current_range()
        self.update_preview()

    def _add_range(self):
        set_key = self._set_var.get()
        cr = self.cfg.setdefault('color_ranges', {})
        cr.setdefault(set_key, []).append([[0, 0, 0], [179, 255, 255]])
        self._idx_spin.config(to=len(cr[set_key]) - 1)
        self._idx_var.set(len(cr[set_key]) - 1)
        self._load_current_range()

    def _remove_range(self):
        set_key = self._set_var.get()
        ranges  = self.cfg.get('color_ranges', {}).get(set_key, [])
        if len(ranges) <= 1:
            messagebox.showinfo('Cannot remove', 'At least one range must remain.')
            return
        idx = self._idx_var.get()
        ranges.pop(idx)
        new_idx = max(0, idx - 1)
        self._idx_spin.config(to=max(0, len(ranges) - 1))
        self._idx_var.set(new_idx)
        self._load_current_range()
        self.update_preview()

    def _read_current_range(self):
        try:
            lo = [int(v.get()) for v in self._lower_vars]
            hi = [int(v.get()) for v in self._upper_vars]
            return lo, hi
        except ValueError:
            return None, None

    def save_to_config(self):
        lo, hi = self._read_current_range()
        if lo is None:
            messagebox.showerror('Invalid', 'HSV values must be integers.')
            return
        set_key = self._set_var.get()
        idx     = self._idx_var.get()
        cr = self.cfg.setdefault('color_ranges', {})
        ranges  = cr.setdefault(set_key, [])
        while len(ranges) <= idx:
            ranges.append([[0, 0, 0], [179, 255, 255]])
        ranges[idx] = [lo, hi]
        save_config(self.cfg)
        messagebox.showinfo('Saved', f'Saved {set_key}[{idx}] to config.json')

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
        self._load_current_range()

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

    def _cv_to_photo(self, cv_img, label):
        self.update_idletasks()
        lw = label.winfo_width()  or 800
        lh = label.winfo_height() or 300
        rgb   = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        img   = Image.fromarray(rgb)
        w, h  = img.size
        scale = min(1.0, lw / max(w, 1), lh / max(h, 1))
        if scale < 1.0:
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
        return ImageTk.PhotoImage(img)

    def update_preview(self):
        if self.cv_image is None:
            return
        lo, hi = self._read_current_range()
        if lo is None:
            return
        invert = self._invert_var.get()
        self.processed_cv = _apply_single(self.cv_image, lo, hi, invert=invert)
        try:
            p = self._cv_to_photo(self.cv_image, self._lbl_orig)
            self._photo_orig = p
            self._lbl_orig.config(image=p)
        except Exception:
            pass
        try:
            p = self._cv_to_photo(self.processed_cv, self._lbl_proc)
            self._photo_proc = p
            self._lbl_proc.config(image=p)
        except Exception:
            pass

    def _apply_preset(self, lo, hi):
        for i in range(3):
            self._lower_vars[i].set(str(lo[i]))
            self._upper_vars[i].set(str(hi[i]))
        self.update_preview()

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

        screen = ImageGrab.grab()
        sw, sh = screen.size
        x1 = int(region['x1'] * sw)
        y1 = int(region['y1'] * sh)
        x2 = int(region['x2'] * sw)
        y2 = int(region['y2'] * sh)
        cropped_pil = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        cropped     = cv2.cvtColor(np.array(cropped_pil), cv2.COLOR_RGB2BGR)

        set_key   = self._live_set_var.get()
        ranges    = self.cfg.get(set_key, [])
        invert    = self._live_invert_var.get()
        processed = _apply_all(cropped, ranges, invert=invert)

        self.after(0, self._update_live_labels, cropped, processed)

    def _update_live_labels(self, orig_bgr, proc_bgr):
        try:
            p = self._cv_to_photo(orig_bgr, self._lbl_live_orig)
            self._photo_live_orig = p
            self._lbl_live_orig.config(image=p)
        except Exception:
            pass
        try:
            p = self._cv_to_photo(proc_bgr, self._lbl_live_proc)
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
