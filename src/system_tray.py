"""Icône et menu de la barre système."""

from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QMessageBox
from PySide6.QtGui import QIcon, QAction, QPixmap
from PySide6.QtCore import QCoreApplication
from pathlib import Path


class SystemTray(QSystemTrayIcon):
    """Icône systray avec menu contextuel."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Icône (priorité PNG, fallback SVG)
        self._icon_path = ""
        if parent and hasattr(parent, '_icon_path'):
            self._icon_path = str(parent._icon_path)
        elif parent and hasattr(parent, 'main_window'):
            self._icon_path = str(parent.main_window._get_icon_path())

        if self._icon_path:
            # Préférer le PNG si dispo
            png_path = str(Path(self._icon_path).with_suffix('.png'))
            icon_path = png_path if Path(png_path).exists() else self._icon_path
            self.setIcon(QIcon(icon_path))
        else:
            pixmap = QPixmap(64, 64)
            pixmap.fill()
            self.setIcon(QIcon(pixmap))

        self.setToolTip("ROCmFP4 Manager")

        # Menu
        self.menu = QMenu()
        self._build_menu()
        self.setContextMenu(self.menu)

        self.activated.connect(self._on_activated)

    def _build_menu(self):
        self.menu.clear()

        # Statut (non cliquable)
        status_action = self.menu.addAction("● Starting...")
        status_action.setEnabled(False)
        self._status_action = status_action

        port_action = self.menu.addAction("Port: —")
        port_action.setEnabled(False)
        self._port_action = port_action

        self.menu.addSeparator()

        # Actions
        self._action_open_chat = self.menu.addAction("🌐 Open Chat")
        self._action_copy_api = self.menu.addAction("📋 Copy API URL")
        self._action_logs = self.menu.addAction("📄 View Logs")

        self.menu.addSeparator()

        self._action_bench = self.menu.addAction("🏋️ Run Benchmark")

        self.menu.addSeparator()

        self._action_stop = self.menu.addAction("⏹ Stop")
        self._action_restart = self.menu.addAction("🔄 Restart")

        self.menu.addSeparator()

        self._action_config = self.menu.addAction("⚙ Configure")

        self._action_autostart = QAction("🚀 Auto-start")
        self._action_autostart.setCheckable(True)
        self.menu.addAction(self._action_autostart)

        self._action_update = self.menu.addAction("🔄 Update ROCmFPX...")

        self.menu.addSeparator()

        self._action_quit = self.menu.addAction("❌ Quit")

    def update_status(self, status: str, port: int = 1412, model: str = ""):
        """Met à jour les infos dans le menu."""
        self._status_action.setText(f"● {status}")
        self._port_action.setText(f"Port: {port}")

        tooltip = f"ROCmFP4 Manager — {status}"
        if model:
            tooltip += f" | {model}"
        self.setToolTip(tooltip)

    def set_autostart_checked(self, checked: bool):
        self._action_autostart.setChecked(checked)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            parent = self.parent()
            if parent and hasattr(parent, 'show_window'):
                parent.show_window()

    # Propriétés pour connecter les signaux
    @property
    def action_open_chat(self):
        return self._action_open_chat

    @property
    def action_copy_api(self):
        return self._action_copy_api

    @property
    def action_logs(self):
        return self._action_logs

    @property
    def action_bench(self):
        return self._action_bench

    @property
    def action_stop(self):
        return self._action_stop

    @property
    def action_restart(self):
        return self._action_restart

    @property
    def action_config(self):
        return self._action_config

    @property
    def action_autostart(self):
        return self._action_autostart

    @property
    def action_update(self):
        return self._action_update

    @property
    def action_quit(self):
        return self._action_quit
