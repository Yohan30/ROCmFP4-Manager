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

# Lancer le serveur de recherche DuckDuckGo (port 8082) en arrière-plan
/home/Yohan/Bureau/DEV/.venv/bin/python3 "$(dirname "$0")/scripts/ddg_search_server.py" --port 8082 &
DDG_PID=$!
echo "🔍 DuckDuckGo Search lancé (PID $DDG_PID) sur le port 8082"

# Active le handler SSE qui utilise iter_chunks() (sans limite de ligne)
# au lieu de readline() (limité à 128 Ko par aiohttp). Une valeur haute
# (2 Mo) évite que les events response.completed volumineux soient tronqués.
export CHAT_STREAM_RESPONSE_CHUNK_MAX_BUFFER_SIZE=2097152

# Web Search native OpenWebUI → DuckDuckGo intégré (gratuit, zero API key, zero proxy)
export ENABLE_WEB_SEARCH=true
export WEB_SEARCH_ENGINE=duckduckgo

exec ~/open-webui-env/bin/open-webui serve --host 0.0.0.0 --port 8080
