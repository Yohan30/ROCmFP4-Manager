#!/usr/bin/env python3
"""Point d'entrée de ROCmFP4 Manager."""

import sys
import os
import signal

# S'assurer que le répertoire parent est dans le PATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.app import ROCmFP4App


def main():
    app = ROCmFP4App(sys.argv)

    # Nettoyer le serveur même en cas de SIGTERM/SIGINT (pkill, Ctrl+C)
    def _signal_handler(signum, frame):
        if hasattr(app, 'cleanup'):
            app.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
