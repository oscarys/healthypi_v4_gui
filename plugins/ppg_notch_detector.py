"""
HealthyPi v4 Plugin — Dicrotic notch detector
===============================================
Detects the dicrotic notch in the PPG IR waveform.

The dicrotic notch is a brief secondary dip on the descending limb of each
PPG pulse, caused by closure of the aortic valve.  It appears as a local
minimum in the first derivative, occurring after the systolic peak and before
the diastolic peak.

Algorithm:
  1. Smooth the PPG IR signal with a Gaussian-weighted moving average.
     Buffer is seeded with the first real sample (not zeros) to avoid
     startup contamination of the envelope tracker.
  2. Compute the first derivative with a 3-point central difference.
     A separate _deriv history buffer stores derivative values (not
     smoothed values), so zero-crossing detection is correct.
  3. Detect systolic peaks as downward zero-crossings of the derivative
     (prev_deriv > 0 and deriv <= 0), above an adaptive amplitude threshold.
  4. In the window [NOTCH_SEARCH_START_MS, NOTCH_SEARCH_END_MS] after each
     systolic peak, look for an upward zero-crossing of the derivative
     (prev_deriv < 0 and deriv >= 0) — this is the notch.
  5. Adaptive amplitude uses an exponential envelope follower seeded from
     the first sample; the warmup period (SMOOTH_ORDER samples) is skipped
     to avoid the zero-filled buffer corrupting the envelope.

Students can modify:
  - NOTCH_SEARCH_START_MS / NOTCH_SEARCH_END_MS to change the search window
  - SMOOTH_ORDER to change smoothing aggressiveness
  - PEAK_THRESHOLD_COEF to adjust systolic peak sensitivity
"""

from __future__ import annotations
from collections import deque
from typing import Optional

import numpy as np

from core.plugin_base import SignalPlugin, PluginResult, Annotation

# ── Tunable parameters ────────────────────────────────────────────────────────
SMOOTH_ORDER           = 9     # Gaussian MA window (samples, odd)
NOTCH_SEARCH_START_MS  = 150   # ms after systolic peak to begin notch search
NOTCH_SEARCH_END_MS    = 500   # ms after systolic peak to end notch search
PEAK_THRESHOLD_COEF    = 0.40  # min amplitude fraction to accept a systolic peak
PEAK_REFRACTORY_MS     = 400   # ms minimum between systolic peaks
ENVELOPE_TC_S          = 5.0   # seconds — envelope follower time constant
# ─────────────────────────────────────────────────────────────────────────────


def _gaussian_weights(n: int) -> np.ndarray:
    x = np.linspace(-2, 2, n)
    w = np.exp(-x ** 2)
    return w / w.sum()


class DicroticNotchDetector(SignalPlugin):
    """Detects systolic peaks and dicrotic notch in the PPG IR waveform."""

    name    = "Dicrotic notch detector"
    enabled = True

    def on_connect(self, sample_rate: float) -> None:
        self._fs     = sample_rate
        self._smooth = _gaussian_weights(SMOOTH_ORDER)
        self._decay  = float(np.exp(-1.0 / (ENVELOPE_TC_S * sample_rate)))

        # Filled on first sample — avoids zero-initialisation artefacts
        self._ppg_buf: Optional[deque] = None
        self._warmup = SMOOTH_ORDER + 3   # samples to skip before envelope tracking

        # Derivative history: stores actual derivative values (not smoothed values)
        self._prev_deriv: float = 0.0

        # Adaptive envelope
        self._env_max: Optional[float] = None
        self._env_min: Optional[float] = None
        self._sample_count: int = 0

        # State machine
        self._peak_refrac  = int(PEAK_REFRACTORY_MS * sample_rate / 1000)
        self._notch_start  = int(NOTCH_SEARCH_START_MS * sample_rate / 1000)
        self._notch_end    = int(NOTCH_SEARCH_END_MS   * sample_rate / 1000)
        self._since_peak   = self._peak_refrac
        self._in_search    = False
        self._notch_found  = False
        self._peak_amp     = 0.0

    def on_sample(self, t: float, sample) -> Optional[PluginResult]:
        val = float(sample.ppg_ir)

        # ── Seed buffer from first sample to avoid zero-fill artefacts ────────
        if self._ppg_buf is None:
            self._ppg_buf = deque([val] * SMOOTH_ORDER, maxlen=SMOOTH_ORDER)

        # ── Smooth ───────────────────────────────────────────────────────────
        self._ppg_buf.append(val)
        smoothed = float(np.dot(np.array(self._ppg_buf), self._smooth))

        # ── Derivative (central difference, one sample delay) ─────────────────
        # Store previous smoothed value for central difference
        if not hasattr(self, '_prev_smoothed'):
            self._prev_smoothed = smoothed
            self._prev_deriv    = 0.0
        deriv            = (smoothed - self._prev_smoothed)  # simple 1st diff
        prev_deriv       = self._prev_deriv
        self._prev_deriv = deriv
        self._prev_smoothed = smoothed

        # ── Adaptive envelope follower ────────────────────────────────────────
        self._sample_count += 1
        if self._env_max is None or self._sample_count <= self._warmup:
            self._env_max = smoothed
            self._env_min = smoothed
        else:
            self._env_max = max(smoothed,
                                self._env_max * self._decay
                                + (1 - self._decay) * smoothed)
            self._env_min = min(smoothed,
                                self._env_min * self._decay
                                + (1 - self._decay) * smoothed)
        amplitude = self._env_max - self._env_min

        # ── Systolic peak: downward zero-crossing of derivative ───────────────
        self._since_peak += 1
        results: list[PluginResult] = []

        peak_detected = (
            prev_deriv > 0 >= deriv                      # derivative crosses zero downward
            and self._since_peak >= self._peak_refrac
            and amplitude > 0
            and (smoothed - self._env_min) > PEAK_THRESHOLD_COEF * amplitude
        )

        if peak_detected:
            self._since_peak  = 0
            self._peak_amp    = smoothed
            self._in_search   = False
            self._notch_found = False
            results.append(PluginResult(
                annotations=[Annotation(
                    channel="ppg_ir", label="SP", color="#2ed573"
                )],
                scalars={"PPG systolic amp (ADC)": round(smoothed, 1)},
            ))

        # ── Notch search: upward zero-crossing of derivative ──────────────────
        if self._since_peak >= self._notch_start and not self._notch_found:
            self._in_search = True

        if self._in_search and self._since_peak <= self._notch_end:
            # Notch = local minimum of smoothed signal = upward zero-crossing
            # of derivative (prev_deriv < 0 and deriv >= 0)
            if prev_deriv < 0 <= deriv:
                ratio = ((smoothed - self._env_min) /
                         (self._peak_amp - self._env_min + 1e-9))
                self._notch_found = True
                self._in_search   = False
                results.append(PluginResult(
                    annotations=[Annotation(
                        channel="ppg_ir", label="DN", color="#ffa502"
                    )],
                    scalars={"Notch/peak ratio": round(ratio, 3)},
                ))

        if results:
            merged_ann     = []
            merged_scalars = {}
            for r in results:
                merged_ann.extend(r.annotations)
                merged_scalars.update(r.scalars)
            return PluginResult(annotations=merged_ann, scalars=merged_scalars)

        return None

    def on_disconnect(self) -> None:
        self._ppg_buf = None
        if hasattr(self, '_prev_smoothed'):
            del self._prev_smoothed
