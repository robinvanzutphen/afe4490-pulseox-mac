import unittest

import numpy as np

from afe.signal_processing import peak_count_rate


class PeakCountTests(unittest.TestCase):
    def test_known_pulse_count(self):
        fs = 500.0
        window = 8.0
        t = np.arange(int(fs * window)) / fs
        signal = np.sin(2 * np.pi * 1.25 * t)  # 10 peaks in 8 s = 75 bpm
        bpm, _, peaks = peak_count_rate(signal, fs, window)
        self.assertEqual(len(peaks), 10)
        self.assertAlmostEqual(bpm, 75.0)

    def test_negative_polarity(self):
        fs = 500.0
        window = 10.0
        t = np.arange(int(fs * window)) / fs
        signal = -np.sin(2 * np.pi * 1.2 * t)
        bpm, _, peaks = peak_count_rate(signal, fs, window)
        self.assertEqual(len(peaks), 12)
        self.assertAlmostEqual(bpm, 72.0)


if __name__ == "__main__":
    unittest.main()
