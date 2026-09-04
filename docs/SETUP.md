# Setup on macOS

For the packaged app, students install nothing: build/obtain `AFE4490_PulseOx.app`
(see [BUILD_THE_APP.md](BUILD_THE_APP.md)), clear the one-time Gatekeeper prompt
(see [GATEKEEPER.md](GATEKEEPER.md)), connect the board, and open the app. The steps
below cover connecting the hardware and the Python backup path.

## 1. Connect the board as a serial device

Plug in the EVM. It should enumerate as a USB CDC / virtual-serial device named
`/dev/cu.usbmodem...`, identifying as USB VID `2047`, PID `0300`. macOS provides the
USB CDC driver in the system, so no driver install is normally needed. List devices:

```bash
python3 -m serial.tools.list_ports -v
```

> Hardware note: the EVM is a standard USB CDC-ACM device (SLAU480C), so macOS should
> enumerate it automatically with no driver install. This still needs confirming on a
> physical Mac - if no `/dev/cu.*` device appears, the blocker is USB enumeration on
> that macOS release, not the Python code. See
> **[CONNECTING_ON_MAC.md](CONNECTING_ON_MAC.md)** for the full first-connection
> assessment, the macOS-vs-Windows differences, and a diagnostic checklist.

Only one program can own the port at a time; close any serial terminal first. (TI's
native GUI is Windows-only, so there is nothing TI to close on a Mac.)

## 2. Python (backup path only)

The app needs no Python. For the source/backup route, install a recent Python 3
(<https://www.python.org/downloads/> or `brew install python`) and use a virtual
environment - see [BACKUP_RUN_FROM_PYTHON.md](BACKUP_RUN_FROM_PYTHON.md):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

This installs numpy, pyqtgraph, PyQt5, and pyserial. Do it before class; a runtime
`pip install` can fail on restricted accounts or classroom networks.

## 3. Test and run

Close any serial terminal, then (replace the port with the one from step 1):

```bash
python stream_test.py /dev/cu.usbmodem14201
python live_viewer.py /dev/cu.usbmodem14201
```

The app programs a known EVM-default profile at connection time, so students do not
need to configure the board first.

## Troubleshooting

| Symptom | Likely cause and action |
|---|---|
| No matching `/dev/cu.*` | Reconnect the board; confirm it enumerates as USB CDC (VID 2047 / PID 0300). |
| Resource busy / port in use | Close any serial terminal, then restart the app. |
| Wrong port | Pass the actual device, e.g. `python live_viewer.py /dev/cu.usbmodemXXXX`. |
| Stream is all zeros | The driver sets `CONTROL0.SPI_READ` before streaming; restart the app. |
| Rate not near 500 Hz | Restore the fixed profile; `PRPCOUNT=0x001F3F` gives 500 Hz at the 4 MHz timing clock. |
| Flat/clipped waveforms | Check probe placement, LED current, ambient light, and receiver gain. |
| App blocked on first open | Gatekeeper - see [GATEKEEPER.md](GATEKEEPER.md). |
