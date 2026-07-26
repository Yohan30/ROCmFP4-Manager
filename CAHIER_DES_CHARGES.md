# Cahier des Charges — ROCmFP4 Manager

> **Date :** 23 juillet 2026
> **Version :** 1.0
> **Cible :** AMD Strix Halo (gfx1151) / Linux
> **Stack :** PySide6 (Qt for Python)
> **Port par défaut :** 1412 (interface web + API)

---

## 1. Résumé du projet

Application de bureau légère permettant de **télécharger, configurer et lancer** des modèles GGUF au format ROCmFP4 sans écrire une seule ligne de commande. Elle gère également les **mises à jour automatiques** du runtime ROCmFPX et peut se **lancer au démarrage** du système.

---

## 2. Architecture générale

```
┌─────────────────────────────────────────────────┐
│                Interface Graphique                │
│  (Systray + Fenêtre de configuration)            │
├─────────────────────────────────────────────────┤
│              Backend Python                      │
│  ┌──────────┐  ┌──────────┐  ┌────────────────┐ │
│  │ ROCmFPX  │  │ Models   │  │ Server         │ │
│  │ Updater  │  │ Manager  │  │ Controller     │ │
│  └──────────┘  └──────────┘  └────────────────┘ │
├─────────────────────────────────────────────────┤
│              ROCmFPX (fork llama.cpp)             │
│  build-strix-rocmfp4/bin/                         │
│  ├── llama-server                                 │
│  ├── llama-cli                                    │
│  └── llama-quantize                               │
└─────────────────────────────────────────────────┘
```

---

## 3. Fonctionnalités détaillées

### 3.1 Gestionnaire ROCmFPX (Updater)

| # | Fonctionnalité | Priorité | Description |
|---|---|---|---|
| 1.1 | **Installation initiale** | Haute | Clone le dépôt `charlie12345/ROCmFPX` et lance `scripts/build-strix-rocmfp4-mtp.sh` avec une barre de progression |
| 1.2 | **Détection de version** | Haute | Lit le commit SHA actuel via `git rev-parse HEAD` et compare avec le remote |
| 1.3 | **Mise à jour automatique** | Haute | `git pull` + rebuild si nouveau commit détecté. Planifiable (tous les X jours) ou manuel |
| 1.4 | **Mise à jour planifiée** | Moyenne | Check quotidien/hebdomadaire via un timer systemd ou une tâche planifiée interne |
| 1.5 | **Rollback** | Basse | Sauvegarde du binaire précédent avant rebuild, possibilité de revenir en arrière |
| 1.6 | **Journal des mises à jour** | Moyenne | Log des commits récupérés (auteur, message, date) |
| 1.7 | **Build personnalisé** | Basse | Choix du script de build (Strix Halo, RDNA3, RDNA4, etc.) |

### 3.2 Gestionnaire de Modèles (Models Manager)

| # | Fonctionnalité | Priorité | Description |
|---|---|---|---|
| 2.1 | **Recherche de modèles** | Haute | Champ de recherche interrogeant HuggingFace via son API pour trouver des GGUFs ROCmFP4 |
| 2.2 | **Détection automatique** | Haute | Détecter les fichiers `.gguf` déjà présents dans le dossier des modèles |
| 2.3 | **Téléchargement** | Haute | Téléchargement via `curl`/`wget`/`huggingface-hub` avec barre de progression et reprise (`--continue`) |
| 2.4 | **Gestion des fichiers MTP** | Haute | Détection et téléchargement du fichier MTP companion associé |
| 2.5 | **Suppression** | Haute | Suppression d'un modèle avec confirmation |
| 2.6 | **Informations détaillées** | Moyenne | Affichage des métadonnées : taille, architecture, type de quant, licence, KLD, etc. |
| 2.7 | **Vérification d'intégrité** | Moyenne | Vérification SHA256 du fichier téléchargé (quand disponible) |
| 2.8 | **Modèles recommandés** | Basse | Liste curated de modèles ROCmFP4 optimisés pour Strix Halo |
| 2.9 | **Quantification locale** | Basse | Interface pour lancer `llama-quantize` sur un BF16/F16 source (pour utilisateurs avancés) |
| 2.10 | **🔗 Importer depuis LM Studio** | Haute | Bouton "Importer" qui détecte et liste les modèles GGUF téléchargés par LM Studio dans `~/.lmstudio/models/` — permet de les copier/lier vers le dossier ROCmFP4-Manager |
| 2.11 | **Scan automatique LM Studio** | Moyenne | Au lancement, scanne le dossier LM Studio et affiche une notification : "X modèles trouvés dans LM Studio — Importer ?" |
| 2.12 | **Lien symbolique vs copie** | Moyenne | Choix entre copie physique ou lien symbolique vers le modèle LM Studio (économie d'espace disque) |
| 2.13 | **Dossier des modèles personnalisable** | Haute | Sélecteur de dossier pour choisir où stocker les GGUFs (au lieu de `~/models/` par défaut) — accessible depuis l'onglet Paramètres

### 3.3 Contrôleur du Serveur (Server Controller)

| # | Fonctionnalité | Priorité | Description |
|---|---|---|---|
| 3.1 | **Lancement du serveur** | Haute | Exécute `llama-server` avec les paramètres choisis |
| 3.2 | **Arrêt du serveur** | Haute | SIGTERM propre, timeout puis SIGKILL |
| 3.3 | **Statut en temps réel** | Haute | Serveur en ligne/hors ligne, tokens/s, mémoire utilisée |
| 3.4 | **Logs en direct** | Haute | Capture et affichage des stdout/stderr de `llama-server` |
| 3.5 | **Auto-démarrage au boot** | Haute | Création/gestion d'un service systemd utilisateur (`~/.config/systemd/user/`) |
| 3.6 | **Redémarrage automatique** | Moyenne | Redémarrage du serveur en cas de crash (optionnel) |

### 3.4 Interface de Configuration

| # | Paramètre | Type | Défaut | Description |
|---|---|---|---|---|
| 4.1 | **Modèle** | Sélecteur | — | Liste des modèles installés |
| 4.2 | **MTP Companion** | Sélecteur | — | Fichier MTP associé (optionnel) |
| 4.3 | **Backend** | Radio | `Vulkan0` | `Vulkan0` ou `ROCm0` |
| 4.4 | **Taille du contexte** | Slider (512-262144) | 32768 | `--ctx-size` |
| 4.5 | **Batch size** | Slider (128-4096) | 2048 | `--batch-size` |
| 4.6 | **Ubatch size** | Slider (64-2048) | 1024 | `--ubatch-size` |
| 4.7 | **Flash Attention** | Toggle | ON | `--flash-attn on` |
| 4.8 | **Cache K** | Sélecteur | `q8_0` | `--cache-type-k` |
| 4.9 | **Cache V** | Sélecteur | `q8_0` | `--cache-type-v` |
| 4.10 | **GPU Layers** | Slider (1-999) | 999 | `--n-gpu-layers` |
| 4.11 | **Port** | Input (1024-65535) | **1412** | `--port` — port par défaut pour l'interface web et l'API |
| 4.12 | **Parallel** | Slider (1-8) | 1 | `--parallel` |
| 4.13 | **MTP Actif** | Toggle | OFF | Active le speculative decoding |
| 4.14 | **MTP - n-max** | Slider (1-6) | 4 | `--spec-draft-n-max` |
| 4.15 | **MTP - p-min** | Slider (0.0-1.0) | 0.55 | `--spec-draft-p-min` |
| 4.16 | **MTP - p-split** | Slider (0.0-1.0) | 0.10 | `--spec-draft-p-split` |
| 4.17 | **Reasoning format** | Sélecteur | `deepseek` | `--reasoning-format` |
| 4.18 | **Température** | Slider (0.0-2.0) | — | Surcharge via API, pas en arg serveur |
| 4.19 | **Arguments avancés** | Zone texte libre | — | Flags supplémentaires |
| 4.20 | **📂 Répertoire des modèles** | Path picker | `~/models/` | Dossier de stockage des GGUFs. Bouton "Parcourir" pour choisir, bouton "Ouvrir" pour ouvrir le dossier dans le gestionnaire de fichiers |
| 4.21 | **📂 Répertoire LM Studio** | Texte (lecture seule) | `~/.lmstudio/models/` | Détection automatique. Affiche le chemin et le nombre de modèles trouvés. Bouton "Importer" pour les rapatrier |
| 4.22 | **🚀 Auto-démarrage au boot** | Toggle | OFF | Bascule pour activer/désactiver le service systemd utilisateur. Bouton "Configurer" pour voir/éditer le fichier service |
| 4.23 | **🚀 Auto-démarrage du serveur** | Toggle | OFF | Démarre automatiquement `llama-server` avec le dernier modèle utilisé au boot (après un délai configurable) |
| 4.24 | **Mode silencieux au démarrage** | Toggle | ON | L'application démarre minimisée dans la barre système sans fenêtre visible

### 3.5 Menu Serveur — Panneau de Contrôle & API

Panneau dédié au contrôle du serveur, visible en permanence dans l'interface, avec **toutes les informations de connexion en un coup d'œil**.

#### 3.5.1 Barre d'état du serveur

```
┌─────────────────────────────────────────────────────────┐
│  ● Serveur actif           │  Port : 1412             │
│  Modèle : Qwen3.5-122B     │  PID : 127453             │
│  Uptime : 2h 34m           │  Tokens/s : 28.4          │
│  Mémoire : 61.2 / 128 Go   │  Connexions : 3           │
├─────────────────────────────────────────────────────────┤
│  🔴 Arrêter   🔄 Redémarrer   📋 Copier URL   🌐 Ouvrir │
└─────────────────────────────────────────────────────────┘
```

| # | Fonctionnalité | Priorité | Description |
|---|---|---|---|
| 5.1 | **Indicateur d'état** | Haute | Bille colorée : 🟢 actif / 🔴 arrêté / 🟡 démarrage / ⚠️ erreur |
| 5.2 | **Port actuel** | Haute | Affichage du port utilisé (modifiable dans les paramètres) |
| 5.3 | **PID du processus** | Moyenne | Affichage du Process ID du `llama-server` |
| 5.4 | **Uptime** | Haute | Temps écoulé depuis le démarrage (formaté : Xh Ym) |
| 5.5 | **Tokens/s en direct** | Haute | Débit instantané lu depuis les logs du serveur |
| 5.6 | **Mémoire utilisée** | Haute | Suivi de la consommation mémoire du modèle (via `/proc/PID/status`) |
| 5.7 | **Connexions actives** | Moyenne | Nombre de requêtes en cours / sessions actives |
| 5.8 | **Modèle chargé** | Haute | Nom du modèle GGUF actuellement en cours d'exécution |

#### 3.5.2 Affichage des URLs API

| # | Fonctionnalité | Priorité | Description |
|---|---|---|---|
| 5.9 | **URL Chat Completions** | Haute | Affiche `http://localhost:{PORT}/v1/chat/completions` — bouton copier |
| 5.10 | **URL Completions** | Haute | Affiche `http://localhost:{PORT}/v1/completions` — bouton copier |
| 5.11 | **URL Embeddings** | Haute | Affiche `http://localhost:{PORT}/v1/embeddings` — bouton copier |
| 5.12 | **URL Health** | Haute | Affiche `http://localhost:{PORT}/health` — bouton copier |
| 5.13 | **URL Interface Web** | Haute | Affiche `http://localhost:{PORT}` — ouvrir dans le navigateur |
| 5.14 | **Bouton "Ouvrir"** | Haute | Lance `xdg-open http://localhost:{PORT}` pour ouvrir le chat UI |
| 5.15 | **Copie rapide** | Haute | Chaque URL a un bouton 📋 pour copier dans le presse-papier |
| 5.16 | **QR Code** | Basse | Génère un QR code de l'URL pour accès mobile sur le réseau local |

#### 3.5.3 Gestion de l'API Key

| # | Fonctionnalité | Priorité | Description |
|---|---|---|---|
| 5.17 | **Génération de clé** | Haute | Bouton "Générer" -> `openssl rand -hex 32` -> préremplit le champ |
| 5.18 | **Saisie manuelle** | Haute | Champ texte pour entrer/coller une clé API |
| 5.19 | **Affichage/masquage** | Haute | 👁️ pour voir la clé en clair |
| 5.20 | **Copie de la clé** | Haute | Bouton copier la clé API |
| 5.21 | **API Key activée/désactivée** | Haute | Toggle pour activer/désactiver l'authentification via `--api-key` |
| 5.22 | **Test de connexion** | Moyenne | Bouton "Tester" → envoie une requête curl à `/v1/models` pour vérifier que l'API répond |
| 5.23 | **Client curl example** | Moyenne | Affiche un exemple prêt à copier : `curl http://localhost:{PORT}/v1/chat/completions -H "Authorization: Bearer {KEY}" -d '...'` |

#### 3.5.4 Boutons d'action rapide

```
┌──────────────────────────────────────────────────────┐
│  🟢  Démarrer  │  🔴  Arrêter  │  🔄  Redémarrer    │
├──────────────────────────────────────────────────────┤
│  🌐  Ouvrir l'interface web                          │
│  📋  Copier l'URL de l'API                           │
│  📄  Voir les logs                                   │
│  📤  Exporter la commande complète                   │
└──────────────────────────────────────────────────────┘
```

| # | Fonctionnalité | Priorité | Description |
|---|---|---|---|
| 5.24 | **Démarrer** | Haute | Lance `llama-server` avec la configuration courante |
| 5.25 | **Arrêter** | Haute | SIGTERM → timeout 5s → SIGKILL |
| 5.26 | **Redémarrer** | Haute | Arrête puis redémarre |
| 5.27 | **Ouvrir UI** | Haute | Ouvre `http://localhost:{PORT}` dans le navigateur |
| 5.28 | **Copier URL API** | Haute | Copie `http://localhost:{PORT}/v1` dans le presse-papier |
| 5.29 | **Logs** | Haute | Bascule vers le panneau des logs |
| 5.30 | **Exporter commande** | Moyenne | Copie la ligne de commande complète générée |

#### 3.5.5 Menu contextuel de la systray

Au clic droit sur l'icône de la barre système :

```
┌──────────────────────────┐
│  ● Serveur actif         │  ← statut en temps réel
│  Port : 1412            │
│  Modèle : Qwen3.5-122B   │
├──────────────────────────┤
│  🌐 Ouvrir le chat       │  ← xdg-open http://localhost:1412
│  📋 Copier l'URL API     │
│  📄 Voir les logs        │
├──────────────────────────┤
│  🏋️ Lancer un bench      │  ← Ouvre l'onglet Bench
├──────────────────────────┤
│  ⏹ Arrêter  🔄 Redémarrer│
├──────────────────────────┤
│  ⚙ Configurer            │  ← ouvre la fenêtre principale
│  🚀 Auto-démarrage  [✅] │  ← Toggle visuel on/off (actif/inactif)
│  🔄 Màj ROCmFPX...       │  ← Vérifier et installer les mises à jour
├──────────────────────────┤
│  ❌ Quitter               │
└──────────────────────────┘
```

Le toggle **🚀 Auto-démarrage** permute en temps réel le service systemd :
- **[✅]** = service systemd activé (se lance au boot)
- **[☐]** = service systemd désactivé

Un clic change l'état immédiatement avec une notification de confirmation.

### 3.6 Autres Fonctionnalités

| # | Fonctionnalité | Priorité | Description |
|---|---|---|---|
| 6.1 | **Systray** | Haute | Icône dans la barre système avec menu rapide (Start/Stop/Ouvrir UI/Quitter) |
| 6.2 | **Notifications** | Haute | Notification desktop quand le serveur est prêt, quand une màj est dispo, etc. |
| 6.3 | **Ouvrir l'interface web** | Haute | Bouton pour lancer le navigateur sur `http://localhost:PORT` |
| 6.4 | **Mode silencieux** | Basse | Lancement minimisé, pas de fenêtre au boot |
| 6.5 | **Export de la commande** | Moyenne | Copier la commande `llama-server` complète dans le presse-papier |
| 6.6 | **Profil de configuration** | Basse | Sauvegarder/charger des profils (ex: "Grand contexte", "Max speed", "Agent") |

### 3.7 Interface de Chat Intégrée

Interface de chat complète intégrée directement dans l'application (comme LM Studio, Lemonade, ou GPT4All) — pas besoin d'ouvrir un navigateur pour discuter.

#### 3.7.1 Aperçu visuel

```
┌────────────────────────────────────────────────────┐
│  ⚙️ Chat  ←→  Serveur  ←→  Modèles  ←→  Config   │
├────────────────────────────────────────────────────┤
│                                                    │
│  ┌──────────────────────────────────────────┐      │
│  │ 👤 Moi ─── 14:32                         │      │
│  │ Quelle est la capitale de la France ?    │      │
│  ├──────────────────────────────────────────┤      │
│  │ 🤖 Qwen3.5-122B ─── 14:32 ── 28.4 t/s   │      │
│  │ La capitale de la France est Paris.      │      │
│  │ C'est la plus grande ville du pays et    │      │
│  │ le siège des institutions politiques.    │      │
│  │                                          │      │
│  │  [💻 Copier]  [📋 Copier le code]        │      │
│  ├──────────────────────────────────────────┤      │
│  │ 🧠 DeepSeek ─── 14:34 ── 4.2 s          │      │
│  │ [Pensée...] On me demande la capitale    │      │
│  │ de la France... Je sais que c'est        │      │
│  │ Paris...                                 │      │
│  │ ──────────────────────────────────────── │      │
│  │ ✓ La capitale de la France est Paris.    │      │
│  └──────────────────────────────────────────┘      │
│                                                    │
│  ┌──────────────────────────────────────────┐      │
│  │  💬 Pose ta question ici...     [📎] [📤]│      │
│  └──────────────────────────────────────────┘      │
│   Modèle : Qwen3.5-122B  ▲  T: 0.7  ▲  Max: 4096  │
├────────────────────────────────────────────────────┤
│  ⚡ 28.4 t/s  │  Contexte: 1.2k/32k  │  🟢 Actif │
└────────────────────────────────────────────────────┘
```

#### 3.7.2 Zone de messages

| # | Fonctionnalité | Priorité | Description |
|---|---|---|---|
| 7.1 | **Bulle utilisateur** | Haute | Message aligné à droite, fond coloré, avatar 👤 |
| 7.2 | **Bulle assistant** | Haute | Message aligné à gauche, avatar 🤖, nom du modèle affiché |
| 7.3 | **Streaming en direct** | Haute | Affichage token par token pendant la génération (comme ChatGPT) |
| 7.4 | **Markdown rendu** | Haute | Rendu complet Markdown : titres, listes, tableaux, **gras**, *italique* |
| 7.5 | **Blocs de code** | Haute | Blocs de code avec coloration syntaxique et bouton 📋 copier |
| 7.6 | **Bouton Copier le message** | Haute | Copie le texte brut du message dans le presse-papier |
| 7.7 | **Horodatage** | Haute | Heure de chaque message |
| 7.8 | **Tokens/s en direct** | Haute | Affiche la vitesse de génération en temps réel à côté du message |
| 7.9 | **Affichage du raisonnement** | Haute | Affiche la chaîne de pensée `🧠` (pour DeepSeek / reasoning_format) dans un bloc repliable |
| 7.10 | **Arrêt de génération** | Haute | Bouton ⏹️ pour stopper la génération en cours |
| 7.11 | **Regénérer** | Moyenne | Bouton 🔄 pour re-générer la dernière réponse |
| 7.12 | **Éditer le message** | Moyenne | Permet de modifier un message utilisateur envoyé et re-soumettre |
| 7.13 | **Supprimer un message** | Moyenne | Menu contextuel "Supprimer" sur chaque message |
| 7.14 | **Images dans le chat** | Basse | Support multi-modal (glisser-déposer une image si le modèle gère la vision) |

#### 3.7.3 Barre de saisie

| # | Fonctionnalité | Priorité | Description |
|---|---|---|---|
| 7.15 | **Champ multi-ligne** | Haute | Zone de texte extensible (Shift+Enter = saut de ligne, Enter = envoyer) |
| 7.16 | **Envoi par Entrée** | Haute | Enter envoie le message (configurable) |
| 7.17 | **Bouton d'envoi** | Haute | Icône 📤 à droite du champ |
| 7.18 | **Attacher un fichier** | Basse | Bouton 📎 pour joindre un fichier (prompt sera `[Contenu du fichier]`) |
| 7.19 | **Indicateur d'écriture** | Haute | 🤖 clignotant ou barre de progression pendant la génération |
| 7.20 | **Touches de raccourci** | Moyenne | Ctrl+Shift+Suppr = effacer tout, Ctrl+Enter = nouvelle ligne (quand Enter=envoi) |
| 7.21 | **Limite de caractères** | Basse | Compteur de caractères si pertinent |

#### 3.7.4 Paramètres rapides en ligne

Contrôles situés sous la barre de saisie, modifiables pendant le chat :

```
  Modèle : [Qwen3.5-122B  ▼]  T: [0.70  ▼]  Max Tokens: [4096  ▼]
  [📎 System Prompt...]  [🧠 Reasoning: ON]  [🌐 Web Search: OFF]
```

| # | Fonctionnalité | Priorité | Description |
|---|---|---|---|
| 7.22 | **Sélecteur de modèle** | Haute | Menu déroulant listant les modèles installés — permet de changer de modèle à chaud |
| 7.23 | **Température** | Haute | Slider ou spinbox (0.0 – 2.0, pas de 0.01) |
| 7.24 | **Max tokens** | Haute | Limite de tokens pour la réponse (256 – 32000+) |
| 7.25 | **Top P** | Moyenne | Nucleus sampling (0.0 – 1.0) |
| 7.26 | **Top K** | Moyenne | Top-K sampling |
| 7.27 | **Presets de sampling** | Basse | Profils rapides : "Précis" (T=0.1), "Créatif" (T=0.9), "Coding" (T=0.3), "Équilibré" (T=0.7) |
| 7.28 | **System Prompt éditable** | Haute | Zone de texte dépliable pour définir le system prompt |
| 7.29 | **Session Memory** | Basse | Nombre de messages gardés dans le contexte (ou "Auto") |
| 7.30 | **Web Search intégré** | Basse | Toggle pour activer la recherche web avant réponse (si serveur configuré) |

#### 3.7.5 Gestion des conversations

| # | Fonctionnalité | Priorité | Description |
|---|---|---|---|
| 7.31 | **Nouveau chat** | Haute | Bouton ➕ pour créer une conversation vierge |
| 7.32 | **Barre latérale d'historique** | Haute | Panneau rétractable à gauche listant les conversations (comme ChatGPT) |
| 7.33 | **Titre automatique** | Haute | Le premier message de la conversation sert de titre (tronqué) |
| 7.34 | **Renommer une conversation** | Haute | Clic droit → Renommer |
| 7.35 | **Supprimer conversation** | Haute | Clic droit → Supprimer (avec confirmation) |
| 7.36 | **Exporter la conversation** | Haute | Export en JSON, Markdown ou TXT |
| 7.37 | **Importer une conversation** | Moyenne | Importer un fichier JSON de conversation |
| 7.38 | **Rechercher dans l'historique** | Moyenne | Champ de recherche en haut de la barre latérale |
| 7.39 | **Date de création** | Moyenne | Groupement par date (Aujourd'hui, Hier, Cette semaine...) |
| 7.40 | **Effacer tout le contexte** | Haute | Bouton "Clear context" pour réinitialiser la conversation sans perdre l'historique affiché |
| 7.41 | **Persistance** | Haute | Les conversations sont sauvegardées automatiquement en SQLite/JSON |

#### 3.7.6 Barre de statut du chat

| # | Fonctionnalité | Priorité | Description |
|---|---|---|---|
| 7.42 | **Modèle actif** | Haute | Nom du modèle en cours + indicateur de connexion au serveur |
| 7.43 | **Tokens utilisés** | Haute | Contexte : tokens utilisés / taille max (ex: `1.2k / 32k`) |
| 7.44 | **Vitesse de génération** | Haute | Tokens/s en temps réel pendant la génération |
| 7.45 | **Latence** | Moyenne | Temps de first-token et temps total de la réponse |
| 7.46 | **Statut serveur** | Haute | 🟢 Actif / 🔴 Déconnecté / 🟡 Démarrage |

#### 3.7.7 Comportement hors-ligne

| # | Fonctionnalité | Priorité | Description |
|---|---|---|---|
| 7.47 | **Détection de connexion** | Haute | Vérifie que le serveur est en ligne avant d'envoyer un message |
| 7.48 | **File d'attente** | Basse | Si le serveur est occupé, mise en file d'attente du message |
| 7.49 | **Mode dégradé** | Basse | Si le serveur plante pendant le chat, message d'erreur clair avec suggestion de redémarrage |

### 3.8 🏋️ Bench intégré (Ollama + llama-bench)

Outil de benchmark intégré pour mesurer les performances du modèle et du système, avec export des résultats.

#### 3.8.1 Aperçu visuel

```
┌────────────────────────────────────────────────────┐
│  🏋️ Bench                                           │
├────────────────────────────────────────────────────┤
│  Modèle : [Qwen3.5-122B-A10B-ROCmFP4 ▼]           │
│  Backend : [Vulkan0 ▼]  [ROCm0 ▼]                  │
│                                                     │
│  ☐ Prefill (pp) : [512] tokens                      │
│  ☐ Decode (tg)  : [128]  tokens                    │
│  ☐ Test multiple : [3] runs                        │
│  ☐ Bench complet llama-bench                       │
│                                                     │
│  [🏁 Lancer le bench]  [📋 Copier la commande]     │
│                                                     │
├────────────────────────────────────────────────────┤
│  Résultats :                                        │
│                                                     │
│  ┌──────┬──────────┬──────────┬──────────┐        │
│  │ Run  │ Prefill  │  Decode  │  Note    │        │
│  ├──────┼──────────┼──────────┼──────────┤        │
│  │ #1   │ 348 t/s  │ 28.4 t/s │ ~~       │        │
│  │ #2   │ 351 t/s  │ 28.1 t/s │ ~~       │        │
│  │ #3   │ 350 t/s  │ 28.5 t/s │ ~~       │        │
│  │ ─────│──────────│──────────│──────────│        │
│  │ ⌀    │ 349 t/s  │ 28.3 t/s │          │        │
│  └──────┴──────────┴──────────┴──────────┘        │
│                                                     │
│  🏆 Score: 28.3 tok/s (Médian)                     │
│  💾 [Exporter en CSV]  [Exporter en JSON]           │
└────────────────────────────────────────────────────┘
```

#### 3.8.2 Types de bench

| # | Fonctionnalité | Priorité | Description |
|---|---|---|---|
| 8.1 | **Bench rapide (llama-bench)** | Haute | Lance `llama-bench` avec le modèle et les paramètres choisis — mesure prefill + decode |
| 8.2 | **Bench personnalisé** | Haute | Configuration manuelle : pp (prefill tokens), tg (generation tokens), batch, nbatch, threads |
| 8.3 | **Multi-run** | Haute | Lance le bench N fois et calcule la moyenne / médiane |
| 8.4 | **Bench comparatif** | Moyenne | Lance le même test sur plusieurs backends (`Vulkan0` vs `ROCm0`) et affiche un tableau comparatif |
| 8.5 | **Bench Ollama (optionnel)** | Basse | Si Ollama est installé, lance `ollama run` + mesure du temps de génération (même prompt) pour comparer ROCmFP4 vs Ollama |
| 8.6 | **Bench contexte long** | Basse | Test de prefill long (4096 tokens) pour mesurer les performances en contexte étendu |

#### 3.8.3 Affichage des résultats

| # | Fonctionnalité | Priorité | Description |
|---|---|---|---|
| 8.7 | **Tableau des résultats** | Haute | Tableau triable : Run, Prefill (t/s), Decode (t/s), Total (s) |
| 8.8 | **Moyenne / Médiane** | Haute | Calcul automatique sur plusieurs runs |
| 8.9 | **Graphique (optionnel)** | Basse | Petit graphique à barres comparant les runs (via matplotlib ou Qt Charts) |
| 8.10 | **Export CSV** | Moyenne | Export des résultats bruts en CSV |
| 8.11 | **Export JSON** | Moyenne | Export des résultats en JSON (compatible avec d'autres outils) |
| 8.12 | **Historique des benchs** | Basse | Sauvegarde des résultats précédents dans un fichier JSON pour suivre l'évolution après màj |

#### 3.8.4 Raccourci rapide (systray)

Le menu de la systray contient un raccourci direct :

```
┌──────────────────────┐
│  ● Serveur actif     │
│  Port : 1412        │
│                      │
│  🌐 Ouvrir le chat   │
│  📋 Copier l'URL API │
│  📄 Voir les logs    │
│  ├──────────────────┤
│  🏋️ Lancer un bench  │  ← Ouvre directement l'onglet Bench
│  ├──────────────────┤
│  ⏹ Arrêter          │
│  🔄 Redémarrer       │
│  ├──────────────────┤
│  ⚙ Configurer        │
│  🚀 Démarrer au boot │  ← Toggle ON/OFF (visuel: ✅ ou ☐)
│  ├──────────────────┤
│  ❌ Quitter          │
└──────────────────────┘
```

| # | Fonctionnalité | Priorité | Description |
|---|---|---|---|
| 8.13 | **🏋️ Raccourci Bench dans systray** | Haute | Lance directement le bench avec les paramètres par défaut depuis le menu contextuel |
| 8.14 | **Bouton "Bench rapide"** | Haute | Bouton dans l'onglet Serveur / Barre d'outils pour lancer un bench sans passer par la config |

---

## 4. Prérequis système

### 4.1 Dépendances obligatoires

- **ROCmFPX** (compilé via le script de build)
- **Python 3.11+** (si backend Python)
- **Git** (pour les mises à jour)
- **systemd** (pour l'auto-démarrage au boot)
- **curl / wget** (pour les téléchargements)
- **Mesa 25.2.8+** (déjà présent sur Strix Halo)
- **Linux 6.17+** (déjà présent)

### 4.2 Dépendances facultatives

- `huggingface-hub` (API Python pour rechercher/télécharger)
- `notify-send` (notifications desktop)
- `xdg-open` (ouvrir le navigateur)

### 4.3 Stack frontend (à choisir)

| Option | Avantages | Inconvénients |
|---|---|---|
| **PyQt6 + Qt6** | Natif, riche, pas de runtime lourd | Apprentissage, packaging |
| **PySide6 + Qt6** | Idem PyQt, licence LGPL | Même chose |
| **Tauri 2 + Svelte** | Interface web moderne, binaire léger | Plus complexe, nécessite Rust + Node |
| **Electron + HTML/JS** | Énorme écosystème | Binaire très lourd |
| **Custom Tkinter** | Aucune dépendance | UI pas très moderne |
| **Textual (TUI)** | Interface terminal, léger | Pas de systray, pas graphique |

**Recommandation : PySide6 (Qt for Python)** — bon équilibre entre expérience utilisateur, facilité de développement et légèreté.

---

## 5. Structure du projet (proposée)

```
ROCmFP4-Manager/
├── CAHIER_DES_CHARGES.md
├── README.md
├── requirements.txt
├── src/
│   ├── main.py                  # Point d'entrée
│   ├── app.py                   # Application Qt
│   ├── system_tray.py           # Icône systray
│   │
│   ├── core/
│   │   ├── rocmfpx_manager.py   # Clone, build, update ROCmFPX
│   │   ├── model_manager.py     # Search, download, manage models
│   │   ├── server_controller.py # Start/stop/monitor llama-server
│   │   └── autostart.py         # Systemd service management
│   │
│   ├── ui/
│   │   ├── main_window.py       # Fenêtre principale (QTabWidget)
│   │   ├── models_tab.py        # Onglet : gestion des modèles
│   │   ├── config_tab.py        # Onglet : configuration serveur
│   │   ├── server_tab.py        # Onglet : logs et contrôle
│   │   ├── bench_tab.py         # 🏋️ Onglet : benchmark intégré
│   │   ├── chat_tab.py          # 💬 Onglet : interface de chat intégrée
│   │   ├── chat/
│   │   │   ├── chat_widget.py   # Widget principal du chat
│   │   │   ├── message_bubble.py# Bulle de message (utilisateur / assistant)
│   │   │   ├── input_bar.py     # Barre de saisie avec paramètres rapides
│   │   │   ├── history_panel.py # Barre latérale d'historique
│   │   │   ├── code_block.py    # Bloc de code avec coloration syntaxique
│   │   │   └── markdown.py      # Rendu Markdown custom
│   │   ├── settings_tab.py      # Onglet : paramètres généraux
│   │   └── widgets.py           # Widgets réutilisables
│   │
│   └── utils/
│       ├── config.py            # Gestion de la configuration (JSON/YAML)
│       ├── huggingface_api.py   # Wrapper API HuggingFace
│       ├── process_utils.py     # Utilitaires de processus
│       ├── conversation_store.py# 💬 Sauvegarde/chargement des conversations
│       └── llm_client.py        # 💬 Client HTTP pour l'API OpenAI du serveur
│
├── config/
│   └── default_settings.json    # Configuration par défaut
│
└── scripts/
    └── install.sh               # Script d'installation
```

---

## 6. Workflow utilisateur

### 6.1 Première utilisation

```
Lancer l'app
    │
    ▼
Détection : ROCmFPX est-il installé ?
    │                       │
   NON                     OUI
    │                       │
    ▼                       ▼
"Cloner et compiler"    Détection des modèles
   Barre de              déjà présents
   progression           │
    │                    ▼
    ▼               Interface principale
  Prêt !
```

### 6.2 Utilisation quotidienne

```
1. Lancer l'app (ou auto-démarrée au boot)
2. L'icône apparaît dans la barre système
3. Sélectionner un modèle installé
4. (Optionnel) Ajuster les paramètres
5. Cliquer "Démarrer le serveur"
6. Le serveur est prêt → notification
7. Cliquer "Ouvrir l'interface" → navigateur
```

### 6.3 Mise à jour ROCmFPX

```
1. Check automatique (quotidien ou au lancement)
2. Nouveau commit détecté ?
    │
   OUI
    │
    ▼
3. Notification : "Mise à jour disponible"
4. Option A : Mise à jour automatique
   Option B : Ignorer
   Option C : Voir le changelog
5. Si accepté :
   - git pull
   - Rebuild (barre progression)
   - Redémarrage du serveur si actif
```

---

## 7. Auto-démarrage (systemd)

Création d'un service **utilisateur** (pas root) :

```
~/.config/systemd/user/rocmfp4-manager.service

[Unit]
Description=ROCmFP4 Manager

[Service]
ExecStart=/opt/ROCMFP4-Manager/venv/bin/python /opt/ROCMFP4-Manager/src/main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

**Gestion via l'app :**
- `systemctl --user enable rocmfp4-manager.service`
- `systemctl --user start/stop/status rocmfp4-manager.service`

Si l'utilisateur veut que le serveur démarre automatiquement avec le dernier modèle utilisé (pas juste l'app), un service séparé peut être créé :

```
~/.config/systemd/user/rocmfp4-server.service

[Unit]
Description=ROCmFP4 llama-server
After=rocmfp4-manager.service

[Service]
ExecStart=/opt/ROCmFP4-Manager/build/bin/llama-server [args...]
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

---

## 8. Contraintes techniques

| Contrainte | Détail |
|---|---|
| **Stockage** | Les modèles pèsent 10-70 Go. Besoin d'un dossier dédié avec espace suffisant. |
| **RAM/VRAM** | Le Qwen 122B prend ~60 Go. Un système 128 Go Strix Halo peut faire tourner le serveur + l'app + le bureau. |
| **Temps de compilation** | La première compilation de ROCmFPX prend ~5-10 minutes. Les mises à jour sont plus rapides (incrémental). |
| **Téléchargement** | Un fichier de 60 Go peut prendre du temps. Nécessité de gérer la reprise et les timeouts. |
| **Multi-instance** | Un seul serveur `llama-server` par modèle à la fois. |
| **Portabilité** | Application Linux uniquement (liée à ROCmFPX / Strix Halo). |

---

## 9. Étapes de développement proposées

### Phase 1 — Socle (prioritaire)
- [ ] Structure du projet Python
- [ ] Module `ROCmFPXManager` : clone, build, détection de version
- [ ] Module `ServerController` : start/stop/monitor `llama-server`
- [ ] Interface de base (systray + fenêtre)
- [ ] Module `autostart.py` : gestion systemd
- [ ] Interface : **toggle auto-démarrage** dans systray + settings

### Phase 2 — Modèles
- [ ] Module `ModelManager` : list, download, delete
- [ ] Intégration HuggingFace API (recherche)
- [ ] Barre de progression téléchargement
- [ ] Gestion MTP companion
- [ ] **📂 Dossier personnalisable** : sélecteur de dossier pour les modèles
- [ ] **📦 Import LM Studio** : scan `~/.lmstudio/models/` + import par copie/symlink
- [ ] Bouton "Ouvrir le dossier" dans l'interface

### Phase 3 — Configuration
- [ ] Interface de configuration complète
- [ ] Sauvegarde/chargement des settings
- [ ] Profils de configuration
- [ ] Validation des paramètres

### Phase 4 — Mises à jour & Finitions
- [ ] Mise à jour automatique de ROCmFPX
- [ ] Notifications desktop
- [ ] Journal des mises à jour
- [ ] Export commande
- [ ] Tests et documentation

### Phase 5 — 💬 Interface de Chat Intégrée
- [ ] `llm_client.py` : client HTTP OpenAI-compatible (streaming + non-streaming)
- [ ] `conversation_store.py` : persistance SQLite des conversations
- [ ] `message_bubble.py` : bulles de message avec rendu Markdown
- [ ] `input_bar.py` : barre de saisie avec paramètres (temp, max tokens, system prompt)
- [ ] `history_panel.py` : barre latérale d'historique des conversations
- [ ] `code_block.py` : blocs de code avec coloration syntaxique et bouton copier
- [ ] `chat_tab.py` : assemblage de tous les composants dans un onglet
- [ ] Streaming en direct token par token
- [ ] Export / Import de conversations
- [ ] Gestion du raisonnement (DeepSeek-style)

### Phase 6 — 🏋️ Bench Intégré
- [ ] `bench_tab.py` : interface de benchmark
- [ ] Exécution `llama-bench` avec paramètres (pp, tg, runs, backend)
- [ ] Tableau des résultats avec moyenne
- [ ] Export CSV / JSON
- [ ] Raccourci systray "Lancer un bench"
- [ ] Bench comparatif (Vulkan vs ROCm)

---

## 10. Questions ouvertes

1. **Qt vs Tauri ?** — PySide6 est plus accessible, Tauri donne un binaire plus petit et une UI plus moderne. Choix à faire.
2. **Namespace de l'app ?** — `rocmfp4-manager` ? `rocgui` ? `halo-launcher` ?
3. **Faut-il un mode "headless" (CLI uniquement) en plus du GUI ?** — Utile pour les serveurs.
4. **Gestion des erreurs ROCmFPX** — Si le build échoue, doit-on proposer un rapport automatique ?
5. **Modèles non-ROCmFP4 ?** — Faut-il supporter les GGUF standards (Q4_K_M, etc.) en fallback ?
