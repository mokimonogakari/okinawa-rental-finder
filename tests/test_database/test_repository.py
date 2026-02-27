"""リポジトリ CRUD テスト"""

import tempfile
from pathlib import Path

import pytest

from src.database.models import init_db
from src.database.repository import PropertyRepository, SavedSearchRepository


@pytest.fixture
def db_conn():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = init_db(db_path)
    yield conn
    conn.close()
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def prop_repo(db_conn):
    return PropertyRepository(db_conn)


def test_upsert_and_search(prop_repo):
    data = {
        "source": "test",
        "source_id": "001",
        "name": "テスト物件",
        "rent": 50000,
        "municipality_code": "47201",
        "municipality": "那覇市",
        "floor_plan": "1LDK",
        "area_sqm": 35.0,
        "building_age": 10,
        "structure": "RC",
        "parking_available": 1,
    }
    prop_repo.upsert_property(data)

    results = prop_repo.search(rent_max=60000)
    assert len(results) == 1
    assert results[0]["name"] == "テスト物件"
    assert results[0]["rent"] == 50000


def test_upsert_updates_existing(prop_repo):
    data1 = {"source": "test", "source_id": "002", "name": "元の名前", "rent": 40000}
    prop_repo.upsert_property(data1)

    data2 = {"source": "test", "source_id": "002", "name": "新しい名前", "rent": 45000}
    prop_repo.upsert_property(data2)

    results = prop_repo.search()
    assert len(results) == 1
    assert results[0]["name"] == "新しい名前"
    assert results[0]["rent"] == 45000


def test_search_with_filters(prop_repo):
    for i in range(5):
        prop_repo.upsert_property({
            "source": "test",
            "source_id": f"f{i}",
            "rent": 30000 + i * 10000,
            "municipality_code": "47201" if i < 3 else "47211",
            "floor_plan": "1LDK" if i < 3 else "2LDK",
            "area_sqm": 25.0 + i * 5,
            "structure": "RC",
            "parking_available": 1 if i % 2 == 0 else 0,
        })

    # 賃料フィルタ
    results = prop_repo.search(rent_min=40000, rent_max=60000)
    assert all(40000 <= r["rent"] <= 60000 for r in results)

    # 市町村フィルタ
    results = prop_repo.search(municipality_codes=["47201"])
    assert all(r["municipality_code"] == "47201" for r in results)

    # 駐車場フィルタ
    results = prop_repo.search(parking_required=True)
    assert all(r["parking_available"] == 1 for r in results)


def test_update_estimation(prop_repo):
    prop_repo.upsert_property({
        "source": "test", "source_id": "est1", "rent": 50000,
    })
    results = prop_repo.search()
    prop_id = results[0]["id"]

    prop_repo.update_estimation(prop_id, 55000, 0.91)

    prop = prop_repo.get_by_id(prop_id)
    assert prop["estimated_rent"] == 55000
    assert prop["affordability_score"] == 0.91


def test_saved_search(db_conn):
    repo = SavedSearchRepository(db_conn)

    search_id = repo.save("テスト条件", {"rent_max": 50000, "area": "那覇市"})
    assert search_id > 0

    all_searches = repo.get_all()
    assert len(all_searches) == 1
    assert all_searches[0]["name"] == "テスト条件"
    assert all_searches[0]["conditions"]["rent_max"] == 50000

    repo.delete(search_id)
    assert len(repo.get_all()) == 0
