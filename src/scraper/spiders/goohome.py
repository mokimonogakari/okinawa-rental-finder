"""グーホーム (goohome.jp) スパイダー - 沖縄最大級ローカル不動産サイト"""

import re

import scrapy

from src.scraper.items import RentalPropertyItem


class GoohomeSpider(scrapy.Spider):
    name = "goohome"
    allowed_domains = ["goohome.jp"]
    custom_settings = {
        "DOWNLOAD_DELAY": 3,
    }

    def start_requests(self):
        # グーホームの賃貸物件一覧ページ (沖縄全域)
        yield scrapy.Request(
            url="https://goohome.jp/rent/okinawa/",
            callback=self.parse_list,
        )

    def parse_list(self, response):
        """物件一覧ページをパース"""
        # 各物件リンクを抽出
        property_links = response.css("a[href*='/rent/detail/']::attr(href)").getall()
        if not property_links:
            # 代替セレクタ
            property_links = response.css(".property-item a::attr(href)").getall()

        for link in property_links:
            yield response.follow(link, callback=self.parse_detail)

        # 次のページ
        next_page = response.css("a.next::attr(href)").get()
        if not next_page:
            next_page = response.css('a[rel="next"]::attr(href)').get()
        if next_page:
            yield response.follow(next_page, callback=self.parse_list)

    def parse_detail(self, response):
        """物件詳細ページをパース"""
        item = RentalPropertyItem()
        item["source"] = "goohome"
        item["source_url"] = response.url

        # source_idをURLから抽出
        m = re.search(r"/detail/(\d+)", response.url)
        item["source_id"] = m.group(1) if m else response.url.split("/")[-1]

        # 物件名
        item["name"] = self._extract_text(response, [
            "h1.property-name::text",
            "h1::text",
            ".property-title::text",
        ])

        # 住所
        item["address"] = self._extract_text(response, [
            ".address::text",
            'th:contains("所在地") + td::text',
            'dt:contains("所在地") + dd::text',
        ])

        # 賃料
        rent_text = self._extract_text(response, [
            ".rent .price::text",
            ".price-main::text",
            'th:contains("賃料") + td::text',
        ])
        item["rent"] = rent_text

        # 管理費
        item["management_fee"] = self._extract_text(response, [
            ".management-fee::text",
            'th:contains("管理費") + td::text',
            'th:contains("共益費") + td::text',
        ])

        # 間取り
        item["floor_plan"] = self._extract_text(response, [
            ".floor-plan::text",
            'th:contains("間取り") + td::text',
        ])

        # 面積
        item["area_sqm"] = self._extract_text(response, [
            ".area::text",
            'th:contains("面積") + td::text',
            'th:contains("専有面積") + td::text',
        ])

        # 築年
        age_text = self._extract_text(response, [
            'th:contains("築年") + td::text',
            'th:contains("築年月") + td::text',
        ])
        if age_text:
            item["building_year"] = self._parse_building_year(age_text)

        # 構造
        item["structure"] = self._extract_text(response, [
            'th:contains("構造") + td::text',
            'th:contains("建物構造") + td::text',
        ])

        # 物件種別
        item["property_type"] = self._extract_text(response, [
            'th:contains("物件種目") + td::text',
            'th:contains("種別") + td::text',
            ".property-type::text",
        ])

        # 階数
        floor_text = self._extract_text(response, [
            'th:contains("所在階") + td::text',
            'th:contains("階") + td::text',
        ])
        if floor_text:
            item["floor_number"], item["total_floors"] = self._parse_floors(floor_text)

        # 交通
        transport_text = self._extract_text(response, [
            ".transport::text",
            'th:contains("交通") + td::text',
            'th:contains("最寄") + td::text',
        ])
        if transport_text:
            station, minutes, t_type = self._parse_transport(transport_text)
            item["nearest_station"] = station
            item["station_walk_minutes"] = minutes
            item["transport_type"] = t_type

        # 駐車場
        parking_text = self._extract_text(response, [
            'th:contains("駐車場") + td::text',
        ])
        if parking_text:
            item["parking_available"] = parking_text
            fee_match = re.search(r"([\d,]+)\s*円", parking_text)
            if fee_match:
                item["parking_fee"] = int(fee_match.group(1).replace(",", ""))

        # 敷金・礼金
        item["deposit_months"] = self._extract_text(response, [
            'th:contains("敷金") + td::text',
        ])
        item["key_money_months"] = self._extract_text(response, [
            'th:contains("礼金") + td::text',
        ])

        # 設備抽出
        equipment_text = " ".join(response.css(
            'th:contains("設備") + td::text, .equipment ::text'
        ).getall())
        self._parse_equipment(item, equipment_text)

        yield item

    def _extract_text(self, response, selectors: list[str]) -> str | None:
        for sel in selectors:
            text = response.css(sel).get()
            if text:
                return text.strip()
        return None

    @staticmethod
    def _parse_building_year(text: str) -> int | None:
        # 「2020年3月」→ 2020
        m = re.search(r"(\d{4})\s*年", text)
        if m:
            return int(m.group(1))
        # 「令和2年」→ 2020
        era_map = {"令和": 2018, "平成": 1988, "昭和": 1925}
        for era, offset in era_map.items():
            m = re.search(rf"{era}\s*(\d+)\s*年", text)
            if m:
                return offset + int(m.group(1))
        return None

    @staticmethod
    def _parse_floors(text: str) -> tuple[int | None, int | None]:
        # 「3階 / 5階建」→ (3, 5)
        m = re.search(r"(\d+)\s*階\s*/?\s*(\d+)\s*階建", text)
        if m:
            return int(m.group(1)), int(m.group(2))
        m = re.search(r"(\d+)\s*階", text)
        if m:
            return int(m.group(1)), None
        return None, None

    @staticmethod
    def _parse_transport(text: str) -> tuple[str | None, str | None, str | None]:
        # 「ゆいレール 牧志駅 徒歩5分」or「バス停 xxx 徒歩3分」
        transport_type = None
        if "ゆいレール" in text or "モノレール" in text:
            transport_type = "monorail"
        elif "バス" in text:
            transport_type = "bus"

        # 駅/バス停名
        m = re.search(r"(?:駅|バス停)\s*[「」]?(.+?)[「」]?\s*(?:徒歩|まで)", text)
        station = m.group(1).strip() if m else None
        if not station:
            m = re.search(r"(?:ゆいレール|モノレール)\s*(.+?)\s*(?:駅|徒歩)", text)
            station = m.group(1).strip() if m else None

        # 徒歩分数
        m = re.search(r"徒歩\s*(\d+)\s*分", text)
        minutes = m.group(1) if m else None

        return station, minutes, transport_type

    @staticmethod
    def _parse_equipment(item, text: str):
        """設備テキストから各フラグを設定"""
        if not text:
            return
        mapping = {
            "has_aircon": ["エアコン", "冷暖房"],
            "has_auto_lock": ["オートロック"],
            "has_delivery_box": ["宅配ボックス", "宅配BOX"],
            "has_bath_dryer": ["浴室乾燥", "浴室暖房乾燥"],
            "has_reheating": ["追い焚き", "追焚", "追いだき"],
            "has_washstand": ["独立洗面", "洗面化粧台"],
            "has_indoor_laundry": ["室内洗濯", "洗濯機置場(室内)"],
            "has_internet": ["インターネット", "ネット対応"],
            "has_fiber": ["光ファイバー", "光回線"],
            "has_bath_toilet_separate": ["バストイレ別", "バス・トイレ別", "セパレート"],
            "has_flooring": ["フローリング"],
            "has_pet_ok": ["ペット可", "ペット相談"],
        }
        for key, keywords in mapping.items():
            item[key] = 1 if any(kw in text for kw in keywords) else 0
