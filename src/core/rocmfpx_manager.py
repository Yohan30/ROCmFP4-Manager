"""Gestion du clonage, build et mise à jour de ROCmFPX (multi-profils)."""

import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional, Callable

# --- Profils prédéfinis ---
DEFAULT_PROFILES = {
    "charlie-main": {
        "repo_url": "https://github.com/charlie12345/ROCmFPX.git",
        "branch": "main",
        "build_script": "scripts/build-strix-rocmfp4-mtp.sh",
        "build_dir": "build-strix-rocmfp4",
        "label": "ROCmFPX Standard (charlie12345)",
    },
    "ciru-dualview": {
        "repo_url": "https://github.com/ciru-ai/ROCmFPX.git",
        "branch": "agent/laguna-radv-device-lost-20260724",
        "build_script": "scripts/build-laguna-strix-vulkan.sh",
        "build_dir": "build-laguna-strix-vulkan",
        "label": "CIRU Laguna V2",
    },
    "rocmfpx-v2": {
        "repo_url": "https://github.com/charlie12345/ROCmFPX.git",
        # Branche locale portant les correctifs DFlash Laguna non mergés en amont
        # (PRs #47 laguna::t_layer_inp et #48 dflash::aux_norm + attn_gate).
        # Ne PAS lancer "Update" sur ce profil : reset --hard ramènerait le
        # code au main upstream et effacerait les correctifs.
        "branch": "laguna-dflash-fixes",
        "build_script": "scripts/build-strix-rocmfp4-mtp.sh",
        "build_dir": "build-strix-rocmfp4",
        "label": "ROCmFPX v2 (Laguna DFlash fixes)",
    },
}

# Répertoire parent pour tous les profils
PROFILES_BASE = Path.home() / "ROCmFPX-profiles"

# Dépendances nécessaires à la compilation selon le gestionnaire de paquets
DEPENDENCIES = {
    "dnf": {
        "packages": [
            "cmake", "gcc-c++", "make",
            "vulkan-headers", "vulkan-loader-devel", "glslc", "spirv-headers-devel",
            "rocm-hip", "rocm-hip-devel", "hipcc",
            "hipblas-devel", "rocblas-devel",
            "rocprim-devel", "rocrand-devel",
            "rocthrust-devel", "rocsolver-devel",
            "mesa-vulkan-drivers",
        ],
        "install_cmd": ["sudo", "dnf", "install", "-y"],
    },
    "apt": {
        "packages": [
            "cmake", "g++", "make",
            "libvulkan-dev", "vulkan-headers",
            "mesa-vulkan-drivers",
        ],
        "install_cmd": ["sudo", "apt-get", "install", "-y"],
    },
}


class ROCmFPXManager:
    """Clone, build et met à jour une version de ROCmFPX selon un profil.
    
    Supporte plusieurs profils (ex: charlie-main, ciru-dualview).
    Un seul profil est actif à la fois. Chaque profil vit dans son
    propre sous-dossier de ~/ROCmFPX-profiles/.
    """

    def __init__(self, config=None):
        """config: instance de Config (optionnelle, pour lire les profils)."""
        self._config = config
        self._listeners: list[Callable] = []
        self._current_commit: str = ""
        self._remote_commit: str = ""
        self._active_profile: str = ""

        # Déterminer le profil actif
        if config:
            self._active_profile = config.get("rocmfpx_active_profile", "charlie-main")
        else:
            self._active_profile = "charlie-main"

        # Compatibilité ascendante : si l'ancien chemin ~/ROCMFPX existe, 
        # migrer automatiquement vers le profil charlie-main
        self._migrate_legacy_path()

    # ------------------------------------------------------------------
    # Gestion des profils
    # ------------------------------------------------------------------

    @property
    def profiles(self) -> dict:
        """Retourne le dictionnaire des profils (fusion defaults + config)."""
        if self._config:
            stored = self._config.get("rocmfpx_profiles", {})
            # Fusion: les profils stockés écrasent les défauts
            merged = {**DEFAULT_PROFILES, **stored}
            return merged
        return dict(DEFAULT_PROFILES)

    @property
    def active_profile(self) -> str:
        # Toujours lire depuis la config si disponible (synchro avec ServerTab)
        if self._config:
            return self._config.get("rocmfpx_active_profile", self._active_profile or "charlie-main")
        return self._active_profile or "charlie-main"

    def set_active_profile(self, profile_id: str):
        """Change le profil actif et sauvegarde."""
        if profile_id not in self.profiles:
            raise ValueError(f"Unknown profile: {profile_id}")
        self._active_profile = profile_id
        if self._config:
            self._config.set("rocmfpx_active_profile", profile_id)
            self._config.save()
        # Réinitialiser les commits
        self._current_commit = ""
        self._remote_commit = ""

    def get_profile(self, profile_id: str = None) -> dict:
        """Retourne les infos d'un profil (ou du profil actif)."""
        pid = profile_id or self._active_profile
        return self.profiles.get(pid, {})

    @property
    def base_path(self) -> Path:
        """Chemin racine du profil actif."""
        # Compatibilité ascendante: si ~/ROCMFPX existe et qu'on est sur charlie-main
        legacy = Path.home() / "ROCMFPX"
        if self._active_profile == "charlie-main" and legacy.exists():
            return legacy
        return PROFILES_BASE / self._active_profile

    @property
    def build_path(self) -> Path:
        profile = self.get_profile()
        build_dir = profile.get("build_dir", "build-strix-rocmfp4")
        return self.base_path / build_dir / "bin"

    @property
    def llama_server_path(self) -> Optional[Path]:
        """Cherche llama-server dans le profil actif uniquement."""
        p = self.build_path / "llama-server"
        if p.exists():
            return p
        return None

    @property
    def llama_bench_path(self) -> Optional[Path]:
        """Cherche llama-bench dans le profil actif uniquement."""
        p = self.build_path / "llama-bench"
        if p.exists():
            return p
        return None

    def _migrate_legacy_path(self):
        """Détecte l'ancien ~/ROCMFPX (sans profils) et l'associe à charlie-main."""
        legacy = Path.home() / "ROCMFPX"
        profile_dir = PROFILES_BASE / "charlie-main"
        if legacy.exists() and not profile_dir.exists():
            # Créer un lien symbolique pour que le nouveau chemin pointe vers l'ancien
            PROFILES_BASE.mkdir(parents=True, exist_ok=True)
            try:
                profile_dir.symlink_to(legacy)
            except OSError:
                pass  # Pas grave si le symlink échoue, on utilisera legacy directement

    # ------------------------------------------------------------------
    # Propriétés de statut
    # ------------------------------------------------------------------

    @property
    def is_installed(self) -> bool:
        git_dir = self.base_path / ".git"
        return git_dir.exists()

    @property
    def label(self) -> str:
        return self.get_profile().get("label", self._active_profile)

    def add_listener(self, callback: Callable):
        self._listeners.append(callback)

    def _notify(self, event: str, data=None):
        for cb in self._listeners:
            try:
                cb(event, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Clonage
    # ------------------------------------------------------------------

    def clone(self):
        """Clone le dépôt ROCmFPX pour le profil actif."""
        profile = self.get_profile()
        repo_url = profile.get("repo_url", "")
        branch = profile.get("branch", "main")

        def task():
            self._notify("clone_start", None)
            try:
                self.base_path.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    ["git", "clone", "--branch", branch, repo_url, str(self.base_path)],
                    check=True, capture_output=True, text=True
                )
                self._current_commit = self._get_current_commit()
                self._notify("clone_done", {"commit": self._current_commit})
            except subprocess.CalledProcessError as e:
                self._notify("error", {"message": str(e.stderr or e.stdout)})

        threading.Thread(target=task, daemon=True).start()

    # ------------------------------------------------------------------
    # Dépendances
    # ------------------------------------------------------------------

    def _detect_package_manager(self) -> Optional[str]:
        """Détecte le gestionnaire de paquets disponible."""
        for pm in DEPENDENCIES:
            if shutil.which(pm):
                return pm
        return None

    def check_dependencies(self) -> list[str]:
        """Vérifie les dépendences et retourne la liste des paquets manquants."""
        pm = self._detect_package_manager()
        if not pm:
            return ["unknown_package_manager"]

        missing = []
        for pkg in DEPENDENCIES[pm]["packages"]:
            # Vérification simple via which ou rpm
            if pkg.startswith("rocm") or pkg.startswith("hip"):
                # Paquets spéciaux via rpm -q
                result = subprocess.run(
                    ["rpm", "-q", pkg], capture_output=True, text=True
                )
                if result.returncode != 0:
                    missing.append(pkg)
            elif pkg == "mesa-vulkan-drivers":
                result = subprocess.run(
                    ["rpm", "-q", pkg], capture_output=True, text=True
                )
                if result.returncode != 0:
                    missing.append(pkg)
            else:
                if not shutil.which(pkg.replace("-c++", "").replace("-dev", "").split("-")[0]):
                    # Vérification plus poussée pour cmake, g++, etc.
                    check = pkg.replace("gcc-c++", "g++").replace("g++", "g++")
                    if pkg == "vulkan-headers":
                        result = subprocess.run(
                            ["rpm", "-q", "vulkan-headers"], capture_output=True, text=True
                        )
                        if result.returncode != 0:
                            missing.append(pkg)
                    elif pkg == "vulkan-loader-devel":
                        result = subprocess.run(
                            ["rpm", "-q", "vulkan-loader-devel"], capture_output=True, text=True
                        )
                        if result.returncode != 0:
                            missing.append(pkg)
                    elif not shutil.which(check.split("-")[0]) \
                         and not shutil.which(pkg.split("-")[0].replace("++", "+")):
                        missing.append(pkg)

        return missing

    def install_dependencies(self) -> bool:
        """Installe les dépendances manquantes automatiquement."""
        pm = self._detect_package_manager()
        if not pm:
            self._notify("error", {"message": "Could not detect package manager."})
            return False

        missing = self.check_dependencies()
        if not missing:
            return True

        install_cmd = DEPENDENCIES[pm]["install_cmd"] + missing
        self._notify("deps_install_start", {"packages": missing})

        try:
            result = subprocess.run(
                install_cmd,
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                self._notify("deps_install_done", None)
                return True
            else:
                self._notify("error", {
                    "message": f"Installation des dépendances échouée:\n{result.stderr}"
                })
                return False
        except (subprocess.TimeoutExpired, Exception) as e:
            self._notify("error", {"message": f"Installation des dépendances: {e}"})
            return False

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self):
        """Vérifie les dépendances puis lance la compilation pour le profil actif."""
        profile = self.get_profile()
        build_script = profile.get("build_script", "scripts/build-strix-rocmfp4-mtp.sh")

        def task():
            self._notify("build_start", None)

            # 1. Vérifier et installer les dépendances
            self._notify("build_log", "🔍 Vérification des dépendances...")
            deps_ok = self.install_dependencies()
            if not deps_ok:
                self._notify("error", {
                    "message": "Some dependencies are missing.\n"
                               "Install them manually:\n"
                               "sudo dnf install cmake gcc-c++ make vulkan-headers vulkan-loader-devel"
                })
                return

            try:
                env = os.environ.copy()
                env["JOBS"] = str(os.cpu_count() or 16)

                script_path = self.base_path / build_script
                if not script_path.exists():
                    self._notify("error", {"message": f"Script introuvable: {script_path}"})
                    return

                self._notify("build_log", "▶️ Lancement de cmake...")
                process = subprocess.Popen(
                    ["bash", str(script_path)],
                    cwd=self.base_path,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )

                for line in process.stdout:
                    line = line.strip()
                    if line:
                        self._notify("build_log", line)

                process.wait()
                if process.returncode == 0:
                    self._notify("build_done", None)
                else:
                    self._notify("error", {
                    "message": f"Build failed (code {process.returncode}).\n"
                               "Check the logs above for details."
                    })
            except Exception as e:
                self._notify("error", {"message": str(e)})

        threading.Thread(target=task, daemon=True).start()

    def check_update(self) -> bool:
        """Vérifie si une mise à jour est disponible. Retourne True si oui."""
        if not self.is_installed:
            return False
        branch = self.get_profile().get("branch", "main")
        try:
            # Fetch ciblé sur la ref configurée (branche ou tag)
            subprocess.run(
                ["git", "fetch", "origin", branch],
                cwd=self.base_path, check=True, capture_output=True, timeout=30
            )
            self._current_commit = self._get_current_commit()
            self._remote_commit = self._get_remote_commit(branch)
            return self._current_commit != self._remote_commit
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    def update(self):
        """Fetch + reset + rebuild pour le profil actif.
        
        Utilise git fetch + reset --hard FETCH_HEAD au lieu de git pull,
        ce qui évite les problèmes de merge et fonctionne avec les tags.
        """
        branch = self.get_profile().get("branch", "main")

        def task():
            self._notify("update_start", None)
            old_commit = self._get_current_commit()
            try:
                # Fetch uniquement la ref cible
                subprocess.run(
                    ["git", "fetch", "origin", branch],
                    cwd=self.base_path, check=True, capture_output=True, timeout=60
                )
                # Reset dur sur FETCH_HEAD (marche pour branches ET tags)
                subprocess.run(
                    ["git", "reset", "--hard", "FETCH_HEAD"],
                    cwd=self.base_path, check=True, capture_output=True, timeout=30
                )
                new_commit = self._get_current_commit()
                self._notify("update_pulled", {"old": old_commit, "new": new_commit})
                self._current_commit = new_commit
                self.build()
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                self._notify("error", {"message": f"Update failed: {e}"})

        threading.Thread(target=task, daemon=True).start()

    def get_changelog(self) -> str:
        """Retourne les logs des commits récents."""
        if not self.is_installed:
            return ""
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-20"],
                cwd=self.base_path, capture_output=True, text=True, check=True
            )
            return result.stdout
        except subprocess.CalledProcessError:
            return ""

    def _get_current_commit(self) -> str:
        if not self.is_installed:
            return ""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.base_path, capture_output=True, text=True, check=True
            )
            return result.stdout.strip()[:12]
        except subprocess.CalledProcessError:
            return ""

    def _get_remote_commit(self, branch: str = "main") -> str:
        """Résout le commit distant pour une branche ou un tag."""
        # Essayer d'abord comme branche (origin/<name>)
        try:
            result = subprocess.run(
                ["git", "rev-parse", f"origin/{branch}"],
                cwd=self.base_path, capture_output=True, text=True, check=True
            )
            return result.stdout.strip()[:12]
        except subprocess.CalledProcessError:
            pass
        # Fallback: tag ou ref directe
        try:
            result = subprocess.run(
                ["git", "rev-parse", f"refs/tags/{branch}"],
                cwd=self.base_path, capture_output=True, text=True, check=True
            )
            return result.stdout.strip()[:12]
        except subprocess.CalledProcessError:
            return ""
