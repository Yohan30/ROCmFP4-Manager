#!/bin/bash
set -e

echo "=============================="
echo " ROCmFP4 Manager - Install"
echo "=============================="

# Vérifier Python
PYTHON=$(which python3 || which python)
if [ -z "$PYTHON" ]; then
    echo "❌ Python 3 requis"
    exit 1
fi

echo "🔍 Python: $($PYTHON --version)"

# Vérifier git
if ! which git > /dev/null 2>&1; then
    echo "❌ Git requis"
    exit 1
fi

# Vérifier systemd
if ! which systemctl > /dev/null 2>&1; then
    echo "⚠️ systemd non trouvé (optionnel pour l'auto-démarrage)"
fi

# Se placer dans le dossier du script
cd "$(dirname "$0")/.."
ROOT=$(pwd)

echo "📁 Installation dans: $ROOT"

# Créer venv
VENV="$ROOT/venv"
if [ ! -d "$VENV" ]; then
    echo "📦 Création de l'environnement virtuel..."
    $PYTHON -m venv "$VENV"
fi

echo "📦 Installation des dépendances..."
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -r "$ROOT/requirements.txt" -q

echo ""
echo "=============================="
echo " ✅ Installation terminée !"
echo "=============================="
echo ""
echo "Pour lancer l'application :"
echo "  $VENV/bin/python src/main.py"
echo ""
echo "Ou directement :"
echo "  cd $ROOT && ./venv/bin/python src/main.py"
