"""Gestion des modèles GGUF : téléchargement, liste, import LM Studio."""

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import List, Dict, Optional, Callable

import requests


class DownloadTask:
    """Représente un téléchargement avec contrôle pause/resume/cancel."""

    def __init__(self, repo_id: str, filename: str, dest_dir: Path,
                 listeners: list[Callable], token: str = ""):
        self.repo_id = repo_id
        self.filename = filename
        self.dest_path = dest_dir / filename
        self.temp_path = dest_dir / (filename + ".part")
        self.token = token
        self._listeners = listeners
        self._paused = threading.Event()
        self._cancelled = threading.Event()
        self._paused.set()  # Not paused initially
        self._downloaded = 0
        self._total = 0
        self._thread: Optional[threading.Thread] = None

    def _notify(self, event: str, data=None):
        for cb in self._listeners:
            try:
                cb(event, data)
            except Exception:
                pass

    def pause(self):
        self._paused.clear()
        self._notify("download_paused", {"name": self.filename})

    def resume(self):
        self._paused.set()
        self._notify("download_resumed", {"name": self.filename})

    @property
    def is_paused(self) -> bool:
        return not self._paused.is_set()

    def cancel(self):
        self._cancelled.set()
        self._paused.set()  # Débloquer si en pause
        self._notify("download_cancelled", {"name": self.filename})

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        # Créer le dossier de destination si nécessaire
        self.dest_path.parent.mkdir(parents=True, exist_ok=True)

        self._notify("download_start", {
            "name": self.filename, "repo": self.repo_id,
            "task": id(self),
        })

        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        # Reprendre un téléchargement partiel
        resume_size = 0
        if self.temp_path.exists():
            resume_size = self.temp_path.stat().st_size
            headers["Range"] = f"bytes={resume_size}-"

        url = f"https://huggingface.co/{self.repo_id}/resolve/main/{self.filename}"

        try:
            # HEAD pour taille totale
            resp = requests.head(url, headers=headers, allow_redirects=True, timeout=15)
            if resp.status_code == 200:
                self._total = int(resp.headers.get("Content-Length", 0))

            # GET avec reprise
            resp = requests.get(url, headers=headers, stream=True, timeout=30)

            mode = "ab" if resume_size > 0 else "wb"
            self._downloaded = resume_size
            last_notify = 0

            with open(self.temp_path, mode) as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if self._cancelled.is_set():
                        self._notify("download_cancelled", {"name": self.filename, "task": id(self)})
                        return

                    # Pause
                    self._paused.wait()

                    if chunk:
                        f.write(chunk)
                        self._downloaded += len(chunk)

                        # Notifier max toutes les 0.3s
                        now = time.time()
                        if now - last_notify > 0.3:
                            last_notify = now
                            pct = (self._downloaded / self._total * 100) if self._total > 0 else 0
                            self._notify("download_progress", {
                                "name": self.filename,
                                "downloaded": self._downloaded,
                                "total": self._total,
                                "percent": pct,
                                "task": id(self),
                            })

            # Renommer .part → fichier final
            if not self._cancelled.is_set():
                self.temp_path.rename(self.dest_path)
                self._notify("download_done", {
                    "name": self.filename,
                    "path": str(self.dest_path),
                    "task": id(self),
                })

        except requests.Timeout:
            self._notify("download_error", {
                "name": self.filename,
                "error": "Connection timeout. The download will resume when you retry.",
                "task": id(self),
            })
        except requests.RequestException as e:
            import traceback
            err = f"{e}\n{traceback.format_exc()}"
            if not self._cancelled.is_set():
                self._notify("download_error", {
                    "name": self.filename, "error": err,
                    "task": id(self),
                })
        except Exception as e:
            import traceback
            err = f"{e}\n{traceback.format_exc()}"
            if not self._cancelled.is_set():
                self._notify("download_error", {
                    "name": self.filename, "error": err,
                    "task": id(self),
                })


class ModelManager:
    """Gère les modèles GGUF : scan, téléchargement, suppression, import."""

    def __init__(self, models_path: Path):
        self.models_path = models_path
        self.models_path.mkdir(parents=True, exist_ok=True)
        self._listeners: list[Callable] = []

    def add_listener(self, callback: Callable):
        self._listeners.append(callback)

    def _notify(self, event: str, data=None):
        for cb in self._listeners:
            try:
                cb(event, data)
            except Exception:
                pass

    @staticmethod
    def _is_multi_part(filename: str) -> bool:
        """Détecte si un fichier fait partie d'un modèle multi-parties (ex: *-00001-of-00003.gguf)."""
        import re
        return bool(re.search(r"-\d{5}-of-\d{5}\.gguf$", filename))

    @staticmethod
    def _get_multi_part_base(filename: str) -> str:
        """Extrait le nom de base d'un fichier multi-parties (sans le suffixe -XXXXX-of-YYYYY)."""
        import re
        return re.sub(r"-\d{5}-of-\d{5}(\.gguf)$", r"\1", filename)

    def scan_models(self) -> List[Dict]:
        """Scanne le dossier des modèles et retourne la liste des GGUFs.

        Les modèles multi-parties (ex: *-00001-of-00003.gguf) sont automatiquement
        groupés en une seule entrée. Les fichiers MTP, mmproj (vision) et les
        singles GGUFs restent individuels.
        """
        raw_files = []
        if not self.models_path.exists():
            return raw_files

        # 1. Collecter tous les .gguf bruts
        for entry in sorted(self.models_path.iterdir()):
            if entry.is_dir():
                group = entry.name
                for f in sorted(entry.iterdir()):
                    if f.suffix == ".gguf":
                        raw_files.append(f)
            elif entry.suffix == ".gguf":
                raw_files.append(entry)

        # 2. Séparer les multi-parties du reste
        multi_part_groups: Dict[str, list] = {}  # base_name -> [files]
        standalone = []  # fichiers seuls (MTP, mmproj, singles)

        for f in raw_files:
            if self._is_multi_part(f.name):
                base = self._get_multi_part_base(f.name)
                if base not in multi_part_groups:
                    multi_part_groups[base] = []
                multi_part_groups[base].append(f)
            else:
                standalone.append(f)

        # 3. Grouper les multi-parties
        models = []
        for base_name, files in sorted(multi_part_groups.items()):
            files.sort()
            total_size = sum(f.stat().st_size for f in files)
            first_part = files[0]
            # Le chemin principal = premier fichier (llama-server détecte les autres)
            main_path = str(first_part)
            group = first_part.parent.name

            # Compter les fichiers mmproj et MTP dans le même dossier
            # pour les détecter comme compagnons
            is_mtp = "MTP" in base_name.upper()

            models.append({
                "name": base_name,
                "path": main_path,
                "size_gb": round(total_size / (1024 ** 3), 2),
                "is_mtp": is_mtp,
                "group": group,
                "is_multi_part": True,
                "part_count": len(files),
                "parts": [str(f) for f in files],
                "has_mmproj": any("mmproj" in f.name.lower() for f in standalone if f.parent == first_part.parent),
                "has_mtp": any("MTP" in f.name for f in standalone if f.parent == first_part.parent),
            })

        # 4. Ajouter les fichiers seuls (MTP, mmproj, singles)
        for f in standalone:
            size_gb = f.stat().st_size / (1024 ** 3)
            group = f.parent.name
            name = f.name
            is_mtp = "MTP" in name.upper()
            is_mmproj = "mmproj" in name.lower()

            models.append({
                "name": name,
                "path": str(f),
                "size_gb": round(size_gb, 2),
                "is_mtp": is_mtp,
                "is_mmproj": is_mmproj,
                "group": group,
                "is_multi_part": False,
                "part_count": 1,
                "parts": [str(f)],
                "has_mmproj": False,
                "has_mtp": False,
            })

        return models

    def scan_lmstudio(self, lmstudio_path: Optional[Path] = None) -> List[Dict]:
        """Scanne le dossier LM Studio et retourne les modèles trouvés."""
        if lmstudio_path is None:
            lmstudio_path = Path.home() / ".lmstudio" / "models"

        models = []
        if not lmstudio_path.exists():
            return models

        for f in lmstudio_path.rglob("*.gguf"):
            size_gb = f.stat().st_size / (1024 ** 3)
            models.append({
                "name": f.name,
                "path": str(f),
                "size_gb": round(size_gb, 2),
                "source": "lmstudio",
            })
        return models

    def import_from_lmstudio(self, source_path: str, use_symlink: bool = False) -> bool:
        """Importe un modèle depuis LM Studio (copie ou lien symbolique)."""
        src = Path(source_path)
        if not src.exists():
            return False

        dst = self.models_path / src.name

        if use_symlink:
            try:
                if dst.exists():
                    dst.unlink()
                dst.symlink_to(src)
                self._notify("imported", {"name": src.name, "type": "symlink"})
                return True
            except OSError:
                return False
        else:
            try:
                shutil.copy2(src, dst)
                self._notify("imported", {"name": src.name, "type": "copy"})
                return True
            except (OSError, shutil.Error):
                return False

    _active_downloads: Dict[int, DownloadTask] = {}

    def download_model(self, repo_id: str, filename: str,
                       token: Optional[str] = None,
                       subdir: str = "") -> int:
        """Télécharge un modèle avec pause/resume/cancel. Retourne l'ID de la tâche."""
        dest_dir = (self.models_path / subdir) if subdir else self.models_path
        dest_dir.mkdir(parents=True, exist_ok=True)
        task = DownloadTask(repo_id, filename, dest_dir,
                           self._listeners, token or "")
        task.start()
        self._active_downloads[id(task)] = task
        return id(task)

    def pause_download(self, task_id: int):
        """Met en pause un téléchargement."""
        task = self._active_downloads.get(task_id)
        if task:
            task.pause()

    def resume_download(self, task_id: int):
        """Reprend un téléchargement en pause."""
        task = self._active_downloads.get(task_id)
        if task:
            task.resume()

    def cancel_download(self, task_id: int):
        """Annule un téléchargement."""
        task = self._active_downloads.get(task_id)
        if task:
            task.cancel()
            # Nettoyer le fichier .part
            if task.temp_path.exists():
                task.temp_path.unlink()

    def delete_model(self, model_path: str, extra_paths: list[str] | None = None) -> bool:
        """Supprime un modèle GGUF (et ses parties supplémentaires si fournies)."""
        paths_to_delete = [model_path] + (extra_paths or [])
        deleted_names = []
        try:
            for p in paths_to_delete:
                path = Path(p)
                if path.exists():
                    if path.is_symlink():
                        path.unlink()
                    else:
                        path.unlink()
                    deleted_names.append(path.name)
            if deleted_names:
                self._notify("deleted", {"names": deleted_names})
            return True
        except OSError:
            return False

    def get_model_size_str(self, size_gb: float) -> str:
        """Formate la taille."""
        if size_gb < 1:
            return f"{size_gb * 1024:.0f} MB"
        return f"{size_gb:.1f} GB"

    def get_available_disk_space(self) -> str:
        """Espace disque disponible dans le dossier des modèles."""
        try:
            usage = shutil.disk_usage(self.models_path)
            free_gb = usage.free / (1024 ** 3)
            return f"{free_gb:.1f} Go"
        except OSError:
            return "?"
