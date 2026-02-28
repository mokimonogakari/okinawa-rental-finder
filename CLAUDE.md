# 沖縄賃貸ファインダー - プロジェクトガイド

## プロジェクト概要
沖縄県の賃貸物件を4サイト（グーホーム、うちなーらいふ、SUUMO、HOME'S）からスクレイピングし、
宅建士監修の検索条件で絞り込み、路線価・地価公示データからAIで適正賃料を推定するWebアプリ。

## 技術スタック
- Python 3.12+ / Scrapy / SQLite (WAL) / Streamlit / scikit-learn
- LINE Notify / 不動産情報ライブラリAPI / 国土数値情報

## ディレクトリ構成
- `config/` - YAML設定ファイル（検索条件マスタ、スクレイピング対象、通知設定）
- `src/scraper/` - Scrapyスパイダー（4サイト）+ パイプライン
- `src/database/` - SQLiteスキーマ・リポジトリ（CRUD）
- `src/pricing/` - 地価データ取得・価格推定モデル（Ridge回帰+RandomForest）
- `src/web/` - Streamlit WebUI（検索/分析/通知設定/管理）
- `src/notification/` - LINE Notify連携
- `tests/` - pytest テスト

## 開発コマンド
```bash
# 仮想環境
source .venv/bin/activate

# テスト実行
pytest tests/ -v

# Lint
ruff check src/ tests/

# Web UI起動
streamlit run src/web/app.py

# スクレイピング（単体）
python -m scrapy crawl goohome

# スクレイピング（全サイト）
./scripts/run_scraper.sh all

# モデル学習
python -m src.pricing.training
```

## 重要な設定ファイル
- `config/settings.yaml` - DB パス、APIキー、スケジュール
- `config/search_conditions.yaml` - 宅建監修の検索条件マスタ（沖縄全41市町村、構造、設備等）
- `config/scraping_targets.yaml` - 各サイトのURL・遅延設定
- `.env` - APIキー（REINFOLIB_API_KEY, LINE_NOTIFY_TOKEN）

## コーディング規約
- Python 3.12+ の型ヒントを使用
- ruff でフォーマット・lint（line-length: 100）
- テストは tests/ 配下に配置、pytest で実行
- コミットメッセージは日本語OK

## 注意事項
- スクレイピングは robots.txt を遵守、DOWNLOAD_DELAY 3-5秒
- SQLite WALモード必須（並行読み取り性能）
- 沖縄特有の条件（台風対策RC構造推奨、駐車場必須、基地騒音）を考慮
