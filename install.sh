#!/usr/bin/env bash
# install.sh – One-shot setup for Xinmeng M87 Linux RGB (C++ version)
# Run as: bash install.sh
#
# What this script does:
#   1. Installs build dependencies (g++, libhidapi-dev)
#   2. Builds the xinmeng_rgb binary
#   3. Installs the udev rule for keyboard access without sudo
#   4. Adds you to the 'input' group

set -e

UDEV_RULE_FILE="/etc/udev/rules.d/99-xinmeng-m87.rules"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║   Xinmeng M87 Linux RGB – C++ Installer                 ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── 1. System packages ────────────────────────────────────────────────────────
echo "[1/4] Installing build dependencies…"
sudo apt-get update -qq
sudo apt-get install -y g++ make pkg-config libhidapi-dev libhidapi-hidraw0 python3 python3-tk

# ── 2. Build ──────────────────────────────────────────────────────────────────
echo "[2/4] Building xinmeng_rgb binary…"
cd "$SCRIPT_DIR"
make clean
make
echo "[✓] Build complete: $SCRIPT_DIR/xinmeng_rgb"

# ── 3. udev rule ─────────────────────────────────────────────────────────────
echo "[3/4] Installing udev rule for keyboard access without sudo…"

sudo cp "$SCRIPT_DIR/99-xinmeng-m87.rules" "$UDEV_RULE_FILE"
echo "[*] udev rule written to $UDEV_RULE_FILE"

sudo udevadm control --reload-rules 2>/dev/null || true
sudo udevadm trigger 2>/dev/null || true

# ── 4. Add user to input group ────────────────────────────────────────────────
echo "[4/4] Adding $USER to 'input' group…"
sudo usermod -aG input "$USER" 2>/dev/null || true

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   Installation complete!                                 ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║                                                          ║"
echo "║  IMPORTANT: Log out and log back in (or reboot) so      ║"
echo "║  the 'input' group change takes effect.                  ║"
echo "║                                                          ║"
echo "║  Launch the GUI (recommended):                           ║"
echo "║    python3 xinmeng_rgb_gui.py                            ║"
echo "║                                                          ║"
echo "║  Command-line (advanced):                                ║"
echo "║    ./xinmeng_rgb detect                                  ║"
echo "║    ./xinmeng_rgb effect static --colour 255,0,0          ║"
echo "║    ./xinmeng_rgb effect breathing --colour 0,128,255     ║"
echo "║    ./xinmeng_rgb effect wave                             ║"
echo "║    ./xinmeng_rgb effect off                              ║"
echo "║    ./xinmeng_rgb guide   # USB capture guide             ║"
echo "║                                                          ║"
echo "╚══════════════════════════════════════════════════════════╝"
