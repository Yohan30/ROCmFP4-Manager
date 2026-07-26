"""Gestion du clonage, build et mise à jour de ROCmFPX."""

import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional, Callable

REPO_URL = "https://github.com/charlie12345/ROCmFPX.git"
STRIX_BUILD_SCRIPT = "scripts/build-strix-rocmfp4-mtp.sh"

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
    """Clone, build et met à jour le fork ROCmFPX de llama.cpp."""

    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or Path.home() / "ROCMFPX"
        self._listeners: list[Callable] = []
        self._current_commit: str = ""
        self._remote_commit: str = ""

    def add_listener(self, callback: Callable):
        self._listeners.append(callback)

    def _notify(self, event: str, data=None):
        for cb in self._listeners:
            try:
                cb(event, data)
            except Exception:
                pass

    @property
    def is_installed(self) -> bool:
        git_dir = self.base_path / ".git"
        return git_dir.exists()

    @property
    def build_path(self) -> Path:
        return self.base_path / "build-strix-rocmfp4" / "bin"

    @property
    def llama_server_path(self) -> Optional[Path]:
        p = self.build_path / "llama-server"
        return p if p.exists() else None

    @property
    def llama_bench_path(self) -> Optional[Path]:
        p = self.build_path / "llama-bench"
        return p if p.exists() else None

    def clone(self):
        """Clone le dépôt ROCmFPX."""
        def task():
            self._notify("clone_start", None)
            try:
                subprocess.run(
                    ["git", "clone", REPO_URL, str(self.base_path)],
                    check=True, capture_output=True, text=True
                )
                subprocess.run(
                    ["git", "checkout", "main"],
                    cwd=self.base_path, check=True, capture_output=True
                )
                self._current_commit = self._get_current_commit()
                self._notify("clone_done", {"commit": self._current_commit})
            except subprocess.CalledProcessError as e:
                self._notify("error", {"message": str(e.stderr or e.stdout)})

        threading.Thread(target=task, daemon=True).start()

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

    def build(self):
        """Vérifie les dépendances puis lance la compilation pour Strix Halo."""
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

                script_path = self.base_path / STRIX_BUILD_SCRIPT
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
        try:
            # Fetch
            subprocess.run(
                ["git", "fetch", "origin"],
                cwd=self.base_path, check=True, capture_output=True, timeout=30
            )
            self._current_commit = self._get_current_commit()
            self._remote_commit = self._get_remote_commit()
            return self._current_commit != self._remote_commit
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    def update(self):
        """Pull + rebuild."""
        def task():
            self._notify("update_start", None)
            try:
                subprocess.run(
                    ["git", "pull", "origin", "main"],
                    cwd=self.base_path, check=True, capture_output=True, timeout=60
                )
                new_commit = self._get_current_commit()
                self._notify("update_pulled", {"old": self._current_commit, "new": new_commit})
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

    def _get_remote_commit(self) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "origin/main"],
                cwd=self.base_path, capture_output=True, text=True, check=True
            )
            return result.stdout.strip()[:12]
        except subprocess.CalledProcessError:
            return ""
