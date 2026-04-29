#!/usr/bin/env python3
"""
Phase 4: Linux HID Command Sender
Opens the M87 keyboard HID device (vendor-specific interface, Usage Page 0xFF00)
and sends raw HID reports.

Supports:
  • Replaying raw bytes from packets/decoded_commands.json (Phase 3 output)
  • Sending individual commands from rgb_effects.py
  • A built-in set of command builders based on common Sinowealth protocol
    (will work once the correct byte structure is confirmed from capture)

Requires: hidapi  (pip install hidapi)
"""

import os
import sys
import json
import time
import struct
import argparse
from typing import Optional

try:
    import hid
    HAVE_HID = True
except ImportError:
    HAVE_HID = False

from .detect import find_rgb_interface, run_detection, KNOWN_DEVICES

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HID_REPORT_SIZE = 64        # bytes per HID report (including Report ID)
SEND_DELAY = 0.02           # seconds between consecutive writes
RGB_USAGE_PAGE = 0xFF00

# ---------------------------------------------------------------------------
# Protocol builder (Sinowealth-style, adjust after packet capture)
# ---------------------------------------------------------------------------
#
# Structure inferred from similar Sinowealth (VID 0x258A) keyboards.
# Byte layout (64 bytes total):
#   [0]        Report ID (usually 0x04 or 0x08)
#   [1]        Command code
#   [2]        Sub-command / mode
#   [3..N]     Parameters
#   rest       0x00 padding
#
# This is a BEST-GUESS until you capture real packets with Phase 2/3.
# ---------------------------------------------------------------------------

REPORT_ID = 0x04            # Common report ID – update after capture

# Command codes (guesses based on similar keyboards)
CMD_SET_MODE       = 0x01
CMD_SET_COLOUR     = 0x02
CMD_SET_SPEED      = 0x03
CMD_SET_BRIGHTNESS = 0x04
CMD_COMMIT         = 0x09   # "apply" – some keyboards need this
CMD_CUSTOM_DATA    = 0x10   # For per-key RGB data

# Mode codes
MODE_STATIC      = 0x00
MODE_BREATHING   = 0x01
MODE_WAVE        = 0x02
MODE_REACTIVE    = 0x03
MODE_RIPPLE      = 0x04
MODE_NEON        = 0x05
MODE_FLICKER     = 0x06
MODE_STARLIGHT   = 0x07
MODE_OFF         = 0xFF


def _make_report(cmd: int, sub: int, params: bytes = b"") -> bytes:
    """Build a 64-byte HID report with padding."""
    payload = bytes([REPORT_ID, cmd, sub]) + params
    if len(payload) > HID_REPORT_SIZE:
        payload = payload[:HID_REPORT_SIZE]
    return payload.ljust(HID_REPORT_SIZE, b"\x00")


def build_set_mode(mode: int, r: int = 255, g: int = 255, b: int = 255) -> bytes:
    """Command: set RGB mode with optional base colour."""
    return _make_report(CMD_SET_MODE, mode, bytes([r, g, b]))


def build_set_colour(r: int, g: int, b: int) -> bytes:
    """Command: set static colour."""
    return _make_report(CMD_SET_COLOUR, 0x00, bytes([r, g, b]))


def build_set_brightness(level: int) -> bytes:
    """
    Set brightness.
    level: 0 (off) – 4 (full), or 0–255 if single-byte range is accepted.
    """
    return _make_report(CMD_SET_BRIGHTNESS, 0x00, bytes([level & 0xFF]))


def build_set_speed(speed: int) -> bytes:
    """Set animation speed. speed: 0 (fast) – 4 (slow), or 0–255."""
    return _make_report(CMD_SET_SPEED, 0x00, bytes([speed & 0xFF]))


def build_commit() -> bytes:
    """Commit/apply changes."""
    return _make_report(CMD_COMMIT, 0x00)


def build_turn_off() -> bytes:
    """Turn all lights off."""
    return _make_report(CMD_SET_MODE, MODE_OFF)


# ---------------------------------------------------------------------------
# Device opener
# ---------------------------------------------------------------------------

class M87HIDDevice:
    """Context manager that opens and holds the M87 HID device handle."""

    def __init__(self, vid: int, pid: int, usage_page: int = RGB_USAGE_PAGE):
        self.vid = vid
        self.pid = pid
        self.usage_page = usage_page
        self._dev: Optional[hid.Device] = None
        self._path: Optional[bytes] = None

    def _find_path(self) -> Optional[bytes]:
        """Find the HID interface path for the RGB control interface."""
        if not HAVE_HID:
            return None
        candidates = list(hid.enumerate(self.vid, self.pid))
        # Prefer vendor-specific usage page
        for d in candidates:
            if d.get("usage_page") == self.usage_page:
                return d["path"]
        # Fallback: highest interface number
        if candidates:
            best = max(candidates, key=lambda d: d.get("interface_number", -1))
            return best["path"]
        return None

    def open(self) -> bool:
        """Open the device. Returns True on success."""
        if not HAVE_HID:
            print("[ERROR] 'hid' library not installed. Run: pip install hidapi")
            return False
        self._path = self._find_path()
        if not self._path:
            print(f"[ERROR] Device VID=0x{self.vid:04X} PID=0x{self.pid:04X} not found.")
            print("        Run  python3 main.py detect  first.")
            return False
        try:
            self._dev = hid.Device(path=self._path)
            print(f"[✓] Opened: {self._path.decode('utf-8', errors='replace')}")
            return True
        except OSError as e:
            if "Permission denied" in str(e):
                print(f"[ERROR] Permission denied. Add udev rule (see README) or run with sudo.")
            else:
                print(f"[ERROR] Cannot open HID device: {e}")
            return False

    def close(self) -> None:
        if self._dev:
            try:
                self._dev.close()
            except Exception:
                pass
            self._dev = None

    def send(self, report: bytes) -> bool:
        """Send a HID report (64 bytes). Returns True on success."""
        if not self._dev:
            return False
        if len(report) < HID_REPORT_SIZE:
            report = report.ljust(HID_REPORT_SIZE, b"\x00")
        try:
            # hid.Device.write() prepends a 0x00 byte on some platforms
            # (null report ID prepend for devices with only one report ID).
            # If your device needs a leading 0x00, use: b"\x00" + report
            written = self._dev.write(report)
            return written > 0
        except Exception as e:
            print(f"[ERROR] Write failed: {e}")
            return False

    def send_all(self, reports: list[bytes], delay: float = SEND_DELAY) -> int:
        """Send multiple reports with delay between them. Returns count sent."""
        sent = 0
        for report in reports:
            if self.send(report):
                sent += 1
            time.sleep(delay)
        return sent

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()


# ---------------------------------------------------------------------------
# High-level send functions
# ---------------------------------------------------------------------------

def get_device_from_json(path: str = "detected_device.json") -> Optional[tuple[int, int]]:
    """Load VID/PID from the detection JSON file."""
    try:
        with open(path) as f:
            data = json.load(f)
        if data:
            return data[0]["vid"], data[0]["pid"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        pass
    return None


def send_command(
    reports: list[bytes],
    vid: Optional[int] = None,
    pid: Optional[int] = None,
    device_json: str = "detected_device.json",
) -> bool:
    """
    Send one or more HID reports to the M87 keyboard.
    VID/PID can be provided directly or loaded from detected_device.json.
    """
    if vid is None or pid is None:
        result = get_device_from_json(device_json)
        if result is None:
            print("[ERROR] No device info found. Run 'python3 main.py detect' first.")
            return False
        vid, pid = result

    with M87HIDDevice(vid, pid) as dev:
        if not dev._dev:
            return False
        count = dev.send_all(reports)
        print(f"[✓] Sent {count}/{len(reports)} report(s)")
        return count == len(reports)


def replay_from_json(
    commands_json: str = "packets/decoded_commands.json",
    label_filter: Optional[str] = None,
    vid: Optional[int] = None,
    pid: Optional[int] = None,
) -> bool:
    """Replay captured commands from Phase 3 output JSON."""
    if not os.path.exists(commands_json):
        print(f"[ERROR] Commands file not found: {commands_json}")
        print("        Run Phase 3 first: python3 main.py analyze --pcap <file>")
        return False

    with open(commands_json) as f:
        commands = json.load(f)

    if label_filter:
        commands = [c for c in commands if label_filter in c.get("label", "")]
        print(f"[*] Filtered to {len(commands)} command(s) matching '{label_filter}'")

    if not commands:
        print("[!] No commands to replay.")
        return False

    reports = [bytes(c["bytes"]) for c in commands]
    print(f"[*] Replaying {len(reports)} command(s)...")
    return send_command(reports, vid=vid, pid=pid)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Xinmeng M87 – Phase 4: Send HID commands"
    )
    sub = parser.add_subparsers(dest="action", required=True)

    # replay subcommand
    replay_p = sub.add_parser("replay", help="Replay commands from decoded_commands.json")
    replay_p.add_argument("--json", default="packets/decoded_commands.json")
    replay_p.add_argument("--label", help="Filter by label substring")
    replay_p.add_argument("--vid", type=lambda x: int(x, 0))
    replay_p.add_argument("--pid", type=lambda x: int(x, 0))

    # send subcommand (raw bytes)
    send_p = sub.add_parser("send", help="Send a raw hex report")
    send_p.add_argument("hex", help="Hex bytes, e.g. 04010000ff0000")
    send_p.add_argument("--vid", type=lambda x: int(x, 0))
    send_p.add_argument("--pid", type=lambda x: int(x, 0))

    # test subcommand
    test_p = sub.add_parser("test", help="Send a built-in test sequence")
    test_p.add_argument("--vid", type=lambda x: int(x, 0))
    test_p.add_argument("--pid", type=lambda x: int(x, 0))

    args = parser.parse_args()

    if args.action == "replay":
        replay_from_json(args.json, args.label, args.vid, args.pid)

    elif args.action == "send":
        try:
            data = bytes.fromhex(args.hex.replace(" ", "").replace(":", ""))
        except ValueError as e:
            print(f"[ERROR] Invalid hex: {e}")
            sys.exit(1)
        send_command([data], args.vid, args.pid)

    elif args.action == "test":
        print("[*] Sending test sequence: RED → GREEN → BLUE → OFF")
        cmds = [
            build_set_colour(255, 0, 0),
            build_commit(),
        ]
        send_command(cmds, args.vid, args.pid)
        time.sleep(1)
        cmds = [build_set_colour(0, 255, 0), build_commit()]
        send_command(cmds, args.vid, args.pid)
        time.sleep(1)
        cmds = [build_set_colour(0, 0, 255), build_commit()]
        send_command(cmds, args.vid, args.pid)
        time.sleep(1)
        cmds = [build_turn_off()]
        send_command(cmds, args.vid, args.pid)
