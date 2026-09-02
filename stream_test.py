r"""
Direct-serial smoke test for the AFE EVM (no TI GUI).

CLOSE the TI GUI first (the serial port is exclusive), then:
    python stream_test.py COM4
    python3 stream_test.py /dev/cu.usbmodem...   # macOS
"""
import sys
import time
from afe.serial_link import AFESerial, CHANNELS
from serial.tools import list_ports

N = 1000


def select_port():
    if len(sys.argv) > 1:
        return sys.argv[1]
    matches = [p.device for p in list_ports.comports()
               if p.vid == 0x2047 and p.pid == 0x0300]
    if matches:
        return matches[0]
    raise SystemExit("AFE4490 EVM not found; pass its serial port explicitly")


def main():
    port = select_port()
    print("Opening %s (TI GUI must be CLOSED)..." % port)
    with AFESerial(port) as dev:
        print("  Device ID        :", dev.device_id())
        maj, minr = dev.firmware_revision()
        print("  Firmware revision: %d.%d" % (maj, minr))

        # Confirm a config register (this read leaves SPI in write mode).
        led2stc = dev.read_register(0x01)
        print("  LED2STC (0x01)   : 0x%06X  (EVM default 0x0017C0)" % led2stc)

        print("\nStreaming %d packets..." % N)
        dev.ser.timeout = 1.0
        dev.reset_link()                     # clean idle
        if not dev.begin_streaming(N):       # robust start (enables SPI_READ, retries)
            print("  could not start streaming"); return
        t0 = time.perf_counter()
        first = last = None
        got = 0
        try:
            for i in range(N):
                ch = dev.read_packet()
                if i == 0:
                    first = ch
                last = ch
                got += 1
        except Exception as e:
            print("  stream stopped after %d packets: %s" % (got, e))
        dt = time.perf_counter() - t0
        dev.stop_streaming()

        if got:
            print("  %d packets in %.3f s  ->  %.1f Hz  (all 6 channels/packet)"
                  % (got, dt, got / dt))
            print("\n  first packet (signed ADC codes):")
            for name in CHANNELS:
                print("    %-16s = %d" % (name, first[name]))
            print("  IR  PPG (LED1-ALED1VAL): first=%d  last=%d"
                  % (first["LED1-ALED1VAL"], last["LED1-ALED1VAL"]))
            print("  RED PPG (LED2-ALED2VAL): first=%d  last=%d"
                  % (first["LED2-ALED2VAL"], last["LED2-ALED2VAL"]))
            print("\nRoute B works: direct full-rate streaming, no GUI.")
        else:
            print("  No packets received.")


if __name__ == "__main__":
    main()
