#!/usr/bin/env python3
"""
Phase 3: Packet Analysis
Parses a .pcap / .pcapng file captured with USBPcap+Wireshark and extracts
HID interrupt OUT packets sent to the M87 keyboard.

Outputs:
  • Console: hex dump of each unique command
  • packets/decoded_commands.json: structured command list for hid_sender.py

Requires: scapy  (pip install scapy)
          OR pyshark (pip install pyshark) as fallback
"""

import sys
import os
import json
import struct
import argparse
from collections import defaultdict
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Optional dependencies – we try scapy first, then pyshark
# ---------------------------------------------------------------------------
try:
    from scapy.all import rdpcap, PcapReader
    from scapy.layers.usb import USBpcap, USB
    HAVE_SCAPY = True
except ImportError:
    HAVE_SCAPY = False

try:
    import pyshark
    HAVE_PYSHARK = True
except ImportError:
    HAVE_PYSHARK = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def hexdump(data: bytes, width: int = 16) -> str:
    """Return a human-readable hex dump string."""
    lines = []
    for i in range(0, len(data), width):
        chunk = data[i:i+width]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"  {i:04X}: {hex_part:<{width*3}}  {ascii_part}")
    return "\n".join(lines)


def is_hid_out(pkt_data: bytes) -> bool:
    """
    Heuristic: a valid HID report for this keyboard is likely 64 bytes,
    starts with a non-zero byte (report ID), and is not all zeros.
    """
    if len(pkt_data) < 8:
        return False
    if all(b == 0 for b in pkt_data):
        return False
    return True


def label_command(data: bytes) -> str:
    """Attempt to label a command based on known byte patterns."""
    if len(data) < 4:
        return "unknown"
    b0, b1, b2, b3 = data[0], data[1], data[2], data[3]

    # Common Sinowealth / vendor-specific patterns
    labels = {
        # Report ID 0x04 / 0x08 are common for RGB commands
        (0x04, 0x01): "rgb_static_colour",
        (0x04, 0x02): "rgb_effect",
        (0x04, 0x03): "rgb_brightness",
        (0x04, 0x09): "rgb_custom_key",
        (0x08, 0x01): "rgb_mode_select",
        (0x08, 0x02): "rgb_colour_set",
        (0x0B, 0x00): "rgb_commit",
        (0x05, 0x10): "rgb_speed",
        (0x05, 0x11): "rgb_direction",
    }
    key = (b0, b1)
    return labels.get(key, f"cmd_0x{b0:02X}_0x{b1:02X}")


# ---------------------------------------------------------------------------
# Scapy-based parser
# ---------------------------------------------------------------------------

def parse_with_scapy(pcap_path: str, vid_filter: Optional[int] = None) -> list[dict]:
    """Extract HID OUT payloads from a pcap file using Scapy."""
    packets = []
    try:
        cap = rdpcap(pcap_path)
    except Exception as e:
        print(f"[ERROR] Could not read pcap with scapy: {e}")
        return []

    for pkt in cap:
        raw = bytes(pkt)
        if len(raw) < 28:          # USBpcap header is at least 27 bytes
            continue

        # USBpcap header layout (little-endian):
        #  0  WORD  headerLen
        #  2  QWORD irpId
        # 10  DWORD status
        # 14  WORD  function
        # 16  BYTE  info      (bit 0: 0=FDO→PDO (OUT), 1=PDO→FDO (IN))
        # 17  WORD  bus
        # 19  WORD  device
        # 21  BYTE  endpoint
        # 22  BYTE  transfer (0=isochronous,1=interrupt,2=control,3=bulk)
        # 23  DWORD dataLength
        try:
            hdr_len = struct.unpack_from("<H", raw, 0)[0]
            transfer_type = raw[22]
            direction_bit = raw[16] & 0x01
            data_len = struct.unpack_from("<I", raw, 23)[0]
        except struct.error:
            continue

        # We want: interrupt transfer (1) + OUT direction (bit=0)
        if transfer_type != 1 or direction_bit != 0:
            continue

        payload = raw[hdr_len:hdr_len + data_len]
        if not is_hid_out(payload):
            continue

        packets.append({
            "label": label_command(payload),
            "length": len(payload),
            "hex": payload.hex(),
            "bytes": list(payload),
        })

    return packets


# ---------------------------------------------------------------------------
# pyshark-based parser (uses tshark under the hood)
# ---------------------------------------------------------------------------

def parse_with_pyshark(pcap_path: str, vid_filter: Optional[int] = None) -> list[dict]:
    """Extract HID OUT payloads from a pcap file using pyshark."""
    packets = []
    try:
        cap = pyshark.FileCapture(
            pcap_path,
            display_filter="usb.transfer_type == 0x01 && usb.endpoint_address.direction == 0",
            keep_packets=False,
        )
        for pkt in cap:
            try:
                if hasattr(pkt, "usb") and hasattr(pkt.usb, "capdata"):
                    raw_hex = pkt.usb.capdata.replace(":", "")
                    payload = bytes.fromhex(raw_hex)
                    if not is_hid_out(payload):
                        continue
                    packets.append({
                        "label": label_command(payload),
                        "length": len(payload),
                        "hex": payload.hex(),
                        "bytes": list(payload),
                    })
            except Exception:
                continue
        cap.close()
    except Exception as e:
        print(f"[ERROR] pyshark error: {e}")
    return packets


# ---------------------------------------------------------------------------
# Plain binary fallback – no pcap library needed
# ---------------------------------------------------------------------------

def parse_raw_hex_file(path: str) -> list[dict]:
    """
    Fallback parser for a plain text file where each line is a hex string
    (e.g. exported from Wireshark "Export packet bytes as hex").
    Example line:  04 01 ff 00 00 00 00 00 ...
    """
    packets = []
    with open(path) as f:
        for line in f:
            line = line.strip().replace(":", "").replace(" ", "")
            if not line or line.startswith("#"):
                continue
            try:
                payload = bytes.fromhex(line)
                if not is_hid_out(payload):
                    continue
                packets.append({
                    "label": label_command(payload),
                    "length": len(payload),
                    "hex": payload.hex(),
                    "bytes": list(payload),
                })
            except ValueError:
                pass
    return packets


# ---------------------------------------------------------------------------
# Deduplication and grouping
# ---------------------------------------------------------------------------

def deduplicate(packets: list[dict]) -> list[dict]:
    """Remove exact duplicate packets (same hex payload)."""
    seen = set()
    unique = []
    for p in packets:
        if p["hex"] not in seen:
            seen.add(p["hex"])
            unique.append(p)
    return unique


def group_by_label(packets: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for p in packets:
        groups[p["label"]].append(p)
    return dict(groups)


# ---------------------------------------------------------------------------
# Main analysis routine
# ---------------------------------------------------------------------------

def analyze(
    pcap_path: str,
    output_path: str = "packets/decoded_commands.json",
    vid_filter: Optional[int] = None,
    dedupe: bool = True,
    raw_hex: bool = False,
) -> list[dict]:
    """
    Parse pcap file, extract HID packets, print summary and save JSON.
    Returns list of packet dicts.
    """
    print(f"\n{'='*60}")
    print("  Xinmeng M87 Linux RGB — Phase 3: Packet Analysis")
    print(f"{'='*60}")
    print(f"\n[*] Input  : {pcap_path}")
    print(f"[*] Output : {output_path}")

    if not os.path.exists(pcap_path):
        print(f"[ERROR] File not found: {pcap_path}")
        return []

    # Choose parser
    if raw_hex:
        print("[*] Using raw hex text parser")
        packets = parse_raw_hex_file(pcap_path)
    elif HAVE_SCAPY:
        print("[*] Using scapy parser")
        packets = parse_with_scapy(pcap_path, vid_filter)
    elif HAVE_PYSHARK:
        print("[*] Using pyshark parser (requires tshark)")
        packets = parse_with_pyshark(pcap_path, vid_filter)
    else:
        print("[ERROR] Neither scapy nor pyshark is installed.")
        print("  Install with:  pip install scapy")
        print("  Or:            pip install pyshark  (also needs tshark)")
        return []

    print(f"[*] Total HID OUT packets found: {len(packets)}")

    if dedupe:
        packets = deduplicate(packets)
        print(f"[*] Unique packets after dedup: {len(packets)}")

    if not packets:
        print("\n[!] No HID OUT packets found.")
        print("    Possible reasons:")
        print("    • Wrong pcap file (check you captured the right USBPcap interface)")
        print("    • Packets are control transfers, not interrupt – check transfer type")
        print("    • Try exporting packet bytes from Wireshark and use --raw-hex flag")
        return []

    # Print packets grouped by label
    groups = group_by_label(packets)
    print(f"\n{'─'*60}")
    print("  Decoded Commands")
    print(f"{'─'*60}")
    for label, pkts in sorted(groups.items()):
        print(f"\n  ▶ {label}  ({len(pkts)} packet(s))")
        for p in pkts[:3]:      # show max 3 examples per group
            print(f"    [{p['length']} bytes]")
            print(hexdump(bytes(p["bytes"])))

    # Save JSON
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(packets, f, indent=2)
    print(f"\n[✓] Saved {len(packets)} commands → {output_path}")
    print("\n[→] Next step:  python3 main.py send --command <label>")
    return packets


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Xinmeng M87 – Phase 3: Analyse USBPcap capture"
    )
    parser.add_argument("pcap", help="Path to .pcap or .pcapng file (or raw hex text if --raw-hex)")
    parser.add_argument(
        "--output", "-o", default="packets/decoded_commands.json",
        help="Output JSON path (default: packets/decoded_commands.json)"
    )
    parser.add_argument(
        "--vid", type=lambda x: int(x, 0),
        help="Filter by USB Vendor ID (e.g. 0x258A)"
    )
    parser.add_argument(
        "--no-dedupe", action="store_true",
        help="Do not remove duplicate packets"
    )
    parser.add_argument(
        "--raw-hex", action="store_true",
        help="Input is a plain text file with one hex string per line"
    )
    args = parser.parse_args()

    analyze(
        pcap_path=args.pcap,
        output_path=args.output,
        vid_filter=args.vid,
        dedupe=not args.no_dedupe,
        raw_hex=args.raw_hex,
    )
