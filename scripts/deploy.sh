#!/bin/bash
# デプロイスクリプト
set -euo pipefail

APP_DIR="/opt/okinawa-rental-finder"
cd "$APP_DIR"

echo "=== デプロイ開始 ==="

# リポジトリ更新
git pull origin main

# 依存関係更新
source .venv/bin/activate
pip install -e '.[dev]'

# systemd再読み込み
sudo cp systemd/*.service systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload

# Webアプリ再起動
sudo systemctl restart okinawa-rental-web

# Caddy再読み込み
sudo cp Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy

echo "=== デプロイ完了 ==="
