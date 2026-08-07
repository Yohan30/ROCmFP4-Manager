"""Application principale PySide6."""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QPixmap, QFontDatabase, QFont

from src.utils.config import Config
from src.utils.i18n import I18n, set_language
from src.core.server_controller import ServerController
from src.core.rocmfpx_manager import ROCmFPXManager
from src.core.model_manager import ModelManager
from src.core.autostart import AutostartManager
from src.ui.main_window import MainWindow
from src.system_tray import SystemTray


class ROCmFP4App(QApplication):
    """Application ROCmFP4 Manager."""

    def __init__(self, argv: list):
        super().__init__(argv)
        self.setApplicationName("ROCmFP4 Manager")
        self.setOrganizationName("ROCmFP4")
        self.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

        # Charger la police emoji pour le rendu des icônes
        self._load_emoji_font()

        # Initialiser les services
        self.config = Config()

        # Appliquer le thème depuis la config
        theme = self.config.get("theme", "dark")
        self._apply_style(theme)

        # Icône globale de l'application
        self._icon_path = self._find_icon()
        app_icon = QIcon(str(self._icon_path))
        self.setWindowIcon(app_icon)
        # Initialiser la langue depuis la config (défaut: anglais)
        set_language(self.config.get("language", "en"))
        self.server = ServerController(self.config)
        self.rocmfpx = ROCmFPXManager(config=self.config)
        self.models_mgr = ModelManager(self.config.models_path)
        self.autostart = AutostartManager()

        # Icône
        # Fenêtre principale
        self.main_window = MainWindow(
            self.config, self.server, self.rocmfpx,
            self.models_mgr, self.autostart, self._icon_path
        )

        # Systray
        self.system_tray = SystemTray(self)
        self.system_tray.show()
        self._connect_systray()

        # Toujours afficher la fenêtre au premier lancement
        self.main_window.show()

        # Nettoyer le serveur à la fermeture
        self.aboutToQuit.connect(self.cleanup)

        # Vérifier et proposer maj ROCmFPX après 5s
        QTimer.singleShot(5000, self._check_rocmfpx_update)

    def cleanup(self):
        """Arrête proprement le serveur et les processus au quitting."""
        if hasattr(self, 'server') and self.server.is_running:
            self.server.stop()
        if hasattr(self, 'system_tray'):
            self.system_tray.hide()

    def _find_icon(self) -> Path:
        """Cherche l'icône de l'application (PNG prioritaire, SVG fallback)."""
        candidates = [
            Path(__file__).parent.parent / "assets" / "icon.png",
            Path(__file__).parent.parent / "assets" / "icon.svg",
            Path(__file__).parent / "assets" / "icon.png",
        ]
        for c in candidates:
            if c.exists():
                return c
        # Fallback
        return Path(__file__).parent.parent / "assets" / "icon.svg"

    def _load_emoji_font(self):
        """Charge la police emoji système et la configure comme fallback."""
        emoji_path = "/usr/share/fonts/google-noto-emoji-fonts/NotoEmoji-Regular.ttf"
        if Path(emoji_path).exists():
            font_id = QFontDatabase.addApplicationFont(emoji_path)
            if font_id >= 0:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    QFont.insertSubstitution("sans-serif", families[0])

    def _darken(self, hex_color: str, factor: float = 1.2) -> str:
        """Éclaircit ou assombrit une couleur hex."""
        hex_color = hex_color.lstrip("#")
        r, g, b = int(hex_color[:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        r = min(255, int(r * factor))
        g = min(255, int(g * factor))
        b = min(255, int(b * factor))
        return f"#{r:02x}{g:02x}{b:02x}"

    def _apply_style(self, theme: str = "dark"):
        """Applique le thème sombre ou clair."""
        if theme == "light":
            self._apply_light_theme()
        else:
            self._apply_dark_theme()

    def _apply_dark_theme(self):
        """Applique un thème sombre avec couleurs personnalisables."""
        accent = self.config.get("accent_color", "#e94560")
        bg = self.config.get("bg_color", "#1a1a2e")
        bg2 = self._darken(bg, 1.8)
        bg3 = self._darken(bg, 2.4)
        text = "#e0e0e0"

        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {bg};
                color: {text};
            }}
            QLabel {{
                font-weight: bold;
            }}
            QGroupBox {{
                border: 1px solid {bg3};
                border-radius: 8px;
                margin-top: 6px;
                padding: 8px 10px 8px 10px;
                font-weight: bold;
                color: {accent};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 2px 8px;
                background-color: {bg};
            }}
            QPushButton {{
                background-color: {bg2};
                color: {text};
                border: 1px solid {bg3};
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 13px;
                font-weight: bold;
                text-align: center;
            }}
            QPushButton:hover {{
                background-color: {bg3};
                border-color: {accent};
            }}
            QPushButton:pressed {{
                background-color: {bg};
            }}
            QPushButton:disabled {{
                background-color: {bg};
                color: #555;
            }}
            QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
                background-color: {bg2};
                color: {text};
                border: 1px solid {bg2};
                border-radius: 4px;
                padding: 4px 8px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {bg2};
                color: {text};
                selection-background-color: {accent};
            }}
            QTableWidget {{
                background-color: {bg2};
                color: {text};
                border: 1px solid {bg2};
                gridline-color: {bg3};
                selection-background-color: {accent};
            }}
            QHeaderView::section {{
                background-color: {bg};
                color: {accent};
                border: none;
                padding: 6px;
                font-weight: bold;
            }}
            QStatusBar {{
                background-color: {bg};
                color: {text};
                border-top: 1px solid {bg2};
            }}
            QTabWidget::pane {{
                border: none;
                background-color: {bg};
            }}
            QTabBar::tab {{
                background-color: {bg2};
                color: #aaa;
                border: none;
                padding: 8px 16px;
                margin-right: 2px;
                font-weight: bold;
            }}
            QTabBar::tab:selected {{
                background-color: {bg};
                color: {accent};
                border-bottom: 2px solid {accent};
                font-weight: bold;
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {bg2};
                color: {text};
                font-weight: bold;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 3px;
                border: 2px solid #888;
                background-color: #3a3a3a;
            }}
            QCheckBox::indicator:checked {{
                background-color: {accent};
                border-color: {accent};
            }}
            QProgressBar {{
                border: 1px solid {bg2};
                border-radius: 6px;
                text-align: center;
                color: {text};
                background-color: {bg2};
            }}
            QProgressBar::chunk {{
                background-color: {accent};
            }}
            QListWidget {{
                background-color: {bg2};
                color: {text};
                border: 1px solid {bg2};
            }}
            QListWidget::item:selected {{
                background-color: {accent};
            }}
            QScrollBar:vertical {{
                background: {bg};
                width: 10px;
            }}
            QScrollBar::handle:vertical {{
                background: {bg3};
                border-radius: 5px;
            }}
            QSplitter::handle {{
                background-color: {bg2};
            }}
        """)

    def _apply_light_theme(self):
        """Applique un thème clair avec couleurs personnalisables."""
        accent = self.config.get("accent_color", "#c0392b")
        bg = self.config.get("bg_color", "#f5f5f5")
        bg2 = "#e8e8e8"
        bg3 = "#ddd"
        text = "#333"

        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {bg};
                color: {text};
            }}
            QLabel {{
                font-weight: bold;
            }}
            QGroupBox {{
                border: 1px solid #ccc;
                border-radius: 8px;
                margin-top: 6px;
                padding: 8px 10px 8px 10px;
                font-weight: bold;
                color: {accent};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 2px 8px;
                background-color: {bg};
            }}
            QPushButton {{
                background-color: #e0e0e0;
                color: {text};
                border: 1px solid #bbb;
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 13px;
                font-weight: bold;
                text-align: center;
            }}
            QPushButton:hover {{
                background-color: #d0d0d0;
                border-color: {accent};
            }}
            QPushButton:pressed {{
                background-color: #c0c0c0;
            }}
            QPushButton:disabled {{
                background-color: {bg2};
                color: #999;
            }}
            QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
                background-color: #fff;
                color: {text};
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 4px 8px;
            }}
            QComboBox QAbstractItemView {{
                background-color: #fff;
                color: {text};
                selection-background-color: {accent};
            }}
            QTableWidget {{
                background-color: #fff;
                color: {text};
                border: 1px solid #ccc;
                gridline-color: {bg3};
                selection-background-color: {accent};
            }}
            QHeaderView::section {{
                background-color: {bg2};
                color: {accent};
                border: none;
                padding: 6px;
                font-weight: bold;
            }}
            QStatusBar {{
                background-color: {bg};
                color: {text};
                border-top: 1px solid #ccc;
            }}
            QTabWidget::pane {{
                border: none;
                background-color: {bg};
            }}
            QTabBar::tab {{
                background-color: #e0e0e0;
                color: #666;
                border: none;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QTabBar::tab:selected {{
                background-color: {bg};
                color: {accent};
                border-bottom: 2px solid {accent};
                font-weight: bold;
            }}
            QTabBar::tab:hover:!selected {{
                background-color: #d0d0d0;
                font-weight: bold;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 3px;
                border: 2px solid #999;
                background-color: #d0d0d0;
            }}
            QCheckBox::indicator:checked {{
                background-color: {accent};
                border-color: {accent};
            }}
            QProgressBar {{
                border: 1px solid #ccc;
                border-radius: 6px;
                text-align: center;
                background-color: #e0e0e0;
            }}
            QProgressBar::chunk {{
                background-color: {accent};
            }}
            QScrollBar:vertical {{
                background: #e0e0e0;
                width: 10px;
            }}
            QScrollBar::handle:vertical {{
                background: #bbb;
                border-radius: 5px;
            }}
            QListWidget {{
                background-color: #fff;
                color: {text};
                border: 1px solid #ccc;
            }}
            QListWidget::item:selected {{
                background-color: {accent};
            }}
            QSplitter::handle {{
                background-color: #ccc;
            }}
        """)

    def _connect_systray(self):
        tray = self.system_tray
        tray.action_open_chat.triggered.connect(
            lambda: self._open_api_webui()
        )
        tray.action_copy_api.triggered.connect(
            lambda: self._copy_to_clipboard(self.config.api_url)
        )
        tray.action_logs.triggered.connect(self._show_logs)
        tray.action_bench.triggered.connect(self._show_bench)
        tray.action_stop.triggered.connect(self.server.stop)
        tray.action_restart.triggered.connect(self._restart_server)
        tray.action_config.triggered.connect(self.show_window)
        tray.action_autostart.toggled.connect(self._toggle_autostart)
        tray.action_update.triggered.connect(self._check_and_update)
        tray.action_quit.triggered.connect(self.quit)

        # Initialiser l'état auto-démarrage
        tray.set_autostart_checked(self.autostart.is_app_autostart_enabled())

        # Connecter les events serveur
        self.server.add_listener(self._on_server_event)

    def _on_server_event(self, event: str, data):
        if event == "started":
            model = data.get("model", "") if data else ""
            self.system_tray.update_status("Server running", self.config.port, model)
        elif event == "stopped":
            self.system_tray.update_status("Server stopped", self.config.port)
        elif event == "error":
            self.system_tray.update_status("Error", self.config.port)
            self.system_tray.showMessage(
                "ROCmFP4 Error", str(data.get("message", "")),
                QIcon(str(self._icon_path)), 5000
            )

    def _open_url(self, url: str):
        import webbrowser
        webbrowser.open(url)

    def _open_api_webui(self):
        """Ouvre l'interface web du serveur avec la clé API si nécessaire."""
        import webbrowser
        url = self.config.api_url
        api_key = self.config.get("api_key", "")
        api_enabled = self.config.get("api_key_enabled", False)
        if api_enabled and api_key:
            url += f"?key={api_key}"
        webbrowser.open(url)

    def _copy_to_clipboard(self, text: str):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)

    def _show_logs(self):
        self.main_window.tabs.setCurrentIndex(0)  # Onglet Serveur
        self.show_window()

    def _show_bench(self):
        # Chercher l'index de l'onglet Bench
        for i in range(self.main_window.tabs.count()):
            if "Bench" in self.main_window.tabs.tabText(i):
                self.main_window.tabs.setCurrentIndex(i)
                break
        self.show_window()

    def _restart_server(self):
        model_path = self.config.get("last_model", "")
        mtp_path = self.config.get("last_mtp_model", "")
        self.server.restart(model_path, mtp_path)

    def _toggle_autostart(self, checked: bool):
        if checked:
            self.autostart.enable_app_autostart()
        else:
            self.autostart.disable_app_autostart()

    def _check_and_update(self):
        """Vérifie et propose les mises à jour ROCmFPX."""
        if not self.rocmfpx.is_installed:
            QMessageBox.information(self.main_window, "ROCmFPX",
                                    "ROCmFPX is not installed yet.\n"
                                    "Go to the ROCmFPX tab to install it.")
            return

        has_update = self.rocmfpx.check_update()
        if has_update:
            reply = QMessageBox.question(
                self.main_window, "Update available",
                "A ROCmFPX update is available.\n"
                "Would you like to install it now?\n\n"
                f"Current commit: {self.rocmfpx._current_commit}\n"
                f"New commit: {self.rocmfpx._remote_commit}",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.rocmfpx.update()
                self.system_tray.showMessage(
                    "ROCmFPX", "Update in progress...",
                    QIcon(str(self._icon_path)), 3000
                )
        else:
            QMessageBox.information(self.main_window, "ROCmFPX",
                                    "ROCmFPX is up to date ✓")

    def _check_rocmfpx_update(self):
        """Vérification silencieuse au démarrage."""
        if self.rocmfpx.is_installed:
            try:
                has_update = self.rocmfpx.check_update()
                if has_update:
                    self.system_tray.showMessage(
                        "ROCmFPX Manager",
                        "🔄 A ROCmFPX update is available.\n"
                        "Open the app to install it.",
                        QIcon(str(self._icon_path)), 5000
                    )
            except Exception:
                pass

    def show_window(self):
        self.main_window.show_window()
