"""Onglet Configuration : paramètres du serveur et lancement."""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QSpinBox, QComboBox, QCheckBox, QSlider,
    QLineEdit, QFileDialog, QGridLayout, QTextEdit, QMessageBox,
    QApplication
)
from PySide6.QtCore import Qt, QTimer

from src.utils.config import Config
from src.core.server_controller import ServerController


class ConfigTab(QWidget):
    """Configuration du serveur llama-server."""

    def __init__(self, config: Config, server: ServerController):
        super().__init__()
        self.config = config
        self.server = server
        self._setup_ui()
        self._load_config()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(12, 12, 12, 12)

        # === Modèle ===
        model_group = QGroupBox("📦 Model")
        model_grid = QGridLayout(model_group)
        model_grid.setSpacing(10)
        model_grid.setContentsMargins(4, 4, 4, 4)
        model_grid.setColumnStretch(1, 1)  # le champ texte prend tout l'espace

        model_grid.addWidget(QLabel("GGUF File:"), 0, 0)
        self.model_path_input = QLineEdit()
        self.model_path_input.setPlaceholderText("Path to .gguf file...")
        self.model_path_input.setMinimumHeight(36)
        self.model_path_input.setToolTip("Path to the main .gguf model file")
        model_grid.addWidget(self.model_path_input, 0, 1)
        self.browse_model_btn = QPushButton("📂 Browse")
        self.browse_model_btn.setMinimumHeight(36)
        self.browse_model_btn.setMinimumWidth(100)
        self.browse_model_btn.clicked.connect(self._browse_model)
        self.model_path_input.textChanged.connect(self._on_model_path_changed)
        model_grid.addWidget(self.browse_model_btn, 0, 2)

        model_grid.addWidget(QLabel("MTP Companion:"), 1, 0)
        self.mtp_path_input = QLineEdit()
        self.mtp_path_input.setPlaceholderText("MTP .gguf file (optional)...")
        self.mtp_path_input.setMinimumHeight(36)
        self.mtp_path_input.setToolTip("MTP companion .gguf file (speculative decoding)\n"
            "Optional — leave EMPTY if the main model already contains MTP (self-speculative)\n"
            "mmproj-F32.gguf is a CLIP vision file, NOT an MTP model")
        model_grid.addWidget(self.mtp_path_input, 1, 1)
        self.browse_mtp_btn = QPushButton("📂 Browse")
        self.browse_mtp_btn.setMinimumHeight(36)
        self.browse_mtp_btn.setMinimumWidth(100)
        self.browse_mtp_btn.clicked.connect(self._browse_mtp)
        model_grid.addWidget(self.browse_mtp_btn, 1, 2)

        model_grid.addWidget(QLabel("Vision Model:"), 2, 0)
        self.mmproj_path_input = QLineEdit()
        self.mmproj_path_input.setPlaceholderText("mmproj .gguf file (optional, for vision)...")
        self.mmproj_path_input.setMinimumHeight(36)
        self.mmproj_path_input.setToolTip("mmproj-F32.gguf file for vision/multimodal capabilities\n"
            "Optional — only if the model supports images")
        model_grid.addWidget(self.mmproj_path_input, 2, 1)
        self.browse_mmproj_btn = QPushButton("📂 Browse")
        self.browse_mmproj_btn.setMinimumHeight(36)
        self.browse_mmproj_btn.setMinimumWidth(100)
        self.browse_mmproj_btn.clicked.connect(self._browse_mmproj)
        model_grid.addWidget(self.browse_mmproj_btn, 2, 2)

        model_grid.addWidget(QLabel("Draft Model:"), 3, 0)
        self.draft_path_input = QLineEdit()
        self.draft_path_input.setPlaceholderText("Draft .gguf file (optional, for speculative decoding)...")
        self.draft_path_input.setMinimumHeight(36)
        self.draft_path_input.setToolTip("External draft model for speculative decoding\n"
            "Used as --spec-draft-model when MTP is enabled\n"
            "Leave empty to use the main model as its own draft (self-speculative)")
        model_grid.addWidget(self.draft_path_input, 3, 1)
        self.browse_draft_btn = QPushButton("📂 Browse")
        self.browse_draft_btn.setMinimumHeight(36)
        self.browse_draft_btn.setMinimumWidth(100)
        self.browse_draft_btn.clicked.connect(self._browse_draft)
        model_grid.addWidget(self.browse_draft_btn, 3, 2)

        model_grid.addWidget(QLabel("Chat Template:"), 4, 0)
        self.chat_template_input = QLineEdit()
        self.chat_template_input.setPlaceholderText("Path to .jinja template file (optional)...")
        self.chat_template_input.setMinimumHeight(36)
        self.chat_template_input.setToolTip("Custom Jinja chat template file\n"
            "Uses --chat-template <file> instead of the embedded template\n"
            "Leave empty to use --jinja (embedded template from GGUF)")
        model_grid.addWidget(self.chat_template_input, 4, 1)
        self.browse_template_btn = QPushButton("📂 Browse")
        self.browse_template_btn.setMinimumHeight(36)
        self.browse_template_btn.setMinimumWidth(100)
        self.browse_template_btn.clicked.connect(self._browse_template)
        model_grid.addWidget(self.browse_template_btn, 4, 2)

        layout.addWidget(model_group)

        # === Performance ===
        perf_group = QGroupBox("⚡ Performance")
        perf_grid = QGridLayout(perf_group)
        perf_grid.setSpacing(8)
        perf_grid.setContentsMargins(10, 16, 10, 10)
        perf_grid.setColumnStretch(1, 1)
        perf_grid.setColumnStretch(3, 1)

        # Row 0
        backend_label = QLabel("Backend:")
        backend_label.setToolTip("GPU backend to use\nVulkan0 = recommended on Strix Halo (fastest)\nROCm0 = HIP/ROCm backend")
        perf_grid.addWidget(backend_label, 0, 0)
        self.backend_combo = QComboBox()
        self.backend_combo.addItems(["Vulkan0", "ROCm0"])
        self.backend_combo.setToolTip("Vulkan0: recommended (tested faster on Strix Halo)\nROCm0: alternative HIP/ROCm backend")
        perf_grid.addWidget(self.backend_combo, 0, 1)

        ctx_label = QLabel("Context:")
        ctx_label.setToolTip("Context size in tokens (-c)\nMemory = context × ~2 MB per token\n32768 = ~8 GB VRAM")
        perf_grid.addWidget(ctx_label, 0, 2)

        # Slider + saisie manuelle pour le contexte
        ctx_widget = QWidget()
        ctx_row = QHBoxLayout(ctx_widget)
        ctx_row.setContentsMargins(0, 0, 0, 0)
        ctx_row.setSpacing(6)

        self.ctx_slider = QSlider(Qt.Horizontal)
        self.ctx_slider.setRange(0, 3)
        self.ctx_slider.setTickPosition(QSlider.TicksBelow)
        self.ctx_slider.setTickInterval(1)
        self.ctx_slider.setFixedWidth(180)
        ctx_row.addWidget(self.ctx_slider)

        self.ctx_input = QLineEdit()
        self.ctx_input.setPlaceholderText("32768")
        self.ctx_input.setFixedWidth(100)
        self.ctx_input.setAlignment(Qt.AlignRight)
        self.ctx_input.setToolTip("Taille du contexte (-c) en tokens\n32k / 64k / 128k / 200k\nOu saisissez une valeur personnalisée")
        ctx_row.addWidget(self.ctx_input)

        ctx_row.addWidget(QLabel("tokens"))
        ctx_row.addStretch()
        perf_grid.addWidget(ctx_widget, 0, 3)

        # Mapping slider ↔ valeurs
        self._ctx_steps = [32768, 65536, 131072, 204800]
        self._ctx_labels = ["32k", "64k", "128k", "200k"]

        def _ctx_slider_changed(pos):
            val = self._ctx_steps[pos]
            self.ctx_input.setText(str(val))

        def _ctx_text_changed():
            txt = self.ctx_input.text().strip()
            if not txt:
                return
            try:
                val = int(txt)
                # Trouver le step le plus proche
                closest = min(range(len(self._ctx_steps)),
                              key=lambda i: abs(self._ctx_steps[i] - val))
                self.ctx_slider.blockSignals(True)
                self.ctx_slider.setValue(closest)
                self.ctx_slider.blockSignals(False)
            except ValueError:
                pass

        self.ctx_slider.valueChanged.connect(_ctx_slider_changed)
        self.ctx_input.textChanged.connect(_ctx_text_changed)

        # Valeur initiale
        self.ctx_slider.setValue(0)  # 32k

        # Row 1
        batch_label = QLabel("Batch:")
        batch_label.setToolTip("Taille du batch pour le traitement des prompts (-b)\nValeur élevée = préremplissage plus rapide")
        perf_grid.addWidget(batch_label, 1, 0)
        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(128, 16384)
        self.batch_spin.setSingleStep(128)
        self.batch_spin.setValue(2048)
        self.batch_spin.setToolTip("Taille de batch (-b) pour le traitement du prompt")
        perf_grid.addWidget(self.batch_spin, 1, 1)

        ubatch_label = QLabel("Ubatch:")
        ubatch_label.setToolTip("Taille du batch physique pour les calculs GPU (-ub)\nGénéralement moitié du batch principal")
        perf_grid.addWidget(ubatch_label, 1, 2)
        self.ubatch_spin = QSpinBox()
        self.ubatch_spin.setRange(64, 16384)
        self.ubatch_spin.setSingleStep(64)
        self.ubatch_spin.setValue(1024)
        self.ubatch_spin.setToolTip("Taille de batch physique GPU (-ub)")
        perf_grid.addWidget(self.ubatch_spin, 1, 3)

        # Row 2
        gpu_layers_label = QLabel("GPU Layers:")
        gpu_layers_label.setToolTip("Number of model layers to offload to GPU (-ngl)\n999 = all layers on GPU")
        perf_grid.addWidget(gpu_layers_label, 2, 0)
        self.gpu_layers_spin = QSpinBox()
        self.gpu_layers_spin.setRange(1, 999)
        self.gpu_layers_spin.setValue(999)
        self.gpu_layers_spin.setToolTip("999 = all layers on GPU\n0 = CPU only\nAdjust if GPU memory is insufficient")
        perf_grid.addWidget(self.gpu_layers_spin, 2, 1)

        self.flash_attn_check = QCheckBox("Flash Attention")
        self.flash_attn_check.setChecked(True)
        self.flash_attn_check.setToolTip("Flash attention memory (-fa)\nReduces context memory usage\nRecommended: enabled")
        perf_grid.addWidget(self.flash_attn_check, 2, 2)

        # Fix cache SWA
        self.no_kv_unified_check = QCheckBox("Fix SWA cache bug")
        self.no_kv_unified_check.setChecked(False)
        self.no_kv_unified_check.setToolTip(
            "Workaround for SWA cache invalidation (--no-kv-unified)\n"
            "ENABLE if llama.cpp shows 'forcing full prompt re-processing'\n"
            "(Qwen 3.x / Gemma 3-4 models on any KV cache type)\n"
            "⚠️ If this doesn't help, try --swa-full in Advanced args\n"
            "   (but --swa-full DOUBLES VRAM and may crash!)"
        )
        perf_grid.addWidget(self.no_kv_unified_check, 3, 2)

        # === Environnement ROCm (env vars, PAS des flags CLI) ===
        # Cases compactes sur la ligne existante → aucune hauteur ajoutée
        self.env_gfx_check = QCheckBox("gfx1151")
        self.env_gfx_check.setChecked(True)
        self.env_gfx_check.setToolTip(
            "Export HSA_OVERRIDE_GFX_VERSION=11.5.1\n"
            "Required for AMD Strix Halo (gfx1151) on HIP/ROCm"
        )
        perf_grid.addWidget(self.env_gfx_check, 3, 0)

        self.env_umem_check = QCheckBox("Unified mem")
        self.env_umem_check.setChecked(True)
        self.env_umem_check.setToolTip(
            "Export GGML_HIP_ENABLE_UNIFIED_MEMORY=1\n"
            "Unified memory pool (HIP)"
        )
        perf_grid.addWidget(self.env_umem_check, 3, 1)

        self.env_ldlib_check = QCheckBox("LD_LIBRARY_PATH")
        self.env_ldlib_check.setChecked(True)
        self.env_ldlib_check.setToolTip(
            "Prepend the ROCmFPX build/bin to LD_LIBRARY_PATH\n"
            "Avoids a soname clash if a Vulkan llama.cpp build is also installed"
        )
        perf_grid.addWidget(self.env_ldlib_check, 3, 3)

        # Parallel dans un sous-layout horizontal
        parallel_widget = QWidget()
        parallel_layout = QHBoxLayout(parallel_widget)
        parallel_layout.setContentsMargins(0, 0, 0, 0)
        parallel_layout.setSpacing(6)
        parallel_layout.addWidget(QLabel("Parallel:"))
        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(1, 8)
        self.parallel_spin.setValue(1)
        parallel_layout.addWidget(self.parallel_spin)
        parallel_layout.addStretch()
        perf_grid.addWidget(parallel_widget, 2, 3)

        layout.addWidget(perf_group)

        # === Cache ===
        cache_group = QGroupBox("💾 K/V Cache")
        cache_grid = QHBoxLayout(cache_group)
        cache_grid.setSpacing(12)
        cache_grid.setContentsMargins(10, 16, 10, 10)

        cache_grid.addWidget(QLabel("Cache K:"))
        self.cache_k_combo = QComboBox()
        kv_cache_types = [
            "f32", "f16", "bf16",
            "q8_0", "q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1",
            "q4_0_rocmfp4", "q4_0_rocmfp4_fast",
            "q3_0_rocmfpx", "q6_0_rocmfpx", "q8_0_rocmfpx",
            "turbo3", "turbo4",
        ]
        self.cache_k_combo.addItems(kv_cache_types)
        self.cache_k_combo.setCurrentText("q8_0")
        self.cache_k_combo.setFixedWidth(140)
        cache_grid.addWidget(self.cache_k_combo)

        cache_grid.addSpacing(20)

        cache_grid.addWidget(QLabel("Cache V:"))
        self.cache_v_combo = QComboBox()
        self.cache_v_combo.addItems(kv_cache_types)
        self.cache_v_combo.setCurrentText("q8_0")
        self.cache_v_combo.setFixedWidth(140)
        cache_grid.addWidget(self.cache_v_combo)

        cache_grid.addStretch()

        layout.addWidget(cache_group)

        # === MTP Speculative Decoding ===
        mtp_group = QGroupBox("🚀 MTP Speculative Decoding")
        mtp_layout = QVBoxLayout(mtp_group)
        mtp_layout.setSpacing(8)
        mtp_layout.setContentsMargins(10, 16, 10, 10)

        mtp_top_row = QHBoxLayout()
        mtp_top_row.setSpacing(8)

        self.mtp_check = QCheckBox("Enable MTP")
        mtp_top_row.addWidget(self.mtp_check)

        mtp_top_row.addSpacing(12)
        mtp_top_row.addWidget(QLabel("n-max:"))
        self.mtp_nmax_spin = QSpinBox()
        self.mtp_nmax_spin.setRange(1, 6)
        self.mtp_nmax_spin.setValue(4)
        self.mtp_nmax_spin.setFixedWidth(70)
        mtp_top_row.addWidget(self.mtp_nmax_spin)

        mtp_top_row.addSpacing(12)
        mtp_top_row.addWidget(QLabel("p-min:"))
        self.mtp_pmin_spin = QSpinBox()
        self.mtp_pmin_spin.setRange(5, 100)
        self.mtp_pmin_spin.setValue(55)
        self.mtp_pmin_spin.setSuffix("%")
        self.mtp_pmin_spin.setFixedWidth(70)
        mtp_top_row.addWidget(self.mtp_pmin_spin)

        mtp_top_row.addSpacing(12)
        mtp_top_row.addWidget(QLabel("p-split:"))
        self.mtp_psplit_spin = QSpinBox()
        self.mtp_psplit_spin.setRange(1, 100)
        self.mtp_psplit_spin.setValue(10)
        self.mtp_psplit_spin.setSuffix("%")
        self.mtp_psplit_spin.setFixedWidth(70)
        mtp_top_row.addWidget(self.mtp_psplit_spin)

        mtp_top_row.addStretch()

        mtp_layout.addLayout(mtp_top_row)
        layout.addWidget(mtp_group)



        # === Advanced arguments ===
        adv_group = QGroupBox("Advanced arguments (optional)")
        adv_layout = QVBoxLayout(adv_group)
        self.adv_args_input = QLineEdit()
        self.adv_args_input.setPlaceholderText("e.g. --no-mmap --cont-batching ...")
        adv_layout.addWidget(self.adv_args_input)

        # Label pour indiquer si les args sont spécifiques au modèle
        self.adv_args_label = QLabel("")
        self.adv_args_label.setStyleSheet("font-size: 11px; color: #888;")
        adv_layout.addWidget(self.adv_args_label)
        layout.addWidget(adv_group)

        # === Boutons ===
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("💾 Save configuration")
        self.save_btn.setMinimumHeight(38)
        self.save_btn.setStyleSheet("QPushButton { text-align: center; }")
        self.save_btn.clicked.connect(self._save_config)
        btn_layout.addWidget(self.save_btn)

        self.reset_btn = QPushButton("↩️ Reset")
        self.reset_btn.setMinimumHeight(38)
        self.reset_btn.setStyleSheet("QPushButton { text-align: center; }")
        self.reset_btn.clicked.connect(self._reset_config)
        btn_layout.addWidget(self.reset_btn)

        self.copy_btn = QPushButton("📋 Copier params")
        self.copy_btn.setMinimumHeight(38)
        self.copy_btn.setStyleSheet("QPushButton { text-align: center; }")
        self.copy_btn.setToolTip("Copie les paramètres batch/ubatch/cache/MTP/flash attn/advanced args en ligne de commande")
        self.copy_btn.clicked.connect(self._copy_params)
        btn_layout.addWidget(self.copy_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        layout.addStretch()

    def _load_config(self):
        """Charge la configuration : paramètres du modèle si dispo, sinon globaux."""
        model_path = self.config.get("last_model", "")
        self.model_path_input.setText(model_path)
        g = lambda k, d: self.config.get_model_setting(model_path, k, d)

        self.mtp_path_input.setText(self.config.get("last_mtp_model", ""))
        self.mmproj_path_input.setText(self.config.get("last_mmproj_model", ""))
        self.draft_path_input.setText(self.config.get("last_draft_model", ""))
        self.chat_template_input.setText(self.config.get("chat_template", ""))
        self.backend_combo.setCurrentText(g("backend", "Vulkan0"))
        self.ctx_input.setText(str(int(g("context_size", 32768))))
        self.batch_spin.setValue(int(g("batch_size", 2048)))
        self.ubatch_spin.setValue(int(g("ubatch_size", 1024)))
        self.gpu_layers_spin.setValue(int(g("gpu_layers", 999)))
        self.flash_attn_check.setChecked(g("flash_attn", True))
        self.no_kv_unified_check.setChecked(g("no_kv_unified", False))
        self.env_gfx_check.setChecked(g("env_hsa_override_gfx", True))
        self.env_umem_check.setChecked(g("env_unified_memory", True))
        self.env_ldlib_check.setChecked(g("env_prepend_ld_library_path", True))
        self.parallel_spin.setValue(int(g("parallel", 1)))
        self.cache_k_combo.setCurrentText(g("cache_type_k", "q8_0"))
        self.cache_v_combo.setCurrentText(g("cache_type_v", "q8_0"))
        self.mtp_check.setChecked(g("mtp_enabled", False))
        self.mtp_nmax_spin.setValue(int(g("mtp_n_max", 4)))
        self.mtp_pmin_spin.setValue(int(g("mtp_p_min", 0.55) * 100))
        self.mtp_psplit_spin.setValue(int(g("mtp_p_split", 0.10) * 100))

        # Charger les args spécifiques au modèle et mettre à jour le label
        self._load_model_args()
        self._update_model_label()

    def _update_model_label(self):
        """Met à jour le label indiquant si le modèle a un profil sauvegardé."""
        model_path = self.model_path_input.text().strip()
        if model_path:
            model_name = Path(model_path).name
            if self.config.has_model_settings(model_path):
                self.adv_args_label.setText(
                    f"✅ Model profile active for {model_name} "
                    f"(all settings below are model-specific)"
                )
                self.adv_args_label.setStyleSheet("font-size: 11px; color: #34a853; font-weight: bold;")
            else:
                self.adv_args_label.setText(
                    f"🆕 No saved profile for {model_name} — using global defaults"
                )
                self.adv_args_label.setStyleSheet("font-size: 11px; color: #fbbc04;")
        else:
            self.adv_args_label.setText("")

    def _on_model_path_changed(self):
        """Appelé quand le chemin du modèle change : recharge TOUS les paramètres
        spécifiques au modèle (pas seulement les arguments avancés)."""
        self._load_model_args()
        self._update_model_label()
        self._reload_model_specific_fields()

    def _reload_model_specific_fields(self):
        """Recharge tous les champs de l'UI depuis les paramètres du modèle
        courant, sans toucher au champ model_path (évite la récursion)."""
        model_path = self.model_path_input.text().strip()
        g = lambda k, d: self.config.get_model_setting(model_path, k, d)

        self.backend_combo.setCurrentText(g("backend", "Vulkan0"))
        raw_ctx = str(int(g("context_size", 32768)))
        self.ctx_input.setText(raw_ctx)
        # Forcer la mise à jour du slider
        try:
            val = int(raw_ctx)
            closest = min(range(len(self._ctx_steps)),
                          key=lambda i: abs(self._ctx_steps[i] - val))
            self.ctx_slider.blockSignals(True)
            self.ctx_slider.setValue(closest)
            self.ctx_slider.blockSignals(False)
        except ValueError:
            pass
        self.batch_spin.setValue(int(g("batch_size", 2048)))
        self.ubatch_spin.setValue(int(g("ubatch_size", 1024)))
        self.gpu_layers_spin.setValue(int(g("gpu_layers", 999)))
        self.flash_attn_check.setChecked(g("flash_attn", True))
        self.no_kv_unified_check.setChecked(g("no_kv_unified", False))
        self.env_gfx_check.setChecked(g("env_hsa_override_gfx", True))
        self.env_umem_check.setChecked(g("env_unified_memory", True))
        self.env_ldlib_check.setChecked(g("env_prepend_ld_library_path", True))
        self.parallel_spin.setValue(int(g("parallel", 1)))
        self.cache_k_combo.setCurrentText(g("cache_type_k", "q8_0"))
        self.cache_v_combo.setCurrentText(g("cache_type_v", "q8_0"))
        self.mtp_check.setChecked(g("mtp_enabled", False))
        self.mtp_nmax_spin.setValue(int(g("mtp_n_max", 4)))
        self.mtp_pmin_spin.setValue(int(g("mtp_p_min", 0.55) * 100))
        self.mtp_psplit_spin.setValue(int(g("mtp_p_split", 0.10) * 100))

    def _load_model_args(self):
        """Load model-specific advanced arguments."""
        model_path = self.model_path_input.text().strip()
        if model_path:
            args = self.config.get_model_args(model_path)
            self.adv_args_input.setText(args)
        else:
            self.adv_args_input.setText(self.config.get("advanced_args", ""))

    def _save_config(self):
        model_path = self.model_path_input.text().strip()
        self.config.set("last_model", model_path)
        self.config.set("last_mtp_model", self.mtp_path_input.text())
        self.config.set("last_mmproj_model", self.mmproj_path_input.text())
        self.config.set("last_draft_model", self.draft_path_input.text())
        self.config.set("chat_template", self.chat_template_input.text())

        # Construire le dict des paramètres à sauvegarder
        raw_ctx = self.ctx_input.text().strip()
        try:
            ctx_val = int(raw_ctx)
        except ValueError:
            ctx_val = 32768

        settings = {
            "backend": self.backend_combo.currentText(),
            "context_size": ctx_val,
            "batch_size": self.batch_spin.value(),
            "ubatch_size": self.ubatch_spin.value(),
            "gpu_layers": self.gpu_layers_spin.value(),
            "flash_attn": self.flash_attn_check.isChecked(),
            "no_kv_unified": self.no_kv_unified_check.isChecked(),
            "env_hsa_override_gfx": self.env_gfx_check.isChecked(),
            "env_unified_memory": self.env_umem_check.isChecked(),
            "env_prepend_ld_library_path": self.env_ldlib_check.isChecked(),
            "parallel": self.parallel_spin.value(),
            "cache_type_k": self.cache_k_combo.currentText(),
            "cache_type_v": self.cache_v_combo.currentText(),
            "mtp_enabled": self.mtp_check.isChecked(),
            "mtp_n_max": self.mtp_nmax_spin.value(),
            "mtp_p_min": self.mtp_pmin_spin.value() / 100.0,
            "mtp_p_split": self.mtp_psplit_spin.value() / 100.0,
        }

        if model_path:
            # Sauvegarder dans le profil du modèle
            self.config.set_model_settings(model_path, settings)
            # Sauvegarder aussi les args avancés
            self.config.set_model_args(model_path, self.adv_args_input.text())
        else:
            # Pas de modèle sélectionné → sauvegarde globale (fallback)
            for k, v in settings.items():
                self.config.set(k, v)
            self.config.set("advanced_args", self.adv_args_input.text())

        self.config.save()

        # Mettre à jour le label
        self._update_model_label()

        model_name = Path(model_path).name if model_path else "Global"
        QMessageBox.information(
            self, "Configuration",
            f"Configuration saved for {model_name} ✓"
        )

    def _reset_config(self):
        from src.utils.config import Config as Cfg
        temp = Cfg()
        for k, v in temp._data.items():
            self.config.set(k, v)
        self._load_config()
        QMessageBox.information(self, "Configuration", "Configuration reset ✓")

    def _copy_params(self):
        """Copie les paramètres batch/ubatch/cache/MTP/flash attn/advanced args."""
        parts = []

        # Batch & Ubatch
        b = self.batch_spin.value()
        u = self.ubatch_spin.value()
        parts.append(f"--batch-size {b}")
        parts.append(f"--ubatch-size {u}")

        # Cache K/V
        ck = self.cache_k_combo.currentText()
        cv = self.cache_v_combo.currentText()
        parts.append(f"--cache-type-k {ck}")
        parts.append(f"--cache-type-v {cv}")

        # MTP n-max
        nm = self.mtp_nmax_spin.value()
        parts.append(f"--spec-draft-n-max {nm}")

        # Flash Attention (seulement si coché)
        if self.flash_attn_check.isChecked():
            parts.append("--flash-attn on")

        # MTP p-min / p-split
        pmin = self.mtp_pmin_spin.value()
        psplit = self.mtp_psplit_spin.value()
        parts.append(f"--spec-draft-p-min {pmin / 100:.2f}")
        parts.append(f"--spec-draft-p-split {psplit / 100:.2f}")

        # Advanced args
        adv = self.adv_args_input.text().strip()
        if adv:
            parts.append(adv)

        cmd = " ".join(parts)
        QApplication.clipboard().setText(cmd)

    def _browse_model(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a GGUF model",
            str(self.config.models_path),
            "GGUF Files (*.gguf);;All Files (*)"
        )
        if path:
            self.model_path_input.setText(path)

    def _browse_mtp(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select MTP companion",
            str(self.config.models_path),
            "GGUF Files (*.gguf);;All Files (*)"
        )
        if path:
            self.mtp_path_input.setText(path)

    def _browse_mmproj(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Vision model (mmproj)",
            str(self.config.models_path),
            "GGUF Files (*.gguf);;All Files (*)"
        )
        if path:
            self.mmproj_path_input.setText(path)

    def _browse_draft(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Draft model",
            str(self.config.models_path),
            "GGUF Files (*.gguf);;All Files (*)"
        )
        if path:
            self.draft_path_input.setText(path)

    def _browse_template(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Chat Template",
            str(Path.home()),
            "Jinja Templates (*.jinja *.j2);;All Files (*)"
        )
        if path:
            self.chat_template_input.setText(path)
