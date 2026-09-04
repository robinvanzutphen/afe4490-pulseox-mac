# Will the board connect on a Mac? (first-connection assessment)

Short answer: **very likely yes on a modern Mac, with no driver to install** — but it
is the one thing that cannot be proven without plugging the actual board into a Mac.
This page explains why, what differs from Windows, and exactly what to do.

## Why it should just work on macOS

TI's EVM user guide (SLAU480C, "Installing the USB Drivers") states that the board
talks to the PC **"through the USB, using the CDC profile"** — i.e. it is a standard
**USB CDC-ACM** virtual serial device, presented by the on-board MSP430F5529.

That matters because:

- **macOS has a built-in CDC-ACM driver.** Any class-compliant CDC-ACM device
  enumerates automatically as `/dev/cu.usbmodemXXXX` with **no driver install** — just
  like **Windows 10/11**, which auto-bind their built-in `usbser.sys` to the board.
  Students install nothing on either OS. (Only *older* Windows — XP/7/8, the era of
  SLAU480C — needed a one-time TI `.inf`, shown as "MSP430-USB example" until bound.)
- **It is class-compliant, not an FTDI/CP210x/CH340 chip.** Those third-party
  USB-serial chips need a vendor kext on macOS; this board does **not** — it uses the
  native MSP430 USB stack, which macOS handles itself.
- **The protocol is OS-independent** and is already unit-tested on macOS in CI
  (framing, 24-bit LSB-first decode, register/LED mapping, signal processing all pass
  on the macOS runners).

## What the software already does right for macOS

- **Auto-detects** the board by USB `VID 0x2047 / PID 0x0300` (the same descriptor on
  every OS). pyserial reports VID/PID on macOS via IOKit, so auto-detect works.
- Uses the **`/dev/cu.*`** device, not `/dev/tty.*`. On macOS `cu.*` is non-blocking
  and does not wait for carrier-detect; opening `tty.*` on a virtual COM port can hang.
  Using `cu.*` is the correct, safe choice.
- If auto-detect misses, it shows a **manual port chooser** listing the `/dev/cu.*`
  devices so you can pick it.
- Programs the **EVM-default register profile on connect** and handles the firmware's
  "first start is a dud" quirk — all OS-independent.

## macOS vs Windows serial: what actually differs

| | Windows | macOS |
|---|---|---|
| Port name | `COM4`, `COM7`, … | `/dev/cu.usbmodemXXXX` |
| Driver | Win10/11: **none** (auto `usbser.sys`); XP/7/8: one-time TI `.inf` | **none** — built-in CDC-ACM |
| First appearance | "MSP430-USB example" until driver bound → "Virtual COM Port" | appears directly as `/dev/cu.usbmodem*` |
| Identify by | VID `2047` / PID `0300` | same VID/PID (from the USB descriptor) |
| Known quirk | TI GUI needs COM number ≤ 25 (not relevant to this app) | use `cu.*` not `tty.*` (the app already does) |
| Baud 230400 8-N-1 | honored | nominal for CDC-ACM (USB ignores real baud) — fine |

## First-connection checklist on a Mac

1. Plug the board into USB (it is bus-powered; the blue power LED lights).
2. Confirm it enumerated:

   ```bash
   python3 -m serial.tools.list_ports -v
   ```

   You should see a `/dev/cu.usbmodem…` line reporting `VID:PID=2047:0300`.
3. Launch `AFE4490_PulseOx.app` (clear the one-time Gatekeeper prompt — see
   [GATEKEEPER.md](GATEKEEPER.md)) and press **Start**. It auto-selects the board, or
   lists the port for you to choose.

## If it does NOT appear (the one hardware-dependent failure mode)

If no `/dev/cu.usbmodem*` shows up in step 2, the board's USB descriptor is not being
enumerated by that macOS release — this is a hardware/firmware matter, **not** an app
bug (the app cannot talk to a port that does not exist). To diagnose:

```bash
ioreg -p IOUSB -l -w 0 | grep -i -A3 -B3 "MSP430\|2047\|AFE"
```

If the device shows in `ioreg` but no `/dev/cu.*` node appears, the CDC interface is
not binding the class driver on that macOS version. Options then: try another macOS
version/Mac, or fall back to the **Windows** exe (which is fully verified end to end,
board included, per the project's live-board test). No amount of app-side change fixes
a missing serial node.

## Honest confidence

- **App + analysis + save on macOS:** verified (automated GUI test on the compiled
  `.app`, both Apple-Silicon and Intel).
- **Serial protocol logic on macOS:** verified (unit tests pass on macOS).
- **Live board over USB on macOS:** **not yet verified** — no board was available on a
  Mac. Based on the CDC-ACM profile and correct `cu.*`/VID-PID handling, first-try
  success on a current Mac is **likely**, but treat the checklist above as a required
  pre-class acceptance test before shipping to a student who will rely on it.
