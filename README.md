# ROCmFP4 Manager

Desktop GUI to **download, configure and run** GGUF models in **ROCmFP4** format on **AMD Strix Halo** — without touching the command line. Now with **multi-profile ROCmFPX**, **DeepSeek V4 support**, and more.

![ROCmFP4 Manager](assets/icon.svg)

## Features

- **Multi-profile ROCmFPX** — Manage multiple ROCmFPX builds side-by-side (Standard, CIRU Laguna V2, DFlash fixes). Per-model profile assignment. Legacy path auto-migration.
- **Model management** — HuggingFace search & download, LM Studio import, multi-part and MTP support, draft model selection, custom chat templates
- **Visual configuration** — Context, batch, K/V cache, MTP, flash attention, all via sliders. Advanced env var toggles (HSA_OVERRIDE, unified memory, LD_LIBRARY_PATH)
- **Server control** — Start/Stop/Restart, live logs, API URLs displayed, LAN access toggle, API mode indicator, ROCmFPX profile selector per model
- **Built-in chat** — Discussion interface with streaming, markdown, history, reasoning content display (DeepSeek thinking), graceful stop generation
- **Built-in bench** — Performance tests with `llama-bench`, multi-run, CSV/JSON export
- **Auto-start** — systemd service to launch the app and/or server at boot
- **Theme support** — Dark/Light themes with customizable accent and background colors
- **Auto-update** — Check and install new versions from GitHub releases
- **OpenAI Responses API** — Built-in adapter (port 1413) translating `/v1/responses` to Chat Completions. Full streaming SSE with proper event types, separate reasoning/text output items, UTF-8 encoding, tool calls, `previous_response_id` state management. Compatible with Open WebUI and VS Code Copilot.
- **DeepSeek V4 / Lucebox** — Auto-detection of DeepSeek V4 models, seamless launch via `dflash_server` with fused decode, expert routing, and speculative decoding options
- **GPU Max Clock** — systemd service and script to set GPU to maximum clock for inference

## Requirements

- **AMD Strix Halo** (Radeon 8060S / gfx1151)
- **Linux 6.17+** with Mesa 25.2.8+
- **Python 3.11+**
- **Git**
- **[ROCmFPX](https://github.com/charlie12345/ROCmFPX)** (fork of llama.cpp with AMD-optimized kernels)

## Installation

```bash
# 1. Clone
git clone https://github.com/Yohan30/ROCmFP4-Manager.git
cd ROCmFP4-Manager

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Launch
python src/main.py
```

The app will detect if ROCmFPX is installed and offer to clone/build it.

## Quick Start

1. **ROCmFPX tab** → Clone and build (first time only). Choose your profile: Standard, CIRU Laguna V2, or DFlash fixes.
2. **Models tab** → Search and download a model, or import from LM Studio. DeepSeek V4 models are auto-detected.
3. **Configuration tab** → Select the model, adjust settings (context, batch, K/V cache, env vars, advanced args per model)
4. **Server tab** → Select the ROCmFPX profile for this model, then click "Start"
5. **Chat tab** → Chat with the model! Reasoning/thinking tokens are displayed for DeepSeek models.

## Default Ports

- Web UI + API: **`http://localhost:1412`**
- Chat API: `http://localhost:1412/v1/chat/completions`
- Responses API (adapter): **`http://localhost:1413/v1/responses`**

## Tech Stack

- **Python 3** / **PySide6 (Qt6)**
- **[ROCmFPX](https://github.com/charlie12345/ROCmFPX)** — Multi-profile support (Standard, CIRU Laguna V2, DFlash fixes)
- **[Lucebox](https://github.com/Luce-Org/lucebox.git)** — DeepSeek V4 inference via `dflash_server`
- **systemd** (auto-start, GPU max clock)
- **HuggingFace Hub** (model download)

## Author

**Necti** — [github.com/Yohan30](https://github.com/Yohan30)

## License

MIT
