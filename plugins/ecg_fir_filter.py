"""
HealthyPi v4 Plugin — ECG FIR low-pass filter
===============================================
Demonstrates the `signals` output with a proper linear-phase FIR filter.

A windowed-sinc low-pass filter (Hamming window) is applied to the ECG
channel.  Unlike a moving average, this has a well-defined frequency
response: it passes everything below CUTOFF_HZ and attenuates above it,
with a flat passband and no P-wave distortion at clinically relevant
cutoffs (≥ 30 Hz).

The filter is a Type-I linear-phase FIR (odd number of taps), which
means it has exactly (NUM_TAPS - 1) / 2 samples of constant group delay.
No phase distortion within the passband — QRS peaks and P waves stay
at their correct positions in time.

Students can modify:
  - CUTOFF_HZ   frequency below which the signal is preserved (default 40 Hz
                ≈ standard clinical ECG bandwidth upper limit)
  - NUM_TAPS    filter length — more taps = sharper transition but more delay
                (delay = (NUM_TAPS-1)/2 samples = (NUM_TAPS-1)/(2*fs) seconds)

Example — compare two cutoffs side by side in main.py:
    from plugins.ecg_fir_filter import ECGFIRFilter
    lp40 = ECGFIRFilter(name="ECG FIR 40 Hz", cutoff_hz=40)
    lp20 = ECGFIRFilter(name="ECG FIR 20 Hz", cutoff_hz=20)
    self._plugins = [..., lp40, lp20]
"""

from __future__ import annotations
import math
from collections import deque
from typing import Optional

from core.plugin_base import SignalPlugin, PluginResult

# ── Tunable parameters ────────────────────────────────────────────────────────
CUTOFF_HZ: float = 40.0   # low-pass cutoff frequency in Hz
NUM_TAPS:  int   = 9      # filter length (forced odd; delay = (NUM_TAPS-1)/2 samples)
# ─────────────────────────────────────────────────────────────────────────────


def _hamming_sinc(cutoff_hz: float, num_taps: int, fs: float) -> list[float]:
    """
    Design a windowed-sinc low-pass FIR filter.
    Returns a list of `num_taps` coefficients (normalised to unity DC gain).
    """
    if num_taps % 2 == 0:
        num_taps += 1          # force odd for Type-I linear phase
    fc = cutoff_hz / fs        # normalised cutoff (0..0.5)
    M  = num_taps - 1
    h  = []
    for n in range(num_taps):
        if n == M // 2:
            h.append(2.0 * fc)
        else:
            h.append(math.sin(2 * math.pi * fc * (n - M / 2))
                     / (math.pi * (n - M / 2)))
    # Hamming window
    w = [0.54 - 0.46 * math.cos(2 * math.pi * n / M)
         for n in range(num_taps)]
    h = [hi * wi for hi, wi in zip(h, w)]
    # Normalise to unity DC gain
    s = sum(h)
    return [hi / s for hi in h]


class ECGFIRFilter(SignalPlugin):
    """
    Linear-phase windowed-sinc FIR low-pass filter on the ECG channel.
    Outputs the filtered waveform as a plugin signal plot.
    """

    name    = "ECG FIR filter"
    enabled = True

    def __init__(self, name: str = "ECG FIR filter",
                 cutoff_hz: float = CUTOFF_HZ,
                 num_taps:  int   = NUM_TAPS):
        self.name        = name
        self._cutoff_hz  = cutoff_hz
        self._num_taps   = num_taps if num_taps % 2 == 1 else num_taps + 1
        self._coeffs: list[float] = []
        self._buf:    deque       = deque()

    def on_connect(self, sample_rate: float) -> None:
        self._coeffs   = _hamming_sinc(self._cutoff_hz, self._num_taps, sample_rate)
        n              = len(self._coeffs)
        self._buf      = deque([0.0] * n, maxlen=n)
        self._delay_ms = (n - 1) / 2 / sample_rate * 1000

    def on_sample(self, t: float, sample) -> Optional[PluginResult]:
        self._buf.append(float(sample.ecg))
        filtered = sum(c * x for c, x in zip(self._coeffs, self._buf))

        channel = self.name.lower().replace(" ", "_")

        return PluginResult(
            signals={channel: filtered},
            scalars={
                f"cutoff (Hz)":   self._cutoff_hz,
                f"taps":          len(self._coeffs),
                f"delay (ms)":    round(self._delay_ms, 1),
            },
        )

    def on_disconnect(self) -> None:
        self._buf.clear()
