#!/usr/bin/env python3
"""
Phase 5: RGB Effects Engine
Generates RGB command sequences for all supported lighting effects.
Each effect is a generator that yields (r, g, b) tuples or pre-built HID reports.

Effects available:
  static       – Single solid colour
  breathing    – Fade in/out on one colour
  wave         – Rainbow wave (left→right)
  rainbow      – Full-spectrum colour cycle
  reactive     – Colour on keypress, fades out (uses mode command)
  ripple       – Ripple from centre outward
  neon         – Neon / colour shift
  starlight    – Random twinkling keys
  off          – Turn all lights off

All effects are hardware-mode commands (single HID report) where possible.
For per-key effects that require many reports, frame-by-frame generation is used.
"""

import time
import math
import colorsys
import itertools
from typing import Generator, Callable, Optional

from .hid_sender import (
    build_set_mode, build_set_colour, build_set_brightness,
    build_set_speed, build_commit, build_turn_off,
    send_command, M87HIDDevice, get_device_from_json,
    MODE_STATIC, MODE_BREATHING, MODE_WAVE, MODE_REACTIVE,
    MODE_RIPPLE, MODE_NEON, MODE_FLICKER, MODE_STARLIGHT, MODE_OFF,
    SEND_DELAY,
)

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def hsv_to_rgb(h: float, s: float = 1.0, v: float = 1.0) -> tuple[int, int, int]:
    """h in [0,1], s,v in [0,1] → (R,G,B) each 0-255."""
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def clamp(val: float, lo: float = 0, hi: float = 255) -> int:
    return int(max(lo, min(hi, val)))


def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Convert '#RRGGBB' or 'RRGGBB' to (R, G, B)."""
    hex_str = hex_str.lstrip("#")
    r = int(hex_str[0:2], 16)
    g = int(hex_str[2:4], 16)
    b = int(hex_str[4:6], 16)
    return r, g, b


# ---------------------------------------------------------------------------
# Hardware-mode effects (single report)
# ---------------------------------------------------------------------------

def effect_static(r: int, g: int, b: int, brightness: int = 4) -> list[bytes]:
    """Static solid colour."""
    return [
        build_set_mode(MODE_STATIC, r, g, b),
        build_set_brightness(brightness),
        build_commit(),
    ]


def effect_breathing(r: int, g: int, b: int, speed: int = 2, brightness: int = 4) -> list[bytes]:
    """Breathing (fade in/out)."""
    return [
        build_set_mode(MODE_BREATHING, r, g, b),
        build_set_speed(speed),
        build_set_brightness(brightness),
        build_commit(),
    ]


def effect_wave(speed: int = 2, brightness: int = 4) -> list[bytes]:
    """Rainbow wave."""
    return [
        build_set_mode(MODE_WAVE),
        build_set_speed(speed),
        build_set_brightness(brightness),
        build_commit(),
    ]


def effect_rainbow(speed: int = 2, brightness: int = 4) -> list[bytes]:
    """Full-spectrum colour cycle (same as wave, hardware mode)."""
    return effect_wave(speed, brightness)


def effect_reactive(r: int, g: int, b: int, speed: int = 2) -> list[bytes]:
    """Reactive: colour on keypress."""
    return [
        build_set_mode(MODE_REACTIVE, r, g, b),
        build_set_speed(speed),
        build_commit(),
    ]


def effect_ripple(r: int, g: int, b: int, speed: int = 2) -> list[bytes]:
    """Ripple effect."""
    return [
        build_set_mode(MODE_RIPPLE, r, g, b),
        build_set_speed(speed),
        build_commit(),
    ]


def effect_neon(speed: int = 2, brightness: int = 4) -> list[bytes]:
    """Neon colour-shift."""
    return [
        build_set_mode(MODE_NEON),
        build_set_speed(speed),
        build_set_brightness(brightness),
        build_commit(),
    ]


def effect_starlight(r: int, g: int, b: int, speed: int = 2) -> list[bytes]:
    """Starlight twinkling."""
    return [
        build_set_mode(MODE_STARLIGHT, r, g, b),
        build_set_speed(speed),
        build_commit(),
    ]


def effect_off() -> list[bytes]:
    """Turn off all lighting."""
    return [build_turn_off()]


# ---------------------------------------------------------------------------
# Software-animated effects (frame-based, for music sync or custom patterns)
# These yield (r, g, b) tuples at ~FPS rate.
# ---------------------------------------------------------------------------

def gen_breathing(
    r: int, g: int, b: int,
    fps: int = 30,
    period: float = 3.0,
) -> Generator[tuple[int, int, int], None, None]:
    """Software breathing: yields (R,G,B) at ~fps Hz."""
    step = 1.0 / fps
    t = 0.0
    while True:
        bright = (1 + math.sin(2 * math.pi * t / period)) / 2
        yield clamp(r * bright), clamp(g * bright), clamp(b * bright)
        t += step
        time.sleep(step)


def gen_rainbow(fps: int = 30, period: float = 5.0) -> Generator[tuple[int, int, int], None, None]:
    """Software rainbow cycle: yields (R,G,B) at ~fps Hz."""
    step = 1.0 / fps
    t = 0.0
    while True:
        hue = (t % period) / period
        yield hsv_to_rgb(hue)
        t += step
        time.sleep(step)


def gen_colour_pulse(
    colours: list[tuple[int, int, int]],
    fps: int = 30,
    hold: float = 0.5,
    fade: float = 1.0,
) -> Generator[tuple[int, int, int], None, None]:
    """Cycle through a list of colours with fade transitions."""
    step = 1.0 / fps
    n = len(colours)
    while True:
        for i in range(n):
            c0 = colours[i]
            c1 = colours[(i + 1) % n]
            # Fade out
            fade_steps = int(fade * fps)
            for k in range(fade_steps):
                alpha = k / fade_steps
                r = clamp(c0[0] * (1 - alpha) + c1[0] * alpha)
                g = clamp(c0[1] * (1 - alpha) + c1[1] * alpha)
                b = clamp(c0[2] * (1 - alpha) + c1[2] * alpha)
                yield r, g, b
                time.sleep(step)
            # Hold
            hold_steps = int(hold * fps)
            for _ in range(hold_steps):
                yield c1
                time.sleep(step)


# ---------------------------------------------------------------------------
# Effect registry and runner
# ---------------------------------------------------------------------------

EFFECT_REGISTRY: dict[str, Callable] = {
    "static":    effect_static,
    "breathing": effect_breathing,
    "wave":      effect_wave,
    "rainbow":   effect_rainbow,
    "reactive":  effect_reactive,
    "ripple":    effect_ripple,
    "neon":      effect_neon,
    "starlight": effect_starlight,
    "off":       effect_off,
}

EFFECT_DESCRIPTIONS: dict[str, str] = {
    "static":    "Solid single colour (provide --colour R,G,B)",
    "breathing": "Fade in/out on a colour (provide --colour R,G,B)",
    "wave":      "Rainbow wave across keyboard",
    "rainbow":   "Full-spectrum colour cycle",
    "reactive":  "Light up on keypress (provide --colour R,G,B)",
    "ripple":    "Ripple from keypress (provide --colour R,G,B)",
    "neon":      "Neon colour shift",
    "starlight": "Random twinkling (provide --colour R,G,B)",
    "off":       "Turn all lights off",
}


def apply_effect(
    effect_name: str,
    r: int = 255,
    g: int = 255,
    b: int = 255,
    speed: int = 2,
    brightness: int = 4,
    vid: Optional[int] = None,
    pid: Optional[int] = None,
) -> bool:
    """Build and send an effect command to the keyboard."""
    if effect_name not in EFFECT_REGISTRY:
        print(f"[ERROR] Unknown effect '{effect_name}'.")
        print(f"        Available: {', '.join(EFFECT_REGISTRY.keys())}")
        return False

    fn = EFFECT_REGISTRY[effect_name]

    # Determine which arguments the function accepts
    import inspect
    sig = inspect.signature(fn)
    kwargs: dict = {}
    if "r" in sig.parameters:
        kwargs["r"] = r
    if "g" in sig.parameters:
        kwargs["g"] = g
    if "b" in sig.parameters:
        kwargs["b"] = b
    if "speed" in sig.parameters:
        kwargs["speed"] = speed
    if "brightness" in sig.parameters:
        kwargs["brightness"] = brightness

    reports = fn(**kwargs)
    print(f"[*] Applying effect: {effect_name}  colour=({r},{g},{b})  speed={speed}  brightness={brightness}")
    return send_command(reports, vid=vid, pid=pid)


def list_effects() -> None:
    print("\nAvailable RGB effects:")
    print(f"{'─'*50}")
    for name, desc in EFFECT_DESCRIPTIONS.items():
        print(f"  {name:<12}  {desc}")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Xinmeng M87 – Phase 5: Apply RGB effect"
    )
    parser.add_argument(
        "effect", nargs="?",
        help="Effect name (see --list for options)"
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List all available effects"
    )
    parser.add_argument(
        "--colour", "--color", default="255,255,255",
        help="RGB colour as R,G,B (default: 255,255,255)"
    )
    parser.add_argument(
        "--hex-colour", metavar="RRGGBB",
        help="RGB colour as hex, e.g. FF0000 for red"
    )
    parser.add_argument(
        "--speed", type=int, default=2, choices=range(5),
        help="Speed 0(fast)–4(slow) (default: 2)"
    )
    parser.add_argument(
        "--brightness", type=int, default=4, choices=range(5),
        help="Brightness 0(off)–4(full) (default: 4)"
    )
    parser.add_argument("--vid", type=lambda x: int(x, 0))
    parser.add_argument("--pid", type=lambda x: int(x, 0))

    args = parser.parse_args()

    if args.list or not args.effect:
        list_effects()
        import sys; sys.exit(0)

    if args.hex_colour:
        r, g, b = hex_to_rgb(args.hex_colour)
    else:
        try:
            parts = [int(x) for x in args.colour.split(",")]
            r, g, b = parts[0], parts[1], parts[2]
        except (ValueError, IndexError):
            print("[ERROR] Colour must be R,G,B (e.g. 255,0,0)")
            import sys; sys.exit(1)

    apply_effect(
        args.effect,
        r=r, g=g, b=b,
        speed=args.speed,
        brightness=args.brightness,
        vid=args.vid,
        pid=args.pid,
    )
