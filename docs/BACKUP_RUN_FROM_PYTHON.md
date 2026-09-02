# Backup: run the app from Python on macOS

The normal way to start the program is **`AFE4490_PulseOx.app`** - it contains its
own Python and needs nothing installed. Use this backup **only** if the `.app` will
not run on a particular Mac. The `.py` source is the identical application.

Close any serial-terminal program first; the board's `/dev/cu.*` port can be used by
one program at a time.

## Option A - double-click `run_gui_backup.command`

1. Install a **Python 3** if the Mac has none: from
   <https://www.python.org/downloads/> or `brew install python`.
2. Make the launcher executable once (Finder cannot run it otherwise). In Terminal,
   in this folder:

   ```bash
   chmod +x run_gui_backup.command
   ```

3. Double-click **`run_gui_backup.command`**. It finds Python 3, offers to install
   the four packages the first time, and launches the viewer. To force a port:

   ```bash
   bash run_gui_backup.command /dev/cu.usbmodem14201
   ```

## Option B - a virtual environment (most robust)

Recent macOS Python installs refuse a plain `pip install` into the system Python
("externally-managed-environment", PEP 668). A virtual environment avoids that
entirely and is the recommended backup:

```bash
cd afe_toolkit_mac
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python live_viewer.py                 # or:  python live_viewer.py /dev/cu.usbmodemXXXX
```

Next time, just `source .venv/bin/activate` again before running.

## Option C - an IDE

Open this folder in VS Code / PyCharm, select the `.venv` interpreter from Option B,
and run `live_viewer.py`. Keep the folder intact - `live_viewer.py` imports the
`afe/` package sitting next to it.

## Find the board / check the link

List serial devices (look for VID `2047`, PID `0300`):

```bash
python -m serial.tools.list_ports -v
```

Quick health check - connects, reads device ID and firmware, streams 1000 frames:

```bash
python stream_test.py /dev/cu.usbmodemXXXX
```

A good result reports `AFE4490`, firmware `1.3`+, and a rate near 500 Hz.

## Troubleshooting

| Symptom | Action |
|---|---|
| `run_gui_backup.command` won't open from Finder | `chmod +x run_gui_backup.command`, or run `bash run_gui_backup.command`. |
| `externally-managed-environment` on pip | Use the venv in Option B. |
| `ModuleNotFoundError` | Dependencies not installed - `pip install -r requirements.txt` inside the venv. |
| No `/dev/cu.*` for the board | Reconnect; confirm it enumerates (`python -m serial.tools.list_ports -v`). See [SETUP.md](SETUP.md). |
| Resource busy / port in use | Close any serial terminal, then retry. |
| Stream is all zeros | The driver sets `CONTROL0.SPI_READ` before streaming; restart the app. |

See [SETUP.md](SETUP.md) for USB/serial details and [PROTOCOL.md](PROTOCOL.md) for
the byte-level protocol.
