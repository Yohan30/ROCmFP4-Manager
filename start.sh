#!/bin/bash
cd "$(dirname "$0")"
export HSA_OVERRIDE_GFX_VERSION=11.5.1
export GGML_HIP_ENABLE_UNIFIED_MEMORY=1
./venv/bin/python src/main.py
