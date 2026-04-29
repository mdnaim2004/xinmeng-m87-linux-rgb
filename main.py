#!/usr/bin/env python3
"""
Xinmeng M87 Linux RGB Control Tool
====================================
All-in-one CLI entry point.

Usage:
  python3 main.py detect              # Phase 1 – Find keyboard
  python3 main.py guide               # Phase 2 – Windows capture guide
  python3 main.py analyze --pcap FILE # Phase 3 – Analyse pcap
  python3 main.py send --hex BYTES    # Phase 4 – Send raw HID report
  python3 main.py replay              # Phase 4 – Replay captured packets
  python3 main.py effect EFFECT       # Phase 5 – Apply RGB effect
  python3 main.py music               # Phase 6 – Music-reactive RGB
  python3 main.py gui                 # Launch GUI (optional)

Run  python3 main.py <command> --help  for per-command help.
"""

import sys
import argparse


# ---------------------------------------------------------------------------
# Sub-command handlers
# ---------------------------------------------------------------------------

def cmd_detect(args):
    from src.detect import run_detection, list_all_hid_devices, print_device_table
    if args.list_all:
        devices = list_all_hid_devices()
        print_device_table(devices, "All HID Devices")
    else:
        run_detection(save=not args.no_save, output_path=args.save)


def cmd_guide(args):
    from src.capture_guide import print_guide, save_guide
    print_guide()
    if args.save:
        save_guide(args.save)


def cmd_analyze(args):
    from src.analyze_pcap import analyze
    analyze(
        pcap_path=args.pcap,
        output_path=args.output,
        vid_filter=args.vid,
        dedupe=not args.no_dedupe,
        raw_hex=args.raw_hex,
    )


def cmd_replay(args):
    from src.hid_sender import replay_from_json
    replay_from_json(
        commands_json=args.json,
        label_filter=args.label,
        vid=args.vid,
        pid=args.pid,
    )


def cmd_send(args):
    from src.hid_sender import send_command
    try:
        data = bytes.fromhex(args.hex.replace(" ", "").replace(":", ""))
    except ValueError as e:
        print(f"[ERROR] Invalid hex string: {e}")
        sys.exit(1)
    send_command([data], vid=args.vid, pid=args.pid)


def cmd_effect(args):
    from src.rgb_effects import apply_effect, list_effects, hex_to_rgb

    if args.list:
        list_effects()
        return

    if not args.effect:
        list_effects()
        return

    if args.hex_colour:
        r, g, b = hex_to_rgb(args.hex_colour)
    else:
        try:
            parts = [int(x.strip()) for x in args.colour.split(",")]
            r, g, b = parts[0], parts[1], parts[2]
        except (ValueError, IndexError):
            print("[ERROR] --colour must be R,G,B  e.g. 255,0,0")
            sys.exit(1)

    apply_effect(
        args.effect,
        r=r, g=g, b=b,
        speed=args.speed,
        brightness=args.brightness,
        vid=args.vid,
        pid=args.pid,
    )


def cmd_music(args):
    from src.music_sync import MusicSyncEngine, list_audio_devices
    if args.list_devices:
        list_audio_devices()
        return
    engine = MusicSyncEngine(
        vid=args.vid,
        pid=args.pid,
        device=args.device,
        mode=args.mode,
        sensitivity=args.sensitivity,
    )
    engine.start()


def cmd_gui(args):
    try:
        from gui.main_gui import run_gui
        run_gui()
    except ImportError as e:
        print(f"[ERROR] GUI dependencies missing: {e}")
        print("  Install with:  pip install PyQt5")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=(
            "Xinmeng M87 Linux RGB Control Tool\n"
            "────────────────────────────────────\n"
            "Phase 1: detect  →  Find keyboard\n"
            "Phase 2: guide   →  Windows USB capture guide\n"
            "Phase 3: analyze →  Parse pcap file\n"
            "Phase 4: send / replay → Send HID commands\n"
            "Phase 5: effect  →  Apply RGB effect\n"
            "Phase 6: music   →  Music-reactive RGB\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # ── detect ──────────────────────────────────────────────────────────────
    p = sub.add_parser("detect", help="Phase 1 – Detect M87 keyboard")
    p.add_argument("--list-all", action="store_true", help="List all HID devices")
    p.add_argument("--save", default="detected_device.json", help="Output JSON path")
    p.add_argument("--no-save", action="store_true", help="Do not save JSON")
    p.set_defaults(func=cmd_detect)

    # ── guide ────────────────────────────────────────────────────────────────
    p = sub.add_parser("guide", help="Phase 2 – Show Windows USB capture guide")
    p.add_argument("--save", metavar="PATH", help="Save guide as Markdown file")
    p.set_defaults(func=cmd_guide)

    # ── analyze ──────────────────────────────────────────────────────────────
    p = sub.add_parser("analyze", help="Phase 3 – Analyse pcap capture file")
    p.add_argument("--pcap", required=True, help="Path to .pcap / .pcapng file")
    p.add_argument("--output", "-o", default="packets/decoded_commands.json")
    p.add_argument("--vid", type=lambda x: int(x, 0))
    p.add_argument("--no-dedupe", action="store_true")
    p.add_argument("--raw-hex", action="store_true",
                   help="Input is a plain text hex file (one packet per line)")
    p.set_defaults(func=cmd_analyze)

    # ── replay ───────────────────────────────────────────────────────────────
    p = sub.add_parser("replay", help="Phase 4 – Replay captured packets")
    p.add_argument("--json", default="packets/decoded_commands.json")
    p.add_argument("--label", help="Filter by label")
    p.add_argument("--vid", type=lambda x: int(x, 0))
    p.add_argument("--pid", type=lambda x: int(x, 0))
    p.set_defaults(func=cmd_replay)

    # ── send ─────────────────────────────────────────────────────────────────
    p = sub.add_parser("send", help="Phase 4 – Send a raw HID report (hex bytes)")
    p.add_argument("hex", help="Hex string, e.g. 04010000ff000000")
    p.add_argument("--vid", type=lambda x: int(x, 0))
    p.add_argument("--pid", type=lambda x: int(x, 0))
    p.set_defaults(func=cmd_send)

    # ── effect ───────────────────────────────────────────────────────────────
    p = sub.add_parser("effect", help="Phase 5 – Apply an RGB lighting effect")
    p.add_argument("effect", nargs="?", help="Effect name (see --list)")
    p.add_argument("--list", action="store_true", help="List available effects")
    p.add_argument("--colour", "--color", default="255,255,255",
                   help="R,G,B colour (default: 255,255,255)")
    p.add_argument("--hex-colour", metavar="RRGGBB",
                   help="Colour as hex, e.g. FF0000")
    p.add_argument("--speed", type=int, default=2, choices=range(5))
    p.add_argument("--brightness", type=int, default=4, choices=range(5))
    p.add_argument("--vid", type=lambda x: int(x, 0))
    p.add_argument("--pid", type=lambda x: int(x, 0))
    p.set_defaults(func=cmd_effect)

    # ── music ────────────────────────────────────────────────────────────────
    p = sub.add_parser("music", help="Phase 6 – Music-reactive RGB")
    p.add_argument("--list-devices", action="store_true",
                   help="List audio input devices")
    p.add_argument("--device", "-d", type=int,
                   help="Audio device index")
    p.add_argument("--mode", choices=["rgb", "hue", "fire"], default="rgb")
    p.add_argument("--sensitivity", type=float, default=1.5)
    p.add_argument("--vid", type=lambda x: int(x, 0))
    p.add_argument("--pid", type=lambda x: int(x, 0))
    p.set_defaults(func=cmd_music)

    # ── gui ──────────────────────────────────────────────────────────────────
    p = sub.add_parser("gui", help="Launch the graphical control panel")
    p.set_defaults(func=cmd_gui)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
