# Building `AFE4490_PulseOx.app`

A macOS app can only be built on macOS - PyInstaller and every other Python-to-app
packager cannot cross-compile from Windows or Linux. So this kit ships the source
and two ways to produce the `.app`. Both build **and self-test on real macOS**, so
the result is verified, not just compiled.

macOS runs on two processor families and PyInstaller builds for the machine it runs
on, so there are two separate builds:

- **Apple Silicon** (`arm64`) - M1/M2/M3/M4 Macs.
- **Intel** (`x86_64`) - older Macs.

An `arm64` app will not run natively on Intel, and an Intel app runs on Apple
Silicon only through Rosetta. The safe classroom approach is to build **both** and
give each student the one matching their Mac (the student `READ ME FIRST.txt` tells
them how to tell). GitHub Actions builds both for you in one run.

## Route A - GitHub Actions (no Mac required)

The included workflow `.github/workflows/build-macos.yml` runs on GitHub's hosted
Apple-Silicon and Intel macOS runners.

1. Put this folder in a GitHub repository (a **private** repo is fine):

   ```bash
   cd afe_toolkit_mac
   git init && git add . && git commit -m "AFE4490 macOS kit"
   git branch -M main
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```

2. On GitHub: **Actions** tab -> **Build macOS applications** -> **Run workflow**.
3. When it finishes (a few minutes), open the run and download the two artifacts:
   - `AFE4490-PulseOx-macOS-arm64`  -> `AFE4490_PulseOx_macOS_arm64.zip`
   - `AFE4490-PulseOx-macOS-x86_64` -> `AFE4490_PulseOx_macOS_x86_64.zip`

Each ZIP contains the `AFE4490_PulseOx.app`. The workflow fails the build if the
unit tests or the app's packaged `--self-test` do not pass on that runner, so a
successful run is a tested app.

## Route B - build on a Mac

On any Mac with a recent Python 3 (from <https://www.python.org/downloads/> or
Homebrew), open Terminal in this folder and run:

```bash
bash build_macos.sh
```

It creates a private virtual environment, installs the build dependencies, runs the
hardware-free tests, builds the app for that Mac's architecture, runs the packaged
self-test, and writes:

```
release/AFE4490_PulseOx_macOS_<arch>.zip
```

To also cover the other architecture, run `build_macos.sh` on a Mac of that type, or
use Route A. Optionally set an institutional signing identity (see below):

```bash
MACOS_SIGNING_IDENTITY="Developer ID Application: ..." bash build_macos.sh
```

## Signing and notarization (optional, not required)

Without an Apple Developer ID the app is unsigned, so students clear a one-time
Gatekeeper prompt - see [GATEKEEPER.md](GATEKEEPER.md). The complete fix (no prompt
at all) is Apple Developer ID signing **plus** notarization, which needs a paid
Apple Developer account; `build_macos.sh` accepts a signing identity but notarizing
and stapling is a separate institutional step.

## After building

Unzip the artifact for each architecture and distribute the `.app` together with
`READ ME FIRST.txt`. Before class, confirm the board actually enumerates on a
physical Mac - see the acceptance test in
[VERIFICATION_AND_SETTINGS.md](VERIFICATION_AND_SETTINGS.md) and the macOS notes in
[SETUP.md](SETUP.md).
