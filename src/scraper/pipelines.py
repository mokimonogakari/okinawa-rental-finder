"""Scrapyパイプライン - データクレンジング・正規化・DB保存"""

import re
import sqlite3
from datetime import datetime
from pathlib import Path

import yaml

from src.database.models import get_connection, init_db
from src.database.repository import PropertyRepository


class DataCleansingPipeline:
    """データクレンジング・正規化パイプライン"""

    # 間取り正規化マッピング
    FLOOR_PLAN_MAP = {
        "ワンルーム": "1R",
        "1ルーム": "1R",
    }

    # 構造正規化マッピング
    STRUCTURE_MAP = {
        "鉄筋コンクリート": "RC",
        "鉄筋コンクリート造": "RC",
        "RC造": "RC",
        "RC": "RC",
        "鉄骨鉄筋コンクリート": "SRC",
        "鉄骨鉄筋コンクリート造": "SRC",
        "SRC造": "SRC",
        "SRC": "SRC",
        "鉄骨造": "S",
        "鉄骨": "S",
        "S造": "S",
        "軽量鉄骨": "LS",
        "軽量鉄骨造": "LS",
        "木造": "W",
    }

    # 市町村名→コードマッピング (沖縄県)
    MUNICIPALITY_MAP = {}

    def open_spider(self, spider):
        config_path = Path(__file__).parent.parent.parent / "config" / "search_conditions.yaml"
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)
            for region, cities in config.get("areas", {}).items():
                for city in cities:
                    self.MUNICIPALITY_MAP[city["name"]] = city["code"]

    def process_item(self, item, spider):
        # 賃料の正規化
        item["rent"] = self._parse_price(item.get("rent"))
        item["management_fee"] = self._parse_price(item.get("management_fee")) or 0

        # 敷金・礼金の正規化 (「1ヶ月」→ 1.0)
        item["deposit_months"] = self._parse_months(item.get("deposit_months"))
        item["key_money_months"] = self._parse_months(item.get("key_money_months"))

        # 面積の正規化 (「25.5㎡」→ 25.5)
        item["area_sqm"] = self._parse_float(item.get("area_sqm"))

        # 間取り正規化
        fp = item.get("floor_plan", "")
        if fp in self.FLOOR_PLAN_MAP:
            item["floor_plan"] = self.FLOOR_PLAN_MAP[fp]

        # 部屋数の抽出
        if item.get("floor_plan"):
            item["room_count"] = self._extract_room_count(item["floor_plan"])

        # 構造正規化
        structure = item.get("structure", "")
        if structure:
            item["structure"] = self.STRUCTURE_MAP.get(structure, structure)

        # 築年数計算
        if item.get("building_year"):
            current_year = datetime.now().year
            item["building_age"] = current_year - int(item["building_year"])

        # 市町村コードの付与
        if item.get("municipality") and not item.get("municipality_code"):
            muni = item["municipality"]
            item["municipality_code"] = self.MUNICIPALITY_MAP.get(muni)

        # 住所から市町村を抽出
        if not item.get("municipality") and item.get("address"):
            item["municipality"] = self._extract_municipality(item["address"])
            if item["municipality"]:
                item["municipality_code"] = self.MUNICIPALITY_MAP.get(item["municipality"])

        # 駐車場フラグ
        parking = item.get("parking_available")
        if isinstance(parking, str):
            item["parking_available"] = 1 if parking not in ("なし", "無", "") else 0

        # 設備フラグのブール正規化
        for key in list(item.keys()):
            if key.startswith("has_"):
                val = item.get(key)
                if isinstance(val, str):
                    item[key] = 1 if val else 0
                elif val is None:
                    item[key] = 0

        # 徒歩分数
        item["station_walk_minutes"] = self._parse_int(item.get("station_walk_minutes"))

        return item

    @staticmethod
    def _parse_price(value) -> int | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return int(value)
        s = str(value).replace(",", "").replace("円", "").replace("¥", "").strip()
        # 「5.5万」「5.5万円」形式
        m = re.match(r"([\d.]+)\s*万", s)
        if m:
            return int(float(m.group(1)) * 10000)
        # 純粋な数値
        m = re.match(r"(\d+)", s)
        if m:
            return int(m.group(1))
        return None

    @staticmethod
    def _parse_months(value) -> float:
        if value is None or value == "" or value == "-":
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).replace("ヶ月", "").replace("ヵ月", "").replace("カ月", "").strip()
        if s in ("なし", "無", "-", "0"):
            return 0.0
        try:
            return float(s)
        except ValueError:
            return 0.0

    @staticmethod
    def _parse_float(value) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).replace("㎡", "").replace("m²", "").replace("m2", "").replace(",", "").replace("約", "").strip()
        try:
            v = float(s)
            # 専有面積として異常な値を除外 (一般的な賃貸は5〜300㎡)
            if v < 5 or v > 300:
                return None
            return v
        except ValueError:
            return None

    @staticmethod
    def _parse_int(value) -> int | None:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        s = str(value).replace("分", "").replace("min", "").strip()
        try:
            return int(s)
        except ValueError:
            return None

    @staticmethod
    def _extract_room_count(floor_plan: str) -> int:
        m = re.match(r"(\d+)", floor_plan)
        return int(m.group(1)) if m else 1

    @staticmethod
    def _extract_municipality(address: str) -> str | None:
        """住所文字列から沖縄県内の市町村名を抽出"""
        # 「沖縄県那覇市xxx」→「那覇市」
        m = re.search(r"(?:沖縄県)?(\S+?[市町村])", address)
        return m.group(1) if m else None


class SQLitePipeline:
    """SQLiteへの保存パイプライン"""

    def __init__(self):
        self.conn = None
        self.repo = None

    def open_spider(self, spider):
        settings_path = Path(__file__).parent.parent.parent / "config" / "settings.yaml"
        with open(settings_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        db_path = Path(__file__).parent.parent.parent / config["database"]["path"]
        self.conn = init_db(db_path)
        self.repo = PropertyRepository(self.conn)

    def close_spider(self, spider):
        if self.conn:
            self.conn.close()

    def process_item(self, item, spider):
        data = {k: v for k, v in dict(item).items() if v is not None}
        if "rent" not in data or data["rent"] is None:
            spider.logger.warning(f"賃料なしのためスキップ: {data.get('source_url', 'unknown')}")
            return item
        self.repo.upsert_property(data)
        return item


class DuplicateFilterPipeline:
    """重複物件フィルタ"""

    def __init__(self):
        self.seen = set()

    def process_item(self, item, spider):
        key = (item.get("source"), item.get("source_id"))
        if key in self.seen:
            from scrapy.exceptions import DropItem
            raise DropItem(f"重複物件: {key}")
        self.seen.add(key)
        return item
