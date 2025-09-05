# -*- coding: utf-8 -*-
"""
Interface de suivi des performances (CPU, RAM, GPU, VRAM) avec indicateurs circulaires.
- Thème sombre et palette d'accents.
- Mise à jour en temps réel via un service local PerformStatsSensorService (HTTP).
- Requêtes asynchrones, badge d'état, lissage, paramètres persistants, icône de zone de notification.

Exécution:
  pip install PySide6  # ou PyQt5
  python performance_gui.py

Compatibilité:
- Windows 11, Python 3.10+
- Backend: service HTTP local exposé par PerformStatsSensorService
  URL par défaut: http://127.0.0.1:9755/metrics
  Override possible via la variable d'environnement PERF_STATS_SERVICE_URL
"""

from __future__ import annotations
import sys
import os
import json
import math
import platform
from dataclasses import dataclass
from typing import Optional, Dict, Any

# Tentative d'import PySide6 puis fallback PyQt5
QT_BACKEND = "PySide6"
try:
    from PySide6.QtCore import Qt, QTimer, QPointF, QSettings, QUrl, QSize
    from PySide6.QtGui import QColor, QPainter, QPen, QFont, QIcon, QAction
    from PySide6.QtWidgets import (
        QApplication,
        QWidget,
        QLabel,
        QVBoxLayout,
        QGridLayout,
        QFrame,
        QMainWindow,
        QHBoxLayout,
        QSystemTrayIcon,
        QMenu,
        QDialog,
        QFormLayout,
        QLineEdit,
        QSpinBox,
        QDoubleSpinBox,
        QComboBox,
        QCheckBox,
        QPushButton,
        QMessageBox,
    )
    from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
except Exception:  # noqa: BLE001
    QT_BACKEND = "PyQt5"
    from PyQt5.QtCore import Qt, QTimer, QPointF, QSettings, QUrl, QSize  # type: ignore
    from PyQt5.QtGui import QColor, QPainter, QPen, QFont, QIcon  # type: ignore
    from PyQt5.QtWidgets import (  # type: ignore
        QApplication,
        QWidget,
        QLabel,
        QVBoxLayout,
        QGridLayout,
        QFrame,
        QMainWindow,
        QHBoxLayout,
        QSystemTrayIcon,
        QMenu,
        QDialog,
        QFormLayout,
        QLineEdit,
        QSpinBox,
        QDoubleSpinBox,
        QComboBox,
        QCheckBox,
        QPushButton,
        QMessageBox,
        QAction,
    )
    from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply  # type: ignore

# Journalisation (PERF_STATS_DEBUG=1 pour DEBUG)
import logging
LOG_LEVEL = logging.DEBUG if os.getenv("PERF_STATS_DEBUG", "0") == "1" else logging.INFO
logging.basicConfig(level=LOG_LEVEL, format='[Perform-Stats] %(levelname)s %(message)s')
logger = logging.getLogger("Perform-Stats")


def dprint(msg: str) -> None:
    try:
        logger.debug(msg)
    except Exception:
        pass


# -----------------------------
# Thème et palette de couleurs
# -----------------------------
COLOR_PALETTE = {
    "bg": "#0F1115",
    "panel_bg": "#151A21",
    "text_primary": "#E6E9EF",
    "text_secondary": "#9AA4B2",
    "track": "#2A2F36",
    "accent_blue": "#3B82F6",
    "accent_green": "#22C55E",
    "accent_purple": "#8B5CF6",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "success": "#22C55E",
}


def resource_path(relative_path: str) -> str:
    """Récupère le chemin d'une ressource, compatible PyInstaller."""
    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)


# -----------------------------
# Widget: Indicateur circulaire
# -----------------------------
class CircularIndicator(QWidget):
    """Indicateur circulaire générique avec anneau de progression.

    - name: légende (ex: "CPU")
    - color: couleur d'accent principale de l'anneau
    """

    def __init__(self, name: str, color: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.name = name
        self.color = QColor(color)
        self._value = 0.0  # 0..100
        self._subtext = ""  # ex: température ou autre
        self.setMinimumSize(160, 160)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_value(self, value: float) -> None:
        self._value = max(0.0, min(100.0, float(value)))
        # Ne pas appeler update() ici pour batcher, laisser le parent décider

    def set_subtext(self, text: str) -> None:
        self._subtext = text
        # Idem: pas d'update() immédiat

    def paintEvent(self, event) -> None:  # noqa: N802
        size = min(self.width(), self.height())
        margin = 14
        radius = (size - margin * 2) / 2
        center = QPointF(self.width() / 2, self.height() / 2)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Background transparent
        painter.fillRect(self.rect(), Qt.transparent)

        # Piste (track) circulaire
        pen_track = QPen(QColor(COLOR_PALETTE["track"]))
        pen_track.setWidth(14)
        pen_track.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_track)
        painter.drawArc(
            int(center.x() - radius),
            int(center.y() - radius),
            int(radius * 2),
            int(radius * 2),
            0,
            360 * 16,
        )

        # Progression
        pen_prog = QPen(self.color)
        pen_prog.setWidth(14)
        pen_prog.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_prog)
        # Qt utilise des angles en 1/16e de degré, 90° (12h) -> départ
        span_angle = -int(360 * 16 * (self._value / 100.0))
        painter.drawArc(
            int(center.x() - radius),
            int(center.y() - radius),
            int(radius * 2),
            int(radius * 2),
            90 * 16,
            span_angle,
        )

        # Textes (alignements centrés via rectangles)
        # Valeur (%) au centre
        value_font = QFont()
        value_font.setPointSize(18)
        value_font.setBold(True)
        painter.setFont(value_font)
        painter.setPen(QColor(COLOR_PALETTE["text_primary"]))
        value_text = f"{int(round(self._value))}%"
        value_rect_x = int(center.x() - radius + 8)
        value_rect_y = int(center.y() - 26)
        value_rect_w = int(2 * radius - 16)
        value_rect_h = 36
        painter.drawText(
            value_rect_x, value_rect_y, value_rect_w, value_rect_h,
            Qt.AlignHCenter | Qt.AlignVCenter,
            value_text,
        )

        # Sous-texte (optionnel) juste sous la valeur
        if self._subtext:
            sub_font = QFont()
            sub_font.setPointSize(9)
            painter.setFont(sub_font)
            painter.setPen(QColor(COLOR_PALETTE["text_primary"]))
            sub_rect_x = int(center.x() - radius + 8)
            sub_rect_y = int(center.y() + 4)
            sub_rect_w = int(2 * radius - 16)
            sub_rect_h = 24
            painter.drawText(
                sub_rect_x, sub_rect_y, sub_rect_w, sub_rect_h,
                Qt.AlignHCenter | Qt.AlignVCenter,
                self._subtext,
            )

        # Légende (name) alignée au bas du cercle, avec marge
        label_font = QFont()
        label_font.setPointSize(10)
        painter.setFont(label_font)
        painter.setPen(QColor(COLOR_PALETTE["text_secondary"]))
        name_rect_x = int(center.x() - radius + 8)
        name_rect_y = int(center.y() + radius - 32)
        name_rect_w = int(2 * radius - 16)
        name_rect_h = 22
        painter.drawText(
            name_rect_x, name_rect_y, name_rect_w, name_rect_h,
            Qt.AlignHCenter | Qt.AlignVCenter,
            self.name,
        )


class TemperatureCircularIndicator(CircularIndicator):
    """Indicateur circulaire spécialisé pour le GPU avec température.

    - max_temp: température de référence pour le mapping de couleur (vert->rouge)
    """

    def __init__(self, name: str, max_temp: float = 90.0, parent: Optional[QWidget] = None):
        super().__init__(name, COLOR_PALETTE["accent_blue"], parent)
        self.max_temp = max(1.0, float(max_temp))
        self._temp_c = 0.0

    def set_stats(self, usage_percent: float, temp_c: Optional[float]) -> None:
        self.set_value(usage_percent)
        if temp_c is not None:
            self._temp_c = temp_c
            # Le texte est géré par le parent pour permettre °F/°C
            # Mise à jour couleur selon température
            self.color = self._color_from_temperature(temp_c)
        else:
            self.color = QColor(COLOR_PALETTE["text_secondary"])  # gris si inconnu

    def _color_from_temperature(self, t: float) -> QColor:
        # 0..0.66 -> vert->jaune, 0.66..1.0 -> jaune->rouge
        ratio = max(0.0, min(1.0, t / self.max_temp))
        if ratio < 2/3:
            # vert -> jaune
            k = ratio / (2/3)
            r = int(34 + (245 - 34) * k)   # 0x22 -> 0xF5
            g = int(197 + (158 - 197) * k) # 0xC5 -> 0x9E
            b = int(94 + (11 - 94) * k)    # 0x5E -> 0x0B
        else:
            # jaune -> rouge
            k = (ratio - 2/3) / (1/3)
            r = 245
            g = int(158 + (68 - 158) * k)  # 0x9E -> 0x44
            b = 11
        return QColor(r, g, b)


# -------------------------------------
# Paramètres et validation
# -------------------------------------
@dataclass
class AppSettings:
    service_url: str = os.getenv("PERF_STATS_SERVICE_URL", "http://127.0.0.1:9755/metrics")
    interval_ms: int = int(float(os.getenv("PERF_STATS_INTERVAL_MS", "1000")))
    http_timeout_s: float = float(os.getenv("PERF_STATS_HTTP_TIMEOUT", "1.0"))
    temp_unit: str = os.getenv("PERF_STATS_TEMP_UNIT", "C")  # "C" ou "F"
    minimize_to_tray: bool = True
    update_epsilon: float = 0.8  # seuil de variation pour appliquer la MAJ

    def save(self, qs: QSettings) -> None:
        qs.setValue("service_url", self.service_url)
        qs.setValue("interval_ms", self.interval_ms)
        qs.setValue("http_timeout_s", self.http_timeout_s)
        qs.setValue("temp_unit", self.temp_unit)
        qs.setValue("minimize_to_tray", self.minimize_to_tray)
        qs.setValue("update_epsilon", self.update_epsilon)

    @staticmethod
    def load(qs: QSettings) -> "AppSettings":
        s = AppSettings()
        s.service_url = str(qs.value("service_url", s.service_url))
        s.interval_ms = int(qs.value("interval_ms", s.interval_ms))
        s.http_timeout_s = float(qs.value("http_timeout_s", s.http_timeout_s))
        s.temp_unit = str(qs.value("temp_unit", s.temp_unit))
        s.minimize_to_tray = bool(qs.value("minimize_to_tray", s.minimize_to_tray))
        s.update_epsilon = float(qs.value("update_epsilon", s.update_epsilon))
        return s


def sanitize_metrics(svc: Dict[str, Any]) -> Dict[str, Any]:
    """Validation/normalisation stricte des métriques."""
    def fnum(x):
        try:
            return float(x)
        except Exception:
            return None

    out: Dict[str, Any] = {"cpu": {}, "ram": {}, "gpu": {}, "vram": {}}

    cpu = svc.get("cpu", {}) if isinstance(svc, dict) else {}
    cpu_load = fnum(cpu.get("load"))
    cpu_temp = fnum(cpu.get("temp_c"))
    if cpu_load is not None:
        cpu_load = max(0.0, min(100.0, cpu_load))
    out["cpu"] = {"load": cpu_load, "temp_c": cpu_temp}

    ram = svc.get("ram", {}) if isinstance(svc, dict) else {}
    ru = fnum(ram.get("used_gb"))
    rt = fnum(ram.get("total_gb"))
    rp = fnum(ram.get("used_pct"))
    if rp is None and ru is not None and rt is not None and rt > 0:
        rp = (ru / rt) * 100.0
    if rp is not None:
        rp = max(0.0, min(100.0, rp))
    out["ram"] = {"used_pct": rp, "used_gb": ru, "total_gb": rt}

    gpu = svc.get("gpu", {}) if isinstance(svc, dict) else {}
    gl = fnum(gpu.get("load"))
    gt = fnum(gpu.get("temp_c"))
    if gl is not None:
        gl = max(0.0, min(100.0, gl))
    out["gpu"] = {"load": gl, "temp_c": gt}

    vram = svc.get("vram", {}) if isinstance(svc, dict) else {}
    vu = fnum(vram.get("used_gb"))
    vt = fnum(vram.get("total_gb"))
    vp = fnum(vram.get("used_pct"))
    if vp is None and vu is not None and vt is not None and vt > 0:
        vp = (vu / vt) * 100.0
    if vp is not None:
        vp = max(0.0, min(100.0, vp))
    out["vram"] = {"used_pct": vp, "used_gb": vu, "total_gb": vt}

    return out


# -------------------------------------
# Panneau de performances (UI principale)
# -------------------------------------
class PerformancePanel(QFrame):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("performance_panel")
        self._init_ui()

    def _init_ui(self) -> None:
        perf_layout = QVBoxLayout(self)
        perf_layout.setSpacing(20)
        perf_layout.setContentsMargins(20, 20, 20, 20)

        # En-tête avec titre et badge d'état
        header = QHBoxLayout()
        title = QLabel("Stats systèmes")
        title.setStyleSheet(
            f"color: {COLOR_PALETTE['text_primary']}; font-size: 18px; font-weight: bold;"
        )
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.status_label = QLabel("• Inconnu")
        self.status_label.setStyleSheet("color: #9AA4B2; font-weight: bold;")
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        header.addWidget(title, 1)
        header.addWidget(self.status_label, 0)
        perf_layout.addLayout(header)

        # Grille d'indicateurs circulaires
        indicators_layout = QGridLayout()
        indicators_layout.setSpacing(20)

        # Indicateurs principaux
        self.cpu_indicator = CircularIndicator("CPU", COLOR_PALETTE['accent_blue'])
        self.ram_indicator = CircularIndicator("RAM", COLOR_PALETTE['accent_green'])
        self.gpu_indicator = TemperatureCircularIndicator("GPU", max_temp=90.0)
        self.vram_indicator = CircularIndicator("VRAM", COLOR_PALETTE['accent_purple'])

        indicators_layout.addWidget(self.cpu_indicator, 0, 0)
        indicators_layout.addWidget(self.ram_indicator, 0, 1)
        indicators_layout.addWidget(self.gpu_indicator, 1, 0)
        indicators_layout.addWidget(self.vram_indicator, 1, 1)

        perf_layout.addLayout(indicators_layout)
        perf_layout.addStretch()

        # Style du panneau
        self.setStyleSheet(
            f"""
            QFrame#performance_panel {{
                background-color: {COLOR_PALETTE['panel_bg']};
                border-radius: 16px;
            }}
            """
        )

    def set_status(self, ok: bool) -> None:
        if ok:
            self.status_label.setText("• En ligne")
            self.status_label.setStyleSheet(f"color: {COLOR_PALETTE['success']}; font-weight: bold;")
        else:
            self.status_label.setText("• Hors ligne")
            self.status_label.setStyleSheet(f"color: {COLOR_PALETTE['danger']}; font-weight: bold;")


# -----------------
# Fenêtre principale
# -----------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Moniteur de Performances")
        self.setMinimumSize(780, 560)

        # Icône fenêtré et tray (préférence ICO, fallback PNG)
        icon_path_ico = resource_path('monitor_pdp.ico')
        icon_path_png = resource_path('monitor_pdp.png')
        if os.path.exists(icon_path_ico):
            app_icon = QIcon(icon_path_ico)
        elif os.path.exists(icon_path_png):
            app_icon = QIcon(icon_path_png)
        else:
            app_icon = QIcon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)

        # Panel de performance
        self.panel = PerformancePanel()
        main_layout.addWidget(self.panel, 1)

        # QSettings
        self.qs = QSettings("HardwareMonitor", "UI")
        self.settings = AppSettings.load(self.qs)

        # Réseau (asynchrone)
        self.nam = QNetworkAccessManager(self)
        self.nam.finished.connect(self._on_network_reply)
        self._req_in_flight = False

        # Config service / timer
        self.service_url = self.settings.service_url
        self.http_timeout = self.settings.http_timeout_s
        self._base_interval_ms = max(250, int(self.settings.interval_ms))
        self._max_interval_ms = 10_000
        self._current_interval_ms = self._base_interval_ms

        # Dernières métriques valides + affichées (pour lissage)
        self._last_metrics: Optional[Dict[str, Any]] = None
        self._display_cache = {
            'cpu': 0.0,
            'ram': 0.0,
            'gpu': 0.0,
            'vram': 0.0,
            'cpu_text': '',
            'ram_text': '',
            'gpu_text': '',
            'vram_text': '',
        }

        dprint(f"QT_BACKEND={QT_BACKEND}; service_url={self.service_url}; timeout={self.http_timeout}s; interval={self._base_interval_ms}ms")

        # Démarrage MAJ périodique
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(self._current_interval_ms)

        # Tray icon et menu
        self.tray = QSystemTrayIcon(app_icon, self)
        self.tray.setToolTip("Moniteur de Performances")
        tray_menu = QMenu()
        act_show = QAction("Afficher", self)
        act_show.triggered.connect(self.showNormal)
        act_hide = QAction("Masquer", self)
        act_hide.triggered.connect(self.hide)
        act_settings = QAction("Paramètres...", self)
        act_settings.triggered.connect(self._open_settings)
        act_quit = QAction("Quitter", self)
        act_quit.triggered.connect(QApplication.instance().quit)
        tray_menu.addAction(act_show)
        tray_menu.addAction(act_hide)
        tray_menu.addSeparator()
        tray_menu.addAction(act_settings)
        tray_menu.addSeparator()
        tray_menu.addAction(act_quit)
        self.tray.setContextMenu(tray_menu)
        self.tray.setVisible(True)

        # Raccourci: double-clic tray -> restaurer
        def on_tray_activated(reason):
            if reason == QSystemTrayIcon.DoubleClick:
                self.showNormal()
                self.activateWindow()
        self.tray.activated.connect(on_tray_activated)

    # --------- Gestion fermeture / minimisation ---------
    def closeEvent(self, event):  # noqa: N802
        if self.settings.minimize_to_tray:
            event.ignore()
            self.hide()
            if self.tray.isVisible():
                self.tray.showMessage("Moniteur de Performances", "L'application continue en zone de notification.", QSystemTrayIcon.Information, 2000)
        else:
            super().closeEvent(event)

    # --------- Paramètres ---------
    def _open_settings(self):
        dlg = SettingsDialog(self.settings, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self.settings = dlg.result_settings
            self.settings.save(self.qs)
            # Appliquer immédiatement
            self.service_url = self.settings.service_url
            self.http_timeout = self.settings.http_timeout_s
            self._base_interval_ms = max(250, int(self.settings.interval_ms))
            # Reset backoff
            self._current_interval_ms = self._base_interval_ms
            self.timer.start(self._current_interval_ms)

    # --------- Tick -> requête réseau ---------
    def _tick(self) -> None:
        if self._req_in_flight:
            return
        try:
            req = QNetworkRequest(QUrl(self.service_url))
            # Timeout: Qt 6 a un attribute; sinon on gère via timer + abandon
            req.setTransferTimeout(int(self.http_timeout * 1000)) if hasattr(req, 'setTransferTimeout') else None
            self._req_in_flight = True
            self.nam.get(req)
        except Exception as e:
            dprint(f"Req error: {e}")
            self._on_request_failed()

    def _on_network_reply(self, reply: QNetworkReply) -> None:
        self._req_in_flight = False
        if reply.error() != QNetworkReply.NetworkError.NoError:
            dprint(f"HTTP error: {reply.error()} {reply.errorString()}")
            self._on_request_failed()
            reply.deleteLater()
            return
        try:
            ba = reply.readAll()
            data = bytes(ba)
            svc = json.loads(data.decode('utf-8'))
            svc = sanitize_metrics(svc)
            self._on_request_success(svc)
        except Exception as e:
            dprint(f"Parse error: {e}")
            self._on_request_failed()
        finally:
            reply.deleteLater()

    # --------- Backoff / succès / échec ---------
    def _on_request_success(self, svc: Dict[str, Any]) -> None:
        self.panel.set_status(True)
        self._last_metrics = svc
        if self._current_interval_ms != self._base_interval_ms:
            self._current_interval_ms = self._base_interval_ms
            self.timer.start(self._current_interval_ms)
        self._apply_service_metrics(svc)

    def _on_request_failed(self) -> None:
        self.panel.set_status(False)
        if self._last_metrics is not None:
            # Conserver dernières valeurs pour éviter clignotement
            self._apply_service_metrics(self._last_metrics)
        else:
            self._clear_metrics()
        # Backoff progressif
        self._current_interval_ms = min(self._max_interval_ms, max(self._base_interval_ms, self._current_interval_ms * 2))
        self.timer.start(self._current_interval_ms)

    # -------- Application des métriques avec lissage --------
    def _apply_service_metrics(self, svc: Dict[str, Any]) -> None:
        eps = self.settings.update_epsilon
        alpha = 0.35  # facteur de lissage

        # CPU
        cpu = svc.get("cpu", {})
        cpu_load = cpu.get("load")
        if isinstance(cpu_load, (int, float)):
            val = float(cpu_load)
            cur = self._display_cache['cpu']
            new_val = cur + (val - cur) * alpha
            if abs(new_val - self.panel.cpu_indicator._value) > eps:
                self.panel.cpu_indicator.set_value(new_val)
                self._display_cache['cpu'] = new_val
        cpu_temp = cpu.get("temp_c")
        cpu_text = "N/A"
        if isinstance(cpu_temp, (int, float)):
            t = float(cpu_temp)
            if self.settings.temp_unit.upper() == 'F':
                t = (t * 9/5) + 32
                cpu_text = f"{int(round(t))}°F"
            else:
                cpu_text = f"{int(round(t))}°C"
        if cpu_text != self._display_cache['cpu_text']:
            self.panel.cpu_indicator.set_subtext(cpu_text)
            self._display_cache['cpu_text'] = cpu_text

        # RAM
        ram = svc.get("ram", {})
        ram_pct = ram.get("used_pct")
        if isinstance(ram_pct, (int, float)):
            val = float(ram_pct)
            cur = self._display_cache['ram']
            new_val = cur + (val - cur) * alpha
            if abs(new_val - self.panel.ram_indicator._value) > eps:
                self.panel.ram_indicator.set_value(new_val)
                self._display_cache['ram'] = new_val
        ru = ram.get("used_gb")
        rt = ram.get("total_gb")
        ram_text = ""
        if isinstance(ru, (int, float)) and isinstance(rt, (int, float)) and rt > 0:
            ram_text = f"{float(ru):.1f}/{float(rt):.0f}Go"
        if ram_text != self._display_cache['ram_text']:
            self.panel.ram_indicator.set_subtext(ram_text)
            self._display_cache['ram_text'] = ram_text

        # GPU
        gpu = svc.get("gpu", {})
        gpu_load = gpu.get("load")
        gpu_temp = gpu.get("temp_c")
        gl_val = 0.0
        if isinstance(gpu_load, (int, float)):
            val = float(gpu_load)
            cur = self._display_cache['gpu']
            gl_val = cur + (val - cur) * alpha
            if abs(gl_val - self.panel.gpu_indicator._value) > eps:
                # set_stats met juste la valeur et la couleur; le texte est géré plus bas
                self.panel.gpu_indicator.set_stats(gl_val, float(gpu_temp) if isinstance(gpu_temp, (int, float)) else None)
                self._display_cache['gpu'] = gl_val
            else:
                # même si pas de MAJ de valeur, s'assurer que la couleur suit la T°
                if isinstance(gpu_temp, (int, float)):
                    self.panel.gpu_indicator.color = self.panel.gpu_indicator._color_from_temperature(float(gpu_temp))
        # Sous-texte GPU
        gpu_text = "N/A"
        if isinstance(gpu_temp, (int, float)):
            t = float(gpu_temp)
            if self.settings.temp_unit.upper() == 'F':
                t = (t * 9/5) + 32
                gpu_text = f"{int(round(t))}°F"
            else:
                gpu_text = f"{int(round(t))}°C"
        if gpu_text != self._display_cache['gpu_text']:
            self.panel.gpu_indicator.set_subtext(gpu_text)
            self._display_cache['gpu_text'] = gpu_text

        # VRAM
        vram = svc.get("vram", {})
        vram_pct = vram.get("used_pct")
        if isinstance(vram_pct, (int, float)):
            val = float(vram_pct)
            cur = self._display_cache['vram']
            new_val = cur + (val - cur) * alpha
            if abs(new_val - self.panel.vram_indicator._value) > eps:
                self.panel.vram_indicator.set_value(new_val)
                self._display_cache['vram'] = new_val
        vu = vram.get("used_gb")
        vt = vram.get("total_gb")
        vram_text = ""
        if isinstance(vu, (int, float)) and isinstance(vt, (int, float)) and vt > 0:
            vram_text = f"{float(vu):.1f}/{float(vt):.0f}Go"
        if vram_text != self._display_cache['vram_text']:
            self.panel.vram_indicator.set_subtext(vram_text)
            self._display_cache['vram_text'] = vram_text

        # Un seul repaint en fin de cycle
        self.panel.update()

    def _clear_metrics(self) -> None:
        for key in ('cpu','ram','gpu','vram'):
            self._display_cache[key] = 0.0
        for key in ('cpu_text','ram_text','gpu_text','vram_text'):
            self._display_cache[key] = ""

        self.panel.cpu_indicator.set_value(0.0)
        self.panel.cpu_indicator.set_subtext("N/A")
        self.panel.ram_indicator.set_value(0.0)
        self.panel.ram_indicator.set_subtext("N/A")
        self.panel.gpu_indicator.set_stats(0.0, None)
        self.panel.gpu_indicator.set_subtext("N/A")
        self.panel.vram_indicator.set_value(0.0)
        self.panel.vram_indicator.set_subtext("N/A")
        self.panel.update()


# --------------------
# Boîte de dialogue paramètres
# --------------------
class SettingsDialog(QDialog):
    def __init__(self, cur: AppSettings, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Paramètres")
        self.setMinimumWidth(420)
        self.result_settings = cur

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.edt_url = QLineEdit(cur.service_url)
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(250, 60000)
        self.spin_interval.setSingleStep(250)
        self.spin_interval.setValue(int(cur.interval_ms))
        self.spin_timeout = QDoubleSpinBox()
        self.spin_timeout.setRange(0.2, 30.0)
        self.spin_timeout.setSingleStep(0.1)
        self.spin_timeout.setValue(float(cur.http_timeout_s))
        self.cmb_temp_unit = QComboBox()
        self.cmb_temp_unit.addItems(["C", "F"])
        self.cmb_temp_unit.setCurrentText(cur.temp_unit.upper())
        self.chk_min_tray = QCheckBox("Réduire dans la zone de notification à la fermeture")
        self.chk_min_tray.setChecked(cur.minimize_to_tray)
        self.spin_eps = QDoubleSpinBox()
        self.spin_eps.setRange(0.1, 10.0)
        self.spin_eps.setSingleStep(0.1)
        self.spin_eps.setValue(float(cur.update_epsilon))

        form.addRow("URL du service:", self.edt_url)
        form.addRow("Intervalle (ms):", self.spin_interval)
        form.addRow("Timeout HTTP (s):", self.spin_timeout)
        form.addRow("Unité température:", self.cmb_temp_unit)
        form.addRow("Seuil de mise à jour (%):", self.spin_eps)
        form.addRow("", self.chk_min_tray)

        layout.addLayout(form)

        # Démarrage auto (Windows) optionnel
        self.chk_autostart = None
        if platform.system() == 'Windows':
            self.chk_autostart = QCheckBox("Démarrer avec Windows")
            self.chk_autostart.setChecked(self._is_autostart_enabled())
            layout.addWidget(self.chk_autostart)

        btns = QHBoxLayout()
        btn_ok = QPushButton("OK")
        btn_cancel = QPushButton("Annuler")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(btn_ok)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    def accept(self) -> None:  # noqa: D401
        s = AppSettings(
            service_url=self.edt_url.text().strip(),
            interval_ms=int(self.spin_interval.value()),
            http_timeout_s=float(self.spin_timeout.value()),
            temp_unit=self.cmb_temp_unit.currentText(),
            minimize_to_tray=self.chk_min_tray.isChecked(),
            update_epsilon=float(self.spin_eps.value()),
        )
        self.result_settings = s
        # Autostart
        if self.chk_autostart is not None:
            try:
                self._set_autostart(self.chk_autostart.isChecked())
            except Exception as e:
                QMessageBox.warning(self, "Autostart", f"Impossible de changer le démarrage auto: {e}")
        super().accept()

    # --- Démarrage automatique via registre (Windows) ---
    def _is_autostart_enabled(self) -> bool:
        try:
            import winreg  # type: ignore
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\\Microsoft\\Windows\\CurrentVersion\\Run", 0, winreg.KEY_READ)
            try:
                _ = winreg.QueryValueEx(key, "HardwareMonitorUI")[0]
                return True
            except Exception:
                return False
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False

    def _set_autostart(self, enabled: bool) -> None:
        import winreg  # type: ignore
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\\Microsoft\\Windows\\CurrentVersion\\Run", 0, winreg.KEY_SET_VALUE)
        try:
            if enabled:
                if getattr(sys, 'frozen', False):
                    exe_path = sys.executable
                else:
                    exe_path = f'"{sys.executable}" "{os.path.abspath(__file__)}"'
                winreg.SetValueEx(key, "HardwareMonitorUI", 0, winreg.REG_SZ, exe_path)
            else:
                try:
                    winreg.DeleteValue(key, "HardwareMonitorUI")
                except FileNotFoundError:
                    pass
        finally:
            winreg.CloseKey(key)


# -------
# Entrée
# -------
if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Fond global sombre
    app.setStyleSheet(
        f"""
        QWidget {{
            background-color: {COLOR_PALETTE['bg']};
            color: {COLOR_PALETTE['text_primary']};
        }}
        QLabel {{
            color: {COLOR_PALETTE['text_primary']};
        }}
        """
    )

    # Icône application (tray)
    icon_ico = resource_path('monitor_pdp.ico')
    icon_png = resource_path('monitor_pdp.png')
    icon = QIcon(icon_ico) if os.path.exists(icon_ico) else (QIcon(icon_png) if os.path.exists(icon_png) else QIcon())
    if not icon.isNull():
        app.setWindowIcon(icon)

    w = MainWindow()
    w.show()
    sys.exit(app.exec())