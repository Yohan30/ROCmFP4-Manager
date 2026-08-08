"""Utilitaires de gestion des processus."""

import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

# Fichier PID partagé entre les instances pour suivre le serveur en cours
PID_FILE = Path.home() / ".cache" / "rocmfp4-manager" / "server.pid"


class ProcessManager:
    """Gère le cycle de vie d'un processus externe."""

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._log_file: Optional[Path] = None
        self._writer_thread: Optional[threading.Thread] = None
        # Nettoyer un éventuel ancien serveur orphelin
        self._cleanup_orphan()

    @property
    def is_running(self) -> bool:
        if self._process is None:
            return False
        return self._process.poll() is None

    @property
    def pid(self) -> Optional[int]:
        if self._process and self.is_running:
            return self._process.pid
        return None

    def adopt(self, pid: int) -> bool:
        """Adopte un processus existant (déjà en cours) pour le suivre.

        Permet à l'UI de surveiller un llama-server lancé indépendamment."""
        try:
            # Vérifier que le processus existe
            os.kill(pid, 0)
            # Créer un objet Popen fictif pour les métriques
            proc_path = Path(f"/proc/{pid}")
            if not proc_path.exists():
                return False

            class FakeProcess:
                _adopted = True
                def __init__(self, pid):
                    self.pid = pid
                    self.returncode = None
                def poll(self):
                    try:
                        os.kill(self.pid, 0)
                        return None
                    except ProcessLookupError:
                        return 0
                def wait(self, timeout=None):
                    try:
                        os.kill(self.pid, 0)
                        time.sleep(timeout or 1)
                        return None
                    except ProcessLookupError:
                        return 0

            self._process = FakeProcess(pid)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    def _cleanup_orphan(self):
        """Tue un éventuel ancien serveur orphelin (PID stocké)."""
        if PID_FILE.exists():
            try:
                old_pid = int(PID_FILE.read_text().strip())
                # Vérifier si c'est bien un llama-server
                try:
                    with open(f"/proc/{old_pid}/cmdline") as f:
                        cmd = f.read()
                    if "llama-server" in cmd:
                        os.kill(old_pid, signal.SIGTERM)
                        # Attendre un peu
                        for _ in range(5):
                            try:
                                os.kill(old_pid, 0)
                                time.sleep(0.5)
                            except ProcessLookupError:
                                break
                        else:
                            os.kill(old_pid, signal.SIGKILL)
                except (FileNotFoundError, ProcessLookupError, OSError):
                    pass
            except (ValueError, OSError):
                pass
            finally:
                try:
                    PID_FILE.unlink(missing_ok=True)
                except OSError:
                    pass

    def start(self, args: list, cwd: Optional[Path] = None,
              log_path: Optional[Path] = None, env: Optional[dict] = None) -> bool:
        """Démarre un processus avec les arguments donnés."""
        if self.is_running:
            return False

        self._log_file = log_path

        # Toujours utiliser PIPE pour stdout afin d'éviter le block-buffering
        # qui empêcherait la lecture des logs en temps réel quand stdout
        # est redirigé vers un fichier (comportement par défaut de la libc).
        stdout = subprocess.PIPE
        stderr = subprocess.STDOUT  # fusionner stderr dans stdout

        try:
            self._process = subprocess.Popen(
                args,
                stdout=stdout,
                stderr=stderr,
                cwd=str(cwd) if cwd else None,
                env=env,
                text=True,
                bufsize=1,  # line-buffered sur le PIPE
                start_new_session=True,
            )
            # Sauvegarder le PID pour nettoyage inter-instances
            try:
                PID_FILE.parent.mkdir(parents=True, exist_ok=True)
                PID_FILE.write_text(str(self._process.pid))
            except OSError:
                pass

            # Thread écrivain : lit le PIPE ligne par ligne et écrit
            # dans le fichier de log avec flush immédiat (si log_path).
            if log_path:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                self._start_pipe_writer(log_path)

            return True
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"Exécutable introuvable : {args[0] if args else '?'}"
            ) from e

    def stop(self, timeout: int = 5):
        """Arrête le processus et tout son groupe (SIGTERM puis SIGKILL si timeout)."""
        if not self._process or not self.is_running:
            self._process = None
            return

        pid = self._process.pid
        # Ne pas tuer un processus adopté (lancé en externe)
        if getattr(self._process, '_adopted', False):
            self._process = None
            return

        pgid = pid
        try:
            pgid = os.getpgid(pid)
        except ProcessLookupError:
            self._process = None
            return
        try:
            # Tuer tout le groupe de processus (négatif = groupe en Unix)
            os.kill(-pgid, signal.SIGTERM)
            self._process.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, OSError):
            try:
                os.kill(-pgid, signal.SIGKILL)
                self._process.wait(timeout=2)
            except (subprocess.TimeoutExpired, OSError):
                pass

        self._process = None
        self._writer_thread = None
        # Nettoyer le fichier PID
        try:
            PID_FILE.unlink(missing_ok=True)
        except OSError:
            pass

    @property
    def stdout(self):
        """Retourne le pipe stdout du processus (None si pas démarré ou adopté)."""
        if self._process and not getattr(self._process, '_adopted', False):
            return self._process.stdout
        return None

    def _start_pipe_writer(self, log_path: Path):
        """Démarre un thread daemon qui lit le PIPE stdout et écrit dans
        le fichier de log avec flush immédiat à chaque ligne.

        Ceci résout le problème de block-buffering : quand stdout est un
        fichier (pas un terminal), la libc bufferise par blocs de 4-8 Ko.
        En passant par un PIPE (line-buffered) puis en flushant dans le
        fichier, les logs sont visibles en temps réel.
        """
        def _writer():
            try:
                with open(log_path, "a", buffering=1) as log_f:
                    for line in self._process.stdout:
                        log_f.write(line)
                        log_f.flush()
            except (ValueError, OSError):
                pass  # pipe fermé, processus terminé

        self._writer_thread = threading.Thread(target=_writer, daemon=True)
        self._writer_thread.start()

    def read_output(self) -> str:
        """Lit la sortie capturée (mode PIPE uniquement)."""
        if not self._process:
            return ""
        output = ""
        if self._process.stdout and not self._process.stdout.closed:
            try:
                output = self._process.stdout.read()
            except ValueError:
                pass
        return output

    def get_memory_mb(self) -> Optional[float]:
        """Lit la mémoire RSS du processus depuis /proc."""
        pid = self.pid
        if pid is None:
            return None
        try:
            with open(f"/proc/{pid}/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        # "VmRSS: 12345 kB"
                        parts = line.split()
                        if len(parts) >= 2:
                            return int(parts[1]) / 1024
        except (FileNotFoundError, IOError, ValueError):
            pass
        return None
