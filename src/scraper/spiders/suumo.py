"""SUUMO (suumo.jp) スパイダー - 全国最大手不動産ポータル 沖縄エリア

実サイトのHTML構造 (2026年2月確認):
- 物件ブロック: div.cassetteitem
- 物件名: div.cassetteitem_content-title
- 物件種別: div.cassetteitem_content-label span.ui-pct
- 住所: li.cassetteitem_detail-col1
- 交通: li.cassetteitem_detail-col2 > div.cassetteitem_detail-text
- 築年/階建: li.cassetteitem_detail-col3 > div (2つ)
- 部屋テーブル: table.cassetteitem_other > tbody > tr.js-cassette_link
  - td[2]: 階数
  - td[3]: 賃料(span.cassetteitem_price--rent) / 管理費(span.cassetteitem_price--administration)
  - td[4]: 敷金(span.cassetteitem_price--deposit) / 礼金(span.cassetteitem_price--gratuity)
  - td[5]: 間取り(span.cassetteitem_madori) / 面積(span.cassetteitem_menseki)
  - td[8]: 詳細リンク(a.js-cassette_link_href href="/chintai/jnc_xxx/")
- ページネーション: p.pagination-parts > a (「次へ」テキスト)
"""

import re
from datetime import datetime

import scrapy

from src.scraper.items import RentalPropertyItem

# 沖縄県の主要市町村エリアコード (SUUMO URL用)
OKINAWA_AREA_CODES = [
    "naha", "urasoe", "ginowan", "okinawashi", "nago",
    "itoman", "tomigusuku", "uruma", "nanjo",
    "chatan", "nishihara", "haebaru", "yonabaru", "nakagusuku",
    "kitanakagusuku", "kadena", "yomitan", "kin",
    "motobu", "onna", "ginoza",
    "miyakojima", "ishigaki",
]


class SuumoSpider(scrapy.Spider):
    name = "suumo"
    allowed_domains = ["suumo.jp"]
    custom_settings = {
        "DOWNLOAD_DELAY": 5,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 0.3,
    }

    def start_requests(self):
        """各市町村の一覧ページに直接アクセス"""
        for area_code in OKINAWA_AREA_CODES:
            url = f"https://suumo.jp/chintai/okinawa/sc_{area_code}/"
            yield scrapy.Request(url=url, callback=self.parse_list)

    def parse_list(self, response):
        """物件一覧ページをパース"""
        cassettes = response.css("div.cassetteitem")

        for cassette in cassettes:
            # --- 建物単位の情報 ---
            building_name = cassette.css(
                "div.cassetteitem_content-title::text"
            ).get("").strip()

            property_type = cassette.css(
                "div.cassetteitem_content-label span::text"
            ).get("").strip()

            address = cassette.css(
                "li.cassetteitem_detail-col1::text"
            ).get("").strip()

            # 交通 (複数行の場合あり、最初のものを使用)
            transport_texts = cassette.css(
                "li.cassetteitem_detail-col2 div.cassetteitem_detail-text::text"
            ).getall()
            transport_text = ""
            for t in transport_texts:
                t = t.strip()
                if t:
                    transport_text = t
                    break

            # 築年数・階建
            col3_divs = cassette.css("li.cassetteitem_detail-col3 div::text").getall()
            building_age_text = col3_divs[0].strip() if len(col3_divs) > 0 else ""
            total_floors_text = col3_divs[1].strip() if len(col3_divs) > 1 else ""

            # --- 部屋単位の情報 ---
            rows = cassette.css("table.cassetteitem_other tbody tr.js-cassette_link")

            for row in rows:
                item = RentalPropertyItem()
                item["source"] = "suumo"
                item["name"] = building_name
                item["property_type"] = property_type
                item["address"] = address

                # 築年
                if building_age_text:
                    item["building_year"] = self._parse_building_year(building_age_text)

                # 総階数
                total_floors = self._parse_total_floors(total_floors_text)
                if total_floors:
                    item["total_floors"] = total_floors

                # 交通
                if transport_text:
                    station, minutes, t_type = self._parse_transport(transport_text)
                    item["nearest_station"] = station
                    item["station_walk_minutes"] = minutes
                    item["transport_type"] = t_type

                # td セルを取得
                tds = row.css("td")

                # td[2]: 階数
                floor_text = tds[2].css("::text").get("").strip() if len(tds) > 2 else ""
                if floor_text:
                    floor_num, _ = self._parse_floors(floor_text)
                    item["floor_number"] = floor_num

                # td[3]: 賃料 / 管理費
                if len(tds) > 3:
                    item["rent"] = tds[3].css(
                        "span.cassetteitem_price--rent span.cassetteitem_other-emphasis::text"
                    ).get("").strip()
                    if not item["rent"]:
                        # フォールバック
                        item["rent"] = tds[3].css(
                            "span.cassetteitem_price--rent ::text"
                        ).get("").strip()
                    item["management_fee"] = tds[3].css(
                        "span.cassetteitem_price--administration::text"
                    ).get("").strip()

                # td[4]: 敷金 / 礼金
                if len(tds) > 4:
                    item["deposit_months"] = tds[4].css(
                        "span.cassetteitem_price--deposit::text"
                    ).get("").strip()
                    item["key_money_months"] = tds[4].css(
                        "span.cassetteitem_price--gratuity::text"
                    ).get("").strip()

                # td[5]: 間取り / 面積
                if len(tds) > 5:
                    item["floor_plan"] = tds[5].css(
                        "span.cassetteitem_madori::text"
                    ).get("").strip()
                    # 面積は sup タグの 2 を含むので結合
                    area_parts = tds[5].css("span.cassetteitem_menseki ::text").getall()
                    item["area_sqm"] = "".join(area_parts).strip()

                # td[8]: 詳細リンク
                detail_link = row.css(
                    "a.js-cassette_link_href::attr(href)"
                ).get()
                if not detail_link:
                    detail_link = row.css("a[href*='/chintai/jnc_']::attr(href)").get()

                if detail_link:
                    item["source_url"] = response.urljoin(detail_link)
                    m = re.search(r"jnc_(\w+)", detail_link)
                    item["source_id"] = m.group(1) if m else detail_link.rstrip("/").split("/")[-1]
                else:
                    # source_id がないと DB upsert できないので生成
                    item["source_id"] = f"suumo_{building_name}_{floor_text}".replace(" ", "")
                    item["source_url"] = response.url

                yield item

        # ページネーション: 「次へ」リンク
        next_page = response.css("p.pagination-parts a:contains('次へ')::attr(href)").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse_list)

    @staticmethod
    def _parse_building_year(text: str) -> int | None:
        # 「築9年」→ 現在年 - 9
        m = re.search(r"築(\d+)年", text)
        if m:
            return datetime.now().year - int(m.group(1))
        # 「2020年築」
        m = re.search(r"(\d{4})年", text)
        if m:
            return int(m.group(1))
        if "新築" in text:
            return datetime.now().year
        return None

    @staticmethod
    def _parse_total_floors(text: str) -> int | None:
        # 「10階建」→ 10
        m = re.search(r"(\d+)階建", text)
        return int(m.group(1)) if m else None

    @staticmethod
    def _parse_transport(text: str) -> tuple[str | None, str | None, str | None]:
        """「沖縄都市モノレール/安里駅 歩10分」をパース"""
        transport_type = None
        if "モノレール" in text or "ゆいレール" in text:
            transport_type = "monorail"
        elif "バス" in text:
            transport_type = "bus"

        # 駅名: 「/安里駅」のパターン
        station = None
        m = re.search(r"/(.+?)駅", text)
        if m:
            station = m.group(1).strip()
        else:
            m = re.search(r"/(.+?)(?:停|　| )", text)
            if m:
                station = m.group(1).strip()

        # 徒歩分数: 「歩10分」
        minutes = None
        m = re.search(r"歩(\d+)分", text)
        if m:
            minutes = m.group(1)

        return station, minutes, transport_type

    @staticmethod
    def _parse_floors(text: str) -> tuple[int | None, int | None]:
        # 「7階」→ (7, None)
        # 「3-7階」→ (7, None) 上階を採用
        m = re.search(r"(\d+)-(\d+)階", text)
        if m:
            return int(m.group(2)), None
        m = re.search(r"(\d+)階", text)
        if m:
            return int(m.group(1)), None
        return None, None
