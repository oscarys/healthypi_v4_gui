"""
HealthyPi v4 — Signal processing plugin interface
==================================================

Students implement SignalPlugin to add real-time processing.

Quick start
-----------
1. Create a file in plugins/, e.g. plugins/my_filter.py
2. Subclass SignalPlugin
3. Override on_sample() — it runs in the serial thread at ~125 Hz
4. Return a PluginResult to send annotations back to the GUI

Example
-------
    from core.plugin_base import SignalPlugin, PluginResult, Annotation

    class MyPlugin(SignalPlugin):
        name = "My filter"

        def on_sample(self, t, sample):
            if sample.heart_rate > 100:
                return PluginResult(
                    annotations=[Annotation(channel="ecg", label="Tachy")],
                    scalars={"custom_hr": sample.heart_rate},
                )

Threading note
--------------
on_sample() is called from the serial reader thread.
  - Keep it fast (< 1 ms per call ideally).
  - Do NOT touch any Qt widget from here.
  - Use numpy — it releases the GIL during heavy operations.
  - The PluginResult is posted to the GUI via a Queue automatically.

on_connect / on_disconnect are called from the GUI thread.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from .parser import HealthyPiSample


# ── Result types ─────────────────────────────────────────────────────────────

@dataclass
class Annotation:
    """
    A single event marker to be drawn on one of the waveform plots.

    Positioning is automatic — the GUI places the marker at the sample that
    was being processed when on_sample() returned this result. You do not
    need to specify a timestamp or index.

    channel : "ecg" | "respiration" | "ppg_ir" | "ppg_red"
    label   : short string shown as an overlay (≤ 8 chars recommended)
    color   : HTML colour string, e.g. "#ff4757"
    """
    channel: str
    label:   str  = ""
    color:   str  = "#ffffff"


@dataclass
class PluginResult:
    """
    What a plugin returns from on_sample().
    All fields are optional — return only what you need.

    annotations : list of event markers to draw on the waveform plots
    scalars     : dict of named values to show in the plugin panel
                  e.g. {"RR_ms": 820, "filtered_ecg": -42.3}
    signals     : dict of named continuous signal values to plot and log
                  e.g. {"filtered_ecg": -42.3, "resp_envelope": 1200.0}
                  A new plot is created automatically the first time a
                  channel name is seen.  Values are logged to the CSV
                  alongside the raw hardware channels.
    """
    annotations: list[Annotation]  = field(default_factory=list)
    scalars:     dict[str, float]  = field(default_factory=dict)
    signals:     dict[str, float]  = field(default_factory=dict)


# ── Base class ────────────────────────────────────────────────────────────────

class SignalPlugin(ABC):
    """
    Base class for all HealthyPi v4 real-time signal processing plugins.

    Subclass this and override on_sample().
    Optionally override on_connect() / on_disconnect() for init/teardown.
    Set class attribute `name` to a human-readable label for the GUI panel.
    Set `enabled = False` to ship a plugin disabled by default.
    """

    #: Human-readable name shown in the plugin panel
    name: str = "Unnamed plugin"

    #: Whether the plugin starts enabled.
    #: Default is False — students opt in by checking the box in the plugin panel.
    enabled: bool = False

    def on_connect(self, sample_rate: float) -> None:
        """
        Called once when the serial port is opened.
        Use this to initialise filter states, ring buffers, etc.

        sample_rate : nominal sample rate in Hz (125.0 for HealthyPi v4)
        """

    @abstractmethod
    def on_sample(self, t: float, sample: HealthyPiSample) -> Optional[PluginResult]:
        """
        Called for every decoded sample (~125 Hz).

        t      : timestamp in seconds (monotonic, from thread start)
        sample : fully decoded HealthyPiSample (PPG already polarity-corrected)

        Return a PluginResult, or None if there is nothing to report this tick.
        """

    def on_disconnect(self) -> None:
        """Called when the serial port is closed. Release any resources."""
