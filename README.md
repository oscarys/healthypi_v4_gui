<img src="assets/logos_uami_ibero.png" alt="Universidad Autónoma Metropolitana, Unidad Iztapalapa; Universidad Iberoamericana, Campus CDMX" width="420"/>

# HealthyPi v4 Monitor

A PyQt6 desktop application for real-time acquisition, visualisation, and logging of physiological signals from the [ProtoCentral HealthyPi v4](https://github.com/Protocentral/protocentral_healthypi_v4) board.

> Designed by Oscar Yáñez Suárez as a fully open teaching tool — students can add real-time signal processing algorithms through a simple plugin interface.

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL%203.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)](https://python.org)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-41cd52)](https://pypi.org/project/PyQt6/)

---

## Screenshots

![HealthyPi v4 Monitor — main window](assets/gui_main.png)

---

## Features

- **Real-time waveforms** — ECG, Respiration, and PPG IR at 125 Hz via pyqtgraph
- **Vitals panel** — Heart Rate, SpO₂, Respiration Rate, Temperature
- **Lead-on/off indicator** — reads ADS1292R status register directly from the packet
- **Threaded capture** — serial I/O in a daemon thread; the GUI never blocks
- **CSV data logging** — timestamped, auto-named files; plugin signal columns included automatically
- **Plugin interface** — add real-time DSP in a single Python file; plugins can output event annotations, scalar readouts, and continuous waveform signals that appear as extra scrolling plots and CSV columns
- **Adjustable display window** — 2 to 30 seconds of scrolling history
- **Bilingual interface** — English / Spanish, switchable at runtime from *Settings → Language* and remembered between sessions
- **Editable UI layout** — toolbar and panels defined in `.ui` files, editable in Qt Designer
- **Dark theme** throughout

---

## Installation

You need **Python 3.11 or newer** and a USB cable to the HealthyPi v4. Pick your system:

| System | Go to |
|--------|-------|
| Windows 10 / 11 (native) | [Windows](#windows-native) |
| Windows with WSL2 | [Windows + WSL2](#windows-with-wsl2) |
| macOS | [macOS](#macos) |
| Linux | [Linux](#linux) |

Whatever the system, the app is installed inside a **virtual environment**, which avoids most "wrong Python / wrong pip" problems.

### Windows (native)

1. **Install Python 3.11+** from [python.org/downloads](https://www.python.org/downloads/windows/) (recommended) and tick **“Add python.exe to PATH”** on the first installer page.
   The Microsoft Store version also works, but if `python` opens the Store or does nothing, turn off *Settings → Apps → Advanced app settings → App execution aliases → python.exe*, or use the `py` launcher below.
2. **Get the code** — install [Git for Windows](https://git-scm.com/download/win), or download the ZIP from GitHub and unzip it.
3. **Open PowerShell** in the project folder and run:

   ```powershell
   git clone https://github.com/<your-username>/healthypi_v4_gui.git
   cd healthypi_v4_gui
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

   If activation fails with *“running scripts is disabled on this system”*, allow scripts for your user only (no admin needed) and retry:

   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
   ```

   Using **Command Prompt** instead? Activate with `.venv\Scripts\activate.bat`.
4. **Serial driver and port.** Plug in the board, open **Device Manager → Ports (COM & LPT)**. You should see *Silicon Labs CP210x USB to UART Bridge (COMx)*; `COMx` is what you select in the app.
   - No entry, or a yellow warning icon under *Other devices*? Install the [Silicon Labs CP210x driver](https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers) (use the “Universal Windows Driver”), then replug the board.
   - Windows normally needs no special permission to open a COM port. “Access is denied” means **another program already has the port open** (Arduino IDE serial monitor, PuTTY, another instance of this app) — close it.
   - Use a **data** USB cable; charge-only cables show no port at all.
5. Run the app (with the venv active): `python main.py`

> **Next time:** open PowerShell in the folder, run `.\.venv\Scripts\Activate.ps1`, then `python main.py`.

### Windows with WSL2

WSL2 does not see USB devices by default, so the board has to be **forwarded** into Linux with [usbipd-win](https://learn.microsoft.com/windows/wsl/connect-usb). The GUI also needs WSLg (Windows 11, or Windows 10 22H2 with a current WSL).

> **Simplest option:** if you only want to *use* the app, install it natively on Windows (previous section). Use WSL2 only if you specifically want a Linux environment.

1. **In Windows (PowerShell as Administrator), once:**

   ```powershell
   wsl --update
   winget install --interactive --exact dorssel.usbipd-win
   ```

   Restart the terminal afterwards.
2. **Every time you plug the board in** (admin PowerShell):

   ```powershell
   usbipd list                          # find the CP210x line, note its BUSID (e.g. 2-3)
   usbipd bind --busid 2-3              # one time only per device
   usbipd attach --wsl --busid 2-3      # repeat after every replug / reboot
   ```

   While attached, the board **disappears from Windows** (no COM port) and appears in Linux.
3. **In the WSL2 Ubuntu terminal:**

   ```bash
   sudo apt update
   sudo apt install -y python3 python3-venv python3-pip git libxcb-cursor0 libxkbcommon-x11-0 libgl1
   git clone https://github.com/<your-username>/healthypi_v4_gui.git
   cd healthypi_v4_gui
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   sudo usermod -aG dialout $USER       # then run `wsl --shutdown` in PowerShell and reopen Ubuntu
   ls /dev/ttyUSB*                      # should list /dev/ttyUSB0
   python main.py
   ```

   If `/dev/ttyUSB0` is missing, the CP210x kernel module may not be in your WSL kernel; run `wsl --update` and check again. Keep the project inside the Linux filesystem (`~/`), not under `/mnt/c/`, for speed.

### macOS

1. **Install Python 3.11+** (the system Python 3.9 that ships with the Command Line Tools is too old). Either:
   - **Homebrew** (recommended): install from [brew.sh](https://brew.sh), then `brew install python@3.12 git`
   - **python.org** installer: [python.org/downloads/macos](https://www.python.org/downloads/macos/). Then run **Install Certificates.command** (in `/Applications/Python 3.x/`) if pip reports SSL errors.
2. **Install the app:**

   ```bash
   git clone https://github.com/<your-username>/healthypi_v4_gui.git
   cd healthypi_v4_gui
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   python main.py
   ```

   With Homebrew Python, `pip install` outside a venv fails with *“externally-managed-environment”* — the venv above is the fix. Use `python3.12 -m venv .venv` if `python3` still points at an old version (`python3 --version` to check).
3. **Serial port.** Recent macOS includes the CP210x driver, and no permission prompt is needed. The board appears as `/dev/cu.SLAB_USBtoUART` or `/dev/cu.usbserial-XXXX`; choose the **`cu.`** entry (not `tty.`). If no port shows up, install the [Silicon Labs driver](https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers), approve it in *System Settings → Privacy & Security*, and replug.
   On Apple Silicon Macs use a native (arm64) Python; Homebrew and python.org both provide one.

### Linux

```bash
# Debian / Ubuntu (package names differ on other distros)
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git libxcb-cursor0

git clone https://github.com/<your-username>/healthypi_v4_gui.git
cd healthypi_v4_gui
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

- **Serial permission** (`Permission denied: '/dev/ttyUSB0'`): add yourself to the group that owns the port, then **log out and back in**:

  ```bash
  sudo usermod -aG dialout $USER     # Debian/Ubuntu/Fedora; on Arch the group is `uucp`
  groups                             # should now include dialout
  ```
- If the port vanishes seconds after plugging in, `brltty` (braille daemon) or ModemManager may be grabbing it: `sudo apt remove brltty`, or `sudo systemctl disable --now ModemManager`.
- Error *“Could not load the Qt platform plugin “xcb””*: install `libxcb-cursor0` (as above). On Wayland-only systems also try `QT_QPA_PLATFORM=wayland python main.py`.

### Check your installation

With the virtual environment active, run this one-liner. It should print the versions and every serial port the system can see (your board must be among them):

```bash
python -c "import sys, PyQt6.QtCore as q, pyqtgraph, serial, numpy; from serial.tools import list_ports; print(sys.version.split()[0], 'Qt', q.QT_VERSION_STR); [print(p.device, '-', p.description) for p in list_ports.comports()]"
```

Expected output looks like `3.12.4 Qt 6.7.2` followed by e.g. `COM3 - Silicon Labs CP210x USB to UART Bridge (COM3)`.

### Troubleshooting

| Symptom | Likely cause and fix |
|---------|----------------------|
| `python` is not recognised / opens the Microsoft Store (Windows) | Python not on PATH or Store alias intercepting. Use `py -3`, reinstall ticking “Add to PATH”, or disable the App execution alias. |
| `Activate.ps1 cannot be loaded… scripts is disabled` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or use `activate.bat` from Command Prompt. |
| `No matching distribution found for PyQt6` | Python older than 3.9 or a 32-bit Python. Install a 64-bit Python 3.11+. |
| `externally-managed-environment` (macOS/Linux) | You skipped the virtual environment. Create and activate `.venv` first. |
| `ModuleNotFoundError: No module named 'PyQt6'` | The venv is not active, or you installed with a different Python. Activate it and use `python -m pip install -r requirements.txt`. |
| Serial port list is empty | Cable is charge-only, driver missing (Windows/macOS), board not forwarded (WSL2), or board not powered. Replug; the list refreshes automatically. |
| `Permission denied` on `/dev/ttyUSB0` | Not in `dialout`/`uucp` group, or you did not log out and back in. |
| `Access is denied` / `Resource busy` | Another program holds the port. Close serial monitors and other instances of this app. |
| Port opens but no data | Wrong port, or board running different firmware. Baud rate must be 115200; verify the board streams with the Arduino IDE serial monitor, then close it. |
| `xcb` Qt plugin error (Linux/WSL2) | `sudo apt install libxcb-cursor0`. |

---

## Running

With the virtual environment active (`source .venv/bin/activate` or `.\.venv\Scripts\Activate.ps1`):

```bash
python main.py
```

1. Select the correct serial port from the dropdown (`/dev/ttyUSB0`, `COM3`, etc.).
2. Press **Connect**.
3. Attach ECG electrodes and SpO₂ probe — the **LEADS ON** indicator turns green.
4. Press **Record** to start a CSV session; choose a save path when prompted.

> **Recording tip:** Start recording *after* connecting so that all active plugin signal channels are included in the CSV header. Any channel that appears after recording starts will not have a column in that session's file.

---

## Project structure

```
healthypi_v4_gui/
├── main.py                      Entry point — MainWindow, runtime widget wiring
├── requirements.txt
├── ReadHealthyPi4CSVs.ipynb     Jupyter notebook for post-recording analysis
├── ui/
│   ├── main_window.ui           Main window layout (Qt Designer)
│   └── vitals_panel.ui          Vitals group box layout (Qt Designer)
├── core/
│   ├── parser.py                Byte-level FSM packet decoder (PPG polarity here)
│   ├── serial_reader.py         Daemon thread — pyserial + PluginRunner hook
│   ├── logger.py                Thread-safe CSV writer with dynamic signal columns
│   ├── ring_buffer.py           NumPy ring buffer for waveform display
│   ├── plugin_base.py           SignalPlugin ABC, PluginResult, Annotation
│   └── plugin_runner.py         Dispatches on_sample() to registered plugins
├── plugins/
│   ├── r_peak_detector.py       Pan-Tompkins-inspired QRS detector
│   ├── ppg_notch_detector.py    Dicrotic notch detector
│   ├── ecg_fir_filter.py        Windowed-sinc FIR low-pass filter (signal output)
│   └── ecg_passthrough.py       Identity plugin — useful for pipeline debugging
├── resources/
│   └── i18n.py                  Runtime EN/ES dictionary translations — tr(), set_language()
└── assets/
    ├── packet_structure.svg
    └── plugin_flow.svg
```

---

## Serial packet structure

The board streams 27-byte packets at ~125 Hz over USB CDC (115200 baud, 8N1).
Protocol confirmed against the `HealthyPiv4_Pi_only.ino` firmware source.

![Packet structure](assets/packet_structure.svg)

> **PPG polarity:** The AFE4490 raw ADC value is inversely proportional to blood volume. `parser.py` negates both `ppg_ir` and `ppg_red` at decode time so all downstream consumers — plots, logger, plugins — see the physiologically correct convention: systolic peaks deflect upward. This negation is the single source of truth; plugins receive already-corrected values.

---

## Plugin interface

![Plugin data flow](assets/plugin_flow.svg)

Data flows from the board through three stages:

1. **Serial reader thread** — reads raw bytes, feeds the FSM parser, produces `HealthyPiSample` objects at ~125 Hz.
2. **Plugin runner** — still inside the serial thread, calls `on_sample()` on every registered plugin for every sample and enqueues results.
3. **GUI timer** — a `QTimer` fires every 40 ms in the main thread, drains both queues, updates waveform plots, vitals cards, annotation overlays, plugin panel, and logger.

Your plugin code lives entirely in step 2. You never touch the GUI.

### Quick start

1. Create a file in `plugins/`, e.g. `plugins/my_plugin.py`.
2. Subclass `SignalPlugin` and implement `on_sample()`.
3. Register it in `main.py` by adding it to `self._plugins`.

```python
# plugins/my_plugin.py
from core.plugin_base import SignalPlugin, PluginResult, Annotation

class MyPlugin(SignalPlugin):
    name    = "My plugin"   # shown in the plugin panel
    enabled = False   # plugins start unchecked; the user switches them on

    def on_connect(self, sample_rate: float) -> None:
        self.fs = sample_rate   # initialise filter state here

    def on_sample(self, t: float, sample) -> PluginResult | None:
        # called at ~125 Hz in the serial reader thread
        filtered = ...   # your processing here

        return PluginResult(
            annotations=[Annotation(channel="ecg", label="R", color="#ff4757")],
            scalars={"my_value": 42.0},
            signals={"my_signal": filtered},
        )

    def on_disconnect(self) -> None:
        pass   # release state if needed
```

```python
# main.py
from plugins.my_plugin import MyPlugin
self._plugins = [RPeakDetector(), DicroticNotchDetector(), ECGFIRFilter(), MyPlugin()]
```

### `SignalPlugin` — base class

```python
class SignalPlugin(ABC):
    name:    str    # shown in the GUI panel
    enabled: bool   # default False (starts unchecked); user can toggle at runtime
```

| Method | When called | Thread |
|--------|-------------|--------|
| `on_connect(sample_rate)` | Serial port opens | Serial thread |
| `on_sample(t, sample)` | Every decoded packet (~125 Hz) | Serial thread |
| `on_disconnect()` | Serial port closes | Serial thread |

### `HealthyPiSample` — the data object

```python
@dataclass
class HealthyPiSample:
    ecg:          int    # int16 — filtered ECG ADC count
    respiration:  int    # int16 — chest impedance ADC count
    ppg_ir:       int    # int32 — PPG infrared (polarity corrected, peaks up)
    ppg_red:      int    # int32 — PPG red channel (polarity corrected)
    temperature:  float  # °C
    resp_rate:    int    # BPM — FFT-derived on the board
    spo2:         int    # %
    heart_rate:   int    # BPM
    bp_sys:       int    # placeholder — firmware hardcodes 80
    bp_dia:       int    # placeholder — firmware hardcodes 120
    status:       int    # ADS1292R status register byte
    leads_on:     bool   # True when (status & 0x1F) == 0
```

### `PluginResult` — what you return

```python
@dataclass
class PluginResult:
    annotations: list[Annotation]  = []   # event markers on the waveform plots
    scalars:     dict[str, float]  = {}   # named values in the plugin panel
    signals:     dict[str, float]  = {}   # continuous waveform values
```

All three fields are optional — return only what you need.

**`Annotation`** — draws a dashed vertical line with a label on a hardware waveform plot. Positioning is automatic: the marker is placed at the sample being processed when `on_sample()` returned, scrolls in lockstep with the waveform, and expires after 10 seconds.

```python
Annotation(
    channel = "ecg",       # "ecg" | "respiration" | "ppg_ir" | "ppg_red"
    label   = "R",         # ≤ 8 chars recommended
    color   = "#ff4757",   # HTML colour
)
```

**`scalars`** — key/value pairs displayed in the plugin panel. Rows appear the first time a key is seen and update on every subsequent result.

**`signals`** — continuous waveform output. Each key creates a new scrolling plot below the hardware plots the first time it appears, and adds a column to the CSV log. The output channel name is derived from the plugin `name` attribute by default (lowercase, spaces → underscores), or set explicitly as the dict key.

### Threading rules

`on_sample()` runs in the **serial reader thread**, not the GUI thread.

| You can | You must not |
|---------|--------------|
| Use NumPy arrays (releases the GIL) | Touch any `QWidget` or Qt object |
| Maintain `self` state | Call `QTimer`, `QApplication`, etc. |
| Use `collections.deque` | Block for I/O or `time.sleep()` |
| Raise exceptions (caught and printed) | Take more than ~1 ms per call |

There is an inherent ~40 ms latency between `on_sample()` firing and the GUI updating (one `QTimer` tick). For annotations this is handled transparently — each result carries a `sample_index` counter that stays in lockstep with the ring buffer, so markers land on the correct sample regardless of when the result is processed.

---

## Included plugins

### R-peak detector (`plugins/r_peak_detector.py`)

Simplified Pan-Tompkins QRS detector operating on the ECG channel.

Pipeline: `ECG → low-pass MA → derivative → square → integrator → adaptive threshold → refractory`

Key parameters:

```python
REFRACTORY_MS   = 200    # min ms between R peaks
THRESHOLD_COEF  = 0.45   # fraction of running max used as threshold
LP_ORDER        = 5      # low-pass filter length (samples)
INT_ORDER       = 15     # integrator length (samples)
```

Returns an `"R"` annotation on the ECG plot and `RR interval (ms)` / `HR from RR (BPM)` scalars on each detection.

### Dicrotic notch detector (`plugins/ppg_notch_detector.py`)

Detects systolic peaks and dicrotic notch on the PPG IR channel. The dicrotic notch is the brief secondary dip caused by aortic valve closure, visible on the descending limb of each pulse.

Pipeline: `PPG IR → Gaussian smooth → 1st derivative → peak detection → notch search`

Key parameters:

```python
SMOOTH_ORDER           = 9     # Gaussian MA window (samples, odd)
NOTCH_SEARCH_START_MS  = 150   # search window start after systolic peak
NOTCH_SEARCH_END_MS    = 500   # search window end
PEAK_THRESHOLD_COEF    = 0.40  # min amplitude fraction to accept a peak
```

Returns `"SP"` (systolic peak) and `"DN"` (dicrotic notch) annotations on the PPG plot, and `PPG systolic amp` / `Notch/peak ratio` scalars.

### FIR low-pass filter (`plugins/ecg_fir_filter.py`)

Windowed-sinc (Hamming) linear-phase FIR filter on the ECG channel. Outputs the filtered waveform as a plugin signal plot and CSV column. Unlike a moving average, this has a well-defined frequency response with a flat passband — P waves and QRS morphology are preserved up to the cutoff frequency.

Key parameters:

```python
CUTOFF_HZ = 40.0   # low-pass cutoff frequency in Hz
NUM_TAPS  = 9      # filter length — more taps = sharper transition, more delay
                   # group delay = (NUM_TAPS - 1) / 2 samples
```

Accepts constructor arguments so multiple instances can compare cutoffs side by side:

```python
from plugins.ecg_fir_filter import ECGFIRFilter
self._plugins = [
    ...,
    ECGFIRFilter(name="ECG FIR 40 Hz", cutoff_hz=40),
    ECGFIRFilter(name="ECG FIR 20 Hz", cutoff_hz=20),
]
```

### Passthrough (`plugins/ecg_passthrough.py`)

Copies raw ECG to a signal output with no processing. Useful for verifying the display pipeline: if the passthrough plot matches the ECG plot exactly, any distortion seen in another plugin is in that plugin's algorithm, not in the framework.

---

## Analysing recorded CSV files

A Jupyter notebook is included to get you started with post-recording analysis:

```
ReadHealthyPi4CSVs.ipynb
```

It demonstrates how to load a recording into a pandas DataFrame, inspect the available columns (including any plugin signal columns such as `ecg_fir_filter`), and produce basic plots — ECG raw vs filtered, and scaled/mean-removed PPG IR and Red channels side by side.

**Requirements:**

```bash
pip install jupyter numpy pandas matplotlib
jupyter notebook ReadHealthyPi4CSVs.ipynb
```

Set the `FILE` variable in the first cell to the path of your recording before running.

---

## UI layout files

The main window layout and vitals panel are defined in `.ui` files under `ui/` and loaded at runtime with `PyQt6.uic.loadUi()`. You can open and edit them in Qt Designer without touching Python.

```
ui/main_window.ui    QMainWindow — toolbar, three-column central layout, status bar
ui/vitals_panel.ui   Vitals group box — vital card placeholders, session stats grid
```

The plots area and plugin panel are built at runtime from plugin registration data and are therefore not described in `.ui` files.

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| PyQt6 | ≥ 6.4 | GUI framework |
| pyqtgraph | ≥ 0.13 | Real-time waveform plots |
| pyserial | ≥ 3.5 | Serial port I/O |
| numpy | ≥ 1.23 | Ring buffer, DSP in plugins |

---

## License

GPL-3.0 — see [LICENSE](LICENSE).

Hardware protocol details are based on the [ProtoCentral HealthyPi v4](https://github.com/Protocentral/protocentral_healthypi_v4) firmware, released under the MIT License.
