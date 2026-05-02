"""
HealthyPi v4 — Fixed-length ring buffer backed by NumPy.
Used to hold the last N samples of each waveform channel for display.
"""

import numpy as np


class RingBuffer:
    """
    Circular buffer of floats, length N.
    push() adds one value; view() returns a read-only array from oldest to newest.
    """

    def __init__(self, size: int):
        self._size         = size
        self._buf          = np.zeros(size, dtype=np.float32)
        self._idx          = 0
        self._full         = False
        self.total_samples = 0   # monotonic counter, never wraps

    def push(self, value: float):
        self._buf[self._idx] = value
        self._idx = (self._idx + 1) % self._size
        if self._idx == 0:
            self._full = True
        self.total_samples += 1

    def push_many(self, values):
        for v in values:
            self.push(v)

    def view(self) -> np.ndarray:
        """Return array ordered oldest → newest."""
        if not self._full:
            return self._buf[:self._idx].copy()
        return np.roll(self._buf, -self._idx)

    def clear(self):
        self._buf[:] = 0.0
        self._idx          = 0
        self._full         = False
        self.total_samples = 0

    @property
    def size(self) -> int:
        return self._size
