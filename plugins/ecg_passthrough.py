"""
HealthyPi v4 Plugin — ECG passthrough
=======================================
Copies the raw ECG sample directly to a plugin signal output with no
processing whatsoever.

If the signal plot tracks the ECG plot perfectly, the display pipeline
is correct and any distortion seen with other plugins is in their algorithm.

If the passthrough plot is *also* distorted or misaligned, the problem
is in the signal display pipeline itself.
"""

from __future__ import annotations
from typing import Optional

from core.plugin_base import SignalPlugin, PluginResult


class ECGPassthrough(SignalPlugin):

    name    = "ECG passthrough"
    enabled = True

    def on_connect(self, sample_rate: float) -> None:
        pass

    def on_sample(self, t: float, sample) -> Optional[PluginResult]:
        return PluginResult(
            signals={"ecg_passthrough": float(sample.ecg)},
        )

    def on_disconnect(self) -> None:
        pass
