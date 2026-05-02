"""
HealthyPi v4 Plugin — R-peak detector
=======================================
A simplified Pan-Tompkins-inspired QRS detector operating on the ECG channel.

Pipeline:
  1. 5-point moving-average low-pass  (cuts high-freq noise)
  2. First difference (derivative, emphasises QRS slope)
  3. Squaring (makes all values positive, enhances large slopes)
  4. 15-point moving-average integrator (smooths the energy envelope)
  5. Adaptive threshold: threshold = 0.45 × running max of integrated signal
  6. Refractory period of 200 ms (125 samples × 0.2 s) prevents double detection

Returns:
  PluginResult with an Annotation on the "ecg" channel at each detected R peak,
  and a scalar "RR_ms" (last RR interval in milliseconds).

Students can modify:
  - REFRACTORY_MS  to change minimum interval between peaks
  - THRESHOLD_COEF to make detection more/less sensitive
  - The filter order (LP_ORDER, INT_ORDER) to change smoothing

Reference:
  Pan, J. & Tompkins, W.J. (1985). A real-time QRS detection algorithm.
  IEEE Trans. Biomed. Eng., 32(3), 230–236.
"""

from __future__ import annotations
from collections import deque
from typing import Optional

import numpy as np

from core.plugin_base import SignalPlugin, PluginResult, Annotation

# ── Tunable parameters ────────────────────────────────────────────────────────
REFRACTORY_MS   = 200    # ms — minimum time between two R peaks
THRESHOLD_COEF  = 0.45   # fraction of running max used as detection threshold
RUNNING_MAX_TC  = 600    # samples — exponential decay time constant for running max
LP_ORDER        = 5      # moving-average low-pass filter length (samples)
INT_ORDER       = 15     # moving-average integrator length (samples)
# ─────────────────────────────────────────────────────────────────────────────


class RPeakDetector(SignalPlugin):
    """Pan-Tompkins-inspired real-time R-peak detector."""

    name    = "R-peak detector"
    enabled = True

    def on_connect(self, sample_rate: float) -> None:
        self._fs            = sample_rate
        self._refrac        = int(REFRACTORY_MS * sample_rate / 1000)
        self._since_last    = self._refrac   # start ready to detect

        # Filter state buffers
        self._lp_buf   = deque([0.0] * LP_ORDER,  maxlen=LP_ORDER)
        self._int_buf  = deque([0.0] * INT_ORDER, maxlen=INT_ORDER)
        self._prev_lp  = 0.0   # for derivative

        # Adaptive threshold
        self._run_max  = 0.0

        # RR interval tracking
        self._last_r_t: Optional[float] = None
        self._rr_ms:    float           = 0.0

    def on_sample(self, t: float, sample) -> Optional[PluginResult]:
        # ── Step 1: low-pass moving average ──────────────────────────────────
        self._lp_buf.append(float(sample.ecg))
        lp = sum(self._lp_buf) / LP_ORDER

        # ── Step 2: first difference (derivative) ────────────────────────────
        diff = lp - self._prev_lp
        self._prev_lp = lp

        # ── Step 3: square ───────────────────────────────────────────────────
        sq = diff * diff

        # ── Step 4: moving-average integrator ────────────────────────────────
        self._int_buf.append(sq)
        integrated = sum(self._int_buf) / INT_ORDER

        # ── Step 5: adaptive threshold ────────────────────────────────────────
        decay = np.exp(-1.0 / RUNNING_MAX_TC)
        self._run_max = max(integrated, self._run_max * decay)
        threshold = THRESHOLD_COEF * self._run_max

        # ── Step 6: threshold crossing + refractory ──────────────────────────
        self._since_last += 1
        detected = (
            integrated > threshold
            and self._since_last >= self._refrac
            and self._run_max > 0
        )

        if detected:
            self._since_last = 0

            # RR interval
            if self._last_r_t is not None:
                self._rr_ms = (t - self._last_r_t) * 1000.0
            self._last_r_t = t

            return PluginResult(
                annotations=[
                    Annotation(
                        channel = "ecg",
                        label   = "R",
                        color   = "#ff4757",
                    )
                ],
                scalars={
                    "RR interval (ms)": round(self._rr_ms, 1),
                    "HR from RR (BPM)": round(60000.0 / self._rr_ms, 1)
                              if self._rr_ms > 0 else 0.0,
                },
            )

        return None

    def on_disconnect(self) -> None:
        pass
