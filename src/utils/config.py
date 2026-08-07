"""Gestion de la configuration utilisateur."""

import json
import os
from pathlib import Path


def _model_key(model_path: str) -> str:
    """Extrait une clé unique pour un modèle depuis son chemin."""
    return Path(model_path).name


class Config:
    """Charge et sauvegarde la configuration depuis default_settings.json + user overrides."""

    DEFAULTS_PATH = Path(__file__).parent.parent.parent / "config" / "default_settings.json"
    CONFIG_DIR = Path.home() / ".config" / "rocmfp4-manager"
    CONFIG_PATH = CONFIG_DIR / "settings.json"

    def __init__(self):
        self._data = self._load()

    def _load(self) -> dict:
        """Charge la config: d'abord les défauts, puis les surcharges utilisateur."""
        defaults = {}
        if self.DEFAULTS_PATH.exists():
            with open(self.DEFAULTS_PATH) as f:
                defaults = json.load(f)

        overrides = {}
        if self.CONFIG_PATH.exists():
            with open(self.CONFIG_PATH) as f:
                overrides = json.load(f)

        merged = {**defaults, **overrides}
        # Fusion profonde pour rocmfpx_profiles (les overrides complètent les defaults)
        if "rocmfpx_profiles" in defaults and "rocmfpx_profiles" in overrides:
            merged["rocmfpx_profiles"] = {**defaults["rocmfpx_profiles"], **overrides["rocmfpx_profiles"]}
        # Résoudre les chemins ~
        for key in ("models_path", "lmstudio_path", "rocmfpx_path"):
            if key in merged and isinstance(merged[key], str):
                merged[key] = str(Path(merged[key]).expanduser())
        return merged

    def save(self):
        """Sauvegarde la config utilisateur (sans les defaults)."""
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(self.CONFIG_PATH, "w") as f:
            json.dump(self._data, f, indent=2)

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value

    def get_model_args(self, model_path: str) -> str:
        """Retourne les arguments avancés spécifiques à un modèle.
        Si le modèle n'a pas d'args dédiés, utilise les args globaux.
        """
        key = _model_key(model_path)
        model_args = self._data.get("model_advanced_args", {})
        return model_args.get(key, self._data.get("advanced_args", ""))

    def set_model_args(self, model_path: str, args: str):
        """Sauvegarde les arguments avancés pour un modèle spécifique."""
        key = _model_key(model_path)
        if "model_advanced_args" not in self._data:
            self._data["model_advanced_args"] = {}
        self._data["model_advanced_args"][key] = args

    # ------------------------------------------------------------------
    # Paramètres par modèle (profils modèles)
    # ------------------------------------------------------------------

    # Liste des clés qui peuvent être sauvegardées par modèle
    MODEL_SETTING_KEYS = [
        "backend", "context_size", "batch_size", "ubatch_size",
        "gpu_layers", "flash_attn", "no_kv_unified", "parallel",
        "cache_type_k", "cache_type_v",
        "mtp_enabled", "mtp_n_max", "mtp_p_min", "mtp_p_split",
        "env_hsa_override_gfx", "env_unified_memory", "env_prepend_ld_library_path",
        "rocmfpx_active_profile",
    ]

    def get_model_setting(self, model_path: str, key: str, default=None):
        """Récupère un paramètre pour un modèle spécifique, avec fallback global."""
        if not model_path:
            return self.get(key, default)
        model_key = _model_key(model_path)
        model_settings = self._data.get("model_settings", {})
        if model_key in model_settings and key in model_settings[model_key]:
            return model_settings[model_key][key]
        return self.get(key, default)

    def set_model_settings(self, model_path: str, settings: dict):
        """Sauvegarde plusieurs paramètres pour un modèle spécifique."""
        if not model_path:
            return
        model_key = _model_key(model_path)
        if "model_settings" not in self._data:
            self._data["model_settings"] = {}
        if model_key not in self._data["model_settings"]:
            self._data["model_settings"][model_key] = {}
        self._data["model_settings"][model_key].update(settings)

    def get_model_settings(self, model_path: str) -> dict:
        """Retourne tous les paramètres sauvegardés pour un modèle."""
        if not model_path:
            return {}
        model_key = _model_key(model_path)
        return self._data.get("model_settings", {}).get(model_key, {})

    def has_model_settings(self, model_path: str) -> bool:
        """Vérifie si un modèle a des paramètres personnalisés."""
        return bool(self.get_model_settings(model_path))

    @property
    def data(self) -> dict:
        return self._data

    @property
    def models_path(self) -> Path:
        p = Path(self.get("models_path", "~/models/rocmfp4"))
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def port(self) -> int:
        return int(self.get("port", 1412))

    @property
    def api_url(self) -> str:
        host = self.get("host", "127.0.0.1")
        return f"http://{host}:{self.port}"

    @property
    def api_chat_url(self) -> str:
        return f"{self.api_url}/v1/chat/completions"

    @property
    def api_completions_url(self) -> str:
        return f"{self.api_url}/v1/completions"

    @property
    def api_embeddings_url(self) -> str:
        return f"{self.api_url}/v1/embeddings"

    @property
    def api_health_url(self) -> str:
        return f"{self.api_url}/health"

    # ------------------------------------------------------------------
    # Lucebox / dflash_server
    # ------------------------------------------------------------------

    def is_lucebox_model(self, model_path: str) -> bool:
        """Détecte si le modèle nécessite dflash_server (Lucebox/DeepSeek V4)."""
        name = Path(model_path).name.lower()
        return any(kw in name for kw in [
            "deepseek-v4-flash", "rocmfp2-strix", "ds4", "dspark"
        ]) and Path.home() / "lucebox" / "server" / "build-hip" / "dflash_server"

    def build_lucebox_args(self, model_path: str) -> list:
        """Construit la liste d'arguments pour dflash_server (Lucebox)."""
        host = self.get("host", "127.0.0.1")
        args = [
            str(model_path),
            "--host", host,
            "--port", str(self.port),
            "--max-ctx", str(self.get("context_size", 8192)),
            "--chunk", str(self.get("batch_size", 2048)),
        ]

        # Draft model (DSpark)
        draft = self.get("last_draft_model", "")
        if draft:
            args.extend(["--draft", draft])

        # Device
        backend = self.get("backend", "Vulkan0")
        if backend == "Lucebox":
            args.extend(["--target-device", "hip:0"])
        elif backend == "ROCm0":
            args.extend(["--target-device", "hip:0"])
        else:
            args.extend(["--target-device", "auto:0"])

        # DeepSeek4 options
        if self.get("ds4_fused_decode", True):
            args.append("--ds4-fused-decode")

        top_k = self.get("ds4_expert_top_k", 4)
        if top_k > 0:
            args.extend(["--ds4-expert-top-k", str(top_k)])

        prefill = self.get("ds4_prefill", "exact")
        if prefill != "exact":
            args.extend(["--ds4-prefill", prefill])

        if self.get("flash_attn", True):
            args.extend(["--fa-window", "0"])

        # dflash_server uses its own hardcoded template or --chat-template-file
        chat_template = self.get("chat_template", "")
        if chat_template:
            args.extend(["--chat-template-file", chat_template])

        # Model name
        args.extend(["--model-name", Path(model_path).stem[:40]])

        return args

    def build_server_args(self, model_path: str, mtp_path: str = "", mmproj_path: str = "") -> list:
        """Construit la liste d'arguments pour llama-server.
        Utilise les paramètres spécifiques au modèle si disponibles, sinon les globaux.
        """
        g = lambda k, d: self.get_model_setting(model_path, k, d)

        args = [
            "--model", model_path,
            "--host", self.get("host", "127.0.0.1"),
            "--port", str(self.port),
            "-dev", g("backend", "Vulkan0"),
            "--n-gpu-layers", str(g("gpu_layers", 999)),
            "--ctx-size", str(g("context_size", 32768)),
            "--parallel", str(g("parallel", 1)),
            "--batch-size", str(g("batch_size", 2048)),
            "--ubatch-size", str(g("ubatch_size", 1024)),
        ]

        if g("flash_attn", True):
            args.append("--flash-attn")
            args.append("on")

        # Fix SWA cache invalidation (llama.cpp PR #13194)
        # --no-kv-unified : alternative légère, ne double PAS la VRAM
        # --swa-full      : garantit le fix mais DOUBLE la VRAM du cache SWA → crash si VRAM insuffisante
        if g("no_kv_unified", False):
            args.append("--no-kv-unified")

        args.extend(["--cache-type-k", g("cache_type_k", "q8_0")])
        args.extend(["--cache-type-v", g("cache_type_v", "q8_0")])

        # Vision model (mmproj)
        mmproj = mmproj_path or self.get("last_mmproj_model", "")
        if mmproj:
            args.extend(["--mmproj", mmproj])

        # Chat template: explicit file overrides --jinja
        chat_template = self.get("chat_template", "")
        if chat_template:
            args.extend(["--chat-template-file", chat_template])
        else:
            args.append("--jinja")

        rf = g("reasoning_format", "deepseek")
        if rf:
            args.extend(["--reasoning-format", rf])

        if self.get("api_key_enabled", False):
            api_key = self.get("api_key", "")
            if api_key:
                args.extend(["--api-key", api_key])

        # MTP spéculatif
        if g("mtp_enabled", False):
            # Draft model: explicit draft > MTP companion > main model (self-speculative)
            draft_model = (self.get("last_draft_model", "") or
                          mtp_path or
                          model_path)
            args.extend([
                "--spec-type", "draft-mtp",
                "--spec-draft-model", draft_model,
                "--spec-draft-device", g("backend", "Vulkan0"),
                "--spec-draft-ngl", str(g("gpu_layers", 999)),
                "--spec-draft-n-max", str(g("mtp_n_max", 4)),
                "--spec-draft-p-min", str(g("mtp_p_min", 0.55)),
                "--spec-draft-p-split", str(g("mtp_p_split", 0.10)),
                # KV du draft = même type que le KV cible (choisi dans l'UI).
                # Avant: forcé en f16 (2x la mémoire du q8_0).
                "--spec-draft-type-k", g("cache_type_k", "q8_0"),
                "--spec-draft-type-v", g("cache_type_v", "q8_0"),
                "--spec-draft-backend-sampling",
            ])

        # Utiliser les arguments spécifiques au modèle si disponibles
        extra = self.get_model_args(model_path)
        if extra:
            import shlex
            try:
                args.extend(shlex.split(extra))
            except ValueError as e:
                # Chaîne malformée (ex: guillemet non fermé) → message clair
                raise ValueError(
                    f"Malformed advanced arguments for model:\n{extra}\n\n"
                    f"Error: {e}\n\n"
                    "Check quotes in the 'Advanced arguments' field "
                    "(Configuration tab)."
                ) from e

        return args

    def build_server_env(self, server_bin, model_path: str = "") -> dict:
        """Construit l'environnement de llama-server selon les paramètres du modèle.
        Utilise les paramètres spécifiques au modèle si disponibles, sinon les globaux.
        """
        g = lambda k, d: self.get_model_setting(model_path, k, d) if model_path else self.get(k, d)
        env = os.environ.copy()
        if g("env_hsa_override_gfx", True):
            env["HSA_OVERRIDE_GFX_VERSION"] = "11.5.1"
        if g("env_unified_memory", True):
            env["GGML_HIP_ENABLE_UNIFIED_MEMORY"] = "1"
        if g("env_prepend_ld_library_path", True):
            bin_dir = str(Path(server_bin).resolve().parent)
            old = env.get("LD_LIBRARY_PATH")
            env["LD_LIBRARY_PATH"] = bin_dir + (os.pathsep + old if old else "")

        # Vulkan : lever la limite de taille d'un seul buffer (max_buffer_size).
        # Sans ça, le buffer de calcul d'un gros modèle à gros ubatch (ex. Step-3.7
        # 197B, b8192/u2048) dépasse la limite du driver → "Failed to allocate
        # pinned memory (... exceeds device buffer size limit)".
        # 64 Go : largement au-delà du buffer de calcul, mais < GTT (113 Go).
        # Configurable via vk_max_buffer_size (0 = désactivé, limite du driver).
        vk_max_buf = int(self.get("vk_max_buffer_size", 68719476736))
        if vk_max_buf > 0:
            env["GGML_VK_FORCE_MAX_BUFFER_SIZE"] = str(vk_max_buf)

        return env

    # ------------------------------------------------------------------
    # Profils ROCmFPX
    # ------------------------------------------------------------------

    @property
    def rocmfpx_active_profile(self) -> str:
        return self.get("rocmfpx_active_profile", "charlie-main")

    @property
    def rocmfpx_profiles(self) -> dict:
        return self.get("rocmfpx_profiles", {})

    def get_rocmfpx_build_dirs(self) -> list[Path]:
        """Retourne tous les répertoires build/bin possibles (tous profils)."""
        from pathlib import Path
        paths = []
        profiles = self.rocmfpx_profiles
        profiles_base = Path.home() / "ROCmFPX-profiles"

        for pid, info in profiles.items():
            build_dir = info.get("build_dir", "build-strix-rocmfp4")
            # Nouveau chemin (multi-profils)
            p = profiles_base / pid / build_dir / "bin"
            if p.exists():
                paths.append(p)
            # Compatibilité legacy: ~/ROCMFPX/build-strix-rocmfp4/bin/
            if pid == "charlie-main":
                legacy = Path.home() / "ROCMFPX" / build_dir / "bin"
                if legacy.exists() and legacy not in paths:
                    paths.append(legacy)

        # Ajouter aussi le rocmfpx_path legacy si défini
        rocmfpx_path = self.get("rocmfpx_path", "")
        if rocmfpx_path:
            from pathlib import Path
            rp = Path(rocmfpx_path)
            candidates = [
                rp / "build-strix-rocmfp4" / "bin",
                rp / "build" / "bin",
            ]
            for c in candidates:
                if c.exists() and c not in paths:
                    paths.append(c)

        return paths
