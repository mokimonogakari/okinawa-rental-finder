"""地価データの取得・管理

データソース:
1. 不動産情報ライブラリAPI (国土交通省) - 取引価格・地価公示
2. 国土数値情報ダウンロード - 地価公示(L01)・都道府県地価調査(L02)
"""

import json
import logging
import os
import time
import zipfile
from pathlib import Path

import requests

from src.database.models import get_connection
from src.database.repository import LandPriceRepository

logger = logging.getLogger(__name__)

REINFOLIB_BASE_URL = "https://www.reinfolib.mlit.go.jp/ex-api/external"
KOKUDO_DL_BASE = "https://nlftp.mlit.go.jp/ksj/gml/data"
OKINAWA_PREF_CODE = "47"


class ReinfolibClient:
    """不動産情報ライブラリ API クライアント"""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("REINFOLIB_API_KEY", "")
        self.session = requests.Session()
        self.session.headers.update({
            "Ocp-Apim-Subscription-Key": self.api_key,
        })

    def get_transaction_prices(
        self, year: int, area: str = OKINAWA_PREF_CODE,
        city: str | None = None, quarter: int | None = None,
    ) -> list[dict]:
        """不動産取引価格情報を取得 (XIT001)"""
        params = {"year": year, "area": area}
        if city:
            params["city"] = city
        if quarter:
            params["quarter"] = quarter

        try:
            resp = self.session.get(f"{REINFOLIB_BASE_URL}/XIT001", params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])
        except requests.RequestException as e:
            logger.error(f"不動産情報ライブラリAPI エラー: {e}")
            return []

    def get_land_prices(
        self, year: int, area: str = OKINAWA_PREF_CODE,
    ) -> list[dict]:
        """地価公示・地価調査データを取得 (XPT002 - GeoJSON)"""
        params = {"year": year, "area": area}
        try:
            resp = self.session.get(f"{REINFOLIB_BASE_URL}/XPT002", params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
            return [f.get("properties", {}) | {
                "latitude": f["geometry"]["coordinates"][1],
                "longitude": f["geometry"]["coordinates"][0],
            } for f in features if f.get("geometry")]
        except requests.RequestException as e:
            logger.error(f"地価公示API エラー: {e}")
            return []

    def get_municipalities(self, area: str = OKINAWA_PREF_CODE) -> list[dict]:
        """市区町村一覧を取得 (XIT002)"""
        params = {"area": area}
        try:
            resp = self.session.get(f"{REINFOLIB_BASE_URL}/XIT002", params=params, timeout=30)
            resp.raise_for_status()
            return resp.json().get("data", [])
        except requests.RequestException as e:
            logger.error(f"市区町村一覧API エラー: {e}")
            return []


class KokudoDataLoader:
    """国土数値情報 地価データローダー"""

    def __init__(self, data_dir: str | Path = "./data/land_price"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def download_land_price_data(self, year: int = 2024, data_type: str = "L01") -> Path | None:
        """地価公示(L01)または都道府県地価調査(L02)のGMLデータをダウンロード"""
        year_short = str(year)[2:]  # 2024 → "24"
        filename = f"{data_type}-{year_short}_{OKINAWA_PREF_CODE}_GML.zip"

        # URLパターン: https://nlftp.mlit.go.jp/ksj/gml/data/L01/L01-24/L01-24_47_GML.zip
        url = f"{KOKUDO_DL_BASE}/{data_type}/{data_type}-{year_short}/{filename}"

        output_path = self.data_dir / filename
        if output_path.exists():
            logger.info(f"既にダウンロード済み: {output_path}")
            return output_path

        try:
            logger.info(f"ダウンロード中: {url}")
            resp = requests.get(url, timeout=60, stream=True)
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info(f"ダウンロード完了: {output_path}")
            return output_path
        except requests.RequestException as e:
            logger.error(f"ダウンロード失敗: {e}")
            return None

    def extract_and_parse(self, zip_path: Path) -> list[dict]:
        """ZIPファイルを展開し、GeoJSONまたはGMLからデータを抽出"""
        extract_dir = zip_path.parent / zip_path.stem
        if not extract_dir.exists():
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

        # GeoJSONファイルを探す
        geojson_files = list(extract_dir.rglob("*.geojson"))
        if geojson_files:
            return self._parse_geojson(geojson_files[0])

        # GMLファイルを探す (フォールバック)
        gml_files = list(extract_dir.rglob("*.xml")) + list(extract_dir.rglob("*.gml"))
        if gml_files:
            return self._parse_gml(gml_files[0])

        logger.warning(f"パース可能なファイルが見つかりません: {extract_dir}")
        return []

    def _parse_geojson(self, filepath: Path) -> list[dict]:
        """GeoJSONファイルをパース"""
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        results = []
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            geom = feature.get("geometry", {})
            coords = geom.get("coordinates", [None, None])

            results.append({
                "latitude": coords[1] if len(coords) > 1 else None,
                "longitude": coords[0] if len(coords) > 0 else None,
                "price_per_sqm": props.get("L01_006") or props.get("L02_006"),
                "address": props.get("L01_025") or props.get("L02_023") or "",
                "land_use": props.get("L01_027") or props.get("L02_025"),
                "zoning": props.get("L01_029") or props.get("L02_027"),
                "nearest_station": props.get("L01_031") or props.get("L02_029"),
                "station_distance_m": props.get("L01_032") or props.get("L02_030"),
            })
        return results

    def _parse_gml(self, filepath: Path) -> list[dict]:
        """GMLファイルを簡易パース (lxml使用)"""
        try:
            from lxml import etree
        except ImportError:
            logger.error("lxml が必要です: pip install lxml")
            return []

        tree = etree.parse(str(filepath))
        root = tree.getroot()
        nsmap = {k or "default": v for k, v in root.nsmap.items()}

        results = []
        # GMLの構造はデータセットにより異なるため、基本的なパターンに対応
        for member in root.iter():
            if "StandardAreaCode" in member.tag or "L01" in member.tag:
                data = {}
                for child in member:
                    tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    data[tag] = child.text
                if data:
                    results.append(data)

        return results


def fetch_and_store_land_prices(db_path: str, api_key: str | None = None, year: int = 2024):
    """地価データを取得してDBに保存するメイン関数"""
    conn = get_connection(db_path)
    repo = LandPriceRepository(conn)

    # 1. 不動産情報ライブラリAPIから取引価格を取得
    if api_key:
        client = ReinfolibClient(api_key)
        logger.info("不動産情報ライブラリAPIから取引価格を取得中...")

        transactions = client.get_transaction_prices(year=year)
        logger.info(f"取引価格データ: {len(transactions)}件")

        for tx in transactions:
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO transaction_prices
                       (year, municipality, municipality_code, property_type, district,
                        nearest_station, station_walk_minutes, trade_price, price_per_sqm,
                        area_sqm, building_year, structure, land_use, zoning)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        year,
                        tx.get("Municipality"),
                        tx.get("MunicipalityCode"),
                        tx.get("Type"),
                        tx.get("DistrictName"),
                        tx.get("NearestStation"),
                        tx.get("TimeToNearestStation"),
                        tx.get("TradePrice"),
                        tx.get("PricePerUnit"),
                        tx.get("Area"),
                        tx.get("BuildingYear"),
                        tx.get("Structure"),
                        tx.get("Use"),
                        tx.get("CityPlanning"),
                    ),
                )
            except Exception as e:
                logger.warning(f"取引データ保存エラー: {e}")

        conn.commit()

        # 地価公示データ
        land_data = client.get_land_prices(year=year)
        logger.info(f"地価公示データ: {len(land_data)}件")

        for ld in land_data:
            try:
                repo.upsert({
                    "data_source": "reinfolib",
                    "year": year,
                    "address": ld.get("address", ""),
                    "municipality": ld.get("municipality"),
                    "municipality_code": ld.get("municipalityCode"),
                    "latitude": ld.get("latitude"),
                    "longitude": ld.get("longitude"),
                    "price_per_sqm": ld.get("price"),
                    "land_use": ld.get("currentUse"),
                    "zoning": ld.get("cityPlanning"),
                    "nearest_station": ld.get("nearestStation"),
                    "station_distance_m": ld.get("stationDistance"),
                })
            except Exception as e:
                logger.warning(f"地価データ保存エラー: {e}")

    # 2. 国土数値情報からダウンロード
    loader = KokudoDataLoader()
    for data_type in ["L01", "L02"]:
        zip_path = loader.download_land_price_data(year=year, data_type=data_type)
        if zip_path:
            records = loader.extract_and_parse(zip_path)
            logger.info(f"{data_type}データ: {len(records)}件")

            for rec in records:
                try:
                    repo.upsert({
                        "data_source": f"kokudo_{data_type.lower()}",
                        "year": year,
                        "address": rec.get("address", ""),
                        "latitude": rec.get("latitude"),
                        "longitude": rec.get("longitude"),
                        "price_per_sqm": rec.get("price_per_sqm"),
                        "land_use": rec.get("land_use"),
                        "zoning": rec.get("zoning"),
                        "nearest_station": rec.get("nearest_station"),
                        "station_distance_m": rec.get("station_distance_m"),
                    })
                except Exception as e:
                    logger.warning(f"国土数値情報保存エラー: {e}")

    conn.close()
    logger.info("地価データの取得・保存が完了しました")
