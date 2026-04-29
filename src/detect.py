#!/usr/bin/env python3
"""
Phase 1: Device Detection
Detects Xinmeng M87 / M87 Pro keyboard on Linux using hidapi and pyusb.
Lists all HID interfaces, VID/PID, usage pages, and selects the correct
vendor-specific interface used for RGB control.
"""

import sys
import json

try:
    import hid
except ImportError:
    hid = None

try:
    import usb.core
    import usb.util
except ImportError:
    usb = None

# ---------------------------------------------------------------------------
# Known VID / PID values for Xinmeng / Sinowealth-based M87 keyboards.
# If your keyboard is not listed here, run this script anyway – it will scan
# ALL connected HID devices and show you the candidates.
# ---------------------------------------------------------------------------
KNOWN_DEVICES = [
    {"vid": 0x258A, "pid": 0x002A, "name": "Xinmeng M87 (Sinowealth 0x258A:0x002A)"},
    {"vid": 0x258A, "pid": 0x0049, "name": "Xinmeng M87 Pro (Sinowealth 0x258A:0x0049)"},
    {"vid": 0x258A, "pid": 0x0026, "name": "Xinmeng M87 variant (Sinowealth 0x258A:0x0026)"},
    {"vid": 0x258A, "pid": 0x00C7, "name": "Xinmeng M87 variant (Sinowealth 0x258A:0x00C7)"},
    {"vid": 0x258A, "pid": 0x0033, "name": "Xinmeng M87 variant (Sinowealth 0x258A:0x0033)"},
    {"vid": 0x0416, "pid": 0xC343, "name": "Xinmeng M87 (Winbond/Generalplus 0x0416:0xC343)"},
    {"vid": 0x0416, "pid": 0xC542, "name": "Xinmeng M87 variant (0x0416:0xC542)"},
    {"vid": 0x3151, "pid": 0x4005, "name": "Xinmeng M87 variant (0x3151:0x4005)"},
]

# Vendor-specific HID Usage Page used for raw LED / RGB commands
RGB_USAGE_PAGE = 0xFF00


def check_dependencies() -> bool:
    """Return True if at least one detection library is available."""
    if hid is None and usb is None:
        print("[ERROR] Neither 'hid' (hidapi) nor 'pyusb' is installed.")
        print("  Install with:  pip install hidapi pyusb")
        return False
    return True


# ---------------------------------------------------------------------------
# hidapi-based detection
# ---------------------------------------------------------------------------

def list_all_hid_devices() -> list[dict]:
    """Return a list of every HID device currently visible to the OS."""
    if hid is None:
        return []
    devices = []
    for dev in hid.enumerate():
        devices.append({
            "vid": dev["vendor_id"],
            "pid": dev["product_id"],
            "manufacturer": dev.get("manufacturer_string", ""),
            "product": dev.get("product_string", ""),
            "serial": dev.get("serial_number", ""),
            "usage_page": dev.get("usage_page", 0),
            "usage": dev.get("usage", 0),
            "interface": dev.get("interface_number", -1),
            "path": dev.get("path", b"").decode("utf-8", errors="replace"),
            "release": dev.get("release_number", 0),
        })
    return devices


def find_known_devices() -> list[dict]:
    """Scan HID bus and return only devices matching KNOWN_DEVICES."""
    if hid is None:
        return []
    found = []
    for known in KNOWN_DEVICES:
        for dev in hid.enumerate(known["vid"], known["pid"]):
            found.append({
                **known,
                "usage_page": dev.get("usage_page", 0),
                "usage": dev.get("usage", 0),
                "interface": dev.get("interface_number", -1),
                "path": dev.get("path", b"").decode("utf-8", errors="replace"),
                "product": dev.get("product_string", ""),
                "manufacturer": dev.get("manufacturer_string", ""),
            })
    return found


def find_rgb_interface(vid: int, pid: int) -> dict | None:
    """
    For a given VID/PID, locate the HID interface whose Usage Page is
    0xFF00 (vendor-specific) – that is the one used for RGB control.
    Falls back to the interface with the highest interface number if none
    matches the usage page exactly.
    """
    if hid is None:
        return None
    candidates = []
    for dev in hid.enumerate(vid, pid):
        usage_page = dev.get("usage_page", 0)
        candidates.append(dev)
        if usage_page == RGB_USAGE_PAGE:
            return dev
    # Fallback: interface with highest number (usually vendor-specific)
    if candidates:
        return max(candidates, key=lambda d: d.get("interface_number", -1))
    return None


# ---------------------------------------------------------------------------
# pyusb-based detection (useful when hidapi is not present)
# ---------------------------------------------------------------------------

def list_usb_devices() -> list[dict]:
    """List USB devices using pyusb (does not require hidapi)."""
    if usb is None:
        return []
    devices = []
    for dev in usb.core.find(find_all=True):
        try:
            manufacturer = usb.util.get_string(dev, dev.iManufacturer) if dev.iManufacturer else ""
        except Exception:
            manufacturer = ""
        try:
            product = usb.util.get_string(dev, dev.iProduct) if dev.iProduct else ""
        except Exception:
            product = ""
        devices.append({
            "vid": dev.idVendor,
            "pid": dev.idProduct,
            "manufacturer": manufacturer,
            "product": product,
            "bus": dev.bus,
            "address": dev.address,
        })
    return devices


def find_usb_known_devices() -> list[dict]:
    """Find known devices via pyusb."""
    if usb is None:
        return []
    known_vids = {d["vid"] for d in KNOWN_DEVICES}
    found = []
    for dev in usb.core.find(find_all=True):
        if dev.idVendor in known_vids:
            for known in KNOWN_DEVICES:
                if known["vid"] == dev.idVendor and known["pid"] == dev.idProduct:
                    try:
                        product = usb.util.get_string(dev, dev.iProduct) if dev.iProduct else ""
                    except Exception:
                        product = ""
                    found.append({
                        **known,
                        "product": product,
                        "bus": dev.bus,
                        "address": dev.address,
                    })
    return found


# ---------------------------------------------------------------------------
# Pretty printing helpers
# ---------------------------------------------------------------------------

def _sep(char: str = "─", width: int = 60) -> str:
    return char * width


def print_device_table(devices: list[dict], title: str = "HID Devices") -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    if not devices:
        print("  (none found)")
        return
    for i, d in enumerate(devices):
        print(f"\n  [{i+1}] VID=0x{d['vid']:04X}  PID=0x{d['pid']:04X}")
        if d.get("name"):
            print(f"       Name      : {d['name']}")
        if d.get("manufacturer"):
            print(f"       Mfr       : {d['manufacturer']}")
        if d.get("product"):
            print(f"       Product   : {d['product']}")
        if d.get("interface") is not None and d["interface"] != -1:
            print(f"       Interface : {d['interface']}")
        if d.get("usage_page"):
            print(f"       UsagePage : 0x{d['usage_page']:04X}  Usage=0x{d.get('usage',0):04X}")
        if d.get("path"):
            print(f"       Path      : {d['path']}")
        if d.get("bus"):
            print(f"       Bus/Addr  : {d['bus']}/{d['address']}")


def save_device_info(devices: list[dict], path: str = "detected_device.json") -> None:
    """Save detected device info to JSON for use by other scripts."""
    with open(path, "w") as f:
        json.dump(devices, f, indent=2)
    print(f"\n[✓] Device info saved to: {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_detection(save: bool = True, output_path: str = "detected_device.json") -> list[dict]:
    """
    Full detection routine.
    Returns list of detected device dicts (may be empty if nothing found).
    """
    if not check_dependencies():
        sys.exit(1)

    print("\n" + _sep("═"))
    print("  Xinmeng M87 Linux RGB — Phase 1: Device Detection")
    print(_sep("═"))

    # --- Known device scan (fast path) ---
    print("\n[*] Scanning for known Xinmeng / Sinowealth devices...")
    known_found = find_known_devices()
    if known_found:
        print(f"[✓] Found {len(known_found)} known device interface(s)!")
        print_device_table(known_found, "Known Keyboard Interfaces")
        if save:
            save_device_info(known_found, output_path)
        return known_found

    # --- USB-level scan as fallback ---
    print("[*] No known HID devices found – trying pyusb scan...")
    usb_found = find_usb_known_devices()
    if usb_found:
        print(f"[✓] Found {len(usb_found)} device(s) via USB scan.")
        print_device_table(usb_found, "USB Matches")
        if save:
            save_device_info(usb_found, output_path)
        return usb_found

    # --- Full HID dump so the user can identify their keyboard ---
    print("\n[!] Keyboard not found in known list.")
    print("    Listing ALL connected HID devices so you can identify yours:")
    all_hid = list_all_hid_devices()
    print_device_table(all_hid, "All Connected HID Devices")

    if not all_hid:
        print("\n[!] No HID devices found at all.")
        print("    Make sure the keyboard is plugged in and udev rules are set.")
        print("    You may need to add a udev rule – see README for instructions.")
    else:
        print("\n[!] Identify your keyboard in the list above.")
        print("    Then edit KNOWN_DEVICES in this file to add it.")

    return []


def get_saved_device(path: str = "detected_device.json") -> list[dict] | None:
    """Load previously saved device info."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Xinmeng M87 – Phase 1: Detect keyboard HID device"
    )
    parser.add_argument(
        "--list-all", action="store_true",
        help="List every HID device on the system (not just known ones)"
    )
    parser.add_argument(
        "--save", default="detected_device.json",
        help="Path to save detected device JSON (default: detected_device.json)"
    )
    parser.add_argument(
        "--no-save", action="store_true",
        help="Do not save device info to file"
    )
    args = parser.parse_args()

    if args.list_all:
        devices = list_all_hid_devices()
        print_device_table(devices, "All HID Devices on System")
    else:
        run_detection(save=not args.no_save, output_path=args.save)
