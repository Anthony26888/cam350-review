#!/bin/zsh
cd "$(dirname "$0")"
export PATH="$PWD/.venv/bin:$PATH"
export CAM350_REVIEW_SKIP_LICENSE=1
python main.py
