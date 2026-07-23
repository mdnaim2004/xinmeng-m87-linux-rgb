#!/usr/bin/env python3
"""
music_visualizer.py
===================
Real-time audio visualizer & Web UI for Xinmeng M87 Pro v2 keyboards on Linux.
Serves a modern glassmorphic dashboard on http://localhost:8080.
"""

import sys
import os
import json
import subprocess
import math
import time
import struct
import colorsys
import signal
import threading
import queue
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Configuration
PORT = 8080
LATENCY_MS = 20
SAMPLE_RATE = 11025
CHUNK_SIZE = 512  # 256 samples, ~23ms chunks

# Command codes matching C++ tool
CMD_SET_MODE = 0x01
CMD_SET_BRIGHTNESS = 0x04
CMD_COMMIT = 0x09
REPORT_ID = 0x04

# Keyboard hardware modes
MODE_MAP = {
    'static': 0x00,
    'breathing': 0x01,
    'wave': 0x02,
    'reactive': 0x03,
    'ripple': 0x04,
    'neon': 0x05,
    'starlight': 0x07,
    'off': 0xFF
}

# Shared state between Web Server and Visualizer thread
class VisualizerState:
    def __init__(self):
        self.mode = 'music'
        self.gain = 1.5
        self.speed = 2
        self.r = 0
        self.g = 255
        self.b = 136
        self.current_r = 0
        self.current_g = 255
        self.current_b = 136
        self.volume = 0.0
        self.device_name = "Xinmeng M87 Pro v2 (Apple mode)"
        self.device_path = ""
        self.clients = set()
        self.lock = threading.Lock()
        self.settings_changed = False

shared_state = VisualizerState()

# Web Server Request Handler
class WebServerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress logging HTTP requests in stdout to keep terminal clean
        return

    def do_GET(self):
        if self.path == '/':
            self.serve_file('web/index.html', 'text/html')
        elif self.path == '/style.css':
            self.serve_file('web/style.css', 'text/css')
        elif self.path == '/app.js':
            self.serve_file('web/app.js', 'application/javascript')
        elif self.path == '/api/stream':
            self.handle_sse()
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        if self.path == '/api/control':
            self.handle_control()
        else:
            self.send_error(404, "Not Found")

    def serve_file(self, filepath, content_type):
        if not os.path.exists(filepath):
            self.send_error(404, "File Not Found")
            return
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store, must-revalidate')
        self.end_headers()
        with open(filepath, 'rb') as f:
            self.wfile.write(f.read())

    def handle_sse(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        # Queue client connection
        client_queue = queue.Queue(maxsize=10)
        with shared_state.lock:
            shared_state.clients.add(client_queue)

        # Push initial device and state
        initial_device = {
            "type": "device",
            "device": {
                "name": shared_state.device_name,
                "path": shared_state.device_path
            }
        }
        initial_state = {
            "type": "state",
            "state": {
                "mode": shared_state.mode,
                "gain": shared_state.gain,
                "speed": shared_state.speed,
                "color": f"#{shared_state.r:02x}{shared_state.g:02x}{shared_state.b:02x}"
            }
        }
        try:
            self.wfile.write(f"data: {json.dumps(initial_device)}\n\n".encode())
            self.wfile.write(f"data: {json.dumps(initial_state)}\n\n".encode())
            self.wfile.flush()
        except Exception:
            with shared_state.lock:
                shared_state.clients.discard(client_queue)
            return

        while True:
            try:
                # Block for next event (max 2 seconds to keep connection alive)
                event_data = client_queue.get(timeout=2.0)
                self.wfile.write(f"data: {json.dumps(event_data)}\n\n".encode())
                self.wfile.flush()
            except queue.Empty:
                try:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                except Exception:
                    break
            except Exception:
                break

        with shared_state.lock:
            shared_state.clients.discard(client_queue)

    def handle_control(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        try:
            params = json.loads(post_data.decode('utf-8'))
            with shared_state.lock:
                shared_state.mode = params.get('mode', shared_state.mode)
                shared_state.gain = params.get('gain', shared_state.gain)
                shared_state.speed = params.get('speed', shared_state.speed)
                shared_state.r = params.get('r', shared_state.r)
                shared_state.g = params.get('g', shared_state.g)
                shared_state.b = params.get('b', shared_state.b)
                shared_state.settings_changed = True
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        except Exception as e:
            self.send_error(400, f"Bad Request: {e}")

# Keyboard helpers
def get_keyboard_path():
    json_path = "detected_device.json"
    if not os.path.exists(json_path):
        print("[ERROR] detected_device.json not found. Run './xinmeng_rgb detect' first.")
        sys.exit(1)
    
    try:
        with open(json_path, "r") as f:
            devices = json.load(f)
            if devices and isinstance(devices, list):
                shared_state.device_name = devices[0].get("name")
                shared_state.device_path = devices[0].get("path")
                return shared_state.device_path
    except Exception as e:
        print(f"[ERROR] Failed to parse detected_device.json: {e}")
        sys.exit(1)
    
    print("[ERROR] No valid device path found in detected_device.json")
    sys.exit(1)

def build_report(cmd, sub, params=None):
    report = bytearray(64)
    report[0] = REPORT_ID
    report[1] = cmd
    report[2] = sub
    if params:
        for idx, val in enumerate(params):
            if idx + 3 < 64:
                report[idx + 3] = val
    return report

def apply_keyboard_settings(fd, mode, r, g, b, speed):
    commit_report = build_report(CMD_COMMIT, 0x00)
    
    if mode == 'music':
        # Music mode uses static template as base
        init_mode = build_report(CMD_SET_MODE, 0x00, [r, g, b])
        fd.write(init_mode)
        fd.write(commit_report)
    elif mode in MODE_MAP:
        hardware_mode = MODE_MAP[mode]
        if hardware_mode == 0xFF:
            # Turn off
            off_report = build_report(CMD_SET_MODE, 0xFF)
            fd.write(off_report)
            fd.write(commit_report)
        else:
            mode_report = build_report(CMD_SET_MODE, hardware_mode, [r, g, b])
            speed_report = build_report(0x03, 0x00, [speed])
            brightness_report = build_report(CMD_SET_BRIGHTNESS, 0x00, [0x04]) # Level 4
            
            fd.write(mode_report)
            if mode in ['breathing', 'wave', 'neon', 'ripple', 'reactive']:
                fd.write(speed_report)
            if mode in ['static', 'breathing', 'wave', 'neon']:
                fd.write(brightness_report)
            fd.write(commit_report)

# Server running target
def start_web_server():
    server_address = ('', PORT)
    httpd = ThreadingHTTPServer(server_address, WebServerHandler)
    print(f"[✓] Web server started on http://localhost:{PORT}")
    
    # Auto-open browser
    threading.Thread(target=lambda: (time.sleep(1), webbrowser.open(f"http://localhost:{PORT}"))).start()
    
    try:
        httpd.serve_forever()
    except Exception:
        pass

def main():
    path = get_keyboard_path()
    print(f"[*] Keyboard target node: {path}")

    # Open device node
    try:
        fd = open(path, "wb", buffering=0)
    except PermissionError:
        print(f"\n[ERROR] Permission denied to write to {path}.")
        print("Please reload the udev rules to grant permission:")
        print("  sudo cp 99-xinmeng-m87.rules /etc/udev/rules.d/")
        print("  sudo udevadm control --reload-rules && sudo udevadm trigger")
        print("\nOr test quickly by running this script as root:")
        print("  sudo python3 music_visualizer.py")
        sys.exit(1)

    print("[✓] Keyboard connection established.")
    
    # Initialise brightness
    init_brightness = build_report(CMD_SET_BRIGHTNESS, 0x00, [0x04])
    init_commit = build_report(CMD_COMMIT, 0x00)
    fd.write(init_brightness)
    fd.write(init_commit)

    # Spawn parec to capture system audio
    cmd = [
        "parec",
        "-d", "@DEFAULT_MONITOR@",
        "--format=s16le",
        "--channels=1",
        f"--rate={SAMPLE_RATE}",
        f"--latency-msec={LATENCY_MS}"
    ]

    print("[*] Launching PulseAudio/PipeWire audio monitor...")
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        print("[ERROR] 'parec' tool not found. Please verify PulseAudio/PipeWire is installed.")
        fd.close()
        sys.exit(1)

    # Start multi-threaded web server
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()

    print("\n" + "=" * 65)
    print("  Xinmeng M87 Linux Web Dashboard Active")
    print(f"  Access the control panel: http://localhost:{PORT}")
    print("  Press Ctrl+C in this terminal to exit")
    print("=" * 65 + "\n")

    # Visualizer state variables
    hue = 0.0
    global_max_rms = 1000.0
    last_update = 0.0

    def sigint_handler(sig, frame):
        print("\n[*] Exiting visualizer, resetting keyboard mode...")
        try:
            proc.terminate()
            # Restore keyboard to a soft cyan static color on exit
            off_mode = build_report(CMD_SET_MODE, 0x00, [0, 150, 180])
            fd.write(off_mode)
            fd.write(init_commit)
            fd.close()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, sigint_handler)

    try:
        while True:
            # Check for settings change from Web UI
            with shared_state.lock:
                changed = shared_state.settings_changed
                current_mode = shared_state.mode
                r = shared_state.r
                g = shared_state.g
                b = shared_state.b
                speed = shared_state.speed
                gain = shared_state.gain

            if changed:
                with shared_state.lock:
                    shared_state.settings_changed = False
                print(f"[*] Applying mode update: mode={current_mode} color=({r},{g},{b}) speed={speed}")
                apply_keyboard_settings(fd, current_mode, r, g, b, speed)

            # If visualizer mode is active, stream audio beats
            if current_mode == 'music':
                # Read chunks of PCM data
                data = proc.stdout.read(CHUNK_SIZE)
                if not data:
                    break

                num_samples = len(data) // 2
                if num_samples == 0:
                    continue

                samples = struct.unpack(f"<{num_samples}h", data[:num_samples * 2])

                # Calculate RMS
                sq_sum = sum(s * s for s in samples)
                rms = math.sqrt(sq_sum / num_samples)

                # Auto-gain decay
                global_max_rms = max(global_max_rms * 0.998, rms, 200.0)
                normalized = min(1.0, rms / global_max_rms)

                # Smoothly cycle colors
                hue = (hue + 0.003) % 1.0

                # Scale value (brightness) and saturation with volume
                val = 0.05 + 0.95 * normalized
                sat = 0.8 + 0.2 * normalized

                # Convert HSV to RGB
                cr, cg, cb = [int(x * 255) for x in colorsys.hsv_to_rgb(hue, sat, val)]

                # Throttled write to keyboard (avoid USB queue clog)
                now = time.time()
                if now - last_update >= 0.025:
                    mode_report = build_report(CMD_SET_MODE, 0x00, [cr, cg, cb])
                    fd.write(mode_report)
                    fd.write(init_commit)
                    last_update = now

                    # Stream data to SSE web clients (downsample to 64 points)
                    event_data = {
                        "type": "audio",
                        "volume": normalized,
                        "samples": list(samples[::4]),
                        "color": {"r": cr, "g": cg, "b": cb}
                    }
                    
                    with shared_state.lock:
                        for q in shared_state.clients:
                            try:
                                q.put_nowait(event_data)
                            except queue.Full:
                                pass

            else:
                # Wait passively if we are not in music mode
                time.sleep(0.05)

    except KeyboardInterrupt:
        pass
    finally:
        sigint_handler(None, None)

if __name__ == "__main__":
    main()
