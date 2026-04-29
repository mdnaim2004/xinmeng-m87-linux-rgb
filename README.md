# Xinmeng M87 Linux RGB

A repository for Xinmeng M87 / M87 Pro keyboard RGB control on Linux.

## Overview

The **Xinmeng M87** is a mechanical keyboard that comes with RGB lighting. This repository provides resources to control the RGB lighting of the Xinmeng M87 / M87 Pro keyboard on Linux systems.

## Contents

| File | Description |
|------|-------------|
| `20240301154823_2169.zip` | Official Windows RGB software (M87 keyboard v1.0.0.1) |

## Windows Software

The included zip file (`20240301154823_2169.zip`) contains the official **M87 keyboard v1.0.0.1** RGB control software for Windows. Extract and run `M87 keyboard-1.0.0.1.exe` on a Windows machine to configure your keyboard's RGB settings.

## Linux Usage

On Linux, you can use tools like [hidapi](https://github.com/libusb/hidapi) or [OpenRGB](https://openrgb.org/) to communicate with the keyboard over USB HID.

### OpenRGB

[OpenRGB](https://openrgb.org/) is an open-source RGB lighting control software that supports many keyboards including some Xinmeng models.

1. Install OpenRGB from your distro's package manager or from the [official website](https://openrgb.org/).
2. Connect your Xinmeng M87 keyboard via USB.
3. Launch OpenRGB and check if your keyboard is detected.

## Requirements

- Xinmeng M87 or M87 Pro keyboard
- USB connection

## License

This repository is provided for personal and educational use. The Windows software included is property of its respective owners.
