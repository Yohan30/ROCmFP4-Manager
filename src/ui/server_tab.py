"""Onglet Serveur : contrôle, statut, logs, URLs API."""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QPlainTextEdit, QFrame, QGridLayout, QApplication,
    QLineEdit, QCheckBox, QSplitter, QSpacerItem, QSizePolicy,
    QSpinBox
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QPixmap, QPainter

from src.core.server_controller import ServerController
from src.utils.config import Config


class ServerTab(QWidget):
    """Panneau de contrôle du serveur."""

    _server_signal = Signal(str, object)

    def __init__(self, server: ServerController, config: Config, icon_path: Path = None):
        super().__init__()
        self.server = server
        self.config = config
        self.icon_path = icon_path
        self._setup_ui()
        self._connect_signals()
        self._server_signal.connect(self._on_server_event_ui)

        # Timer rafraîchissement logs
        self._log_timer = QTimer(self)
        self._log_timer.setInterval(500)
        self._log_timer.timeout.connect(self._refresh_logs)
        self._log_timer.start()

        # Timer rafraîchissement statut
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(2000)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # === Splitter vertical : contrôles (haut) / logs (bas) ===
        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setHandleWidth(6)

        # --- Widget haut : status + API + contrôles ---
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setSpacing(4)
        top_layout.setContentsMargins(10, 4, 10, 8)

        # === Barre d'état ===
        status_group = QGroupBox("Server Status")
        status_outer = QHBoxLayout(status_group)
        status_outer.setSpacing(6)

        status_grid = QGridLayout()
        status_grid.setSpacing(8)

        self.status_indicator = QLabel("● Stopped")
        self.status_indicator.setStyleSheet("font-size: 16px; font-weight: bold; color: #ea4335;")
        self.status_indicator.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        status_grid.addWidget(self.status_indicator, 0, 0, 2, 1)

        self.pid_label = QLabel("PID: —")
        status_grid.addWidget(self.pid_label, 0, 1)

        self.port_label = QLabel(f"Port: {self.config.port}")
        status_grid.addWidget(self.port_label, 0, 2)

        self.uptime_label = QLabel("Uptime: —")
        status_grid.addWidget(self.uptime_label, 1, 1)

        self.tps_label = QLabel("Tokens/s: —")
        status_grid.addWidget(self.tps_label, 1, 2)

        self.mem_label = QLabel("Memory: —")
        status_grid.addWidget(self.mem_label, 1, 3)

        self.model_label = QLabel("Model: —")
        self.model_label.setWordWrap(True)
        status_grid.addWidget(self.model_label, 2, 0, 1, 4)

        status_outer.addLayout(status_grid, 1)

        # Logo à droite (SVG redessiné)
        svg_path = self.icon_path.parent / "icon.svg"
        if svg_path.exists():
            from PySide6.QtSvg import QSvgRenderer
            renderer = QSvgRenderer(str(svg_path))
            logo_pixmap = QPixmap(120, 120)
            logo_pixmap.fill(Qt.transparent)
            painter = QPainter(logo_pixmap)
            renderer.render(painter)
            painter.end()
            logo_lbl = QLabel()
            logo_lbl.setPixmap(logo_pixmap)
            logo_lbl.setAlignment(Qt.AlignCenter)
            logo_lbl.setStyleSheet("background: transparent; border: none;")
            status_outer.addWidget(logo_lbl, 0)

        top_layout.addWidget(status_group)

        # === URLs API ===
        api_group = QGroupBox("API Endpoints")
        api_layout = QVBoxLayout(api_group)

        urls = [
            ("Chat Completions", self.config.api_chat_url),
            ("Completions", self.config.api_completions_url),
            ("Embeddings", self.config.api_embeddings_url),
            ("Health", self.config.api_health_url),
            ("Web Interface", self.config.api_url),
        ]

        for label, url in urls:
            row = QHBoxLayout()
            row.addWidget(QLabel(label), 0)
            url_label = QLabel(url)
            url_label.setStyleSheet("color: #1a73e8; font-family: monospace;")
            url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row.addWidget(url_label, 1)

            if label == "Web Interface":
                port_label = QLabel("Port:")
                row.addWidget(port_label, 0)
                self.port_spin = QSpinBox()
                self.port_spin.setRange(1024, 65535)
                self.port_spin.setValue(self.config.port)
                self.port_spin.setFixedWidth(80)
                self.port_spin.setToolTip("Change server port (requires restart)")
                self.port_spin.valueChanged.connect(self._on_port_changed)
                row.addWidget(self.port_spin, 0)
                open_btn = QPushButton("Open")
                open_btn.clicked.connect(lambda: self._open_webui())
                row.addWidget(open_btn, 0)

            api_layout.addLayout(row)

        # API Key
        key_group = QGroupBox("API Key")
        key_inner = QVBoxLayout(key_group)

        # Ligne unique : champ + boutons + checkbox + status
        key_row = QHBoxLayout()
        key_row.setSpacing(0)

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Enter or paste your API key...")
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setMaximumWidth(440)
        self.api_key_input.setText(self.config.get("api_key", ""))
        self.api_key_input.textChanged.connect(self._on_api_key_text_changed)
        key_row.addWidget(self.api_key_input)

        # Espaceur fixe 36px
        spacer36 = QWidget()
        spacer36.setFixedWidth(36)
        key_row.addWidget(spacer36)

        self.key_toggle_btn = QPushButton("Show")
        self.key_toggle_btn.setToolTip("Show/Hide API key")
        self.key_toggle_btn.clicked.connect(self._toggle_api_key_visibility)
        key_row.addWidget(self.key_toggle_btn)
        key_row.addSpacing(6)

        self.key_generate_btn = QPushButton("Generate")
        self.key_generate_btn.setMinimumHeight(32)
        self.key_generate_btn.clicked.connect(self._generate_api_key)
        key_row.addWidget(self.key_generate_btn)

        key_row.addStretch()

        self.api_key_enabled_check = QCheckBox()
        self.api_key_enabled_check.setToolTip("Enable API key authentication")
        self.api_key_enabled_check.setChecked(self.config.get("api_key_enabled", False))
        self.api_key_enabled_check.toggled.connect(self._on_api_key_enabled_toggled)

        self.api_key_status_label = QLabel()
        self._update_api_key_status_label()

        # Grouper checkbox + status sans espace
        toggle_group = QHBoxLayout()
        toggle_group.setSpacing(0)
        toggle_group.addWidget(self.api_key_enabled_check)
        toggle_group.addWidget(self.api_key_status_label)
        key_row.addLayout(toggle_group)

        # Petit espace avant le bord droit
        key_row.addSpacing(60)

        key_inner.addLayout(key_row)

        top_layout.addWidget(api_group)
        top_layout.addWidget(key_group)

        # === Boutons d'action ===
        btn_group = QGroupBox("Controls")
        btn_layout = QHBoxLayout(btn_group)
        btn_layout.setSpacing(6)

        self.start_btn = QPushButton("Start")
        self.start_btn.setMinimumHeight(32)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setMinimumHeight(32)
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_btn)

        self.restart_btn = QPushButton("Restart")
        self.restart_btn.setMinimumHeight(32)
        self.restart_btn.setEnabled(False)
        btn_layout.addWidget(self.restart_btn)

        self.open_btn = QPushButton("Open Web UI")
        self.open_btn.setMinimumHeight(32)
        btn_layout.addWidget(self.open_btn)

        self.copy_api_btn = QPushButton("Copy API URL")
        self.copy_api_btn.setMinimumHeight(32)
        btn_layout.addWidget(self.copy_api_btn)

        top_layout.addWidget(btn_group)
        top_widget.setMinimumHeight(290)

        # --- Widget bas : logs ---
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(12, 12, 12, 12)

        log_header = QHBoxLayout()
        log_title = QLabel("Server Logs")
        log_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        log_header.addWidget(log_title)
        log_header.addStretch()

        self.maximize_log_btn = QPushButton("Maximize")
        self.maximize_log_btn.setFixedHeight(28)
        self.maximize_log_btn.setToolTip("Toggle log panel size")
        self.maximize_log_btn.clicked.connect(self._toggle_log_size)
        log_header.addWidget(self.maximize_log_btn)

        self.fullscreen_log_btn = QPushButton("Full Screen")
        self.fullscreen_log_btn.setFixedHeight(28)
        self.fullscreen_log_btn.setToolTip("Show logs in full screen")
        self.fullscreen_log_btn.clicked.connect(self._toggle_fullscreen_logs)
        log_header.addWidget(self.fullscreen_log_btn)

        self.clear_log_btn = QPushButton("Clear")
        self.clear_log_btn.setFixedHeight(28)
        log_header.addWidget(self.clear_log_btn)

        log_layout.addLayout(log_header)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFont(QFont("monospace", 9))
        self.log_output.document().setMaximumBlockCount(500)
        log_layout.addWidget(self.log_output, 1)

        log_widget.setMinimumHeight(100)

        # Ajouter au splitter
        self.splitter.addWidget(top_widget)
        self.splitter.addWidget(log_widget)
        self.splitter.setStretchFactor(0, 1)  # top
        self.splitter.setStretchFactor(1, 1)  # logs
        self.splitter.setSizes([620, 180])

        layout.addWidget(self.splitter, 1)
        self._log_maximized = False
        self._log_normal_sizes = [620, 180]

    def _connect_signals(self):
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        self.restart_btn.clicked.connect(self._on_restart)
        self.open_btn.clicked.connect(self._open_webui)
        self.copy_api_btn.clicked.connect(
            lambda: self._copy_url(self.config.api_url)
        )
        self.clear_log_btn.clicked.connect(self.log_output.clear)
        self.server.add_listener(self._on_server_event_threadsafe)

    def _on_server_event_threadsafe(self, event: str, data):
        self._server_signal.emit(event, data)

    def _on_server_event_ui(self, event: str, data):
        if event == "started":
            self.status_indicator.setText("● Running")
            self.status_indicator.setStyleSheet("font-size: 16px; font-weight: bold; color: #34a853;")
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.restart_btn.setEnabled(True)
            self._refresh_status()
        elif event == "stopped":
            self.status_indicator.setText("● Stopped")
            self.status_indicator.setStyleSheet("font-size: 16px; font-weight: bold; color: #ea4335;")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.restart_btn.setEnabled(False)
            self.pid_label.setText("PID: —")
            self.uptime_label.setText("Uptime: —")
            self.tps_label.setText("Tokens/s: —")
            self.mem_label.setText("Memory: —")
            self.model_label.setText("Model: —")

    def _on_start(self):
        """Démarre le serveur avec le modèle sélectionné."""
        model_path = self.config.get("last_model", "")
        mtp_path = self.config.get("last_mtp_model", "")
        mmproj_path = self.config.get("last_mmproj_model", "")
        if not model_path:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Warning",
                                "No model selected.\n"
                                "Go to the Configuration tab to choose one.")
            return
        try:
            success = self.server.start(model_path, mtp_path, mmproj_path)
            if not success:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self, "Erreur",
                    "Impossible de démarrer le serveur.\n"
                    "Un autre serveur est peut-être déjà en cours d'exécution.\n"
                    "Vérifiez dans l'onglet Server ou avec 'pgrep -a llama-server'."
                )
        except FileNotFoundError as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Erreur", str(e))

    def _on_stop(self):
        self.server.stop()

    def _on_restart(self):
        model_path = self.config.get("last_model", "")
        mtp_path = self.config.get("last_mtp_model", "")
        mmproj_path = self.config.get("last_mmproj_model", "")
        self.server.restart(model_path, mtp_path, mmproj_path)

    def _refresh_logs(self):
        if self.server.log_buffer:
            new_logs = list(self.server.log_buffer)
            self.server.log_buffer.clear()
            for line in new_logs:
                self.log_output.appendPlainText(line)
            # Scroller vers le bas
            scrollbar = self.log_output.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def _refresh_status(self):
        if self.server.is_running:
            self.uptime_label.setText(f"Uptime: {self.server.get_uptime_str()}")
            tps = self.server.tokens_per_sec
            self.tps_label.setText(f"Tokens/s: {tps:.1f}" if tps > 0 else "Tokens/s: —")
            mem = self.server.memory_mb
            self.mem_label.setText(f"Memory: {mem:.0f} MB" if mem else "Memory: —")
            self.pid_label.setText(f"PID: {self.server.pid}")
            self.model_label.setText(f"Model: {self.config.get('last_model', '—')}")

    def _on_api_key_text_changed(self, text):
        self.config.set("api_key", text)
        self.config.save()
        self._update_api_key_status_label()

    def _toggle_api_key_visibility(self):
        """Affiche/masque la clé API dans le champ de saisie."""
        if self.api_key_input.echoMode() == QLineEdit.Password:
            self.api_key_input.setEchoMode(QLineEdit.Normal)
            self.key_toggle_btn.setText("Hide")
        else:
            self.api_key_input.setEchoMode(QLineEdit.Password)
            self.key_toggle_btn.setText("Show")

    def _generate_api_key(self):
        """Génère une clé API aléatoire via openssl rand."""
        import subprocess
        try:
            result = subprocess.run(
                ["openssl", "rand", "-hex", "32"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                key = result.stdout.strip()
                self.api_key_input.setText(key)
                self.config.set("api_key", key)
                self.config.save()
                self._update_api_key_status_label()
        except Exception:
            # Fallback: génération Python
            import secrets
            key = secrets.token_hex(32)
            self.api_key_input.setText(key)
            self.config.set("api_key", key)
            self.config.save()
            self._update_api_key_status_label()

    def _copy_api_key(self):
        """Copie la clé API dans le presse-papier."""
        key = self.api_key_input.text()
        if key:
            QApplication.clipboard().setText(key)

    def _on_api_key_enabled_toggled(self, enabled):
        self.config.set("api_key_enabled", enabled)
        if enabled:
            key = self.api_key_input.text()
            if key:
                self.config.set("api_key", key)
        self.config.save()
        self._update_api_key_status_label()

    def _update_api_key_status_label(self):
        """Met à jour le label de statut de la clé API."""
        enabled = self.config.get("api_key_enabled", False)
        key = self.config.get("api_key", "")
        if enabled and key:
            self.api_key_status_label.setText("Enabled")
            self.api_key_status_label.setStyleSheet("color: #34a853; font-weight: bold;")
        elif enabled and not key:
            self.api_key_status_label.setText("No key set")
            self.api_key_status_label.setStyleSheet("color: #fbbc04; font-weight: bold;")
        else:
            self.api_key_status_label.setText("Disabled")
            self.api_key_status_label.setStyleSheet("color: #ea4335;")

    def _toggle_log_size(self):
        """Bascule entre vue normale et logs maximisés (×2)."""
        total = self.splitter.height()
        if self._log_maximized:
            # Restaurer
            self.splitter.setSizes(self._log_normal_sizes)
            self.maximize_log_btn.setText("Maximize")
            self._log_maximized = False
        else:
            # Sauvegarder tailles normales
            self._log_normal_sizes = self.splitter.sizes()
            # Doubler la hauteur des logs
            log_h = self._log_normal_sizes[1] * 2
            self.splitter.setSizes([max(80, total - log_h), log_h])
            self.maximize_log_btn.setText("Restore")
            self._log_maximized = True

    def _toggle_fullscreen_logs(self):
        """Bascule entre vue normale et logs en plein écran."""
        if not hasattr(self, '_log_fullscreen'):
            self._log_fullscreen = False
        if self._log_fullscreen:
            # Restaurer
            self.splitter.widget(0).setVisible(True)
            if hasattr(self, '_log_fs_normal_sizes'):
                self.splitter.setSizes(self._log_fs_normal_sizes)
            self.fullscreen_log_btn.setText("Full Screen")
            self._log_fullscreen = False
        else:
            # Plein écran
            self._log_fs_normal_sizes = self.splitter.sizes()
            self.splitter.widget(0).setVisible(False)
            self.fullscreen_log_btn.setText("Restore")
            self._log_fullscreen = True

    def _copy_url(self, url: str):
        QApplication.clipboard().setText(url)

    def _open_webui(self):
        import webbrowser
        webbrowser.open(self.config.api_url)

    def _on_port_changed(self, port: int):
        """Met à jour le port dans la config."""
        self.config.port = port
        self.config.set("port", port)
        self.config.save()
        self.port_label.setText(f"Port: {port}")
