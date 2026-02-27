#!/bin/bash
# ==================================================
# さくらVPS セットアップスクリプト
# Ubuntu 24.04 LTS 想定
# ==================================================
set -euo pipefail

echo "=== 沖縄賃貸ファインダー VPSセットアップ ==="

# --- パッケージ更新 ---
sudo apt update && sudo apt upgrade -y

# --- Python 3.12+ ---
sudo apt install -y python3 python3-pip python3-venv python3-dev

# --- Caddy (リバースプロキシ) ---
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy

# --- プロジェクトセットアップ ---
APP_DIR="/opt/okinawa-rental-finder"
sudo mkdir -p "$APP_DIR"

# ユーザー作成
sudo useradd -r -s /bin/false -d "$APP_DIR" okinawa-rental || true

echo ""
echo "=== 次のステップ ==="
echo "1. リポジトリをクローン: git clone <repo> $APP_DIR"
echo "2. cd $APP_DIR && python3 -m venv .venv && source .venv/bin/activate"
echo "3. pip install -e '.[dev]'"
echo "4. cp .env.example .env && vim .env  (APIキー設定)"
echo "5. sudo cp systemd/*.service systemd/*.timer /etc/systemd/system/"
echo "6. sudo cp Caddyfile /etc/caddy/Caddyfile"
echo "7. sudo systemctl daemon-reload"
echo "8. sudo systemctl enable --now okinawa-rental-web"
echo "9. sudo systemctl enable --now okinawa-rental-scraper.timer"
echo "10. sudo systemctl restart caddy"
