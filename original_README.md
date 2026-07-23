# Xinmeng M87 / M87 Pro – Linux RGB Control Tool (C++)

A standalone C++ tool to control RGB lighting on the **Xinmeng M87 / M87 Pro** keyboard on **Linux** (Ubuntu, Linux Mint, Debian, etc.).

Written in **C++17** using **libhidapi** — no Python, no virtual environment, no extra runtime required.

---

## Project Structure

```
xinmeng-m87-linux-rgb/
├── xinmeng_rgb.cpp          ← C++ source (single file, all features)
├── Makefile                 ← Build system
├── install.sh               ← One-shot installer (build + udev + group)
├── 99-xinmeng-m87.rules     ← udev rule (keyboard access without sudo)
├── 20240301154823_2169.zip  ← Official Windows driver (for packet capture)
└── README.md
```

---

## Quick Start

### 1. Install & build

```bash
bash install.sh
```

Then **log out and back in** (or reboot) so the `input` group change takes effect.

### 2. Detect your keyboard

```bash
./xinmeng_rgb detect
```

### 3. Apply an RGB effect

```bash
./xinmeng_rgb effect static --colour 255,0,0          # Solid red
./xinmeng_rgb effect breathing --colour 0,128,255      # Blue breathing
./xinmeng_rgb effect wave                              # Rainbow wave
./xinmeng_rgb effect rainbow                           # Colour cycle
./xinmeng_rgb effect off                               # Lights off
```

---

## Building Manually

```bash
# Install dependency
sudo apt install libhidapi-dev libhidapi-hidraw0

# Build
make

# Or manually:
g++ -std=c++17 -O2 xinmeng_rgb.cpp $(pkg-config --libs --cflags hidapi-hidraw) -o xinmeng_rgb
```

---

## All Commands

```
./xinmeng_rgb detect                   # Find keyboard, save detected_device.json
./xinmeng_rgb detect --list-all        # List every HID device on the system

./xinmeng_rgb effect <name>            # Apply RGB effect
./xinmeng_rgb effect --list            # List all effects

./xinmeng_rgb send "04 01 00 00 ff..." # Send raw 64-byte HID report
./xinmeng_rgb replay <json_file>       # Replay captured packets from JSON
./xinmeng_rgb guide                    # Show Windows USB capture guide
```

---

## RGB Effects

| Effect       | Description |
|--------------|-------------|
| `static`     | Solid single colour |
| `breathing`  | Fade in/out |
| `wave`       | Rainbow wave |
| `rainbow`    | Colour cycle |
| `reactive`   | Light up on keypress |
| `ripple`     | Ripple from keypress |
| `neon`       | Neon colour shift |
| `starlight`  | Random twinkling |
| `off`        | All lights off |

```bash
./xinmeng_rgb effect static --colour 255,165,0        # Orange
./xinmeng_rgb effect breathing --hex-colour 00ff88    # Teal breathing
./xinmeng_rgb effect wave --speed 0 --brightness 4   # Fast wave, full bright
./xinmeng_rgb effect static --colour 255,0,0 --vid 0x258A --pid 0x002A
```

Options:
- `--colour R,G,B` — RGB values 0–255 (default: 255,255,255)
- `--hex-colour RRGGBB` — Colour as hex string (e.g. `FF0000`)
- `--speed 0-4` — 0=fastest, 4=slowest (default: 2)
- `--brightness 0-4` — 0=off, 4=full (default: 4)
- `--vid 0xXXXX` / `--pid 0xXXXX` — Override keyboard VID/PID

---

## Troubleshooting

### "Permission denied" when opening keyboard

The udev rule isn't active yet:
```bash
sudo cp 99-xinmeng-m87.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
sudo usermod -aG input $USER
# Log out and back in
```

Or simply run with `sudo ./xinmeng_rgb effect static --colour 255,0,0` to test first.

### Keyboard not detected

```bash
./xinmeng_rgb detect --list-all
```

If your keyboard appears but VID/PID isn't in the known list, add it to `KNOWN_DEVICES` in `xinmeng_rgb.cpp` and rebuild with `make`.

### RGB commands sent but nothing happens

The byte protocol may differ from the built-in guess. Use the Windows driver + Wireshark to capture the real packets:

```bash
./xinmeng_rgb guide
```

Then replay captured bytes:
```bash
./xinmeng_rgb replay packets/decoded_commands.json
```

---

## Known VID / PID

| VID    | PID    | Model |
|--------|--------|-------|
| 0x258A | 0x002A | Xinmeng M87 (Sinowealth) |
| 0x258A | 0x0049 | Xinmeng M87 Pro |
| 0x258A | 0x0026 | Xinmeng M87 variant |
| 0x258A | 0x00C7 | Xinmeng M87 variant |
| 0x0416 | 0xC343 | Xinmeng M87 (Generalplus) |

If yours isn't listed, run `./xinmeng_rgb detect --list-all`, find your keyboard's VID/PID, and add it to `KNOWN_DEVICES` in `xinmeng_rgb.cpp`.

---

## Capturing Real Packets (Advanced)

The built-in effect commands are based on a best-guess protocol derived from similar Sinowealth keyboards. For your exact keyboard, capture the real USB packets:

1. Use the Windows driver (`20240301154823_2169.zip`) on a Windows PC
2. Capture USB traffic with USBPcap + Wireshark
3. Export the HID OUT packets as hex
4. Create a JSON file and replay with `./xinmeng_rgb replay`

Run `./xinmeng_rgb guide` for step-by-step instructions.

---

## Runtime Dependency

| Library | Purpose | Install |
|---------|---------|---------|
| `libhidapi-hidraw0` | HID device communication | `sudo apt install libhidapi-hidraw0` |

The compiled binary is otherwise fully standalone — no Python, no virtual environment.

---

## License

MIT – Free to use, modify, and share.
