"""LINE Webhook受信 — 友だち追加時にユーザーIDを記録"""

import hashlib
import hmac
import base64
import json
import logging
import os
import re
from http.server import HTTPServer, BaseHTTPRequestHandler

logger = logging.getLogger(__name__)

CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
USER_IDS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "line_user_ids.txt")

# LINE ユーザーIDの形式: U + 32桁の16進数
LINE_USER_ID_PATTERN = re.compile(r"^U[0-9a-f]{32}$")


def verify_signature(body: bytes, signature: str) -> bool:
    """Webhookリクエストの署名を検証"""
    if not CHANNEL_SECRET:
        logger.error("LINE_CHANNEL_SECRET が未設定のためリクエストを拒否")
        return False
    digest = hmac.new(
        CHANNEL_SECRET.encode("utf-8"), body, hashlib.sha256
    ).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def save_user_id(user_id: str) -> None:
    """ユーザーIDをファイルに保存"""
    if not LINE_USER_ID_PATTERN.match(user_id):
        logger.warning("不正なユーザーID形式を検出")
        return

    os.makedirs(os.path.dirname(USER_IDS_FILE), exist_ok=True)

    existing = set()
    if os.path.exists(USER_IDS_FILE):
        with open(USER_IDS_FILE) as f:
            existing = {line.strip() for line in f if line.strip()}

    if user_id not in existing:
        with open(USER_IDS_FILE, "a") as f:
            f.write(user_id + "\n")
        logger.info(f"新しいユーザーID保存: {user_id[:8]}***")
    else:
        logger.debug(f"既存ユーザーID: {user_id[:8]}***")


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        signature = self.headers.get("X-Line-Signature", "")

        if not verify_signature(body, signature):
            self.send_response(403)
            self.end_headers()
            return

        try:
            data = json.loads(body)
            for event in data.get("events", []):
                event_type = event.get("type")
                user_id = event.get("source", {}).get("userId", "")

                if event_type == "follow" and user_id:
                    save_user_id(user_id)
                elif event_type == "message" and user_id:
                    save_user_id(user_id)

        except json.JSONDecodeError:
            logger.warning("不正なJSONリクエスト")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')

    def log_message(self, format, *args):
        logger.debug(format % args)


def run_webhook_server(port: int = 8502):
    """Webhookサーバーを起動"""
    server = HTTPServer(("0.0.0.0", port), WebhookHandler)
    logger.info(f"LINE Webhook server listening on port {port}")
    server.serve_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_webhook_server()
