#!/bin/bash
# =========================================================================
#  BACKUP LAUNCHER (macOS) - run the app from Python source.
#
#  The normal way to start this program is the bundled AFE4490_PulseOx.app
#  (needs no Python). Use THIS only if the .app will not run on a Mac.
#
#  Close any serial terminal first - the board's port is used by one program.
#  Double-click in Finder, or from Terminal:
#      bash run_gui_backup.command                 # auto-detect the board
#      bash run_gui_backup.command /dev/cu.usbmodem14201
#
#  If double-clicking does nothing, make it executable once:
#      chmod +x run_gui_backup.command
# =========================================================================
cd "$(dirname "$0")" || exit 1

PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && \
     "$c" -c 'import sys; raise SystemExit(0 if sys.version_info[0]==3 else 1)' >/dev/null 2>&1; then
    PY="$c"; break
  fi
done

if [ -z "$PY" ]; then
  echo "No python3 was found on this Mac."
  echo
  echo "  The normal way to run this program is AFE4490_PulseOx.app (needs no Python)."
  echo "  To use this Python backup, install Python 3 from"
  echo "  https://www.python.org/downloads/  (or 'brew install python'),"
  echo "  then run this file again."
  echo
  read -n 1 -s -r -p "Press any key to close..."; echo
  exit 1
fi

echo "Using: $PY ($("$PY" --version 2>&1))"
if ! "$PY" -c 'import numpy, pyqtgraph, PyQt5, serial' >/dev/null 2>&1; then
  echo
  echo "Required packages are missing: numpy pyqtgraph PyQt5 pyserial"
  printf "Install them now with pip? [y/N] "
  read -r ans
  case "$ans" in
    [Yy]*)
      if ! "$PY" -m pip install -r requirements.txt; then
        echo
        echo "pip install failed. On recent macOS this is often the"
        echo "'externally-managed-environment' block - use the virtual-environment"
        echo "steps in docs/BACKUP_RUN_FROM_PYTHON.md instead."
        read -n 1 -s -r -p "Press any key to close..."; echo
        exit 1
      fi
      ;;
    *)
      echo "Skipped. See docs/BACKUP_RUN_FROM_PYTHON.md for the recommended venv method."
      read -n 1 -s -r -p "Press any key to close..."; echo
      exit 1
      ;;
  esac
fi

echo "Launching the viewer from source..."
"$PY" live_viewer.py "$@"
status=$?
if [ "$status" -ne 0 ]; then
  echo
  echo "The application exited with an error (code $status) - see the messages above."
  read -n 1 -s -r -p "Press any key to close..."; echo
fi
exit "$status"
