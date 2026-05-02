"""
HealthyPi v4 — Serial reader thread.

Runs in a daemon thread; feeds raw bytes to HealthyPiParser and puts
decoded HealthyPiSample objects onto a thread-safe Queue for the GUI.
Also timestamps each sample at arrival using time.monotonic().

If a PluginRunner is provided, it is called synchronously inside this
thread for every decoded sample (before the sample hits the GUI queue).
Plugin results are dispatched to plugin_queue by the runner itself.
"""

import threading
import time
import queue
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

import serial
import serial.tools.list_ports

from .parser import HealthyPiParser, HealthyPiSample

if TYPE_CHECKING:
    from .plugin_runner import PluginRunner

BAUD_RATE   = 115200
READ_CHUNK  = 256   # bytes read per serial.read() call


@dataclass
class TimestampedSample:
    t:      float          # seconds, monotonic clock from thread start
    sample: HealthyPiSample


class SerialReaderThread(threading.Thread):
    """
    Daemon thread that reads from a serial port, parses packets,
    and places TimestampedSample objects onto `data_queue`.

    Signals:
      - data_queue:   Queue[TimestampedSample]
      - error_queue:  Queue[str]   — human-readable error messages
    """

    def __init__(self, port: str, data_queue: queue.Queue,
                 error_queue: queue.Queue, baud: int = BAUD_RATE,
                 plugin_runner: "Optional[PluginRunner]" = None):
        super().__init__(daemon=True)
        self.port           = port
        self.baud           = baud
        self.data_queue     = data_queue
        self.error_queue    = error_queue
        self.plugin_runner  = plugin_runner
        self._stop_event    = threading.Event()
        self._ser: Optional[serial.Serial] = None
        self.parser         = HealthyPiParser()
        self._t0            = 0.0

    # ------------------------------------------------------------------
    def run(self):
        try:
            self._ser = serial.Serial(
                port      = self.port,
                baudrate  = self.baud,
                bytesize  = serial.EIGHTBITS,
                parity    = serial.PARITY_NONE,
                stopbits  = serial.STOPBITS_ONE,
                timeout   = 0.1,
            )
        except serial.SerialException as e:
            self.error_queue.put(f"Cannot open {self.port}: {e}")
            return

        self.parser.reset()
        self._t0 = time.monotonic()

        if self.plugin_runner:
            self.plugin_runner.on_connect(BAUD_RATE / (27 * 10))  # ≈ 125 Hz nominal

        try:
            while not self._stop_event.is_set():
                raw = self._ser.read(READ_CHUNK)
                if not raw:
                    continue
                now = time.monotonic() - self._t0
                for sample in self.parser.feed_buffer(raw):
                    ts = TimestampedSample(t=now, sample=sample)
                    self.data_queue.put(ts)
                    if self.plugin_runner:
                        self.plugin_runner.process(now, sample)
        except serial.SerialException as e:
            self.error_queue.put(f"Serial error on {self.port}: {e}")
        finally:
            if self.plugin_runner:
                self.plugin_runner.on_disconnect()
            if self._ser and self._ser.is_open:
                self._ser.close()

    def stop(self):
        self._stop_event.set()

    # ------------------------------------------------------------------
    @staticmethod
    def list_ports() -> list[str]:
        """Return available serial port names."""
        return sorted(p.device for p in serial.tools.list_ports.comports())
