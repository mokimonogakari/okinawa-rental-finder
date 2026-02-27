"""うちなーらいふ (e-uchina.net) スパイダー - 沖縄特化物件サイト"""

import re

import scrapy

from src.scraper.items import RentalPropertyItem


class UchinaSpider(scrapy.Spider):
    name = "uchina"
    allowed_domains = ["e-uchina.net"]
    custom_settings = {
        "DOWNLOAD_DELAY": 4,
    }

    def start_requests(self):
        yield scrapy.Request(
            url="https://e-uchina.net/chintai/",
            callback=self.parse_list,
        )

    def parse_list(self, response):
        """物件一覧ページをパース"""
        property_links = response.css("a[href*='/chintai/detail']::attr(href)").getall()
        if not property_links:
            property_links = response.css(".bukken-item a::attr(href)").getall()

        for link in property_links:
            yield response.follow(link, callback=self.parse_detail)

        next_page = response.css("a.next::attr(href)").get()
        if not next_page:
            next_page = response.css('a[rel="next"]::attr(href)').get()
            if not next_page:
                next_page = response.css("li.next a::attr(href)").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse_list)

    def parse_detail(self, response):
        """物件詳細ページをパース"""
        item = RentalPropertyItem()
        item["source"] = "uchina"
        item["source_url"] = response.url

        m = re.search(r"/detail[/_]?(\w+)", response.url)
        item["source_id"] = m.group(1) if m else response.url.split("/")[-1]

        item["name"] = self._css_first(response, [
            "h1::text",
            ".bukken-name::text",
            ".property-name::text",
        ])

        item["address"] = self._css_first(response, [
            'th:contains("住所") + td::text',
            'th:contains("所在地") + td::text',
            ".address::text",
        ])

        item["rent"] = self._css_first(response, [
            ".chinryou::text",
            ".price::text",
            'th:contains("賃料") + td::text',
        ])

        item["management_fee"] = self._css_first(response, [
            'th:contains("管理費") + td::text',
            'th:contains("共益費") + td::text',
        ])

        item["floor_plan"] = self._css_first(response, [
            'th:contains("間取") + td::text',
            ".madori::text",
        ])

        item["area_sqm"] = self._css_first(response, [
            'th:contains("面積") + td::text',
            'th:contains("専有") + td::text',
        ])

        age_text = self._css_first(response, [
            'th:contains("築年") + td::text',
        ])
        if age_text:
            item["building_year"] = self._parse_year(age_text)

        item["structure"] = self._css_first(response, [
            'th:contains("構造") + td::text',
        ])

        item["property_type"] = self._css_first(response, [
            'th:contains("種別") + td::text',
            'th:contains("物件種目") + td::text',
        ])

        floor_text = self._css_first(response, [
            'th:contains("階") + td::text',
        ])
        if floor_text:
            item["floor_number"], item["total_floors"] = self._parse_floors(floor_text)

        transport_text = self._css_first(response, [
            'th:contains("交通") + td::text',
            'th:contains("最寄") + td::text',
        ])
        if transport_text:
            item["nearest_station"], item["station_walk_minutes"], item["transport_type"] = (
                self._parse_transport(transport_text)
            )

        parking_text = self._css_first(response, [
            'th:contains("駐車場") + td::text',
        ])
        if parking_text:
            item["parking_available"] = parking_text
            fee = re.search(r"([\d,]+)\s*円", parking_text)
            if fee:
                item["parking_fee"] = int(fee.group(1).replace(",", ""))

        item["deposit_months"] = self._css_first(response, [
            'th:contains("敷金") + td::text',
        ])
        item["key_money_months"] = self._css_first(response, [
            'th:contains("礼金") + td::text',
        ])

        equip_text = " ".join(
            response.css('th:contains("設備") + td ::text, .equipment ::text').getall()
        )
        self._parse_equipment(item, equip_text)

        yield item

    @staticmethod
    def _css_first(response, selectors: list[str]) -> str | None:
        for sel in selectors:
            text = response.css(sel).get()
            if text:
                return text.strip()
        return None

    @staticmethod
    def _parse_year(text: str) -> int | None:
        m = re.search(r"(\d{4})\s*年", text)
        if m:
            return int(m.group(1))
        era_map = {"令和": 2018, "平成": 1988, "昭和": 1925}
        for era, offset in era_map.items():
            m = re.search(rf"{era}\s*(\d+)\s*年", text)
            if m:
                return offset + int(m.group(1))
        return None

    @staticmethod
    def _parse_floors(text: str) -> tuple[int | None, int | None]:
        m = re.search(r"(\d+)\s*階\s*/?\s*(\d+)\s*階建", text)
        if m:
            return int(m.group(1)), int(m.group(2))
        m = re.search(r"(\d+)\s*階", text)
        if m:
            return int(m.group(1)), None
        return None, None

    @staticmethod
    def _parse_transport(text: str) -> tuple[str | None, str | None, str | None]:
        transport_type = None
        if "ゆいレール" in text or "モノレール" in text:
            transport_type = "monorail"
        elif "バス" in text:
            transport_type = "bus"
        m = re.search(r"(?:ゆいレール|モノレール)\s*(.+?)\s*(?:駅|徒歩)", text)
        station = m.group(1).strip() if m else None
        m = re.search(r"徒歩\s*(\d+)\s*分", text)
        minutes = m.group(1) if m else None
        return station, minutes, transport_type

    @staticmethod
    def _parse_equipment(item, text: str):
        if not text:
            return
        mapping = {
            "has_aircon": ["エアコン", "冷暖房"],
            "has_auto_lock": ["オートロック"],
            "has_delivery_box": ["宅配ボックス"],
            "has_bath_dryer": ["浴室乾燥"],
            "has_reheating": ["追い焚き", "追焚"],
            "has_washstand": ["独立洗面"],
            "has_indoor_laundry": ["室内洗濯"],
            "has_internet": ["インターネット"],
            "has_fiber": ["光ファイバー"],
            "has_bath_toilet_separate": ["バストイレ別", "セパレート"],
            "has_flooring": ["フローリング"],
            "has_pet_ok": ["ペット可", "ペット相談"],
        }
        for key, keywords in mapping.items():
            item[key] = 1 if any(kw in text for kw in keywords) else 0
