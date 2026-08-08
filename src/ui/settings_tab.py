"""Onglet Paramètres : configuration générale, auto-démarrage, dossier."""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QCheckBox, QFileDialog, QLineEdit, QMessageBox,
    QGridLayout, QComboBox, QSpinBox, QColorDialog
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtSvg import QSvgRenderer

from src.utils.config import Config
from src.core.autostart import AutostartManager


class SettingsTab(QWidget):
    """Paramètres généraux de l'application."""

    def __init__(self, config: Config, autostart: AutostartManager, icon_path: Path = None):
        super().__init__()
        self.config = config
        self.autostart = autostart
        self.icon_path = icon_path
        self._loading = True  # Flag pour éviter les popups au chargement initial
        self._setup_ui()
        self._load_settings()
        self._loading = False

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # === Auto-démarrage ===
        boot_group = QGroupBox("Auto-start")
        boot_outer = QHBoxLayout(boot_group)
        boot_outer.setSpacing(10)

        boot_layout = QVBoxLayout()

        self.autostart_app_check = QCheckBox(
            "Launch ROCmFP4 Manager at system startup"
        )
        self.autostart_app_check.toggled.connect(self._on_autostart_toggle)
        boot_layout.addWidget(self.autostart_app_check)

        self.autostart_server_check = QCheckBox(
            "Auto-start server with last used model"
        )
        self.autostart_server_check.toggled.connect(self._on_setting_changed)
        boot_layout.addWidget(self.autostart_server_check)

        self.silent_start_check = QCheckBox(
            "Start silently (minimized to system tray)"
        )
        self.silent_start_check.toggled.connect(self._on_setting_changed)
        boot_layout.addWidget(self.silent_start_check)

        self.service_status_label = QLabel("Service status: checking...")
        boot_layout.addWidget(self.service_status_label)

        service_btn_row = QHBoxLayout()
        self.install_service_btn = QPushButton("Install as systemd service")
        self.install_service_btn.setMinimumHeight(32)
        self.install_service_btn.clicked.connect(self._install_service)
        service_btn_row.addWidget(self.install_service_btn)

        self.uninstall_service_btn = QPushButton("Uninstall service")
        self.uninstall_service_btn.setMinimumHeight(32)
        self.uninstall_service_btn.clicked.connect(self._uninstall_service)
        service_btn_row.addWidget(self.uninstall_service_btn)
        service_btn_row.addStretch()
        boot_layout.addLayout(service_btn_row)

        boot_outer.addLayout(boot_layout, 1)

        # Logo à droite
        svg_path = Path(__file__).parent.parent.parent / "assets" / "icon.svg"
        if svg_path.exists() and self.icon_path:
            from PySide6.QtGui import QPainter
            renderer = QSvgRenderer(str(svg_path))
            logo_pixmap = QPixmap(100, 100)
            logo_pixmap.fill(Qt.transparent)
            painter = QPainter(logo_pixmap)
            renderer.render(painter)
            painter.end()
            logo_lbl = QLabel()
            logo_lbl.setPixmap(logo_pixmap)
            logo_lbl.setAlignment(Qt.AlignCenter)
            logo_lbl.setStyleSheet("background: transparent; border: none;")
            boot_outer.addWidget(logo_lbl, 0)

        layout.addWidget(boot_group)

        # === Langue + Thème sur une ligne ===
        lang_theme_row = QHBoxLayout()
        lang_theme_row.setSpacing(10)

        # Langue
        lang_group = QGroupBox("Language")
        lang_layout = QHBoxLayout(lang_group)
        lang_layout.addWidget(QLabel("Language:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("English", "en")
        self.lang_combo.addItem("Français", "fr")
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        lang_layout.addWidget(self.lang_combo)
        lang_layout.addStretch()
        lang_theme_row.addWidget(lang_group, 1)

        # Thème
        theme_group = QGroupBox("Theme")
        theme_layout = QHBoxLayout(theme_group)
        theme_layout.setSpacing(8)

        theme_layout.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        theme_layout.addWidget(self.theme_combo)

        theme_layout.addWidget(QLabel("Accent:"))
        self.accent_color_btn = QPushButton()
        self.accent_color_btn.setFixedSize(28, 22)
        self.accent_color_btn.clicked.connect(self._pick_accent_color)
        theme_layout.addWidget(self.accent_color_btn)

        theme_layout.addWidget(QLabel("Bg:"))
        self.bg_color_btn = QPushButton()
        self.bg_color_btn.setFixedSize(28, 22)
        self.bg_color_btn.clicked.connect(self._pick_bg_color)
        theme_layout.addWidget(self.bg_color_btn)

        lang_theme_row.addWidget(theme_group, 1)

        layout.addLayout(lang_theme_row)

        # === Dossier des modèles ===
        paths_group = QGroupBox("📂 Paths")
        paths_grid = QGridLayout(paths_group)
        paths_grid.setSpacing(8)

        paths_grid.addWidget(QLabel("GGUF models folder:"), 0, 0)
        self.models_path_input = QLineEdit()
        self.models_path_input.setReadOnly(True)
        paths_grid.addWidget(self.models_path_input, 0, 1)
        self.browse_models_btn = QPushButton("📂 Parcourir")
        self.browse_models_btn.clicked.connect(self._browse_models_path)
        paths_grid.addWidget(self.browse_models_btn, 0, 2)
        self.open_models_btn = QPushButton("📂 Ouvrir")
        self.open_models_btn.clicked.connect(self._open_models_path)
        paths_grid.addWidget(self.open_models_btn, 0, 3)

        paths_grid.addWidget(QLabel("ROCmFPX folder (source):"), 1, 0)
        self.rocmfpx_path_input = QLineEdit()
        self.rocmfpx_path_input.setReadOnly(True)
        self.rocmfpx_path_input.setPlaceholderText("Détection automatique...")
        paths_grid.addWidget(self.rocmfpx_path_input, 1, 1)
        self.browse_rocmfpx_btn = QPushButton("📂 Parcourir")
        self.browse_rocmfpx_btn.clicked.connect(self._browse_rocmfpx_path)
        paths_grid.addWidget(self.browse_rocmfpx_btn, 1, 2)

        paths_grid.addWidget(QLabel("LM Studio folder (auto-detect):"), 2, 0)
        self.lmstudio_path_label = QLabel(str(Path.home() / ".lmstudio" / "models"))
        self.lmstudio_path_label.setStyleSheet("font-family: monospace;")
        paths_grid.addWidget(self.lmstudio_path_label, 2, 1, 1, 3)

        layout.addWidget(paths_group)

        # === Serveur ===
        srv_group = QGroupBox("🌐 Server")
        srv_grid = QGridLayout(srv_group)
        srv_grid.setSpacing(8)

        srv_grid.addWidget(QLabel("Port:"), 0, 0)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(1412)
        self.port_spin.setMinimumHeight(32)
        srv_grid.addWidget(self.port_spin, 0, 1)

        srv_grid.addWidget(QLabel("Host:"), 0, 2)
        self.host_input = QLineEdit("127.0.0.1")
        self.host_input.setMinimumHeight(32)
        srv_grid.addWidget(self.host_input, 0, 3)

        srv_grid.addWidget(QLabel("Reasoning format:"), 1, 0)
        self.reasoning_combo = QComboBox()
        self.reasoning_combo.addItems(["deepseek", "off", ""])
        self.reasoning_combo.setMinimumHeight(32)
        srv_grid.addWidget(self.reasoning_combo, 1, 1)

        srv_grid.addWidget(QLabel("API Key:"), 1, 2)
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Leave empty to disable")
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setMinimumHeight(32)
        srv_grid.addWidget(self.api_key_input, 1, 3)

        self.gen_key_btn = QPushButton("🔑 Generate")
        self.gen_key_btn.clicked.connect(self._generate_api_key)
        srv_grid.addWidget(self.gen_key_btn, 1, 4)

        layout.addWidget(srv_group)

        # === À propos ===
        about_group = QGroupBox("About")
        about_layout = QVBoxLayout(about_group)

        about_layout.addWidget(QLabel("ROCmFP4 Manager v0.1.0 by Necti"))
        about_layout.addWidget(QLabel(
            "GUI to download, configure, and run "
            "ROCmFP4 GGUF models on AMD Strix Halo."
        ))
        about_layout.addWidget(QLabel(
            "GitHub: https://github.com/Yohan30/ROCmFP4-Manager"
        ))
        about_layout.addWidget(QLabel(
            "ROCmFPX: https://github.com/charlie12345/ROCmFPX"
        ))

        layout.addWidget(about_group)

        # === Boutons ===
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("Save settings")
        self.save_btn.setMinimumHeight(38)
        self.save_btn.clicked.connect(self._save_settings)
        btn_layout.addWidget(self.save_btn)

        self.update_btn = QPushButton("Check for update")
        self.update_btn.setMinimumHeight(38)
        self.update_btn.clicked.connect(self._check_for_update)
        btn_layout.addWidget(self.update_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        layout.addStretch()

    def _load_settings(self):
        self.models_path_input.setText(str(self.config.models_path))
        rocmfpx_path = self.config.get("rocmfpx_path", "")
        if rocmfpx_path:
            self.rocmfpx_path_input.setText(rocmfpx_path)
        else:
            # Détection
            default = Path.home() / "ROCMFPX"
            if default.exists():
                self.rocmfpx_path_input.setText(str(default))

        self.autostart_app_check.setChecked(self.config.get("autostart_app", False))
        self.autostart_server_check.setChecked(self.config.get("autostart_server", False))
        self.silent_start_check.setChecked(self.config.get("silent_start", True))

        # Langue
        lang = self.config.get("language", "en")
        idx = self.lang_combo.findData(lang)
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)

        # Thème
        theme = self.config.get("theme", "dark")
        idx = self.theme_combo.findData(theme)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)

        # Couleurs
        accent = self.config.get("accent_color", "#e94560")
        self.accent_color_btn.setStyleSheet(f"background-color: {accent}; border: 1px solid #888; border-radius: 3px;")
        bg = self.config.get("bg_color", "#1a1a2e")
        self.bg_color_btn.setStyleSheet(f"background-color: {bg}; border: 1px solid #888; border-radius: 3px;")

        # Serveur
        self.port_spin.setValue(int(self.config.get("port", 1412)))
        self.host_input.setText(self.config.get("host", "127.0.0.1"))
        self.reasoning_combo.setCurrentText(self.config.get("reasoning_format", "deepseek"))
        self.api_key_input.setText(self.config.get("api_key", ""))

        # Statut du service
        if self.autostart.is_app_autostart_enabled():
            self.service_status_label.setText("✅ Auto-start service: active")
            self.service_status_label.setStyleSheet("color: #34a853;")
        else:
            self.service_status_label.setText("❌ Auto-start service: inactive")
            self.service_status_label.setStyleSheet("color: #ea4335;")

    def _save_settings(self):
        self.config.set("autostart_app", self.autostart_app_check.isChecked())
        self.config.set("autostart_server", self.autostart_server_check.isChecked())
        self.config.set("silent_start", self.silent_start_check.isChecked())
        self.config.set("language", self.lang_combo.currentData())
        self.config.set("port", self.port_spin.value())
        self.config.set("host", self.host_input.text())
        self.config.set("reasoning_format", self.reasoning_combo.currentText())
        self.config.set("api_key", self.api_key_input.text())
        self.config.set("api_key_enabled", bool(self.api_key_input.text()))
        self.config.save()
        QMessageBox.information(self, "Settings", "Settings saved ✓")

    def _check_for_update(self):
        """Vérifie si une mise à jour est disponible sur GitHub."""
        import requests, webbrowser
        repo_url = "Yohan30/ROCmFP4-Manager"
        api_url = f"https://api.github.com/repos/{repo_url}/releases/latest"
        current = "v0.1.0"
        try:
            self.update_btn.setEnabled(False)
            self.update_btn.setText("Checking...")
            from PySide6.QtCore import QCoreApplication
            QCoreApplication.processEvents()

            resp = requests.get(api_url, timeout=10)
            self.update_btn.setEnabled(True)
            self.update_btn.setText("Check for update")

            if resp.status_code == 200:
                latest = resp.json().get("tag_name", "unknown")
                body = resp.json().get("body", "")
                if latest != current:
                    dialog = QMessageBox(self)
                    dialog.setWindowTitle("Update available")
                    dialog.setIcon(QMessageBox.Information)
                    dialog.setText(f"New version: {latest}")
                    dialog.setInformativeText(f"Current: {current}\n\n{body}")
                    update_btn = dialog.addButton("Download & Install", QMessageBox.AcceptRole)
                    dialog.addButton("Open release page", QMessageBox.HelpRole)
                    cancel_btn = dialog.addButton("Later", QMessageBox.RejectRole)
                    dialog.exec()

                    if dialog.clickedButton() == update_btn:
                        self._perform_update(repo_url, latest)
                    elif dialog.clickedButton() != cancel_btn:
                        webbrowser.open(f"https://github.com/{repo_url}/releases/latest")
                else:
                    QMessageBox.information(self, "Up to date", f"Running latest version ({current}).")
            elif resp.status_code == 404:
                QMessageBox.information(self, "No releases", "No releases yet.\nCreate a release on GitHub to enable updates.")
            else:
                QMessageBox.warning(self, "Error", f"GitHub API error: {resp.status_code}")
        except Exception as e:
            self.update_btn.setEnabled(True)
            self.update_btn.setText("Check for update")
            QMessageBox.warning(self, "Network error", f"Could not check for updates:\n{e}")

    def _perform_update(self, repo_url: str, version: str):
        """Télécharge et installe la mise à jour via git pull, puis redémarre."""
        import subprocess, sys, os, shutil
        repo_dir = Path(__file__).parent.parent.parent

        if not shutil.which("git"):
            QMessageBox.warning(self, "Error", "Git is required for updates.\nPlease run: git pull")
            return

        reply = QMessageBox.question(
            self, "Confirm update",
            f"Update to {version} and restart?\nUnsaved changes will be lost.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        try:
            result = subprocess.run(
                ["git", "-C", str(repo_dir), "pull", "origin", "main"],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                # Force fetch + reset si conflit
                subprocess.run(["git", "-C", str(repo_dir), "fetch", "origin"], timeout=30)
                subprocess.run(["git", "-C", str(repo_dir), "reset", "--hard", "origin/main"], timeout=30)

            QMessageBox.information(self, "Done", f"Updated to {version}.\nRestarting...")

            # Redémarrage
            python = sys.executable
            script = str(repo_dir / "src" / "main.py")
            os.execv(python, [python, script])

        except Exception as e:
            QMessageBox.warning(self, "Update failed", str(e))

    def _generate_api_key(self):
        import secrets
        key = secrets.token_hex(32)
        self.api_key_input.setText(key)
        self.api_key_input.setEchoMode(QLineEdit.Normal)

    def _on_language_changed(self, index):
        lang = self.lang_combo.itemData(index)
        self.config.set("language", lang)
        self.config.save()
        from src.utils.i18n import set_language
        set_language(lang)
        if self._loading:
            return  # Ne pas afficher le popup pendant le chargement initial
        QMessageBox.information(
            self,
            "Language / Langue",
            "🇬🇧 Please restart the application for the language change to take full effect.\n\n"
            "🇫🇷 Veuillez redémarrer l'application pour que le changement de langue "
            "soit complètement appliqué."
        )

    def _on_theme_changed(self, index):
        theme = self.theme_combo.itemData(index)
        self.config.set("theme", theme)
        self.config.save()
        QMessageBox.information(
            self, "Theme",
            "Please restart the application for the theme change to take effect."
        )

    def _pick_accent_color(self):
        current = self.config.get("accent_color", "#e94560")
        color = QColorDialog.getColor(QColor(current), self, "Choose accent color")
        if color.isValid():
            self.config.set("accent_color", color.name())
            self.config.save()
            self.accent_color_btn.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #888; border-radius: 3px;")
            QMessageBox.information(self, "Color", "Restart the application to apply the new accent color.")

    def _pick_bg_color(self):
        current = self.config.get("bg_color", "#1a1a2e")
        color = QColorDialog.getColor(QColor(current), self, "Choose background color")
        if color.isValid():
            self.config.set("bg_color", color.name())
            self.config.save()
            self.bg_color_btn.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #888; border-radius: 3px;")
            QMessageBox.information(self, "Color", "Restart the application to apply the new background color.")

    def _on_autostart_toggle(self, checked: bool):
        if checked:
            ok = self.autostart.enable_app_autostart()
            if ok:
                self.service_status_label.setText("✅ Service d'auto-démarrage: actif")
                self.service_status_label.setStyleSheet("color: #34a853;")
            else:
                QMessageBox.warning(self, "Error",
                                    "Cannot enable auto-start.\n"
                                    "Check that systemd is available.")
                self.autostart_app_check.setChecked(False)
        else:
            self.autostart.disable_app_autostart()
            self.service_status_label.setText("❌ Service d'auto-démarrage: inactif")
            self.service_status_label.setStyleSheet("color: #ea4335;")

    def _on_setting_changed(self):
        """Sauvegarde immédiate des checkboxes secondaires."""
        self.config.set("autostart_server", self.autostart_server_check.isChecked())
        self.config.set("silent_start", self.silent_start_check.isChecked())
        self.config.save()

    def _install_service(self):
        """Installe le service systemd utilisateur."""
        ok = self.autostart.enable_app_autostart()
        if ok:
            self.autostart_app_check.setChecked(True)
            self.service_status_label.setText("✅ Service installé et activé")
            self.service_status_label.setStyleSheet("color: #34a853;")
            QMessageBox.information(self, "Service", "Service systemd installé avec succès !\nL'application démarrera automatiquement au login.")
        else:
            QMessageBox.warning(self, "Erreur", "Impossible d'installer le service.\nVérifiez que systemd est disponible.")

    def _uninstall_service(self):
        """Désinstalle le service systemd."""
        self.autostart.disable_app_autostart()
        self.autostart_app_check.setChecked(False)
        self.service_status_label.setText("❌ Service désinstallé")
        self.service_status_label.setStyleSheet("color: #ea4335;")
        QMessageBox.information(self, "Service", "Service systemd désinstallé.")

    def _browse_models_path(self):
        path = QFileDialog.getExistingDirectory(
            self, "Choose models folder",
            str(self.config.models_path)
        )
        if path:
            self.models_path_input.setText(path)
            self.config.set("models_path", path)
            self.config.save()

    def _browse_rocmfpx_path(self):
        path = QFileDialog.getExistingDirectory(
            self, "Choose ROCmFPX folder",
            str(self.config.get("rocmfpx_path", str(Path.home() / "ROCMFPX")))
        )
        if path:
            self.rocmfpx_path_input.setText(path)
            self.config.set("rocmfpx_path", path)
            self.config.save()

    def _open_models_path(self):
        import subprocess
        subprocess.run(["xdg-open", str(self.config.models_path)])
