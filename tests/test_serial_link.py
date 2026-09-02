"""Hardware-free checks for the TI EVM byte protocol."""
import importlib.util
import pathlib
import sys
import types
import unittest


class FakePort:
    def __init__(self, incoming=b""):
        self.incoming = bytearray(incoming)
        self.writes = []
        self.timeout = 1.0
        self.in_waiting = len(self.incoming)

    def read(self, n):
        out = bytes(self.incoming[:n])
        del self.incoming[:n]
        self.in_waiting = len(self.incoming)
        return out

    def write(self, data):
        self.writes.append(bytes(data))
        return len(data)

    def reset_input_buffer(self):
        pass

    def close(self):
        pass


serial_stub = types.SimpleNamespace(
    Serial=lambda **kwargs: FakePort(),
    PARITY_NONE="N",
)
sys.modules.setdefault("serial", serial_stub)

MODULE_PATH = pathlib.Path(__file__).parents[1] / "afe" / "serial_link.py"
SPEC = importlib.util.spec_from_file_location("serial_link_under_test", MODULE_PATH)
serial_link = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(serial_link)


def bare_device(incoming=b""):
    dev = serial_link.AFESerial.__new__(serial_link.AFESerial)
    dev.ser = FakePort(incoming)
    dev._streaming = False
    return dev


class ProtocolTests(unittest.TestCase):
    def test_stream_packet_order_endianness_and_signed_values(self):
        expected = [0, 1, -1, 0x7FFFFF, -0x800000, 0x123456]
        payload = b"".join((value & 0xFFFFFF).to_bytes(3, "little") for value in expected)
        dev = bare_device(b"junk" + b"\x01\x02" + payload + b"\x03\x0d")
        packet = dev.read_packet()
        self.assertEqual(list(packet), serial_link.CHANNELS)
        self.assertEqual(list(packet.values()), expected)

    def test_start_command_uses_four_byte_big_endian_count(self):
        dev = bare_device()
        dev.start_streaming(70000)
        self.assertEqual(dev.ser.writes[-1], b"\x01\x2a\x00\x01\x11\x70\x0d")

    def test_led_fields_follow_ti_register_map(self):
        dev = bare_device()
        dev.read_register = lambda address: 0x010000
        writes = []
        dev.write_register = lambda address, value: writes.append((address, value))
        dev.set_led_current(0x12, 0x34)
        self.assertEqual(writes, [(0x22, 0x011234)])

    def test_bad_read_frame_is_rejected(self):
        dev = bare_device(b"\x03\x02\x01\x02\x03\x00\x0d")
        with self.assertRaises(serial_link.AFESerialError):
            dev.read_register(0x22)


if __name__ == "__main__":
    unittest.main()
