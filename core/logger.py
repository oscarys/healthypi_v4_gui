"""
HealthyPi v4 — CSV data logger.

Thread-safe; the GUI thread calls log() at ~125 Hz.
Data is written to disk periodically (every FLUSH_INTERVAL rows)
to avoid blocking the GUI on every sample.

Plugin signal columns are registered at start() time and written
alongside the hardware channels on every row.  Any signal column
not present in a given tick is written as an empty string.
"""

import csv
import os
import threading
import time
from pathlib import Path
from typing import Optional

from .serial_reader import TimestampedSample

FLUSH_INTERVAL = 256   # rows between disk flushes

BASE_HEADER = [
    "time_s",
    "ecg",
    "respiration",
    "ppg_ir",
    "ppg_red",
    "temperature_c",
    "resp_rate_bpm",
    "spo2_pct",
    "heart_rate_bpm",
    "bp_sys",
    "bp_dia",
    "status",
    "leads_on",
]


class DataLogger:
    """
    Writes TimestampedSample objects to a CSV file.

    Plugin signal columns can be registered at start() time:
        logger.start("/path/to/file.csv", signal_channels=["filtered_ecg", "resp_env"])

    Then supply values each tick via log():
        logger.log(ts, signals={"filtered_ecg": -42.3})

    Columns not present in a given tick are written as empty strings,
    keeping the CSV well-formed for import into numpy / pandas.
    """

    def __init__(self):
        self._lock               = threading.Lock()
        self._file               = None
        self._writer             = None
        self._path: Optional[Path] = None
        self._row_count          = 0
        self._active             = False
        self._start_wall         = 0.0
        self._signal_channels: list[str] = []

    # ------------------------------------------------------------------
    def start(self, path: str,
              signal_channels: Optional[list[str]] = None) -> str:
        """
        Open a new CSV file for logging.

        signal_channels : optional list of plugin signal column names to
                          append after the standard hardware columns.
        Returns the resolved path (may differ if auto-named).
        """
        with self._lock:
            if self._active:
                self._close()

            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)

            if p.exists():
                stem, suffix = p.stem, p.suffix
                i = 1
                while p.exists():
                    p = p.parent / f"{stem}_{i:03d}{suffix}"
                    i += 1

            self._signal_channels = list(signal_channels or [])
            header = BASE_HEADER + self._signal_channels

            self._file = open(p, "w", newline="", buffering=1)
            self._writer = csv.writer(self._file)
            self._writer.writerow(header)
            self._path       = p
            self._row_count  = 0
            self._active     = True
            self._start_wall = time.time()
            return str(p)

    def stop(self):
        with self._lock:
            self._close()

    def log(self, ts: TimestampedSample,
            signals: Optional[dict[str, float]] = None):
        """
        Write one row.  signals maps plugin channel names to their current
        values; missing channels are written as empty strings.
        """
        if not self._active:
            return
        s = ts.sample
        row = [
            f"{ts.t:.4f}",
            s.ecg,
            s.respiration,
            s.ppg_ir,
            s.ppg_red,
            f"{s.temperature:.2f}",
            s.resp_rate,
            s.spo2,
            s.heart_rate,
            s.bp_sys,
            s.bp_dia,
            s.status,
            int(s.leads_on),
        ]
        if self._signal_channels:
            sig = signals or {}
            for ch in self._signal_channels:
                val = sig.get(ch)
                row.append(f"{val:.4f}" if val is not None else "")

        with self._lock:
            if not self._active:
                return
            self._writer.writerow(row)
            self._row_count += 1
            if self._row_count % FLUSH_INTERVAL == 0:
                self._file.flush()
                os.fsync(self._file.fileno())

    # ------------------------------------------------------------------
    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def row_count(self) -> int:
        return self._row_count

    @property
    def filepath(self) -> Optional[str]:
        return str(self._path) if self._path else None

    @property
    def elapsed_seconds(self) -> float:
        if not self._active:
            return 0.0
        return time.time() - self._start_wall

    @property
    def signal_channels(self) -> list[str]:
        return list(self._signal_channels)

    # ------------------------------------------------------------------
    def _close(self):
        """Must be called with self._lock held."""
        self._active = False
        if self._file:
            try:
                self._file.flush()
                self._file.close()
            except OSError:
                pass
            self._file   = None
            self._writer = None
