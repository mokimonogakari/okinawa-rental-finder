#!/bin/bash
# スクレイパー実行スクリプト
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"

source .venv/bin/activate 2>/dev/null || true

SPIDER="${1:-all}"
LOG_DIR="$APP_DIR/logs"
mkdir -p "$LOG_DIR"
DATE=$(date +%Y%m%d_%H%M%S)

if [ "$SPIDER" = "all" ]; then
    for name in goohome uchina suumo homes; do
        echo "[$(date)] Starting spider: $name"
        python -m scrapy crawl "$name" 2>&1 | tee "$LOG_DIR/scrape_${name}_${DATE}.log"
        echo "[$(date)] Finished spider: $name"
        sleep 60  # サイト間のインターバル
    done
else
    echo "[$(date)] Starting spider: $SPIDER"
    python -m scrapy crawl "$SPIDER" 2>&1 | tee "$LOG_DIR/scrape_${SPIDER}_${DATE}.log"
    echo "[$(date)] Finished spider: $SPIDER"
fi

# スクレイピング後にモデル再学習
echo "[$(date)] Starting model training..."
python -m src.pricing.training 2>&1 | tee "$LOG_DIR/training_${DATE}.log"

# 通知チェック
echo "[$(date)] Checking notifications..."
python -m src.notification.line_notify 2>&1 | tee "$LOG_DIR/notify_${DATE}.log"

echo "[$(date)] All done."
