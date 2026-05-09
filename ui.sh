#!/usr/bin/env bash
# Interactive terminal UI for xinmeng_rgb

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$SCRIPT_DIR/xinmeng_rgb"

EFFECT="static"
COLOUR="255,0,0"
SPEED="2"
BRIGHTNESS="4"
VID=""
PID=""

print_banner() {
  clear || true
  cat <<'EOF'
╔══════════════════════════════════════════════════════════╗
║            Xinmeng M87 RGB Control - UI                 ║
╚══════════════════════════════════════════════════════════╝
EOF
  echo "Current profile: effect=$EFFECT colour=$COLOUR speed=$SPEED brightness=$BRIGHTNESS"
  if [[ -n "$VID" && -n "$PID" ]]; then
    echo "Device override: VID=$VID PID=$PID"
  else
    echo "Device override: auto (detected_device.json or known devices)"
  fi
  echo
}

usage() {
  cat <<'EOF'
Usage:
  bash ui.sh

Optional:
  bash ui.sh --help
EOF
}

require_bin() {
  if [[ ! -x "$BIN" ]]; then
    echo "[ERROR] Binary not found: $BIN"
    echo "Run: bash install.sh"
    exit 1
  fi
}

is_uint_0_255() {
  [[ "$1" =~ ^[0-9]+$ ]] && (( $1 >= 0 && $1 <= 255 ))
}

is_uint_0_4() {
  [[ "$1" =~ ^[0-9]+$ ]] && (( $1 >= 0 && $1 <= 4 ))
}

valid_hex_colour() {
  [[ "$1" =~ ^[0-9A-Fa-f]{6}$ ]]
}

apply_effect() {
  local cmd=("$BIN" effect "$EFFECT" --colour "$COLOUR" --speed "$SPEED" --brightness "$BRIGHTNESS")

  if [[ -n "$VID" && -n "$PID" ]]; then
    cmd+=(--vid "$VID" --pid "$PID")
  fi

  echo
  echo "[*] Running: ${cmd[*]}"
  if ! "${cmd[@]}"; then
    echo
    echo "[ERROR] Command failed."
    echo "Tip: if permission denied, run install first and re-login: bash install.sh"
    read -r -p "Press Enter to continue..." _
    return 1
  fi

  echo "[OK] Effect applied."
  read -r -p "Press Enter to continue..." _
}

run_detect() {
  echo
  echo "[*] Detecting keyboard..."
  if "$BIN" detect; then
    echo "[OK] Detection finished."
  else
    echo "[WARN] Detection failed. You can still set VID/PID manually in this UI."
  fi
  read -r -p "Press Enter to continue..." _
}

list_effects() {
  echo
  "$BIN" effect --list || true
  echo
  read -r -p "Press Enter to continue..." _
}

pick_effect() {
  print_banner
  echo "Select an effect:"
  local options=(static breathing wave rainbow reactive ripple neon starlight off back)
  select choice in "${options[@]}"; do
    if [[ -z "${choice:-}" ]]; then
      echo "Invalid selection."
      continue
    fi
    if [[ "$choice" == "back" ]]; then
      return
    fi
    EFFECT="$choice"
    echo "Effect set to: $EFFECT"
    read -r -p "Press Enter to continue..." _
    return
  done
}

set_colour_rgb() {
  local r g b
  read -r -p "R (0-255): " r
  read -r -p "G (0-255): " g
  read -r -p "B (0-255): " b

  if is_uint_0_255 "$r" && is_uint_0_255 "$g" && is_uint_0_255 "$b"; then
    COLOUR="$r,$g,$b"
    echo "Colour set to: $COLOUR"
  else
    echo "Invalid RGB values."
  fi
  read -r -p "Press Enter to continue..." _
}

set_colour_hex() {
  local hex
  read -r -p "Hex colour (RRGGBB): " hex
  if ! valid_hex_colour "$hex"; then
    echo "Invalid hex colour."
    read -r -p "Press Enter to continue..." _
    return
  fi

  local r=$((16#${hex:0:2}))
  local g=$((16#${hex:2:2}))
  local b=$((16#${hex:4:2}))
  COLOUR="$r,$g,$b"
  echo "Colour set to: $COLOUR"
  read -r -p "Press Enter to continue..." _
}

set_speed() {
  local s
  read -r -p "Speed (0-4, 0=fastest): " s
  if is_uint_0_4 "$s"; then
    SPEED="$s"
    echo "Speed set to: $SPEED"
  else
    echo "Invalid speed value."
  fi
  read -r -p "Press Enter to continue..." _
}

set_brightness() {
  local b
  read -r -p "Brightness (0-4, 4=full): " b
  if is_uint_0_4 "$b"; then
    BRIGHTNESS="$b"
    echo "Brightness set to: $BRIGHTNESS"
  else
    echo "Invalid brightness value."
  fi
  read -r -p "Press Enter to continue..." _
}

set_device_override() {
  local v p
  read -r -p "VID (example: 0x258A): " v
  read -r -p "PID (example: 0x002A): " p

  if [[ "$v" =~ ^0x[0-9A-Fa-f]{4}$ && "$p" =~ ^0x[0-9A-Fa-f]{4}$ ]]; then
    VID="$v"
    PID="$p"
    echo "Device override set: VID=$VID PID=$PID"
  else
    echo "Invalid VID/PID format."
  fi
  read -r -p "Press Enter to continue..." _
}

clear_device_override() {
  VID=""
  PID=""
  echo "Device override cleared (auto mode)."
  read -r -p "Press Enter to continue..." _
}

run_off_now() {
  EFFECT="off"
  apply_effect
}

main_menu() {
  while true; do
    print_banner
    cat <<'EOF'
1) Detect keyboard
2) List available effects
3) Choose effect
4) Set colour (RGB)
5) Set colour (Hex)
6) Set speed
7) Set brightness
8) Set VID/PID override
9) Clear VID/PID override
10) Apply current profile
11) Turn RGB off now
0) Exit
EOF
    echo
    read -r -p "Select option: " opt
    case "$opt" in
      1) run_detect ;;
      2) list_effects ;;
      3) pick_effect ;;
      4) set_colour_rgb ;;
      5) set_colour_hex ;;
      6) set_speed ;;
      7) set_brightness ;;
      8) set_device_override ;;
      9) clear_device_override ;;
      10) apply_effect ;;
      11) run_off_now ;;
      0) echo "Bye."; exit 0 ;;
      *) echo "Invalid option."; read -r -p "Press Enter to continue..." _ ;;
    esac
  done
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

require_bin
main_menu
