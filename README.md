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
| インフラ | さくらのVPS 1G (880円/月) |
| リバプロ | Caddy |

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
# さくらVPSセットアップ
./scripts/setup_vps.sh

# デプロイ
./scripts/deploy.sh
```

## ライセンス

MIT
