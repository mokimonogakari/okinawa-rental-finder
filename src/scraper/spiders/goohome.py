"""グーホーム (goohome.jp) スパイダー - 沖縄最大級ローカル不動産サイト

実サイトのHTML構造 (2026年2月確認):
- 物件カード: section.insp_caset
- メインコンテナ: div.inside_box[pno="xxx-xxxx"] (pno属性=物件ID)
- 賃料: span.price ("8.45") + span.price_name ("万円")
- 管理費: span.price_kanri ("管理費等:4,000円")
- 敷金/礼金: span.price_sikirei ("敷1ヶ月/礼1ヶ月")
- 保証金: span.price_hosyou ("保証金:-")
- 間取り: span.floor_plan ("1LDK")
- 面積: span.floor_plan_area ("約50㎡")
- 住所: p.address span.text ("那覇市<br>壺川２丁目")
- 駐車場: p.parking span.text ("1台/10,000円")
- 建物情報: div.other_info ul > li (構造, 築年, 階数)
- 物件種別: div.prop-label-box span.prop-label
- 画像リンク: div.imgbox a[href] → 詳細ページ
- ページネーション: div.insp_page-n ul > li > a
  URL: ?page={page}-{items_per_page}
"""

import re

import scrapy

from src.scraper.items import RentalPropertyItem

# グーホームの沖縄主要エリア (URL用)
GOOHOME_AREAS = [
    "naha", "urasoe", "ginowan", "okinawashi", "nago",
    "itoman", "tomigusuku", "uruma", "nanjo",
    "chatan", "nishihara", "haebaru", "yonabaru", "nakagusuku",
    "kitanakagusuku", "kadena", "yomitan", "kin",
    "motobu", "onna", "ginoza",
    "miyakojima", "ishigaki",
]


class GoohomeSpider(scrapy.Spider):
    name = "goohome"
    allowed_domains = ["goohome.jp"]
    custom_settings = {
        "DOWNLOAD_DELAY": 3,
    }

    def start_requests(self):
        """各市町村の物件一覧ページにアクセス (部屋単位表示)"""
        for area in GOOHOME_AREAS:
            url = f"https://goohome.jp/chintai/mansion/{area}/?page=1-20"
            yield scrapy.Request(url=url, callback=self.parse_list)

    def parse_list(self, response):
        """物件一覧ページをパース"""
        cards = response.css("section.insp_caset")

        for card in cards:
            item = RentalPropertyItem()
            item["source"] = "goohome"

            # 物件ID: div.inside_box の pno 属性
            pno = card.css("div.inside_box::attr(pno)").get()
            if not pno:
                pno = card.css("input[name='pck[]']::attr(value)").get()
            if not pno:
                continue
            item["source_id"] = pno

            # 詳細ページURL
            detail_href = card.css("div.imgbox a::attr(href)").get()
            if not detail_href:
                detail_href = card.css("p.detail_view_btn a::attr(href)").get()
            if detail_href:
                item["source_url"] = response.urljoin(detail_href)
            else:
                item["source_url"] = response.urljoin(
                    f"/chintai/mansion/{pno}/"
                )

            # 物件種別ラベル
            labels = card.css("div.prop-label-box span.prop-label::text").getall()
            for label in labels:
                label = label.strip()
                if label in ("賃貸アパート", "賃貸マンション", "一戸建て", "賃貸テラスハウス"):
                    item["property_type"] = label
                    break

            # 賃料: span.price + span.price_name
            rent_value = card.css("span.price::text").get("")
            rent_unit = card.css("span.price_name::text").get("")
            if rent_value:
                item["rent"] = f"{rent_value.strip()}{rent_unit.strip()}"

            # 管理費: span.price_kanri ("管理費等:4,000円")
            kanri_text = card.css("span.price_kanri::text").get("")
            if kanri_text:
                item["management_fee"] = kanri_text.strip()

            # 敷金/礼金: span.price_sikirei ("敷1ヶ月/礼1ヶ月")
            sikirei_text = card.css("span.price_sikirei::text").get("")
            if sikirei_text:
                deposit, key_money = self._parse_sikirei(sikirei_text)
                item["deposit_months"] = deposit
                item["key_money_months"] = key_money

            # 保証金: span.price_hosyou ("保証金:-")
            hosyou_text = card.css("span.price_hosyou::text").get("")
            if hosyou_text and "保証金" in hosyou_text:
                item["security_deposit"] = hosyou_text.strip()

            # 間取り: span.floor_plan
            floor_plan = card.css("span.floor_plan::text").get("")
            if floor_plan:
                item["floor_plan"] = floor_plan.strip()

            # 面積: span.floor_plan_area ("約50㎡")
            area_text = card.css("span.floor_plan_area::text").get("")
            if area_text:
                item["area_sqm"] = area_text.strip()

            # 住所: p.address span.text
            address_parts = card.css("p.address span.text ::text").getall()
            if address_parts:
                item["address"] = "".join(
                    p.strip() for p in address_parts
                ).strip()

            # 駐車場: p.parking span.text
            parking_text = card.css("p.parking span.text::text").get("")
            if parking_text:
                parking_text = parking_text.strip()
                item["parking_available"] = parking_text
                fee_match = re.search(r"([\d,]+)\s*円", parking_text)
                if fee_match:
                    item["parking_fee"] = int(
                        fee_match.group(1).replace(",", "")
                    )

            # 建物情報: div.other_info ul > li (構造, 築年, 階数)
            other_items = card.css("div.other_info ul > li::text").getall()
            for info in other_items:
                info = info.strip()
                if not info:
                    continue
                # 構造: "鉄筋(RC造)", "鉄骨(S造)" etc.
                if re.search(r"(RC|SRC|S造|木造|鉄筋|鉄骨|ブロック)", info):
                    item["structure"] = info
                # 築年: "築2026年(-)" or "築1991年(34年)"
                elif info.startswith("築") or re.search(r"築\d+年", info):
                    item["building_year"] = self._parse_building_year(info)
                # 階数: "2階/5階建" or "4階/4階建"
                elif re.search(r"\d+階", info):
                    floor_num, total = self._parse_floors(info)
                    item["floor_number"] = floor_num
                    item["total_floors"] = total

            # PR/コメント → 物件名の代わりに使用
            comment = card.css("div.comment.web_pr p::text").get("")
            if not comment:
                comment = card.css("div.comment.web_pr h3::text").get("")
            if comment:
                item["name"] = comment.strip()[:100]

            yield item

        # ページネーション: div.insp_page-n 内の次ページリンク
        # PC版: div.insp_page-n 内のリンク一覧から次ページを探す
        current_url = response.url
        page_links = response.css("div.insp_page-n a::attr(href)").getall()
        next_page = self._find_next_page(current_url, page_links)

        # フォールバック: SP版 "次の20件" リンク
        if not next_page:
            next_page = response.css(
                "ul.insp_prev-next li.next a::attr(href)"
            ).get()

        if next_page:
            yield response.follow(next_page, callback=self.parse_list)

    @staticmethod
    def _parse_sikirei(text: str) -> tuple[str | None, str | None]:
        """'敷1ヶ月/礼1ヶ月' → ('1ヶ月', '1ヶ月')"""
        deposit = None
        key_money = None
        m = re.search(r"敷(\S+)", text)
        if m:
            val = m.group(1).rstrip("/")
            deposit = val if val != "-" else None
        m = re.search(r"礼(\S+)", text)
        if m:
            val = m.group(1).rstrip("/")
            key_money = val if val != "-" else None
        return deposit, key_money

    @staticmethod
    def _parse_building_year(text: str) -> int | None:
        """'築2026年(-)' or '築1991年(34年)' → 2026 or 1991"""
        m = re.search(r"築(\d{4})年", text)
        if m:
            return int(m.group(1))
        # 「新築」
        if "新築" in text:
            from datetime import datetime
            return datetime.now().year
        return None

    @staticmethod
    def _parse_floors(text: str) -> tuple[int | None, int | None]:
        """'2階/5階建' → (2, 5), '4階建' → (None, 4)"""
        m = re.search(r"(\d+)階/(\d+)階建", text)
        if m:
            return int(m.group(1)), int(m.group(2))
        m = re.search(r"(\d+)階建", text)
        if m:
            return None, int(m.group(1))
        m = re.search(r"(\d+)階", text)
        if m:
            return int(m.group(1)), None
        return None, None

    @staticmethod
    def _find_next_page(
        current_url: str, page_links: list[str]
    ) -> str | None:
        """現在ページの次ページURLを特定"""
        m = re.search(r"page=(\d+)-(\d+)", current_url)
        if not m:
            return None
        current_page = int(m.group(1))
        items_per_page = int(m.group(2))
        next_page_num = current_page + 1
        target = f"page={next_page_num}-{items_per_page}"
        for link in page_links:
            if target in link:
                return link
        return None
