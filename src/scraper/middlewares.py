"""Scrapyミドルウェア - リクエスト制御"""

import random

from scrapy import signals


class RandomUserAgentMiddleware:
    """ランダムUser-Agentミドルウェア"""

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    ]

    def process_request(self, request, spider):
        request.headers["User-Agent"] = random.choice(self.USER_AGENTS)


class PoliteRequestMiddleware:
    """礼儀正しいリクエスト制御"""

    @classmethod
    def from_crawler(cls, crawler):
        ext = cls()
        crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)
        return ext

    def spider_opened(self, spider):
        spider.logger.info(f"PoliteRequestMiddleware: {spider.name} started")

    def process_request(self, request, spider):
        request.headers.setdefault("Accept", "text/html,application/xhtml+xml")
        request.headers.setdefault("Accept-Language", "ja,en;q=0.9")
        return None
