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

    def build_server_args(self, model_path: str, mtp_path: str = "", mmproj_path: str = "") -> list:
        """Construit la liste d'arguments pour llama-server."""
        args = [
            "--model", model_path,
            "--host", self.get("host", "127.0.0.1"),
            "--port", str(self.port),
            "-dev", self.get("backend", "Vulkan0"),
            "--n-gpu-layers", str(self.get("gpu_layers", 999)),
            "--ctx-size", str(self.get("context_size", 32768)),
            "--parallel", str(self.get("parallel", 1)),
            "--batch-size", str(self.get("batch_size", 2048)),
            "--ubatch-size", str(self.get("ubatch_size", 1024)),
        ]

        if self.get("flash_attn", True):
            args.append("--flash-attn")
            args.append("on")

        # Fix SWA cache invalidation (llama.cpp PR #13194)
        # --no-kv-unified : alternative légère, ne double PAS la VRAM
        # --swa-full      : garantit le fix mais DOUBLE la VRAM du cache SWA → crash si VRAM insuffisante
        if self.get("no_kv_unified", False):
            args.append("--no-kv-unified")

        args.extend(["--cache-type-k", self.get("cache_type_k", "q8_0")])
        args.extend(["--cache-type-v", self.get("cache_type_v", "q8_0")])

        # Vision model (mmproj)
        mmproj = mmproj_path or self.get("last_mmproj_model", "")
        if mmproj:
            args.extend(["--mmproj", mmproj])

        args.append("--jinja")

        rf = self.get("reasoning_format", "")
        if rf:
            args.extend(["--reasoning-format", rf])

        if self.get("api_key_enabled", False):
            api_key = self.get("api_key", "")
            if api_key:
                args.extend(["--api-key", api_key])

        # MTP spéculatif
        if self.get("mtp_enabled", False):
            draft_model = mtp_path if mtp_path else model_path
            args.extend([
                "--spec-type", "draft-mtp",
                "--spec-draft-model", draft_model,
                "--spec-draft-device", self.get("backend", "Vulkan0"),
                "--spec-draft-ngl", str(self.get("gpu_layers", 999)),
                "--spec-draft-n-max", str(self.get("mtp_n_max", 4)),
                "--spec-draft-p-min", str(self.get("mtp_p_min", 0.55)),
                "--spec-draft-p-split", str(self.get("mtp_p_split", 0.10)),
                "--spec-draft-type-k", "f16",
                "--spec-draft-type-v", "f16",
                "--spec-draft-backend-sampling",
            ])

        # Utiliser les arguments spécifiques au modèle si disponibles
        extra = self.get_model_args(model_path)
        if extra:
            import shlex
            args.extend(shlex.split(extra))

        return args
