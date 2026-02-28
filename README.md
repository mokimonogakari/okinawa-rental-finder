# 沖縄賃貸ファインダー 🏠

沖縄県の賃貸物件を複数サイトからスクレイピングし、宅建士監修の検索条件で絞り込み、AI価格推定で「お得物件」を見つけるWebアプリケーション。

## 機能

- **マルチサイトスクレイピング**: グーホーム、うちなーらいふ、SUUMO、HOME'Sの4サイトから物件情報を自動収集
- **宅建士監修の検索条件**: 沖縄特有の条件（台風対策の構造、駐車場、基地騒音等）を含む詳細検索
- **AI適正価格推定**: 路線価・地価公示・周辺相場から機械学習モデルで適正賃料を推定
- **割安度スコア**: 実際賃料と推定賃料を比較し「お得物件」を自動判定
- **LINE通知**: 条件に合う新着物件をLINE Notifyで自動通知
- **分析ダッシュボード**: 市町村別相場、賃料分布、価格トレンドをグラフ表示

## 技術スタック

| コンポーネント | 技術 |
|-------------|------|
| スクレイパー | Scrapy |
| データベース | SQLite (WALモード) |
| Web UI | Streamlit |
| 価格推定 | scikit-learn (Ridge回帰 + Random Forest) |
| 通知 | LINE Notify API |
| 地価データ | 不動産情報ライブラリAPI + 国土数値情報 |
| インフラ | さくらのVPS 1G |
| リバプロ | Nginx |

## デプロイ先環境

### 推奨環境: さくらのVPS 1G (880円/月)

| 項目 | 要件 |
|------|------|
| OS | Ubuntu 24.04 LTS |
| CPU | 2コア以上 |
| メモリ | 1GB以上 (2GB推奨) |
| ディスク | 25GB以上 |
| Python | 3.12以上 |
| ネットワーク | 外部HTTPS通信可能 (スクレイピング先4サイト + API) |

### なぜさくらVPS 1Gか

- **月額880円**で必要十分なスペック
- 国内サーバーのためスクレイピング対象サイトとの通信が高速
- Ubuntu 24.04対応、Python 3.12プリインストール
- 固定IPアドレス付き

### 他の選択肢との比較

| 環境 | 費用 | 判定 | 理由 |
|------|------|------|------|
| **さくらVPS 1G** | 880円/月 | **推奨** | コスパ最良。常時稼働+定期スクレイピング |
| さくらVPS 2G | 1,738円/月 | 余裕がある場合 | メモリ2GBでモデル学習が安定 |
| Render.com Free | 0円 | 不可 | スリープあり、スクレイピング定期実行不可 |
| GitHub Pages | 0円 | 不可 | 静的サイトのみ。Python実行不可 |
| AWS EC2 t3.micro | ~1,500円/月 | 割高 | 同等スペックで費用が高い |
| 自宅PC (WSL) | 0円 | 開発用 | PC起動中のみ。本番運用には不向き |

### 共存可能な既存サービス

VPSに既存サービスがある場合、Nginx パスベースルーティングで共存可能:

```
http://your-server/          → 既存サービス
http://your-server/rental    → 沖縄賃貸ファインダー (Streamlit)
```

## セットアップ

```bash
# リポジトリクローン
git clone https://github.com/yourname/okinawa-rental-finder.git
cd okinawa-rental-finder

# 仮想環境
python3 -m venv .venv
source .venv/bin/activate

# 依存関係インストール
pip install -e '.[dev]'

# 環境変数設定
cp .env.example .env
# .env を編集してAPIキーを設定
```

## 使い方

```bash
# Web UI起動
streamlit run src/web/app.py

# スクレイピング実行 (全サイト)
./scripts/run_scraper.sh all

# 特定サイトのみ
./scripts/run_scraper.sh goohome

# 価格推定モデル学習
python -m src.pricing.training

# テスト実行
pytest tests/ -v
```

## 設定ファイル

| ファイル | 内容 |
|---------|------|
| `config/settings.yaml` | アプリ全体設定 |
| `config/search_conditions.yaml` | 検索条件マスタ (宅建監修) |
| `config/scraping_targets.yaml` | スクレイピング対象サイト |
| `config/notification.yaml` | LINE通知設定 |

## VPSデプロイ

```bash
# 1. アプリ配置
sudo mkdir -p /opt/okinawa-rental-finder
sudo chown $USER:$USER /opt/okinawa-rental-finder
git clone https://github.com/mokimonogakari/okinawa-rental-finder.git /opt/okinawa-rental-finder
cd /opt/okinawa-rental-finder

# 2. Python環境構築
python3 -m venv .venv
.venv/bin/pip install -e .
mkdir -p data/models data/land_price logs

# 3. 環境変数設定
cp .env.example .env
# .env を編集してAPIキーを設定

# 4. systemd登録 (Web UI常駐 + スクレイピング定期実行)
sudo cp systemd/*.service systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now okinawa-rental-web
sudo systemctl enable --now okinawa-rental-scraper.timer

# 5. Nginx設定 (既存Nginx設定に /rental locationを追加)
# → 詳細は docs/ ディレクトリ参照
sudo nginx -t && sudo systemctl reload nginx
```

## ライセンス

MIT
