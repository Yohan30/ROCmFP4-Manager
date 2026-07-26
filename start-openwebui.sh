#!/bin/bash
# Script pour lancer Open WebUI avec l'API ROCmFP4-Manager
# Open WebUI sera accessible sur : http://192.168.8.64:8080

cd "$(dirname "$0")"

# Vérifier que ROCmFP4-Manager est en cours (port 1412)
if ! curl -s -o /dev/null "http://127.0.0.1:1412/health" 2>/dev/null; then
    echo "⚠️  ROCmFP4-Manager ne semble pas actif sur http://127.0.0.1:1412"
    echo "   Lance d'abord le serveur depuis l'onglet Server de ROCmFP4-Manager"
    echo ""
fi

echo "🚀 Démarrage d'Open WebUI..."
echo "   Interface : http://192.168.8.64:8080"
echo "   API ROCmFP4 : http://127.0.0.1:1412"
echo "   Clé API : 141283"
echo ""

exec ~/open-webui-env/bin/open-webui serve --host 0.0.0.0 --port 8080
