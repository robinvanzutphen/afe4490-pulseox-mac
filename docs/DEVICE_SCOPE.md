# Device scope — what the AFE4490 EVM can do

Board: **AFE44x0SPO2EVM** — an AFE4490 (or AFE4400) analog front-end for pulse
oximetry, driven by an on-board **MSP430F5529** microcontroller over USB.
Reference documents: EVM user guide **SLAU480C** (`slau480c.pdf`); chip datasheet
**SBAS602** (AFE4490) — needed for exact bit-field maths (gain codes, mA, etc.).

## Capabilities

| Block | You can control… | Registers |
|---|---|---|
| **Transmit (LEDs)** | LED1 (IR) & LED2 (Red) drive current, Tx reference (4490), H-bridge mode | `LEDCNTRL 0x22`, `CONTROL2 0x23` |
| **Receive (gain/BW)** | TIA feedback **R** (gain) and **C** (bandwidth), separate gain per LED (4490), 2nd-stage gain, ambient-cancel DAC, filter corner (4490) | `TIAGAIN 0x20`, `TIA_AMB_GAIN 0x21` |
| **Timing engine** | Pulse-repetition frequency & duty cycle; start/end counts (in 4 MHz ticks) for each LED-on / sample / ADC-convert window; averaging (4490) | `0x01–0x1D`, `PRPCOUNT 0x1D`, `CONTROL1 0x1E` |
| **Data (read)** | Raw & ambient-subtracted 24-bit ADC codes for IR and Red | `0x2A–0x2F` |
| **Diagnostics** | LED open/short, photodiode & cable fault flags | `CONTROL0 0x00` (DIAG_EN), `DIAG 0x30` |
| **System** | Software reset, SPI-read enable, timer reset, power-down AFE/Tx/Rx, clock source | `CONTROL0`, `CONTROL1`, `CONTROL2` |

- **49 registers**, addresses `0x00`–`0x30`, all **24-bit containers**. The
  AFE4490 ADC itself is 22-bit; signed results are carried in those 24-bit
  registers. AFE4400 and AFE4490 share the same map; the 4490 enables extra
  features.
- Data acquisition up to **3000 Hz** in evaluation mode (via the TI GUI capture).
- Probe: DB9 cable, back-to-back Red/IR LEDs (H-bridge driven) + one photodiode.

## The register map

The authoritative, field-by-field map lives in the TI GUI at
`Config Files\Register Map_4490.xml` (and `_4400.xml`). A concise, code-friendly
version — name → address, mode, EVM default, group, one-line description — is in
[`afe/registers.py`](../afe/registers.py). Print it any time:

```
python3 -m afe.registers
```

## From raw signal to SpO₂ (the teaching pipeline)

This is the analysis students build on recorded data — the *why* behind the board:

1. **Ambient subtraction** — remove background light (the hardware already gives you
   `LED-ALED` difference registers).
2. **Split DC and AC** — DC = tissue/bone/venous (large, slow); AC = arterial
   pulsation (~1 % of DC, at heart rate).
3. **DC removal** — high-pass / detrend to isolate the pulsatile AC. *(The live
   viewer's "Remove DC" checkbox demonstrates exactly this.)*
4. **Normalise: AC/DC** per wavelength — cancels skin tone, finger size, LED brightness.
5. **Ratio of ratios** `R = (AC/DC)_red ÷ (AC/DC)_ir`.
6. **Calibrate** `SpO₂ ≈ 110 − 25·R` (empirical; Beer–Lambert + Hb/HbO₂ spectra
   explain why Red 660 nm and IR 905 nm).
7. **Heart rate** from AC peak detection or the FFT of the pulsatile signal.
