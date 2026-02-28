# デプロイ・初期セットアップガイド

## 前提条件

- Ubuntu 22.04+ のVPSまたはサーバー
- Python 3.12+
- Git
- Nginx（リバースプロキシ用）

## 1. リポジトリのクローン

```bash
cd /home/ubuntu
git clone https://github.com/mokimonogakari/okinawa-rental-finder.git
cd okinawa-rental-finder
```

## 2. Python仮想環境のセットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -e ".[dev]"  # 開発用（テスト・リンター）
```

## 3. 環境変数の設定

```bash
cp .env.example .env
chmod 600 .env
```

`.env` を編集して以下を設定:

```bash
# 不動産情報ライブラリ API キー（任意）
REINFOLIB_API_KEY=your_api_key_here

# LINE Messaging API（通知機能に必要）
LINE_CHANNEL_ACCESS_TOKEN=your_token_here
LINE_CHANNEL_SECRET=your_secret_here
LINE_USER_IDS=Uxxxx,Uyyyy
```

LINE Messaging API の設定手順は [line-messaging-api-setup.md](./line-messaging-api-setup.md) を参照。

## 4. データベース初期化

```bash
.venv/bin/python -c "from src.database.models import init_db; init_db('data/okinawa_rental.db')"
```

## 5. 初回スクレイピング

```bash
# 全サイト実行（約30分）
.venv/bin/python -m scrapy crawl uchina    # e-uchina.net（API、高速）
.venv/bin/python -m scrapy crawl goohome   # グーホーム沖縄
.venv/bin/python -m scrapy crawl suumo     # SUUMO
.venv/bin/python -m scrapy crawl homes     # HOME'S
```

## 6. 価格推定モデルの学習

スクレイピング後、推定賃料と割安度スコアを算出:

```bash
.venv/bin/python -c "
from src.pricing.training import run_training_pipeline
results = run_training_pipeline('./config/settings.yaml')
print(results)
"
```

最低50件のデータが必要。200件以上で精度が安定する。

## 7. systemdサービスの設定

### Web UI（Streamlit）

```bash
sudo tee /etc/systemd/system/okinawa-rental-web.service << 'EOF'
[Unit]
Description=沖縄賃貸ファインダー Web UI (Streamlit)
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/okinawa-rental-finder
EnvironmentFile=/home/ubuntu/okinawa-rental-finder/.env
ExecStart=/home/ubuntu/okinawa-rental-finder/.venv/bin/streamlit run src/web/app.py --server.port 8501 --server.headless true --server.baseUrlPath /rental
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

### スクレイパー（日次バッチ）

```bash
sudo tee /etc/systemd/system/okinawa-rental-scraper.service << 'EOF'
[Unit]
Description=沖縄賃貸スクレイパー

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=/home/ubuntu/okinawa-rental-finder
EnvironmentFile=/home/ubuntu/okinawa-rental-finder/.env
ExecStart=/home/ubuntu/okinawa-rental-finder/scripts/run_scraper.sh all
EOF

sudo tee /etc/systemd/system/okinawa-rental-scraper.timer << 'EOF'
[Unit]
Description=沖縄賃貸スクレイパー日次タイマー

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF
```

### LINE Webhookサーバー

```bash
sudo tee /etc/systemd/system/okinawa-rental-webhook.service << 'EOF'
[Unit]
Description=LINE Webhook Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/okinawa-rental-finder
EnvironmentFile=/home/ubuntu/okinawa-rental-finder/.env
ExecStart=/home/ubuntu/okinawa-rental-finder/.venv/bin/python -m src.notification.webhook
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

### サービスの有効化と起動

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now okinawa-rental-web
sudo systemctl enable --now okinawa-rental-webhook
sudo systemctl enable --now okinawa-rental-scraper.timer
```

## 8. Nginx リバースプロキシ設定

`/etc/nginx/sites-enabled/your-domain.conf` に以下を追加:

```nginx
# 沖縄賃貸ファインダー (Streamlit) - Basic認証付き
location /rental/ {
    auth_basic "Okinawa Rental Finder";
    auth_basic_user_file /etc/nginx/.htpasswd_rental;
    proxy_pass http://127.0.0.1:8501/rental/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 86400;
}

# Streamlit WebSocket
location /rental/_stcore/ {
    auth_basic "Okinawa Rental Finder";
    auth_basic_user_file /etc/nginx/.htpasswd_rental;
    proxy_pass http://127.0.0.1:8501/rental/_stcore/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
}

# Streamlit static files
location /rental/static/ {
    auth_basic "Okinawa Rental Finder";
    auth_basic_user_file /etc/nginx/.htpasswd_rental;
    proxy_pass http://127.0.0.1:8501/rental/static/;
}

# LINE Webhook（認証なし — LINE platformからのリクエスト）
location /rental/webhook {
    proxy_pass http://127.0.0.1:8502/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

### Basic認証の設定

```bash
sudo apt install apache2-utils
sudo htpasswd -cb /etc/nginx/.htpasswd_rental admin your_password
sudo nginx -t && sudo systemctl reload nginx
```

## 9. 動作確認

```bash
# Web UI
curl -u admin:your_password https://your-domain/rental/

# LINE Webhook
BODY='{"events":[]}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "your_channel_secret" -binary | base64)
curl -X POST -H "Content-Type: application/json" -H "X-Line-Signature: $SIG" \
  -d "$BODY" https://your-domain/rental/webhook

# サービス状態確認
sudo systemctl status okinawa-rental-web
sudo systemctl status okinawa-rental-webhook
sudo systemctl list-timers | grep okinawa
```

## 10. 更新手順

```bash
cd /home/ubuntu/okinawa-rental-finder
git pull origin main
sudo systemctl restart okinawa-rental-web okinawa-rental-webhook
```

## トラブルシューティング

### サービスが起動しない

```bash
sudo journalctl -u okinawa-rental-web -f  # ログ確認
```

### Streamlitのポートが使用中

```bash
sudo lsof -i :8501  # ポート使用状況確認
```

### スクレイピングが0件

- robots.txtの制限を確認
- `download_delay` を増やす（config/settings.yaml）
- ログを確認: `logs/scrape_*.log`

### メモリ不足（1GB VPS）

- スクレイピングは1サイトずつ実行（`scripts/run_scraper.sh` の `sleep 60`）
- Streamlitの `--server.maxUploadSize 5` を設定
- 不要なDockerコンテナを停止
