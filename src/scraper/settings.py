"""Scrapy設定"""

BOT_NAME = "okinawa_rental"
SPIDER_MODULES = ["src.scraper.spiders"]
NEWSPIDER_MODULE = "src.scraper.spiders"

# robots.txt 遵守
ROBOTSTXT_OBEY = True

# リクエスト制御
CONCURRENT_REQUESTS = 1
CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_DELAY = 4
RANDOMIZE_DOWNLOAD_DELAY = True

# AutoThrottle (サーバー負荷に応じた自動調整)
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 3
AUTOTHROTTLE_MAX_DELAY = 10
AUTOTHROTTLE_TARGET_CONCURRENCY = 0.5

# リトライ
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]

# ミドルウェア
DOWNLOADER_MIDDLEWARES = {
    "src.scraper.middlewares.RandomUserAgentMiddleware": 400,
    "src.scraper.middlewares.PoliteRequestMiddleware": 500,
}

# パイプライン
ITEM_PIPELINES = {
    "src.scraper.pipelines.DuplicateFilterPipeline": 100,
    "src.scraper.pipelines.DataCleansingPipeline": 200,
    "src.scraper.pipelines.SQLitePipeline": 300,
}

# ログ
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"

# キャッシュ (開発時)
# HTTPCACHE_ENABLED = True
# HTTPCACHE_DIR = ".scrapy/httpcache"

# Request fingerprinting
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
