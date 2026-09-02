# AFE44x0 EVM serial protocol (Route B reference)

The MSP430 firmware (rev 1.3+) on the AFE44x0SPO2EVM speaks a simple byte protocol
over its USB virtual COM port. This is what `afe/serial_link.py` implements.

- **Port:** the board's USB serial device (for example `COM4` on Windows or
  `/dev/cu.usbmodem...` on macOS), **230400 baud, 8-N-1**.
- **Exclusive:** the TI GUI must be **closed** to use the port from Python.
- Source: TI "AFE4400 and AFE4490 SPO2 Front End Demonstration Kit — Message
  Communication Protocol v2.0" (verified against the live board here).

## Commands  (`0x0D` = carriage return = end-of-packet)

| Command | PC → EVM | EVM → PC |
|---|---|---|
| Write register | `02` + ASCII addr (2) + ASCII data (6) + `0D` | — |
| Read register  | `03` + ASCII addr (2) + `0D` | `03 02` + 3 data bytes (**LSB first**) + `03 0D` |
| Start streaming | `01 2A` + N (4 bytes, **MSB first**) + `0D` | N packets (see below) |
| Stop streaming | `06 0D` | — |
| Device ID | `04 0D` | `04 02` + ASCII `"4490"`/`"4400"` + `03 0D` |
| Firmware rev | `07 0D` | `07 02` + major + minor + `03 0D` |

- Addresses and write-data are **ASCII hex, uppercase** (e.g. reg `0x2E` → `"2E"` →
  bytes `32 45`; data `0x011414` → `"011414"`).
- Read/stream data come back as **raw bytes, little-endian**, 24-bit per value.

## Streaming packet

Each streamed packet is **22 bytes**:

```
01 02 | <18 data bytes = 6 channels x 3 bytes, LSB first> | 03 0D
```

The 6 channels are registers `0x2A`–`0x2F`, in order:

| # | Register | Meaning |
|---|---|---|
| 1 | LED2VAL       | Red raw |
| 2 | ALED2VAL      | Red ambient |
| 3 | LED1VAL       | IR raw |
| 4 | ALED1VAL      | IR ambient |
| 5 | LED2-ALED2VAL | **Red PPG** (ambient-subtracted) |
| 6 | LED1-ALED1VAL | **IR PPG** (ambient-subtracted) |

Values are 24-bit **two's-complement** → sign-extend from bit 23.

## Two behaviours you MUST handle (learned the hard way on the live board)

1. **SPI_READ must be 1 to stream.** `CONTROL0` (reg `0x00`) bit 0 = SPI_READ.
   With it `0`, streaming still produces packets but the data is **all zeros**.
   Set `CONTROL0 = 0x000001` before streaming.
2. **A register read toggles SPI_READ back off.** The firmware flips SPI_READ
   internally to service a single read command, leaving it `0`. So enable SPI_READ
   as the **last** action before `start` — never read a register in between.
3. **The first `start` after connecting is a dud** (yields no data). Issue a
   `stop` and `start` again. `serial_link.begin_streaming()` retries automatically.

## Integrity limits

The TI stream has start/end framing but no CRC, packet sequence number, or device
timestamp. The driver rejects malformed trailers and re-synchronizes on `01 02`,
so byte insertion/deletion is not silently accepted as a valid frame. However, a
whole correctly framed packet lost below the application cannot be proven missing.
USB CDC is reliable and the default stream is only about 11 kB/s, but this protocol
cannot provide end-to-end loss detection.

CSV time is derived from sample index and the configured 500 Hz PRF, not from GUI
redraw timing. This avoids host scheduling jitter and duplicate batch-boundary
timestamps. If timing registers are changed, the software sample-rate constant
must be changed with them.

## Sample rate

Streaming arrives at the pulse-repetition rate set by `PRPCOUNT`/timing registers.
EVM default ≈ **500 Hz**. The 230400-baud UART (~23 kB/s) caps throughput at
~1000 packets/s, so 500 Hz is comfortable; push the PRF higher only if needed.
