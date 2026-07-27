"""Onglet Chat : interface de discussion intégrée."""

import json
import time
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTextEdit, QScrollArea, QFrame, QSplitter, QListWidget,
    QListWidgetItem, QLineEdit, QSpinBox, QDoubleSpinBox,
    QComboBox, QMessageBox, QApplication, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QUrl
from PySide6.QtGui import QFont, QTextCursor, QTextDocument, QIcon
from pathlib import Path

from src.utils.config import Config
from src.core.server_controller import ServerController


class LLMRequestThread(QThread):
    """Thread pour les requêtes API en streaming (Chat Completions)."""
    token_received = Signal(str)
    finished = Signal()
    error = Signal(str)

    def __init__(self, url: str, payload: dict, api_key: str = ""):
        super().__init__()
        self.url = url
        self.payload = payload
        self.api_key = api_key

    def run(self):
        import requests
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = requests.post(
                self.url, json=self.payload, headers=headers, stream=True, timeout=120
            )
            response.raise_for_status()

            for line in response.iter_lines(decode_unicode=True):
                if line:
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            choices = data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    self.token_received.emit(content)
                        except json.JSONDecodeError:
                            pass
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


class ResponsesRequestThread(QThread):
    """Thread pour les requêtes Responses API en streaming (SSE typé)."""
    token_received = Signal(str)
    finished = Signal()
    error = Signal(str)
    response_id_received = Signal(str)

    def __init__(self, url: str, payload: dict, api_key: str = ""):
        super().__init__()
        self.url = url
        self.payload = payload
        self.api_key = api_key

    def run(self):
        import requests
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = requests.post(
                self.url, json=self.payload, headers=headers, stream=True, timeout=120
            )
            response.raise_for_status()

            current_event = None
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue

                # Ligne event:
                if line.startswith("event: "):
                    current_event = line[7:].strip()
                    continue

                # Ligne data:
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        current_event = None
                        continue

                    # response.created → récupérer l'ID
                    if current_event == "response.created":
                        resp_id = data.get("response", {}).get("id", "")
                        if resp_id:
                            self.response_id_received.emit(resp_id)

                    # response.output_text.delta → token
                    elif current_event == "response.output_text.delta":
                        delta = data.get("delta", "")
                        if delta:
                            self.token_received.emit(delta)

                    # response.completed → fin
                    elif current_event == "response.completed":
                        break

                    current_event = None

            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


class ChatTab(QWidget):
    """Interface de chat complète intégrée."""

    def __init__(self, config: Config, server: ServerController):
        super().__init__()
        self.config = config
        self.server = server
        self._messages = []  # [{"role": "user"|"assistant", "content": str}]
        self._current_thread = None
        self._previous_response_id: str = ""  # Pour mode Responses stateful
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Splitter: historique (gauche) + chat (droite)
        splitter = QSplitter(Qt.Horizontal)

        # === Barre latérale d'historique ===
        history_widget = QWidget()
        history_layout = QVBoxLayout(history_widget)
        history_layout.setContentsMargins(4, 4, 4, 4)

        self.new_chat_btn = QPushButton("➕ New Chat")
        self.new_chat_btn.clicked.connect(self._new_chat)
        history_layout.addWidget(self.new_chat_btn)

        self.search_history = QLineEdit()
        self.search_history.setPlaceholderText("🔍 Search...")
        history_layout.addWidget(self.search_history)

        self.history_list = QListWidget()
        self.history_list.setMaximumWidth(200)
        history_layout.addWidget(self.history_list, 1)

        splitter.addWidget(history_widget)

        # === Zone de chat ===
        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)
        chat_layout.setContentsMargins(8, 8, 8, 8)

        # Zone des messages (scroll)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.messages_container = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setAlignment(Qt.AlignTop)
        self.messages_layout.setSpacing(8)
        self.scroll_area.setWidget(self.messages_container)

        chat_layout.addWidget(self.scroll_area, 1)

        # Indicateur d'écriture
        self.writing_indicator = QLabel("")
        self.writing_indicator.setVisible(False)
        chat_layout.addWidget(self.writing_indicator)

        # Barre de saisie
        input_frame = QFrame()
        input_frame.setFrameShape(QFrame.StyledPanel)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(8, 8, 8, 8)

        self.input_edit = QTextEdit()
        self.input_edit.setPlaceholderText("💬 Type your question here...")
        self.input_edit.setMaximumHeight(120)
        self.input_edit.setMinimumHeight(50)
        self.input_edit.setAcceptRichText(False)
        input_layout.addWidget(self.input_edit, 1)

        self.send_btn = QPushButton("📤")
        self.send_btn.setFixedSize(40, 40)
        self.send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self.send_btn)

        self.stop_btn = QPushButton("⏹")
        self.stop_btn.setFixedSize(40, 40)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_generation)
        input_layout.addWidget(self.stop_btn)

        chat_layout.addWidget(input_frame)

        # Paramètres rapides
        params_layout = QHBoxLayout()
        params_layout.setSpacing(8)

        params_layout.addWidget(QLabel("Modèle:"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(150)
        params_layout.addWidget(self.model_combo)

        params_layout.addWidget(QLabel("T:"))
        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 2.0)
        self.temp_spin.setSingleStep(0.05)
        self.temp_spin.setValue(0.7)
        self.temp_spin.setDecimals(2)
        self.temp_spin.setFixedWidth(60)
        params_layout.addWidget(self.temp_spin)

        params_layout.addWidget(QLabel("Max tokens:"))
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(64, 32000)
        self.max_tokens_spin.setSingleStep(512)
        self.max_tokens_spin.setValue(4096)
        self.max_tokens_spin.setFixedWidth(80)
        params_layout.addWidget(self.max_tokens_spin)

        # System prompt
        self.system_prompt_btn = QPushButton("📎 System")
        self.system_prompt_btn.setCheckable(True)
        self.system_prompt_btn.toggled.connect(self._toggle_system_prompt)
        params_layout.addWidget(self.system_prompt_btn)

        params_layout.addStretch()

        # Status
        self.chat_status = QLabel("🔴 Server offline")
        params_layout.addWidget(self.chat_status)

        chat_layout.addLayout(params_layout)

        # System prompt expandable
        self.system_prompt_edit = QTextEdit()
        self.system_prompt_edit.setPlaceholderText("System prompt (optional)...")
        self.system_prompt_edit.setMaximumHeight(80)
        self.system_prompt_edit.setVisible(False)
        chat_layout.addWidget(self.system_prompt_edit)

        splitter.addWidget(chat_widget)
        splitter.setSizes([200, 800])

        layout.addWidget(splitter)

        # Connecter Enter
        self.input_edit.installEventFilter(self)

        # Timer statut serveur
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(2000)
        self._status_timer.timeout.connect(self._update_status)
        self._status_timer.start()

    def eventFilter(self, obj, event):
        if obj == self.input_edit and event.type() == event.Type.KeyPress:
            from PySide6.QtGui import QKeyEvent
            ke = QKeyEvent(event)
            if ke.key() == Qt.Key_Return and not ke.modifiers() & Qt.ShiftModifier:
                self._send_message()
                return True
        return super().eventFilter(obj, event)

    def _update_status(self):
        if self.server.is_running:
            self.chat_status.setText("🟢 Connected")
            self.chat_status.setStyleSheet("color: #34a853;")
        else:
            self.chat_status.setText("🔴 Server offline")
            self.chat_status.setStyleSheet("color: #ea4335;")

    def _toggle_system_prompt(self, checked: bool):
        self.system_prompt_edit.setVisible(checked)

    def _new_chat(self):
        self._messages = []
        self._previous_response_id = ""
        self._clear_messages_ui()
        self.input_edit.clear()

    def _clear_messages_ui(self):
        while self.messages_layout.count():
            item = self.messages_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def _add_message(self, role: str, content: str):
        self._messages.append({"role": role, "content": content})

        # Créer une bulle
        bubble = QFrame()
        if role == "user":
            bubble.setStyleSheet("""
                QFrame {
                    background-color: #1a73e8;
                    border-radius: 12px;
                    padding: 10px 14px;
                    margin-left: 60px;
                }
            """)
        else:
            bubble.setStyleSheet("""
                QFrame {
                    background-color: #2d2d3d;
                    border-radius: 12px;
                    padding: 10px 14px;
                    margin-right: 60px;
                }
            """)

        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(0, 0, 0, 0)
        bubble_layout.setSpacing(4)

        # Header
        header = QLabel(f"{'👤 You' if role == 'user' else '🤖 Assistant'}")
        header.setStyleSheet("font-weight: bold; font-size: 11px; color: #aaa;")
        bubble_layout.addWidget(header)

        # Contenu (markdown simple)
        content_label = QLabel(self._render_markdown(content))
        content_label.setWordWrap(True)
        content_label.setTextFormat(Qt.RichText)
        content_label.setStyleSheet("font-size: 13px; color: #eee;")
        bubble_layout.addWidget(content_label)

        # Bouton copier
        copy_btn = QPushButton("📋 Copy")
        copy_btn.setFixedWidth(80)
        copy_btn.setStyleSheet("font-size: 10px; padding: 2px 8px;")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(content))
        bubble_layout.addWidget(copy_btn, 0, Qt.AlignRight)

        self.messages_layout.addWidget(bubble)

        # Scroller vers le bas
        QTimer.singleShot(100, self._scroll_to_bottom)

    def _render_markdown(self, text: str) -> str:
        """Convertit du markdown simple en HTML."""
        import re
        html = text

        # Code blocks
        html = re.sub(
            r'```(\w*)\n(.*?)```',
            r'<pre style="background:#1e1e2e;padding:8px;border-radius:6px;font-family:monospace;font-size:12px;overflow-x:auto;">\2</pre>',
            html, flags=re.DOTALL
        )

        # Inline code
        html = re.sub(
            r'`([^`]+)`',
            r'<code style="background:#1e1e2e;padding:1px 4px;border-radius:3px;font-family:monospace;">\1</code>',
            html
        )

        # Bold
        html = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html)

        # Italic
        html = re.sub(r'\*(.+?)\*', r'<i>\1</i>', html)

        # Line breaks
        html = html.replace("\n", "<br>")

        return html

    def _scroll_to_bottom(self):
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _send_message(self):
        text = self.input_edit.toPlainText().strip()
        if not text:
            return

        if not self.server.is_running:
            QMessageBox.warning(self, "Server stopped",
                                "The server is not running.\n"
                                "Start it from the Server tab.")
            return

        self.input_edit.clear()
        self._add_message("user", text)
        self._add_message("assistant", "⏳ Generating...")
        self.writing_indicator.setText("🤖 Writing...")
        self.writing_indicator.setVisible(True)
        self.send_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        api_key = self.config.get("api_key", "") if self.config.get("api_key_enabled", False) else ""
        api_mode = self.config.get("api_mode", "chat_completions")

        if api_mode == "responses":
            self._send_responses_request(text, api_key)
        else:
            self._send_chat_request(text, api_key)

        self._response_buffer = ""

    def _send_chat_request(self, text: str, api_key: str):
        """Envoie une requête Chat Completions classique."""
        messages = [{"role": "system", "content": self.system_prompt_edit.toPlainText()}] \
            if self.system_prompt_edit.toPlainText() else []
        messages += [{"role": m["role"], "content": m["content"]}
                     for m in self._messages[:-1]]  # exclure le placeholder

        payload = {
            "model": self.model_combo.currentText() or "default",
            "messages": messages,
            "temperature": self.temp_spin.value(),
            "max_tokens": self.max_tokens_spin.value(),
            "stream": True,
        }

        self._current_thread = LLMRequestThread(
            url=self.config.api_chat_url,
            payload=payload,
            api_key=api_key,
        )
        self._current_thread.token_received.connect(self._on_token)
        self._current_thread.finished.connect(self._on_finished)
        self._current_thread.error.connect(self._on_error)
        self._current_thread.start()

    def _send_responses_request(self, text: str, api_key: str):
        """Envoie une requête Responses API."""
        # Construire l'input: messages précédents + nouveau
        input_items = []

        # System prompt → instructions (envoyé à chaque requête)
        instructions = self.system_prompt_edit.toPlainText()

        # Messages précédents (historique)
        for m in self._messages[:-1]:  # exclure le placeholder
            input_items.append({
                "type": "message",
                "role": m["role"],
                "content": m["content"],
            })

        # Nouveau message
        input_items.append({
            "type": "message",
            "role": "user",
            "content": text,
        })

        payload = {
            "model": self.model_combo.currentText() or "default",
            "input": input_items,
            "temperature": self.temp_spin.value(),
            "max_output_tokens": self.max_tokens_spin.value(),
            "stream": True,
        }

        if instructions:
            payload["instructions"] = instructions

        # Stateful: previous_response_id
        if self._previous_response_id:
            payload["previous_response_id"] = self._previous_response_id

        self._current_thread = ResponsesRequestThread(
            url=self.server.api_responses_url,
            payload=payload,
            api_key=api_key,
        )
        self._current_thread.token_received.connect(self._on_token)
        self._current_thread.response_id_received.connect(self._on_response_id)
        self._current_thread.finished.connect(self._on_finished)
        self._current_thread.error.connect(self._on_error)
        self._current_thread.start()

    def _on_response_id(self, response_id: str):
        """Stocke le response_id pour le state management."""
        self._previous_response_id = response_id

    def _on_token(self, token: str):
        self._response_buffer += token
        # Mettre à jour le dernier message assistant
        last_idx = len(self._messages) - 1
        if last_idx >= 0 and self._messages[last_idx]["role"] == "assistant":
            self._messages[last_idx]["content"] = self._response_buffer
            # Mettre à jour l'affichage
            self._update_last_assistant_message()

    def _update_last_assistant_message(self):
        """Remplace le contenu de la dernière bulle assistant."""
        last_widget = self.messages_layout.itemAt(self.messages_layout.count() - 1)
        if last_widget and last_widget.widget():
            bubble = last_widget.widget()
            # Trouver le QLabel de contenu
            for child in bubble.findChildren(QLabel):
                if child.objectName() == "content_label":
                    child.setText(self._render_markdown(self._response_buffer))
                    break
            else:
                # Fallback: chercher tous les labels
                labels = bubble.findChildren(QLabel)
                for label in labels:
                    if "Assistant" not in label.text() and "📋" not in label.text():
                        label.setText(self._render_markdown(self._response_buffer))
                        break

    def _on_finished(self):
        self.writing_indicator.setVisible(False)
        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._current_thread = None

    def _on_error(self, error_msg: str):
        self.writing_indicator.setVisible(False)
        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        # Remplacer le message d'attente par l'erreur
        if self._messages and self._messages[-1]["role"] == "assistant":
            self._messages[-1]["content"] = f"❌ Erreur: {error_msg}"
            self._update_last_assistant_message()
            QMessageBox.critical(self, "API Error", error_msg)

        self._current_thread = None

    def _stop_generation(self):
        if self._current_thread and self._current_thread.isRunning():
            self._current_thread.terminate()
            self._current_thread.wait()
            self._current_thread = None
            self.writing_indicator.setVisible(False)
            self.send_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

            if self._response_buffer:
                if self._messages and self._messages[-1]["role"] == "assistant":
                    self._messages[-1]["content"] = self._response_buffer
                    self._update_last_assistant_message()
