"""HOME'S (homes.co.jp) スパイダー - LIFULL HOME'S 沖縄エリア

実サイトのHTML構造 (2026年2月確認):
- 建物カード: div.mod-mergeBuilding--rent--photo (.rMansion / .rApart)
- 建物名: span.bukkenName
- 建物種別: span.bType ("賃貸マンション" / "賃貸アパート")
- 建物仕様テーブル: div.bukkenSpec table
  - 所在地: th:contains("所在地") + td
  - 交通: span.prg-stationText (複数)
  - 築年数/階数: th:contains("築年数/階数") + td ("12年 / 6階建")
- 部屋テーブル: table.unitSummary tbody.prg-roomList
  - 部屋行: tr.prg-room[data-href]
  - 階/部屋番号: td.floar li.roomKaisuu / li.roomNumber
  - 賃料/管理費: td.price span.num (万円), slash後のテキストが管理費
  - 敷金/礼金: td.price <br>後 ("無/1ヶ月/-/-")
  - 間取り/面積: td.layout (br区切り "2DK<br>38.16m²")
  - 詳細リンク: td.detail a.prg-detailAnchor / tr[data-href]
  - 設備タグ: tr.prg-relatedKeywordsRow li.relatedKeyword
- ページネーション: div.mod-listPaging li.nextPage a
  URL: ?page={N}
"""

import re
from datetime import datetime

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
        # 通常の建物カード
        buildings = response.css("div.mod-mergeBuilding--rent--photo")

        for building in buildings:
            # --- 建物単位の情報 ---
            building_name = building.css("span.bukkenName::text").get("").strip()
            building_type = building.css("span.bType::text").get("").strip()

            # 所在地: bukkenSpec テーブルの "所在地" 行
            address = ""
            spec_rows = building.css("div.bukkenSpec table tr")
            age_text = ""
            total_floors_text = ""
            for row in spec_rows:
                th_text = row.css("th::text").get("").strip()
                td_text = row.css("td::text").get("").strip()
                if "所在地" in th_text:
                    address = td_text
                elif "築年数" in th_text or "階数" in th_text:
                    age_text = td_text

            # 交通
            transport_texts = building.css("span.prg-stationText::text").getall()
            primary_transport = ""
            for t in transport_texts:
                t = t.strip()
                if t:
                    primary_transport = t
                    break

            # 築年数/階数パース ("12年 / 6階建")
            building_year = None
            total_floors = None
            if age_text:
                building_year = self._parse_building_age(age_text)
                m = re.search(r"(\d+)階建", age_text)
                if m:
                    total_floors = int(m.group(1))

            # --- 部屋単位 ---
            room_rows = building.css(
                "table.unitSummary tbody.prg-roomList tr.prg-room.prg-roomInfo"
            )
            if not room_rows:
                room_rows = building.css("tr.prg-room[data-href]")

            for room_row in room_rows:
                item = RentalPropertyItem()
                item["source"] = "homes"
                item["name"] = building_name
                item["property_type"] = building_type
                item["address"] = address

                if building_year:
                    item["building_year"] = building_year
                if total_floors:
                    item["total_floors"] = total_floors

                # 交通
                if primary_transport:
                    station, minutes, t_type = self._parse_transport(
                        primary_transport
                    )
                    item["nearest_station"] = station
                    item["station_walk_minutes"] = minutes
                    item["transport_type"] = t_type

                # 階/部屋番号: td.floar
                floor_text = room_row.css("li.roomKaisuu::text").get("")
                if floor_text:
                    m = re.search(r"(\d+)階", floor_text)
                    if m:
                        item["floor_number"] = int(m.group(1))

                # 賃料/管理費: td.price
                price_cell = room_row.css("td.price")
                if price_cell:
                    # 賃料: span.num の数値 + "万円"
                    rent_num = price_cell.css("span.num::text").get("")
                    if rent_num:
                        item["rent"] = f"{rent_num.strip()}万円"

                    # 管理費: priceLabel後のテキスト ("/" 以降)
                    price_texts = price_cell.css(
                        "span[id^='label-'] ::text"
                    ).getall()
                    full_price_text = "".join(price_texts)
                    mgmt_match = re.search(
                        r"/\s*([\d,]+円|-)", full_price_text
                    )
                    if mgmt_match:
                        item["management_fee"] = mgmt_match.group(1).strip()

                    # 敷金/礼金: <br>後のテキスト ("無/1ヶ月/-/-")
                    all_text = " ".join(
                        price_cell.css("::text").getall()
                    ).strip()
                    deposit_match = re.search(
                        r"([^\s/]+)/([^\s/]+)/([^\s/]+)/([^\s/]+)\s*$",
                        all_text,
                    )
                    if deposit_match:
                        deposit = deposit_match.group(1)
                        key_money = deposit_match.group(2)
                        if deposit and deposit != "無" and deposit != "-":
                            item["deposit_months"] = deposit
                        if key_money and key_money != "無" and key_money != "-":
                            item["key_money_months"] = key_money

                # 間取り/面積: td.layout
                layout_cell = room_row.css("td.layout")
                if layout_cell:
                    layout_texts = layout_cell.css("::text").getall()
                    layout_full = " ".join(t.strip() for t in layout_texts if t.strip())
                    # "2DK 38.16m²" or "1K 25.0m²"
                    parts = re.split(r"\s+", layout_full, maxsplit=1)
                    if parts:
                        item["floor_plan"] = parts[0]
                    if len(parts) > 1:
                        item["area_sqm"] = parts[1]

                # 詳細リンク
                detail_href = room_row.css(
                    "td.detail a.prg-detailAnchor::attr(href)"
                ).get()
                if not detail_href:
                    detail_href = room_row.attrib.get("data-href", "")
                if detail_href:
                    item["source_url"] = response.urljoin(detail_href)
                    # URLからIDを抽出
                    m = re.search(r"/room/([^/]+)/", detail_href)
                    if m:
                        item["source_id"] = m.group(1)
                    else:
                        m = re.search(r"b-(\d+)", detail_href)
                        item["source_id"] = (
                            m.group(1) if m
                            else detail_href.rstrip("/").split("/")[-1]
                        )
                else:
                    item["source_id"] = f"homes_{building_name}_{floor_text}"
                    item["source_url"] = response.url

                # 設備タグ (relatedKeyword)
                # 次のtr.prg-relatedKeywordsRow から取得
                keywords_row = room_row.xpath(
                    "following-sibling::tr["
                    "contains(@class,'prg-relatedKeywordsRow')][1]"
                )
                if keywords_row:
                    keywords = keywords_row.css(
                        "li.relatedKeyword span::text"
                    ).getall()
                    equip_text = " ".join(kw.strip() for kw in keywords)
                    self._parse_equipment(item, equip_text)

                yield item

        # ページネーション
        next_page = response.css(
            "div.mod-listPaging li.nextPage a::attr(href)"
        ).get()
        if next_page:
            yield response.follow(next_page, callback=self.parse_list)

    @staticmethod
    def _parse_building_age(text: str) -> int | None:
        """'12年 / 6階建' or '新築 / 3階建' → 築年数から建築年を算出"""
        if "新築" in text:
            return datetime.now().year
        m = re.search(r"(\d+)年", text)
        if m:
            age = int(m.group(1))
            return datetime.now().year - age
        return None

    @staticmethod
    def _parse_transport(
        text: str,
    ) -> tuple[str | None, str | None, str | None]:
        """'沖縄都市モノレール 美栄橋駅 徒歩8分' をパース"""
        transport_type = None
        if "モノレール" in text or "ゆいレール" in text:
            transport_type = "monorail"
        elif "バス" in text:
            transport_type = "bus"

        station = None
        m = re.search(r"(?:レール|線)\s+(.+?)(?:駅|停)", text)
        if m:
            station = m.group(1).strip()
        else:
            m = re.search(r"\s(.+?)(?:駅|停)\s", text)
            if m:
                station = m.group(1).strip()

        minutes = None
        m = re.search(r"徒歩(\d+)分", text)
        if m:
            minutes = m.group(1)

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
            "has_reheating": ["追い焚き", "追焚"],
            "has_washstand": ["独立洗面", "洗面化粧台"],
            "has_indoor_laundry": ["室内洗濯", "洗濯機"],
            "has_internet": ["インターネット", "ネット対応"],
            "has_fiber": ["光ファイバー", "光回線"],
            "has_bath_toilet_separate": ["バス・トイレ別", "バストイレ別"],
            "has_flooring": ["フローリング"],
            "has_pet_ok": ["ペット可", "ペット相談"],
        }
        for key, keywords in mapping.items():
            item[key] = 1 if any(kw in text for kw in keywords) else 0
