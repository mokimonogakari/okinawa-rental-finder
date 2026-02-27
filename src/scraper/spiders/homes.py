"""HOME'S (homes.co.jp) スパイダー - LIFULL HOME'S 沖縄エリア"""

import re

import scrapy

from src.scraper.items import RentalPropertyItem


class HomesSpider(scrapy.Spider):
    name = "homes"
    allowed_domains = ["www.homes.co.jp"]
    custom_settings = {
        "DOWNLOAD_DELAY": 5,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 0.3,
    }

    def start_requests(self):
        yield scrapy.Request(
            url="https://www.homes.co.jp/chintai/okinawa/list/",
            callback=self.parse_list,
        )

    def parse_list(self, response):
        """物件一覧ページをパース"""
        # HOME'Sの物件カード
        modules = response.css(".mod-mergeBuilding, .mod-bukkenDetail")

        for module in modules:
            # 建物情報
            building_name = module.css(
                ".bukkenName::text, .prg-buildingName::text"
            ).get("").strip()
            address = module.css(
                ".bukkenAddress::text, .prg-address::text"
            ).get("").strip()

            transport_text = module.css(
                ".bukkenAccess::text, .prg-access::text"
            ).get("")

            age_text = module.css(
                ".bukkenAge::text, .prg-buildYear::text"
            ).get("")
            structure_text = module.css(
                ".bukkenStructure::text, .prg-structure::text"
            ).get("")

            # 各部屋
            rooms = module.css(".prg-roomTable tr, .mod-mergeRoom")
            if not rooms:
                # 単一部屋の物件
                item = self._build_item_from_module(
                    module, building_name, address, transport_text,
                    age_text, structure_text, response
                )
                if item:
                    yield item
                continue

            for room in rooms:
                item = RentalPropertyItem()
                item["source"] = "homes"
                item["name"] = building_name
                item["address"] = address
                item["structure"] = structure_text.strip()

                if age_text:
                    item["building_year"] = self._parse_building_year(age_text.strip())

                if transport_text:
                    station, minutes, t_type = self._parse_transport(transport_text)
                    item["nearest_station"] = station
                    item["station_walk_minutes"] = minutes
                    item["transport_type"] = t_type

                # 賃料
                item["rent"] = room.css(
                    ".prg-price::text, .roomRent::text"
                ).get("").strip()
                item["management_fee"] = room.css(
                    ".prg-adminCost::text, .roomAdminCost::text"
                ).get("").strip()

                # 間取り・面積
                item["floor_plan"] = room.css(
                    ".prg-madori::text, .roomMadori::text"
                ).get("").strip()
                item["area_sqm"] = room.css(
                    ".prg-menseki::text, .roomMenseki::text"
                ).get("").strip()

                # 敷金・礼金
                item["deposit_months"] = room.css(
                    ".prg-shikikin::text, .roomShikikin::text"
                ).get("").strip()
                item["key_money_months"] = room.css(
                    ".prg-reikin::text, .roomReikin::text"
                ).get("").strip()

                # 階
                floor_text = room.css(
                    ".prg-floor::text, .roomFloor::text"
                ).get("")
                if floor_text:
                    item["floor_number"], item["total_floors"] = self._parse_floors(floor_text)

                # 詳細リンク
                detail_link = room.css("a[href*='/chintai/room']::attr(href)").get()
                if not detail_link:
                    detail_link = room.css("a::attr(href)").get()
                if detail_link:
                    item["source_url"] = response.urljoin(detail_link)
                    m = re.search(r"/room/(\w+)", detail_link)
                    item["source_id"] = m.group(1) if m else detail_link.split("/")[-2]
                else:
                    item["source_id"] = f"homes_{building_name}"
                    item["source_url"] = response.url

                yield item

        # ページネーション
        next_page = response.css("a.nextPage::attr(href)").get()
        if not next_page:
            next_page = response.css("li.next a::attr(href)").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse_list)

    def _build_item_from_module(self, module, name, address, transport, age, structure, response):
        """単一部屋の物件からアイテムを生成"""
        item = RentalPropertyItem()
        item["source"] = "homes"
        item["name"] = name
        item["address"] = address
        item["structure"] = structure.strip()

        if age:
            item["building_year"] = self._parse_building_year(age.strip())

        if transport:
            station, minutes, t_type = self._parse_transport(transport)
            item["nearest_station"] = station
            item["station_walk_minutes"] = minutes
            item["transport_type"] = t_type

        item["rent"] = module.css(".prg-price::text, .bukkenPrice::text").get("").strip()
        item["management_fee"] = module.css(".prg-adminCost::text").get("").strip()
        item["floor_plan"] = module.css(".prg-madori::text, .bukkenMadori::text").get("").strip()
        item["area_sqm"] = module.css(".prg-menseki::text, .bukkenMenseki::text").get("").strip()
        item["deposit_months"] = module.css(".prg-shikikin::text").get("").strip()
        item["key_money_months"] = module.css(".prg-reikin::text").get("").strip()

        detail_link = module.css("a[href*='/chintai/']::attr(href)").get()
        if detail_link:
            item["source_url"] = response.urljoin(detail_link)
            m = re.search(r"/(\w+)/?$", detail_link)
            item["source_id"] = m.group(1) if m else name
        else:
            item["source_url"] = response.url
            item["source_id"] = f"homes_{name}"

        if not item.get("rent"):
            return None
        return item

    @staticmethod
    def _parse_building_year(text: str) -> int | None:
        m = re.search(r"(\d{4})年", text)
        if m:
            return int(m.group(1))
        m = re.search(r"築(\d+)年", text)
        if m:
            from datetime import datetime
            return datetime.now().year - int(m.group(1))
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

        m = re.search(r"/(.+?)(?:駅|停)", text)
        station = m.group(1).strip() if m else None

        m = re.search(r"歩?(\d+)分", text)
        minutes = m.group(1) if m else None

        return station, minutes, transport_type

    @staticmethod
    def _parse_floors(text: str) -> tuple[int | None, int | None]:
        m = re.search(r"(\d+)階/?(\d+)?階建?", text)
        if m:
            return int(m.group(1)), int(m.group(2)) if m.group(2) else None
        m = re.search(r"(\d+)階", text)
        if m:
            return int(m.group(1)), None
        return None, None
