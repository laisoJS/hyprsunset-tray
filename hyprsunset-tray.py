import sys
import shlex
import signal
import logging
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, QSettings, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMenu, QSlider,
    QSystemTrayIcon, QWidget
)
from PyQt6.QtNetwork import QLocalSocket


SETTINGS = QSettings("hyprsunset_tray", "settings")
MIN_TEMP = 2000
MAX_TEMP = 6000
STEP = 100
DEFAULT_TEMP = SETTINGS.value("temperature", 4000, int)
HYPRSUNSET_BIN = "hyprsunset"

LOG_DIR = Path.home() / ".local" / "share"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "hyprsunset_tray.log"),
        logging.StreamHandler(sys.stderr),
    ],
)
log = logging.getLogger("hyprsunset_tray")


class HyprsunsetController(QObject):
    state_changed = pyqtSignal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.process: QProcess | None = None
        self._temperature: int = DEFAULT_TEMP

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.state() == QProcess.ProcessState.Running

    @property
    def temperature(self) -> int:
        return self._temperature

    def set_temperature(self, kelvin: int) -> None:
        self._temperature = max(MIN_TEMP, min(MAX_TEMP, kelvin))
        SETTINGS.setValue("temperature", self._temperature)
        if self.is_running:
            self._restart()

    def start(self) -> bool:
        if self.is_running:
            return True

        self.process = QProcess(self)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_error)

        args = ["-t", str(self._temperature)]
        log.info("Starting hyprsunset with args: %s", shlex.join(args))

        self.process.start(HYPRSUNSET_BIN, args)
        ok = self.process.waitForStarted(1000)
        if not ok:
            log.error("Failed to start hyprsunset")
            return False

        self.state_changed.emit(True)
        return True

    def stop(self) -> None:
        if not self.is_running or not self.process:
            return

        log.info("Stopping hyprsunset")
        if not self.process.waitForFinished(1000):
            self.process.kill()

    def _restart(self) -> None:
        self.stop()
        QTimer.singleShot(50, self.start)

    def _on_finished(self) -> None:
        log.info("hyprsunset terminated")
        self.state_changed.emit(False)

    def _on_error(self, error: QProcess.ProcessError) -> None:
        log.error("QProcess error: %s", error)


class TempDialog(QWidget):
    """Floating temperature control dialog."""
    def __init__(self, controller: HyprsunsetController, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Hyprsunset Temperature")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(300, 90)

        self._pending = controller.temperature

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(MIN_TEMP, MAX_TEMP)
        self.slider.setSingleStep(STEP)
        self.slider.setValue(self._pending)
        self.label = QLabel(f"{self._pending}K")

        layout.addWidget(QLabel("Temperature:"))
        layout.addWidget(self.slider)
        layout.addWidget(self.label)

        self.slider.valueChanged.connect(lambda v: self.label.setText(f"{v}K"))
        self.slider.valueChanged.connect(lambda v: setattr(self, "_pending", v))
    def closeEvent(self, a0) -> None:
        self.controller.set_temperature(self._pending)
        return super().closeEvent(a0)


class HyprsunsetTray(QSystemTrayIcon):
    def __init__(self, controller: HyprsunsetController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.temp_dialog: TempDialog | None = None

        self.menu = QMenu()

        # Toggle action (on/off)
        self.toggle_action = QAction("Enable Hyprsunset", self)
        self.toggle_action.triggered.connect(self._toggle)
        self.menu.addAction(self.toggle_action)

        # Temperature dialog action
        self.menu.addSeparator()
        self.temp_action = QAction("Temperature...", self)

        self.temp_action.triggered.connect(self._show_temp_dialog)
        self.menu.addAction(self.temp_action)

        # Exit
        self.menu.addSeparator()
        quit_action = QAction("Exit", self)
        quit_action.triggered.connect(QApplication.quit)
        self.menu.addAction(quit_action)

        self.setContextMenu(self.menu)
        self.setToolTip(f"Hyprsunset: {self.controller.temperature}K")
        self.activated.connect(self._on_activated)

        self.controller.state_changed.connect(self._on_controller_state_changed)
        self._on_controller_state_changed(self.controller.is_running)

        if SETTINGS.value("enabled", False, bool):
            self.controller.start()

    def _toggle(self) -> None:
        if self.controller.is_running:
            self.controller.stop()
        else:
            self.controller.start()

    def _show_temp_dialog(self) -> None:
        if self.temp_dialog is None:
            self.temp_dialog = TempDialog(self.controller, parent=None)

        self.temp_dialog.show()
        self.temp_dialog.raise_()
        self.temp_dialog.activateWindow()

    def _on_controller_state_changed(self, running: bool) -> None:
        self.setIcon(self._icon_for_state(running))
        self.toggle_action.setText("Disable Hyprsunset" if running else "Enable Hyprsunset")
        self.setToolTip(f"Hyprsunset: {self.controller.temperature}K")
        SETTINGS.setValue("enabled", running)

        self.temp_action.setEnabled(running)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle()

    @staticmethod
    def _icon_for_state(running: bool) -> QIcon:
        icon_name = "weather-clear-night" if running else "weather-clear"
        if QIcon.hasThemeIcon(icon_name):
            return QIcon.fromTheme(icon_name)

        color = QColor("#ffcc00" if running else "#ffffff")
        pm = QPixmap(32, 32)
        pm.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(color)
        painter.drawEllipse(4, 4, 24, 24)
        painter.end()

        return QIcon(pm)


def main() -> None:
    socket = QLocalSocket()
    socket.connectToServer("hyprsunset_tray")
    if socket.waitForConnected(200):
        log.warning("Another instance is already running")
        return

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    signal.signal(signal.SIGINT, lambda *_: app.quit())

    controller = HyprsunsetController()
    tray = HyprsunsetTray(controller)
    tray.show()

    log.info("Hyprsunset tray started.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

