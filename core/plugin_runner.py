"""
HealthyPi v4 — Plugin runner
=============================
Sits between the serial reader thread and the GUI.
Calls each registered plugin's on_sample() inside the serial thread,
collects PluginResults, and puts them onto a queue for the GUI to read.

Usage (in SerialReaderThread.run):
    runner = PluginRunner(plugin_queue)
    runner.register(MyPlugin())
    runner.on_connect(125.0)
    # per sample:
    runner.process(t, sample)
    # on teardown:
    runner.on_disconnect()
"""

from __future__ import annotations
import queue
import traceback
from dataclasses import dataclass

from .plugin_base import SignalPlugin, PluginResult
from .parser import HealthyPiSample

NOMINAL_RATE = 125.0   # Hz


@dataclass
class PluginResultEnvelope:
    """Wraps a PluginResult with metadata for the GUI."""
    plugin_name:  str
    t:            float
    sample_index: int    # absolute sample count when on_sample() was called,
                         # same reference as RingBuffer.total_samples
    result:       PluginResult


class PluginRunner:
    """
    Manages a list of SignalPlugin instances.
    Thread-safe for reads (process() is called from the serial thread;
    register/enable/disable are called from the GUI thread before connect).
    """

    def __init__(self, result_queue: queue.Queue):
        self._plugins:      list[SignalPlugin] = []
        self._result_queue: queue.Queue        = result_queue
        self._sample_index: int                = 0   # increments per sample

    # ── Registration ─────────────────────────────────────────────────────────

    def register(self, plugin: SignalPlugin) -> None:
        """Add a plugin. Call before on_connect()."""
        self._plugins.append(plugin)

    def plugins(self) -> list[SignalPlugin]:
        return list(self._plugins)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_connect(self, sample_rate: float = NOMINAL_RATE) -> None:
        self._sample_index = 0
        for p in self._plugins:
            if p.enabled:
                try:
                    p.on_connect(sample_rate)
                except Exception:
                    traceback.print_exc()

    def on_disconnect(self) -> None:
        for p in self._plugins:
            try:
                p.on_disconnect()
            except Exception:
                traceback.print_exc()

    # ── Per-sample dispatch ──────────────────────────────────────────────────

    def process(self, t: float, sample: HealthyPiSample) -> None:
        """
        Called from the serial reader thread for every decoded sample.
        Runs all enabled plugins and enqueues their results.
        """
        self._sample_index += 1
        idx = self._sample_index
        for p in self._plugins:
            if not p.enabled:
                continue
            try:
                result = p.on_sample(t, sample)
                if result is not None:
                    self._result_queue.put_nowait(
                        PluginResultEnvelope(
                            plugin_name  = p.name,
                            t            = t,
                            sample_index = idx,
                            result       = result,
                        )
                    )
            except Exception:
                # Never let a plugin crash the serial thread
                traceback.print_exc()
