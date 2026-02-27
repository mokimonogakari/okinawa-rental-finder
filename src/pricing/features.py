"""特徴量エンジニアリング - 価格推定モデル用"""

import numpy as np
import pandas as pd


# 沖縄市町村のエリアグルーピング
AREA_GROUPS = {
    "那覇市": "naha",
    "浦添市": "urasoe",
    "豊見城市": "south_urban",
    "糸満市": "south_urban",
    "南城市": "south_rural",
    "南風原町": "south_urban",
    "与那原町": "south_urban",
    "八重瀬町": "south_rural",
    "沖縄市": "central",
    "うるま市": "central",
    "宜野湾市": "central_urban",
    "北谷町": "central_urban",
    "嘉手納町": "central",
    "読谷村": "central",
    "中城村": "central",
    "西原町": "central_urban",
    "北中城村": "central",
    "名護市": "north",
    "本部町": "north",
    "恩納村": "north_resort",
    "金武町": "north",
    "宜野座村": "north",
    "国頭村": "north_remote",
    "大宜味村": "north_remote",
    "東村": "north_remote",
    "今帰仁村": "north",
    "宮古島市": "island",
    "石垣市": "island",
    "久米島町": "island_remote",
    "竹富町": "island_remote",
    "与那国町": "island_remote",
}

# 構造の数値エンコーディング (耐久性順)
STRUCTURE_ENCODING = {
    "SRC": 5,
    "RC": 4,
    "S": 3,
    "LS": 2,
    "W": 1,
}

# 間取りの数値化 (おおよその広さ順)
FLOOR_PLAN_ENCODING = {
    "1R": 1, "1K": 2, "1DK": 3, "1LDK": 4,
    "2K": 5, "2DK": 6, "2LDK": 7,
    "3K": 8, "3DK": 9, "3LDK": 10,
    "4K以上": 11,
}


def build_features(df: pd.DataFrame, land_price_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """物件データから特徴量データフレームを構築"""
    features = pd.DataFrame()

    # --- 数値特徴量 ---
    features["area_sqm"] = pd.to_numeric(df["area_sqm"], errors="coerce")
    features["building_age"] = pd.to_numeric(df["building_age"], errors="coerce").fillna(20)
    features["floor_number"] = pd.to_numeric(df["floor_number"], errors="coerce").fillna(1)
    features["total_floors"] = pd.to_numeric(df["total_floors"], errors="coerce").fillna(3)
    features["station_walk_minutes"] = pd.to_numeric(
        df["station_walk_minutes"], errors="coerce"
    ).fillna(15)

    # --- 構造エンコーディング ---
    features["structure_score"] = df["structure"].map(STRUCTURE_ENCODING).fillna(2)

    # --- 間取りエンコーディング ---
    features["floor_plan_score"] = df["floor_plan"].map(FLOOR_PLAN_ENCODING).fillna(4)
    features["room_count"] = pd.to_numeric(df.get("room_count"), errors="coerce").fillna(
        features["floor_plan_score"].clip(upper=4)
    )

    # --- 駐車場 ---
    features["parking_available"] = pd.to_numeric(
        df["parking_available"], errors="coerce"
    ).fillna(0)

    # --- 設備スコア (設備数の合計) ---
    equip_cols = [c for c in df.columns if c.startswith("has_")]
    if equip_cols:
        features["equipment_score"] = df[equip_cols].apply(
            pd.to_numeric, errors="coerce"
        ).fillna(0).sum(axis=1)
    else:
        features["equipment_score"] = 0

    # --- エリアグルーピング (one-hot) ---
    if "municipality" in df.columns:
        df["area_group"] = df["municipality"].map(AREA_GROUPS).fillna("other")
        area_dummies = pd.get_dummies(df["area_group"], prefix="area")
        features = pd.concat([features, area_dummies], axis=1)

    # --- 市町村コード (one-hot、上位カテゴリ) ---
    if "municipality_code" in df.columns:
        mc = df["municipality_code"].fillna("unknown")
        mc_dummies = pd.get_dummies(mc, prefix="mc")
        features = pd.concat([features, mc_dummies], axis=1)

    # --- 交通タイプ ---
    if "transport_type" in df.columns:
        features["is_monorail"] = (df["transport_type"] == "monorail").astype(int)

    # --- 地価データとの結合 ---
    if land_price_df is not None and not land_price_df.empty:
        if "municipality_code" in df.columns and "municipality_code" in land_price_df.columns:
            avg_land = land_price_df.groupby("municipality_code")["price_per_sqm"].mean()
            features["avg_land_price"] = df["municipality_code"].map(avg_land).fillna(
                avg_land.median() if not avg_land.empty else 0
            )
        else:
            features["avg_land_price"] = 0
    else:
        features["avg_land_price"] = 0

    # --- 派生特徴量 ---
    features["age_area_interaction"] = features["building_age"] * features["area_sqm"]
    features["rent_per_sqm_area"] = features["area_sqm"].apply(
        lambda x: 1.0 / max(x, 1)  # 面積の逆数 (単価の代替)
    )
    features["floor_ratio"] = features["floor_number"] / features["total_floors"].clip(lower=1)

    # NaN処理
    features = features.fillna(0)

    return features


def get_target(df: pd.DataFrame) -> pd.Series:
    """目的変数 (賃料) を取得"""
    return pd.to_numeric(df["rent"], errors="coerce")
