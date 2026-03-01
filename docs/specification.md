# 仕様書

## 機能一覧

| # | 機能名 | 説明 | ステータス |
|---|--------|------|-----------|
| 1 | マルチサイトスクレイピング | goohome/uchina/suumo/homesの4サイトから物件取得 | 稼働中 |
| 2 | データクレンジング | 賃料・面積・構造等の正規化パイプライン | 稼働中 |
| 3 | 物件検索 | エリア・賃料・間取り・築年数・設備等の複合検索 | 稼働中 |
| 4 | 掲載媒体表示 | 各物件カードにソースサイトをバッジ表示 | 稼働中 |
| 5 | 保存済み条件クイック検索 | 通知条件からワンタップで検索条件を適用 | 稼働中 |
| 6 | AI適正価格推定 | Ridge+RandomForestで推定賃料を算出 (R²=0.83) | 稼働中 |
| 7 | 割安度スコア | 実賃料/推定賃料の比率でお得度判定 | 稼働中 |
| 8 | LINE新着通知 | 日次スクレイピング後、保存条件マッチ物件をLINE送信 | 稼働中 |
| 9 | 価格分析ダッシュボード | 市町村別相場・分布・トレンドをグラフ表示 | 稼働中 |
| 10 | 通知設定管理 | 保存済み条件の一覧・ON/OFF・削除 | 稼働中 |

## 画面一覧

| 画面名 | パス | 説明 |
|--------|------|------|
| 物件検索 | /rental (🔍 物件検索) | メイン検索画面。サイドバーにフィルタ、メインに物件カード一覧 |
| 価格分析 | /rental (📊 価格分析) | 市町村別相場グラフ、賃料分布、トレンド |
| 通知設定 | /rental (🔔 通知設定) | 保存済み検索条件の管理、LINE設定状況、テスト通知 |
| 管理 | /rental (⚙️ 管理) | スクレイピング実行状況、DB統計 |

## データモデル

### properties テーブル

| カラム | 型 | 説明 |
|--------|------|------|
| id | INTEGER PK | 自動採番 |
| source | TEXT | 取得元 (goohome/uchina/suumo/homes) |
| source_id | TEXT | ソース側の物件ID |
| source_url | TEXT | 物件詳細ページURL |
| name | TEXT | 物件名 |
| address | TEXT | 住所 |
| municipality | TEXT | 市町村名 |
| municipality_code | TEXT | 市町村コード (YAML定義) |
| rent | INTEGER | 賃料 (円/月) |
| management_fee | INTEGER | 管理費 (円/月) |
| deposit_months | REAL | 敷金 (月数) |
| key_money_months | REAL | 礼金 (月数) |
| floor_plan | TEXT | 間取り (1R, 2LDK等) |
| room_count | INTEGER | 部屋数 |
| area_sqm | REAL | 専有面積 (㎡) |
| structure | TEXT | 構造 (RC/SRC/S/LS/W) |
| building_year | INTEGER | 築年 |
| building_age | INTEGER | 築年数 |
| floor_number | INTEGER | 階数 |
| total_floors | INTEGER | 総階数 |
| parking_available | INTEGER | 駐車場 (0/1) |
| parking_fee | INTEGER | 駐車場料金 |
| nearest_station | TEXT | 最寄駅/バス停 |
| station_walk_minutes | INTEGER | 徒歩分数 |
| transport_type | TEXT | 交通手段 (monorail/bus) |
| latitude | REAL | 緯度 |
| longitude | REAL | 経度 |
| has_aircon | INTEGER | エアコン (0/1) |
| has_auto_lock | INTEGER | オートロック (0/1) |
| has_bath_dryer | INTEGER | 浴室乾燥機 (0/1) |
| has_reheating | INTEGER | 追い焚き (0/1) |
| has_internet | INTEGER | ネット対応 (0/1) |
| has_pet_ok | INTEGER | ペット可 (0/1) |
| estimated_rent | INTEGER | AI推定賃料 (円) |
| affordability_score | REAL | 割安度 (実賃料/推定賃料) |
| notified | INTEGER | LINE通知済み (0/1) |
| is_active | INTEGER | 有効フラグ |
| scraped_at | TEXT | 初回取得日時 |
| updated_at | TEXT | 最終更新日時 |

**ユニーク制約**: `(source, source_id)`

### saved_searches テーブル

| カラム | 型 | 説明 |
|--------|------|------|
| id | INTEGER PK | 自動採番 |
| name | TEXT | 条件名 (ユーザー入力) |
| conditions | TEXT | 検索条件JSON |
| notify_enabled | INTEGER | 通知ON/OFF (0/1) |
| created_at | TEXT | 作成日時 |

## LINE通知フロー

```
日次スクレイピング (03:00 JST)
    ↓
全4サイトをクロール
    ↓
DataCleansingPipeline: 賃料・面積・構造等を正規化
    ↓
SQLitePipeline: upsert (新規→notified=0, 既存→notified据え置き)
    ↓
価格推定モデル学習 (Ridge + RandomForest)
    ↓
check_and_notify():
    ├─ notified=0 の物件を取得
    ├─ notify_enabled=true の保存済み条件でフィルタ
    ├─ マッチした物件をLINE Messaging APIで送信
    └─ 全未通知物件を notified=1 にマーク (未マッチ含む)
```

## 掲載媒体バッジ

検索結果の各物件カード左上に掲載媒体をカラーバッジで表示:

| ソース | 表示名 | バッジ色 |
|--------|--------|----------|
| uchina | うちなーらいふ | オレンジ (#f97316) |
| goohome | グーホーム | 青 (#3b82f6) |
| suumo | SUUMO | 緑 (#22c55e) |
| homes | HOME'S | 紫 (#a855f7) |

## 市町村コード体系

`config/search_conditions.yaml` で定義。各市町村に一意のコードを付与し、パイプラインで住所テキストから自動マッピング。

**注意**: 南風原町(47350)と北谷町(47327)は修正済み (旧: 両方47326で重複していた)。
