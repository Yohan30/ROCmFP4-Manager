"""Adaptateur OpenAI Responses API → Chat Completions API.

Traduit les requêtes du format Responses API vers le format Chat Completions
compris par llama-server (ROCmFPX), et inversement pour les réponses.

Endpoints exposés :
    POST /v1/responses          — Créer une réponse (streaming ou non)
    GET  /v1/responses/{id}     — Récupérer une réponse stockée
    DELETE /v1/responses/{id}   — Supprimer une réponse stockée
"""

import json
import re
import time
import uuid
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Optional
from urllib.parse import urlparse

import requests


# ---------------------------------------------------------------------------
# Serveur HTTP multi-thread
# ---------------------------------------------------------------------------

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """HTTPServer avec un thread par requête (évite le blocage)."""
    daemon_threads = True


# ---------------------------------------------------------------------------
# Génération d'IDs
# ---------------------------------------------------------------------------

def _gen_response_id() -> str:
    return "resp_" + uuid.uuid4().hex + uuid.uuid4().hex[:8]


def _gen_item_id(prefix: str = "msg") -> str:
    return f"{prefix}_" + uuid.uuid4().hex + uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Traducteur de requêtes
# ---------------------------------------------------------------------------

class RequestTranslator:
    """Convertit une requête Responses API en requête Chat Completions."""

    @staticmethod
    def translate(responses_body: dict) -> dict:
        """Transforme le body Responses en body Chat Completions."""
        chat_body: dict = {}

        # --- model ---
        if "model" in responses_body:
            chat_body["model"] = responses_body["model"]

        # --- messages ---
        messages = RequestTranslator._build_messages(responses_body)
        chat_body["messages"] = messages

        # --- temperature ---
        if "temperature" in responses_body:
            chat_body["temperature"] = responses_body["temperature"]

        # --- max_output_tokens → max_tokens ---
        if "max_output_tokens" in responses_body:
            chat_body["max_tokens"] = responses_body["max_output_tokens"]

        # --- top_p ---
        if "top_p" in responses_body:
            chat_body["top_p"] = responses_body["top_p"]

        # --- stream ---
        if "stream" in responses_body:
            chat_body["stream"] = responses_body["stream"]

        # --- text.format → response_format ---
        text_config = responses_body.get("text", {})
        text_format = text_config.get("format", {})
        if text_format:
            fmt_type = text_format.get("type", "")
            if fmt_type == "json_schema":
                chat_body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": text_format.get("name", "response"),
                        "strict": text_format.get("strict", True),
                        "schema": text_format.get("schema", {}),
                    },
                }
            elif fmt_type == "json_object":
                chat_body["response_format"] = {"type": "json_object"}

        # --- tools ---
        tools = responses_body.get("tools", [])
        if tools:
            chat_tools = RequestTranslator._translate_tools(tools)
            if chat_tools:
                chat_body["tools"] = chat_tools

        # --- tool_choice ---
        if "tool_choice" in responses_body:
            tc = responses_body["tool_choice"]
            if isinstance(tc, str):
                if tc in ("none", "auto", "required"):
                    chat_body["tool_choice"] = tc
            elif isinstance(tc, dict):
                chat_body["tool_choice"] = tc

        # --- top_logprobs ---
        if "top_logprobs" in responses_body:
            chat_body["top_logprobs"] = responses_body["top_logprobs"]

        return chat_body

    @staticmethod
    def _build_messages(body: dict) -> list[dict]:
        """Construit le tableau 'messages' à partir du body Responses."""
        messages: list[dict] = []

        # 1. instructions → system message
        instructions = body.get("instructions", "")
        if instructions:
            messages.append({"role": "system", "content": instructions})

        # 2. input → user/assistant messages
        raw_input = body.get("input")

        if raw_input is None:
            return messages

        # Cas 1: string simple
        if isinstance(raw_input, str):
            messages.append({"role": "user", "content": raw_input})
            return messages

        # Cas 2: liste d'Items
        if isinstance(raw_input, list):
            for item in raw_input:
                item_type = item.get("type", "message")
                if item_type == "message":
                    role = item.get("role", "user")
                    content = RequestTranslator._extract_content(item)
                    messages.append({"role": role, "content": content})
                elif item_type == "function_call":
                    # On ne peut pas représenter ça comme un message standard,
                    # donc on l'ignore pour le moment
                    pass
                elif item_type == "function_call_output":
                    call_id = item.get("call_id", "")
                    output = item.get("output", "")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": str(output) if not isinstance(output, str) else output,
                    })

        return messages

    @staticmethod
    def _extract_content(item: dict) -> str | list[dict]:
        """Extrait le contenu d'un Item message (texte ou multimodal)."""
        content = item.get("content", "")

        # Cas: string simple
        if isinstance(content, str):
            return content

        # Cas: liste de content parts
        if isinstance(content, list):
            parts = []
            for part in content:
                part_type = part.get("type", "")
                if part_type == "input_text" or part_type == "output_text":
                    parts.append({"type": "text", "text": part.get("text", "")})
                elif part_type == "input_image":
                    parts.append({
                        "type": "image_url",
                        "image_url": {"url": part.get("image_url", "")},
                    })
            return parts if parts else ""

        return str(content)

    @staticmethod
    def _translate_tools(tools: list) -> list[dict]:
        """Traduit les tools Responses vers le format Chat Completions."""
        chat_tools = []
        for tool in tools:
            tool_type = tool.get("type", "")
            if tool_type == "function":
                chat_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.get("name", ""),
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {}),
                        "strict": tool.get("strict", True),
                    },
                })
            # Les outils natifs (web_search, file_search, etc.) sont ignorés
            # car llama-server ne les supporte pas nativement.
        return chat_tools


# ---------------------------------------------------------------------------
# Traducteur de réponses
# ---------------------------------------------------------------------------

class ResponseTranslator:
    """Convertit une réponse Chat Completions en réponse Responses API."""

    @staticmethod
    def translate(chat_response: dict, request_body: dict) -> dict:
        """Transforme une réponse Chat Completions en réponse Responses."""
        response_id = _gen_response_id()
        model = chat_response.get("model", request_body.get("model", "unknown"))
        created_at = chat_response.get("created", int(time.time()))

        output_items = ResponseTranslator._build_output_items(chat_response)

        resp: dict = {
            "id": response_id,
            "object": "response",
            "created_at": created_at,
            "model": model,
            "status": "completed",
            "output": output_items,
            "output_text": ResponseTranslator._extract_text(output_items),
            "usage": ResponseTranslator._translate_usage(chat_response.get("usage")),
            "temperature": request_body.get("temperature"),
            "top_p": request_body.get("top_p"),
            "max_output_tokens": request_body.get("max_output_tokens"),
            "tools": request_body.get("tools", []),
        }

        # Report des champs optionnels
        for key in ("instructions", "text", "tool_choice", "parallel_tool_calls"):
            if key in request_body:
                resp[key] = request_body[key]

        return resp

    @staticmethod
    def _build_output_items(chat_response: dict) -> list[dict]:
        """Construit le tableau 'output' à partir d'une réponse Chat Completions."""
        items: list[dict] = []
        choices = chat_response.get("choices", [])

        for choice in choices:
            msg = choice.get("message", {})
            finish_reason = choice.get("finish_reason", "stop")

            # Reasoning/thinking (DeepSeek, Laguna, etc.)
            reasoning = msg.get("reasoning_content", "")
            if reasoning:
                items.append({
                    "id": _gen_item_id("rs"),
                    "type": "reasoning",
                    "status": "completed",
                    "content": [
                        {"type": "reasoning_text", "text": reasoning, "annotations": []}
                    ],
                })

            # Message texte - toujours présent, utilise le reasoning comme fallback si content vide
            content = msg.get("content", "")
            display_text = content if content else reasoning
            item_id = _gen_item_id("msg")
            output_item: dict = {
                "id": item_id,
                "type": "message",
                "role": "assistant",
                "status": "completed" if finish_reason == "stop" else "in_progress",
                "content": [
                    {
                        "type": "output_text",
                        "text": display_text,
                        "annotations": [],
                        "logprobs": [],
                    }
                ],
            }
            items.append(output_item)

            # Tool calls
            tool_calls = msg.get("tool_calls", [])
            for tc in tool_calls:
                fc_item = {
                    "id": _gen_item_id("fc"),
                    "type": "function_call",
                    "call_id": tc.get("id", ""),
                    "name": tc.get("function", {}).get("name", ""),
                    "arguments": tc.get("function", {}).get("arguments", "{}"),
                    "status": "completed",
                }
                items.append(fc_item)

        return items

    @staticmethod
    def _extract_text(output_items: list[dict]) -> str:
        """Extrait le texte concaténé des output_items (reasoning + message)."""
        texts = []
        for item in output_items:
            if item.get("type") == "reasoning":
                for content_part in item.get("content", []):
                    if content_part.get("type") == "reasoning_text":
                        texts.append(content_part.get("text", ""))
            elif item.get("type") == "message":
                for content_part in item.get("content", []):
                    if content_part.get("type") == "output_text":
                        t = content_part.get("text", "")
                        if t:
                            texts.append(t)
        return "\n".join(texts) if texts else (output_items[-1].get("content", [{}])[-1].get("text", "") if output_items else "")

    @staticmethod
    def _translate_usage(usage: dict | None) -> dict:
        """Traduit le usage Chat Completions vers le format Responses."""
        if not usage:
            return {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 0},
            }
        return {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "input_tokens_details": {
                "cached_tokens": usage.get("prompt_tokens_details", {}).get("cached_tokens", 0),
                "cache_write_tokens": 0,
            },
            "output_tokens_details": {
                "reasoning_tokens": usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0),
            },
        }


# ---------------------------------------------------------------------------
# Gestionnaire de streaming
# ---------------------------------------------------------------------------

class StreamTranslator:
    """Convertit un flux SSE Chat Completions en flux SSE Responses."""

    @staticmethod
    def translate_events(chat_sse_line: str, reasoning_item_id: str,
                          message_item_id: str) -> list[str]:
        """Traduit une ligne SSE Chat Completions en événements Responses.

        Retourne une liste de chaînes SSE à envoyer.
        """
        if not chat_sse_line.startswith("data: "):
            return []

        data_str = chat_sse_line[6:]
        if data_str.strip() == "[DONE]":
            # La fin est gérée par _handle_stream après la boucle
            return []

        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            return []

        events: list[str] = []
        choices = data.get("choices", [])
        if not choices:
            return events

        choice = choices[0]
        delta = choice.get("delta", {})
        finish_reason = choice.get("finish_reason")

        # Token de reasoning (DeepSeek, Laguna...)
        reasoning = delta.get("reasoning_content", "")
        if reasoning:
            events.append(
                f"event: response.reasoning_text.delta\n"
                f"data: {json.dumps({'type': 'response.reasoning_text.delta', 'item_id': reasoning_item_id, 'output_index': 0, 'content_index': 0, 'delta': reasoning}, ensure_ascii=False)}\n\n"
            )

        # Token de texte
        content = delta.get("content", "")
        if content:
            events.append(
                f"event: response.output_text.delta\n"
                f"data: {json.dumps({'type': 'response.output_text.delta', 'item_id': message_item_id, 'output_index': 0, 'content_index': 0, 'delta': content}, ensure_ascii=False)}\n\n"
            )

        # Fin du contenu + fin de l'output item
        # NOTE: ces événements sont émis depuis _handle_stream après la boucle,
        # avec le texte complet accumulé. On ne les émet pas ici car on n'a pas
        # le texte complet à ce stade.
        if finish_reason:
            pass  # _handle_stream s'en charge

        # Tool calls en streaming
        tool_calls = delta.get("tool_calls", [])
        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name")
            args = func.get("arguments", "")
            tc_id = tc.get("id", "")
            if name:
                events.append(
                    f"event: response.function_call_arguments.done\n"
                    f"data: {json.dumps({'type': 'response.function_call_arguments.done', 'item_id': tc_id, 'output_index': 0, 'call_id': tc_id, 'name': name, 'arguments': args}, ensure_ascii=False)}\n\n"
                )
            elif args:
                events.append(
                    f"event: response.function_call_arguments.delta\n"
                    f"data: {json.dumps({'type': 'response.function_call_arguments.delta', 'item_id': tc_id, 'output_index': 0, 'delta': args}, ensure_ascii=False)}\n\n"
                )

        return events


# ---------------------------------------------------------------------------
# Stockage des réponses (pour previous_response_id)
# ---------------------------------------------------------------------------

class ResponseStore:
    """Stocke en mémoire les réponses pour le state management."""

    def __init__(self, max_stored: int = 100):
        self._store: dict[str, dict] = {}
        self._max = max_stored
        self._lock = threading.Lock()

    def put(self, response_id: str, response: dict, input_items: list[dict]):
        with self._lock:
            if len(self._store) >= self._max:
                # Supprimer le plus ancien
                oldest = next(iter(self._store))
                del self._store[oldest]
            self._store[response_id] = {
                "response": response,
                "input_items": input_items,
            }

    def get(self, response_id: str) -> dict | None:
        with self._lock:
            return self._store.get(response_id)

    def delete(self, response_id: str) -> bool:
        with self._lock:
            if response_id in self._store:
                del self._store[response_id]
                return True
            return False

    def get_input_items(self, response_id: str) -> list[dict]:
        """Récupère les input_items + output_items pour reconstruire le contexte."""
        entry = self.get(response_id)
        if not entry:
            return []
        items = list(entry.get("input_items", []))
        # Ajouter les output items de la réponse précédente
        output = entry.get("response", {}).get("output", [])
        items.extend(output)
        return items


# ---------------------------------------------------------------------------
# Serveur HTTP
# ---------------------------------------------------------------------------

class ResponsesHandler(BaseHTTPRequestHandler):
    """Handler HTTP pour le proxy Responses API."""

    protocol_version = "HTTP/1.1"

    # Référence vers l'adaptateur (set par le serveur)
    adapter: "ResponsesAdapter" = None

    def log_message(self, format, *args):
        """Override pour logger dans l'adapter plutôt que stderr."""
        if self.adapter:
            self.adapter._log(f"[ResponsesProxy] {args[0]}", *args[1:])

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: int, code: str, message: str):
        self._send_json(status, {
            "error": {"code": code, "message": message, "type": code},
        })

    # --- Helpers pour émettre des événements SSE ---

    def _emit_output_item_added(self, item_id: str, item_type: str, output_index: int, role: str = ""):
        """Émet response.output_item.added."""
        item: dict = {
            "id": item_id, "object": "realtime.item",
            "type": item_type, "status": "in_progress", "content": [],
        }
        if role:
            item["role"] = role
        event = json.dumps({
            "type": "response.output_item.added",
            "output_index": output_index,
            "item": item,
        }, ensure_ascii=False)
        self.wfile.write(f"event: response.output_item.added\ndata: {event}\n\n".encode("utf-8"))

    def _emit_content_part_added(self, item_id: str, output_index: int, content_index: int, part_type: str):
        """Émet response.content_part.added."""
        event = json.dumps({
            "type": "response.content_part.added",
            "item_id": item_id,
            "output_index": output_index,
            "content_index": content_index,
            "part": {"type": part_type, "text": "", "annotations": []},
        }, ensure_ascii=False)
        self.wfile.write(f"event: response.content_part.added\ndata: {event}\n\n".encode("utf-8"))

    def _emit_content_part_done(self, item_id: str, output_index: int, content_index: int, part_type: str, text: str):
        """Émet response.content_part.done."""
        event = json.dumps({
            "type": "response.content_part.done",
            "item_id": item_id,
            "output_index": output_index,
            "content_index": content_index,
            "part": {"type": part_type, "text": text, "annotations": []},
        }, ensure_ascii=False)
        self.wfile.write(f"event: response.content_part.done\ndata: {event}\n\n".encode("utf-8"))

    def _emit_output_item_done(self, item_id: str, output_index: int, item_type: str, text: str, role: str = ""):
        """Émet response.output_item.done."""
        item: dict = {
            "id": item_id, "object": "realtime.item",
            "type": item_type, "status": "completed",
            "content": [{"type": f"{item_type}_text" if item_type == "reasoning" else "output_text", "text": text, "annotations": []}],
        }
        if role:
            item["role"] = role
        event = json.dumps({
            "type": "response.output_item.done",
            "output_index": output_index,
            "item": item,
        }, ensure_ascii=False)
        self.wfile.write(f"event: response.output_item.done\ndata: {event}\n\n".encode("utf-8"))

    def _proxy_get(self, path: str):
        """Proxy une requête GET vers le serveur llama-server principal."""
        try:
            # Forwarder les headers d'auth du client
            headers = {}
            auth = self.headers.get("Authorization", "")
            if auth:
                headers["Authorization"] = auth
            elif self.adapter.api_key:
                headers["Authorization"] = f"Bearer {self.adapter.api_key}"

            resp = requests.get(
                self.adapter.chat_url.rsplit("/v1/", 1)[0] + path,
                headers=headers,
                timeout=10,
            )
            body = resp.content
            self.send_response(resp.status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
        except requests.RequestException as e:
            self._send_error_json(502, "proxy_error", f"Failed to reach upstream server: {e}")

    def do_OPTIONS(self):
        """CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        self.adapter._log(f"[REQ] GET {parsed.path} from {self.client_address[0]}")

        # GET / → info service
        if parsed.path == "/" or parsed.path == "":
            self._send_json(200, {
                "object": "list",
                "data": [
                    {"id": "responses", "object": "endpoint", "url": "/v1/responses"},
                    {"id": "models", "object": "endpoint", "url": "/v1/models"},
                ],
            })
            return

        # GET /health
        if parsed.path == "/health":
            self._send_json(200, {"status": "ok", "proxy": "ResponsesAdapter"})
            return

        # GET /logs → debug
        if parsed.path == "/logs":
            self._send_json(200, {"logs": self.adapter.logs})
            return

        # GET /v1 → endpoints disponibles
        if parsed.path == "/v1" or parsed.path == "/v1/":
            self._send_json(200, {
                "object": "list",
                "data": [
                    {"object": "endpoint", "url": "/v1/responses", "methods": ["POST"]},
                    {"object": "endpoint", "url": "/v1/responses/{id}", "methods": ["GET", "DELETE"]},
                    {"object": "endpoint", "url": "/v1/models", "methods": ["GET"]},
                ],
            })
            return

        # GET /v1/responses → info (navigateur)
        if parsed.path == "/v1/responses" or parsed.path == "/v1/responses/" or parsed.path == "/responses" or parsed.path == "/responses/":
            self._send_json(200, {
                "service": "ROCmFP4 Manager — OpenAI Responses API Adapter",
                "version": "0.3.0",
                "endpoint": "/v1/responses",
                "method": "POST",
                "docs": "https://platform.openai.com/docs/api-reference/responses",
                "example": 'curl -X POST http://HOST:1413/v1/responses -H "Content-Type: application/json" -d \'{"model":"MODEL","input":"Hello"}\'',
                "note": "This endpoint only accepts POST requests. Use a proper API client, not a browser."
            })
            return

        # GET /v1/models → proxy vers le serveur principal
        if parsed.path == "/v1/models":
            self._proxy_get("/v1/models")
            return

        # Alias: GET /models → proxy (compatibilité clients qui n'utilisent pas /v1)
        if parsed.path == "/models":
            self._proxy_get("/v1/models")
            return

        # GET /v1/responses/{id}
        match = re.match(r"^/v1/responses/(resp_[a-f0-9]+)$", parsed.path)
        if match:
            response_id = match.group(1)
            entry = self.adapter.store.get(response_id)
            if entry:
                self._send_json(200, entry["response"])
            else:
                self._send_error_json(404, "not_found", f"Response '{response_id}' not found")
            return

        self._send_error_json(404, "not_found", f"Unknown endpoint: {parsed.path}")

    def do_DELETE(self):
        parsed = urlparse(self.path)
        match = re.match(r"^/v1/responses/(resp_[a-f0-9]+)$", parsed.path)
        if match:
            response_id = match.group(1)
            deleted = self.adapter.store.delete(response_id)
            if deleted:
                self._send_json(200, {"id": response_id, "object": "response.deleted", "deleted": True})
            else:
                self._send_error_json(404, "not_found", f"Response '{response_id}' not found")
            return

        self._send_error_json(404, "not_found", f"Unknown endpoint: {parsed.path}")

    def do_POST(self):
        parsed = urlparse(self.path)
        self.adapter._log(f"[REQ] POST {parsed.path} from {self.client_address[0]}")

        # Accepter /v1/responses et /responses (alias)
        if parsed.path != "/v1/responses" and parsed.path != "/responses":
            self._send_error_json(404, "not_found", f"Unknown endpoint: {parsed.path}")
            return

        # Lire le body
        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length)) if content_length > 0 else {}

        # Injecter le previous_response_id dans l'input si présent
        previous_id = body.get("previous_response_id")
        if previous_id:
            prev_items = self.adapter.store.get_input_items(previous_id)
            if prev_items:
                current_input = body.get("input", [])
                if isinstance(current_input, str):
                    current_input = [{"type": "message", "role": "user", "content": current_input}]
                elif not isinstance(current_input, list):
                    current_input = []
                body["input"] = prev_items + current_input

        # Traduire la requête
        try:
            chat_body = RequestTranslator.translate(body)
        except Exception as e:
            self._send_error_json(400, "invalid_request", f"Failed to translate request: {e}")
            return

        # Auth header à propager
        auth_header = self.headers.get("Authorization", "")
        headers = {"Content-Type": "application/json"}
        if auth_header:
            headers["Authorization"] = auth_header
        elif self.adapter.api_key:
            headers["Authorization"] = f"Bearer {self.adapter.api_key}"

        stream = body.get("stream", False)

        if stream:
            self._handle_stream(chat_body, headers, body)
        else:
            self._handle_sync(chat_body, headers, body)

    def _handle_sync(self, chat_body: dict, headers: dict, original_body: dict):
        """Gère une requête non-streaming."""
        try:
            resp = requests.post(
                self.adapter.chat_url,
                json=chat_body,
                headers=headers,
                timeout=300,
            )
        except requests.RequestException as e:
            self._send_error_json(502, "upstream_error", f"Chat API unavailable: {e}")
            return

        if resp.status_code != 200:
            self._send_error_json(
                502, "upstream_error",
                f"Chat API returned {resp.status_code}: {resp.text[:500]}",
            )
            return

        try:
            chat_response = resp.json()
        except json.JSONDecodeError:
            self._send_error_json(502, "invalid_upstream", "Chat API returned invalid JSON")
            return

        # Traduire la réponse
        try:
            responses_resp = ResponseTranslator.translate(chat_response, original_body)
        except Exception as e:
            self._send_error_json(500, "translation_error", f"Failed to translate response: {e}")
            return

        # Stocker pour previous_response_id
        store = original_body.get("store", True)
        if store:
            input_items = self._extract_input_items(original_body)
            self.adapter.store.put(responses_resp["id"], responses_resp, input_items)

        self._send_json(200, responses_resp)

    def _handle_stream(self, chat_body: dict, headers: dict, original_body: dict):
        """Gère une requête streaming avec traduction SSE."""
        response_id = _gen_response_id()

        try:
            resp = requests.post(
                self.adapter.chat_url,
                json=chat_body,
                headers=headers,
                stream=True,
                timeout=300,
            )
        except requests.RequestException as e:
            self._send_error_json(502, "upstream_error", f"Chat API unavailable: {e}")
            return

        if resp.status_code != 200:
            self._send_error_json(
                502, "upstream_error",
                f"Chat API returned {resp.status_code}: {resp.text[:500]}",
            )
            return

        # Forcer UTF-8 : llama-server ne met pas toujours charset=utf-8 dans
        # le header SSE, et requests décode alors en Latin-1 → double encodage.
        resp.encoding = "utf-8"

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        # IDs séparés pour reasoning et message (spec Responses API)
        reasoning_item_id = _gen_item_id("rs")
        message_item_id = _gen_item_id("msg")

        # État du stream
        reasoning_started = False   # output_item.added émis pour reasoning ?
        reasoning_ended = False     # output_item.done émis pour reasoning ?
        message_started = False     # output_item.added émis pour message ?

        # Événement initial: response.created
        created_event = json.dumps({
            "type": "response.created",
            "response": {
                "id": response_id,
                "object": "response",
                "status": "in_progress",
                "output": [],
            },
        }, ensure_ascii=False)
        self.wfile.write(f"event: response.created\ndata: {created_event}\n\n".encode("utf-8"))
        self.wfile.flush()

        # Événement: response.in_progress
        in_progress_event = json.dumps({
            "type": "response.in_progress",
            "response": {"id": response_id, "object": "response", "status": "in_progress"},
        }, ensure_ascii=False)
        self.wfile.write(f"event: response.in_progress\ndata: {in_progress_event}\n\n".encode("utf-8"))
        self.wfile.flush()

        # On n'émet PAS les output_item.added/content_part.added upfront.
        # Ils seront émis dynamiquement quand le premier delta arrive
        # (reasoning → reasoning item, puis texte → message item).

        accumulated_text = ""
        accumulated_reasoning = ""

        try:
            for line in resp.iter_lines(decode_unicode=True):
                if line:
                    sse_events = StreamTranslator.translate_events(
                        line, reasoning_item_id, message_item_id
                    )
                    for event_str in sse_events:
                        # Détecter le type de delta pour gérer les transitions
                        if "response.reasoning_text.delta" in event_str:
                            if not reasoning_started:
                                # Premier delta reasoning → créer l'item reasoning
                                reasoning_started = True
                                self._emit_output_item_added(reasoning_item_id, "reasoning", 0)
                                self._emit_content_part_added(reasoning_item_id, 0, 0, "reasoning_text")
                                self.wfile.flush()

                        elif "response.output_text.delta" in event_str:
                            if not message_started:
                                # Fin du reasoning si actif
                                if reasoning_started and not reasoning_ended:
                                    reasoning_ended = True
                                    self._emit_content_part_done(reasoning_item_id, 0, 0, "reasoning_text", accumulated_reasoning)
                                    self._emit_output_item_done(reasoning_item_id, 0, "reasoning", accumulated_reasoning)
                                # Créer l'item message
                                message_started = True
                                output_idx = 1 if reasoning_started else 0
                                self._emit_output_item_added(message_item_id, "message", output_idx, role="assistant")
                                self._emit_content_part_added(message_item_id, output_idx, 0, "output_text")
                                self.wfile.flush()

                        self.wfile.write(event_str.encode("utf-8"))
                        self.wfile.flush()

                        # Accumuler le texte
                        if "response.output_text.delta" in event_str:
                            try:
                                delta_data = json.loads(event_str.split("\n")[1].replace("data: ", ""))
                                accumulated_text += delta_data.get("delta", "")
                            except Exception:
                                pass
                        elif "response.reasoning_text.delta" in event_str:
                            try:
                                delta_data = json.loads(event_str.split("\n")[1].replace("data: ", ""))
                                accumulated_reasoning += delta_data.get("delta", "")
                            except Exception:
                                pass
        except Exception:
            pass

        # --- Événements de fin de stream (avec le texte complet accumulé) ---
        try:
            output_items = []

            # Si le reasoning a été commencé mais pas terminé (fin de stream)
            if reasoning_started and not reasoning_ended:
                reasoning_ended = True
                self._emit_content_part_done(reasoning_item_id, 0, 0, "reasoning_text", accumulated_reasoning)
                self._emit_output_item_done(reasoning_item_id, 0, "reasoning", accumulated_reasoning)
                self.wfile.flush()

            # Si aucun message n'a été commencé (pas de output_text du tout)
            if not message_started:
                if accumulated_text:
                    output_idx = 1 if reasoning_started else 0
                    self._emit_output_item_added(message_item_id, "message", output_idx, role="assistant")
                    self._emit_content_part_added(message_item_id, output_idx, 0, "output_text")
                    self.wfile.flush()
                message_started = True

            # Ajouter l'item reasoning à l'output si présent
            if reasoning_started:
                output_items.append({
                    "id": reasoning_item_id,
                    "object": "realtime.item",
                    "type": "reasoning",
                    "status": "completed",
                    "content": [{"type": "reasoning_text", "text": accumulated_reasoning, "annotations": []}],
                })

            # Finaliser l'item message
            msg_output_idx = 1 if reasoning_started else 0
            self._emit_content_part_done(message_item_id, msg_output_idx, 0, "output_text", accumulated_text)
            self._emit_output_item_done(message_item_id, msg_output_idx, "message", accumulated_text, role="assistant")
            self.wfile.flush()

            # Construire l'output pour response.completed
            msg_item = {
                "id": message_item_id,
                "object": "realtime.item",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": accumulated_text, "annotations": []}],
            }
            output_items.append(msg_item)

            # 3. response.completed
            response_completed = json.dumps({
                "type": "response.completed",
                "response": {
                    "id": response_id,
                    "object": "response",
                    "status": "completed",
                    "output": output_items,
                    "output_text": accumulated_text,
                    "usage": {"input_tokens": 0, "output_tokens": len(accumulated_text.split()), "total_tokens": 0},
                },
            }, ensure_ascii=False)
            self.wfile.write(f"event: response.completed\ndata: {response_completed}\n\n".encode("utf-8"))
            self.wfile.flush()

            # 4. [DONE]
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except Exception:
            pass

        # Stocker la réponse complète si demandé
        store = original_body.get("store", True)
        if store:
            stored_output = []
            if reasoning_started:
                stored_output.append({
                    "id": reasoning_item_id,
                    "type": "reasoning",
                    "status": "completed",
                    "content": [{"type": "reasoning_text", "text": accumulated_reasoning, "annotations": []}],
                })
            stored_output.append({
                "id": message_item_id,
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": accumulated_text, "annotations": [], "logprobs": []}],
            })
            stored_response = {
                "id": response_id,
                "object": "response",
                "status": "completed",
                "output": stored_output,
                "output_text": accumulated_text,
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            }
            input_items = self._extract_input_items(original_body)
            self.adapter.store.put(response_id, stored_response, input_items)

    def _extract_input_items(self, body: dict) -> list[dict]:
        """Extrait les input items normalisés depuis le body."""
        raw_input = body.get("input", [])
        if isinstance(raw_input, str):
            return [{"type": "message", "role": "user", "content": raw_input}]
        if isinstance(raw_input, list):
            return raw_input
        return []


# ---------------------------------------------------------------------------
# Adaptateur principal
# ---------------------------------------------------------------------------

class ResponsesAdapter:
    """Proxy Responses API → Chat Completions API.

    Usage:
        adapter = ResponsesAdapter(chat_url="http://localhost:1412/v1/chat/completions")
        adapter.start(port=1413)  # écoute sur le port 1413
        # ... utiliser ...
        adapter.stop()
    """

    def __init__(self, chat_url: str = "http://127.0.0.1:1412/v1/chat/completions",
                  api_key: str = "", port: int = 1413, host: str = "127.0.0.1"):
        self.chat_url = chat_url
        self.api_key = api_key
        self.port = port
        self.host = host
        self.store = ResponseStore()
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._logs: list[str] = []

    def _log(self, msg: str, *args):
        try:
            log_line = msg % args if args else msg
        except (TypeError, ValueError):
            log_line = msg + " " + " ".join(str(a) for a in args) if args else msg
        self._logs.append(log_line)
        if len(self._logs) > 200:
            self._logs = self._logs[-200:]

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def logs(self) -> list[str]:
        return list(self._logs)

    def start(self):
        """Démarre le serveur proxy dans un thread séparé."""
        if self._running:
            return

        ResponsesHandler.adapter = self

        try:
            self._server = ThreadingHTTPServer((self.host, self.port), ResponsesHandler)
            self._server.allow_reuse_address = True
        except OSError as e:
            self._log(f"ResponsesAdapter FAILED to bind {self.host}:{self.port}: {e}")
            self._running = False
            return

        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self._running = True
        self._log(f"ResponsesAdapter started on http://{self.host}:{self.port}")

    def stop(self):
        """Arrête le serveur proxy (non-bloquant, force la fermeture)."""
        self._running = False
        server = self._server
        self._server = None
        if server:
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._log("ResponsesAdapter stopped")

    @property
    def responses_url(self) -> str:
        return f"http://{self.host}:{self.port}/v1/responses"
