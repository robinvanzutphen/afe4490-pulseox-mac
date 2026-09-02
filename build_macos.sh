#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
PYTHON_BIN="${PYTHON_BIN:-python3}"
BUILD_ENV=".build-macos"
ARCH="${MACOS_ARCH:-$(uname -m)}"

case "$ARCH" in
  arm64|x86_64) ;;
  *) echo "Unsupported MACOS_ARCH: $ARCH" >&2; exit 1 ;;
esac

"$PYTHON_BIN" -c 'import sys; assert sys.version_info >= (3, 10)'
"$PYTHON_BIN" -m venv "$BUILD_ENV"
source "$BUILD_ENV/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r requirements-build.txt
python -m unittest discover -s tests -v

SIGN_ARGS=()
if [[ -n "${MACOS_SIGNING_IDENTITY:-}" ]]; then
  SIGN_ARGS=(--codesign-identity "$MACOS_SIGNING_IDENTITY")
fi

python -m PyInstaller --noconfirm --clean --windowed --onedir \
  --name AFE4490_PulseOx \
  --osx-bundle-identifier nl.amsterdamumc.bmo.afe4490-pulseox \
  --target-architecture "$ARCH" \
  --hidden-import serial.tools.list_ports \
  ${SIGN_ARGS[@]+"${SIGN_ARGS[@]}"} \
  live_viewer.py

"dist/AFE4490_PulseOx.app/Contents/MacOS/AFE4490_PulseOx" --self-test
mkdir -p release
ditto -c -k --sequesterRsrc --keepParent \
  "dist/AFE4490_PulseOx.app" \
  "release/AFE4490_PulseOx_macOS_${ARCH}.zip"

echo "Built and self-tested: release/AFE4490_PulseOx_macOS_${ARCH}.zip"
