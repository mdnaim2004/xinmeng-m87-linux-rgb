/*
 * xinmeng_rgb.cpp
 * ================
 * C++ RGB controller for the Xinmeng M87 / M87 Pro keyboard on Linux.
 * Uses libhidapi – no Python or virtual environment required.
 *
 * Build:
 *   make          (uses Makefile)
 *   OR manually:
 *   g++ -std=c++17 -O2 xinmeng_rgb.cpp $(pkg-config --libs --cflags hidapi-hidraw) -o xinmeng_rgb
 *
 * Usage:
 *   ./xinmeng_rgb detect              # Find keyboard
 *   ./xinmeng_rgb effect static --colour 255,0,0
 *   ./xinmeng_rgb effect breathing --colour 0,128,255
 *   ./xinmeng_rgb effect wave
 *   ./xinmeng_rgb effect off
 *   ./xinmeng_rgb send 04010000ff000000
 *   ./xinmeng_rgb guide
 *   ./xinmeng_rgb replay packets/decoded_commands.json
 *
 * Requirements (runtime):
 *   libhidapi-hidraw0   (sudo apt install libhidapi-hidraw0)
 *
 * udev rule (keyboard access without sudo):
 *   sudo cp 99-xinmeng-m87.rules /etc/udev/rules.d/
 *   sudo udevadm control --reload-rules && sudo udevadm trigger
 */

#include <hidapi/hidapi.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

// ============================================================================
// Known VID / PID table
// ============================================================================

struct KnownDevice {
    uint16_t vid;
    uint16_t pid;
    const char* name;
};

static const KnownDevice KNOWN_DEVICES[] = {
    {0x258A, 0x002A, "Xinmeng M87 (Sinowealth)"},
    {0x258A, 0x0049, "Xinmeng M87 Pro"},
    {0x258A, 0x0026, "Xinmeng M87 variant"},
    {0x258A, 0x00C7, "Xinmeng M87 variant"},
    {0x0416, 0xC343, "Xinmeng M87 (Generalplus)"},
    {0x3151, 0x0000, "Xinmeng M87 (generic VID 0x3151)"},
};
static const size_t KNOWN_DEVICES_COUNT = sizeof(KNOWN_DEVICES) / sizeof(KNOWN_DEVICES[0]);

// ============================================================================
// HID protocol constants
// ============================================================================

static constexpr int    HID_REPORT_SIZE = 64;
static constexpr int    RGB_USAGE_PAGE  = 0xFF00;
static constexpr uint8_t REPORT_ID      = 0x04;

// Command codes (Sinowealth-style best-guess; update after capturing real packets)
static constexpr uint8_t CMD_SET_MODE       = 0x01;
static constexpr uint8_t CMD_SET_COLOUR     = 0x02;
static constexpr uint8_t CMD_SET_SPEED      = 0x03;
static constexpr uint8_t CMD_SET_BRIGHTNESS = 0x04;
static constexpr uint8_t CMD_COMMIT         = 0x09;

// Mode codes
static constexpr uint8_t MODE_STATIC    = 0x00;
static constexpr uint8_t MODE_BREATHING = 0x01;
static constexpr uint8_t MODE_WAVE      = 0x02;
static constexpr uint8_t MODE_REACTIVE  = 0x03;
static constexpr uint8_t MODE_RIPPLE    = 0x04;
static constexpr uint8_t MODE_NEON      = 0x05;
static constexpr uint8_t MODE_FLICKER   = 0x06;
static constexpr uint8_t MODE_STARLIGHT = 0x07;
static constexpr uint8_t MODE_OFF       = 0xFF;

// ============================================================================
// Helper: build a 64-byte HID report
// ============================================================================

using Report = std::vector<uint8_t>;

static Report make_report(uint8_t cmd, uint8_t sub,
                          const std::vector<uint8_t>& params = {})
{
    Report r;
    r.push_back(REPORT_ID);
    r.push_back(cmd);
    r.push_back(sub);
    for (uint8_t b : params) r.push_back(b);
    r.resize(HID_REPORT_SIZE, 0x00);
    return r;
}

static Report build_set_mode(uint8_t mode,
                              uint8_t rr = 255, uint8_t gg = 255, uint8_t bb = 255)
{
    return make_report(CMD_SET_MODE, mode, {rr, gg, bb});
}

// build_set_colour: utility function for direct colour commands (used in custom/music scenarios).
[[maybe_unused]]
static Report build_set_colour(uint8_t rr, uint8_t gg, uint8_t bb) {
    return make_report(CMD_SET_COLOUR, 0x00, {rr, gg, bb});
}

static Report build_set_brightness(uint8_t level) {
    return make_report(CMD_SET_BRIGHTNESS, 0x00, {level});
}

static Report build_set_speed(uint8_t speed) {
    return make_report(CMD_SET_SPEED, 0x00, {speed});
}

static Report build_commit() {
    return make_report(CMD_COMMIT, 0x00);
}

static Report build_turn_off() {
    return build_set_mode(MODE_OFF);
}

// ============================================================================
// Hex helpers
// ============================================================================

// bytes_to_hex: utility function for debug output.
[[maybe_unused]]
static std::string bytes_to_hex(const Report& r) {
    std::ostringstream oss;
    for (size_t i = 0; i < r.size(); i++) {
        if (i) oss << ' ';
        oss << std::hex << std::uppercase << std::setw(2) << std::setfill('0')
            << static_cast<int>(r[i]);
    }
    return oss.str();
}

static std::optional<std::vector<uint8_t>> hex_string_to_bytes(const std::string& hex) {
    std::string clean;
    for (char c : hex) {
        if (c != ' ' && c != ':' && c != '-') clean += c;
    }
    if (clean.size() % 2 != 0) return std::nullopt;
    std::vector<uint8_t> out;
    out.reserve(clean.size() / 2);
    for (size_t i = 0; i < clean.size(); i += 2) {
        char buf[3] = {clean[i], clean[i+1], '\0'};
        char* end;
        unsigned long val = std::strtoul(buf, &end, 16);
        if (*end != '\0') return std::nullopt;
        out.push_back(static_cast<uint8_t>(val));
    }
    return out;
}

// ============================================================================
// Device detection
// ============================================================================

struct DeviceInfo {
    uint16_t    vid;
    uint16_t    pid;
    std::string name;
    std::string path;
    int         interface_number;
    uint16_t    usage_page;
    uint16_t    usage;
    std::string manufacturer;
    std::string product;
};

static std::string wchar_to_string(const wchar_t* ws) {
    if (!ws) return "";
    std::string s;
    while (*ws) {
        wchar_t c = *ws++;
        if (c < 128) s += static_cast<char>(c);
        else s += '?';
    }
    return s;
}

// List ALL HID devices on the system
static std::vector<DeviceInfo> list_all_hid_devices() {
    std::vector<DeviceInfo> result;
    struct hid_device_info* devs = hid_enumerate(0, 0);
    for (struct hid_device_info* d = devs; d; d = d->next) {
        DeviceInfo info;
        info.vid              = d->vendor_id;
        info.pid              = d->product_id;
        info.path             = d->path ? d->path : "";
        info.interface_number = d->interface_number;
        info.usage_page       = d->usage_page;
        info.usage            = d->usage;
        info.manufacturer     = wchar_to_string(d->manufacturer_string);
        info.product          = wchar_to_string(d->product_string);
        result.push_back(info);
    }
    hid_free_enumeration(devs);
    return result;
}

// Find known Xinmeng devices; return the RGB-interface entry
static std::vector<DeviceInfo> find_known_devices() {
    std::vector<DeviceInfo> result;
    for (size_t k = 0; k < KNOWN_DEVICES_COUNT; k++) {
        const KnownDevice& kd = KNOWN_DEVICES[k];
        struct hid_device_info* devs = hid_enumerate(kd.vid, kd.pid);
        if (!devs) continue;

        // Prefer vendor-specific usage page (0xFF00); fall back to the
        // highest interface number; seed with the first node so that a
        // path is always chosen when devs is non-null.
        struct hid_device_info* best = devs;
        int best_iface = devs->interface_number;
        for (struct hid_device_info* d = devs; d; d = d->next) {
            if (d->usage_page == RGB_USAGE_PAGE) {
                best = d;
                break;
            }
            if (d->interface_number > best_iface) {
                best_iface = d->interface_number;
                best = d;
            }
        }
        if (best) {
            DeviceInfo info;
            info.vid              = best->vendor_id;
            info.pid              = best->product_id;
            info.name             = kd.name;
            info.path             = best->path ? best->path : "";
            info.interface_number = best->interface_number;
            info.usage_page       = best->usage_page;
            info.usage            = best->usage;
            info.manufacturer     = wchar_to_string(best->manufacturer_string);
            info.product          = wchar_to_string(best->product_string);
            result.push_back(info);
        }
        hid_free_enumeration(devs);
    }
    return result;
}

static void print_device_table(const std::vector<DeviceInfo>& devs,
                                const std::string& title) {
    std::cout << "\n" << std::string(60, '=') << "\n";
    std::cout << "  " << title << "\n";
    std::cout << std::string(60, '=') << "\n";
    if (devs.empty()) {
        std::cout << "  (none found)\n";
        return;
    }
    for (size_t i = 0; i < devs.size(); i++) {
        const auto& d = devs[i];
        std::cout << "\n  [" << (i+1) << "]"
                  << " VID=0x" << std::hex << std::uppercase << std::setw(4) << std::setfill('0') << d.vid
                  << "  PID=0x" << std::setw(4) << d.pid << std::dec << "\n";
        if (!d.name.empty())         std::cout << "       Name      : " << d.name << "\n";
        if (!d.manufacturer.empty()) std::cout << "       Mfr       : " << d.manufacturer << "\n";
        if (!d.product.empty())      std::cout << "       Product   : " << d.product << "\n";
        if (d.interface_number >= 0) std::cout << "       Interface : " << d.interface_number << "\n";
        if (d.usage_page)
            std::cout << "       UsagePage : 0x"
                      << std::hex << std::uppercase << std::setw(4) << std::setfill('0') << d.usage_page
                      << "  Usage=0x" << std::setw(4) << d.usage << std::dec << "\n";
        if (!d.path.empty())         std::cout << "       Path      : " << d.path << "\n";
    }
    std::cout << "\n";
}

// Save detected device as a simple JSON file
static void save_device_json(const DeviceInfo& d,
                              const std::string& path = "detected_device.json") {
    std::ofstream f(path);
    if (!f.is_open()) {
        std::cerr << "[ERROR] Failed to open " << path << " for writing.\n";
        return;
    }
    f << "[\n  {\n"
      << "    \"vid\": " << d.vid << ",\n"
      << "    \"pid\": " << d.pid << ",\n"
      << "    \"name\": \"" << d.name << "\",\n"
      << "    \"path\": \"" << d.path << "\",\n"
      << "    \"interface\": " << d.interface_number << "\n"
      << "  }\n]\n";
    if (!f.good()) {
        std::cerr << "[ERROR] Failed to write to " << path << ".\n";
        return;
    }
    std::cout << "[✓] Device info saved to: " << path << "\n";
}

// Load VID/PID from detected_device.json (minimal parser)
static bool load_device_json(uint16_t& vid, uint16_t& pid,
                              const std::string& path = "detected_device.json") {
    std::ifstream f(path);
    if (!f) return false;
    std::string content((std::istreambuf_iterator<char>(f)),
                         std::istreambuf_iterator<char>());

    auto parse_val = [&](const std::string& key) -> std::optional<int> {
        std::string search = "\"" + key + "\": ";
        auto pos = content.find(search);
        if (pos == std::string::npos) return std::nullopt;
        pos += search.size();
        try { return std::stoi(content.substr(pos)); }
        catch (...) { return std::nullopt; }
    };

    auto v = parse_val("vid");
    auto p = parse_val("pid");
    if (!v || !p) return false;
    vid = static_cast<uint16_t>(*v);
    pid = static_cast<uint16_t>(*p);
    return true;
}

// ============================================================================
// Phase 1 – detect command
// ============================================================================

static int cmd_detect(bool list_all, bool no_save,
                       const std::string& save_path) {
    std::cout << "\n" << std::string(60, '=') << "\n";
    std::cout << "  Xinmeng M87 Linux RGB — Device Detection\n";
    std::cout << std::string(60, '=') << "\n";

    if (list_all) {
        auto all = list_all_hid_devices();
        print_device_table(all, "All HID Devices on System");
        return 0;
    }

    std::cout << "\n[*] Scanning for known Xinmeng / Sinowealth devices...\n";
    auto known = find_known_devices();
    if (!known.empty()) {
        std::cout << "[✓] Found " << known.size() << " known device interface(s)!\n";
        print_device_table(known, "Known Keyboard Interfaces");
        if (!no_save) save_device_json(known[0], save_path);
        return 0;
    }

    std::cout << "[!] Keyboard not found in known list.\n";
    std::cout << "    Listing ALL connected HID devices so you can identify yours:\n";
    auto all = list_all_hid_devices();
    print_device_table(all, "All Connected HID Devices");
    if (all.empty()) {
        std::cout << "\n[!] No HID devices found at all.\n";
        std::cout << "    Make sure the keyboard is plugged in and udev rules are set.\n";
        std::cout << "    Install udev rule: sudo cp 99-xinmeng-m87.rules /etc/udev/rules.d/\n";
        std::cout << "    Then: sudo udevadm control --reload-rules && sudo udevadm trigger\n";
    } else {
        std::cout << "\n[!] Identify your keyboard in the list above.\n";
        std::cout << "    Then add its VID/PID to the KNOWN_DEVICES table in xinmeng_rgb.cpp.\n";
    }
    return 1;
}

// ============================================================================
// HID device wrapper
// ============================================================================

class M87HIDDevice {
public:
    explicit M87HIDDevice(uint16_t vid, uint16_t pid)
        : vid_(vid), pid_(pid), dev_(nullptr) {}

    ~M87HIDDevice() { close(); }

    bool open() {
        // Find the right interface path
        struct hid_device_info* devs = hid_enumerate(vid_, pid_);
        if (!devs) {
            std::fprintf(stderr,
                "[ERROR] Device VID=0x%04X PID=0x%04X not found.\n"
                "        Run './xinmeng_rgb detect' first.\n",
                vid_, pid_);
            return false;
        }

        // Prefer vendor-specific usage page (0xFF00); fall back to the
        // highest interface number; seed with the first node so that a
        // path is always chosen when devs is non-null.
        const char* best_path = devs->path;
        int best_iface = devs->interface_number;
        for (auto* d = devs; d; d = d->next) {
            if (d->usage_page == RGB_USAGE_PAGE) {
                best_path = d->path;
                break;
            }
            if (d->interface_number > best_iface) {
                best_iface = d->interface_number;
                best_path  = d->path;
            }
        }

        if (best_path) {
            dev_ = hid_open_path(best_path);
        }
        hid_free_enumeration(devs);

        if (!dev_) {
            const wchar_t* err = hid_error(nullptr);
            if (err) {
                std::wcerr << L"[ERROR] Cannot open HID device: " << err << L"\n";
            } else {
                std::cerr << "[ERROR] Cannot open HID device.\n";
            }
            std::cerr << "        If you get \"Permission denied\", install the udev rule:\n"
                         "          sudo cp 99-xinmeng-m87.rules /etc/udev/rules.d/\n"
                         "          sudo udevadm control --reload-rules && sudo udevadm trigger\n"
                         "          sudo usermod -aG input $USER\n"
                         "        Then log out and back in.\n";
            return false;
        }
        hid_set_nonblocking(dev_, 0);
        return true;
    }

    void close() {
        if (dev_) { hid_close(dev_); dev_ = nullptr; }
    }

    // Send one HID report (64 bytes).
    // hidapi hid_write() expects the buffer to already start with the Report ID
    // (or 0x00 in byte 0 if the device does not use report IDs).
    bool send(const Report& report) {
        if (!dev_) return false;
        Report r = report;
        r.resize(HID_REPORT_SIZE, 0x00);

        int written = hid_write(dev_, r.data(), r.size());
        if (written < 0) {
            const wchar_t* err = hid_error(dev_);
            if (err) std::wcerr << L"[ERROR] Write failed: " << err << L"\n";
            else     std::cerr  << "[ERROR] Write failed.\n";
            return false;
        }
        if (written != static_cast<int>(r.size())) {
            std::cerr << "[ERROR] Incomplete HID write: wrote "
                      << written << " of " << r.size() << " bytes.\n";
            return false;
        }
        return true;
    }

    bool send_all(const std::vector<Report>& reports,
                  unsigned delay_ms = 20) {
        int sent = 0;
        for (const auto& r : reports) {
            if (send(r)) sent++;
            std::this_thread::sleep_for(std::chrono::milliseconds(delay_ms));
        }
        std::printf("[✓] Sent %d/%zu report(s)\n", sent, reports.size());
        return sent == static_cast<int>(reports.size());
    }

private:
    uint16_t    vid_;
    uint16_t    pid_;
    hid_device* dev_;
};

// ============================================================================
// High-level send helper (loads VID/PID from JSON if not provided)
// ============================================================================

static bool send_command(const std::vector<Report>& reports,
                          uint16_t vid = 0, uint16_t pid = 0) {
    if (vid == 0 || pid == 0) {
        if (!load_device_json(vid, pid)) {
            std::cerr << "[ERROR] No device info found. "
                         "Run './xinmeng_rgb detect' first.\n";
            return false;
        }
    }
    M87HIDDevice dev(vid, pid);
    if (!dev.open()) return false;
    return dev.send_all(reports);
}

// ============================================================================
// Phase 5 – RGB effects
// ============================================================================

struct EffectArgs {
    uint8_t  r          = 255;
    uint8_t  g          = 255;
    uint8_t  b          = 255;
    uint8_t  speed      = 2;
    uint8_t  brightness = 4;
    uint16_t vid        = 0;
    uint16_t pid        = 0;
};

static std::vector<Report> effect_static(const EffectArgs& a) {
    return {
        build_set_mode(MODE_STATIC, a.r, a.g, a.b),
        build_set_brightness(a.brightness),
        build_commit(),
    };
}

static std::vector<Report> effect_breathing(const EffectArgs& a) {
    return {
        build_set_mode(MODE_BREATHING, a.r, a.g, a.b),
        build_set_speed(a.speed),
        build_set_brightness(a.brightness),
        build_commit(),
    };
}

static std::vector<Report> effect_wave(const EffectArgs& a) {
    return {
        build_set_mode(MODE_WAVE),
        build_set_speed(a.speed),
        build_set_brightness(a.brightness),
        build_commit(),
    };
}

static std::vector<Report> effect_rainbow(const EffectArgs& a) {
    return effect_wave(a);
}

static std::vector<Report> effect_reactive(const EffectArgs& a) {
    return {
        build_set_mode(MODE_REACTIVE, a.r, a.g, a.b),
        build_set_speed(a.speed),
        build_commit(),
    };
}

static std::vector<Report> effect_ripple(const EffectArgs& a) {
    return {
        build_set_mode(MODE_RIPPLE, a.r, a.g, a.b),
        build_set_speed(a.speed),
        build_commit(),
    };
}

static std::vector<Report> effect_neon(const EffectArgs& a) {
    return {
        build_set_mode(MODE_NEON),
        build_set_speed(a.speed),
        build_set_brightness(a.brightness),
        build_commit(),
    };
}

static std::vector<Report> effect_starlight(const EffectArgs& a) {
    return {
        build_set_mode(MODE_STARLIGHT, a.r, a.g, a.b),
        build_set_speed(a.speed),
        build_commit(),
    };
}

static std::vector<Report> effect_off(const EffectArgs&) {
    return {build_turn_off()};
}

struct EffectEntry {
    const char* name;
    const char* desc;
    std::vector<Report> (*fn)(const EffectArgs&);
};

static const EffectEntry EFFECTS[] = {
    {"static",    "Solid single colour (use --colour R,G,B)",            effect_static},
    {"breathing", "Fade in/out on a colour (use --colour R,G,B)",        effect_breathing},
    {"wave",      "Rainbow wave across keyboard",                         effect_wave},
    {"rainbow",   "Full-spectrum colour cycle",                           effect_rainbow},
    {"reactive",  "Light up on keypress (use --colour R,G,B)",           effect_reactive},
    {"ripple",    "Ripple from keypress (use --colour R,G,B)",           effect_ripple},
    {"neon",      "Neon colour shift",                                    effect_neon},
    {"starlight", "Random twinkling (use --colour R,G,B)",               effect_starlight},
    {"off",       "Turn all lights off",                                  effect_off},
};
static const size_t EFFECTS_COUNT = sizeof(EFFECTS) / sizeof(EFFECTS[0]);

static void list_effects() {
    std::cout << "\nAvailable RGB effects:\n";
    std::cout << std::string(55, '-') << "\n";
    for (size_t i = 0; i < EFFECTS_COUNT; i++) {
        std::printf("  %-12s  %s\n", EFFECTS[i].name, EFFECTS[i].desc);
    }
    std::cout << "\n";
}

// Parse "255,0,128" → r,g,b
static bool parse_colour(const std::string& s, uint8_t& r, uint8_t& g, uint8_t& b) {
    std::istringstream ss(s);
    int ri, gi, bi;
    char c1, c2;
    if (!(ss >> ri >> c1 >> gi >> c2 >> bi)) return false;
    if (c1 != ',' || c2 != ',') return false;
    if (ri < 0 || ri > 255 || gi < 0 || gi > 255 || bi < 0 || bi > 255) return false;
    r = static_cast<uint8_t>(ri);
    g = static_cast<uint8_t>(gi);
    b = static_cast<uint8_t>(bi);
    return true;
}

// Parse "#RRGGBB" or "RRGGBB"
static bool parse_hex_colour(const std::string& s, uint8_t& r, uint8_t& g, uint8_t& b) {
    std::string hex = s;
    if (!hex.empty() && hex[0] == '#') hex = hex.substr(1);
    if (hex.size() != 6) return false;
    auto parse = [&](const std::string& h) -> std::optional<uint8_t> {
        char* end;
        unsigned long v = std::strtoul(h.c_str(), &end, 16);
        if (*end || v > 255) return std::nullopt;
        return static_cast<uint8_t>(v);
    };
    auto rv = parse(hex.substr(0, 2));
    auto gv = parse(hex.substr(2, 2));
    auto bv = parse(hex.substr(4, 2));
    if (!rv || !gv || !bv) return false;
    r = *rv; g = *gv; b = *bv;
    return true;
}

static int cmd_effect(const std::string& effect_name, EffectArgs args) {
    if (effect_name.empty() || effect_name == "--list" || effect_name == "list") {
        list_effects();
        return 0;
    }
    const EffectEntry* entry = nullptr;
    for (size_t i = 0; i < EFFECTS_COUNT; i++) {
        if (EFFECTS[i].name == effect_name) { entry = &EFFECTS[i]; break; }
    }
    if (!entry) {
        std::cerr << "[ERROR] Unknown effect '" << effect_name << "'.\n";
        list_effects();
        return 1;
    }
    std::printf("[*] Applying effect: %s  colour=(%u,%u,%u)  speed=%u  brightness=%u\n",
                effect_name.c_str(), args.r, args.g, args.b, args.speed, args.brightness);
    auto reports = entry->fn(args);
    return send_command(reports, args.vid, args.pid) ? 0 : 1;
}

// ============================================================================
// Phase 4 – send raw HID report
// ============================================================================

static int cmd_send(const std::string& hex_str, uint16_t vid = 0, uint16_t pid = 0) {
    auto bytes = hex_string_to_bytes(hex_str);
    if (!bytes) {
        std::cerr << "[ERROR] Invalid hex string.\n";
        return 1;
    }
    Report r(*bytes);
    r.resize(HID_REPORT_SIZE, 0x00);
    return send_command({r}, vid, pid) ? 0 : 1;
}

// ============================================================================
// Phase 4 – replay from JSON (simple parser)
// ============================================================================

static int cmd_replay(const std::string& json_path,
                       const std::string& label_filter,
                       uint16_t vid = 0, uint16_t pid = 0) {
    std::ifstream f(json_path);
    if (!f) {
        std::cerr << "[ERROR] File not found: " << json_path << "\n";
        std::cerr << "        Run Phase 3 first (capture + analyze packets).\n";
        return 1;
    }

    // Minimal JSON parser: extract complete JSON objects, then read "hex" and optional "label".
    auto extract_json_string_field = [](const std::string& text,
                                        const std::string& field_name) -> std::optional<std::string> {
        const std::string key = "\"" + field_name + "\"";
        auto field_pos = text.find(key);
        if (field_pos == std::string::npos) return std::nullopt;

        auto colon_pos = text.find(':', field_pos + key.size());
        if (colon_pos == std::string::npos) return std::nullopt;

        auto q1 = text.find('"', colon_pos + 1);
        if (q1 == std::string::npos) return std::nullopt;
        auto q2 = text.find('"', q1 + 1);
        if (q2 == std::string::npos) return std::nullopt;

        return text.substr(q1 + 1, q2 - q1 - 1);
    };

    std::vector<Report> reports;
    std::string line;
    std::string object_text;
    int brace_depth = 0;
    while (std::getline(f, line)) {
        for (char ch : line) {
            if (ch == '{') {
                if (brace_depth == 0) object_text.clear();
                ++brace_depth;
            }

            if (brace_depth > 0) object_text.push_back(ch);

            if (ch == '}' && brace_depth > 0) {
                --brace_depth;
                if (brace_depth == 0) {
                    auto hex = extract_json_string_field(object_text, "hex");
                    if (!hex || hex->empty()) continue;

                    if (!label_filter.empty()) {
                        auto label = extract_json_string_field(object_text, "label");
                        if (!label || label->find(label_filter) == std::string::npos) continue;
                    }

                    auto bytes = hex_string_to_bytes(*hex);
                    if (!bytes || bytes->empty()) continue;
                    Report r(*bytes);
                    r.resize(HID_REPORT_SIZE, 0x00);
                    reports.push_back(r);
                }
            }
        }

        if (brace_depth > 0) object_text.push_back('\n');
    }

    if (reports.empty()) {
        std::cout << "[!] No commands found in " << json_path;
        if (!label_filter.empty()) {
            std::cout << " matching label filter \"" << label_filter << "\"";
        }
        std::cout << "\n";
        return 1;
    }
    std::printf("[*] Replaying %zu command(s) from %s\n", reports.size(), json_path.c_str());
    return send_command(reports, vid, pid) ? 0 : 1;
}

// ============================================================================
// Phase 2 – Windows capture guide
// ============================================================================

static void cmd_guide() {
    const char* guide = R"(
╔══════════════════════════════════════════════════════════════════════════════╗
║      Xinmeng M87 Linux RGB — Windows USB Packet Capture Guide               ║
╚══════════════════════════════════════════════════════════════════════════════╝

Why do we need this?
  The Xinmeng M87 uses a proprietary HID protocol for RGB control. The Windows
  driver knows this protocol but the specification is not public. We capture
  USB packets sent by the official driver on Windows, then replay the same bytes
  on Linux.

═══════════════════════════════════════════════════════════════════════════════
STEP 0 – What you need (Windows PC with official driver installed)
═══════════════════════════════════════════════════════════════════════════════
  • Windows 10/11 PC (VM with USB pass-through also works)
  • Official "M87 keyboard-1.0.0.1.exe" driver installed
  • USBPcap  → https://desowin.org/usbpcap/  (free, open-source)
  • Wireshark → https://www.wireshark.org/   (free, open-source)

═══════════════════════════════════════════════════════════════════════════════
STEP 1 – Install USBPcap + Wireshark
═══════════════════════════════════════════════════════════════════════════════
  1. Download and install USBPcapSetup-*.exe with default settings.
  2. Download and install Wireshark with USBPcap option enabled.
  3. Reboot if prompted.

═══════════════════════════════════════════════════════════════════════════════
STEP 2 – Identify the USB interface for your keyboard
═══════════════════════════════════════════════════════════════════════════════
  1. Open Device Manager → Universal Serial Bus controllers.
  2. Note which USB root hub / controller the keyboard is on.
  3. Open Wireshark → Capture Interfaces → look for USBPcap1 / USBPcap2, etc.
  4. Choose the one associated with your keyboard port.

═══════════════════════════════════════════════════════════════════════════════
STEP 3 – Capture packets
═══════════════════════════════════════════════════════════════════════════════
  1. Start capture on the correct USBPcap interface in Wireshark.
  2. Open the official M87 keyboard driver software.
  3. Change RGB modes (static → breathing → wave, etc.) while capturing.
  4. Stop capture.
  5. Save as: File → Save As → m87_capture.pcapng

═══════════════════════════════════════════════════════════════════════════════
STEP 4 – Export raw bytes from Wireshark (easy method, no scapy needed)
═══════════════════════════════════════════════════════════════════════════════
  1. In Wireshark, filter: usb.transfer_type == 0x01 && usb.dst == "host.0"
     (This shows interrupt OUT packets, host→keyboard.)
  2. File → Export Packet Dissections → As Plain Text → save as bytes.txt
  3. Copy bytes.txt to this Linux machine.

═══════════════════════════════════════════════════════════════════════════════
STEP 5 – Replay on Linux
═══════════════════════════════════════════════════════════════════════════════
  After extracting the raw hex from Wireshark, create a simple JSON file:

    [
      { "label": "static_red", "hex": "04010000ff000000..." },
      { "label": "breathing",  "hex": "04010100ff000000..." }
    ]

  Then replay:
    ./xinmeng_rgb replay packets/decoded_commands.json

  Or send a single raw report:
    ./xinmeng_rgb send "04 01 00 00 ff 00 00 00"

═══════════════════════════════════════════════════════════════════════════════
Known VID/PID combinations:
═══════════════════════════════════════════════════════════════════════════════
  VID=0x258A  PID=0x002A  Xinmeng M87 (Sinowealth)
  VID=0x258A  PID=0x0049  Xinmeng M87 Pro
  VID=0x258A  PID=0x0026  Xinmeng M87 variant
  VID=0x258A  PID=0x00C7  Xinmeng M87 variant
  VID=0x0416  PID=0xC343  Xinmeng M87 (Generalplus)

  If yours differs, add it to KNOWN_DEVICES in xinmeng_rgb.cpp.

)";
    std::cout << guide;
}

// ============================================================================
// Usage / help
// ============================================================================

static void print_usage(const char* prog) {
    std::printf(R"(
Xinmeng M87 Linux RGB Control Tool (C++ / libhidapi)
=====================================================

Usage: %s <command> [options]

Commands:
  detect                   Find Xinmeng M87 keyboard
    --list-all             List every HID device on the system
    --no-save              Do not write detected_device.json
    --save <path>          Save path (default: detected_device.json)

  effect <name>            Apply an RGB lighting effect
    --list                 List all available effects
    --colour R,G,B         Colour as R,G,B (default: 255,255,255)
    --hex-colour RRGGBB    Colour as hex (e.g. FF0000)
    --speed <0-4>          Speed: 0=fast, 4=slow (default: 2)
    --brightness <0-4>     Brightness: 0=off, 4=full (default: 4)
    --vid 0xXXXX           Override Vendor ID
    --pid 0xXXXX           Override Product ID

  send <hex>               Send a raw 64-byte HID report
    --vid 0xXXXX           Override Vendor ID
    --pid 0xXXXX           Override Product ID

  replay <json_file>       Replay captured packets from a JSON file
    --label <filter>       Filter by label substring
    --vid 0xXXXX           Override Vendor ID
    --pid 0xXXXX           Override Product ID

  guide                    Show Windows USB packet capture guide

Examples:
  %s detect
  %s effect static --colour 255,0,0
  %s effect breathing --colour 0,128,255 --speed 1
  %s effect wave --brightness 3
  %s effect rainbow
  %s effect off
  %s send "04 01 00 00 ff 00 00 00"
  %s replay packets/decoded_commands.json
  %s guide

Available effects:
)", prog, prog, prog, prog, prog, prog, prog, prog, prog, prog);
    list_effects();
}

// ============================================================================
// Argument parsing helpers
// ============================================================================

static std::string next_arg(int& i, int argc, char** argv, const char* flag) {
    if (i + 1 >= argc) {
        std::fprintf(stderr, "[ERROR] '%s' requires an argument.\n", flag);
        std::exit(1);
    }
    return argv[++i];
}

static uint16_t parse_vid_pid(const std::string& s, const char* name) {
    char* end;
    unsigned long v = std::strtoul(s.c_str(), &end, 0);
    if (*end || v > 0xFFFF) {
        std::fprintf(stderr, "[ERROR] Invalid %s value: %s\n", name, s.c_str());
        std::exit(1);
    }
    return static_cast<uint16_t>(v);
}

// ============================================================================
// main
// ============================================================================

int main(int argc, char** argv) {
    if (argc < 2) {
        print_usage(argv[0]);
        return 0;
    }

    if (hid_init() != 0) {
        std::cerr << "[ERROR] hidapi initialisation failed.\n";
        return 1;
    }

    std::string cmd = argv[1];
    int ret = 0;

    // ------------------------------------------------------------------
    // detect
    // ------------------------------------------------------------------
    if (cmd == "detect") {
        bool list_all = false;
        bool no_save  = false;
        std::string save_path = "detected_device.json";

        for (int i = 2; i < argc; i++) {
            std::string a = argv[i];
            if (a == "--list-all")      list_all  = true;
            else if (a == "--no-save")  no_save   = true;
            else if (a == "--save")     save_path = next_arg(i, argc, argv, "--save");
            else {
                std::fprintf(stderr, "[ERROR] Unknown option: %s\n", a.c_str());
                ret = 1;
            }
        }
        if (!ret) ret = cmd_detect(list_all, no_save, save_path);

    // ------------------------------------------------------------------
    // effect
    // ------------------------------------------------------------------
    } else if (cmd == "effect") {
        if (argc < 3 || std::string(argv[2]) == "--help" || std::string(argv[2]) == "-h") {
            list_effects();
            hid_exit();
            return 0;
        }
        if (std::string(argv[2]) == "--list") {
            list_effects();
            hid_exit();
            return 0;
        }

        std::string effect_name = argv[2];
        EffectArgs args;
        std::string colour_str;
        std::string hex_colour_str;

        for (int i = 3; i < argc; i++) {
            std::string a = argv[i];
            if (a == "--colour" || a == "--color") {
                colour_str = next_arg(i, argc, argv, a.c_str());
            } else if (a == "--hex-colour" || a == "--hex-color") {
                hex_colour_str = next_arg(i, argc, argv, a.c_str());
            } else if (a == "--speed") {
                std::string speed_str = next_arg(i, argc, argv, "--speed");
                char* end = nullptr;
                long speed = std::strtol(speed_str.c_str(), &end, 10);
                if (end == speed_str.c_str() || *end != '\0' || speed < 0 || speed > 4) {
                    std::cerr << "[ERROR] Invalid --speed value: " << speed_str
                              << "  (expected integer 0-4)\n";
                    ret = 1;
                } else {
                    args.speed = static_cast<uint8_t>(speed);
                }
            } else if (a == "--brightness") {
                std::string brightness_str = next_arg(i, argc, argv, "--brightness");
                char* end = nullptr;
                long brightness = std::strtol(brightness_str.c_str(), &end, 10);
                if (end == brightness_str.c_str() || *end != '\0' || brightness < 0 || brightness > 4) {
                    std::cerr << "[ERROR] Invalid --brightness value: " << brightness_str
                              << "  (expected integer 0-4)\n";
                    ret = 1;
                } else {
                    args.brightness = static_cast<uint8_t>(brightness);
                }
            } else if (a == "--vid") {
                args.vid = parse_vid_pid(next_arg(i, argc, argv, "--vid"), "VID");
            } else if (a == "--pid") {
                args.pid = parse_vid_pid(next_arg(i, argc, argv, "--pid"), "PID");
            } else {
                std::fprintf(stderr, "[WARN] Unknown option: %s\n", a.c_str());
            }
        }

        if (!hex_colour_str.empty()) {
            if (!parse_hex_colour(hex_colour_str, args.r, args.g, args.b)) {
                std::cerr << "[ERROR] Invalid --hex-colour value: " << hex_colour_str << "\n";
                ret = 1;
            }
        } else if (!colour_str.empty()) {
            if (!parse_colour(colour_str, args.r, args.g, args.b)) {
                std::cerr << "[ERROR] Invalid --colour value: " << colour_str
                          << "  (expected R,G,B e.g. 255,0,0)\n";
                ret = 1;
            }
        }

        if (!ret) ret = cmd_effect(effect_name, args);

    // ------------------------------------------------------------------
    // send
    // ------------------------------------------------------------------
    } else if (cmd == "send") {
        if (argc < 3) {
            std::cerr << "[ERROR] 'send' requires hex bytes argument.\n"
                         "        Example: ./xinmeng_rgb send \"04 01 00 00 ff 00 00 00\"\n";
            ret = 1;
        } else {
            std::string hex_str = argv[2];
            uint16_t vid = 0, pid = 0;
            for (int i = 3; i < argc; i++) {
                std::string a = argv[i];
                if (a == "--vid") vid = parse_vid_pid(next_arg(i, argc, argv, "--vid"), "VID");
                else if (a == "--pid") pid = parse_vid_pid(next_arg(i, argc, argv, "--pid"), "PID");
            }
            ret = cmd_send(hex_str, vid, pid);
        }

    // ------------------------------------------------------------------
    // replay
    // ------------------------------------------------------------------
    } else if (cmd == "replay") {
        std::string json_path = "packets/decoded_commands.json";
        std::string label_filter;
        uint16_t vid = 0, pid = 0;

        if (argc >= 3 && argv[2][0] != '-') json_path = argv[2];

        for (int i = (argc >= 3 && argv[2][0] != '-') ? 3 : 2; i < argc; i++) {
            std::string a = argv[i];
            if (a == "--json")    json_path    = next_arg(i, argc, argv, "--json");
            else if (a == "--label") label_filter = next_arg(i, argc, argv, "--label");
            else if (a == "--vid")   vid = parse_vid_pid(next_arg(i, argc, argv, "--vid"), "VID");
            else if (a == "--pid")   pid = parse_vid_pid(next_arg(i, argc, argv, "--pid"), "PID");
        }
        ret = cmd_replay(json_path, label_filter, vid, pid);

    // ------------------------------------------------------------------
    // guide
    // ------------------------------------------------------------------
    } else if (cmd == "guide") {
        cmd_guide();

    // ------------------------------------------------------------------
    // help / unknown
    // ------------------------------------------------------------------
    } else if (cmd == "--help" || cmd == "-h" || cmd == "help") {
        print_usage(argv[0]);
    } else {
        std::fprintf(stderr, "[ERROR] Unknown command: %s\n", cmd.c_str());
        print_usage(argv[0]);
        ret = 1;
    }

    hid_exit();
    return ret;
}
