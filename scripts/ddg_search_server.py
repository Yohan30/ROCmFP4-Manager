#!/usr/bin/env python3
"""Micro serveur de recherche DuckDuckGo → format SearXNG pour OpenWebUI.
Gratuit, zero API key, lancement: python ddg_search_server.py --port 8082
"""

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import sys
import os
import threading


class SearchHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        
        if parsed.path == "/health":
            self._json({"status": "ok"})
            return
            
        if parsed.path == "/search":
            params = parse_qs(parsed.query)
            query = params.get("q", [""])[0]
            fmt = params.get("format", ["html"])[0]
            
            if not query:
                self._json({"error": "missing query"})
                return
                
            try:
                from ddgs import DDGS
                results = []
                with DDGS() as ddgs:
                    for i, r in enumerate(ddgs.text(query, max_results=5)):
                        results.append({
                            "title": r.get("title", ""),
                            "url": r.get("href", ""),
                            "content": r.get("body", ""),
                            "score": 1.0 - (i * 0.1),  # score décroissant
                        })
                
                self._json({
                    "query": query,
                    "results": results,
                    "number_of_results": len(results),
                })
            except Exception as e:
                self._json({"error": str(e)}, 500)
            return
            
        self._json({"error": "not found"}, 404)

    def _json(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        pass  # silencieux


def main():
    port = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--port" else 8082
    server = HTTPServer(("127.0.0.1", port), SearchHandler)
    print(f"🔍 DuckDuckGo Search API → http://127.0.0.1:{port}/search?q=<query>&format=json")
    server.serve_forever()


if __name__ == "__main__":
    main()
