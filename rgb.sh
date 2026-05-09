#!/usr/bin/env bash
set -e

VID="0x05AC"
PID="0x024F"
BIN="./xinmeng_rgb"

sudo "$BIN" effect "$@" --vid "$VID" --pid "$PID"
