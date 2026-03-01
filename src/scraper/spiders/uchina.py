"""うちなーらいふ (e-uchina.net) スパイダー - 沖縄特化物件サイト

SPAサイトのため、内部JSON API経由でデータ取得 (2026年2月確認):
- エンドポイント: https://www.e-uchina.net/api/search
- パラメータ: searchType=jukyo, city[0]={JIS市区町村コード}, perPage=50
- レスポンス: JSON (Laravel Paginator形式)
  data.bukkens.data[] に物件レコード配列
  ページネーション: page=N, per_page=50, last_page=N
- 個別物件API: /api/bukken/{bukken_hid}
- 認証不要、CSRFトークン不要

主な物件フィールド:
- bukken_hid: 物件ID ("r-5980-2250510-0344")
- permalink: 詳細ページURL
- disp_name / bukken_name: 物件名
- address_disp: 住所 ("浦添市経塚")
- price_disp: 賃料 ("15万円")
- price_kyoeki_disp: 管理費 ("11,000円")
- price_shiki_disp / price_rei_disp: 敷金/礼金
- madori_space_all_disp: 間取り ("3LDK")
- house_space_metr: 面積(㎡)
- kozo_type_disp: 構造 ("RC")
- kenchiku_date: 築年月 ("201911")
- floor_number: 階数
- building_house_kaisu_chijo: 総階数
- transport_info: 交通情報
- short_parking_disp: 駐車場
- parking_price: 駐車場料金
- options: 設備(カンマ区切り)
- map_ido / map_keido: 緯度/経度
- bukken_type_disp: 物件種別
"""

import json
import re

import scrapy

from src.scraper.items import RentalPropertyItem

# 沖縄県の主要市町村 JISコード
OKINAWA_CITY_CODES = [
    ("47201", "那覇市"), ("47205", "宜野湾市"), ("47207", "石垣市"),
    ("47208", "浦添市"), ("47209", "名護市"), ("47210", "糸満市"),
    ("47211", "沖縄市"), ("47212", "豊見城市"), ("47213", "うるま市"),
    ("47214", "宮古島市"), ("47215", "南城市"),
    ("47301", "国頭村"), ("47302", "大宜味村"), ("47303", "東村"),
    ("47306", "今帰仁村"), ("47308", "本部町"), ("47311", "恩納村"),
    ("47313", "宜野座村"), ("47314", "金武町"),
    ("47324", "伊江村"), ("47325", "読谷村"),
    ("47326", "嘉手納町"), ("47327", "北谷町"), ("47328", "北中城村"),
    ("47329", "中城村"), ("47330", "西原町"),
    ("47348", "与那原町"), ("47350", "南風原町"),
    ("47353", "渡嘉敷村"), ("47354", "座間味村"),
    ("47361", "粟国村"), ("47362", "渡名喜村"),
    ("47375", "南大東村"), ("47376", "北大東村"),
    ("47381", "伊平屋村"), ("47382", "伊是名村"),
    ("47357", "久米島町"), ("47358", "八重瀬町"),
    ("47401", "多良間村"), ("47402", "竹富町"), ("47404", "与那国町"),
]


class UchinaSpider(scrapy.Spider):
    name = "uchina"
    allowed_domains = ["e-uchina.net"]
    custom_settings = {
        "DOWNLOAD_DELAY": 2,
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        },
    }

    def start_requests(self):
        """各市町村のAPI検索エンドポイントにリクエスト (perPage=50で効率化)"""
        for city_code, city_name in OKINAWA_CITY_CODES:
            url = (
                f"https://www.e-uchina.net/api/search"
                f"?searchType=jukyo&city[0]={city_code}&perPage=50"
            )
            yield scrapy.Request(
                url=url,
                callback=self.parse_api,
                cb_kwargs={"city_code": city_code, "city_name": city_name},
                headers={"Referer": "https://www.e-uchina.net/jukyo/"},
            )

    def parse_api(self, response, city_code: str, city_name: str):
        """APIレスポンス(JSON)をパース"""
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError:
            self.logger.error(f"JSON parse failed for city_code={city_code}")
            return

        bukkens = data.get("data", {}).get("bukkens", {})
        records = bukkens.get("data", [])

        for rec in records:
            item = self._build_item(rec)
            if item:
                yield item

        # ページネーション
        next_url = bukkens.get("next_page_url")
        if next_url:
            yield scrapy.Request(
                url=next_url,
                callback=self.parse_api,
                cb_kwargs={"city_code": city_code, "city_name": city_name},
                headers={"Referer": "https://www.e-uchina.net/jukyo/"},
            )

    def _build_item(self, rec: dict) -> RentalPropertyItem | None:
        """APIレコードからRentalPropertyItemを生成"""
        item = RentalPropertyItem()
        item["source"] = "uchina"

        # 物件ID
        bukken_hid = rec.get("bukken_hid", "")
        item["source_id"] = bukken_hid or str(rec.get("id", ""))

        # 詳細URL
        item["source_url"] = rec.get("permalink", "")

        # 物件名
        item["name"] = rec.get("disp_name") or rec.get("bukken_name", "")

        # 住所
        item["address"] = rec.get("address_disp", "")

        # 賃料
        price_disp = rec.get("price_disp", "")
        if price_disp:
            item["rent"] = price_disp

        # 管理費
        kyoeki_disp = rec.get("price_kyoeki_disp", "")
        if kyoeki_disp:
            item["management_fee"] = kyoeki_disp

        # 敷金
        shiki_disp = rec.get("price_shiki_disp", "")
        if shiki_disp and shiki_disp != "ナシ":
            item["deposit_months"] = shiki_disp

        # 礼金
        rei_disp = rec.get("price_rei_disp", "")
        if rei_disp and rei_disp != "ナシ":
            item["key_money_months"] = rei_disp

        # 保証金
        hosho_disp = rec.get("price_hosho_disp", "")
        if hosho_disp and hosho_disp != "ナシ":
            item["security_deposit"] = hosho_disp

        # 間取り
        madori = rec.get("madori_space_all_disp", "")
        if madori:
            item["floor_plan"] = madori

        # 面積 (専有面積を優先、なければ建物面積)
        space_metr = rec.get("man_senyu_metr") or rec.get("house_space_metr")
        if space_metr:
            item["area_sqm"] = f"{space_metr}㎡"

        # 構造
        kozo = rec.get("kozo_type_disp", "")
        if kozo:
            item["structure"] = kozo

        # 物件種別
        bukken_type = rec.get("bukken_type_disp", "")
        if bukken_type:
            item["property_type"] = bukken_type

        # 築年
        kenchiku_date = rec.get("kenchiku_date", "")
        if kenchiku_date:
            item["building_year"] = self._parse_kenchiku_date(kenchiku_date)

        # 階数
        floor_num = rec.get("floor_number")
        if floor_num:
            try:
                item["floor_number"] = int(floor_num)
            except (ValueError, TypeError):
                pass

        total_floors = rec.get("building_house_kaisu_chijo")
        if total_floors:
            try:
                item["total_floors"] = int(total_floors)
            except (ValueError, TypeError):
                pass

        # 交通
        transport = rec.get("transport_info", "")
        if transport:
            station, minutes, t_type = self._parse_transport(transport)
            item["nearest_station"] = station
            item["station_walk_minutes"] = minutes
            item["transport_type"] = t_type

        # 駐車場
        parking_disp = rec.get("short_parking_disp", "")
        if parking_disp:
            item["parking_available"] = parking_disp
        parking_price = rec.get("parking_price")
        if parking_price and int(parking_price) > 0:
            item["parking_fee"] = int(parking_price)

        # 緯度経度
        lat = rec.get("map_ido")
        lng = rec.get("map_keido")
        if lat:
            item["latitude"] = float(lat)
        if lng:
            item["longitude"] = float(lng)

        # 設備 (options フィールドから)
        options_str = rec.get("options", "")
        self._parse_options(item, options_str)

        return item

    @staticmethod
    def _parse_kenchiku_date(date_str: str) -> int | None:
        """'201911' → 2019"""
        if len(date_str) >= 4:
            try:
                return int(date_str[:4])
            except ValueError:
                pass
        return None

    @staticmethod
    def _parse_transport(text: str) -> tuple[str | None, str | None, str | None]:
        """'【バス停】第二経塚バス停: 徒歩約7分' をパース"""
        transport_type = None
        if "モノレール" in text or "ゆいレール" in text:
            transport_type = "monorail"
        elif "バス" in text:
            transport_type = "bus"

        # 駅名/バス停名を抽出
        station = None
        m = re.search(r"】(.+?)(?:駅|バス停)", text)
        if m:
            station = m.group(1).strip()
        else:
            m = re.search(r"(?:駅|バス停)\s*(.+?):", text)
            if m:
                station = m.group(1).strip()

        # 徒歩分数
        minutes = None
        m = re.search(r"徒歩約?(\d+)分", text)
        if m:
            minutes = m.group(1)

        return station, minutes, transport_type

    @staticmethod
    def _parse_options(item, options_str: str):
        """options文字列から設備フラグを設定"""
        if not options_str:
            return

        mapping = {
            "has_aircon": ["option_aircon", "option_eakon"],
            "has_auto_lock": ["option_auto_lock"],
            "has_delivery_box": ["option_takuhai"],
            "has_bath_dryer": ["option_yokushitsu_kanso"],
            "has_reheating": ["option_oidaki"],
            "has_washstand": ["option_senmenjo"],
            "has_indoor_laundry": ["option_sentakuki"],
            "has_internet": ["option_internet", "option_net"],
            "has_fiber": ["option_hikari"],
            "has_bath_toilet_separate": ["option_bt"],
            "has_flooring": ["option_flooring"],
            "has_pet_ok": ["option_pet"],
        }
        for key, option_names in mapping.items():
            item[key] = 1 if any(o in options_str for o in option_names) else 0
