"""Onglet ROCmFPX : installation, compilation et mises à jour (multi-profils)."""

import os
import shutil
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QPlainTextEdit, QProgressBar, QMessageBox, QGridLayout,
    QComboBox
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont

from src.core.rocmfpx_manager import ROCmFPXManager
from src.utils.config import Config
from src.utils.i18n import _


class ROCmFPXTab(QWidget):
    """Installation, compilation et mise à jour de ROCmFPX (multi-profils)."""

    # Signal thread-safe pour les événements provenant des threads de build
    _event_signal = Signal(str, object)

    def __init__(self, rocmfpx: ROCmFPXManager, config: Config):
        super().__init__()
        self.rocmfpx = rocmfpx
        self.config = config
        self._build_in_progress = False
        self._setup_ui()
        self._refresh_status()
        # Connecter le signal thread-safe au slot UI
        self._event_signal.connect(self._on_rocmfpx_event_ui)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # === Sélecteur de profil ===
        profile_group = QGroupBox("🔄 " + _("rocmfpx_profile"))
        profile_layout = QHBoxLayout(profile_group)
        profile_layout.setSpacing(10)

        profile_label = QLabel(_("rocmfpx_profile_select") + ":")
        profile_layout.addWidget(profile_label)

        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(320)
        self.profile_combo.setMinimumHeight(34)
        self._populate_profiles()
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        profile_layout.addWidget(self.profile_combo)

        profile_layout.addStretch()
        layout.addWidget(profile_group)

        # === Statut ===
        status_group = QGroupBox("📡 " + _("rocmfpx_status"))
        status_grid = QGridLayout(status_group)
        status_grid.setSpacing(8)

        self.status_icon = QLabel("⬜")
        self.status_icon.setStyleSheet("font-size: 24px;")
        status_grid.addWidget(self.status_icon, 0, 0)

        self.status_text = QLabel("Detecting...")
        self.status_text.setStyleSheet("font-size: 14px; font-weight: bold;")
        status_grid.addWidget(self.status_text, 0, 1)

        status_grid.addWidget(QLabel("Path:"), 1, 0)
        self.path_label = QLabel(str(self.rocmfpx.base_path))
        self.path_label.setStyleSheet("font-family: monospace;")
        status_grid.addWidget(self.path_label, 1, 1)

        status_grid.addWidget(QLabel("Version (commit):"), 2, 0)
        self.commit_label = QLabel("—")
        self.commit_label.setStyleSheet("font-family: monospace;")
        status_grid.addWidget(self.commit_label, 2, 1)

        status_grid.addWidget(QLabel("llama-server:"), 3, 0)
        self.bin_status = QLabel("—")
        status_grid.addWidget(self.bin_status, 3, 1)

        layout.addWidget(status_group)

        # === Actions ===
        action_group = QGroupBox("🔧 " + _("rocmfpx"))
        action_layout = QHBoxLayout(action_group)
        action_layout.setSpacing(12)

        self.clone_btn = QPushButton("📥 1. " + _("rocmfpx_clone"))
        self.clone_btn.setMinimumHeight(44)
        self.clone_btn.setMinimumWidth(180)
        self.clone_btn.clicked.connect(self._clone)
        action_layout.addWidget(self.clone_btn)

        self.build_btn = QPushButton("🔨 2. " + _("rocmfpx_compile"))
        self.build_btn.setMinimumHeight(44)
        self.build_btn.setMinimumWidth(200)
        self.build_btn.setEnabled(False)
        self.build_btn.clicked.connect(self._build)
        action_layout.addWidget(self.build_btn)

        self.update_btn = QPushButton("🔄 " + _("rocmfpx_check_updates"))
        self.update_btn.setMinimumHeight(44)
        self.update_btn.setMinimumWidth(200)
        self.update_btn.setEnabled(False)
        self.update_btn.clicked.connect(self._check_update)
        action_layout.addWidget(self.update_btn)

        self.changelog_btn = QPushButton("📜 " + _("rocmfpx_changelog"))
        self.changelog_btn.setMinimumHeight(44)
        self.changelog_btn.setEnabled(False)
        self.changelog_btn.clicked.connect(self._show_changelog)
        action_layout.addWidget(self.changelog_btn)

        self.delete_build_btn = QPushButton("🗑️ " + _("rocmfpx_delete_build"))
        self.delete_build_btn.setMinimumHeight(44)
        self.delete_build_btn.setMinimumWidth(180)
        self.delete_build_btn.setEnabled(False)
        self.delete_build_btn.setStyleSheet("color: #ea4335;")
        self.delete_build_btn.clicked.connect(self._delete_build)
        action_layout.addWidget(self.delete_build_btn)

        layout.addWidget(action_group)

        # === Progression ===
        progress_group = QGroupBox("⏳ Progress")
        progress_layout = QVBoxLayout(progress_group)
        progress_layout.setSpacing(4)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMinimumHeight(24)
        progress_layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        progress_layout.addWidget(self.progress_label)

        layout.addWidget(progress_group)

        # === Logs de compilation ===
        log_group = QGroupBox("📋 " + _("rocmfpx_build_logs"))
        log_layout = QVBoxLayout(log_group)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFont(QFont("monospace", 9))
        self.log_output.document().setMaximumBlockCount(500)
        self.log_output.setPlaceholderText("Build logs will appear here...")
        log_layout.addWidget(self.log_output)

        btn_layout = QHBoxLayout()
        self.clear_log_btn = QPushButton("🗑️ Clear")
        self.clear_log_btn.clicked.connect(self.log_output.clear)
        btn_layout.addWidget(self.clear_log_btn)
        btn_layout.addStretch()
        log_layout.addLayout(btn_layout)

        layout.addWidget(log_group, 1)

    def _populate_profiles(self):
        """Remplit le sélecteur de profils."""
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        active = self.rocmfpx.active_profile
        for pid, info in self.rocmfpx.profiles.items():
            label = info.get("label", pid)
            self.profile_combo.addItem(label, pid)
            if pid == active:
                self.profile_combo.setCurrentIndex(self.profile_combo.count() - 1)
        self.profile_combo.blockSignals(False)

    def _on_profile_changed(self, index: int):
        """Callback quand l'utilisateur change de profil dans le sélecteur."""
        if index < 0:
            return
        new_profile = self.profile_combo.itemData(index)
        if new_profile == self.rocmfpx.active_profile:
            return

        # Empêcher le changement pendant un build
        if self._build_in_progress:
            self.profile_combo.blockSignals(True)
            # Re-sélectionner l'ancien profil
            for i in range(self.profile_combo.count()):
                if self.profile_combo.itemData(i) == self.rocmfpx.active_profile:
                    self.profile_combo.setCurrentIndex(i)
                    break
            self.profile_combo.blockSignals(False)
            QMessageBox.warning(
                self, _("rocmfpx"), 
                "Cannot switch profile during a build operation.\nPlease wait for the current build to finish."
            )
            return

        self.rocmfpx.set_active_profile(new_profile)
        self._refresh_status()

    def _refresh_status(self):
        """Met à jour l'affichage du statut pour le profil actif."""
        installed = self.rocmfpx.is_installed
        built = self.rocmfpx.llama_server_path is not None
        profile = self.rocmfpx.get_profile()
        build_dir_name = profile.get("build_dir", "build-strix-rocmfp4")
        build_dir_exists = (self.rocmfpx.base_path / build_dir_name).exists()

        # Mettre à jour le sélecteur (au cas où)
        for i in range(self.profile_combo.count()):
            if self.profile_combo.itemData(i) == self.rocmfpx.active_profile:
                self.profile_combo.setCurrentIndex(i)
                break

        if installed and built:
            self.status_icon.setText("✅")
            self.status_text.setText(_("rocmfpx_ready") + " ✓")
            self.status_text.setStyleSheet("font-size: 14px; font-weight: bold; color: #34a853;")
            self.clone_btn.setEnabled(False)
            self.clone_btn.setText("📥 " + _("rocmfpx_clone") + " ✓")
            self.build_btn.setEnabled(False)
            self.build_btn.setText("🔨 " + _("rocmfpx_compile") + " ✓")
            self.update_btn.setEnabled(True)
            self.changelog_btn.setEnabled(True)
            self.delete_build_btn.setEnabled(True)
            self.bin_status.setText("✅ " + _("ready"))
            self.bin_status.setStyleSheet("color: #34a853;")
        elif installed and not built:
            self.status_icon.setText("⚠️")
            self.status_text.setText(_("rocmfpx_cloned_only"))
            self.status_text.setStyleSheet("font-size: 14px; font-weight: bold; color: #fbbc04;")
            self.clone_btn.setEnabled(False)
            self.clone_btn.setText("📥 " + _("rocmfpx_clone") + " ✓")
            self.build_btn.setEnabled(True)
            self.build_btn.setText("🔨 2. " + _("rocmfpx_compile"))
            self.update_btn.setEnabled(True)
            self.changelog_btn.setEnabled(True)
            self.delete_build_btn.setEnabled(build_dir_exists)
            self.bin_status.setText("❌ Not compiled")
            self.bin_status.setStyleSheet("color: #ea4335;")
        else:
            self.status_icon.setText("⬜")
            self.status_text.setText(_("rocmfpx_not_installed"))
            self.status_text.setStyleSheet("font-size: 14px; font-weight: bold; color: #ea4335;")
            self.clone_btn.setEnabled(True)
            self.clone_btn.setText("📥 1. " + _("rocmfpx_clone"))
            self.build_btn.setEnabled(False)
            self.build_btn.setText("🔨 2. " + _("rocmfpx_compile"))
            self.update_btn.setEnabled(False)
            self.changelog_btn.setEnabled(False)
            self.delete_build_btn.setEnabled(False)
            self.bin_status.setText("—")

        # Chemin
        self.path_label.setText(str(self.rocmfpx.base_path))

        # Commit
        if installed:
            try:
                import subprocess
                result = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=self.rocmfpx.base_path, capture_output=True, text=True, check=True
                )
                self.commit_label.setText(result.stdout.strip())
            except Exception:
                self.commit_label.setText("—")
        else:
            self.commit_label.setText("—")

        # Sauvegarder le chemin dans la config
        if installed:
            self.config.set("rocmfpx_path", str(self.rocmfpx.base_path))
            self.config.save()

    def _clone(self):
        """Clone le dépôt ROCmFPX pour le profil actif."""
        self.clone_btn.setEnabled(False)
        self.clone_btn.setText("⏳ " + _("clone_in_progress"))
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Mode indéterminé
        self.progress_label.setVisible(True)
        profile = self.rocmfpx.get_profile()
        self.progress_label.setText("📥 Cloning " + profile.get("repo_url", "") + "...")
        self.log_output.appendPlainText("▶️ Cloning repository (" + self.rocmfpx.label + ")...")

        self.rocmfpx.add_listener(self._on_rocmfpx_event_threadsafe)
        self.rocmfpx.clone()

    def _build(self):
        """Lance la compilation."""
        self._build_in_progress = True
        self.profile_combo.setEnabled(False)
        self.build_btn.setEnabled(False)
        self.build_btn.setText("🔨 " + _("build_in_progress"))
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Mode indéterminé
        self.progress_label.setVisible(True)
        self.progress_label.setText("🔨 " + _("rocmfpx_compiling"))
        self.log_output.appendPlainText("▶️ Starting build for " + self.rocmfpx.label + "...")
        self.log_output.appendPlainText("ℹ️  This may take several minutes.")
        self.log_output.appendPlainText("   Profile: " + self.rocmfpx.active_profile)
        self.log_output.appendPlainText("   Build dir: " + str(self.rocmfpx.base_path / self.rocmfpx.get_profile().get("build_dir", "")))

        self.rocmfpx.add_listener(self._on_rocmfpx_event_threadsafe)
        self.rocmfpx.build()

    def _on_rocmfpx_event_threadsafe(self, event: str, data):
        """Callback appelé depuis un thread secondaire → émet le signal Qt."""
        self._event_signal.emit(event, data)

    def _on_rocmfpx_event_ui(self, event: str, data):
        """Gère les événements du ROCmFPXManager (exécuté sur le thread principal)."""
        if event == "clone_start":
            self.log_output.appendPlainText("📦 Cloning started...")
        elif event == "clone_done":
            self.log_output.appendPlainText(f"✅ " + _("clone_done") + f" (commit: {data.get('commit', '?')})")
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setVisible(False)
            self.progress_label.setVisible(False)
            self.clone_btn.setText("📥 " + _("rocmfpx_clone") + " ✓")
            self.build_btn.setEnabled(True)
            self._refresh_status()
        elif event == "build_start":
            self.log_output.appendPlainText("🔨 Build started...")
        elif event == "build_log":
            line = data if isinstance(data, str) else str(data)
            self.log_output.appendPlainText(line)
            # Scroller vers le bas
            scrollbar = self.log_output.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        elif event == "build_done":
            self.log_output.appendPlainText("✅ " + _("build_done"))
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.progress_label.setText("✅ Build complete!")
            self._build_in_progress = False
            self.profile_combo.setEnabled(True)
            self.build_btn.setText("🔨 " + _("rocmfpx_compile") + " ✓")
            self._refresh_status()
            QMessageBox.information(
                self, "ROCmFPX",
                "✅ " + _("build_done") + "\n\n"
                "You can now start a model from the Server tab."
            )
        elif event == "update_start":
            self.log_output.appendPlainText("🔄 Update started...")
        elif event == "update_pulled":
            self.log_output.appendPlainText(
                f"🔄 Pull done: {data.get('old', '?')} → {data.get('new', '?')}"
            )
        elif event == "error":
            msg = data.get("message", "Unknown error") if isinstance(data, dict) else str(data)
            self.log_output.appendPlainText(f"❌ Error: {msg}")
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setVisible(False)
            self.progress_label.setVisible(False)
            self._build_in_progress = False
            self.profile_combo.setEnabled(True)
            self.clone_btn.setEnabled(True)
            self.clone_btn.setText("📥 1. " + _("rocmfpx_clone"))
            self.build_btn.setEnabled(self.rocmfpx.is_installed)
            if self.rocmfpx.is_installed:
                self.build_btn.setText("🔨 2. " + _("rocmfpx_compile"))
            self._refresh_status()
            QMessageBox.critical(self, "ROCmFPX Error", msg)

    def _delete_build(self):
        """Supprime le dossier de build pour permettre une recompilation propre."""
        profile = self.rocmfpx.get_profile()
        build_dir_name = profile.get("build_dir", "build-strix-rocmfp4")
        build_dir = self.rocmfpx.base_path / build_dir_name
        if not build_dir.exists():
            QMessageBox.information(self, "Build", "Aucun build à supprimer.")
            return

        reply = QMessageBox.question(
            self, _("rocmfpx_delete_build"),
            "⚠️  This will delete the " + build_dir_name + "/ folder\n"
            "and you will need to recompile entirely.\n\n"
            "Binaries (llama-server, etc.) will not be available\n"
            "until compilation is run again.\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            shutil.rmtree(build_dir, ignore_errors=True)
            self.log_output.appendPlainText("🗑️ " + _("rocmfpx_build_deleted"))
            self._refresh_status()

    def _check_update(self):
        """Vérifie et propose les mises à jour."""
        # S'assurer que le listener est bien enregistré pour recevoir les events
        self.rocmfpx.add_listener(self._on_rocmfpx_event_threadsafe)

        has_update = self.rocmfpx.check_update()
        if has_update:
            current = self.rocmfpx._current_commit or "?"
            remote = self.rocmfpx._remote_commit or "?"
            msg = _("update_available") + "\n"
            if current != "?":
                msg += f"Current: {current}\n"
            if remote != "?":
                msg += f"Available: {remote}\n\n"
            msg += "Update now?"
            reply = QMessageBox.question(
                self, "Update available",
                msg,
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._build_in_progress = True
                self.profile_combo.setEnabled(False)
                self.progress_bar.setVisible(True)
                self.progress_bar.setRange(0, 0)
                self.progress_label.setVisible(True)
                self.progress_label.setText("🔄 Mise à jour en cours...")
                self.log_output.appendPlainText("🔄 Mise à jour en cours...")
                self.rocmfpx.update()
        else:
            QMessageBox.information(self, "ROCmFPX", _("up_to_date") + " ✓")

    def _show_changelog(self):
        """Affiche les derniers commits."""
        log = self.rocmfpx.get_changelog()
        if log:
            QMessageBox.information(
                self, "Recent ROCmFPX commits",
                f"Recent commits:\n\n{log}"
            )
        else:
            QMessageBox.information(self, "ROCmFPX", "Could not fetch changelog.")
