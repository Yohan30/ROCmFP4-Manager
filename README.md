# ROCmFP4 Manager 🚀

Interface graphique pour **télécharger, configurer et lancer** des modèles GGUF au format **ROCmFP4** sur **AMD Strix Halo** — sans écrire une seule ligne de commande.

![ROCmFP4 Manager](assets/icon.svg)

## ✨ Fonctionnalités

- **📦 Gestion des modèles** — Recherche sur HuggingFace, téléchargement, import depuis LM Studio
- **⚙️ Configuration visuelle** — Contexte, batch, cache K/V, MTP, flash attention, tout en sliders
- **🖥️ Contrôle du serveur** — Start/Stop/Redémarrer, logs en direct, URLs API affichées
- **💬 Chat intégré** — Interface de discussion comme LM Studio (streaming, markdown, historique)
- **🏋️ Bench intégré** — Tests de performance avec `llama-bench`, multi-run, export CSV/JSON
- **🚀 Auto-démarrage** — Service systemd pour lancer l'app et/ou le serveur au boot
- **🔄 Mise à jour automatique** — Vérification et installation des nouvelles versions de ROCmFPX
- **🌙 Thème sombre** — Design moderne aux couleurs AMD (rouge/noir)

## Prérequis

- **AMD Strix Halo** (Radeon 8060S / gfx1151)
- **Linux 6.17+** avec Mesa 25.2.8+
- **Python 3.11+**
- **Git**
- **ROCmFPX** (compilé via le script de build — l'app peut le faire)

## Installation

```bash
# 1. Cloner
git clone https://github.com/Yohan30/ROCmFP4-Manager.git
cd ROCmFP4-Manager

# 2. Installer les dépendances Python
pip install -r requirements.txt

# 3. Lancer
python src/main.py
```

L'application détectera si ROCmFPX est installé et proposera de le cloner/compiler.

## Utilisation rapide

1. **Onglet ROCmFPX** → Cloner et compiler (première fois seulement)
2. **Onglet Modèles** → Rechercher et télécharger un modèle, ou importer depuis LM Studio
3. **Onglet Configuration** → Sélectionner le modèle, ajuster les paramètres
4. **Onglet Serveur** → Cliquer "Démarrer"
5. **Onglet Chat** → Discuter avec le modèle !

## Port par défaut

- Interface web + API : **`http://localhost:1412`**
- API chat : `http://localhost:1412/v1/chat/completions`

## Stack technique

- **Python 3** / **PySide6 (Qt6)**
- **ROCmFPX** (fork llama.cpp avec kernels AMD optimisés)
- **systemd** (auto-démarrage)
- **HuggingFace Hub** (téléchargement de modèles)

## Licence

MIT
