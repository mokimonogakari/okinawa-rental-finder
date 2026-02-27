"""SQLite データベーススキーマ定義・初期化"""

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
-- 物件テーブル (メイン)
CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,              -- スクレイピング元 (goohome/uchina/suumo/homes)
    source_id TEXT NOT NULL,           -- 元サイトでの物件ID
    source_url TEXT,                   -- 元サイトの物件ページURL
    name TEXT,                         -- 物件名
    address TEXT,                      -- 住所
    municipality TEXT,                 -- 市町村名
    municipality_code TEXT,            -- 市町村コード (47xxx)
    latitude REAL,                     -- 緯度
    longitude REAL,                    -- 経度

    -- 賃料
    rent INTEGER NOT NULL,             -- 賃料 (円/月)
    management_fee INTEGER DEFAULT 0,  -- 管理費・共益費 (円/月)
    deposit_months REAL DEFAULT 0,     -- 敷金 (ヶ月)
    key_money_months REAL DEFAULT 0,   -- 礼金 (ヶ月)
    security_deposit INTEGER,          -- 保証金 (円)

    -- 物件スペック
    property_type TEXT,                -- マンション/アパート/一戸建て/テラスハウス
    structure TEXT,                    -- RC/SRC/S/LS/W
    floor_plan TEXT,                   -- 間取り (1LDK等)
    room_count INTEGER,               -- 部屋数
    area_sqm REAL,                     -- 専有面積 (㎡)
    building_year INTEGER,             -- 築年 (西暦)
    building_age INTEGER,              -- 築年数
    floor_number INTEGER,              -- 所在階
    total_floors INTEGER,              -- 建物階数

    -- 交通
    nearest_station TEXT,              -- 最寄駅/バス停
    station_walk_minutes INTEGER,      -- 徒歩分数
    transport_type TEXT,               -- monorail/bus

    -- 駐車場
    parking_available INTEGER DEFAULT 0,   -- 0:なし 1:あり
    parking_fee INTEGER,                   -- 駐車場料金 (円/月, 込みの場合0)
    parking_spaces INTEGER,                -- 駐車可能台数

    -- 設備 (ビットフラグの代わりにBOOLEANカラム)
    has_aircon INTEGER DEFAULT 0,
    has_auto_lock INTEGER DEFAULT 0,
    has_delivery_box INTEGER DEFAULT 0,
    has_bath_dryer INTEGER DEFAULT 0,
    has_reheating INTEGER DEFAULT 0,
    has_washstand INTEGER DEFAULT 0,
    has_indoor_laundry INTEGER DEFAULT 0,
    has_internet INTEGER DEFAULT 0,
    has_fiber INTEGER DEFAULT 0,
    has_bath_toilet_separate INTEGER DEFAULT 0,
    has_flooring INTEGER DEFAULT 0,
    has_pet_ok INTEGER DEFAULT 0,

    -- 契約条件
    lease_type TEXT,                    -- ordinary/fixed
    guarantor_required TEXT,            -- required/available/none
    brokerage_fee_months REAL,          -- 仲介手数料 (ヶ月)
    move_in_date TEXT,                  -- 入居可能日

    -- 価格推定結果
    estimated_rent INTEGER,            -- 推定賃料 (円/月)
    affordability_score REAL,          -- 割安度スコア (実際賃料/推定賃料)
    estimated_at TEXT,                 -- 推定日時

    -- メタデータ
    scraped_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    is_active INTEGER DEFAULT 1,       -- 掲載中フラグ
    notified INTEGER DEFAULT 0,        -- LINE通知済みフラグ

    UNIQUE(source, source_id)
);

-- 地価データテーブル
CREATE TABLE IF NOT EXISTS land_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_source TEXT NOT NULL,          -- reinfolib/kokudo_l01/kokudo_l02
    year INTEGER NOT NULL,
    municipality TEXT,
    municipality_code TEXT,
    address TEXT,
    latitude REAL,
    longitude REAL,
    price_per_sqm INTEGER,             -- 円/㎡
    land_use TEXT,                      -- 用途区分
    zoning TEXT,                        -- 用途地域
    nearest_station TEXT,
    station_distance_m INTEGER,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),

    UNIQUE(data_source, year, address)
);

-- 不動産取引価格テーブル
CREATE TABLE IF NOT EXISTS transaction_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    quarter INTEGER,
    municipality TEXT,
    municipality_code TEXT,
    property_type TEXT,                 -- 宅地(土地)/中古マンション等/宅地(土地と建物)
    district TEXT,                      -- 地区名
    nearest_station TEXT,
    station_walk_minutes INTEGER,
    trade_price INTEGER,               -- 取引総額
    price_per_sqm INTEGER,             -- 坪単価/㎡単価
    area_sqm REAL,                     -- 面積
    building_year INTEGER,
    structure TEXT,
    land_use TEXT,
    zoning TEXT,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 検索条件保存テーブル (通知用)
CREATE TABLE IF NOT EXISTS saved_searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    conditions_json TEXT NOT NULL,      -- JSON形式の検索条件
    notify_enabled INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 通知履歴テーブル
CREATE TABLE IF NOT EXISTS notification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER,
    search_id INTEGER,
    sent_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    status TEXT DEFAULT 'sent',         -- sent/failed
    FOREIGN KEY (property_id) REFERENCES properties(id),
    FOREIGN KEY (search_id) REFERENCES saved_searches(id)
);

-- 価格推定モデルメタデータ
CREATE TABLE IF NOT EXISTS model_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_type TEXT NOT NULL,           -- ridge/random_forest
    version TEXT NOT NULL,
    training_samples INTEGER,
    r2_score REAL,
    mae REAL,                           -- 平均絶対誤差
    rmse REAL,                          -- 二乗平均平方根誤差
    feature_importances_json TEXT,
    model_path TEXT NOT NULL,
    trained_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    is_active INTEGER DEFAULT 0         -- 現在使用中のモデル
);

-- インデックス
CREATE INDEX IF NOT EXISTS idx_properties_municipality ON properties(municipality_code);
CREATE INDEX IF NOT EXISTS idx_properties_rent ON properties(rent);
CREATE INDEX IF NOT EXISTS idx_properties_active ON properties(is_active);
CREATE INDEX IF NOT EXISTS idx_properties_source ON properties(source, source_id);
CREATE INDEX IF NOT EXISTS idx_properties_scraped ON properties(scraped_at);
CREATE INDEX IF NOT EXISTS idx_properties_notified ON properties(notified, is_active);
CREATE INDEX IF NOT EXISTS idx_properties_score ON properties(affordability_score);
CREATE INDEX IF NOT EXISTS idx_land_prices_municipality ON land_prices(municipality_code, year);
CREATE INDEX IF NOT EXISTS idx_land_prices_location ON land_prices(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_transaction_municipality ON transaction_prices(municipality_code, year);
"""


def init_db(db_path: str | Path) -> sqlite3.Connection:
    """データベースを初期化し、接続を返す"""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # WALモード有効化 (並行読み取り性能向上)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")

    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """DB接続を取得 (既存DB前提)"""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn
