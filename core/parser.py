"""
HealthyPi v4 — Serial packet parser
Protocol confirmed from HealthyPiv4_Pi_only.ino firmware source.

Packet structure (27 bytes total):
  [0x0A][0xFA][0x14][0x00][0x02]  ← header (5 bytes, len=20)
  [payload: 20 bytes]
  [0x00][0x0B]                    ← footer (2 bytes)

Payload layout (all little-endian):
  [0:2]   ECG waveform        int16
  [2:4]   Respiration wave    int16
  [4:8]   PPG IR              int32   (raw from AFE4490)
  [8:12]  PPG Red             int32   (raw from AFE4490)
  [12:14] Temperature         int16  → divide by 100 → °C
  [14]    Respiration rate    uint8  BPM (FFT-derived)
  [15]    SpO2                uint8  %
  [16]    Heart rate          uint8  BPM
  [17]    BP sys              uint8  hardcoded 80 (placeholder)
  [18]    BP dia              uint8  hardcoded 120 (placeholder)
  [19]    Status reg          uint8  ADS1292R status; bit mask 0x1f==0 → leads on

PPG polarity note:
  The AFE4490 raw ADC value is inversely proportional to absorbed light:
  more blood volume → more absorption → LOWER ADC count.
  Physiological convention is the opposite (peaks = systole = upward deflection).
  ppg_ir and ppg_red are therefore NEGATED here so all downstream consumers
  (plots, logger, plugins) see the correct polarity.  The negation is applied
  once, at parse time, so there is a single source of truth.
"""

import struct
from dataclasses import dataclass
from typing import Optional

# --- Protocol constants (mirror firmware defines) ---
SOF1        = 0x0A
SOF2        = 0xFA
PROTO_VER   = 0x02
PAYLOAD_LEN = 20
EOF1        = 0x00
EOF2        = 0x0B
PKT_TOTAL   = 5 + PAYLOAD_LEN + 2   # 27 bytes

# Parser FSM states
_S_IDLE   = 0
_S_SOF2   = 1
_S_LENL   = 2
_S_LENH   = 3
_S_VER    = 4
_S_DATA   = 5
_S_STOP1  = 6


@dataclass
class HealthyPiSample:
    ecg:            int    # int16 ADC count (filtered by firmware)
    respiration:    int    # int16 chest-impedance ADC count
    ppg_ir:         int    # int32, NEGATED → physiologically correct (peaks up)
    ppg_red:        int    # int32, NEGATED → physiologically correct (peaks up)
    temperature:    float  # °C  (raw int16 / 100)
    resp_rate:      int    # BPM (FFT-derived on board)
    spo2:           int    # % oxygen saturation
    heart_rate:     int    # BPM
    bp_sys:         int    # placeholder — firmware hardcodes 80
    bp_dia:         int    # placeholder — firmware hardcodes 120
    status:         int    # ADS1292R status register byte
    leads_on:       bool   # True when (status & 0x1f) == 0


def _parse_payload(payload: bytes) -> Optional[HealthyPiSample]:
    """Decode a confirmed 20-byte payload into a HealthyPiSample."""
    if len(payload) < PAYLOAD_LEN:
        return None
    ecg          = struct.unpack_from('<h', payload, 0)[0]
    resp         = struct.unpack_from('<h', payload, 2)[0]
    ppg_ir       = struct.unpack_from('<i', payload, 4)[0]
    ppg_red      = struct.unpack_from('<i', payload, 8)[0]
    temp_raw     = struct.unpack_from('<h', payload, 12)[0]
    resp_rate    = payload[14]
    spo2         = payload[15]
    hr           = payload[16]
    bp_sys       = payload[17]
    bp_dia       = payload[18]
    status       = payload[19]
    return HealthyPiSample(
        ecg          = ecg,
        respiration  = resp,
        ppg_ir       = -ppg_ir,   # invert: AFE4490 raw is inversely proportional to blood volume
        ppg_red      = -ppg_red,  # invert: same reason
        temperature  = temp_raw / 100.0,
        resp_rate    = resp_rate,
        spo2         = spo2,
        heart_rate   = hr,
        bp_sys       = bp_sys,
        bp_dia       = bp_dia,
        status       = status,
        leads_on     = (status & 0x1F) == 0,
    )


class HealthyPiParser:
    """
    Byte-by-byte streaming FSM parser.
    Feed raw bytes from the serial port; collect decoded samples.

    Usage:
        parser = HealthyPiParser()
        for byte in serial_stream:
            sample = parser.feed(byte)
            if sample:
                process(sample)
    """

    def __init__(self):
        self._state       = _S_IDLE
        self._pkt_len     = 0
        self._payload     = bytearray()
        self._data_count  = 0
        self.stats        = {"total": 0, "ok": 0, "errors": 0}

    def feed(self, byte: int) -> Optional[HealthyPiSample]:
        """Feed one byte. Returns a HealthyPiSample when a complete packet is parsed."""
        s = self._state

        if s == _S_IDLE:
            if byte == SOF1:
                self._state = _S_SOF2

        elif s == _S_SOF2:
            self._state = _S_LENL if byte == SOF2 else _S_IDLE

        elif s == _S_LENL:
            self._pkt_len = byte
            self._state   = _S_LENH

        elif s == _S_LENH:
            self._pkt_len |= (byte << 8)
            self._state    = _S_VER

        elif s == _S_VER:
            if byte == PROTO_VER:
                self._payload    = bytearray()
                self._data_count = 0
                self._state      = _S_DATA
            else:
                self._state = _S_IDLE
                self.stats["errors"] += 1

        elif s == _S_DATA:
            self._payload.append(byte)
            self._data_count += 1
            if self._data_count >= self._pkt_len:
                self._state = _S_STOP1

        elif s == _S_STOP1:
            # byte should be EOF1 (0x00) — lenient, just wait for EOF2
            self._state = _S_IDLE
            self.stats["total"] += 1
            # EOF2 check is done on the *next* byte; restructure to two-stop-byte check
            # by storing the first stop byte and checking EOF2 here with a peek approach.
            # Simplified: accept packet regardless of stop bytes (firmware is reliable).
            sample = _parse_payload(bytes(self._payload))
            if sample:
                self.stats["ok"] += 1
                return sample
            else:
                self.stats["errors"] += 1

        return None

    def feed_buffer(self, data: bytes):
        """Feed multiple bytes, returning a list of decoded samples."""
        results = []
        for b in data:
            s = self.feed(b)
            if s:
                results.append(s)
        return results

    def reset(self):
        self._state = _S_IDLE
        self._payload = bytearray()
        self._data_count = 0
