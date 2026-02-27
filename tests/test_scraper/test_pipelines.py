"""パイプラインテスト"""

from src.scraper.pipelines import DataCleansingPipeline


class MockSpider:
    name = "test"


def test_parse_price_yen():
    pipeline = DataCleansingPipeline()
    assert pipeline._parse_price("50,000円") == 50000
    assert pipeline._parse_price("50000") == 50000
    assert pipeline._parse_price(50000) == 50000


def test_parse_price_man():
    pipeline = DataCleansingPipeline()
    assert pipeline._parse_price("5.5万") == 55000
    assert pipeline._parse_price("5.5万円") == 55000
    assert pipeline._parse_price("10万") == 100000


def test_parse_months():
    pipeline = DataCleansingPipeline()
    assert pipeline._parse_months("1ヶ月") == 1.0
    assert pipeline._parse_months("0.5ヶ月") == 0.5
    assert pipeline._parse_months("なし") == 0.0
    assert pipeline._parse_months(None) == 0.0
    assert pipeline._parse_months(2) == 2.0


def test_parse_float():
    pipeline = DataCleansingPipeline()
    assert pipeline._parse_float("25.5㎡") == 25.5
    assert pipeline._parse_float("35m2") == 35.0
    assert pipeline._parse_float(40.0) == 40.0


def test_extract_room_count():
    pipeline = DataCleansingPipeline()
    assert pipeline._extract_room_count("1LDK") == 1
    assert pipeline._extract_room_count("2DK") == 2
    assert pipeline._extract_room_count("3LDK") == 3
    assert pipeline._extract_room_count("1R") == 1


def test_extract_municipality():
    pipeline = DataCleansingPipeline()
    assert pipeline._extract_municipality("沖縄県那覇市首里") == "那覇市"
    assert pipeline._extract_municipality("那覇市牧志") == "那覇市"
    assert pipeline._extract_municipality("沖縄県中城村") == "中城村"
    assert pipeline._extract_municipality("北谷町") == "北谷町"
