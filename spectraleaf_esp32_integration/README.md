# SpectraLeaf ESP32 Integration

This folder connects the SpectraLeaf analysis logic with an ESP32 controller.

It contains two parts:

- `firmware/SpectraLeafESP32Cam/SpectraLeafESP32Cam.ino`
  - ESP32-CAM firmware.
  - Moves the filter/camera position with a servo.
  - Captures JPEG images.
  - Exposes HTTP endpoints used by the PC app.

- `auto_capture_analyze.py`
  - PC-side local app/bridge.
  - Calls the ESP32 for 532, 556, 680, 725, 850 and 940 nm captures.
  - Saves the images.
  - Runs the existing SpectraLeaf leaf mask and calibration profile.
  - Writes a session report and `analysis.json`.
  - Serves a dashboard with ESP32 status, manual filter movement, single-band
    preview capture, repeated live preview, automatic full capture, result
    tables, mask preview and saved-session links.

## Expected Flow

1. Put the leaf in the box.
2. Open the PC auto-capture app.
3. Enter the ESP32 IP address.
4. Press `Capture + analyze`.
5. The app calls:

```text
/capture?band=532
/capture?band=556
/capture?band=680
/capture?band=725
/capture?band=850
/capture?band=940
```

6. The app saves all images and computes:

- leaf mask
- raw per-band mean and median brightness
- white-normalized camera values from the calibration profile
- source-curve-compensated values
- spectrometer-equivalent estimates where the calibration allows it
- NDVI / NDRE / GNDVI / CIre-style indices

## ESP32 API

By default the firmware is set for direct connection mode:

```cpp
static const bool AP_MODE = true;
static const char *AP_SSID = "SpectraLeaf-ESP32";
static const char *AP_PASS = "spectraleaf";
```

After flashing, the ESP32 creates its own Wi-Fi network named
`SpectraLeaf-ESP32`. Connect the PC to that network, then use:

```text
http://192.168.4.1
```

No internet or router is required. If you later set `AP_MODE` to `false`, open
the serial monitor and read the ESP32 IP address from your router network.

Useful endpoints:

```text
http://192.168.4.1/status
http://192.168.4.1/bands
http://192.168.4.1/move?band=850
http://192.168.4.1/light?state=on
http://192.168.4.1/light?state=off
http://192.168.4.1/light?state=toggle
http://192.168.4.1/capture?band=850
http://192.168.4.1/capture?band=850&light=auto
```

`/capture?band=850` returns a JPEG image.

## Firmware Configuration

Edit these values at the top of:

```text
firmware/SpectraLeafESP32Cam/SpectraLeafESP32Cam.ino
```

Direct Wi-Fi mode is already enabled by default. To change the hotspot name or
password:

```cpp
static const char *AP_SSID = "SpectraLeaf-ESP32";
static const char *AP_PASS = "spectraleaf";
```

If you want router mode instead, set `AP_MODE=false` and fill in:

```cpp
static const char *WIFI_SSID = "YOUR_WIFI_NAME";
static const char *WIFI_PASS = "YOUR_WIFI_PASSWORD";
```

Set servo pin:

```cpp
static const int SERVO_PIN = 12;
```

Set the light transistor control pin:

```cpp
static const int LIGHT_PIN = 4;
static const bool LIGHT_ACTIVE_HIGH = true;
```

Wire this pin to the transistor gate/base through the correct resistor/driver
for your circuit. If your transistor circuit turns the lamp on when the pin is
LOW, set `LIGHT_ACTIVE_HIGH` to `false`.

Set filter wheel angles:

```cpp
BandPosition BANDS[] = {
  {532, 0},
  {556, 30},
  {680, 60},
  {725, 90},
  {850, 120},
  {940, 150},
};
```

Those angles are placeholders. You must adjust them to match the real physical positions of your filter wheel.

## Arduino Libraries

Use Arduino IDE or PlatformIO with an ESP32 board package.

The sketch uses:

- `esp_camera`
- `WiFi`
- `WebServer`
- `ESP32Servo`

Install `ESP32Servo` from the Arduino Library Manager if it is missing.

Board target for the default pin map:

```text
AI Thinker ESP32-CAM
```

## Start the PC App

From this folder, run:

```bat
start_auto_capture_app.bat
```

Or from the project root:

```bat
python spectraleaf_esp32_integration\auto_capture_analyze.py serve --port 8765
```

Then open:

```text
http://127.0.0.1:8765
```

The dashboard can:

- check the ESP32 connection
- load filter positions from `/bands`
- move to a selected wavelength
- capture one preview image
- run a repeated "live preview" by polling captures
- capture all six bands and analyze them
- show the leaf-mask overlay, band values, indices and calibration outputs
  - open previous saved sessions

- `desktop_app.py`
  - Proper PySide desktop app.
  - Fresh navigation-based control center with Dashboard, Capture, Results,
    Visual review, Sessions and Settings pages.
  - Controls ESP32 status, light/transistor output, filter movement, single
    preview, repeated preview and full automatic capture.
  - After capture it builds a mixed-image JSON input and runs the original
    `run_pipeline` backend, so the normal interpretation, graphs, masks,
    calibration report, suspicious-region outputs and glossary tabs all work.

- `desktop_app_before_redesign.pyc`
  - Runnable backup of the previous desktop GUI before the full redesign.
  - Launch with `start_desktop_app_before_redesign.bat` if you need to compare
    or recover the earlier interface.

## Start the Desktop App

From this folder, run:

```bat
start_spectraleaf_desktop_app.bat
```

Or from the project root:

```bat
python spectraleaf_esp32_integration\desktop_app.py
```

To launch the backup of the previous GUI:

```bat
start_desktop_app_before_redesign.bat
```

The automatic desktop sessions are saved to:

```text
outputs\spectraleaf_desktop_sessions\
```

Each automatic session contains the raw captured band images, a
`mixed_import_spec.json` file, and an `analysis` folder with the standard
SpectraLeaf backend outputs.

## Command Line Capture

If you already know the ESP32 IP:

```bat
python spectraleaf_esp32_integration\auto_capture_analyze.py run --esp32 http://192.168.4.1 --sample test_leaf_1
```

Output is written to:

```text
outputs\esp32_auto_sessions\
```

Each session contains:

- `532.jpg`, `556.jpg`, `680.jpg`, `725.jpg`, `850.jpg`, `940.jpg`
- `leaf_mask_overlay.jpg`
- `analysis.json`
- `report.html`

## Important Hardware Notes

The firmware is a strong starting point, but the exact hardware is still unknown.

Things you must confirm:

- Is the camera actually an ESP32-CAM module, or is the ESP32 only controlling a separate camera?
- Is the position mechanism a servo, stepper motor, or something else?
- Which GPIO pins are wired to the servo/motor driver, LED, and trigger?
- Are the filter angles actually 0/30/60/90/120/150 degrees, or different?

If your ESP32 only controls a motor and the pictures are taken by another camera, the firmware should be changed so `/capture` triggers that external camera instead of using `esp_camera`.
