#!/usr/bin/env bash
set -eu
cd -- "$(dirname -- "$0")"
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install .
.venv/bin/python -m pip check
echo 'Installazione completata. Eseguire bash avvia.sh.'
