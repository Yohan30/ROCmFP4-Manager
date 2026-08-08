"""Onglet Modèles : liste, téléchargement, import LM Studio."""

import time
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QProgressBar, QLineEdit, QComboBox, QMessageBox,
    QFileDialog, QCheckBox
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor

from src.core.model_manager import ModelManager
from src.utils.config import Config


class ModelsTab(QWidget):
    """Gestion des modèles GGUF."""

    # Signal thread-safe pour les téléchargements
    _dl_signal = Signal(str, object)
    # Signal émis quand un modèle est sélectionné (chemin du .gguf)
    model_selected = Signal(str)

    def __init__(self, models_mgr: ModelManager, config: Config):
        super().__init__()
        self.models_mgr = models_mgr
        self.config = config
        self._lmstudio_models = []
        self._setup_ui()
        self._connect_signals()
        self._refresh()
        self._dl_signal.connect(self._on_model_event_ui)

        # File de téléchargement séquentiel
        self._download_queue: list[tuple[str, str, str]] = []  # (repo_id, filename, subdir)
        self._downloading = False

        # Timer refresh (ralenti pour éviter le scintillement)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(5000)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # === Barre de recherche HF ===
        search_group = QGroupBox("🔍 Search on HuggingFace")
        search_layout = QVBoxLayout(search_group)
        search_layout.setSpacing(6)

        # Barre de recherche
        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("e.g. Qwen3.5, ROCmFP4, DeepSeek...")
        search_row.addWidget(self.search_input, 1)

        self.search_btn = QPushButton("🔍 Search")
        search_row.addWidget(self.search_btn)

        self.download_btn = QPushButton("⬇️ Download")
        self.download_btn.setEnabled(False)
        search_row.addWidget(self.download_btn)
        search_layout.addLayout(search_row)

        # Filtres rapides (presets)
        presets_row = QHBoxLayout()
        presets_row.setSpacing(6)
        presets_row.addWidget(QLabel("Quick:"))
        for label, query in [
            ("🔴 ROCmFP4", "ROCmFP4"),
            ("🔶 NVFP4", "NVFP4"),
            ("🤖 Qwen", "Qwen"),
            ("🧠 DeepSeek", "DeepSeek"),
            ("📚 LLama", "Llama"),
            ("⭐ Popular", "GGUF"),
        ]:
            btn = QPushButton(label)
            btn.setStyleSheet("font-size: 11px; padding: 4px 10px;")
            btn.clicked.connect(lambda checked, q=query: self._quick_search(q))
            presets_row.addWidget(btn)
        presets_row.addStretch()
        search_layout.addLayout(presets_row)

        layout.addWidget(search_group)

        # === Modèles installés + LM Studio (fusionnés) ===
        models_group = QGroupBox("📦 Models")
        models_layout = QVBoxLayout(models_group)

        self.models_table = QTableWidget(0, 7)
        self.models_table.setHorizontalHeaderLabels(["Model", "File", "Size", "Type", "Source", "HF Page", "Actions"])
        self.models_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.models_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.models_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.models_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.models_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.models_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.models_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.models_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.models_table.setSelectionMode(QTableWidget.SingleSelection)
        self.models_table.verticalHeader().setVisible(False)
        self.models_table.verticalHeader().setDefaultSectionSize(38)
        models_layout.addWidget(self.models_table)

        # Boutons modèles + LM Studio
        btn_layout = QHBoxLayout()
        self.open_folder_btn = QPushButton("📂 Open folder")
        btn_layout.addWidget(self.open_folder_btn)

        self.delete_btn = QPushButton("🗑️ Delete")
        self.delete_btn.setEnabled(False)
        btn_layout.addWidget(self.delete_btn)

        self.refresh_btn = QPushButton("🔄 Refresh")
        btn_layout.addWidget(self.refresh_btn)

        btn_layout.addStretch()

        self.scan_lmstudio_btn = QPushButton("🔍 Scan LM Studio")
        self.scan_lmstudio_btn.setStyleSheet("font-size: 11px; padding: 4px 10px;")
        btn_layout.addWidget(self.scan_lmstudio_btn)

        self.use_symlink_check = QCheckBox("Symlink")
        self.use_symlink_check.setChecked(True)
        self.use_symlink_check.setToolTip("Use symbolic link to save disk space")
        btn_layout.addWidget(self.use_symlink_check)

        self.import_all_lmstudio_btn = QPushButton("📥 Import all LM Studio")
        self.import_all_lmstudio_btn.setStyleSheet("font-size: 11px; padding: 4px 10px;")
        self.import_all_lmstudio_btn.setVisible(False)
        btn_layout.addWidget(self.import_all_lmstudio_btn)

        space = self.models_mgr.get_available_disk_space()
        self.disk_space_label = QLabel(f"💾 Free space: {space}")
        btn_layout.addWidget(self.disk_space_label)

        models_layout.addLayout(btn_layout)
        layout.addWidget(models_group, 1)

        # === Progression ===
        progress_group = QGroupBox("⏳ Downloads")
        progress_layout = QVBoxLayout(progress_group)
        progress_layout.setSpacing(6)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMinimumHeight(24)
        progress_layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        self.progress_label.setStyleSheet("font-size: 12px;")
        progress_layout.addWidget(self.progress_label)

        # Boutons pause/resume/cancel
        dl_btn_layout = QHBoxLayout()
        dl_btn_layout.setSpacing(6)

        self.pause_btn = QPushButton("⏸ Pause")
        self.pause_btn.setVisible(False)
        self.pause_btn.clicked.connect(self._pause_download)
        dl_btn_layout.addWidget(self.pause_btn)

        self.resume_btn = QPushButton("▶️ Resume")
        self.resume_btn.setVisible(False)
        self.resume_btn.clicked.connect(self._resume_download)
        dl_btn_layout.addWidget(self.resume_btn)

        self.cancel_btn = QPushButton("⏹ Cancel")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.setStyleSheet("color: #ea4335;")
        self.cancel_btn.clicked.connect(self._cancel_download)
        dl_btn_layout.addWidget(self.cancel_btn)

        dl_btn_layout.addStretch()
        progress_layout.addLayout(dl_btn_layout)

        layout.addWidget(progress_group)

    def _connect_signals(self):
        self.search_btn.clicked.connect(self._search_hf)
        self.search_input.returnPressed.connect(self._search_hf)
        self.download_btn.clicked.connect(self._download_selected)
        self.models_table.itemSelectionChanged.connect(self._on_model_selected)
        self.delete_btn.clicked.connect(self._delete_model)
        self.refresh_btn.clicked.connect(self._refresh)
        self.open_folder_btn.clicked.connect(self._open_models_folder)
        self.scan_lmstudio_btn.clicked.connect(self._scan_lmstudio)
        self.import_all_lmstudio_btn.clicked.connect(self._import_all_lmstudio)
        self.models_mgr.add_listener(self._on_model_event_threadsafe)

    # ID de la tâche de téléchargement en cours
    _current_dl_task_id: int = 0
    _dl_last_time: float = 0.0
    _dl_last_bytes: int = 0

    def _on_model_event_threadsafe(self, event: str, data):
        self._dl_signal.emit(event, data)

    def _on_model_event_ui(self, event: str, data):
        if event == "download_start":
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.progress_label.setVisible(True)
            self.pause_btn.setVisible(True)
            self.resume_btn.setVisible(False)
            self.cancel_btn.setVisible(True)
            self._current_dl_task_id = data.get("task", 0)
            self._dl_last_time = time.time()
            self._dl_last_bytes = 0
            self.progress_label.setText(f"⬇️ {data.get('name', '')} — 0%")
            # Pas de _refresh() ici → évite le scintillement
        elif event == "download_progress":
            pct = data.get("percent", 0)
            downloaded = data.get("downloaded", 0)
            total = data.get("total", 0)
            self.progress_bar.setValue(int(pct))
            self.progress_label.setVisible(True)

            def fmt(s):
                if s >= 1024**3:
                    return f"{s/(1024**3):.1f} GB"
                return f"{s/(1024**2):.0f} MB"

            # Vitesse et ETA
            now = time.time()
            elapsed = now - self._dl_last_time
            self._dl_last_time = now
            delta_bytes = downloaded - self._dl_last_bytes
            self._dl_last_bytes = downloaded

            speed_str = ""
            eta_str = ""
            if elapsed > 0.1 and delta_bytes > 0 and total > 0:
                speed_bps = delta_bytes / elapsed
                if speed_bps >= 1024**3:
                    speed_str = f"{speed_bps/(1024**3):.1f} GB/s"
                elif speed_bps >= 1024**2:
                    speed_str = f"{speed_bps/(1024**2):.1f} MB/s"
                else:
                    speed_str = f"{speed_bps/1024:.0f} KB/s"
                remaining = total - downloaded
                if remaining > 0:
                    eta_secs = remaining / speed_bps
                    if eta_secs > 3600:
                        eta_str = f"{eta_secs/3600:.1f}h"
                    elif eta_secs > 60:
                        eta_str = f"{eta_secs/60:.0f}m"
                    else:
                        eta_str = f"{eta_secs:.0f}s"

            dl_str = fmt(downloaded) if downloaded else "?"
            total_str = fmt(total) if total else "?"
            info_parts = [f"⬇️ {data.get('name', '')}"]
            info_parts.append(f"{pct:.0f}% ({dl_str}/{total_str})")
            if speed_str:
                info_parts.append(f"⚡ {speed_str}")
            if eta_str:
                info_parts.append(f"⏱ {eta_str}")
            self.progress_label.setText(" — ".join(info_parts))
        elif event == "download_paused":
            self.pause_btn.setVisible(False)
            self.resume_btn.setVisible(True)
            self.progress_label.setText(f"⏸ PAUSED — {data.get('name', '')}")
        elif event == "download_resumed":
            self.pause_btn.setVisible(True)
            self.resume_btn.setVisible(False)
        elif event == "download_cancelled":
            if self._download_queue:
                self._download_queue.pop(0)
            self._process_download_queue()
            self._refresh()
        elif event == "download_done":
            if self._download_queue:
                self._download_queue.pop(0)
            more = bool(self._download_queue)
            if more:
                # Ne pas montrer de message, lancer le suivant
                self._process_download_queue()
            else:
                self.progress_bar.setVisible(False)
                self.pause_btn.setVisible(False)
                self.resume_btn.setVisible(False)
                self.cancel_btn.setVisible(False)
                self.progress_label.setVisible(False)
                self._refresh()
                QMessageBox.information(self, "Download",
                                        f"✅ {data.get('name', '')} downloaded!")
        elif event == "download_error":
            if self._download_queue:
                self._download_queue.pop(0)
            QMessageBox.warning(self, "Download",
                                f"⚠️ {data.get('error', 'Unknown error')}\n\n"
                                "The download will be skipped.")
            self._process_download_queue()
        elif event == "imported":
            self._scan_lmstudio()  # appelle _refresh() automatiquement
        elif event == "deleted":
            self._refresh()

    def _pause_download(self):
        if self._current_dl_task_id:
            self.models_mgr.pause_download(self._current_dl_task_id)

    def _resume_download(self):
        if self._current_dl_task_id:
            self.models_mgr.resume_download(self._current_dl_task_id)

    def _cancel_download(self):
        if self._current_dl_task_id:
            self.models_mgr.cancel_download(self._current_dl_task_id)
            self.progress_bar.setVisible(False)
            self.pause_btn.setVisible(False)
            self.resume_btn.setVisible(False)
            self.cancel_btn.setVisible(False)
            self.progress_label.setVisible(False)
            self._refresh()

    def _refresh(self):
        models = self.models_mgr.scan_models()
        installed_names = {m["name"] for m in models}

        # Grouper par dossier
        grouped = {}
        for m in models:
            g = m.get("group", "") or "Other"
            if g not in grouped:
                grouped[g] = []
            grouped[g].append(m)

        # Ajouter les modèles LM Studio non encore importés
        if self._lmstudio_models:
            lmstudio_not_imported = [
                m for m in self._lmstudio_models
                if m["name"] not in installed_names
            ]
            if lmstudio_not_imported:
                grouped["📥 LM Studio"] = [
                    {
                        "name": m["name"],
                        "path": m["path"],
                        "size_gb": m["size_gb"],
                        "is_mtp": False,
                        "group": "📥 LM Studio",
                        "source": "lmstudio",
                    }
                    for m in lmstudio_not_imported
                ]

        # Aplatir
        rows = []
        for group_name in sorted(grouped.keys()):
            group_models = grouped[group_name]
            total_size = sum(m["size_gb"] for m in group_models)
            rows.append({
                "is_header": True,
                "group": group_name,
                "total_size": total_size,
                "count": len(group_models),
            })
            for m in group_models:
                is_multi = m.get("is_multi_part", False)
                part_count = m.get("part_count", 1)
                is_mtp = m.get("is_mtp", False)
                is_mmproj = m.get("is_mmproj", False)
                source = m.get("source", "downloaded")

                # Déterminer le type
                if is_mtp:
                    type_label = "MTP"
                elif is_mmproj:
                    type_label = "Vision"
                elif is_multi:
                    type_label = f"Multi ({part_count} parts)"
                else:
                    type_label = "Main"

                # Afficher le nom (pour multi-part, montrer le nom de base)
                display_name = m["name"]

                rows.append({
                    "is_header": False,
                    "name": display_name,
                    "path": m["path"],
                    "size_gb": m["size_gb"],
                    "type_label": type_label,
                    "is_mtp": is_mtp,
                    "is_multi": is_multi,
                    "source": source,
                })

        self.models_table.setRowCount(len(rows))
        last_row = 0
        for idx, r in enumerate(rows):
            last_row = idx
            if r["is_header"]:
                group_item = QTableWidgetItem(f"  {r['group']} ({r['count']} models)")
                group_item.setFlags(group_item.flags() & ~Qt.ItemIsSelectable)
                font = group_item.font()
                font.setBold(True)
                group_item.setFont(font)
                self.models_table.setItem(idx, 0, group_item)
                self.models_table.setItem(idx, 1, QTableWidgetItem(""))
                self.models_table.setItem(idx, 2, QTableWidgetItem(
                    self.models_mgr.get_model_size_str(r["total_size"])
                ))
                for col in range(3, 7):
                    self.models_table.setItem(idx, col, QTableWidgetItem(""))
            else:
                self.models_table.setItem(idx, 0, QTableWidgetItem(""))
                self.models_table.setItem(idx, 1, QTableWidgetItem(r["name"]))
                self.models_table.setItem(idx, 2,
                    QTableWidgetItem(self.models_mgr.get_model_size_str(r["size_gb"])))
                self.models_table.setItem(idx, 3, QTableWidgetItem(r["type_label"]))

                # Source
                is_lmstudio = r.get("source") == "lmstudio"
                source_item = QTableWidgetItem("LM Studio" if is_lmstudio else "HF")
                source_item.setTextAlignment(Qt.AlignCenter)
                self.models_table.setItem(idx, 4, source_item)

                # HF Page
                hf_url = self._guess_hf_url(r)
                if hf_url:
                    hf_btn = QPushButton("Open")
                    hf_btn.setFlat(True)
                    hf_btn.setStyleSheet("QPushButton { border: none; background: transparent; color: #1a73e8; font-size: 12px; padding: 2px 6px; text-decoration: underline; } QPushButton:hover { color: #e94560; }")
                    _url = hf_url
                    hf_btn.clicked.connect(lambda checked, u=_url: self._open_url(u))
                    self.models_table.setCellWidget(idx, 5, hf_btn)
                else:
                    self.models_table.setItem(idx, 5, QTableWidgetItem("—"))

                # Actions
                if is_lmstudio:
                    import_btn = QPushButton("Import")
                    import_btn.setStyleSheet("font-size: 11px; padding: 2px 8px;")
                    _p = r["path"]
                    import_btn.clicked.connect(
                        lambda checked, p=_p: self._import_single(p)
                    )
                    self.models_table.setCellWidget(idx, 6, import_btn)
                else:
                    select_btn = QPushButton("Use")
                    select_btn.setStyleSheet("font-size: 11px; padding: 2px 8px;")
                    _p = r["path"]
                    select_btn.clicked.connect(lambda checked, p=_p: self._select_model(p))
                    self.models_table.setCellWidget(idx, 6, select_btn)

        # Afficher/masquer le bouton "Import all"
        has_lmstudio = any(
            r.get("source") == "lmstudio" for r in rows if not r.get("is_header")
        )
        self.import_all_lmstudio_btn.setVisible(has_lmstudio)
        self.disk_space_label.setText(
            f"💾 Espace libre: {self.models_mgr.get_available_disk_space()}"
        )

    def _on_model_selected(self):
        self.delete_btn.setEnabled(len(self.models_table.selectedItems()) > 0)

    def _select_model(self, path: str):
        self.config.set("last_model", path)
        self.config.save()
        self.model_selected.emit(path)
        QMessageBox.information(self, "Model selected",
                                f"✅ {Path(path).name}\nYou can start the server from the Server tab.")

    def _delete_model(self):
        """Supprime le modèle sélectionné (fonctionne avec les lignes groupées)."""
        row = self.models_table.currentRow()
        if row < 0:
            return
        # Chercher le chemin dans les données de la ligne (colonne cachée ou tooltip)
        # On scanne les modèles et on fait correspondre par position réelle
        models = self.models_mgr.scan_models()
        # Construire une liste plate des lignes "fichier" (sans les en-têtes de groupe)
        flat_files = []
        grouped = {}
        for m in models:
            g = m.get("group", "") or "Other"
            if g not in grouped:
                grouped[g] = []
            grouped[g].append(m)

        group_idx = 0
        for g in sorted(grouped):
            flat_files.append(None)  # en-tête de groupe
            for m in grouped[g]:
                flat_files.append(m)

        if row < len(flat_files) and flat_files[row] is not None:
            m = flat_files[row]
            is_multi = m.get("is_multi_part", False)
            parts = m.get("parts", [])
            extra = parts[1:] if is_multi and len(parts) > 1 else None
            name_label = m['name']
            if is_multi:
                name_label += f" ({len(parts)} parts)"
            reply = QMessageBox.question(
                self, "Confirm",
                f"Delete {name_label}?\nThis action is irreversible.",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.models_mgr.delete_model(m["path"], extra_paths=extra)
                self._refresh()

    def _open_models_folder(self):
        import subprocess
        subprocess.run(["xdg-open", str(self.config.models_path)])

    def _quick_search(self, query: str):
        """Lance une recherche rapide avec un terme prédéfini."""
        self.search_input.setText(query)
        self._search_hf()

    def _search_hf(self):
        query = self.search_input.text().strip()
        if not query:
            return

        self.search_btn.setEnabled(False)
        self.search_btn.setText("🔍 Search...")

        from src.utils.huggingface_api import HuggingFaceAPI
        hf = HuggingFaceAPI()
        results = hf.search_models(query)

        self.search_btn.setEnabled(True)
        self.search_btn.setText("🔍 Search")

        if not results:
            QMessageBox.information(self, "Results", "No models found.")
            return

        # Boîte de dialogue avec tableau stylisé
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, \
            QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QLabel

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Results for '{query}'")
        dialog.setMinimumSize(800, 500)

        dl = QVBoxLayout(dialog)
        dl.setSpacing(8)

        # Pagination : la liste peut être volumineuse (plus de 50 modèles), on
        # affiche PAGE_SIZE lignes à la fois pour ne pas figer l'interface.
        PAGE_SIZE = 500
        total = len(results)
        n_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        page = [0]  # page courante (liste pour mutation depuis les closures)

        # En-tête
        header = QLabel()
        header.setStyleSheet("font-weight: bold; font-size: 14px; padding: 8px;")
        dl.addWidget(header)

        # Tableau
        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(["Model", "Author", "Downloads", "Total Size", "Type", "HF Page"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(True)

        def _update_header():
            if n_pages > 1:
                header.setText(
                    f"🔍 {total} model(s) found — page {page[0] + 1}/{n_pages} — "
                    "double-click to see files"
                )
            else:
                header.setText(f"🔍 {total} model(s) found — double-click to see files")

        def _fill_page(p):
            """Remplit le tableau avec la page `p` des résultats."""
            start = p * PAGE_SIZE
            end = min(start + PAGE_SIZE, total)
            slice_results = results[start:end]
            table.setRowCount(len(slice_results))
            for local_i, r in enumerate(slice_results):
                # Nom
                name = r["name"]
                if r["is_rocmfp4"]:
                    name = "🔴 " + name
                name_item = QTableWidgetItem(name)
                name_item.setToolTip(r["id"])
                table.setItem(local_i, 0, name_item)

                # Auteur
                table.setItem(local_i, 1, QTableWidgetItem(r["author"]))

                # Téléchargements (formaté)
                dl_count = r["downloads"]
                if dl_count >= 1000000:
                    dl_str = f"⬇️ {dl_count/1000000:.1f}M"
                elif dl_count >= 1000:
                    dl_str = f"⬇️ {dl_count/1000:.0f}K"
                else:
                    dl_str = f"⬇️ {dl_count}"
                dl_item = QTableWidgetItem(dl_str)
                dl_item.setTextAlignment(Qt.AlignCenter)
                table.setItem(local_i, 2, dl_item)

                # Taille totale
                total_size = r.get("total_size", 0)
                if total_size > 0:
                    if total_size >= 1024**3:
                        size_str = f"{total_size/(1024**3):.1f} GB"
                    elif total_size >= 1024**2:
                        size_str = f"{total_size/(1024**2):.1f} MB"
                    else:
                        size_str = "—"
                else:
                    size_str = "—"
                size_item = QTableWidgetItem(size_str)
                size_item.setTextAlignment(Qt.AlignCenter)
                table.setItem(local_i, 3, size_item)

                # Type
                type_text = "ROCmFP4" if r["is_rocmfp4"] else "GGUF"
                type_item = QTableWidgetItem(type_text)
                type_item.setTextAlignment(Qt.AlignCenter)
                if r["is_rocmfp4"]:
                    type_item.setForeground(QColor("#ff4d00"))
                table.setItem(local_i, 4, type_item)

                # Bouton lien HF
                if r.get("id"):
                    hf_btn = QPushButton("Open")
                    hf_btn.setFlat(True)
                    hf_btn.setStyleSheet("QPushButton { border: none; background: transparent; color: #1a73e8; font-size: 12px; padding: 2px 6px; text-decoration: underline; } QPushButton:hover { color: #e94560; }")
                    _hf_id = r["id"]
                    hf_btn.clicked.connect(lambda checked, hf_id=_hf_id: self._open_hf_page(hf_id))
                    table.setCellWidget(local_i, 5, hf_btn)
                else:
                    table.setItem(local_i, 5, QTableWidgetItem("—"))

        dl.addWidget(table)

        # Double-clic sur une ligne → ouvre les fichiers
        table.cellDoubleClicked.connect(dialog.accept)

        # Navigation de page (affichée uniquement si plusieurs pages)
        if n_pages > 1:
            page_nav = QHBoxLayout()
            page_nav.addStretch()
            prev_btn = QPushButton("◀ Prev")
            next_btn = QPushButton("Next ▶")
            page_label = QLabel()
            page_label.setStyleSheet("color: #888; min-width: 60px;")
            page_nav.addWidget(prev_btn)
            page_nav.addWidget(page_label)
            page_nav.addWidget(next_btn)
            page_nav.addStretch()
            dl.addLayout(page_nav)

            def _update_page_buttons():
                prev_btn.setEnabled(page[0] > 0)
                next_btn.setEnabled(page[0] < n_pages - 1)
                page_label.setText(f"{page[0] + 1} / {n_pages}")

            def _go(p):
                page[0] = max(0, min(p, n_pages - 1))
                _fill_page(page[0])
                _update_header()
                _update_page_buttons()

            prev_btn.clicked.connect(lambda: _go(page[0] - 1))
            next_btn.clicked.connect(lambda: _go(page[0] + 1))
            _update_page_buttons()

        # Remplir la première page
        _fill_page(0)
        _update_header()

        # Boutons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("✅ Select & show files")
        ok_btn.setMinimumHeight(36)
        ok_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(ok_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumHeight(36)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)

        dl.addLayout(btn_layout)

        if dialog.exec() == QDialog.Accepted:
            row = table.currentRow()
            if row >= 0:
                global_row = page[0] * PAGE_SIZE + row
                if global_row < total:
                    selected = results[global_row]
                    self._show_model_files(selected["id"])

    def _show_model_files(self, repo_id: str):
        from src.utils.huggingface_api import HuggingFaceAPI
        hf = HuggingFaceAPI()
        files = hf.list_gguf_files(repo_id)

        if not files:
            QMessageBox.information(self, "Files",
                                    f"No GGUF files found in {repo_id}")
            return

        # Boîte de dialogue stylisée pour les fichiers
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, \
            QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QLabel, QFrame
        from PySide6.QtGui import QColor, QFont
        from PySide6.QtCore import Qt
        import re

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Files in {repo_id}")
        dialog.setMinimumSize(750, 450)

        dl = QVBoxLayout(dialog)
        dl.setSpacing(8)

        repo_label = QLabel(f"📦 {repo_id}")
        repo_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 8px;")
        dl.addWidget(repo_label)

        hint = QLabel("💡 Click to select, click again to deselect — select multiple files at once")
        hint.setStyleSheet("font-size: 11px; color: #888; padding: 0 8px;")
        dl.addWidget(hint)

        # Sélection par clic toggle (pas de Ctrl+click nécessaire)
        selected_rows: set[int] = set()
        accent = self.config.get("accent_color", "#5555ff")

        def _toggle_row(row: int, _col: int):
            if row in selected_rows:
                selected_rows.discard(row)
                for col in range(table.columnCount()):
                    item = table.item(row, col)
                    if item:
                        item.setBackground(QColor("transparent"))
            else:
                selected_rows.add(row)
                for col in range(table.columnCount()):
                    item = table.item(row, col)
                    if item:
                        item.setBackground(QColor(accent))

        table = QTableWidget(len(files), 4)
        table.setHorizontalHeaderLabels(["Filename", "Size", "Quantization", ""])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.verticalHeader().setVisible(False)
        table.cellClicked.connect(_toggle_row)

        # Patterns de quantization courants
        quant_patterns = [
            (r"Q4_0_ROCMFP4_FAST", "ROCmFP4 FAST"),
            (r"Q4_0_ROCMFP4_STRIX_LEAN", "ROCmFP4 STRIX_LEAN"),
            (r"Q4_0_ROCMFP4_COHERENT", "ROCmFP4 COHERENT"),
            (r"Q4_0_ROCMFP4", "ROCmFP4"),
            (r"MTP", "MTP"),
            (r"Q4_K_M", "Q4_K_M"),
            (r"Q6_K", "Q6_K"),
            (r"Q8_0", "Q8_0"),
            (r"Q4_0", "Q4_0"),
            (r"Q5_K_M", "Q5_K_M"),
            (r"NVFP4", "NVFP4"),
            (r"BF16", "BF16"),
            (r"F16", "F16"),
        ]

        total_size = 0

        for i, f in enumerate(files):
            fname_item = QTableWidgetItem(f["filename"])
            fname_item.setToolTip(f["filename"])
            font = fname_item.font()
            font.setBold(True)
            fname_item.setFont(font)
            table.setItem(i, 0, fname_item)

            # Taille réelle depuis l'API
            size = f.get("size", 0)
            if size > 0:
                total_size += size
                if size >= 1024**3:
                    size_str = f"{size/(1024**3):.1f} GB"
                elif size >= 1024**2:
                    size_str = f"{size/(1024**2):.1f} MB"
                else:
                    size_str = f"{size/1024:.0f} KB"
            else:
                # Fallback: extraire du nom
                size_str = ""
                match = re.search(r'(\d+(?:\.\d+)?)\s*(GB|MB|GiB|MiB)', f["filename"], re.IGNORECASE)
                if match:
                    size_str = match.group(0)
            table.setItem(i, 1, QTableWidgetItem(size_str))

            # Quantization
            quant = "Unknown"
            for pattern, label in quant_patterns:
                if re.search(pattern, f["filename"], re.IGNORECASE):
                    quant = label
                    break
            quant_item = QTableWidgetItem(quant)
            quant_item.setTextAlignment(Qt.AlignCenter)
            if "ROCmFP4" in quant:
                quant_item.setForeground(QColor("#ff4d00"))
            elif quant == "MTP":
                quant_item.setForeground(QColor("#9b59b6"))
            table.setItem(i, 2, quant_item)

            # Badge recommandé
            badge = ""
            if "rocmfp4" in f["filename"].lower() and "mtp" not in f["filename"].lower():
                badge = "⭐"
            elif "iMatrix" in f["filename"] or "imatrix" in f["filename"]:
                badge = "⭐"
            table.setItem(i, 3, QTableWidgetItem(badge))

        dl.addWidget(table)

        # Barre de résumé des tailles
        summary_frame = QFrame()
        summary_frame.setProperty("summary", True)
        summary_layout = QHBoxLayout(summary_frame)
        summary_layout.setContentsMargins(12, 8, 12, 8)

        file_count = len(files)
        if total_size > 0:
            if total_size >= 1024**3:
                total_str = f"{total_size/(1024**3):.1f} GB"
            else:
                total_str = f"{total_size/(1024**2):.0f} MB"
        else:
            total_str = "?"

        summary_layout.addWidget(QLabel(f"📁 {file_count} file(s)"))
        summary_layout.addWidget(QLabel("•"))
        summary_layout.addWidget(QLabel(f"💾 Total: {total_str}"))
        summary_layout.addStretch()

        dl.addWidget(summary_frame)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        download_btn = QPushButton("⬇️ Download selected")
        download_btn.setMinimumHeight(36)
        download_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(download_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumHeight(36)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)

        dl.addLayout(btn_layout)

        if dialog.exec() == QDialog.Accepted:
            selected_files = []
            for row in sorted(selected_rows):
                if row < len(files):
                    selected_files.append(files[row]["filename"])
            if selected_files:
                repo_name = repo_id.split("/")[-1]
                self._download_queue = [(repo_id, fn, repo_name) for fn in selected_files]
                self._process_download_queue()

    def _process_download_queue(self):
        """Lance le téléchargement suivant dans la file."""
        if not self._download_queue:
            self._downloading = False
            self.progress_bar.setVisible(False)
            self.progress_label.setVisible(False)
            self.pause_btn.setVisible(False)
            self.resume_btn.setVisible(False)
            self.cancel_btn.setVisible(False)
            self._refresh()
            return
        self._downloading = True
        repo_id, filename, subdir = self._download_queue[0]
        self.progress_label.setText(f"⬇️ {filename} — en attente...")
        self.progress_label.setVisible(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.pause_btn.setVisible(True)
        self.resume_btn.setVisible(False)
        self.cancel_btn.setVisible(True)
        self._current_dl_task_id = self.models_mgr.download_model(
            repo_id, filename, subdir=subdir
        )
        self._dl_last_time = time.time()
        self._dl_last_bytes = 0

    def _download_model(self, repo_id: str, filename: str, subdir: str = ""):
        self.models_mgr.download_model(repo_id, filename, subdir=subdir)

    def _download_selected(self):
        pass  # Géré via _search_hf → _show_model_files → _download_model

    def _scan_lmstudio(self):
        lmstudio_path = Path.home() / ".lmstudio" / "models"
        models = self.models_mgr.scan_lmstudio(lmstudio_path)
        self._lmstudio_models = models
        self._refresh()

    def _import_single(self, path: str):
        use_symlink = self.use_symlink_check.isChecked()
        self.models_mgr.import_from_lmstudio(path, use_symlink)

    def _open_hf_page(self, model_id: str):
        """Ouvre la page HuggingFace du modèle."""
        import webbrowser
        webbrowser.open(f"https://huggingface.co/{model_id}")

    def _open_url(self, url: str):
        """Ouvre une URL dans le navigateur."""
        import webbrowser
        webbrowser.open(url)

    def _guess_hf_url(self, model_info: dict) -> str:
        """Construit une URL de recherche HuggingFace pour un modèle installé."""
        name = model_info.get("name", "")
        # Nettoyer le nom pour la recherche
        clean = name.replace(".gguf", "")
        # Enlever les suffixes de split comme -00001-of-00003
        import re
        clean = re.sub(r'-\d{5}-of-\d{5}', '', clean)
        return f"https://huggingface.co/models?search={clean}"

    def _import_all_lmstudio(self):
        use_symlink = self.use_symlink_check.isChecked()
        imported = 0
        for m in self._lmstudio_models:
            if self.models_mgr.import_from_lmstudio(m["path"], use_symlink):
                imported += 1
        if imported:
            QMessageBox.information(self, "Import", f"✅ {imported} model(s) imported from LM Studio")
            self._lmstudio_models = []
            self._refresh()
