#!/usr/bin/env python3
"""
xinmeng_rgb_gui.py
==================
Graphical user interface for the Xinmeng M87 / M87 Pro Linux RGB controller.

Requires:
  - python3-tk   (sudo apt install python3-tk)
  - ./xinmeng_rgb binary (built with: make)

Launch:
  python3 xinmeng_rgb_gui.py
  or:
  ./xinmeng_rgb_gui.py
"""

import os
import sys
import json
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, colorchooser, messagebox

# ---------------------------------------------------------------------------
# Locate the xinmeng_rgb binary next to this script
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BINARY = os.path.join(SCRIPT_DIR, "xinmeng_rgb")
DEVICE_JSON = os.path.join(SCRIPT_DIR, "detected_device.json")

# ---------------------------------------------------------------------------
# Effect definitions (name, description, uses colour, uses speed)
# ---------------------------------------------------------------------------
EFFECTS = [
    {"id": "static",    "label": "Static",    "desc": "Solid single colour",           "colour": True,  "speed": False},
    {"id": "breathing", "label": "Breathing", "desc": "Fade in / out on a colour",     "colour": True,  "speed": True},
    {"id": "wave",      "label": "Wave",      "desc": "Rainbow wave across keyboard",  "colour": False, "speed": True},
    {"id": "rainbow",   "label": "Rainbow",   "desc": "Full-spectrum colour cycle",    "colour": False, "speed": True},
    {"id": "reactive",  "label": "Reactive",  "desc": "Lights up on keypress",         "colour": True,  "speed": True},
    {"id": "ripple",    "label": "Ripple",    "desc": "Ripple from keypress",          "colour": True,  "speed": True},
    {"id": "neon",      "label": "Neon",      "desc": "Neon colour shift",             "colour": False, "speed": True},
    {"id": "starlight", "label": "Starlight", "desc": "Random twinkling",             "colour": True,  "speed": True},
    {"id": "off",       "label": "Off",       "desc": "All lights off",               "colour": False, "speed": False},
]

# ---------------------------------------------------------------------------
# Colour theme
# ---------------------------------------------------------------------------
BG        = "#1e1e2e"   # main background
BG2       = "#2a2a3e"   # panel background
BG3       = "#313145"   # card background
ACCENT    = "#7c6af7"   # purple accent
ACCENT2   = "#5a4fcf"   # darker accent (hover)
FG        = "#cdd6f4"   # main text
FG2       = "#a6adc8"   # secondary text
SUCCESS   = "#a6e3a1"   # green
ERROR     = "#f38ba8"   # red
WARNING   = "#fab387"   # orange
BTN_FG    = "#ffffff"


# ---------------------------------------------------------------------------
# Helper: run xinmeng_rgb subprocess
# ---------------------------------------------------------------------------
def run_binary(args: list[str], timeout: int = 10) -> tuple[bool, str]:
    """Run ./xinmeng_rgb with the given args. Returns (ok, output)."""
    if not os.path.isfile(BINARY):
        return False, f"Binary not found: {BINARY}\nRun 'make' first."
    try:
        result = subprocess.run(
            [BINARY] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (result.stdout + result.stderr).strip()
        return result.returncode == 0, out
    except subprocess.TimeoutExpired:
        return False, "Command timed out."
    except Exception as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------
class RGBApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Xinmeng M87 – RGB Controller")
        self.resizable(False, False)
        self.configure(bg=BG)

        # State
        self._colour_hex = "#ff0000"    # currently selected colour
        self._effect_idx = tk.IntVar(value=0)
        self._speed_var  = tk.IntVar(value=2)
        self._bright_var = tk.IntVar(value=4)
        self._device_ok  = False

        self._build_ui()
        self._center_window()

        # Detect keyboard on startup (background thread)
        self.after(200, lambda: threading.Thread(target=self._detect_keyboard,
                                                 daemon=True).start())

    # ------------------------------------------------------------------ layout

    def _build_ui(self):
        pad = dict(padx=14, pady=8)

        # ── Title bar ───────────────────────────────────────────────────────
        title_frame = tk.Frame(self, bg=ACCENT, pady=10)
        title_frame.pack(fill="x")

        tk.Label(title_frame, text="⌨  Xinmeng M87 RGB Controller",
                 bg=ACCENT, fg=BTN_FG,
                 font=("Segoe UI", 15, "bold")).pack()
        tk.Label(title_frame, text="Linux Edition",
                 bg=ACCENT, fg="#d0ccff",
                 font=("Segoe UI", 9)).pack()

        # ── Main content area ────────────────────────────────────────────────
        content = tk.Frame(self, bg=BG, padx=16, pady=10)
        content.pack(fill="both", expand=True)

        # -- Device status row -----------------------------------------------
        dev_frame = tk.Frame(content, bg=BG2, bd=0, relief="flat")
        dev_frame.pack(fill="x", pady=(0, 10))
        dev_frame.configure(highlightbackground=BG3, highlightthickness=1)

        inner = tk.Frame(dev_frame, bg=BG2, padx=12, pady=8)
        inner.pack(fill="x")

        tk.Label(inner, text="Keyboard Status", bg=BG2, fg=FG2,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")

        row = tk.Frame(inner, bg=BG2)
        row.pack(fill="x", pady=(4, 0))

        self._dev_dot   = tk.Label(row, text="●", bg=BG2, fg=WARNING,
                                   font=("Segoe UI", 12))
        self._dev_dot.pack(side="left")

        self._dev_label = tk.Label(row, text="Detecting…", bg=BG2, fg=FG2,
                                   font=("Segoe UI", 10))
        self._dev_label.pack(side="left", padx=(4, 0))

        self._detect_btn = self._make_button(row, "Re-detect",
                                             self._on_detect_click,
                                             small=True)
        self._detect_btn.pack(side="right")

        # -- Effect selection ------------------------------------------------
        eff_outer = tk.LabelFrame(content, text="  RGB Effect  ", bg=BG,
                                  fg=FG2, bd=0,
                                  font=("Segoe UI", 9, "bold"),
                                  relief="groove",
                                  highlightbackground=BG3,
                                  highlightthickness=1)
        eff_outer.pack(fill="x", pady=(0, 10))

        eff_grid = tk.Frame(eff_outer, bg=BG, padx=8, pady=6)
        eff_grid.pack(fill="x")

        self._effect_cards = []
        for idx, eff in enumerate(EFFECTS):
            col = idx % 3
            row_num = idx // 3
            card = self._make_effect_card(eff_grid, idx, eff)
            card.grid(row=row_num, column=col, padx=5, pady=4, sticky="nsew")

        for c in range(3):
            eff_grid.columnconfigure(c, weight=1)

        # -- Colour picker ---------------------------------------------------
        self._colour_frame = tk.Frame(content, bg=BG2, bd=0)
        self._colour_frame.configure(highlightbackground=BG3, highlightthickness=1)
        self._colour_frame.pack(fill="x", pady=(0, 10))

        cf_inner = tk.Frame(self._colour_frame, bg=BG2, padx=12, pady=8)
        cf_inner.pack(fill="x")

        tk.Label(cf_inner, text="Colour", bg=BG2, fg=FG2,
                 font=("Segoe UI", 9, "bold")).grid(row=0, column=0,
                                                    sticky="w", columnspan=3)

        # RGB sliders
        self._r_var = tk.IntVar(value=255)
        self._g_var = tk.IntVar(value=0)
        self._b_var = tk.IntVar(value=0)

        for i, (label, var, colour) in enumerate([
                ("R", self._r_var, "#ff5555"),
                ("G", self._g_var, "#55ff55"),
                ("B", self._b_var, "#5555ff"),
        ]):
            tk.Label(cf_inner, text=label, bg=BG2, fg=colour,
                     font=("Segoe UI", 9, "bold"), width=2).grid(
                row=i+1, column=0, pady=2, sticky="w")

            sl = ttk.Scale(cf_inner, from_=0, to=255, orient="horizontal",
                           variable=var, length=200,
                           command=lambda _v, _var=var: self._on_slider_change())
            sl.grid(row=i+1, column=1, padx=(6, 8), pady=2, sticky="ew")

            val_lbl = tk.Label(cf_inner, textvariable=var, bg=BG2, fg=FG,
                               font=("Segoe UI", 9), width=3, anchor="e")
            val_lbl.grid(row=i+1, column=2, pady=2)

        cf_inner.columnconfigure(1, weight=1)

        # colour preview + picker button
        preview_row = tk.Frame(cf_inner, bg=BG2)
        preview_row.grid(row=4, column=0, columnspan=3, pady=(6, 0), sticky="ew")

        self._preview = tk.Label(preview_row, width=4, bg=self._colour_hex,
                                 relief="solid", bd=1)
        self._preview.pack(side="left")

        self._hex_lbl = tk.Label(preview_row, text=self._colour_hex.upper(),
                                 bg=BG2, fg=FG2, font=("Courier New", 10))
        self._hex_lbl.pack(side="left", padx=8)

        self._make_button(preview_row, "Pick colour…",
                          self._on_pick_colour, small=True).pack(side="right")

        # -- Speed & Brightness ----------------------------------------------
        sb_frame = tk.Frame(content, bg=BG2, bd=0)
        sb_frame.configure(highlightbackground=BG3, highlightthickness=1)
        sb_frame.pack(fill="x", pady=(0, 10))
        self._sb_frame = sb_frame

        sb_inner = tk.Frame(sb_frame, bg=BG2, padx=12, pady=8)
        sb_inner.pack(fill="x")

        tk.Label(sb_inner, text="Speed & Brightness", bg=BG2, fg=FG2,
                 font=("Segoe UI", 9, "bold")).grid(row=0, column=0,
                                                    sticky="w", columnspan=3)

        for i, (label, var, lo, hi, lo_lbl, hi_lbl) in enumerate([
                ("Speed",      self._speed_var,  0, 4, "Slowest", "Fastest"),
                ("Brightness", self._bright_var, 0, 4, "Off",     "Full"),
        ]):
            tk.Label(sb_inner, text=label, bg=BG2, fg=FG,
                     font=("Segoe UI", 9), width=10, anchor="w").grid(
                row=i+1, column=0, pady=4, sticky="w")

            tk.Label(sb_inner, text=lo_lbl, bg=BG2, fg=FG2,
                     font=("Segoe UI", 8)).grid(row=i+1, column=1,
                                                padx=(6, 2), sticky="e")

            sl = ttk.Scale(sb_inner, from_=lo, to=hi, orient="horizontal",
                           variable=var, length=180)
            sl.grid(row=i+1, column=2, padx=4, pady=4)

            tk.Label(sb_inner, text=hi_lbl, bg=BG2, fg=FG2,
                     font=("Segoe UI", 8)).grid(row=i+1, column=3,
                                                padx=(2, 0), sticky="w")

            val_lbl = tk.Label(sb_inner, textvariable=var, bg=BG2, fg=FG,
                               font=("Segoe UI", 9), width=2, anchor="e")
            val_lbl.grid(row=i+1, column=4, padx=(4, 0))

        sb_inner.columnconfigure(2, weight=1)

        # -- Apply button ----------------------------------------------------
        apply_row = tk.Frame(content, bg=BG)
        apply_row.pack(fill="x", pady=(0, 6))

        self._apply_btn = self._make_button(apply_row, "✔  Apply Effect",
                                            self._on_apply, large=True)
        self._apply_btn.pack(fill="x")

        # -- Status bar ------------------------------------------------------
        self._status_var = tk.StringVar(value="Ready.")
        status_bar = tk.Label(self, textvariable=self._status_var,
                              bg=BG3, fg=FG2,
                              font=("Segoe UI", 9),
                              anchor="w", padx=12, pady=4)
        status_bar.pack(fill="x", side="bottom")

        # Initial state update
        self._update_effect_ui()

    # ------------------------------------------------------------------ widgets

    def _make_button(self, parent, text, command,
                     small=False, large=False) -> tk.Button:
        font_size = 8 if small else (12 if large else 10)
        pad_x = 8 if small else (12 if large else 10)
        pad_y = 3 if small else (8 if large else 5)
        return tk.Button(
            parent, text=text, command=command,
            bg=ACCENT, fg=BTN_FG, activebackground=ACCENT2,
            activeforeground=BTN_FG,
            relief="flat", bd=0, cursor="hand2",
            font=("Segoe UI", font_size, "bold"),
            padx=pad_x, pady=pad_y,
        )

    def _make_effect_card(self, parent, idx: int, eff: dict) -> tk.Frame:
        card = tk.Frame(parent, bg=BG3, bd=0, cursor="hand2",
                        relief="solid",
                        highlightbackground=BG3, highlightthickness=2)

        rb = tk.Radiobutton(
            card,
            variable=self._effect_idx,
            value=idx,
            bg=BG3,
            activebackground=BG3,
            selectcolor=BG3,
            bd=0,
            highlightthickness=0,
            command=self._update_effect_ui,
        )
        rb.grid(row=0, column=0, rowspan=2, padx=(6, 0), pady=6)

        tk.Label(card, text=eff["label"], bg=BG3, fg=FG,
                 font=("Segoe UI", 9, "bold")).grid(
            row=0, column=1, sticky="w", padx=(2, 8), pady=(6, 0))

        tk.Label(card, text=eff["desc"], bg=BG3, fg=FG2,
                 font=("Segoe UI", 8), wraplength=110, justify="left").grid(
            row=1, column=1, sticky="w", padx=(2, 8), pady=(0, 6))

        # clicking anywhere on the card selects this effect
        card.bind("<Button-1>", lambda _e, i=idx: self._select_effect(i))

        self._effect_cards.append(card)
        return card

    # ------------------------------------------------------------------ logic

    def _center_window(self):
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"+{x}+{y}")

    def _select_effect(self, idx: int):
        self._effect_idx.set(idx)
        self._update_effect_ui()

    def _update_effect_ui(self):
        idx = self._effect_idx.get()
        eff = EFFECTS[idx]

        # Highlight selected card
        for i, card in enumerate(self._effect_cards):
            hl = ACCENT if i == idx else BG3
            card.configure(highlightbackground=hl)

        # Show/hide colour section
        if eff["colour"]:
            # Re-pack before the speed/brightness frame
            self._colour_frame.pack(fill="x", pady=(0, 10),
                                    before=self._sb_frame)
        else:
            self._colour_frame.pack_forget()

    def _on_slider_change(self):
        r = self._r_var.get()
        g = self._g_var.get()
        b = self._b_var.get()
        self._colour_hex = "#{:02x}{:02x}{:02x}".format(r, g, b)
        self._preview.configure(bg=self._colour_hex)
        self._hex_lbl.configure(text=self._colour_hex.upper())

    def _on_pick_colour(self):
        initial = self._colour_hex if self._colour_hex else "#ff0000"
        result = colorchooser.askcolor(color=initial,
                                       title="Choose RGB colour",
                                       parent=self)
        if result and result[0]:
            r, g, b = (int(x) for x in result[0])
            self._r_var.set(r)
            self._g_var.set(g)
            self._b_var.set(b)
            self._on_slider_change()

    def _detect_keyboard(self):
        self._set_status("Detecting keyboard…")
        ok, out = run_binary(["detect"])
        if ok:
            # Try to read detected device name from JSON
            name = self._read_device_name()
            self._device_ok = True
            self._update_device_label(True, name or "Keyboard detected")
            self._set_status("Keyboard detected and ready.")
        else:
            self._device_ok = False
            self._update_device_label(False, "Keyboard not detected")
            self._set_status("Keyboard not found. Check connection and try Re-detect.", error=True)

    def _read_device_name(self) -> str:
        try:
            with open(DEVICE_JSON) as f:
                data = json.load(f)
            if data and isinstance(data, list):
                return data[0].get("name", "")
        except Exception:
            pass
        return ""

    def _update_device_label(self, ok: bool, text: str):
        colour = SUCCESS if ok else ERROR
        self._dev_dot.configure(fg=colour)
        self._dev_label.configure(text=text)

    def _on_detect_click(self):
        self._update_device_label(False, "Detecting…")
        self._dev_dot.configure(fg=WARNING)
        threading.Thread(target=self._detect_keyboard, daemon=True).start()

    def _on_apply(self):
        idx = self._effect_idx.get()
        eff = EFFECTS[idx]
        args = ["effect", eff["id"]]

        if eff["colour"]:
            r = self._r_var.get()
            g = self._g_var.get()
            b = self._b_var.get()
            args += ["--colour", f"{r},{g},{b}"]

        if eff["speed"]:
            # Map slider 0-4 so that 0 = fastest (as CLI expects)
            speed_val = 4 - self._speed_var.get()  # invert: slider right = faster
            args += ["--speed", str(speed_val)]

        args += ["--brightness", str(self._bright_var.get())]

        self._apply_btn.configure(state="disabled", text="Applying…")
        self._set_status(f"Applying effect: {eff['label']}…")

        threading.Thread(target=self._do_apply, args=(args, eff["label"]),
                         daemon=True).start()

    def _do_apply(self, args: list[str], label: str):
        ok, out = run_binary(args)
        if ok:
            self._set_status(f"✔  {label} applied successfully.")
        else:
            self._set_status(f"✘  Failed: {out}", error=True)
            if "detect" in out.lower() or "not found" in out.lower():
                self.after(0, lambda: messagebox.showerror(
                    "Keyboard not found",
                    "Could not communicate with the keyboard.\n\n"
                    "Please click 'Re-detect' and try again.\n\n"
                    f"Details:\n{out}",
                    parent=self,
                ))
        self.after(0, lambda: self._apply_btn.configure(
            state="normal", text="✔  Apply Effect"))

    def _set_status(self, msg: str, error: bool = False):
        self.after(0, lambda: self._status_var.set(msg))

    # ------------------------------------------------------------------ style

    def _apply_ttk_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Horizontal.TScale",
                        troughcolor=BG3,
                        background=ACCENT,
                        sliderthickness=14)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    # Check Python version
    if sys.version_info < (3, 8):
        print("Python 3.8 or newer is required.", file=sys.stderr)
        sys.exit(1)

    # Check binary exists
    if not os.path.isfile(BINARY):
        print(f"[!] Binary not found at: {BINARY}", file=sys.stderr)
        print("    Please build it first with:  make", file=sys.stderr)
        print("    Or run the installer:         bash install.sh", file=sys.stderr)

    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("[!] tkinter is not installed.", file=sys.stderr)
        print("    Install it with:  sudo apt install python3-tk", file=sys.stderr)
        sys.exit(1)

    app = RGBApp()
    app.mainloop()


if __name__ == "__main__":
    main()
