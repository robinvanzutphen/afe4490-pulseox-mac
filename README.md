# AFE4490 Pulse Oximeter - macOS toolkit

A teaching application for the TI **AFE44x0SPO2EVM** (AFE4490) pulse-oximeter
board. It streams the IR and Red PPG waveforms over the board's USB serial port
(~500 Hz) and walks students from the raw signal to heart rate and an educational
SpO2 estimate. Same program as the Windows version; this folder is the macOS kit.

> Teaching / evaluation only. **Not a medical device**; the displayed SpO2 value
> is not clinically calibrated.

## Important: the `.app` is built on macOS, not shipped here

A macOS application (`AFE4490_PulseOx.app`) can only be produced on macOS - no tool
can cross-build it from Windows. So unlike the Windows folder, this kit does **not**
contain a ready-made binary. You build it once, then distribute the resulting
`.app`. There are two robust ways, both of which also run the tests and the app's
self-test on real macOS:

- **No Mac available - GitHub Actions.** Push this folder to GitHub and run the
  included workflow; it builds the app for Apple Silicon *and* Intel and gives you
  two downloadable ZIPs.
- **On any Mac - one command:** `bash build_macos.sh`.

Full steps: **[docs/BUILD_THE_APP.md](docs/BUILD_THE_APP.md)**.

After building, put `AFE4490_PulseOx.app` next to `READ ME FIRST.txt` and distribute
that pair.

## Run it (once the `.app` exists)

1. Close any serial-terminal program using the board (the COM/`cu` port is exclusive).
2. Plug the AFE4490 board into USB.
3. Double-click **`AFE4490_PulseOx.app`**. It finds the board automatically (TI USB
   VID `2047`, PID `0300`); otherwise it asks for the `/dev/cu.*` port.
4. Click **Start**.

Recordings are saved to **`~/Documents/AFE4490 PulseOx data`**.

### First launch: "Apple could not verify..." (Gatekeeper)

The app is not signed/notarized with an Apple Developer ID, so on a Mac that
downloaded it, macOS blocks the first launch. The simplest student fix is
**Control-click (right-click) the app -> Open -> Open**, once. Full details and
alternatives are in **[docs/GATEKEEPER.md](docs/GATEKEEPER.md)**.

## Backup: run from Python

If the `.app` will not run on some Mac, run the identical app from its Python source
- double-click **`run_gui_backup.command`**, or use a virtual environment / IDE.
Full steps: **[docs/BACKUP_RUN_FROM_PYTHON.md](docs/BACKUP_RUN_FROM_PYTHON.md)**.

## What's in this folder

| Item | Purpose |
|---|---|
| `build_macos.sh` | Builds `AFE4490_PulseOx.app` on a Mac (venv, tests, self-test, ZIP). |
| `.github/workflows/build-macos.yml` | Builds the app on GitHub's macOS runners (no Mac needed). |
| `run_gui_backup.command` | Backup launcher: runs the app from Python source. |
| `live_viewer.py` | The application source (same program as the `.app`). |
| `stream_test.py` | Serial-link health check (device ID, firmware, ~500 Hz). |
| `afe/` | Driver package: `serial_link.py`, `registers.py`, `signal_processing.py`. |
| `tests/` | Hardware-free unit tests (run automatically during the build). |
| `requirements.txt` | Runtime packages for the backup path. |
| `requirements-build.txt` | Adds PyInstaller, for building the `.app`. |
| `READ ME FIRST.txt` | One-page student instructions (distribute with the `.app`). |

## Documentation

- [`docs/BUILD_THE_APP.md`](docs/BUILD_THE_APP.md): produce the `.app` (CI or Mac).
- [`docs/GATEKEEPER.md`](docs/GATEKEEPER.md): the macOS "unidentified developer" warning.
- [`docs/BACKUP_RUN_FROM_PYTHON.md`](docs/BACKUP_RUN_FROM_PYTHON.md): run from Python.
- [`docs/SETUP.md`](docs/SETUP.md): USB/serial-port setup on macOS.
- [`docs/CONNECTING_ON_MAC.md`](docs/CONNECTING_ON_MAC.md): will the board connect on a
  Mac? First-connection assessment and macOS-vs-Windows serial differences.
- [`docs/DEVICE_SCOPE.md`](docs/DEVICE_SCOPE.md): what the board does and the
  raw-signal-to-SpO2 teaching pipeline.
- [`docs/VERIFICATION_AND_SETTINGS.md`](docs/VERIFICATION_AND_SETTINGS.md): exact
  register profile and a pre-class acceptance test.
- [`docs/PROTOCOL.md`](docs/PROTOCOL.md): byte-level serial protocol reference.

## Safety before a student practical

TI states this EVM is for laboratory feasibility/evaluation - not for diagnosis, not
for use with a defibrillator, and not intended for direct patient interface. Use an
SpO2 simulator, or obtain your institution's documented electrical-safety/isolation
approval and authorization for the complete board-cable-computer setup first.
