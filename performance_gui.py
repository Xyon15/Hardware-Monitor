# -*- coding: utf-8 -*-
"""
Interface de suivi des performances (CPU, RAM, GPU, VRAM) avec indicateurs circulaires.
- Thème sombre et palette d'accents.
- Mise à jour en temps réel via un service local PerformStatsSensorService (HTTP).

Exécution:
  pip install PySide6
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
from typing import Optional

# Tentative d'import PySide6 puis fallback PyQt5
QT_BACKEND = "PySide6"
try:
    from PySide6.QtCore import Qt, QTimer, QPointF
    from PySide6.QtGui import QColor, QPainter, QPen, QFont
    from PySide6.QtWidgets import (
        QApplication,
        QWidget,
        QLabel,
        QVBoxLayout,
        QGridLayout,
        QFrame,
        QMainWindow,
    )
except Exception:  # noqa: BLE001
    QT_BACKEND = "PyQt5"
    from PyQt5.QtCore import Qt, QTimer, QPointF  # type: ignore
    from PyQt5.QtGui import QColor, QPainter, QPen, QFont  # type: ignore
    from PyQt5.QtWidgets import (  # type: ignore
        QApplication,
        QWidget,
        QLabel,
        QVBoxLayout,
        QGridLayout,
        QFrame,
        QMainWindow,
    )

# Debug helper (enable with env PERF_STATS_DEBUG=1)
DEBUG = os.getenv("PERF_STATS_DEBUG", "0") == "1"


def dprint(msg: str) -> None:
    if DEBUG:
        try:
            print(f"[Perform-Stats] {msg}")
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
}


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
        self._value = 0  # 0..100
        self._subtext = ""  # ex: température ou autre
        self.setMinimumSize(160, 160)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_value(self, value: float) -> None:
        self._value = max(0, min(100, float(value)))
        self.update()

    def set_subtext(self, text: str) -> None:
        self._subtext = text
        self.update()

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
            self.set_subtext(f"{int(round(temp_c))}°C")
            # Mise à jour couleur selon température
            self.color = self._color_from_temperature(temp_c)
        else:
            self.set_subtext("N/A")
            self.color = QColor(COLOR_PALETTE["text_secondary"])  # gris si inconnu
        self.update()

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

        # Titre
        title = QLabel("Stats systèmes")
        title.setStyleSheet(
            f"color: {COLOR_PALETTE['text_primary']}; font-size: 18px; font-weight: bold;"
        )
        title.setAlignment(Qt.AlignCenter)
        perf_layout.addWidget(title)

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


# -----------------
# Fenêtre principale
# -----------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Moniteur de Performances")
        self.setMinimumSize(720, 520)
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)

        # Panel de performance
        self.panel = PerformancePanel()
        main_layout.addWidget(self.panel, 1)

        # Config service
        self.service_url = os.getenv("PERF_STATS_SERVICE_URL", "http://127.0.0.1:9755/metrics")
        # Timeouts plus tolérants pour éviter les timeouts sporadiques
        self.http_timeout = float(os.getenv("PERF_STATS_HTTP_TIMEOUT", "1.0"))  # secondes

        # Dernières métriques valides pour éviter le clignotement à zéro
        self._last_metrics = None

        dprint(f"QT_BACKEND={QT_BACKEND}; service_url={self.service_url}; timeout={self.http_timeout}s")

        # Démarrage MAJ périodique
        self._start_timer()

    # -------- Service HTTP local --------
    def _get_metrics_from_service(self):
        import json
        import urllib.request
        try:
            with urllib.request.urlopen(self.service_url, timeout=self.http_timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            dprint(f"Service HTTP indisponible: {e}")
            return None

    def _apply_service_metrics(self, svc) -> None:
        # CPU
        cpu = svc.get("cpu", {})
        cpu_load = cpu.get("load")
        if isinstance(cpu_load, (int, float)):
            self.panel.cpu_indicator.set_value(cpu_load)
        else:
            self.panel.cpu_indicator.set_value(0.0)
        cpu_temp = cpu.get("temp_c")
        if isinstance(cpu_temp, (int, float)):
            self.panel.cpu_indicator.set_subtext(f"{int(round(cpu_temp))}°C")
        else:
            # Afficher N/A si indisponible pour cohérence avec GPU
            self.panel.cpu_indicator.set_subtext("N/A")

        # RAM
        ram = svc.get("ram", {})
        ram_pct = ram.get("used_pct")
        if isinstance(ram_pct, (int, float)):
            self.panel.ram_indicator.set_value(ram_pct)
        else:
            self.panel.ram_indicator.set_value(0.0)
        # Sous-texte RAM: "used/total Go" si disponible
        ru = ram.get("used_gb")
        rt = ram.get("total_gb")
        if isinstance(ru, (int, float)) and isinstance(rt, (int, float)) and rt > 0:
            self.panel.ram_indicator.set_subtext(f"{ru:.1f}/{rt:.0f}Go")
        else:
            self.panel.ram_indicator.set_subtext("")

        # GPU
        gpu = svc.get("gpu", {})
        gpu_load = gpu.get("load")
        gpu_temp = gpu.get("temp_c")
        self.panel.gpu_indicator.set_stats(float(gpu_load or 0.0), float(gpu_temp) if isinstance(gpu_temp, (int, float)) else None)

        # VRAM
        vram = svc.get("vram", {})
        vram_pct = vram.get("used_pct")
        if isinstance(vram_pct, (int, float)):
            self.panel.vram_indicator.set_value(vram_pct)
        else:
            self.panel.vram_indicator.set_value(0.0)
        # Sous-texte VRAM: "used/total Go" si disponible
        vu = vram.get("used_gb")
        vt = vram.get("total_gb")
        if isinstance(vu, (int, float)) and isinstance(vt, (int, float)) and vt > 0:
            self.panel.vram_indicator.set_subtext(f"{vu:.1f}/{vt:.0f}Go")
        else:
            self.panel.vram_indicator.set_subtext("")

    def _clear_metrics(self) -> None:
        self.panel.cpu_indicator.set_value(0.0)
        self.panel.cpu_indicator.set_subtext("N/A")
        self.panel.ram_indicator.set_value(0.0)
        self.panel.ram_indicator.set_subtext("N/A")
        self.panel.gpu_indicator.set_stats(0.0, None)
        self.panel.vram_indicator.set_value(0.0)
        self.panel.vram_indicator.set_subtext("N/A")

    def _start_timer(self) -> None:
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_metrics)
        self.timer.start(1000)  # 1 sec

    def _update_metrics(self) -> None:
        svc = self._get_metrics_from_service()
        if svc:
            # Mémorise et applique
            self._last_metrics = svc
            self._apply_service_metrics(svc)
        else:
            # Si service KO, conserver la dernière valeur pour éviter le clignotement
            if self._last_metrics is not None:
                self._apply_service_metrics(self._last_metrics)
            else:
                self._clear_metrics()


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

    w = MainWindow()
    w.show()
    sys.exit(app.exec())