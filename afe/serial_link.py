r"""
Direct USB-serial driver for the TI AFE4400/AFE4490 SpO2 EVM  (Route B).

This talks to the board's MSP430 firmware DIRECTLY over its virtual COM port --
NO TI GUI, NO 32-bit DLL. It implements TI's "AFE44x0 EVM Message Communication
Protocol v2.0" (firmware >= 1.3), which is a simple byte protocol at 230400 8-N-1:

    Write reg : 02  <2 ASCII addr>  <6 ASCII data>  0D
    Read  reg : 03  <2 ASCII addr>  0D        -> 03 02 <3 data LSB-first> 03 0D
    Start ADC : 01 2A <4-byte N, MSB first> 0D  -> N packets of:
                01 02 <18 bytes = 6 chan x 3B, LSB first> 03 0D
    Stop  ADC : 06 0D
    Device ID : 04 0D                          -> 04 02 "4490"/"4400" 03 0D
    FW rev    : 07 0D                          -> 07 02 <maj> <min> 03 0D

Because it bypasses the GUI, it runs on ANY Python (32- or 64-bit) and streams at
the full pulse-repetition rate (hundreds of Hz), not the ~13 Hz of the GUI path.

IMPORTANT: the COM port is exclusive -- CLOSE the TI GUI before using this.

    from afe.serial_link import AFESerial, CHANNELS
    with AFESerial("COM4") as dev:
        print(dev.device_id(), dev.firmware_revision())
        dev.start_streaming(500)
        for _ in range(500):
            chans = dev.read_packet()          # dict: name -> signed int
            print(chans["LED1-ALED1VAL"])      # live IR PPG sample
        dev.stop_streaming()
"""
import time
import serial   # pyserial

# The 6 streamed channels, in packet order (registers 0x2A..0x2F):
CHANNELS = ["LED2VAL", "ALED2VAL", "LED1VAL", "ALED1VAL",
            "LED2-ALED2VAL", "LED1-ALED1VAL"]

# protocol constants
_CR = 0x0D
_STREAM_START_ADDR = 0x2A
READ_RESP_LEN = 7        # 03 02 d0 d1 d2 03 0D
PACKET_LEN = 22          # 01 02 <18 data> 03 0D


def _to_signed24(v):
    return v - (1 << 24) if v & 0x800000 else v


class AFESerialError(Exception):
    pass


class AFESerial:
    def __init__(self, port="COM4", baud=230400, timeout=2.0):
        self.ser = serial.Serial(port=port, baudrate=baud, bytesize=8,
                                 parity=serial.PARITY_NONE, stopbits=1,
                                 timeout=timeout)
        self._streaming = False
        self.reset_link()   # force the device back to a clean idle state

    def reset_link(self):
        """Force the EVM out of any leftover streaming mode and drain the port,
        so register reads/writes start from a known-idle state."""
        self.ser.write(bytes([0x06, _CR]))      # stop-streaming
        time.sleep(0.1)
        self._drain()
        self._streaming = False

    def _drain(self, quiet=0.15):
        """Read and discard everything until the port stays silent for `quiet` s."""
        old = self.ser.timeout
        self.ser.timeout = quiet
        try:
            while self.ser.read(4096):
                pass
        finally:
            self.ser.timeout = old
        self.ser.reset_input_buffer()

    # -- context manager -------------------------------------------------- #
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def close(self):
        try:
            if self._streaming:
                self.stop_streaming()
        finally:
            self.ser.close()

    # -- low level -------------------------------------------------------- #
    def _read_exact(self, n):
        buf = self.ser.read(n)
        if len(buf) != n:
            raise AFESerialError("timeout: wanted %d bytes, got %d" % (n, len(buf)))
        return buf

    # -- info commands ---------------------------------------------------- #
    def device_id(self):
        """Return 'AFE4490' or 'AFE4400'."""
        self.ser.reset_input_buffer()
        self.ser.write(bytes([0x04, _CR]))
        r = self._read_exact(8)          # 04 02 '4' '4' '9'/'0' '0' 03 0D
        if r[:2] != b"\x04\x02" or r[-2:] != b"\x03\x0d":
            raise AFESerialError("bad device-ID response: %s" % r.hex())
        code = r[2:6].decode("ascii", "replace")
        if code not in ("4400", "4490"):
            raise AFESerialError("unexpected device ID: %r" % code)
        return "AFE" + code

    def firmware_revision(self):
        self.ser.reset_input_buffer()
        self.ser.write(bytes([0x07, _CR]))
        r = self._read_exact(6)          # 07 02 maj min 03 0D
        if r[:2] != b"\x07\x02" or r[-2:] != b"\x03\x0d":
            raise AFESerialError("bad firmware response: %s" % r.hex())
        return (r[2], r[3])

    # -- register access -------------------------------------------------- #
    def read_register(self, addr):
        """Read a 24-bit register by integer address (0x00..0x30). Unsigned."""
        self.ser.reset_input_buffer()
        cmd = bytes([0x03]) + b"%02X" % addr + bytes([_CR])
        self.ser.write(cmd)
        r = self._read_exact(READ_RESP_LEN)   # 03 02 d0 d1 d2 03 0D
        if r[0] != 0x03 or r[1] != 0x02 or r[5] != 0x03 or r[6] != _CR:
            raise AFESerialError("bad read response: %s" % r.hex())
        return r[2] | (r[3] << 8) | (r[4] << 16)   # LSB first

    def write_register(self, addr, value):
        """Write a 24-bit value to a register by integer address."""
        cmd = bytes([0x02]) + b"%02X" % addr + b"%06X" % (value & 0xFFFFFF) + bytes([_CR])
        self.ser.write(cmd)

    def set_led_current(self, led1_code, led2_code):
        """Set the IR (LED1) and red (LED2) 8-bit drive codes.

        Preserve LEDCNTRL bits 23:16, which include range/control settings.  The
        caller must pause streaming first because register traffic and streamed
        ADC packets share the same serial channel.
        """
        led1_code = int(led1_code) & 0xFF
        led2_code = int(led2_code) & 0xFF
        current = self.read_register(0x22)          # LEDCNTRL
        # TI SBAS602H, LEDCNTRL (0x22): LED1 is D15:D8; LED2 is D7:D0.
        value = (current & 0xFF0000) | (led1_code << 8) | led2_code
        self.write_register(0x22, value)
        time.sleep(0.02)

    def get_led_current(self):
        """Return the current ``(led1_code, led2_code)`` pair."""
        value = self.read_register(0x22)
        return (value >> 8) & 0xFF, value & 0xFF

    def configure_evm_defaults(self):
        """Bring the AFE up to the EVM default configuration from any state,
        fully GUI-independently. Writes every R/W register to its EVM default
        (SPI in write mode), then switches SPI to read mode so data registers /
        streaming can be read."""
        from afe import registers
        self.write_register(0x00, 0x000000)          # SPI_READ=0 -> write mode
        profile_addresses = set(range(0x01, 0x1F)) | {0x20, 0x21, 0x22, 0x23}
        for name, (addr, mode, default, grp, desc) in registers.REGISTERS.items():
            if addr not in profile_addresses:
                continue  # skip CONTROL0, spare/reserved/alarm, and data registers
            if "W" in mode:
                self.write_register(addr, default)
                time.sleep(0.002)
        self.write_register(0x00, 0x000001)          # SPI_READ=1 -> read mode
        time.sleep(0.05)

    # -- streaming -------------------------------------------------------- #
    def start_streaming(self, n_packets):
        """Ask the EVM to stream `n_packets` ADC packets (each = all 6 channels).
        The stream arrives at the pulse-repetition rate. Use a big number (or call
        again) for continuous capture. Max ~4.29e9 (4-byte counter)."""
        n = int(n_packets) & 0xFFFFFFFF
        self.ser.reset_input_buffer()   # protocol note: clear buffer before start
        cmd = bytes([0x01, _STREAM_START_ADDR,
                     (n >> 24) & 0xFF, (n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF,
                     _CR])
        self.ser.write(cmd)
        self._streaming = True

    def begin_streaming(self, n_packets, retries=4, warmup=0.3):
        """Robustly start streaming: enable SPI_READ, then issue the start
        command and wait for data to actually flow -- the FIRST start after a
        connect is often a dud, so retry with a stop in between until packets
        appear. Do NOT read any register between here and reading packets (a
        register read toggles SPI_READ off and the stream goes silent)."""
        self.write_register(0x00, 0x000001)   # SPI_READ = 1
        time.sleep(0.05)
        for _ in range(retries):
            self.start_streaming(n_packets)
            t0 = time.perf_counter()
            while time.perf_counter() - t0 < warmup:
                if self.ser.in_waiting:
                    return True
                time.sleep(0.01)
            self.stop_streaming()             # dud start -> stop and retry
        return False

    def stop_streaming(self):
        self.ser.write(bytes([0x06, _CR]))
        self._streaming = False
        time.sleep(0.05)
        self.ser.reset_input_buffer()

    def read_packet(self):
        """Read and parse one streamed packet. Returns {channel_name: signed int}.
        Re-synchronises to the 01 02 ... 03 0D framing if bytes get misaligned."""
        # find header 0x01 0x02
        b0 = self._read_exact(1)[0]
        while True:
            if b0 == 0x01:
                b1 = self._read_exact(1)[0]
                if b1 == 0x02:
                    break
                b0 = b1
                continue
            b0 = self._read_exact(1)[0]

        body = self._read_exact(20)              # 18 data + 03 0D
        if body[18] != 0x03 or body[19] != _CR:
            raise AFESerialError("bad packet trailer: %s" % body[-2:].hex())

        out = {}
        for i, name in enumerate(CHANNELS):
            d = body[i * 3:i * 3 + 3]
            out[name] = _to_signed24(d[0] | (d[1] << 8) | (d[2] << 16))  # LSB first
        return out
