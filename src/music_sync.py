#!/usr/bin/env python3
"""
Phase 6: Music / Audio Reactive RGB
Listens to the system audio (microphone or loopback) in real-time,
computes energy/frequency features, and sends matching RGB colours
to the M87 keyboard.

Features:
  • Beat detection (low-frequency energy spikes → colour flash)
  • Frequency mapping (bass/mid/treble → R/G/B channels)
  • Smoothing to avoid flickering
  • Adjustable sensitivity and colour palette

Requires:
  pip install sounddevice numpy

Optional (for loopback – capture "what you hear"):
  • PulseAudio / PipeWire "Monitor" source (built into Linux Mint)
  • No extra packages needed; just select the correct device
"""

import sys
import time
import threading
import argparse
import math
import colorsys
from typing import Optional

try:
    import numpy as np
    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False

try:
    import sounddevice as sd
    HAVE_SD = True
except ImportError:
    HAVE_SD = False

from .hid_sender import send_command, build_set_colour, build_commit, get_device_from_json

# ---------------------------------------------------------------------------
# Audio parameters
# ---------------------------------------------------------------------------

SAMPLE_RATE   = 44100    # Hz
BLOCK_SIZE    = 1024     # samples per block (~23 ms latency)
CHANNELS      = 1        # mono
FFT_SIZE      = 2048     # FFT window size

# Frequency bands (Hz)
BASS_RANGE    = (20,   250)
MID_RANGE     = (250,  4000)
TREBLE_RANGE  = (4000, 20000)

# Smoothing (exponential moving average) – 0=no smoothing, 1=never changes
SMOOTH_FACTOR = 0.35

# Scale factor to normalise amplitudes to 0–255
SCALE = 3.0


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def check_dependencies() -> bool:
    ok = True
    if not HAVE_NUMPY:
        print("[ERROR] numpy not installed.  pip install numpy")
        ok = False
    if not HAVE_SD:
        print("[ERROR] sounddevice not installed.  pip install sounddevice")
        ok = False
    return ok


def list_audio_devices() -> None:
    """Print all available audio input devices."""
    if not HAVE_SD:
        print("[ERROR] sounddevice not installed")
        return
    print("\nAvailable audio input devices:")
    print(f"{'─'*60}")
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        if d["max_input_channels"] > 0:
            marker = " ◀ default" if i == sd.default.device[0] else ""
            print(f"  [{i:2d}]  {d['name']}{marker}")
    print(f"\nTip: To capture 'what you hear' (music), pick a Monitor source.")
    print(f"     In Linux Mint, open PulseAudio Volume Control (pavucontrol),")
    print(f"     then record from 'Monitor of ...' device.")


def freq_band_energy(fft_mag: "np.ndarray", freqs: "np.ndarray", lo: float, hi: float) -> float:
    """Return mean FFT magnitude in the given frequency band."""
    mask = (freqs >= lo) & (freqs <= hi)
    if not mask.any():
        return 0.0
    return float(np.mean(fft_mag[mask]))


def energy_to_colour(
    bass: float,
    mid: float,
    treble: float,
    mode: str = "rgb",
) -> tuple[int, int, int]:
    """
    Map frequency band energies to (R, G, B).

    mode="rgb"     → bass→R, mid→G, treble→B
    mode="hue"     → total energy maps brightness, dominant band maps hue
    mode="fire"    → bass drives orange/red palette (nice for beats)
    """
    def clamp255(v: float) -> int:
        return max(0, min(255, int(v)))

    if mode == "rgb":
        r = clamp255(bass   * SCALE * 255)
        g = clamp255(mid    * SCALE * 255)
        b = clamp255(treble * SCALE * 255)
        return r, g, b

    elif mode == "hue":
        total = bass + mid + treble + 1e-9
        if bass >= mid and bass >= treble:
            hue = 0.0       # red
        elif mid >= bass and mid >= treble:
            hue = 0.33      # green
        else:
            hue = 0.66      # blue
        bright = min(1.0, (bass + mid + treble) * SCALE)
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, bright)
        return clamp255(r * 255), clamp255(g * 255), clamp255(b * 255)

    elif mode == "fire":
        # Map bass to warm orange/red
        energy = min(1.0, (bass * 1.5 + mid * 0.3) * SCALE)
        # Orange-red spectrum: hue 0.0 (red) to 0.1 (orange)
        hue = 0.05 * (1 - energy)
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, energy)
        return clamp255(r * 255), clamp255(g * 255), clamp255(b * 255)

    return 0, 0, 0


# ---------------------------------------------------------------------------
# Beat detector
# ---------------------------------------------------------------------------

class BeatDetector:
    """
    Simple onset/beat detector: fires when energy significantly exceeds
    the recent average.
    """

    def __init__(self, history_len: int = 43, sensitivity: float = 1.5):
        # 43 frames ≈ 1 second of history at ~43 Hz (SAMPLE_RATE / BLOCK_SIZE)
        # This gives a rolling 1-second average energy for beat detection.
        self.history_len = history_len
        self.sensitivity = sensitivity
        self._history: list[float] = [0.0] * history_len
        self._ptr = 0

    def update(self, energy: float) -> bool:
        """Returns True if a beat is detected."""
        avg = sum(self._history) / self.history_len if self._history else 0.0
        is_beat = energy > avg * self.sensitivity and energy > 0.01
        self._history[self._ptr] = energy
        self._ptr = (self._ptr + 1) % self.history_len
        return is_beat


# ---------------------------------------------------------------------------
# Music sync engine
# ---------------------------------------------------------------------------

class MusicSyncEngine:
    """
    Captures audio, analyses it, and sends RGB commands to the keyboard.
    Runs the audio callback in a background thread.
    """

    def __init__(
        self,
        vid: Optional[int] = None,
        pid: Optional[int] = None,
        device: Optional[int] = None,
        mode: str = "rgb",
        sensitivity: float = 1.5,
        fps_limit: float = 30.0,
    ):
        self.vid = vid
        self.pid = pid
        self.audio_device = device
        self.mode = mode
        self.beat_detector = BeatDetector(sensitivity=sensitivity)
        self.min_interval = 1.0 / fps_limit

        self._smooth_r = 0.0
        self._smooth_g = 0.0
        self._smooth_b = 0.0
        self._last_send = 0.0
        self._stop_event = threading.Event()
        self._stream: Optional["sd.InputStream"] = None

        # Load VID/PID if not provided
        if self.vid is None or self.pid is None:
            result = get_device_from_json()
            if result:
                self.vid, self.pid = result

    def _audio_callback(
        self,
        indata: "np.ndarray",
        frames: int,
        time_info,
        status,
    ) -> None:
        if status:
            pass  # ignore xruns etc.

        # Compute FFT
        mono = indata[:, 0]
        windowed = mono * np.hanning(len(mono))
        if len(windowed) < FFT_SIZE:
            windowed = np.pad(windowed, (0, FFT_SIZE - len(windowed)))
        fft_result = np.abs(np.fft.rfft(windowed[:FFT_SIZE]))
        freqs = np.fft.rfftfreq(FFT_SIZE, 1.0 / SAMPLE_RATE)
        fft_norm = fft_result / (FFT_SIZE / 2)   # normalise

        # Band energies
        bass   = freq_band_energy(fft_norm, freqs, *BASS_RANGE)
        mid    = freq_band_energy(fft_norm, freqs, *MID_RANGE)
        treble = freq_band_energy(fft_norm, freqs, *TREBLE_RANGE)

        # Beat detection (bass band)
        is_beat = self.beat_detector.update(bass)

        # Map to colour
        r, g, b = energy_to_colour(bass, mid, treble, self.mode)

        # Flash white on beat
        if is_beat:
            r = min(255, r + 80)
            g = min(255, g + 80)
            b = min(255, b + 80)

        # Smooth
        sf = SMOOTH_FACTOR
        self._smooth_r = self._smooth_r * sf + r * (1 - sf)
        self._smooth_g = self._smooth_g * sf + g * (1 - sf)
        self._smooth_b = self._smooth_b * sf + b * (1 - sf)

        # Rate-limit HID sends
        now = time.time()
        if now - self._last_send < self.min_interval:
            return

        self._last_send = now
        if self.vid is None or self.pid is None:
            return

        sr = int(self._smooth_r)
        sg = int(self._smooth_g)
        sb = int(self._smooth_b)

        reports = [build_set_colour(sr, sg, sb), build_commit()]
        try:
            send_command(reports, vid=self.vid, pid=self.pid)
        except Exception:
            pass

    def start(self) -> None:
        """Start audio capture and RGB sync."""
        if not check_dependencies():
            return

        if self.vid is None or self.pid is None:
            print("[ERROR] Keyboard not detected. Run 'python3 main.py detect' first.")
            return

        print(f"\n[✓] Music Sync started")
        print(f"    Device  : {self.audio_device or 'default'}")
        print(f"    Mode    : {self.mode}")
        print(f"    VID/PID : 0x{self.vid:04X} / 0x{self.pid:04X}")
        print(f"\n    Press Ctrl+C to stop.\n")

        try:
            self._stream = sd.InputStream(
                device=self.audio_device,
                samplerate=SAMPLE_RATE,
                blocksize=BLOCK_SIZE,
                channels=CHANNELS,
                dtype="float32",
                callback=self._audio_callback,
            )
            with self._stream:
                while not self._stop_event.is_set():
                    time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n[*] Stopped by user.")
        except Exception as e:
            print(f"[ERROR] Audio stream error: {e}")
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the engine."""
        self._stop_event.set()
        if self._stream and not self._stream.closed:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Xinmeng M87 – Phase 6: Music-reactive RGB"
    )
    parser.add_argument(
        "--list-devices", action="store_true",
        help="List available audio input devices and exit"
    )
    parser.add_argument(
        "--device", "-d", type=int,
        help="Audio input device index (use --list-devices to find it)"
    )
    parser.add_argument(
        "--mode", choices=["rgb", "hue", "fire"], default="rgb",
        help="Colour mapping mode: rgb=bass/mid/treble→R/G/B, "
             "hue=dominant band→hue, fire=bass→warm palette (default: rgb)"
    )
    parser.add_argument(
        "--sensitivity", type=float, default=1.5,
        help="Beat detection sensitivity (default: 1.5, higher=less sensitive)"
    )
    parser.add_argument("--vid", type=lambda x: int(x, 0))
    parser.add_argument("--pid", type=lambda x: int(x, 0))

    args = parser.parse_args()

    if args.list_devices:
        list_audio_devices()
        sys.exit(0)

    engine = MusicSyncEngine(
        vid=args.vid,
        pid=args.pid,
        device=args.device,
        mode=args.mode,
        sensitivity=args.sensitivity,
    )
    engine.start()
