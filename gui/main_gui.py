#!/usr/bin/env python3
"""
GUI Control Panel for Xinmeng M87 Linux RGB
Built with PyQt5. Shows all effects with colour pickers, sliders,
live music-sync toggle, and device status.

Requires: pip install PyQt5
"""

import sys
import threading
from typing import Optional

try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QGroupBox, QPushButton, QLabel, QSlider, QComboBox, QColorDialog,
        QStatusBar, QTabWidget, QSpinBox, QCheckBox, QTextEdit,
        QGridLayout, QFrame,
    )
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
    from PyQt5.QtGui import QColor, QPalette, QFont, QIcon
    HAVE_PYQT5 = True
except ImportError:
    HAVE_PYQT5 = False

# Import our backend modules
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

try:
    from src.detect import run_detection, get_saved_device
    from src.rgb_effects import apply_effect, EFFECT_REGISTRY, EFFECT_DESCRIPTIONS
    from src.hid_sender import send_command, build_turn_off
    from src.music_sync import MusicSyncEngine, list_audio_devices
    import sounddevice as sd
    HAVE_AUDIO = True
except Exception:
    HAVE_AUDIO = False


# ---------------------------------------------------------------------------
# Worker thread for music sync (keeps GUI responsive)
# ---------------------------------------------------------------------------

if HAVE_PYQT5:
    class MusicSyncWorker(QThread):
        status_update = pyqtSignal(str)

        def __init__(self, engine: "MusicSyncEngine"):
            super().__init__()
            self.engine = engine

        def run(self):
            self.engine.start()

        def stop(self):
            self.engine.stop()
            self.quit()

    # ---------------------------------------------------------------------------
    # Colour swatch button
    # ---------------------------------------------------------------------------

    class ColourButton(QPushButton):
        def __init__(self, colour: QColor = None):
            super().__init__()
            self.setFixedSize(36, 36)
            self._colour = colour or QColor(255, 255, 255)
            self._update_style()

        def _update_style(self):
            c = self._colour
            self.setStyleSheet(
                f"background-color: rgb({c.red()},{c.green()},{c.blue()});"
                f"border: 2px solid #888; border-radius: 4px;"
            )

        @property
        def colour(self) -> QColor:
            return self._colour

        def set_colour(self, c: QColor):
            self._colour = c
            self._update_style()

        def pick_colour(self):
            new = QColorDialog.getColor(self._colour, self, "Pick Colour")
            if new.isValid():
                self.set_colour(new)


    # ---------------------------------------------------------------------------
    # Main Window
    # ---------------------------------------------------------------------------

    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Xinmeng M87 – Linux RGB Control")
            self.setMinimumSize(680, 520)
            self._music_worker: Optional[MusicSyncWorker] = None
            self._vid: Optional[int] = None
            self._pid: Optional[int] = None
            self._load_device()
            self._build_ui()

        def _load_device(self):
            devices = get_saved_device()
            if devices:
                self._vid = devices[0]["vid"]
                self._pid = devices[0]["pid"]

        def _build_ui(self):
            central = QWidget()
            self.setCentralWidget(central)
            layout = QVBoxLayout(central)
            layout.setContentsMargins(12, 12, 12, 12)

            # ── Header ──────────────────────────────────────────────────────
            hdr = QLabel("🎹  Xinmeng M87 Linux RGB Control")
            hdr.setFont(QFont("Sans", 14, QFont.Bold))
            hdr.setAlignment(Qt.AlignCenter)
            layout.addWidget(hdr)

            # Device status bar
            self._status_lbl = QLabel()
            self._update_device_label()
            self._status_lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(self._status_lbl)

            detect_btn = QPushButton("🔍  Detect Keyboard")
            detect_btn.clicked.connect(self._on_detect)
            layout.addWidget(detect_btn)

            # ── Tabs ────────────────────────────────────────────────────────
            tabs = QTabWidget()
            layout.addWidget(tabs)

            tabs.addTab(self._build_effects_tab(), "🌈  Effects")
            tabs.addTab(self._build_music_tab(),   "🎵  Music Sync")
            tabs.addTab(self._build_custom_tab(),  "✏️  Custom")

            # ── Status bar ──────────────────────────────────────────────────
            self.statusBar().showMessage("Ready")

        def _update_device_label(self):
            if self._vid and self._pid:
                self._status_lbl.setText(
                    f"✅  Keyboard: VID=0x{self._vid:04X}  PID=0x{self._pid:04X}"
                )
                self._status_lbl.setStyleSheet("color: green;")
            else:
                self._status_lbl.setText("⚠️  Keyboard not detected. Click 'Detect Keyboard'.")
                self._status_lbl.setStyleSheet("color: orange;")

        def _on_detect(self):
            self.statusBar().showMessage("Detecting keyboard…")
            devices = run_detection(save=True)
            if devices:
                self._vid = devices[0]["vid"]
                self._pid = devices[0]["pid"]
                self._update_device_label()
                self.statusBar().showMessage(
                    f"Found keyboard: VID=0x{self._vid:04X} PID=0x{self._pid:04X}"
                )
            else:
                self.statusBar().showMessage("Keyboard not found.")

        # ── Effects tab ─────────────────────────────────────────────────────

        def _build_effects_tab(self) -> QWidget:
            w = QWidget()
            layout = QVBoxLayout(w)

            # Colour picker
            clr_box = QGroupBox("Colour")
            clr_layout = QHBoxLayout(clr_box)
            self._colour_btn = ColourButton(QColor(255, 0, 128))
            self._colour_btn.clicked.connect(self._colour_btn.pick_colour)
            clr_layout.addWidget(QLabel("Click to pick:"))
            clr_layout.addWidget(self._colour_btn)
            clr_layout.addStretch()

            # Preset colours
            presets = [
                ("Red",    QColor(255, 0, 0)),
                ("Green",  QColor(0, 255, 0)),
                ("Blue",   QColor(0, 0, 255)),
                ("White",  QColor(255, 255, 255)),
                ("Cyan",   QColor(0, 255, 255)),
                ("Purple", QColor(128, 0, 255)),
            ]
            for name, col in presets:
                btn = QPushButton()
                btn.setFixedSize(24, 24)
                btn.setStyleSheet(
                    f"background-color: rgb({col.red()},{col.green()},{col.blue()});"
                    f"border: 1px solid #666; border-radius: 3px;"
                )
                btn.setToolTip(name)
                btn.clicked.connect(lambda checked, c=col: self._colour_btn.set_colour(c))
                clr_layout.addWidget(btn)

            layout.addWidget(clr_box)

            # Speed / Brightness
            ctrl_box = QGroupBox("Controls")
            ctrl_layout = QGridLayout(ctrl_box)
            ctrl_layout.addWidget(QLabel("Speed (0=fast, 4=slow):"), 0, 0)
            self._speed_spin = QSpinBox()
            self._speed_spin.setRange(0, 4)
            self._speed_spin.setValue(2)
            ctrl_layout.addWidget(self._speed_spin, 0, 1)
            ctrl_layout.addWidget(QLabel("Brightness (0=off, 4=full):"), 1, 0)
            self._bright_spin = QSpinBox()
            self._bright_spin.setRange(0, 4)
            self._bright_spin.setValue(4)
            ctrl_layout.addWidget(self._bright_spin, 1, 1)
            layout.addWidget(ctrl_box)

            # Effect buttons
            eff_box = QGroupBox("Effects")
            eff_layout = QGridLayout(eff_box)
            col = 0
            row = 0
            for name, desc in EFFECT_DESCRIPTIONS.items():
                btn = QPushButton(name.capitalize())
                btn.setToolTip(desc)
                btn.clicked.connect(lambda checked, n=name: self._apply_effect(n))
                eff_layout.addWidget(btn, row, col)
                col += 1
                if col >= 3:
                    col = 0
                    row += 1
            layout.addWidget(eff_box)

            # Off button
            off_btn = QPushButton("⬛  Turn Off")
            off_btn.setStyleSheet("background-color: #333; color: white;")
            off_btn.clicked.connect(lambda: self._apply_effect("off"))
            layout.addWidget(off_btn)

            layout.addStretch()
            return w

        def _apply_effect(self, name: str):
            c = self._colour_btn.colour
            r, g, b = c.red(), c.green(), c.blue()
            speed = self._speed_spin.value()
            bright = self._bright_spin.value()
            self.statusBar().showMessage(f"Applying effect: {name}…")
            ok = apply_effect(name, r=r, g=g, b=b,
                              speed=speed, brightness=bright,
                              vid=self._vid, pid=self._pid)
            if ok:
                self.statusBar().showMessage(f"✓ Effect applied: {name}")
            else:
                self.statusBar().showMessage("⚠ Failed to apply effect (is keyboard connected?)")

        # ── Music Sync tab ───────────────────────────────────────────────────

        def _build_music_tab(self) -> QWidget:
            w = QWidget()
            layout = QVBoxLayout(w)

            if not HAVE_AUDIO:
                layout.addWidget(QLabel(
                    "⚠ sounddevice / numpy not installed.\n"
                    "Run:  pip install sounddevice numpy"
                ))
                return w

            # Device selector
            dev_box = QGroupBox("Audio Input Device")
            dev_layout = QHBoxLayout(dev_box)
            dev_layout.addWidget(QLabel("Device:"))
            self._audio_combo = QComboBox()
            self._audio_combo.addItem("Default", None)
            try:
                for i, d in enumerate(sd.query_devices()):
                    if d["max_input_channels"] > 0:
                        label = f"[{i}] {d['name']}"
                        self._audio_combo.addItem(label, i)
            except Exception:
                pass
            dev_layout.addWidget(self._audio_combo)
            layout.addWidget(dev_box)

            # Mode
            mode_box = QGroupBox("Colour Mode")
            mode_layout = QHBoxLayout(mode_box)
            self._music_mode = QComboBox()
            self._music_mode.addItems(["rgb", "hue", "fire"])
            mode_layout.addWidget(QLabel("Mode:"))
            mode_layout.addWidget(self._music_mode)
            layout.addWidget(mode_box)

            # Sensitivity
            sens_box = QGroupBox("Beat Sensitivity")
            sens_layout = QHBoxLayout(sens_box)
            self._sens_slider = QSlider(Qt.Horizontal)
            self._sens_slider.setRange(10, 50)
            self._sens_slider.setValue(15)
            self._sens_val_lbl = QLabel("1.5")
            self._sens_slider.valueChanged.connect(
                lambda v: self._sens_val_lbl.setText(f"{v/10:.1f}")
            )
            sens_layout.addWidget(QLabel("Low"))
            sens_layout.addWidget(self._sens_slider)
            sens_layout.addWidget(QLabel("High"))
            sens_layout.addWidget(self._sens_val_lbl)
            layout.addWidget(sens_box)

            # Start / Stop
            btn_row = QHBoxLayout()
            self._music_start_btn = QPushButton("▶  Start Music Sync")
            self._music_start_btn.setStyleSheet("background: #1a8a1a; color: white; padding: 6px;")
            self._music_start_btn.clicked.connect(self._toggle_music)
            btn_row.addWidget(self._music_start_btn)
            layout.addLayout(btn_row)

            layout.addWidget(QLabel(
                "Tip: To sync to music playback (not microphone),\n"
                "select a 'Monitor of ...' audio device above.\n"
                "Install pavucontrol for easy device management."
            ))

            layout.addStretch()
            return w

        def _toggle_music(self):
            if self._music_worker and self._music_worker.isRunning():
                self._music_worker.stop()
                self._music_worker = None
                self._music_start_btn.setText("▶  Start Music Sync")
                self._music_start_btn.setStyleSheet(
                    "background: #1a8a1a; color: white; padding: 6px;"
                )
                self.statusBar().showMessage("Music sync stopped.")
                return

            dev_idx = self._audio_combo.currentData()
            mode = self._music_mode.currentText()
            sens = self._sens_slider.value() / 10.0
            engine = MusicSyncEngine(
                vid=self._vid, pid=self._pid,
                device=dev_idx, mode=mode, sensitivity=sens
            )
            self._music_worker = MusicSyncWorker(engine)
            self._music_worker.start()
            self._music_start_btn.setText("⏹  Stop Music Sync")
            self._music_start_btn.setStyleSheet(
                "background: #8a1a1a; color: white; padding: 6px;"
            )
            self.statusBar().showMessage("Music sync running…")

        # ── Custom HID tab ───────────────────────────────────────────────────

        def _build_custom_tab(self) -> QWidget:
            w = QWidget()
            layout = QVBoxLayout(w)
            layout.addWidget(QLabel(
                "Send a custom raw HID report.\n"
                "Enter 64 bytes as hex (spaces optional).\n"
                "Use this after analyzing your pcap capture."
            ))
            self._raw_hex_input = QTextEdit()
            self._raw_hex_input.setPlaceholderText(
                "04 01 00 00 ff 00 00 00 ..."
            )
            self._raw_hex_input.setFixedHeight(80)
            self._raw_hex_input.setFont(QFont("Monospace", 10))
            layout.addWidget(self._raw_hex_input)

            send_btn = QPushButton("📤  Send Raw Report")
            send_btn.clicked.connect(self._send_raw)
            layout.addWidget(send_btn)

            layout.addWidget(QLabel("─" * 60))
            layout.addWidget(QLabel(
                "Phase 3 – Analyze a pcap file:\n"
                "Run:  python3 main.py analyze --pcap packets/m87_capture.pcapng\n\n"
                "Phase 4 – Replay captured commands:\n"
                "Run:  python3 main.py replay"
            ))
            layout.addStretch()
            return w

        def _send_raw(self):
            txt = self._raw_hex_input.toPlainText().replace(" ", "").replace("\n", "").replace(":", "")
            try:
                data = bytes.fromhex(txt)
            except ValueError as e:
                self.statusBar().showMessage(f"Invalid hex: {e}")
                return
            ok = send_command([data], vid=self._vid, pid=self._pid)
            if ok:
                self.statusBar().showMessage(f"Sent {len(data)} bytes.")
            else:
                self.statusBar().showMessage("Send failed.")

        def closeEvent(self, event):
            if self._music_worker and self._music_worker.isRunning():
                self._music_worker.stop()
            super().closeEvent(event)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_gui():
    if not HAVE_PYQT5:
        print("[ERROR] PyQt5 not installed. Run:  pip install PyQt5")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Dark palette
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(45, 45, 45))
    palette.setColor(QPalette.WindowText, QColor(220, 220, 220))
    palette.setColor(QPalette.Base, QColor(35, 35, 35))
    palette.setColor(QPalette.AlternateBase, QColor(55, 55, 55))
    palette.setColor(QPalette.Text, QColor(220, 220, 220))
    palette.setColor(QPalette.Button, QColor(55, 55, 55))
    palette.setColor(QPalette.ButtonText, QColor(220, 220, 220))
    palette.setColor(QPalette.Highlight, QColor(80, 120, 200))
    app.setPalette(palette)

    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    run_gui()
