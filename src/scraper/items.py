"""Scrapy Items定義 - 全サイト共通の物件データ構造"""

import scrapy


class RentalPropertyItem(scrapy.Item):
    """賃貸物件アイテム"""

    # ソース情報
    source = scrapy.Field()
    source_id = scrapy.Field()
    source_url = scrapy.Field()

    # 基本情報
    name = scrapy.Field()
    address = scrapy.Field()
    municipality = scrapy.Field()
    municipality_code = scrapy.Field()
    latitude = scrapy.Field()
    longitude = scrapy.Field()

    # 賃料
    rent = scrapy.Field()
    management_fee = scrapy.Field()
    deposit_months = scrapy.Field()
    key_money_months = scrapy.Field()
    security_deposit = scrapy.Field()

    # スペック
    property_type = scrapy.Field()
    structure = scrapy.Field()
    floor_plan = scrapy.Field()
    room_count = scrapy.Field()
    area_sqm = scrapy.Field()
    building_year = scrapy.Field()
    building_age = scrapy.Field()
    floor_number = scrapy.Field()
    total_floors = scrapy.Field()

    # 交通
    nearest_station = scrapy.Field()
    station_walk_minutes = scrapy.Field()
    transport_type = scrapy.Field()

    # 駐車場
    parking_available = scrapy.Field()
    parking_fee = scrapy.Field()
    parking_spaces = scrapy.Field()

    # 設備
    has_aircon = scrapy.Field()
    has_auto_lock = scrapy.Field()
    has_delivery_box = scrapy.Field()
    has_bath_dryer = scrapy.Field()
    has_reheating = scrapy.Field()
    has_washstand = scrapy.Field()
    has_indoor_laundry = scrapy.Field()
    has_internet = scrapy.Field()
    has_fiber = scrapy.Field()
    has_bath_toilet_separate = scrapy.Field()
    has_flooring = scrapy.Field()
    has_pet_ok = scrapy.Field()

    # 契約
    lease_type = scrapy.Field()
    guarantor_required = scrapy.Field()
    brokerage_fee_months = scrapy.Field()
    move_in_date = scrapy.Field()
