# Verification, fixed settings, and what was built

## Bottom line

Direct USB serial is the best student route for this EVM. It is TI's documented
MSP430 message protocol, not reverse-engineered USB traffic. It removes the running
LabVIEW GUI, automation DLL, and Python 2.7/32-bit chain, while preserving all six
ADC channels at the pulse-repetition rate.

The application deliberately does not expose every native-GUI control. On each
connection it programs one known, repeatable EVM profile, then gives students the
controls relevant to the practical: acquisition, display-only filtering, LED drive,
raw recording, heart rate, and the ratio-of-ratios walkthrough.

## Safety boundary

TI's SLAU480C user guide says the EVM is for feasibility/electrical evaluation in
laboratory or development environments, not diagnostic use, not use with a
defibrillator, and not intended for direct patient interface. For teaching, use a
pulse-oximeter simulator unless the complete board, probe, USB connection, PC, and
room procedure have passed the Amsterdam UMC electrical-safety/isolation and human
participant requirements. Software review cannot establish that approval.

## Exact acquisition profile

These are TI GUI v2.4's AFE4490 EVM-default values from
`Config Files/Register Map_4490.xml`:

| Function | Register/value | Effective setting |
|---|---:|---|
| Pulse period | `PRPCOUNT 0x1D = 0x001F3F` | `(7999+1)/4 MHz = 2 ms`, therefore **500 samples/s per channel** |
| Timer/averaging | `CONTROL1 0x1E = 0x000101` | timer enabled; `NUMAV=1`, so two ADC conversions are averaged |
| LED drive | `LEDCNTRL 0x22 = 0x011414` | LED range `01`; LED1 code `0x14`, LED2 code `0x14` |
| Approximate LED current | range 01, Tx ref 0.75 V | full scale 75 mA; `20/256 x 75 = 5.86 mA` nominal for each LED |
| Transmit mode | `CONTROL2 0x23 = 0` | H-bridge, 0.75 V Tx reference, AFE/Rx/Tx powered, internal ADC active |
| Receiver | `TIAGAIN 0x20 = 0`, `TIA_AMB_GAIN 0x21 = 0` | shared 500 kOhm TIA, 5 pF, stage-2 bypassed, ambient DAC off, 500 Hz filter corner |
| Channel identity | fixed by EVM | LED1 = IR; LED2 = red |

The four 2-ms phases are approximately 0.5 ms each. Ambient-2 is sampled first,
then IR/LED1, then Ambient-1, then red/LED2. Conversion and short ADC-reset windows
are interleaved according to registers `0x0D` through `0x1C`. The full table lives
in `afe/registers.py`.

The two sliders change only LED1 and LED2's eight-bit codes. Bits 17:16, which set
the current range, are preserved. TI defines LED1 at `LEDCNTRL[15:8]` and LED2 at
`[7:0]`; this mapping is now used consistently in both drivers and the standalone
app.

## How it was coded from scratch

There were two stages:

1. TI's `Device_GUI.py` was ported from Python 2 to Python 3. That wrapper loads
   `Device GUI.dll` and asks the already-running LabVIEW GUI to read/write named
   registers. It proved the register map and hardware, but one round trip took
   about 79 ms, so it could not reproduce a 500 Hz waveform.
2. `afe/serial_link.py` implemented TI's published EVM message protocol directly
   over the MSP430 USB virtual COM port at 230400 8-N-1. A start command requests
   N frames; each 22-byte frame contains six little-endian 24-bit register values.
   The code finds the header, validates the trailer, sign-extends each value, and
   labels the fixed channel order. No TI executable or DLL is involved.

The live application reads frames on a worker thread so plotting cannot block the
serial reader. Raw tuples go to a queue. The GUI draws a display-only low-pass view,
but keeps the original integer samples for CSV and analysis. CSV time is derived
from sample number at 500 Hz, not from redraw arrival time.

## Protocol assurance

Checked against TI Message Communication Protocol v2.0 (firmware 1.3+) and TI's
later v4.0 packet table:

- write/read/start/stop/device-ID/firmware command bytes: match;
- start count: four raw bytes, most-significant first: match;
- stream frame: `01 02`, 18 payload bytes, `03 0D`: match;
- channel order `0x2A..0x2F`: match;
- each value: least-significant byte first: match;
- signed decoding: sign extension from bit 23: match;
- LED1=IR and LED2=red on the EVM: match TI datasheet and user guide.

Malformed read, device-ID, firmware, or stream frames now raise an error rather than
being treated as data. The reader re-synchronizes after byte misalignment.

### Live board check (2026-08-14)

The connected board on COM4 reported device `4490`, firmware `1.3`. After applying
the fixed profile, 1,000 frames arrived in 1.9944 s (501.4 frames/s measured from
the first received byte) with zero bad trailers. The first start was a firmware dud;
the second attempt streamed normally, confirming why the driver's stop/retry logic
is required. This validates transport and framing. It does not by itself validate
probe placement, optical amplitude, or clinical SpO2 accuracy.

## What the protocol cannot guarantee

Frames contain no CRC, sequence number, or device timestamp. A damaged/misaligned
frame is caught by framing, but loss of one complete, well-framed packet cannot be
identified from the following packet. At 500 Hz the serial load is about 11 kB/s,
well below 230400-baud capacity, and USB CDC is reliable, so this is a low practical
risk rather than a mathematical guarantee.

For a pre-class acceptance test, run `python stream_test.py COM4` and require:

- device ID `AFE4490` and firmware at least 1.3;
- measured receive rate close to 500 Hz with no restarts/timeouts;
- exactly increasing CSV time in 0.002-s steps;
- plausible, nonzero six-channel data;
- red and IR ambient-subtracted channels share the pulse frequency;
- moving only the IR slider changes LED1/IR response, and moving only red changes
  LED2/red response;
- no clipping near the signed register limits and no flat-topped waveform.

For stronger loss detection than TI's protocol permits, the MSP430 firmware would
need modification to add a sequence counter and preferably a CRC. That is not needed
for the planned teaching practical unless regulatory-grade traceability is a goal.

## Signal interpretation and limits

Use `LED1-ALED1VAL` for IR and `LED2-ALED2VAL` for red. TI recommends these
ambient-subtracted outputs for SpO2 work. Their mean is the optical DC component;
a detrended/band-limited RMS estimates AC. The ratio is
`R = (ACred/DCred) / (ACir/DCir)`.

The displayed SpO2 is educational, not calibrated. Beer-Lambert coefficients or a
generic polynomial do not turn this EVM into a clinical oximeter. Probe spectra,
tissue scattering, path length, detector response, motion, perfusion, and empirical
calibration against arterial reference measurements all matter.

## Operating recommendations

- Preinstall dependencies on teaching PCs. Runtime `pip install` is convenient for
  a demo but depends on network access and user permissions.
- Keep the fixed profile for the first practical. Expose gain, ambient DAC, PRF, or
  timing only in an advanced exercise, with bounds and an automatic restore button.
- Save the profile name, register values, firmware version, and nominal sample rate
  beside each dataset if recordings will be compared across sessions.

## Primary references

- TI AFE4490 datasheet, SBAS602H:
  <https://www.ti.com/lit/ds/symlink/afe4490.pdf>
- TI AFE44x0SPO2EVM user's guide, SLAU480C:
  <https://www.ti.com/lit/ug/slau480c/slau480c.pdf>
- TI Message Communication Protocol v2.0 attachment:
  <https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/30/6036.Message-Communication-Protocol-v2.0-_2D00_-AFE44x0EVM.pdf>
- TI EVM product and firmware page:
  <https://www.ti.com/tool/AFE4490SPO2EVM>
