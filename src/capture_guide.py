#!/usr/bin/env python3
"""
Phase 2: Windows USB Packet Capture Guide
Prints a step-by-step guide for capturing USB HID packets from Windows
using USBPcap + Wireshark while using the official M87 driver.
The captured .pcap/.pcapng file is then analysed by analyze_pcap.py.
"""

import sys
import textwrap

GUIDE = """
╔══════════════════════════════════════════════════════════════════════════════╗
║       Xinmeng M87 Linux RGB — Phase 2: Windows USB Packet Capture Guide     ║
╚══════════════════════════════════════════════════════════════════════════════╝

Why do we need this?
  The Xinmeng M87 uses a proprietary HID protocol for RGB control. The Windows
  driver knows this protocol, but the specification is not public.  We capture
  USB packets sent by the official driver on Windows, then replay the same bytes
  on Linux.

═══════════════════════════════════════════════════════════════════════════════
STEP 0 – What you need (Windows PC with the official driver installed)
═══════════════════════════════════════════════════════════════════════════════
  • Windows 10/11 PC (VM with USB pass-through also works)
  • Official "M87 keyboard-1.0.0.1.exe" driver installed
  • USBPcap  → https://desowin.org/usbpcap/  (free, open-source)
  • Wireshark → https://www.wireshark.org/   (free, open-source)

═══════════════════════════════════════════════════════════════════════════════
STEP 1 – Install USBPcap
═══════════════════════════════════════════════════════════════════════════════
  1. Download USBPcapSetup-*.exe from the link above.
  2. Run the installer with default settings.
  3. Reboot if prompted.

═══════════════════════════════════════════════════════════════════════════════
STEP 2 – Open Wireshark and start capturing
═══════════════════════════════════════════════════════════════════════════════
  1. Open Wireshark as Administrator.
  2. In the capture interface list you should see "USBPcap1", "USBPcap2" etc.
  3. Plug in your M87 keyboard (if not already plugged in).
  4. Find which USBPcap interface number your keyboard is on:
       Open USBPcapCMD.exe (installed with USBPcap), it lists all USB devices
       and which filter (USBPcap1/2/…) they belong to.
       Look for "Xinmeng" or "HID Keyboard" with an unusual VID.
  5. Double-click that USBPcap interface in Wireshark to start capturing.

═══════════════════════════════════════════════════════════════════════════════
STEP 3 – Filter the capture to show only your keyboard
═══════════════════════════════════════════════════════════════════════════════
  In Wireshark's display filter bar, type:

      usb.idVendor == 0x258a

  (Replace 0x258a with your keyboard's actual VID if different.)
  Press Enter.  You should see USB control/interrupt transfers appear.

  If you don't know the VID yet, use:   usb  (shows all USB traffic)

═══════════════════════════════════════════════════════════════════════════════
STEP 4 – Trigger RGB changes using the official driver
═══════════════════════════════════════════════════════════════════════════════
  Open the official "M87 keyboard" software on Windows.
  While Wireshark is capturing, do each of the following and PAUSE 2–3 seconds
  between each action (so we can identify which packets belong to which command):

    a) Switch to "Static" lighting, set colour to RED  (255, 0, 0)
    b) Switch to "Static" lighting, set colour to GREEN (0, 255, 0)
    c) Switch to "Static" lighting, set colour to BLUE  (0, 0, 255)
    d) Switch to "Breathing" effect
    e) Switch to "Rainbow Wave" effect
    f) Switch to "React" / "Ripple" effect
    g) Turn lighting OFF
    h) Change brightness: 25%, 50%, 75%, 100%
    i) Change speed if applicable

═══════════════════════════════════════════════════════════════════════════════
STEP 5 – Save the capture file
═══════════════════════════════════════════════════════════════════════════════
  1. Stop the capture (red square icon or Ctrl+E).
  2. File → Save As…
  3. Save as  "m87_capture.pcapng"  (pcap format also works).
  4. Copy the file to your Linux machine (USB drive, network share, etc.).

═══════════════════════════════════════════════════════════════════════════════
STEP 6 – Analyse the capture on Linux
═══════════════════════════════════════════════════════════════════════════════
  Copy m87_capture.pcapng to the  packets/  folder of this project, then run:

      python3 main.py analyze --pcap packets/m87_capture.pcapng

  This will:
    • Extract all HID interrupt OUT packets sent to your keyboard.
    • Group them by action.
    • Display the raw bytes in hex.
    • Save the decoded commands to  packets/decoded_commands.json

═══════════════════════════════════════════════════════════════════════════════
TIPS
═══════════════════════════════════════════════════════════════════════════════
  • Use Wireshark's "Export specified packets" feature if you want to export
    only the filtered packets.
  • In Wireshark, right-click a HID packet → Follow → USB Stream to see
    the full conversation between host and device.
  • HID OUT reports (host → device) are the ones we need. Look for
    packets where  usb.endpoint_address.direction == 0  (OUT).
  • Each HID report is usually 64 bytes (0x40) for keyboards like this.
  • The first byte is often the Report ID (e.g. 0x04 or 0x08).

═══════════════════════════════════════════════════════════════════════════════
ALTERNATIVE: Virtual Machine approach
═══════════════════════════════════════════════════════════════════════════════
  If you do not have a Windows PC:
    1. Install VirtualBox or VMware on Linux.
    2. Create a Windows 10 VM.
    3. In VM settings, enable USB 2.0/3.0 controller and add a USB device
       filter for your M87 keyboard.
    4. Install the driver and follow steps 1–5 above.
    5. Use "Shared Folders" to copy the .pcapng back to Linux.

  With VirtualBox you can also use:
      VBoxManage list usbfilters
  to confirm USB pass-through is working.
"""


def print_guide() -> None:
    print(GUIDE)


def save_guide(path: str = "CAPTURE_GUIDE.md") -> None:
    """Save guide as Markdown file."""
    md_lines = []
    for line in GUIDE.split("\n"):
        # Convert box-drawing chars to plain markdown
        line = line.replace("╔", "").replace("╗", "").replace("╚", "").replace("╝", "")
        line = line.replace("║", "").replace("═", "").replace("─", "")
        md_lines.append(line)
    content = "\n".join(md_lines)
    with open(path, "w") as f:
        f.write("# Xinmeng M87 – Windows USB Packet Capture Guide\n\n")
        f.write(content)
    print(f"[✓] Guide saved to {path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Xinmeng M87 – Phase 2: Show USB capture guide"
    )
    parser.add_argument(
        "--save", metavar="PATH",
        help="Also save guide as a Markdown file"
    )
    args = parser.parse_args()

    print_guide()
    if args.save:
        save_guide(args.save)
