"""Contrôle le cycle de vie du serveur llama-server."""

import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Callable

from src.utils.config import Config
from src.utils.process_utils import ProcessManager
from src.core.responses_adapter import ResponsesAdapter


class ServerController:
    """Lance, arrête et surveille llama-server."""

    def __init__(self, config: Config):
        self.config = config
        self._proc = ProcessManager()
        self._listeners: list[Callable] = []
        self._log_buffer: list[str] = []
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._tokens_per_sec = 0.0
        self._model_name = ""
        self._start_time: Optional[float] = None

        # Adaptateur Responses API (port dédié)
        self._adapter_port = 1413
        self._adapter: Optional[ResponsesAdapter] = None

        # Détecter un serveur déjà en cours au démarrage
        self._detect_existing_server()

    def _get_expected_binary_paths(self) -> list[Path]:
        """Retourne les chemins possibles du binaire (profil actif d'abord)."""
        paths = []

        # Depuis le PATH
        which = subprocess.run(["which", "llama-server"], capture_output=True, text=True)
        if which.returncode == 0:
            paths.append(Path(which.stdout.strip()).resolve())

        # Profil actif d'abord
        active_profile = self.active_profile
        active = self._find_in_profile(active_profile, "llama-server")
        if active:
            paths.append(active.resolve())

        # Puis autres profils
        profiles = self.config.get("rocmfpx_profiles", {})
        for pid in profiles:
            if pid == active_profile:
                continue
            p = self._find_in_profile(pid, "llama-server")
            if p:
                paths.append(p.resolve())

        # Legacy + relatif
        legacy = Path.home() / "ROCMFPX" / "build-strix-rocmfp4" / "bin" / "llama-server"
        if legacy.exists():
            paths.append(legacy.resolve())

        local = Path(__file__).parent.parent.parent / "build-strix-rocmfp4" / "bin" / "llama-server"
        if local.exists():
            paths.append(local.resolve())

        return paths

    def _detect_existing_server(self):
        """Cherche un processus llama-server ROCmFPX déjà en cours et l'adopte.

        Ne cible QUE les llama-server compilés via ROCmFPX (vérifie le chemin
        du binaire dans /proc/PID/exe) pour éviter d'adopter un serveur
        externe (ex: lancé manuellement depuis un autre dossier).
        """
        expected_bins = self._get_expected_binary_paths()
        if not expected_bins:
            return  # Aucun binaire ROCmFPX connu → rien à détecter

        try:
            for entry in Path("/proc").iterdir():
                if not entry.name.isdigit():
                    continue
                try:
                    pid = int(entry.name)

                    # Lire le chemin réel de l'exécutable via /proc/PID/exe
                    exe_path = entry / "exe"
                    if not exe_path.exists():
                        continue
                    try:
                        real_exe = exe_path.resolve()
                    except OSError:
                        continue

                    # Vérifier que c'est bien un llama-server
                    if "llama-server" not in real_exe.name:
                        continue

                    # Vérifier que le chemin correspond à un binaire ROCmFPX attendu
                    if real_exe not in expected_bins:
                        continue

                    # Lire la ligne de commande
                    cmdline_path = entry / "cmdline"
                    if not cmdline_path.exists():
                        continue
                    cmd = cmdline_path.read_text().strip("\0")

                    # C'est notre serveur !
                    self._proc.adopt(pid)
                    self._running = True
                    self._start_time = time.time()

                    # Extraire le nom du modèle
                    model_match = re.search(r"--model\s+(\S+)", cmd)
                    if model_match:
                        self._model_name = Path(model_match.group(1)).name

                    self._notify("started", {
                        "model": self._model_name,
                        "pid": pid,
                        "detected": True,
                    })
                    return
                except (OSError, ValueError):
                    continue
        except PermissionError:
            pass

    @property
    def is_running(self) -> bool:
        return self._proc.is_running

    @property
    def pid(self) -> Optional[int]:
        return self._proc.pid

    @property
    def log_buffer(self) -> list[str]:
        return self._log_buffer

    @property
    def tokens_per_sec(self) -> float:
        return self._tokens_per_sec

    @property
    def uptime_seconds(self) -> float:
        if self._start_time and self.is_running:
            return time.time() - self._start_time
        return 0.0

    @property
    def memory_mb(self) -> Optional[float]:
        return self._proc.get_memory_mb()

    @property
    def api_url(self) -> str:
        return self.config.api_url

    @property
    def api_chat_url(self) -> str:
        return self.config.api_chat_url

    @property
    def api_completions_url(self) -> str:
        return self.config.api_completions_url

    @property
    def api_embeddings_url(self) -> str:
        return self.config.api_embeddings_url

    @property
    def api_health_url(self) -> str:
        return self.config.api_health_url

    @property
    def api_responses_url(self) -> str:
        """URL de l'endpoint Responses API (via l'adaptateur)."""
        host = self.config.get("host", "127.0.0.1")
        return f"http://{host}:{self._adapter_port}/v1/responses"

    @property
    def adapter_running(self) -> bool:
        """Indique si l'adaptateur Responses est actif."""
        return self._adapter is not None and self._adapter.is_running

    @property
    def adapter_logs(self) -> list[str]:
        """Logs de l'adaptateur Responses."""
        if self._adapter:
            return self._adapter.logs
        return []

    def add_listener(self, callback: Callable):
        """Ajoute un callback appelé sur changement d'état ou nouveau log."""
        self._listeners.append(callback)

    def _notify(self, event: str, data=None):
        for cb in self._listeners:
            try:
                cb(event, data)
            except Exception:
                pass

    def _find_llama_server(self) -> Optional[Path]:
        """Cherche le binaire llama-server : profil actif d'abord, puis fallback."""
        # Dans le PATH
        which = subprocess.run(["which", "llama-server"], capture_output=True, text=True)
        if which.returncode == 0:
            return Path(which.stdout.strip())

        # 1. Profil actif en priorité (spécifique au modèle si dispo)
        active_profile = self.active_profile
        active = self._find_in_profile(active_profile, "llama-server")
        if active:
            return active

        # 2. Fallback : tous les autres profils
        profiles = self.config.get("rocmfpx_profiles", {})
        for pid in profiles:
            if pid == active_profile:
                continue
            p = self._find_in_profile(pid, "llama-server")
            if p:
                return p

        # 3. Legacy ~/ROCMFPX
        legacy = Path.home() / "ROCMFPX" / "build-strix-rocmfp4" / "bin" / "llama-server"
        if legacy.exists():
            return legacy

        # 4. Relatif projet
        local = Path(__file__).parent.parent.parent / "build-strix-rocmfp4" / "bin" / "llama-server"
        if local.exists():
            return local

        return None

    def _find_in_profile(self, profile_id: str, binary: str) -> Optional[Path]:
        """Cherche un binaire dans le dossier build d'un profil donné."""
        profiles = self.config.get("rocmfpx_profiles", {})
        info = profiles.get(profile_id, {})
        build_dir = info.get("build_dir", "build-strix-rocmfp4")
        profiles_base = Path.home() / "ROCmFPX-profiles"
        candidate = profiles_base / profile_id / build_dir / "bin" / binary
        if candidate.exists():
            return candidate
        # Legacy
        if profile_id == "charlie-main":
            legacy = Path.home() / "ROCMFPX" / build_dir / "bin" / binary
            if legacy.exists():
                return legacy
        return None

    @property
    def active_profile(self) -> str:
        """Retourne le profil ROCmFPX actif, spécifique au modèle si dispo."""
        model_path = self.config.get("last_model", "")
        return self.config.get_model_setting(model_path, "rocmfpx_active_profile", "charlie-main")

    @property
    def active_profile_label(self) -> str:
        """Label lisible du profil actif."""
        profiles = self.config.get("rocmfpx_profiles", {})
        pid = self.active_profile
        info = profiles.get(pid, {})
        return info.get("label", pid)

    def start(self, model_path: str, mtp_path: str = "", mmproj_path: str = "") -> bool:
        """Démarre le serveur avec le modèle donné."""
        if self.is_running:
            return False

        # Lucebox / DeepSeek V4: détection automatique
        if self.config.is_lucebox_model(model_path):
            return self._start_lucebox(model_path)

        server_bin = self._find_llama_server()
        if not server_bin:
            raise FileNotFoundError(
                "llama-server introuvable. Avez-vous compilé ROCmFPX ?\n"
                "Utilisez l'onglet ROCmFPX ou compilez manuellement."
            )

        args = self.config.build_server_args(model_path, mtp_path, mmproj_path)
        full_args = [str(server_bin)] + args

        log_dir = Path.home() / ".cache" / "rocmfp4-manager" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "llama-server.log"

        self._model_name = Path(model_path).name
        self._log_buffer = []

        env = self.config.build_server_env(server_bin, model_path)

        success = self._proc.start(full_args, log_path=log_file, env=env)
        if success:
            self._start_time = time.time()
            self._running = True
            self._start_monitoring(log_file)
            self._notify("started", {"model": self._model_name, "pid": self.pid})

            # Démarrer l'adaptateur Responses API (toujours actif, coexiste avec Chat Completions)
            threading.Timer(2.0, self.start_adapter).start()

        return success

    def _start_monitoring(self, log_file: Path):
        """Thread de monitoring des logs (lecture PIPE stdout) et extraction des métriques.

        Lit directement le pipe stdout du processus (line-buffered) plutôt que
        le fichier de log, pour éviter les problèmes de block-buffering.
        """

        def monitor():
            token_pattern = re.compile(
                r'(?:tok/s|tokens/s|generation:)', re.IGNORECASE
            )
            stdout = self._proc.stdout
            if stdout is None:
                return  # pas de pipe disponible (processus adopté)

            for line in stdout:
                line = line.strip()
                if line:
                    self._log_buffer.append(line)
                    # Extraire tokens/s
                    if token_pattern.search(line):
                        for word in line.split():
                            try:
                                val = float(word.replace(",", "."))
                                if 0 < val < 1000:
                                    self._tokens_per_sec = val
                            except ValueError:
                                pass
                    self._notify("log", line)

                if not self._running and not self._proc.is_running:
                    break

            # Processus terminé
            if self._running:
                self._running = False
                self._stop_adapter()
                self._notify("stopped", None)

        self._monitor_thread = threading.Thread(target=monitor, daemon=True)
        self._monitor_thread.start()

    def stop(self):
        """Arrête le serveur et l'adaptateur Responses."""
        self._running = False
        self._stop_adapter()
        self._proc.stop()
        self._notify("stopped", None)

    def restart(self, model_path: str = "", mtp_path: str = "", mmproj_path: str = ""):
        """Redémarre le serveur."""
        self.stop()
        time.sleep(1)
        if model_path:
            self.start(model_path, mtp_path, mmproj_path)

    def get_uptime_str(self) -> str:
        """Retourne l'uptime formaté."""
        secs = self.uptime_seconds
        h, r = divmod(int(secs), 3600)
        m, s = divmod(r, 60)
        if h > 0:
            return f"{h}h {m}m"
        return f"{m}m {s}s"

    # ------------------------------------------------------------------
    # Lucebox / dflash_server (DeepSeek V4)
    # ------------------------------------------------------------------

    def _find_dflash_server(self) -> Optional[Path]:
        """Cherche le binaire dflash_server."""
        paths = [
            Path.home() / "lucebox" / "server" / "build-hip" / "dflash_server",
        ]
        for p in paths:
            if p.exists():
                return p
        # Dans le PATH
        which = subprocess.run(["which", "dflash_server"], capture_output=True, text=True)
        if which.returncode == 0:
            return Path(which.stdout.strip())
        return None

    def _start_lucebox(self, model_path: str) -> bool:
        """Démarre dflash_server pour DeepSeek V4."""
        server_bin = self._find_dflash_server()
        if not server_bin:
            raise FileNotFoundError(
                "dflash_server introuvable. Installez Lucebox :\n"
                "git clone https://github.com/Luce-Org/lucebox.git ~/lucebox"
            )

        args = self.config.build_lucebox_args(model_path)
        full_args = [str(server_bin)] + args

        log_dir = Path.home() / ".cache" / "rocmfp4-manager" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "llama-server.log"

        self._model_name = Path(model_path).name
        self._log_buffer = []

        env = os.environ.copy()
        g = lambda k, d: self.config.get_model_setting(model_path, k, d)
        if g("env_hsa_override_gfx", True):
            env["HSA_OVERRIDE_GFX_VERSION"] = "11.5.1"
        if g("env_unified_memory", True):
            env["GGML_HIP_ENABLE_UNIFIED_MEMORY"] = "1"
        # Lucebox DSpark env vars
        env["DFLASH_DS4_SPEC"] = "1"
        env["DFLASH_DS4_FUSED_VERIFY"] = "1"
        env["DFLASH_DS4_SPEC_Q"] = str(self.config.get("ds4_spec_q", 4))
        env["LUCE_MMVQ_MAX_NCOLS"] = "4"

        draft = self.config.get("last_draft_model", "")
        if draft:
            env["DFLASH_DS4_DRAFT"] = draft

        success = self._proc.start(full_args, log_path=log_file, env=env)
        if success:
            self._start_time = time.time()
            self._running = True
            self._start_monitoring(log_file)
            self._notify("started", {"model": self._model_name, "pid": self.pid})

            # Démarrer l'adaptateur Responses API pour Lucebox aussi
            threading.Timer(2.0, self.start_adapter).start()

        return success

    # ------------------------------------------------------------------
    # Adaptateur Responses API
    # ------------------------------------------------------------------

    def start_adapter(self):
        """Démarre l'adaptateur Responses API (proxy vers Chat Completions)."""
        # Toujours tuer l'ancien adaptateur d'abord (évite les zombies)
        self._stop_adapter()

        api_key = self.config.get("api_key", "") if self.config.get("api_key_enabled", False) else ""
        # Utiliser le host de la config pour l'adaptateur aussi
        host = self.config.get("host", "127.0.0.1")
        self._adapter = ResponsesAdapter(
            chat_url=self.config.api_chat_url,
            api_key=api_key,
            port=self._adapter_port,
            host=host,
        )
        self._adapter.start()
        self._notify("adapter_started", {"port": self._adapter_port})

    def _stop_adapter(self):
        """Arrête l'adaptateur Responses API."""
        if self._adapter and self._adapter.is_running:
            self._adapter.stop()
            self._adapter = None
            self._notify("adapter_stopped", None)
