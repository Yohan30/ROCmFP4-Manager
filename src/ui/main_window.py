"""Fenêtre principale de l'application."""

from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QStatusBar, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QIcon, QPixmap

from src.ui.server_tab import ServerTab
from src.ui.config_tab import ConfigTab
from src.ui.models_tab import ModelsTab
from src.ui.bench_tab import BenchTab
from src.ui.rocmfpx_tab import ROCmFPXTab
from src.ui.chat_tab import ChatTab
from src.ui.settings_tab import SettingsTab
from src.core.server_controller import ServerController
from src.core.rocmfpx_manager import ROCmFPXManager
from src.core.model_manager import ModelManager
from src.core.autostart import AutostartManager
from src.utils.config import Config


class MainWindow(QMainWindow):
    """Fenêtre principale avec les onglets."""

    APP_NAME = "ROCmFP4 Manager"
    VERSION = "0.2.0"

    _server_signal = Signal(str, object)

    def __init__(self, config: Config, server: ServerController,
                 rocmfpx: ROCmFPXManager, models: ModelManager,
                 autostart: AutostartManager, icon_path: Path):
        super().__init__()
        self.config = config
        self.server = server
        self.rocmfpx = rocmfpx
        self.models_mgr = models
        self.autostart = autostart
        self._icon_path = icon_path

        self.setWindowTitle(self.APP_NAME)
        self.setMinimumSize(1100, 720)
        self.resize(1280, 832)
        self.setWindowIcon(QIcon(str(icon_path)))

        self._setup_ui()
        self._setup_statusbar()
        self._connect_signals()

        # Timer rafraîchissement
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(2000)
        self._refresh_timer.timeout.connect(self._refresh_status)
        self._refresh_timer.start()

    def _get_icon_path(self) -> Path:
        return self._icon_path

    def _setup_ui(self):
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        # Onglets
        self.server_tab = ServerTab(self.server, self.config, self._icon_path)
        self.config_tab = ConfigTab(self.config, self.server)
        self.models_tab = ModelsTab(self.models_mgr, self.config)
        self.bench_tab = BenchTab(self.config, self.rocmfpx)
        self.rocmfpx_tab = ROCmFPXTab(self.rocmfpx, self.config)
        self.settings_tab = SettingsTab(self.config, self.autostart, self._icon_path)

        self.tabs.addTab(self.server_tab, "🖥️ Server")
        self.tabs.addTab(self.config_tab, "⚙️ Configuration")
        self.tabs.addTab(self.models_tab, "📦 Models")
        self.tabs.addTab(self.rocmfpx_tab, "🔧 ROCmFPX")
        self.tabs.addTab(self.bench_tab, "🏋️ Bench")

        # Chat tab (créé après le reste pour avoir l'API)
        self.chat_tab = ChatTab(self.config, self.server)
        self.tabs.addTab(self.chat_tab, "💬 Chat")

        self.tabs.addTab(self.settings_tab, "🔧 Settings")

        self.setCentralWidget(self.tabs)

    def _setup_statusbar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.status_label = QLabel("Ready")
        self.server_status_label = QLabel("🔴 Server stopped")
        self.model_label = QLabel("")
        self.model_label.setAlignment(Qt.AlignCenter)
        self.tps_label = QLabel("")
        self.tps_label.setAlignment(Qt.AlignCenter)

        self.status_bar.addWidget(self.status_label, 1)
        self.status_bar.addPermanentWidget(self.model_label)
        self.status_bar.addPermanentWidget(self.tps_label)
        # Conteneur centré pour le statut serveur (côté droit)
        server_container = QWidget()
        server_layout = QHBoxLayout(server_container)
        server_layout.setContentsMargins(0, 0, 0, 0)
        server_layout.addStretch()
        server_layout.addWidget(self.server_status_label)
        server_layout.addStretch()
        self.status_bar.addPermanentWidget(server_container)

    def _connect_signals(self):
        self.server.add_listener(self._on_server_event_threadsafe)
        self._server_signal.connect(self._on_server_event_ui)
        # Quand un modèle est sélectionné dans l'onglet Models,
        # mettre à jour le champ model_path du ConfigTab → déclenche le
        # rechargement complet des paramètres spécifiques au modèle.
        self.models_tab.model_selected.connect(self._on_model_selected_from_models_tab)

    def _on_model_selected_from_models_tab(self, model_path: str):
        """Met à jour le ConfigTab quand un modèle est sélectionné depuis Models."""
        self.config_tab.model_path_input.setText(model_path)
        # Forcer le rechargement immédiat (si le champ avait déjà la même valeur,
        # textChanged ne serait pas émis)
        self.config_tab._reload_model_specific_fields()
        self.config_tab._load_model_args()
        self.config_tab._update_model_label()

    def _on_server_event_threadsafe(self, event: str, data):
        self._server_signal.emit(event, data)

    def _on_server_event_ui(self, event: str, data):
        if event == "started":
            model = data.get("model", "") if data else ""
            self.server_status_label.setText(f"🟢 Server running (PID: {self.server.pid})")
            self.model_label.setText(f"📄 {model}")
        elif event == "stopped":
            self.server_status_label.setText("🔴 Server stopped")
            self.model_label.setText("")
            self.tps_label.setText("")
        elif event == "log":
            # Extraire tokens/s pour la statusbar
            pass

    def _refresh_status(self):
        if self.server.is_running:
            tps = self.server.tokens_per_sec
            mem = self.server.memory_mb
            uptime = self.server.get_uptime_str()
            parts = [f"⚡ {tps:.1f} tok/s" if tps > 0 else ""]
            if mem:
                parts.append(f"💾 {mem:.0f} MB")
            parts.append(f"⏱ {uptime}")
            self.tps_label.setText("  |  ".join(p for p in parts if p))

    def show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        """Masquer dans la systray au lieu de fermer."""
        parent = self.parent()
        if parent and hasattr(parent, 'system_tray') and parent.system_tray.isVisible():
            event.ignore()
            self.hide()
        else:
            event.accept()
