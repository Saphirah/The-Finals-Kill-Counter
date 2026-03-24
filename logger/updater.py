"""
FKC Updater  –  downloads a new release zip, waits for the main process to
exit, replaces FinalsKillCounter.exe, then re-launches it.

Invoked by FinalsKillCounter.exe with:
    updater.exe --url <zip_url> --target <path\\to\\FinalsKillCounter.exe> --pid <main_pid>

Never shows a console window (console=False in updater.spec).
"""

import argparse
import ctypes
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
import tkinter as tk
from tkinter import ttk, messagebox


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wait_for_pid(pid: int, timeout_s: int = 30) -> None:
    """Block until process *pid* exits (or *timeout_s* seconds elapse)."""
    SYNCHRONIZE = 0x00100000
    handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        return  # process already gone
    try:
        ctypes.windll.kernel32.WaitForSingleObject(handle, timeout_s * 1000)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

class UpdaterApp:
    """Single-window progress UI that drives the whole update sequence."""

    _BG = "#1e1e1e"

    def __init__(self, url: str, target_exe: str, main_pid: int, new_version: str) -> None:
        self.url = url
        self.target_exe = os.path.abspath(target_exe)
        self.main_pid = main_pid
        self.new_version = new_version

        self.root = tk.Tk()
        self.root.title("Finals Kill Counter \u2013 Updating")
        self.root.geometry("440x150")
        self.root.resizable(False, False)
        self.root.configure(bg=self._BG)
        self.root.attributes("-topmost", True)
        # Prevent the user from closing the window while an update is in progress.
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)

        tk.Label(
            self.root,
            text="Finals Kill Counter \u2013 Updating\u2026",
            bg=self._BG, fg="#4fc3f7",
            font=("Segoe UI", 11, "bold"),
        ).pack(pady=(20, 6))

        self.status_var = tk.StringVar(value="Waiting for application to close\u2026")
        tk.Label(
            self.root,
            textvariable=self.status_var,
            bg=self._BG, fg="#eeeeee",
            font=("Segoe UI", 9),
        ).pack()

        self.progress_var = tk.DoubleVar(value=0.0)
        ttk.Progressbar(
            self.root,
            variable=self.progress_var,
            maximum=100,
            length=390,
            mode="determinate",
        ).pack(pady=16)

        # Kick off the update sequence after the window is fully rendered.
        self.root.after(300, self._start)

    # ------------------------------------------------------------------
    # Internal helpers (thread-safe via root.after)
    # ------------------------------------------------------------------

    def _set_status(self, msg: str) -> None:
        self.root.after(0, lambda m=msg: self.status_var.set(m))

    def _set_progress(self, pct: float) -> None:
        self.root.after(0, lambda p=pct: self.progress_var.set(p))

    def _progress_hook(self, count: int, block_size: int, total_size: int) -> None:
        if total_size > 0:
            pct = min(100.0, count * block_size / total_size * 100.0)
            self._set_progress(pct)

    def _start(self) -> None:
        threading.Thread(target=self._run_update, daemon=True).start()

    # ------------------------------------------------------------------
    # Update sequence (runs on background thread)
    # ------------------------------------------------------------------

    def _run_update(self) -> None:
        try:
            # Step 1 – wait for main app to fully exit
            self._set_status("Waiting for application to close\u2026")
            _wait_for_pid(self.main_pid, timeout_s=30)
            time.sleep(0.8)  # small extra buffer for file handles to release

            # Step 2 – download the zip
            self._set_status("Downloading update\u2026")
            tmp_zip = os.path.join(tempfile.gettempdir(), "fkc_update.zip")
            urllib.request.urlretrieve(self.url, tmp_zip, self._progress_hook)
            self._set_progress(100.0)

            # Step 3 – extract FinalsKillCounter.exe from the zip
            self._set_status("Installing update\u2026")
            target_dir = os.path.dirname(self.target_exe)
            extracted = False
            with zipfile.ZipFile(tmp_zip, "r") as z:
                for member in z.namelist():
                    if member.lower().endswith("finalskillcounter.exe"):
                        new_data = z.read(member)
                        extracted = True
                        break

            try:
                os.remove(tmp_zip)
            except OSError:
                pass

            if not extracted:
                raise RuntimeError(
                    "FinalsKillCounter.exe was not found inside the downloaded archive.\n"
                    "Please update manually."
                )

            # Rename the old EXE out of the way first (Windows allows renaming
            # a just-exited executable before its file lock fully releases),
            # write the new binary, then delete the old copy.
            old_exe = self.target_exe + ".old"
            try:
                if os.path.exists(old_exe):
                    os.remove(old_exe)
                os.rename(self.target_exe, old_exe)
            except OSError as e:
                raise RuntimeError(
                    f"Could not move the old executable:\n{e}\n\n"
                    "Make sure FinalsKillCounter.exe has fully closed and try again."
                ) from e

            try:
                with open(self.target_exe, "wb") as out:
                    out.write(new_data)
            except OSError:
                # Restore the old EXE so the app is still runnable
                try:
                    os.rename(old_exe, self.target_exe)
                except OSError:
                    pass
                raise

            # Clean up the old copy (best-effort)
            try:
                os.remove(old_exe)
            except OSError:
                pass

            # Step 4 – persist the new version in fkc_update_state.json
            state_path = os.path.join(target_dir, 'fkc_update_state.json')
            try:
                try:
                    with open(state_path, 'r', encoding='utf-8') as f:
                        state = json.load(f)
                except Exception:
                    state = {}
                state['version'] = self.new_version
                # Remove any old 'declined' entry so the new version is a clean slate.
                state.pop('declined', None)
                with open(state_path, 'w', encoding='utf-8') as f:
                    json.dump(state, f, indent=2)
            except Exception as e:
                print(f'[updater] Could not write update state: {e}')

            # Step 5 – re-launch the updated application
            self._set_status("Update complete! Restarting\u2026")
            time.sleep(0.8)
            subprocess.Popen([self.target_exe], cwd=target_dir)
            self.root.after(0, self.root.destroy)

        except Exception as exc:
            self.root.after(0, lambda e=str(exc): self._show_error(e))

    def _show_error(self, msg: str) -> None:
        # Allow the user to close the window once an error is shown.
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        messagebox.showerror(
            "Update Failed",
            f"The update could not be completed:\n\n{msg}\n\n"
            "Please download the latest version manually from GitHub.",
        )
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # When frozen with console=False, stdout/stderr are None which crashes
    # argparse on any error message.  Redirect to devnull before parsing.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w')

    parser = argparse.ArgumentParser(description="FKC auto-updater (internal use)")
    parser.add_argument("--url",     required=True,        help="Download URL of the update ZIP")
    parser.add_argument("--target",  required=True,        help="Absolute path to FinalsKillCounter.exe")
    parser.add_argument("--pid",     required=True, type=int, help="PID of the running FKC process")
    parser.add_argument("--version", required=True,        help="New version tag being installed")

    try:
        args = parser.parse_args()
    except SystemExit:
        messagebox.showerror(
            "Updater Error",
            "updater.exe was launched with missing or invalid arguments.\n"
            "It should only be invoked by FinalsKillCounter.exe automatically.",
        )
        return

    app = UpdaterApp(url=args.url, target_exe=args.target, main_pid=args.pid, new_version=args.version)
    app.run()


if __name__ == "__main__":
    main()
