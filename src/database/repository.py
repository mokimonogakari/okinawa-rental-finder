"""物件データのCRUD操作"""

import json
import sqlite3
from datetime import datetime
from typing import Any


class PropertyRepository:
    """物件データのリポジトリ"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert_property(self, data: dict[str, Any]) -> int:
        """物件データをupsert (存在すれば更新、なければ挿入)"""
        columns = [k for k in data.keys() if k != "id"]
        placeholders = ", ".join(f":{c}" for c in columns)
        col_names = ", ".join(columns)

        update_cols = ", ".join(
            f"{c} = excluded.{c}"
            for c in columns
            if c not in ("source", "source_id", "scraped_at")
        )

        sql = f"""
            INSERT INTO properties ({col_names})
            VALUES ({placeholders})
            ON CONFLICT(source, source_id) DO UPDATE SET
                {update_cols},
                updated_at = datetime('now', 'localtime'),
                is_active = 1
        """
        cursor = self.conn.execute(sql, data)
        self.conn.commit()
        return cursor.lastrowid

    def upsert_many(self, items: list[dict[str, Any]]) -> int:
        """複数物件データを一括upsert"""
        count = 0
        for item in items:
            self.upsert_property(item)
            count += 1
        return count

    def search(
        self,
        municipality_codes: list[str] | None = None,
        address_keywords: list[str] | None = None,
        rent_min: int | None = None,
        rent_max: int | None = None,
        floor_plans: list[str] | None = None,
        area_min: float | None = None,
        area_max: float | None = None,
        building_age_max: int | None = None,
        structures: list[str] | None = None,
        property_types: list[str] | None = None,
        parking_required: bool = False,
        equipment_keys: list[str] | None = None,
        floor_min: int | None = None,
        lease_type: str | None = None,
        sort_by: str = "rent",
        sort_order: str = "ASC",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """検索条件に基づいて物件を検索"""
        conditions = ["is_active = 1"]
        params: dict[str, Any] = {}

        if municipality_codes:
            placeholders = ", ".join(f":mc{i}" for i in range(len(municipality_codes)))
            conditions.append(f"municipality_code IN ({placeholders})")
            for i, code in enumerate(municipality_codes):
                params[f"mc{i}"] = code

        if address_keywords:
            kw_conds = []
            for i, kw in enumerate(address_keywords):
                kw_conds.append(f"address LIKE :akw{i}")
                params[f"akw{i}"] = f"%{kw}%"
            conditions.append(f"({' OR '.join(kw_conds)})")

        if rent_min is not None:
            conditions.append("rent >= :rent_min")
            params["rent_min"] = rent_min
        if rent_max is not None:
            conditions.append("rent <= :rent_max")
            params["rent_max"] = rent_max

        if floor_plans:
            placeholders = ", ".join(f":fp{i}" for i in range(len(floor_plans)))
            conditions.append(f"floor_plan IN ({placeholders})")
            for i, fp in enumerate(floor_plans):
                params[f"fp{i}"] = fp

        if area_min is not None:
            conditions.append("area_sqm >= :area_min")
            params["area_min"] = area_min
        if area_max is not None:
            conditions.append("area_sqm <= :area_max")
            params["area_max"] = area_max

        if building_age_max is not None:
            conditions.append("building_age <= :building_age_max")
            params["building_age_max"] = building_age_max

        if structures:
            placeholders = ", ".join(f":st{i}" for i in range(len(structures)))
            conditions.append(f"structure IN ({placeholders})")
            for i, st in enumerate(structures):
                params[f"st{i}"] = st

        if property_types:
            placeholders = ", ".join(f":pt{i}" for i in range(len(property_types)))
            conditions.append(f"property_type IN ({placeholders})")
            for i, pt in enumerate(property_types):
                params[f"pt{i}"] = pt

        if parking_required:
            conditions.append("parking_available = 1")

        if equipment_keys:
            for key in equipment_keys:
                col = f"has_{key}"
                conditions.append(f"{col} = 1")

        if floor_min is not None:
            conditions.append("floor_number >= :floor_min")
            params["floor_min"] = floor_min

        if lease_type:
            conditions.append("lease_type = :lease_type")
            params["lease_type"] = lease_type

        allowed_sorts = {
            "rent", "area_sqm", "building_age", "scraped_at", "affordability_score"
        }
        if sort_by not in allowed_sorts:
            sort_by = "rent"
        if sort_order.upper() not in ("ASC", "DESC"):
            sort_order = "ASC"

        where_clause = " AND ".join(conditions)
        sql = f"""
            SELECT * FROM properties
            WHERE {where_clause}
            ORDER BY {sort_by} {sort_order}
            LIMIT :limit OFFSET :offset
        """
        params["limit"] = limit
        params["offset"] = offset

        rows = self.conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def count(self, **kwargs) -> int:
        """検索条件に一致する物件数を取得"""
        # search と同じ条件構築だが SELECT COUNT(*) にする
        conditions = ["is_active = 1"]
        params: dict[str, Any] = {}

        if "municipality_codes" in kwargs and kwargs["municipality_codes"]:
            codes = kwargs["municipality_codes"]
            placeholders = ", ".join(f":mc{i}" for i in range(len(codes)))
            conditions.append(f"municipality_code IN ({placeholders})")
            for i, code in enumerate(codes):
                params[f"mc{i}"] = code

        if "rent_min" in kwargs and kwargs["rent_min"] is not None:
            conditions.append("rent >= :rent_min")
            params["rent_min"] = kwargs["rent_min"]
        if "rent_max" in kwargs and kwargs["rent_max"] is not None:
            conditions.append("rent <= :rent_max")
            params["rent_max"] = kwargs["rent_max"]

        where_clause = " AND ".join(conditions)
        sql = f"SELECT COUNT(*) as cnt FROM properties WHERE {where_clause}"
        row = self.conn.execute(sql, params).fetchone()
        return row["cnt"]

    def get_by_id(self, property_id: int) -> dict | None:
        """IDで物件を取得"""
        row = self.conn.execute(
            "SELECT * FROM properties WHERE id = ?", (property_id,)
        ).fetchone()
        return dict(row) if row else None

    def mark_inactive(self, source: str, source_ids: list[str]) -> int:
        """指定されたsource_id以外を非アクティブにする (掲載終了検出)"""
        if not source_ids:
            return 0
        placeholders = ", ".join("?" for _ in source_ids)
        cursor = self.conn.execute(
            f"""UPDATE properties
                SET is_active = 0, updated_at = datetime('now', 'localtime')
                WHERE source = ? AND source_id NOT IN ({placeholders}) AND is_active = 1""",
            [source] + source_ids,
        )
        self.conn.commit()
        return cursor.rowcount

    def get_unnotified(self, search_id: int | None = None) -> list[dict]:
        """未通知の物件を取得"""
        sql = "SELECT * FROM properties WHERE is_active = 1 AND notified = 0 ORDER BY scraped_at DESC"
        rows = self.conn.execute(sql).fetchall()
        return [dict(row) for row in rows]

    def mark_notified(self, property_ids: list[int]) -> None:
        """通知済みフラグを立てる"""
        if not property_ids:
            return
        placeholders = ", ".join("?" for _ in property_ids)
        self.conn.execute(
            f"UPDATE properties SET notified = 1 WHERE id IN ({placeholders})",
            property_ids,
        )
        self.conn.commit()

    def update_estimation(
        self, property_id: int, estimated_rent: int, affordability_score: float
    ) -> None:
        """価格推定結果を更新"""
        self.conn.execute(
            """UPDATE properties
               SET estimated_rent = ?, affordability_score = ?,
                   estimated_at = datetime('now', 'localtime')
               WHERE id = ?""",
            (estimated_rent, affordability_score, property_id),
        )
        self.conn.commit()

    def get_training_data(self) -> list[dict]:
        """価格推定モデル学習用データを取得"""
        sql = """
            SELECT rent, management_fee, municipality_code, property_type,
                   structure, floor_plan, room_count, area_sqm, building_age,
                   floor_number, total_floors, station_walk_minutes, transport_type,
                   parking_available, has_aircon, has_auto_lock, has_bath_dryer,
                   has_reheating, has_washstand, has_indoor_laundry, has_internet,
                   has_bath_toilet_separate, has_flooring, latitude, longitude
            FROM properties
            WHERE is_active = 1
                AND rent IS NOT NULL
                AND area_sqm IS NOT NULL
                AND municipality_code IS NOT NULL
        """
        rows = self.conn.execute(sql).fetchall()
        return [dict(row) for row in rows]

    def get_statistics(self, municipality_code: str | None = None) -> dict:
        """統計情報を取得"""
        conditions = ["is_active = 1"]
        params: list = []
        if municipality_code:
            conditions.append("municipality_code = ?")
            params.append(municipality_code)
        where = " AND ".join(conditions)

        sql = f"""
            SELECT
                COUNT(*) as total,
                AVG(rent) as avg_rent,
                MIN(rent) as min_rent,
                MAX(rent) as max_rent,
                AVG(area_sqm) as avg_area,
                AVG(building_age) as avg_age,
                AVG(affordability_score) as avg_score
            FROM properties WHERE {where}
        """
        row = self.conn.execute(sql, params).fetchone()
        return dict(row)


class SavedSearchRepository:
    """保存済み検索条件のリポジトリ"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save(self, name: str, conditions: dict) -> int:
        cursor = self.conn.execute(
            "INSERT INTO saved_searches (name, conditions_json) VALUES (?, ?)",
            (name, json.dumps(conditions, ensure_ascii=False)),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_all(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM saved_searches ORDER BY created_at DESC"
        ).fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["conditions"] = json.loads(d["conditions_json"])
            results.append(d)
        return results

    def update_notify_enabled(self, search_id: int, enabled: bool) -> None:
        self.conn.execute(
            "UPDATE saved_searches SET notify_enabled = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
            (1 if enabled else 0, search_id),
        )
        self.conn.commit()

    def delete(self, search_id: int) -> None:
        self.conn.execute("DELETE FROM saved_searches WHERE id = ?", (search_id,))
        self.conn.commit()


class LandPriceRepository:
    """地価データのリポジトリ"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(self, data: dict[str, Any]) -> int:
        columns = [k for k in data.keys() if k != "id"]
        placeholders = ", ".join(f":{c}" for c in columns)
        col_names = ", ".join(columns)
        update_cols = ", ".join(
            f"{c} = excluded.{c}"
            for c in columns
            if c not in ("data_source", "year", "address")
        )

        sql = f"""
            INSERT INTO land_prices ({col_names})
            VALUES ({placeholders})
            ON CONFLICT(data_source, year, address) DO UPDATE SET {update_cols}
        """
        cursor = self.conn.execute(sql, data)
        self.conn.commit()
        return cursor.lastrowid

    def get_nearby(
        self, lat: float, lon: float, radius_km: float = 2.0, year: int | None = None
    ) -> list[dict]:
        """指定座標付近の地価データを取得 (簡易距離計算)"""
        # 緯度1度≒111km, 経度1度≒91km (沖縄付近)
        lat_range = radius_km / 111.0
        lon_range = radius_km / 91.0

        conditions = [
            "latitude BETWEEN :lat_min AND :lat_max",
            "longitude BETWEEN :lon_min AND :lon_max",
        ]
        params = {
            "lat_min": lat - lat_range,
            "lat_max": lat + lat_range,
            "lon_min": lon - lon_range,
            "lon_max": lon + lon_range,
        }
        if year:
            conditions.append("year = :year")
            params["year"] = year

        where = " AND ".join(conditions)
        sql = f"SELECT * FROM land_prices WHERE {where} ORDER BY price_per_sqm DESC"
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_avg_price(self, municipality_code: str, year: int | None = None) -> float | None:
        """市町村の平均地価を取得"""
        conditions = ["municipality_code = :code"]
        params: dict[str, Any] = {"code": municipality_code}
        if year:
            conditions.append("year = :year")
            params["year"] = year
        where = " AND ".join(conditions)
        sql = f"SELECT AVG(price_per_sqm) as avg_price FROM land_prices WHERE {where}"
        row = self.conn.execute(sql, params).fetchone()
        return row["avg_price"] if row and row["avg_price"] else None
