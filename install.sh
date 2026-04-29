#!/usr/bin/env bash
# install.sh – One-shot setup for Xinmeng M87 Linux RGB on Linux Mint / Ubuntu
# Run as: bash install.sh

set -e

UDEV_RULE_FILE="/etc/udev/rules.d/99-xinmeng-m87.rules"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║   Xinmeng M87 Linux RGB – Installer                     ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── 1. System packages ────────────────────────────────────────────────────────
echo "[1/5] Installing system packages…"
sudo apt-get update -qq

# Critical packages – fail loudly if these are missing
sudo apt-get install -y python3 python3-pip python3-dev libhidapi-dev libhidapi-hidraw0 libhidapi-libusb0 libudev-dev

# Optional packages – warn but continue if unavailable
for pkg in portaudio19-dev tshark; do
    if ! sudo apt-get install -y "$pkg" 2>/dev/null; then
        echo "[!] Optional package '$pkg' could not be installed – continuing."
    fi
done

# ── 2. Python packages ────────────────────────────────────────────────────────
echo "[2/5] Installing Python packages…"
pip3 install --user -r requirements.txt

# ── 3. udev rule ─────────────────────────────────────────────────────────────
echo "[3/5] Installing udev rule for keyboard access without sudo…"

cat <<'EOF' | sudo tee "$UDEV_RULE_FILE" > /dev/null
# Xinmeng M87 / M87 Pro keyboard – allow HID access for all users in 'input' group
# Sinowealth VID 0x258A (add more ATTR{idProduct} lines if your PID differs)
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="258a", GROUP="input", MODE="0660"
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="0416", GROUP="input", MODE="0660"
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="3151", GROUP="input", MODE="0660"
# Generic fallback – any USB HID device claiming vendor usage page
SUBSYSTEM=="usb", ATTRS{idVendor}=="258a", GROUP="input", MODE="0660"
SUBSYSTEM=="usb", ATTRS{idVendor}=="0416", GROUP="input", MODE="0660"
EOF

echo "[*] udev rule written to $UDEV_RULE_FILE"

# ── 4. Add user to input group ────────────────────────────────────────────────
echo "[4/5] Adding $USER to 'input' group…"
sudo usermod -aG input "$USER" 2>/dev/null || true

# Reload udev
sudo udevadm control --reload-rules 2>/dev/null || true
sudo udevadm trigger 2>/dev/null || true

# ── 5. Create packets directory ───────────────────────────────────────────────
echo "[5/5] Creating packets/ directory…"
mkdir -p packets

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   Installation complete!                                 ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║                                                          ║"
echo "║  IMPORTANT: Log out and log back in (or reboot) so      ║"
echo "║  the 'input' group change takes effect.                  ║"
echo "║                                                          ║"
echo "║  Quick start:                                            ║"
echo "║    python3 main.py detect          # Find keyboard       ║"
echo "║    python3 main.py guide           # Capture guide       ║"
echo "║    python3 main.py effect static --colour 255,0,0        ║"
echo "║    python3 main.py music           # Music reactive      ║"
echo "║    python3 main.py gui             # Open GUI            ║"
echo "║                                                          ║"
echo "╚══════════════════════════════════════════════════════════╝"
