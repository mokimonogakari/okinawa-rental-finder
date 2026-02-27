#!/bin/bash
# モデル学習スクリプト
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"

source .venv/bin/activate 2>/dev/null || true

echo "[$(date)] Starting model training..."
python -m src.pricing.training
echo "[$(date)] Training complete."
