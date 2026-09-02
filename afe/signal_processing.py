"""Dependency-light signal processing used by the teaching application."""

import numpy as np


def bandpass_fft(x, fs, low=0.5, high=5.0):
    """Return a zero-phase FFT band-pass of a one-dimensional signal."""
    x = np.asarray(x, dtype=float)
    if len(x) < 8 or not np.isfinite(fs) or fs <= 0:
        return np.zeros_like(x)
    trend = np.linspace(x[0], x[-1], len(x))
    spectrum = np.fft.rfft(x - trend)
    frequencies = np.fft.rfftfreq(len(x), 1.0 / fs)
    spectrum[(frequencies < low) | (frequencies > high)] = 0
    return np.fft.irfft(spectrum, n=len(x))


def _moving_average(x, samples):
    """Centered moving average with edge padding and O(n) work."""
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        return x.copy()
    samples = max(1, int(round(samples)))
    if samples % 2 == 0:
        samples += 1
    maximum = len(x) if len(x) % 2 else max(1, len(x) - 1)
    samples = min(samples, maximum)
    if samples == 1:
        return x.copy()
    half = samples // 2
    padded = np.pad(x, (half, half), mode="edge")
    cumulative = np.concatenate(([0.0], np.cumsum(padded, dtype=float)))
    return (cumulative[samples:] - cumulative[:-samples]) / samples


def peak_count_rate(x, fs, window_seconds, high=3.5):
    """Estimate bpm as detected peaks / selected window * 60.

    The function returns ``(bpm, filtered_signal, peak_indices)``. It waits until
    the requested window is substantially full, automatically selects positive
    or negative PPG polarity, and applies a refractory period derived from the
    maximum accepted heart rate to avoid double-counting one pulse.
    """
    x = np.asarray(x, dtype=float)
    empty = np.asarray([], dtype=int)
    if (len(x) < 64 or not np.isfinite(fs) or fs <= 0
            or not np.isfinite(window_seconds) or window_seconds <= 0):
        return float("nan"), np.zeros_like(x), empty

    # Peak mode deliberately avoids the sharp FFT band-pass used elsewhere.
    # A short average removes sample noise; subtracting a slow average removes
    # baseline drift while retaining the visible PPG pulse morphology.
    smoothed = _moving_average(x, 0.025 * fs)
    baseline = _moving_average(smoothed, 1.0 * fs)
    filtered = smoothed - baseline
    if len(x) / fs < 0.90 * window_seconds:
        return float("nan"), filtered, empty

    centre = float(np.median(filtered))
    p05, p95 = np.percentile(filtered, [5, 95])
    if centre - p05 > p95 - centre:
        filtered = -filtered
        centre = -centre
        p05, p95 = np.percentile(filtered, [5, 95])
    excursion = float(p95 - centre)
    if not np.isfinite(excursion) or excursion <= np.finfo(float).eps:
        return float("nan"), filtered, empty

    threshold = centre + 0.30 * excursion
    candidates = np.flatnonzero(
        (filtered[1:-1] > filtered[:-2])
        & (filtered[1:-1] >= filtered[2:])
        & (filtered[1:-1] > threshold)) + 1

    minimum_gap = max(1, int(np.floor(fs / high)))
    selected = []
    for index in candidates:
        index = int(index)
        if not selected or index - selected[-1] >= minimum_gap:
            selected.append(index)
        elif filtered[index] > filtered[selected[-1]]:
            selected[-1] = index
    peaks = np.asarray(selected, dtype=int)
    if len(peaks) < 2:
        return float("nan"), filtered, peaks
    return len(peaks) * 60.0 / float(window_seconds), filtered, peaks
