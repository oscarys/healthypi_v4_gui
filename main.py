"""
HealthyPi v4 — PyQt6 GUI
================================
Layout:
  ┌─────────────────────────────────────────────────────────┐
  │  Toolbar: port selector · connect · record              │
  ├──────────────┬────────────────────────────┬─────────────┤
  │  Vitals panel│  Waveform plots            │ Plugin panel│
  │  HR / SpO2   │  ECG / Resp / PPG IR       │ per-plugin  │
  │  Temp / RR   │  with annotation overlays  │ scalars     │
  ├──────────────┴────────────────────────────┴─────────────┤
  │  Status bar: port · sample rate · log status            │
  └─────────────────────────────────────────────────────────┘

Threading model:
  • SerialReaderThread  → parses packets, runs PluginRunner, puts
                          TimestampedSample on data_queue and
                          PluginResultEnvelope on plugin_queue
  • QTimer (40 ms)      → GUI thread drains both queues, updates
                          plots/vitals/annotations/plugin scalars
  • DataLogger          → thread-safe CSV writer (called in GUI timer)

PPG polarity:
  AFE4490 raw values are inverted relative to physiological convention.
  Negation is applied in parser.py (single source of truth) so plots,
  logger, and plugins all see correct polarity (systolic peaks upward).
"""

import queue
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont, QColor, QPalette
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QComboBox, QFileDialog,
    QGroupBox, QSizePolicy, QStatusBar, QFrame, QToolBar, QMessageBox,
    QSpinBox, QCheckBox, QScrollArea,
)

from core.serial_reader import SerialReaderThread
from core.logger import DataLogger
from core.ring_buffer import RingBuffer
from core.plugin_runner import PluginRunner

from plugins.r_peak_detector import RPeakDetector
from plugins.ppg_notch_detector import DicroticNotchDetector
from plugins.ecg_fir_filter import ECGFIRFilter
from plugins.ecg_passthrough import ECGPassthrough

# ── Display constants ────────────────────────────────────────────────────────
DISPLAY_SECONDS  = 6
SAMPLE_RATE      = 125
DISPLAY_SAMPLES  = DISPLAY_SECONDS * SAMPLE_RATE
GUI_TIMER_MS     = 40
DRAIN_MAX        = 64
PLUGIN_DRAIN_MAX = 128
ANNOTATION_TTL   = 10.0   # seconds before markers expire

# ── Colours ──────────────────────────────────────────────────────────────────
BG_COLOR       = "#1a1a2e"
PANEL_COLOR    = "#16213e"
CARD_COLOR     = "#0f3460"
ACCENT_ECG     = "#00d4aa"
ACCENT_RESP    = "#f5a623"
ACCENT_PPG     = "#e040fb"
TEXT_PRIMARY   = "#e8e8e8"
TEXT_SECONDARY = "#a0a0b0"
DANGER_COLOR   = "#ff4757"
SUCCESS_COLOR  = "#2ed573"

pg.setConfigOptions(antialias=True, foreground=TEXT_PRIMARY, background=BG_COLOR)

CHANNEL_PLOT = {
    "ecg":         "plot_ecg",
    "respiration": "plot_resp",
    "ppg_ir":      "plot_ppg",
    "ppg_red":     "plot_ppg",
}


# ─────────────────────────────────────────────────────────────────────────────
class VitalCard(QFrame):
    def __init__(self, label, unit, color=TEXT_PRIMARY):
        super().__init__()
        self.setObjectName("VitalCard")
        self.setStyleSheet(f"#VitalCard {{ background: {CARD_COLOR}; border-radius: 10px; border: 1px solid #1a4a7a; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 500;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_lbl = QLabel("---")
        self.value_lbl.setStyleSheet(
            f"color: {color}; font-size: 32px; font-weight: 700; font-family: monospace;")
        self.value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        unit_lbl = QLabel(unit)
        unit_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px;")
        unit_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)
        layout.addWidget(self.value_lbl)
        layout.addWidget(unit_lbl)

    def set_value(self, val, fmt="{}", color=None):
        self.value_lbl.setText(fmt.format(val))
        if color:
            self.value_lbl.setStyleSheet(
                f"color: {color}; font-size: 32px; font-weight: 700; font-family: monospace;")


# ─────────────────────────────────────────────────────────────────────────────
class AnnotationMarker:
    """
    Dashed vertical line with an attached label that scrolls with the waveform.

    Stores the event as an absolute sample count (total_at_event).  On every
    refresh() call the owning WaveformPlot recomputes the display x-position:

        display_x = buf_size - (total_now - total_at_event)

    so the marker moves left by exactly one sample per new sample pushed —
    keeping perfect lock with the waveform underneath it.

    Uses pg.InfLineLabel so the text is always visible regardless of y-scale.
    """

    def __init__(self, plot_widget, sample_index: int,
                 label: str, color: str, ttl: float = ANNOTATION_TTL):
        self._plot        = plot_widget
        self._expiry      = time.monotonic() + ttl
        self.sample_index = sample_index   # absolute sample count at event

        pen = pg.mkPen(color=color, width=1.5, style=Qt.PenStyle.DashLine)
        self._line = pg.InfiniteLine(pos=0, angle=90, pen=pen, movable=False)
        lbl = pg.InfLineLabel(
            self._line, text=label, movable=False,
            position=0.90,
            anchors=[(0.5, 1.0), (0.5, 1.0)],
        )
        lbl.setColor(color)
        lbl.setFont(pg.QtGui.QFont("monospace", 9, pg.QtGui.QFont.Weight.Bold))
        plot_widget.addItem(self._line)

    def update_pos(self, total_now: int, buf_size: int) -> bool:
        if time.monotonic() > self._expiry:
            return False
        age = total_now - self.sample_index
        if age > buf_size or age < 0:
            return False
        self._line.setPos(buf_size - age)
        return True

    def remove(self):
        self._plot.removeItem(self._line)


# ─────────────────────────────────────────────────────────────────────────────
class WaveformPlot(QWidget):
    def __init__(self, title, color, y_label="ADC", n_samples=DISPLAY_SAMPLES):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._buf = RingBuffer(n_samples)
        self._annotations: list[AnnotationMarker] = []

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("left",   y_label,   color=TEXT_SECONDARY)
        self.plot_widget.setLabel("bottom", "samples", color=TEXT_SECONDARY)
        self.plot_widget.showGrid(x=False, y=True, alpha=0.15)
        self.plot_widget.getPlotItem().setTitle(
            f'<span style="color:{color}; font-size:12px">{title}</span>')
        self.plot_widget.getPlotItem().hideButtons()
        self.plot_widget.setMouseEnabled(x=False, y=True)
        self.plot_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        pen = pg.mkPen(color=color, width=1.4)
        self.curve = self.plot_widget.plot([], pen=pen)
        layout.addWidget(self.plot_widget)

    def push(self, value):
        self._buf.push(value)

    def refresh(self):
        data = self._buf.view()
        n    = len(data)
        self.curve.setData(np.arange(n), data)

        # Update every marker's x-position to track the scrolling waveform
        total_now = self._buf.total_samples
        buf_size  = self._buf.size
        dead = []
        for marker in self._annotations:
            if not marker.update_pos(total_now, buf_size):
                dead.append(marker)
        for marker in dead:
            marker.remove()
            self._annotations.remove(marker)

    def add_annotation(self, sample_index: int, label: str, color: str):
        """
        Record an event marker at the given absolute sample_index.

        sample_index comes directly from PluginRunner._sample_index, which
        increments in lockstep with RingBuffer.total_samples (both start at 0
        at connect and increment by 1 per decoded packet).  This guarantees
        pixel-perfect alignment with no clock-rate conversion.
        """
        # Discard if already older than one full window
        if self._buf.total_samples - sample_index > self._buf.size:
            return
        marker = AnnotationMarker(self.plot_widget, sample_index, label, color)
        self._annotations.append(marker)

    def clear(self):
        for a in self._annotations:
            a.remove()
        self._annotations.clear()
        self._buf.clear()
        self.refresh()


# ─────────────────────────────────────────────────────────────────────────────
class PluginPanel(QWidget):
    """
    Right-side panel with one collapsible card per plugin.
    Shows enable/disable checkbox and live scalar readouts.
    Scalar rows are created the first time a key is seen.
    """

    def __init__(self, plugins: list):
        super().__init__()
        self.setFixedWidth(210)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        title = QLabel("Signal Plugins")
        title.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 600; padding: 4px 0;")
        outer.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner_widget = QWidget()
        self._inner_layout = QVBoxLayout(inner_widget)
        self._inner_layout.setSpacing(6)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(inner_widget)
        outer.addWidget(scroll)

        # plugin_name → dict(scalar_key → QLabel)
        self._scalar_labels: dict[str, dict[str, QLabel]] = {}
        # plugin_name → QVBoxLayout of its card
        self._plugin_layouts: dict[str, QVBoxLayout] = {}

        for plugin in plugins:
            self._add_plugin_card(plugin)

        self._inner_layout.addStretch()

    def _add_plugin_card(self, plugin):
        box = QGroupBox()
        box.setStyleSheet(f"""
            QGroupBox {{
                background: {PANEL_COLOR};
                border: 1px solid #1a3a5a;
                border-radius: 6px;
                margin-top: 4px;
                padding-top: 4px;
            }}
        """)
        bl = QVBoxLayout(box)
        bl.setSpacing(3)
        bl.setContentsMargins(6, 6, 6, 6)

        cb = QCheckBox(plugin.name)
        cb.setChecked(plugin.enabled)
        cb.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 10px; font-weight: 600;")
        cb.toggled.connect(lambda checked, p=plugin: setattr(p, "enabled", checked))
        bl.addWidget(cb)

        self._scalar_labels[plugin.name]  = {}
        self._plugin_layouts[plugin.name] = bl
        self._inner_layout.addWidget(box)

    def update_scalars(self, plugin_name: str, scalars: dict):
        if plugin_name not in self._plugin_layouts:
            return
        bl       = self._plugin_layouts[plugin_name]
        existing = self._scalar_labels[plugin_name]

        for key, val in scalars.items():
            if key not in existing:
                row = QHBoxLayout()
                row.setSpacing(4)
                key_lbl = QLabel(key)
                key_lbl.setStyleSheet(
                    f"color: {TEXT_SECONDARY}; font-size: 9px;")
                key_lbl.setWordWrap(True)
                val_lbl = QLabel("—")
                val_lbl.setStyleSheet(
                    f"color: {TEXT_PRIMARY}; font-size: 11px; "
                    f"font-weight: 700; font-family: monospace;")
                val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
                row.addWidget(key_lbl, 2)
                row.addWidget(val_lbl, 1)
                bl.addLayout(row)
                existing[key] = val_lbl

            existing[key].setText(
                f"{val:.1f}" if isinstance(val, float) else str(val))


# ─────────────────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("HealthyPi v4 Monitor")
        self.resize(1400, 800)

        self._plugins = [RPeakDetector(), DicroticNotchDetector(), ECGFIRFilter()]
        self._plugin_q      = queue.Queue()
        self._plugin_runner = PluginRunner(self._plugin_q)
        for p in self._plugins:
            self._plugin_runner.register(p)

        self._reader: SerialReaderThread | None = None
        self._logger        = DataLogger()
        self._data_q        = queue.Queue()
        self._error_q       = queue.Queue()
        self._connected     = False
        self._sample_count  = 0
        self._rate_count    = 0
        self._rate_t0       = time.monotonic()
        self._measured_rate = 0.0
        self._known_ports: list[str] = []   # last-seen port list for auto-refresh
        # plugin signal plots: channel_name → WaveformPlot
        self._plugin_signal_plots: dict[str, WaveformPlot] = {}
        # latest signal values for the current timer tick (for logger)
        self._current_signals: dict[str, float] = {}

        self._apply_dark_palette()
        self._build_ui()
        self._refresh_ports()

        self._timer = QTimer()
        self._timer.setInterval(GUI_TIMER_MS)
        self._timer.timeout.connect(self._on_timer)
        self._timer.start()

    # ── Palette ──────────────────────────────────────────────────────────────
    def _apply_dark_palette(self):
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window,          QColor(BG_COLOR))
        palette.setColor(QPalette.ColorRole.WindowText,      QColor(TEXT_PRIMARY))
        palette.setColor(QPalette.ColorRole.Base,            QColor(PANEL_COLOR))
        palette.setColor(QPalette.ColorRole.Text,            QColor(TEXT_PRIMARY))
        palette.setColor(QPalette.ColorRole.Button,          QColor(CARD_COLOR))
        palette.setColor(QPalette.ColorRole.ButtonText,      QColor(TEXT_PRIMARY))
        palette.setColor(QPalette.ColorRole.Highlight,       QColor(ACCENT_ECG))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#000000"))
        QApplication.instance().setPalette(palette)
        QApplication.instance().setStyleSheet(f"""
            QWidget {{ background: {BG_COLOR}; color: {TEXT_PRIMARY}; }}
            QComboBox, QSpinBox {{
                background: {PANEL_COLOR}; border: 1px solid #2a4a7a;
                border-radius: 5px; padding: 4px 8px; color: {TEXT_PRIMARY};
            }}
            QPushButton {{
                background: {CARD_COLOR}; color: {TEXT_PRIMARY};
                border: 1px solid #2a4a7a; border-radius: 6px;
                padding: 6px 14px; font-weight: 500;
            }}
            QPushButton:hover   {{ background: #1a5a9a; border-color: {ACCENT_ECG}; }}
            QPushButton:pressed {{ background: #0d3a6a; }}
            QPushButton:disabled {{ color: #555; border-color: #333; }}
            QGroupBox {{
                border: 1px solid #1a3a5a; border-radius: 8px;
                margin-top: 8px; padding-top: 8px;
                font-weight: 600; color: {TEXT_SECONDARY};
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
            QStatusBar {{ background: {PANEL_COLOR}; color: {TEXT_SECONDARY}; font-size: 11px; }}
            QToolBar   {{ background: {PANEL_COLOR}; border-bottom: 1px solid #1a3a5a; spacing: 8px; }}
            QScrollArea {{ background: transparent; border: none; }}
            QCheckBox {{ spacing: 5px; }}
            QCheckBox::indicator {{ width: 13px; height: 13px; }}
            QLabel {{ background: transparent; }}
        """)

    # ── UI ───────────────────────────────────────────────────────────────────
    def _build_ui(self):
        self._build_toolbar()
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        root.addWidget(self._build_vitals_panel(), 0)
        root.addWidget(self._build_plots_panel(),  1)
        root.addWidget(self._build_plugin_panel(), 0)
        self._build_status_bar()

    def _build_toolbar(self):
        tb = QToolBar("Main", self)
        tb.setMovable(False)
        self.addToolBar(tb)

        tb.addWidget(QLabel("  Port:"))
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(140)
        tb.addWidget(self.port_combo)

        btn_r = QPushButton("⟳")
        btn_r.setFixedWidth(32)
        btn_r.clicked.connect(self._refresh_ports)
        tb.addWidget(btn_r)
        tb.addSeparator()

        self.connect_btn = QPushButton("▶  Connect")
        self.connect_btn.setCheckable(True)
        self.connect_btn.clicked.connect(self._toggle_connection)
        tb.addWidget(self.connect_btn)
        tb.addSeparator()

        self.record_btn = QPushButton("⏺  Record")
        self.record_btn.setCheckable(True)
        self.record_btn.setEnabled(False)
        self.record_btn.clicked.connect(self._toggle_recording)
        tb.addWidget(self.record_btn)
        tb.addSeparator()

        tb.addWidget(QLabel("  Window (s):"))
        self.window_spin = QSpinBox()
        self.window_spin.setRange(2, 30)
        self.window_spin.setValue(DISPLAY_SECONDS)
        self.window_spin.setFixedWidth(56)
        self.window_spin.valueChanged.connect(self._on_window_changed)
        tb.addWidget(self.window_spin)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)

        self.lead_indicator = QLabel("  ⬤  LEAD OFF  ")
        self.lead_indicator.setStyleSheet(
            f"color: {DANGER_COLOR}; font-weight: 700; font-size: 12px;")
        tb.addWidget(self.lead_indicator)

    def _build_vitals_panel(self):
        panel = QGroupBox("Vitals")
        panel.setFixedWidth(190)
        layout = QVBoxLayout(panel)
        layout.setSpacing(8)
        self.card_hr   = VitalCard("Heart Rate",  "BPM", ACCENT_ECG)
        self.card_spo2 = VitalCard("SpO₂",        "%",   "#5dade2")
        self.card_rr   = VitalCard("Resp Rate",   "BPM", ACCENT_RESP)
        self.card_temp = VitalCard("Temperature", "°C",  "#f39c12")
        for c in (self.card_hr, self.card_spo2, self.card_rr, self.card_temp):
            layout.addWidget(c)
        layout.addStretch()

        stats_box = QGroupBox("Session")
        sg = QGridLayout(stats_box)
        sg.setSpacing(2)

        def stat_row(label, row):
            l = QLabel(label)
            l.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px;")
            v = QLabel("—")
            v.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-size: 11px; font-weight: 600;")
            v.setAlignment(Qt.AlignmentFlag.AlignRight)
            sg.addWidget(l, row, 0)
            sg.addWidget(v, row, 1)
            return v

        self.lbl_samples  = stat_row("Samples:",  0)
        self.lbl_rate     = stat_row("Rate (Hz):", 1)
        self.lbl_log_rows = stat_row("Log rows:",  2)
        self.lbl_log_time = stat_row("Log time:",  3)
        layout.addWidget(stats_box)
        return panel

    def _build_plots_panel(self):
        panel = QWidget()
        self._plots_layout = QVBoxLayout(panel)
        self._plots_layout.setSpacing(6)
        self._plots_layout.setContentsMargins(0, 0, 0, 0)
        n = DISPLAY_SECONDS * SAMPLE_RATE
        self.plot_ecg  = WaveformPlot("ECG",        ACCENT_ECG,  "ADC count", n)
        self.plot_resp = WaveformPlot("Respiration", ACCENT_RESP, "ADC count", n)
        self.plot_ppg  = WaveformPlot("PPG IR",      ACCENT_PPG,  "ADC count", n)
        self._plots_layout.addWidget(self.plot_ecg,  3)
        self._plots_layout.addWidget(self.plot_resp, 2)
        self._plots_layout.addWidget(self.plot_ppg,  2)
        return panel

    def _build_plugin_panel(self):
        self.plugin_panel = PluginPanel(self._plugins)
        return self.plugin_panel

    def _get_or_create_signal_plot(self, channel: str) -> "WaveformPlot":
        """Return the WaveformPlot for a plugin signal channel, creating it if new."""
        if channel not in self._plugin_signal_plots:
            palette = ["#a29bfe", "#fd79a8", "#55efc4", "#fdcb6e", "#74b9ff"]
            color = palette[len(self._plugin_signal_plots) % len(palette)]
            n = self.window_spin.value() * SAMPLE_RATE
            plot = WaveformPlot(channel, color, "plugin", n)
            self._plots_layout.addWidget(plot, 2)
            self._plugin_signal_plots[channel] = plot
        return self._plugin_signal_plots[channel]

    def _clear_signal_plots(self):
        """Remove all plugin signal plots (called on disconnect)."""
        for plot in self._plugin_signal_plots.values():
            self._plots_layout.removeWidget(plot)
            plot.deleteLater()
        self._plugin_signal_plots.clear()
        self._current_signals.clear()

    def _build_status_bar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.status_port = QLabel("Port: —")
        self.status_conn = QLabel("Disconnected")
        self.status_conn.setStyleSheet(f"color: {DANGER_COLOR};")
        self.status_log  = QLabel("Logging: off")
        sb.addWidget(self.status_port)
        sb.addWidget(QLabel("  |  "))
        sb.addWidget(self.status_conn)
        sb.addWidget(QLabel("  |  "))
        sb.addWidget(self.status_log)

    # ── Slots ─────────────────────────────────────────────────────────────────
    def _refresh_ports(self):
        """
        Refresh the port combo box.  Called both manually (⟳ button) and
        automatically from _on_timer.  The combo is only rebuilt when the
        available port list has actually changed, so the current selection
        is preserved when a connected board is already chosen.
        """
        ports = SerialReaderThread.list_ports()
        display = ports if ports else ["(no ports found)"]

        if display == self._known_ports:
            return   # nothing changed — leave combo alone

        self._known_ports = display
        current = self.port_combo.currentText()

        self.port_combo.blockSignals(True)
        self.port_combo.clear()
        self.port_combo.addItems(display)

        # Restore previous selection if it is still available
        idx = self.port_combo.findText(current)
        if idx >= 0:
            self.port_combo.setCurrentIndex(idx)

        self.port_combo.blockSignals(False)

    def _toggle_connection(self, checked):
        self._start_capture() if checked else self._stop_capture()

    def _start_capture(self):
        port = self.port_combo.currentText()
        if not port or port.startswith("("):
            QMessageBox.warning(self, "No port", "Please select a valid serial port.")
            self.connect_btn.setChecked(False)
            return

        self._data_q   = queue.Queue()
        self._error_q  = queue.Queue()
        self._plugin_q = queue.Queue()
        self._plugin_runner = PluginRunner(self._plugin_q)
        for p in self._plugins:
            self._plugin_runner.register(p)

        self._reader = SerialReaderThread(
            port, self._data_q, self._error_q,
            plugin_runner=self._plugin_runner,
        )
        self._reader.start()

        self._connected     = True
        self._sample_count  = 0
        self._rate_count    = 0
        self._rate_t0       = time.monotonic()
        self.connect_btn.setText("■  Disconnect")
        self.record_btn.setEnabled(True)
        self.status_port.setText(f"Port: {port}")
        self.status_conn.setText("Connected")
        self.status_conn.setStyleSheet(f"color: {SUCCESS_COLOR};")
        self._clear_signal_plots()
        for p in (self.plot_ecg, self.plot_resp, self.plot_ppg):
            p.clear()

    def _stop_capture(self):
        if self._reader:
            self._reader.stop()
            self._reader.join(timeout=2.0)
            self._reader = None
        if self._logger.is_active:
            self._logger.stop()
            self.record_btn.setChecked(False)
            self._update_log_status()
        self._connected = False
        self._clear_signal_plots()
        self.connect_btn.setText("▶  Connect")
        self.record_btn.setEnabled(False)
        self.status_conn.setText("Disconnected")
        self.status_conn.setStyleSheet(f"color: {DANGER_COLOR};")
        self.lead_indicator.setText("  ⬤  LEAD OFF  ")
        self.lead_indicator.setStyleSheet(
            f"color: {DANGER_COLOR}; font-weight: 700; font-size: 12px;")

    def _toggle_recording(self, checked):
        if checked:
            default = (
                Path.home() / "HealthyPi_recordings" /
                f"hpi4_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )
            path, _ = QFileDialog.getSaveFileName(
                self, "Save recording to…", str(default),
                "CSV files (*.csv);;All files (*)"
            )
            if not path:
                self.record_btn.setChecked(False)
                return
            actual = self._logger.start(
                path,
                signal_channels=list(self._plugin_signal_plots.keys()),
            )
            self.status_log.setText(f"Logging → {Path(actual).name}")
            self.status_log.setStyleSheet(f"color: {DANGER_COLOR};")
        else:
            self._logger.stop()
            self._update_log_status()

    def _update_log_status(self):
        self.status_log.setText("Logging: off")
        self.status_log.setStyleSheet(f"color: {TEXT_SECONDARY};")

    def _on_window_changed(self, seconds):
        n = seconds * SAMPLE_RATE
        all_plots = [self.plot_ecg, self.plot_resp, self.plot_ppg,
                     *self._plugin_signal_plots.values()]
        for plot in all_plots:
            old_total = plot._buf.total_samples
            plot._buf = RingBuffer(n)
            plot._buf.total_samples = old_total   # preserve this plot's own count
            plot.clear()

    # ── Timer ─────────────────────────────────────────────────────────────────
    def _on_timer(self):
        # Auto-refresh port list every tick (cheap: only rebuilds combo when changed)
        if not self._connected:
            self._refresh_ports()

        while not self._error_q.empty():
            msg = self._error_q.get_nowait()
            QMessageBox.critical(self, "Serial error", msg)
            self._stop_capture()
            self.connect_btn.setChecked(False)
            return

        if not self._connected:
            return

        # Drain waveform data
        drained = 0
        while drained < DRAIN_MAX:
            try:
                ts = self._data_q.get_nowait()
            except queue.Empty:
                break
            s = ts.sample
            self.plot_ecg.push(float(s.ecg))
            self.plot_resp.push(float(s.respiration))
            self.plot_ppg.push(float(s.ppg_ir))   # polarity-corrected in parser

            if self._logger.is_active:
                self._logger.log(ts, signals=self._current_signals if self._current_signals else None)

            if s.heart_rate > 0:
                self.card_hr.set_value(s.heart_rate, "{} bpm")
            if s.spo2 > 0:
                color = (SUCCESS_COLOR if s.spo2 >= 95
                         else "#f39c12" if s.spo2 >= 90
                         else DANGER_COLOR)
                self.card_spo2.set_value(s.spo2, "{}%", color)
            if s.resp_rate > 0:
                self.card_rr.set_value(s.resp_rate, "{} bpm")
            if s.temperature > 0:
                self.card_temp.set_value(s.temperature, "{:.1f}°C")

            lead_on = s.leads_on
            self.lead_indicator.setText(
                "  ⬤  LEADS ON  " if lead_on else "  ⬤  LEAD OFF  ")
            self.lead_indicator.setStyleSheet(
                f"color: {SUCCESS_COLOR if lead_on else DANGER_COLOR}; "
                f"font-weight: 700; font-size: 12px;")

            self._sample_count += 1
            self._rate_count   += 1
            drained += 1

        if drained:
            # Process plugin results BEFORE refresh() so newly added markers
            # get their positions computed in the same frame they appear.
            pdrained = 0
            while pdrained < PLUGIN_DRAIN_MAX:
                try:
                    env = self._plugin_q.get_nowait()
                except queue.Empty:
                    break
                if env.result.scalars:
                    self.plugin_panel.update_scalars(env.plugin_name, env.result.scalars)
                for ann in env.result.annotations:
                    plot_attr = CHANNEL_PLOT.get(ann.channel)
                    if plot_attr:
                        getattr(self, plot_attr).add_annotation(
                            env.sample_index, ann.label, ann.color)
                for ch, val in env.result.signals.items():
                    self._get_or_create_signal_plot(ch).push(val)
                    self._current_signals[ch] = val
                pdrained += 1

            self.plot_ecg.refresh()
            self.plot_resp.refresh()
            self.plot_ppg.refresh()
            for sp in self._plugin_signal_plots.values():
                sp.refresh()

        # Sample rate estimator
        now = time.monotonic()
        elapsed = now - self._rate_t0
        if elapsed >= 1.0:
            self._measured_rate = self._rate_count / elapsed
            self._rate_count    = 0
            self._rate_t0       = now

        self.lbl_samples.setText(f"{self._sample_count:,}")
        self.lbl_rate.setText(f"{self._measured_rate:.1f}")
        if self._logger.is_active:
            self.lbl_log_rows.setText(f"{self._logger.row_count:,}")
            mm, ss = divmod(int(self._logger.elapsed_seconds), 60)
            self.lbl_log_time.setText(f"{mm:02d}:{ss:02d}")
        else:
            self.lbl_log_rows.setText("—")
            self.lbl_log_time.setText("—")

    # ── Cleanup ───────────────────────────────────────────────────────────────
    def closeEvent(self, event):
        self._stop_capture()
        event.accept()


# ─────────────────────────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("HealthyPi v4 Monitor")
    app.setFont(
        QFont("Segoe UI", 10) if sys.platform == "win32"
        else QFont("SF Pro Display", 10) if sys.platform == "darwin"
        else QFont("Ubuntu", 10)
    )
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
