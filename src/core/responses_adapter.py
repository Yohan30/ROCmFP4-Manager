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
from typing import Optional
from urllib.parse import urlparse

import requests


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

            # Message texte
            content = msg.get("content", "")
            item_id = _gen_item_id("msg")

            output_item: dict = {
                "id": item_id,
                "type": "message",
                "role": "assistant",
                "status": "completed" if finish_reason == "stop" else "in_progress",
                "content": [
                    {
                        "type": "output_text",
                        "text": content if content else "",
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
        """Extrait le texte concaténé des output_items."""
        texts = []
        for item in output_items:
            if item.get("type") == "message":
                for content_part in item.get("content", []):
                    if content_part.get("type") == "output_text":
                        texts.append(content_part.get("text", ""))
        return "\n".join(texts)

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
    def translate_events(chat_sse_line: str, response_id: str,
                          item_id: str, request_body: dict) -> list[str]:
        """Traduit une ligne SSE Chat Completions en événements Responses.

        Retourne une liste de chaînes SSE à envoyer.
        """
        if not chat_sse_line.startswith("data: "):
            return []

        data_str = chat_sse_line[6:]
        if data_str.strip() == "[DONE]":
            # Événement de fin
            return [
                f"event: response.completed\ndata: {json.dumps({'response': {'id': response_id, 'object': 'response', 'status': 'completed'}})}\n\n",
                f"data: [DONE]\n\n",
            ]

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

        # Token de texte
        content = delta.get("content", "")
        if content:
            events.append(
                f"event: response.output_text.delta\n"
                f"data: {json.dumps({'item_id': item_id, 'output_index': 0, 'content_index': 0, 'delta': content})}\n\n"
            )

        # Fin du message
        if finish_reason:
            events.append(
                f"event: response.output_item.done\n"
                f"data: {json.dumps({'item': {'id': item_id, 'type': 'message', 'role': 'assistant', 'status': 'completed'}})}\n\n"
            )

        # Tool calls en streaming
        tool_calls = delta.get("tool_calls", [])
        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name")
            args = func.get("arguments", "")
            if name:
                events.append(
                    f"event: response.function_call_arguments.done\n"
                    f"data: {json.dumps({'item_id': tc.get('id', ''), 'name': name, 'arguments': args})}\n\n"
                )
            elif args:
                events.append(
                    f"event: response.function_call_arguments.delta\n"
                    f"data: {json.dumps({'item_id': tc.get('id', ''), 'delta': args})}\n\n"
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

    # Référence vers l'adaptateur (set par le serveur)
    adapter: "ResponsesAdapter" = None

    def log_message(self, format, *args):
        """Override pour logger dans l'adapter plutôt que stderr."""
        if self.adapter:
            self.adapter._log(f"[ResponsesProxy] {args[0]}", *args[1:])

    def _send_json(self, status: int, data: dict):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _send_error_json(self, status: int, code: str, message: str):
        self._send_json(status, {
            "error": {"code": code, "message": message, "type": code},
        })

    def do_OPTIONS(self):
        """CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/health":
            self._send_json(200, {"status": "ok", "proxy": "ResponsesAdapter"})
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

        if parsed.path != "/v1/responses":
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
        store = body.get("store", True)
        if store:
            input_items = self._extract_input_items(original_body)
            self.adapter.store.put(responses_resp["id"], responses_resp, input_items)

        self._send_json(200, responses_resp)

    def _handle_stream(self, chat_body: dict, headers: dict, original_body: dict):
        """Gère une requête streaming avec traduction SSE."""
        response_id = _gen_response_id()
        item_id = _gen_item_id("msg")

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

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        # Événement initial: response.created
        created_event = json.dumps({
            "type": "response.created",
            "response": {
                "id": response_id,
                "object": "response",
                "status": "in_progress",
                "output": [],
            },
        })
        self.wfile.write(f"event: response.created\ndata: {created_event}\n\n".encode())
        self.wfile.flush()

        # Événement: response.in_progress
        self.wfile.write(
            f"event: response.in_progress\n"
            f"data: {json.dumps({'response': {'id': response_id, 'status': 'in_progress'}})}\n\n".encode()
        )
        self.wfile.flush()

        # Événement: output item added
        self.wfile.write(
            f"event: response.output_item.added\n"
            f"data: {json.dumps({'item': {'id': item_id, 'type': 'message', 'role': 'assistant', 'status': 'in_progress'}})}\n\n".encode()
        )
        self.wfile.flush()

        # Événement: content part added
        self.wfile.write(
            f"event: response.content_part.added\n"
            f"data: {json.dumps({'item_id': item_id, 'content_index': 0, 'part': {'type': 'output_text', 'text': '', 'annotations': []}})}\n\n".encode()
        )
        self.wfile.flush()

        accumulated_text = ""

        try:
            for line in resp.iter_lines(decode_unicode=True):
                if line:
                    sse_events = StreamTranslator.translate_events(
                        line, response_id, item_id, original_body
                    )
                    for event_str in sse_events:
                        self.wfile.write(event_str.encode())
                        self.wfile.flush()

                        # Accumuler le texte pour le stockage
                        if "response.output_text.delta" in event_str:
                            try:
                                delta_data = json.loads(event_str.split("\n")[1].replace("data: ", ""))
                                accumulated_text += delta_data.get("delta", "")
                            except Exception:
                                pass
        except Exception:
            pass

        # Stocker la réponse complète si demandé
        store = original_body.get("store", True)
        if store:
            output_item = {
                "id": item_id,
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": accumulated_text, "annotations": [], "logprobs": []}],
            }
            stored_response = {
                "id": response_id,
                "object": "response",
                "status": "completed",
                "output": [output_item],
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
                  api_key: str = "", port: int = 1413):
        self.chat_url = chat_url
        self.api_key = api_key
        self.port = port
        self.store = ResponseStore()
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._logs: list[str] = []

    def _log(self, msg: str, *args):
        log_line = msg % args if args else msg
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

        self._server = HTTPServer(("127.0.0.1", self.port), ResponsesHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self._running = True
        self._log(f"ResponsesAdapter started on http://127.0.0.1:{self.port}")

    def stop(self):
        """Arrête le serveur proxy."""
        if not self._running or not self._server:
            return
        self._server.shutdown()
        self._thread.join(timeout=5)
        self._running = False
        self._log("ResponsesAdapter stopped")

    @property
    def responses_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1/responses"
