"""特徴量エンジニアリングテスト"""

import pandas as pd

from src.pricing.features import (
    AREA_GROUPS,
    FLOOR_PLAN_ENCODING,
    STRUCTURE_ENCODING,
    build_features,
    get_target,
)


def test_structure_encoding():
    assert STRUCTURE_ENCODING["RC"] == 4
    assert STRUCTURE_ENCODING["SRC"] == 5
    assert STRUCTURE_ENCODING["W"] == 1


def test_floor_plan_encoding():
    assert FLOOR_PLAN_ENCODING["1R"] == 1
    assert FLOOR_PLAN_ENCODING["2LDK"] == 7
    assert FLOOR_PLAN_ENCODING["3LDK"] == 10


def test_area_groups():
    assert AREA_GROUPS["那覇市"] == "naha"
    assert AREA_GROUPS["北谷町"] == "central_urban"
    assert AREA_GROUPS["宮古島市"] == "island"


def test_build_features_basic():
    df = pd.DataFrame([{
        "area_sqm": 35.0,
        "building_age": 10,
        "floor_number": 3,
        "total_floors": 5,
        "station_walk_minutes": 10,
        "structure": "RC",
        "floor_plan": "1LDK",
        "room_count": 1,
        "parking_available": 1,
        "municipality": "那覇市",
        "municipality_code": "47201",
        "transport_type": "monorail",
        "has_aircon": 1,
        "has_auto_lock": 0,
    }])

    features = build_features(df)
    assert "area_sqm" in features.columns
    assert "structure_score" in features.columns
    assert "floor_plan_score" in features.columns
    assert features["structure_score"].iloc[0] == 4  # RC
    assert features["floor_plan_score"].iloc[0] == 4  # 1LDK


def test_get_target():
    df = pd.DataFrame({"rent": [50000, 60000, "70000"]})
    target = get_target(df)
    assert list(target) == [50000.0, 60000.0, 70000.0]
