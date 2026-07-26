"""Gestion de l'auto-démarrage via systemd (utilisateur)."""

import os
import subprocess
from pathlib import Path
from typing import Optional


SERVICE_NAME = "rocmfp4-manager"
SERVICE_DISPLAY = "ROCmFP4 Manager"

SERVICE_TEMPLATE = """[Unit]
Description={display}
After=network.target

[Service]
ExecStart={python} {entrypoint}
Restart=on-failure
RestartSec=5
Environment=HSA_OVERRIDE_GFX_VERSION=11.5.1
Environment=GGML_HIP_ENABLE_UNIFIED_MEMORY=1

[Install]
WantedBy=default.target
"""

SERVER_SERVICE_TEMPLATE = """[Unit]
Description={display} - llama-server
After={manager_service}.service

[Service]
ExecStart={server_bin} {server_args}
Restart=on-failure
RestartSec=10
Environment=HSA_OVERRIDE_GFX_VERSION=11.5.1
Environment=GGML_HIP_ENABLE_UNIFIED_MEMORY=1

[Install]
WantedBy=default.target
"""


class AutostartManager:
    """Gère les services systemd utilisateur pour ROCmFP4 Manager."""

    def __init__(self):
        self.service_dir = Path.home() / ".config" / "systemd" / "user"
        self.service_dir.mkdir(parents=True, exist_ok=True)

    @property
    def app_service_path(self) -> Path:
        return self.service_dir / f"{SERVICE_NAME}.service"

    @property
    def server_service_path(self) -> Path:
        return self.service_dir / f"{SERVICE_NAME}-server.service"

    def is_app_autostart_enabled(self) -> bool:
        """Vérifie si le service utilisateur est enable."""
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-enabled", SERVICE_NAME],
                capture_output=True, text=True
            )
            return result.stdout.strip() == "enabled"
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def enable_app_autostart(self):
        """Active l'auto-démarrage de l'application."""
        entrypoint = Path(__file__).parent.parent / "main.py"
        python_bin = shutil_which("python3") or shutil_which("python") or "/usr/bin/python3"

        content = SERVICE_TEMPLATE.format(
            display=SERVICE_DISPLAY,
            python=python_bin,
            entrypoint=str(entrypoint),
        )

        self.app_service_path.write_text(content)

        try:
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            subprocess.run(["systemctl", "--user", "enable", SERVICE_NAME], check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def disable_app_autostart(self):
        """Désactive l'auto-démarrage."""
        try:
            subprocess.run(["systemctl", "--user", "disable", SERVICE_NAME],
                           capture_output=True)
            if self.app_service_path.exists():
                self.app_service_path.unlink()
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def enable_server_autostart(self, server_bin: str, server_args: list):
        """Active l'auto-démarrage du serveur."""
        content = SERVER_SERVICE_TEMPLATE.format(
            display=f"{SERVICE_DISPLAY} - llama-server",
            manager_service=SERVICE_NAME,
            server_bin=server_bin,
            server_args=" ".join(server_args),
        )

        self.server_service_path.write_text(content)

        try:
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            subprocess.run(["systemctl", "--user", "enable", f"{SERVICE_NAME}-server"], check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def disable_server_autostart(self):
        try:
            subprocess.run(["systemctl", "--user", "disable", f"{SERVICE_NAME}-server"],
                           capture_output=True)
            if self.server_service_path.exists():
                self.server_service_path.unlink()
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def get_service_status(self, name: str = SERVICE_NAME) -> str:
        """Retourne le statut du service."""
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-active", name],
                capture_output=True, text=True
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return "unknown"


def shutil_which(cmd: str) -> Optional[str]:
    """Cherche un exécutable dans le PATH."""
    from subprocess import CalledProcessError
    try:
        result = subprocess.run(["which", cmd], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except (CalledProcessError, FileNotFoundError):
        pass
    return None
