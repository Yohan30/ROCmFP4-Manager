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
        """Retourne les chemins possibles du binaire ROCmFPX llama-server."""
        paths = []

        # Depuis le PATH
        which = subprocess.run(["which", "llama-server"], capture_output=True, text=True)
        if which.returncode == 0:
            paths.append(Path(which.stdout.strip()).resolve())

        # Depuis la config ROCmFPX
        rocmfpx_path = self.config.get("rocmfpx_path", "")
        if rocmfpx_path:
            candidates = [
                Path(rocmfpx_path) / "build-strix-rocmfp4" / "bin" / "llama-server",
                Path(rocmfpx_path) / "build" / "bin" / "llama-server",
            ]
            for c in candidates:
                resolved = c.resolve()
                if resolved.exists():
                    paths.append(resolved)

        # Fallback : chemin relatif au projet
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
        return f"http://127.0.0.1:{self._adapter_port}/v1/responses"

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
        """Cherche le binaire llama-server dans le PATH ou le dossier ROCmFPX."""
        # Dans le PATH
        which = subprocess.run(["which", "llama-server"], capture_output=True, text=True)
        if which.returncode == 0:
            return Path(which.stdout.strip())

        # Dans le dossier ROCmFPX
        rocmfpx_path = self.config.get("rocmfpx_path", "")
        if rocmfpx_path:
            candidates = [
                Path(rocmfpx_path) / "build-strix-rocmfp4" / "bin" / "llama-server",
                Path(rocmfpx_path) / "build" / "bin" / "llama-server",
            ]
            for c in candidates:
                if c.exists():
                    return c

        # Dans le répertoire parent
        local = Path(__file__).parent.parent.parent / "build-strix-rocmfp4" / "bin" / "llama-server"
        if local.exists():
            return local

        return None

    def start(self, model_path: str, mtp_path: str = "", mmproj_path: str = "") -> bool:
        """Démarre le serveur llama-server avec le modèle donné."""
        if self.is_running:
            return False

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

        env = os.environ.copy()
        env["HSA_OVERRIDE_GFX_VERSION"] = "11.5.1"
        env["GGML_HIP_ENABLE_UNIFIED_MEMORY"] = "1"

        success = self._proc.start(full_args, log_path=log_file, env=env)
        if success:
            self._start_time = time.time()
            self._running = True
            self._start_monitoring(log_file)
            self._notify("started", {"model": self._model_name, "pid": self.pid})

            # Démarrer l'adaptateur Responses si le mode est activé
            if self.config.get("api_mode", "chat_completions") == "responses":
                threading.Timer(2.0, self.start_adapter).start()

        return success

    def _start_monitoring(self, log_file: Path):
        """Thread de monitoring des logs et extraction des métriques."""

        def monitor():
            last_size = 0
            token_patterns = ["tok/s", "tokens/s", "generation:"]
            while self._running or self._proc.is_running:
                try:
                    if log_file.exists():
                        current_size = log_file.stat().st_size
                        if current_size > last_size:
                            with open(log_file) as f:
                                f.seek(last_size)
                                new_lines = f.readlines()
                                for line in new_lines:
                                    line = line.strip()
                                    if line:
                                        self._log_buffer.append(line)
                                        # Extraire tokens/s
                                        for pat in token_patterns:
                                            if pat in line.lower():
                                                for word in line.split():
                                                    try:
                                                        val = float(word.replace(",", "."))
                                                        if val > 0 and val < 1000:
                                                            self._tokens_per_sec = val
                                                    except ValueError:
                                                        pass
                                        self._notify("log", line)
                            last_size = current_size
                except (IOError, OSError):
                    pass
                time.sleep(0.2)

                # Vérifier si le processus est mort
                if not self._proc.is_running and self._running:
                    self._running = False
                    self._notify("stopped", None)
                    break

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
    # Adaptateur Responses API
    # ------------------------------------------------------------------

    def start_adapter(self):
        """Démarre l'adaptateur Responses API (proxy vers Chat Completions)."""
        if self._adapter and self._adapter.is_running:
            return

        api_key = self.config.get("api_key", "") if self.config.get("api_key_enabled", False) else ""
        self._adapter = ResponsesAdapter(
            chat_url=self.config.api_chat_url,
            api_key=api_key,
            port=self._adapter_port,
        )
        self._adapter.start()
        self._notify("adapter_started", {"port": self._adapter_port})

    def _stop_adapter(self):
        """Arrête l'adaptateur Responses API."""
        if self._adapter and self._adapter.is_running:
            self._adapter.stop()
            self._adapter = None
            self._notify("adapter_stopped", None)
