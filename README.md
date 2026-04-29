# Xinmeng M87 / M87 Pro – Linux RGB Control Tool

A modular Python tool to control RGB lighting on the **Xinmeng M87 / M87 Pro** keyboard on **Linux Mint** (and any Ubuntu-based distro).

---

## Project Structure

```
xinmeng-m87-linux-rgb/
├── main.py                    ← CLI entry point (all phases)
├── install.sh                 ← One-shot installer
├── requirements.txt           ← Python dependencies
├── 99-xinmeng-m87.rules       ← udev rule (keyboard access without sudo)
├── src/
│   ├── detect.py              ← Phase 1 – Device detection
│   ├── capture_guide.py       ← Phase 2 – Windows packet capture guide
│   ├── analyze_pcap.py        ← Phase 3 – Pcap file analyzer
│   ├── hid_sender.py          ← Phase 4 – HID command sender
│   ├── rgb_effects.py         ← Phase 5 – RGB effects engine
│   └── music_sync.py          ← Phase 6 – Music-reactive RGB
├── gui/
│   └── main_gui.py            ← Optional PyQt5 GUI
└── packets/
    └── (your .pcapng files go here)
```

---

## Quick Start

### 1. Install

```bash
bash install.sh
```

Then **log out and back in** (or reboot) so the `input` group change takes effect.

### 2. Detect your keyboard

```bash
python3 main.py detect
```

If found, saves `detected_device.json` with VID/PID. All other commands use this file automatically.

### 3. Apply an RGB effect

```bash
python3 main.py effect static --colour 255,0,0          # Solid red
python3 main.py effect breathing --colour 0,128,255      # Blue breathing
python3 main.py effect wave                              # Rainbow wave
python3 main.py effect rainbow                           # Colour cycle
python3 main.py effect off                               # Lights off
```

### 4. Music-reactive RGB

```bash
python3 main.py music --list-devices   # Show audio input devices
python3 main.py music                  # Start with default mic
python3 main.py music --device 3 --mode fire   # Use device 3, fire palette
```

### 5. Open the GUI

```bash
python3 main.py gui
```

---

## All Commands

```
python3 main.py detect               # Phase 1 – Find keyboard
python3 main.py guide                # Phase 2 – Windows capture guide
python3 main.py analyze --pcap FILE  # Phase 3 – Analyse pcap file
python3 main.py replay               # Phase 4 – Replay captured packets
python3 main.py send <hex>           # Phase 4 – Send raw HID report
python3 main.py effect <name>        # Phase 5 – Apply RGB effect
python3 main.py music                # Phase 6 – Music reactive RGB
python3 main.py gui                  # Launch GUI
```

---

## Six Phases Explained

### Phase 1 – Device Detection (`src/detect.py`)

Scans all USB HID devices using **hidapi** and **pyusb**.  
Checks against a list of known Xinmeng M87 VID/PID combinations.  
Finds the vendor-specific HID interface (Usage Page `0xFF00`) used for RGB.

```bash
python3 main.py detect              # Scan for keyboard
python3 main.py detect --list-all   # Show every HID device on your system
```

If your keyboard is not in the known list, the full device dump helps you find and add it.

---

### Phase 2 – Windows USB Capture Guide (`src/capture_guide.py`)

The M87 uses a **proprietary HID protocol**. To decode it, we capture packets sent by the official Windows driver.

```bash
python3 main.py guide
```

Steps in the guide:
1. Install **USBPcap** + **Wireshark** on Windows
2. Start capturing on the correct USBPcap interface
3. Change RGB modes in the official driver
4. Save as `m87_capture.pcapng`
5. Copy to Linux and run Phase 3

---

### Phase 3 – Packet Analysis (`src/analyze_pcap.py`)

Parses the `.pcapng` file and extracts HID interrupt OUT packets (host → keyboard).

```bash
# Copy your capture to the packets/ folder, then:
python3 main.py analyze --pcap packets/m87_capture.pcapng

# If you exported raw hex from Wireshark:
python3 main.py analyze --pcap packets/bytes.txt --raw-hex
```

Output: `packets/decoded_commands.json` – structured list of every unique command.

**Requirements:**
```bash
pip install scapy        # Recommended
# OR
pip install pyshark      # Needs tshark: sudo apt install tshark
```

---

### Phase 4 – HID Command Sender (`src/hid_sender.py`)

Sends HID reports directly to the keyboard.

```bash
# Replay all captured commands:
python3 main.py replay

# Replay only commands matching a label:
python3 main.py replay --label rgb_static_colour

# Send a raw hex report:
python3 main.py send "04 01 00 00 ff 00 00 00"
```

After Phase 3 you know the exact bytes. If you want to send a new colour, just modify the hex.

---

### Phase 5 – RGB Effects (`src/rgb_effects.py`)

Built-in hardware modes (single HID report each):

| Effect     | Description |
|------------|-------------|
| `static`   | Solid single colour |
| `breathing`| Fade in/out |
| `wave`     | Rainbow wave |
| `rainbow`  | Colour cycle |
| `reactive` | Light up on keypress |
| `ripple`   | Ripple from keypress |
| `neon`     | Neon colour shift |
| `starlight`| Random twinkling |
| `off`      | All lights off |

```bash
python3 main.py effect --list                           # Show all effects
python3 main.py effect static --colour 255,165,0        # Orange
python3 main.py effect breathing --hex-colour 00ff88    # Teal breathing
python3 main.py effect wave --speed 0 --brightness 4    # Fast wave, full bright
```

> **Note:** These commands use a best-guess protocol based on similar Sinowealth keyboards.  
> After completing Phase 3, you can verify and update the byte structure in `src/hid_sender.py`.

---

### Phase 6 – Music-Reactive RGB (`src/music_sync.py`)

Analyses live audio using FFT and maps frequency bands to RGB:

| Mode    | Mapping |
|---------|---------|
| `rgb`   | Bass→Red, Mid→Green, Treble→Blue |
| `hue`   | Dominant band drives hue, total energy drives brightness |
| `fire`  | Bass drives warm orange/red palette |

```bash
pip install sounddevice numpy

python3 main.py music --list-devices          # Show audio devices
python3 main.py music                         # Start (default mic)
python3 main.py music --device 5 --mode fire  # Device 5, fire mode
```

**For music (not microphone):**
1. Open **pavucontrol** (PulseAudio Volume Control)  
   `sudo apt install pavucontrol`
2. Pick a **"Monitor of ..."** device with `--list-devices`
3. Use that device index: `python3 main.py music --device <N>`

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

### Keyboard not detected

```bash
# List everything connected:
python3 main.py detect --list-all

# If you see your keyboard but it's not in the known list,
# note the VID and PID and add them to KNOWN_DEVICES in src/detect.py:
#   {"vid": 0xXXXX, "pid": 0xXXXX, "name": "Xinmeng M87 (your variant)"},
```

### RGB commands sent but nothing happens

The byte protocol may differ from the built-in guess.  
→ Complete Phase 2 (capture) and Phase 3 (analyze) to get the real bytes.

### scapy fails to read pcap

```bash
# Alternative: export raw hex from Wireshark
# File → Export Packet Dissections → As Plain Text
# Then use:
python3 main.py analyze --pcap export.txt --raw-hex
```

---

## Dependencies

| Package | Purpose | Required |
|---------|---------|----------|
| `hidapi` | HID device communication | ✅ |
| `pyusb` | USB device enumeration fallback | ✅ |
| `scapy` | Pcap file parsing (Phase 3) | Phase 3 only |
| `sounddevice` | Audio capture | Phase 6 only |
| `numpy` | FFT / signal processing | Phase 6 only |
| `PyQt5` | GUI | Optional |

```bash
pip install -r requirements.txt
```

---

## Known VID/PID

| VID    | PID    | Model |
|--------|--------|-------|
| 0x258A | 0x002A | Xinmeng M87 (Sinowealth) |
| 0x258A | 0x0049 | Xinmeng M87 Pro |
| 0x258A | 0x0026 | Xinmeng M87 variant |
| 0x258A | 0x00C7 | Xinmeng M87 variant |
| 0x0416 | 0xC343 | Xinmeng M87 (Generalplus) |

If yours isn't listed, add it to `KNOWN_DEVICES` in `src/detect.py`.

---

## License

MIT – Free to use, modify, and share.
