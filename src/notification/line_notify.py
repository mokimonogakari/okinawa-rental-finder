"""LINE Messaging API 通知機能"""

import json
import logging
import os
from pathlib import Path

import requests
import yaml

from src.database.models import init_db
from src.database.repository import PropertyRepository, SavedSearchRepository

logger = logging.getLogger(__name__)

LINE_PUSH_API = "https://api.line.me/v2/bot/message/push"
LINE_MULTICAST_API = "https://api.line.me/v2/bot/message/multicast"
# Messaging API: 1メッセージあたり最大5000文字
LINE_MESSAGE_MAX_CHARS = 5000


def _get_token() -> str:
    """チャネルアクセストークンを取得"""
    return os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")


def _get_user_ids() -> list[str]:
    """送信先ユーザーIDリストを取得"""
    ids_str = os.getenv("LINE_USER_IDS", "")
    return [uid.strip() for uid in ids_str.split(",") if uid.strip()]


def send_line_message(message: str, token: str | None = None, user_ids: list[str] | None = None) -> bool:
    """LINE Messaging APIでメッセージを送信"""
    token = token or _get_token()
    if not token:
        logger.error("LINE_CHANNEL_ACCESS_TOKEN が設定されていません")
        return False

    user_ids = user_ids or _get_user_ids()
    if not user_ids:
        logger.error("LINE_USER_IDS が設定されていません")
        return False

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # 複数ユーザーへ送信: multicast API を使用
    body = {
        "to": user_ids,
        "messages": [{"type": "text", "text": message}],
    }

    try:
        resp = requests.post(LINE_MULTICAST_API, headers=headers, json=body, timeout=10)
        if resp.status_code == 200:
            logger.info(f"LINE通知送信成功 ({len(user_ids)}人)")
            return True
        else:
            logger.error(f"LINE通知エラー: {resp.status_code} {resp.text}")
            return False
    except requests.RequestException as e:
        logger.error(f"LINE通知送信失敗: {e}")
        return False


# 後方互換: 旧関数名でも呼べるようにする
send_line_notification = send_line_message


def send_test_notification() -> bool:
    """テスト通知を送信"""
    return send_line_message("🏠 沖縄賃貸ファインダー\nテスト通知です。正常に動作しています。")


def format_property_notification(prop: dict) -> str:
    """物件情報を通知用テキストにフォーマット"""
    rent = prop.get("rent", 0)
    mgmt = prop.get("management_fee", 0)
    score = prop.get("affordability_score")

    score_text = ""
    if score and score <= 0.85:
        score_text = "🟢 お得!"
    elif score and score <= 1.0:
        score_text = "🔵 適正"
    elif score:
        score_text = "🔴 割高"

    lines = [
        f"🏠 {prop.get('name', '物件名不明')}",
        f"📍 {prop.get('address', '-')}",
        f"💰 {rent:,}円/月 (管理費: {mgmt:,}円)",
        f"🏗 {prop.get('floor_plan', '-')} / {prop.get('area_sqm', '-')}㎡ / 築{prop.get('building_age', '?')}年",
        f"🅿 駐車場: {'あり' if prop.get('parking_available') else 'なし'}",
    ]

    if score_text:
        lines.append(f"📊 推定賃料: {prop.get('estimated_rent', '?'):,}円 {score_text}")

    if prop.get("source_url"):
        lines.append(f"🔗 {prop['source_url']}")

    return "\n".join(lines)


def check_and_notify(config_path: str = "./config/settings.yaml"):
    """保存済み検索条件に合致する新着物件を通知"""
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    db_path = config["database"]["path"]
    conn = init_db(db_path)

    prop_repo = PropertyRepository(conn)
    search_repo = SavedSearchRepository(conn)

    # 未通知物件を取得
    unnotified = prop_repo.get_unnotified()
    if not unnotified:
        logger.info("新着物件なし")
        conn.close()
        return

    logger.info(f"未通知物件: {len(unnotified)}件")

    # 保存済み検索条件を取得
    saved_searches = search_repo.get_all()
    if not saved_searches:
        logger.info("保存済み検索条件なし。全新着物件を通知します。")
        _send_batch(unnotified[:10], prop_repo)
        conn.close()
        return

    # 各検索条件に対してマッチング
    matched_props = set()
    for search in saved_searches:
        if not search.get("notify_enabled"):
            continue
        conds = search.get("conditions", {})
        for prop in unnotified:
            if _matches_conditions(prop, conds):
                matched_props.add(prop["id"])

    if matched_props:
        matched_list = [p for p in unnotified if p["id"] in matched_props]
        _send_batch(matched_list[:10], prop_repo)
    else:
        logger.info("条件に合致する新着物件なし")

    conn.close()


def _matches_conditions(prop: dict, conditions: dict) -> bool:
    """物件が検索条件に合致するかチェック（検索ページと同じフィルタ）"""
    rent = prop.get("rent", 0)

    # 市町村コード
    if conditions.get("municipality_codes"):
        if prop.get("municipality_code") not in conditions["municipality_codes"]:
            return False

    # 住所キーワード（サブエリア）
    if conditions.get("address_keywords"):
        address = prop.get("address", "")
        if not any(kw in address for kw in conditions["address_keywords"]):
            return False

    # 賃料
    if conditions.get("rent_min") and rent < conditions["rent_min"]:
        return False
    if conditions.get("rent_max") and rent > conditions["rent_max"]:
        return False

    # 間取り
    if conditions.get("floor_plans"):
        if prop.get("floor_plan") not in conditions["floor_plans"]:
            return False

    # 面積
    if conditions.get("area_min") and prop.get("area_sqm"):
        if prop["area_sqm"] < conditions["area_min"]:
            return False
    if conditions.get("area_max") and prop.get("area_sqm"):
        if prop["area_sqm"] > conditions["area_max"]:
            return False

    # 築年数
    if conditions.get("building_age_max") is not None:
        age = prop.get("building_age")
        if age is not None and age > conditions["building_age_max"]:
            return False

    # 構造
    if conditions.get("structures"):
        if prop.get("structure") not in conditions["structures"]:
            return False

    # 駐車場
    if conditions.get("parking_required"):
        if not prop.get("parking_available"):
            return False

    # 設備
    if conditions.get("equipment_keys"):
        for key in conditions["equipment_keys"]:
            if not prop.get(f"has_{key}"):
                return False

    # 旧フォーマット互換: municipalities（市町村名テキスト）
    if conditions.get("municipalities"):
        if prop.get("municipality") not in conditions["municipalities"]:
            return False

    return True


def _send_batch(properties: list[dict], repo: PropertyRepository):
    """物件一覧をバッチ通知"""
    if not properties:
        return

    header = f"📋 沖縄賃貸ファインダー 新着通知\n本日の新着: {len(properties)}件\n{'─' * 20}"
    messages = [header]

    for prop in properties:
        messages.append(format_property_notification(prop))

    full_message = "\n\n".join(messages)

    # Messaging API の文字数制限 (5000文字)
    if len(full_message) > LINE_MESSAGE_MAX_CHARS:
        current = header + "\n\n"
        for prop in properties:
            msg = format_property_notification(prop)
            if len(current) + len(msg) > LINE_MESSAGE_MAX_CHARS - 100:
                send_line_message(current)
                current = ""
            current += msg + "\n\n"
        if current.strip():
            send_line_message(current)
    else:
        send_line_message(full_message)

    # 通知済みフラグ
    prop_ids = [p["id"] for p in properties]
    repo.mark_notified(prop_ids)
    logger.info(f"{len(prop_ids)}件の物件を通知済みにしました")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        send_test_notification()
    else:
        check_and_notify()
