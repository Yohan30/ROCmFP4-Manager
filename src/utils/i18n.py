"""Système de traduction simple pour ROCmFP4 Manager."""

from typing import Optional


class I18n:
    """Gère les chaînes traduites. Par défaut: anglais."""

    _instance = None

    def __init__(self, lang: str = "en"):
        self._lang = lang
        self._strings = self._load_strings()

    @classmethod
    def instance(cls, lang: Optional[str] = None):
        if cls._instance is None:
            cls._instance = cls(lang or "en")
        elif lang is not None:
            cls._instance.set_lang(lang)
        return cls._instance

    def set_lang(self, lang: str):
        self._lang = lang
        self._strings = self._load_strings()

    @property
    def lang(self) -> str:
        return self._lang

    def t(self, key: str) -> str:
        """Retourne la chaîne traduite pour la clé donnée."""
        return self._strings.get(key, {}).get(self._lang,
               self._strings.get(key, {}).get("en", key))

    def _load_strings(self) -> dict:
        return {
            # --- Général ---
            "app_name": {"en": "ROCmFP4 Manager", "fr": "ROCmFP4 Manager"},
            "ready": {"en": "Ready", "fr": "Prêt"},
            "save": {"en": "Save", "fr": "Sauvegarder"},
            "reset": {"en": "Reset", "fr": "Réinitialiser"},
            "cancel": {"en": "Cancel", "fr": "Annuler"},
            "close": {"en": "Close", "fr": "Fermer"},
            "browse": {"en": "Browse", "fr": "Parcourir"},
            "open": {"en": "Open", "fr": "Ouvrir"},
            "copy": {"en": "Copy", "fr": "Copier"},
            "delete": {"en": "Delete", "fr": "Supprimer"},
            "refresh": {"en": "Refresh", "fr": "Rafraîchir"},
            "search": {"en": "Search", "fr": "Rechercher"},
            "download": {"en": "Download", "fr": "Télécharger"},

            # --- Serveur ---
            "server": {"en": "Server", "fr": "Serveur"},
            "server_status": {"en": "Server Status", "fr": "Statut du serveur"},
            "server_start": {"en": "Start", "fr": "Démarrer"},
            "server_stop": {"en": "Stop", "fr": "Arrêter"},
            "server_restart": {"en": "Restart", "fr": "Redémarrer"},
            "server_started": {"en": "Server is running", "fr": "Serveur actif"},
            "server_stopped": {"en": "Server stopped", "fr": "Serveur arrêté"},
            "server_starting": {"en": "Starting...", "fr": "Démarrage..."},
            "server_offline": {"en": "Server offline", "fr": "Serveur déconnecté"},
            "server_online": {"en": "Connected", "fr": "Connecté"},
            "server_logs": {"en": "Server Logs", "fr": "Logs du serveur"},

            # --- Port / API ---
            "port": {"en": "Port", "fr": "Port"},
            "api_endpoints": {"en": "API Endpoints", "fr": "Endpoints API"},
            "api_key": {"en": "API Key", "fr": "Clé API"},
            "api_key_disabled": {"en": "Disabled", "fr": "Désactivée"},
            "api_key_generate": {"en": "Generate", "fr": "Générer"},
            "api_chat_url": {"en": "Chat Completions", "fr": "Chat Completions"},
            "api_web_ui": {"en": "Web Interface", "fr": "Interface Web"},

            # --- Backend / Performance ---
            "backend": {"en": "Backend", "fr": "Backend"},
            "context_size": {"en": "Context Size", "fr": "Taille du contexte"},
            "batch_size": {"en": "Batch Size", "fr": "Batch size"},
            "gpu_layers": {"en": "GPU Layers", "fr": "GPU Layers"},
            "flash_attention": {"en": "Flash Attention", "fr": "Flash Attention"},
            "cache_k": {"en": "Cache K", "fr": "Cache K"},
            "cache_v": {"en": "Cache V", "fr": "Cache V"},

            # --- Modèles ---
            "models": {"en": "Models", "fr": "Modèles"},
            "models_installed": {"en": "Installed Models", "fr": "Modèles installés"},
            "models_search": {"en": "Search on HuggingFace", "fr": "Rechercher sur HuggingFace"},
            "models_folder": {"en": "Models Folder", "fr": "Dossier des modèles"},
            "model_select": {"en": "Select", "fr": "Sélectionner"},
            "model_selected": {"en": "Model selected", "fr": "Modèle sélectionné"},
            "no_model": {"en": "No model selected", "fr": "Aucun modèle sélectionné"},
            "import_lmstudio": {"en": "Import from LM Studio", "fr": "Importer depuis LM Studio"},
            "use_symlink": {"en": "Use symbolic link (save disk space)", "fr": "Utiliser un lien symbolique (économie d'espace)"},

            # --- ROCmFPX ---
            "rocmfpx": {"en": "ROCmFPX", "fr": "ROCmFPX"},
            "rocmfpx_status": {"en": "ROCmFPX Status", "fr": "Statut ROCmFPX"},
            "rocmfpx_clone": {"en": "Clone ROCmFPX", "fr": "Cloner ROCmFPX"},
            "rocmfpx_compile": {"en": "Compile (Strix Halo)", "fr": "Compiler (Strix Halo)"},
            "rocmfpx_check_updates": {"en": "Check for updates", "fr": "Vérifier les mises à jour"},
            "rocmfpx_changelog": {"en": "Changelog", "fr": "Changelog"},
            "rocmfpx_delete_build": {"en": "Delete build", "fr": "Supprimer le build"},
            "rocmfpx_ready": {"en": "ROCmFPX installed and compiled", "fr": "ROCmFPX installé et compilé"},
            "rocmfpx_cloned_only": {"en": "ROCmFPX cloned, not yet compiled", "fr": "ROCmFPX cloné, mais pas encore compilé"},
            "rocmfpx_not_installed": {"en": "ROCmFPX is not installed", "fr": "ROCmFPX n'est pas installé"},
            "rocmfpx_compiling": {"en": "Compiling (5-10 min)...", "fr": "Compilation (5-10 min)..."},
            "rocmfpx_build_logs": {"en": "Build Logs", "fr": "Logs de compilation"},
            "rocmfpx_build_deleted": {"en": "Build deleted. You can recompile.", "fr": "Build supprimé. Vous pouvez recompiler."},

            # --- Bench ---
            "bench": {"en": "Benchmark", "fr": "Benchmark"},
            "bench_config": {"en": "Benchmark Configuration", "fr": "Configuration du benchmark"},
            "bench_start": {"en": "Run Benchmark", "fr": "Lancer le bench"},
            "bench_comparison": {"en": "Comparative bench (Vulkan + ROCm)", "fr": "Bench comparatif (Vulkan + ROCm)"},
            "bench_runs": {"en": "Number of runs", "fr": "Nombre de runs"},
            "bench_results": {"en": "Results", "fr": "Résultats"},
            "bench_avg": {"en": "Average decode", "fr": "Moyenne decode"},
            "bench_median": {"en": "Median decode", "fr": "Médiane decode"},
            "bench_export_csv": {"en": "Export CSV", "fr": "Exporter CSV"},
            "bench_export_json": {"en": "Export JSON", "fr": "Exporter JSON"},

            # --- Chat ---
            "chat": {"en": "Chat", "fr": "Chat"},
            "chat_new": {"en": "New Chat", "fr": "Nouveau chat"},
            "chat_placeholder": {"en": "Type your message...", "fr": "Pose ta question ici..."},
            "chat_send": {"en": "Send", "fr": "Envoyer"},
            "chat_stop": {"en": "Stop", "fr": "Arrêter"},
            "chat_writing": {"en": "Writing...", "fr": "Écriture..."},
            "chat_system_prompt": {"en": "System Prompt", "fr": "System Prompt"},
            "chat_temp": {"en": "Temp", "fr": "Temp"},
            "chat_max_tokens": {"en": "Max Tokens", "fr": "Max Tokens"},
            "chat_no_server": {"en": "Server is not running.\nStart it from the Server tab.", "fr": "Le serveur n'est pas en cours d'exécution.\nDémarrez-le depuis l'onglet Serveur."},

            # --- Settings ---
            "settings": {"en": "Settings", "fr": "Paramètres"},
            "settings_autostart": {"en": "Auto-start", "fr": "Auto-démarrage"},
            "settings_autostart_app": {"en": "Launch ROCmFP4 Manager at system startup", "fr": "Lancer ROCmFP4 Manager au démarrage du système"},
            "settings_autostart_server": {"en": "Auto-start server with last used model", "fr": "Démarrer automatiquement le serveur avec le dernier modèle utilisé"},
            "settings_silent": {"en": "Start silently (minimized to system tray)", "fr": "Démarrer silencieusement (minimisé dans la barre système)"},
            "settings_service_active": {"en": "Auto-start service: active", "fr": "Service d'auto-démarrage: actif"},
            "settings_service_inactive": {"en": "Auto-start service: inactive", "fr": "Service d'auto-démarrage: inactif"},
            "settings_language": {"en": "Language", "fr": "Langue"},
            "settings_paths": {"en": "Paths", "fr": "Chemins"},
            "settings_about": {"en": "About", "fr": "À propos"},
            "settings_saved": {"en": "Settings saved", "fr": "Paramètres sauvegardés"},

            # --- Configuration ---
            "config": {"en": "Configuration", "fr": "Configuration"},
            "config_model": {"en": "Model", "fr": "Modèle"},
            "config_mtp": {"en": "MTP Companion", "fr": "MTP Companion"},
            "config_performance": {"en": "Performance", "fr": "Performance"},
            "config_cache": {"en": "K/V Cache", "fr": "Cache K/V"},
            "config_mtp_title": {"en": "MTP Speculative Decoding", "fr": "MTP Speculative Decoding"},
            "config_mtp_enable": {"en": "Enable MTP (self-speculative decoding)", "fr": "Activer le MTP (self-speculative decoding)"},
            "config_server": {"en": "Server", "fr": "Serveur"},
            "config_advanced": {"en": "Advanced arguments (optional)", "fr": "Arguments avancés (optionnel)"},
            "config_reasoning": {"en": "Reasoning format", "fr": "Format de raisonnement"},
            "config_saved": {"en": "Configuration saved", "fr": "Configuration sauvegardée"},

            # --- Erreurs ---
            "error": {"en": "Error", "fr": "Erreur"},
            "warning": {"en": "Warning", "fr": "Attention"},
            "info": {"en": "Information", "fr": "Information"},
            "confirm": {"en": "Confirm", "fr": "Confirmer"},
            "confirm_delete": {"en": "This action is irreversible.", "fr": "Cette action est irréversible."},

            # --- Divers ---
            "uptime": {"en": "Uptime", "fr": "Uptime"},
            "tokens_per_sec": {"en": "Tokens/s", "fr": "Tokens/s"},
            "memory": {"en": "Memory", "fr": "Mémoire"},
            "pid": {"en": "PID", "fr": "PID"},
            "disk_space": {"en": "Free space", "fr": "Espace libre"},
            "model_name": {"en": "Model", "fr": "Modèle"},
            "main": {"en": "Main", "fr": "Principal"},
            "no_results": {"en": "No results found.", "fr": "Aucun résultat trouvé."},

            # --- MTP ---
            "mtp_nmax": {"en": "n-max", "fr": "n-max"},
            "mtp_pmin": {"en": "p-min", "fr": "p-min"},
            "mtp_psplit": {"en": "p-split", "fr": "p-split"},

            # --- Autostart ---
            "autostart_toggle": {"en": "Auto-start", "fr": "Auto-démarrage"},
            "autostart_enabled": {"en": "Auto-start: enabled", "fr": "Auto-démarrage: activé"},
            "autostart_disabled": {"en": "Auto-start: disabled", "fr": "Auto-démarrage: désactivé"},

            # --- Build ---
            "deps_install": {"en": "Installing dependencies...", "fr": "Installation des dépendances..."},
            "deps_check": {"en": "Checking dependencies...", "fr": "Vérification des dépendances..."},
            "clone_in_progress": {"en": "Cloning in progress...", "fr": "Clonage en cours..."},
            "clone_done": {"en": "Clone completed", "fr": "Clonage terminé"},
            "build_in_progress": {"en": "Build in progress...", "fr": "Compilation en cours..."},
            "build_done": {"en": "Build completed successfully!", "fr": "Compilation terminée avec succès !"},
            "build_failed": {"en": "Build failed", "fr": "Build échoué"},
            "update_available": {"en": "An update is available.", "fr": "Une mise à jour est disponible."},
            "up_to_date": {"en": "ROCmFPX is up to date", "fr": "ROCmFPX est à jour"},
        }


# Raccourci global
_i18n = None


def _(key: str) -> str:
    """Fonction de traduction globale."""
    global _i18n
    if _i18n is None:
        _i18n = I18n.instance()
    return _i18n.t(key)


def set_language(lang: str):
    global _i18n
    _i18n = I18n.instance(lang)
