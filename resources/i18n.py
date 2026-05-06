"""
HealthyPi v4 Monitor — runtime i18n
=====================================
Dictionary-based translation system.  No Qt .ts/.qm files, no build step.

Usage
-----
    from resources.i18n import tr, set_language, language_changed

    label.setText(tr("port_label"))
    set_language("es")                    # switch at runtime
    language_changed.connect(my_retranslate)

Adding a new string
-------------------
    1. Add the key + English text to STRINGS["en"].
    2. Add the translated text to STRINGS["es"].
    3. Call tr("your_key") wherever it is needed.

Adding a new language
---------------------
    1. Add a new sub-dict to STRINGS (e.g. STRINGS["fr"]).
    2. Add it to _SUPPORTED.
    Missing keys fall back to English automatically.
"""

from __future__ import annotations
from PyQt6.QtCore import QObject, pyqtSignal, QSettings

# ── Signal emitter ────────────────────────────────────────────────────────────
class _Emitter(QObject):
    changed = pyqtSignal(str)   # emits new language code on every switch

_emitter        = _Emitter()
language_changed = _emitter.changed   # public — connect widgets here

# ── Supported languages ───────────────────────────────────────────────────────
_SUPPORTED  = ("en", "es")
LANG_NAMES  = {"en": "English", "es": "Español"}   # for menu display

# ── Translation strings ───────────────────────────────────────────────────────
STRINGS: dict[str, dict[str, str]] = {

    "en": {
        # ── Window ──────────────────────────────────────────────────────── #
        "window_title":         "HealthyPi v4 Monitor",

        # ── Toolbar ─────────────────────────────────────────────────────── #
        "port_label":           "  Port:",
        "btn_refresh_tip":      "Refresh port list",
        "btn_connect":          "▶  Connect",
        "btn_disconnect":       "■  Disconnect",
        "btn_record":           "⏺  Record",
        "window_label":         "  Window (s):",
        "lead_on":              "  ⬤  LEADS ON  ",
        "lead_off":             "  ⬤  LEAD OFF  ",
        "no_ports":             "(no ports found)",

        # ── Vitals panel ─────────────────────────────────────────────────── #
        "group_vitals":         "Vitals",
        "card_hr_label":        "Heart Rate",
        "card_hr_unit":         "BPM",
        "card_spo2_label":      "SpO₂",
        "card_spo2_unit":       "%",
        "card_rr_label":        "Resp Rate",
        "card_rr_unit":         "BPM",
        "card_temp_label":      "Temperature",
        "card_temp_unit":       "°C",

        # ── Session stats ────────────────────────────────────────────────── #
        "group_session":        "Session",
        "stat_samples":         "Samples:",
        "stat_rate":            "Rate (Hz):",
        "stat_log_rows":        "Log rows:",
        "stat_log_time":        "Log time:",

        # ── Plugin panel ─────────────────────────────────────────────────── #
        "plugin_panel_title":   "Signal Plugins",

        # ── Status bar ───────────────────────────────────────────────────── #
        "status_port_idle":     "Port: —",
        "status_port":          "Port: {}",
        "status_connected":     "Connected",
        "status_disconnected":  "Disconnected",
        "status_log_off":       "Logging: off",
        "status_logging":       "Logging → {}",

        # ── Dialogs ──────────────────────────────────────────────────────── #
        "dlg_no_port_title":    "No port",
        "dlg_no_port_msg":      "Please select a valid serial port.",
        "dlg_serial_err_title": "Serial error",
        "dlg_save_recording":   "Save recording to…",
        "dlg_csv_filter":       "CSV files (*.csv);;All files (*)",

        # ── Settings menu ────────────────────────────────────────────────── #
        "menu_settings":        "Settings",
        "menu_language":        "Language",
    },

    "es": {
        # ── Window ──────────────────────────────────────────────────────── #
        "window_title":         "Monitor HealthyPi v4",

        # ── Toolbar ─────────────────────────────────────────────────────── #
        "port_label":           "  Puerto:",
        "btn_refresh_tip":      "Actualizar lista de puertos",
        "btn_connect":          "▶  Conectar",
        "btn_disconnect":       "■  Desconectar",
        "btn_record":           "⏺  Grabar",
        "window_label":         "  Ventana (s):",
        "lead_on":              "  ⬤  ELECTRODOS OK  ",
        "lead_off":             "  ⬤  SIN ELECTRODOS  ",
        "no_ports":             "(ningún puerto encontrado)",

        # ── Vitals panel ─────────────────────────────────────────────────── #
        "group_vitals":         "Signos vitales",
        "card_hr_label":        "Frec. cardíaca",
        "card_hr_unit":         "LPM",
        "card_spo2_label":      "SpO₂",
        "card_spo2_unit":       "%",
        "card_rr_label":        "Frec. respiratoria",
        "card_rr_unit":         "RPM",
        "card_temp_label":      "Temperatura",
        "card_temp_unit":       "°C",

        # ── Session stats ────────────────────────────────────────────────── #
        "group_session":        "Sesión",
        "stat_samples":         "Muestras:",
        "stat_rate":            "Tasa (Hz):",
        "stat_log_rows":        "Filas log:",
        "stat_log_time":        "T. grabación:",

        # ── Plugin panel ─────────────────────────────────────────────────── #
        "plugin_panel_title":   "Plugins de señal",

        # ── Status bar ───────────────────────────────────────────────────── #
        "status_port_idle":     "Puerto: —",
        "status_port":          "Puerto: {}",
        "status_connected":     "Conectado",
        "status_disconnected":  "Desconectado",
        "status_log_off":       "Grabación: inactiva",
        "status_logging":       "Grabando → {}",

        # ── Dialogs ──────────────────────────────────────────────────────── #
        "dlg_no_port_title":    "Sin puerto",
        "dlg_no_port_msg":      "Por favor seleccione un puerto serial válido.",
        "dlg_serial_err_title": "Error serial",
        "dlg_save_recording":   "Guardar grabación en…",
        "dlg_csv_filter":       "Archivos CSV (*.csv);;Todos los archivos (*)",

        # ── Settings menu ────────────────────────────────────────────────── #
        "menu_settings":        "Configuración",
        "menu_language":        "Idioma",
    },
}

# ── State ─────────────────────────────────────────────────────────────────────
_current: str        = "en"
_active:  dict       = STRINGS["en"]

# ── Public API ────────────────────────────────────────────────────────────────

def tr(key: str, *args) -> str:
    """
    Return the translated string for *key* in the active language.
    Falls back to English if the key is missing in the current language.
    Falls back to the key itself if missing in English too.
    Optional positional *args* are substituted via str.format().
    """
    text = _active.get(key) or STRINGS["en"].get(key, key)
    if args:
        try:
            text = text.format(*args)
        except (IndexError, KeyError):
            pass
    return text


def set_language(lang: str) -> None:
    """Switch to *lang* and notify all connected widgets."""
    global _current, _active
    if lang not in _SUPPORTED:
        return
    _current = lang
    _active  = STRINGS.get(lang, STRINGS["en"])
    QSettings("HealthyPiv4Monitor", "HealthyPiMonitor").setValue("language", lang)
    _emitter.changed.emit(lang)


def current_language() -> str:
    return _current


def load_saved_language() -> None:
    """Call once at startup to restore the persisted language choice."""
    saved = QSettings(
        "HealthyPiv4Monitor", "HealthyPiMonitor"
    ).value("language", "en")
    # Set without emitting — widgets haven't been built yet
    global _current, _active
    _current = saved if saved in _SUPPORTED else "en"
    _active  = STRINGS.get(_current, STRINGS["en"])
