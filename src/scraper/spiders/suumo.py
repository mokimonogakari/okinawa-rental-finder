"""SUUMO (suumo.jp) スパイダー - 全国最大手不動産ポータル 沖縄エリア"""

import re

import scrapy

from src.scraper.items import RentalPropertyItem


class SuumoSpider(scrapy.Spider):
    name = "suumo"
    allowed_domains = ["suumo.jp"]
    custom_settings = {
        "DOWNLOAD_DELAY": 5,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 0.3,
    }

    # 沖縄県の市区町村別URL (SUUMOのエリアコード)
    BASE_URL = "https://suumo.jp/chintai/okinawa/sc_{area_code}/"

    # 全沖縄を一括検索
    START_URL = "https://suumo.jp/chintai/okinawa/"

    def start_requests(self):
        yield scrapy.Request(
            url=self.START_URL,
            callback=self.parse_area_list,
        )

    def parse_area_list(self, response):
        """エリア選択ページ → 各市町村の一覧ページへ"""
        # 市区町村リンクを取得
        area_links = response.css(
            ".searchitem-list a[href*='/chintai/okinawa/sc_']::attr(href)"
        ).getall()

        if area_links:
            for link in area_links:
                yield response.follow(link, callback=self.parse_list)
        else:
            # 直接一覧ページの場合
            yield from self.parse_list(response)

    def parse_list(self, response):
        """物件一覧ページをパース"""
        # SUUMOの物件カセット (各物件ブロック)
        cassettes = response.css(".cassetteitem")

        for cassette in cassettes:
            # 物件の基本情報 (建物単位)
            building_name = cassette.css(".cassetteitem_content-title::text").get("").strip()
            address = cassette.css(".cassetteitem_detail-col1::text").get("").strip()

            transport_items = cassette.css(".cassetteitem_detail-col2 .cassetteitem_detail-text::text").getall()

            age_structure = cassette.css(".cassetteitem_detail-col3 div::text").getall()
            building_age_text = age_structure[0].strip() if len(age_structure) > 0 else ""
            structure_text = age_structure[1].strip() if len(age_structure) > 1 else ""

            # 部屋単位の情報 (1建物に複数部屋)
            rooms = cassette.css("table.cassetteitem_other")
            for room in rooms:
                item = RentalPropertyItem()
                item["source"] = "suumo"
                item["name"] = building_name
                item["address"] = address
                item["structure"] = structure_text

                # 築年
                if building_age_text:
                    item["building_year"] = self._parse_building_year(building_age_text)

                # 交通
                if transport_items:
                    station, minutes, t_type = self._parse_transport(transport_items[0])
                    item["nearest_station"] = station
                    item["station_walk_minutes"] = minutes
                    item["transport_type"] = t_type

                # 部屋情報
                tds = room.css("td")
                # 階
                floor_text = tds[2].css("::text").get("").strip() if len(tds) > 2 else ""
                if floor_text:
                    item["floor_number"], item["total_floors"] = self._parse_floors(floor_text)

                # 賃料・管理費
                item["rent"] = tds[3].css(".cassetteitem_other-emphasis::text").get("").strip() if len(tds) > 3 else None
                item["management_fee"] = tds[4].css("::text").get("").strip() if len(tds) > 4 else None

                # 敷金・礼金
                item["deposit_months"] = tds[5].css("::text").get("").strip() if len(tds) > 5 else None
                item["key_money_months"] = tds[6].css("::text").get("").strip() if len(tds) > 6 else None

                # 間取り・面積
                item["floor_plan"] = tds[7].css("::text").get("").strip() if len(tds) > 7 else None
                item["area_sqm"] = tds[8].css("::text").get("").strip() if len(tds) > 8 else None

                # 詳細ページURL
                detail_link = room.css("a[href*='/chintai/jnc_']::attr(href)").get()
                if not detail_link:
                    detail_link = room.css("td.ui-text--midium a::attr(href)").get()
                if detail_link:
                    item["source_url"] = response.urljoin(detail_link)
                    m = re.search(r"jnc_(\w+)", detail_link)
                    item["source_id"] = m.group(1) if m else detail_link.split("/")[-2]
                else:
                    item["source_id"] = f"{building_name}_{floor_text}"
                    item["source_url"] = response.url

                yield item

        # ページネーション
        next_page = response.css(".pagination-parts a[rel='next']::attr(href)").get()
        if not next_page:
            next_page = response.css("p.pagination-parts a:last-child::attr(href)").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse_list)

    @staticmethod
    def _parse_building_year(text: str) -> int | None:
        m = re.search(r"(\d{4})年", text)
        if m:
            return int(m.group(1))
        # 「築15年」→ 現在年 - 15
        m = re.search(r"築(\d+)年", text)
        if m:
            from datetime import datetime
            return datetime.now().year - int(m.group(1))
        # 新築
        if "新築" in text:
            from datetime import datetime
            return datetime.now().year
        return None

    @staticmethod
    def _parse_transport(text: str) -> tuple[str | None, str | None, str | None]:
        transport_type = None
        if "ゆいレール" in text or "モノレール" in text:
            transport_type = "monorail"
        elif "バス" in text:
            transport_type = "bus"

        # 「ゆいレール/牧志駅 歩5分」
        m = re.search(r"(?:駅|停)\s*歩?(\d+)分", text)
        minutes = m.group(1) if m else None

        m = re.search(r"/(.+?)(?:駅|停)", text)
        station = m.group(1).strip() if m else None

        return station, minutes, transport_type

    @staticmethod
    def _parse_floors(text: str) -> tuple[int | None, int | None]:
        m = re.search(r"(\d+)階/?(\d+)?階建?", text.replace("-", ""))
        if m:
            return int(m.group(1)), int(m.group(2)) if m.group(2) else None
        m = re.search(r"(\d+)階", text)
        if m:
            return int(m.group(1)), None
        return None, None
