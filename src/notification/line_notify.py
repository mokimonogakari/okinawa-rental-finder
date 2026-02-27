"""LINE Notify 通知機能"""

import json
import logging
import os
from pathlib import Path

import requests
import yaml

from src.database.models import get_connection, init_db
from src.database.repository import PropertyRepository, SavedSearchRepository

logger = logging.getLogger(__name__)

LINE_NOTIFY_API = "https://notify-api.line.me/api/notify"


def send_line_notification(message: str, token: str | None = None) -> bool:
    """LINE Notifyでメッセージを送信"""
    token = token or os.getenv("LINE_NOTIFY_TOKEN", "")
    if not token:
        logger.error("LINE_NOTIFY_TOKEN が設定されていません")
        return False

    headers = {"Authorization": f"Bearer {token}"}
    data = {"message": message}

    try:
        resp = requests.post(LINE_NOTIFY_API, headers=headers, data=data, timeout=10)
        if resp.status_code == 200:
            logger.info("LINE通知送信成功")
            return True
        else:
            logger.error(f"LINE通知エラー: {resp.status_code} {resp.text}")
            return False
    except requests.RequestException as e:
        logger.error(f"LINE通知送信失敗: {e}")
        return False


def send_test_notification() -> bool:
    """テスト通知を送信"""
    return send_line_notification("\n🏠 沖縄賃貸ファインダー\nテスト通知です。正常に動作しています。")


def format_property_notification(prop: dict) -> str:
    """物件情報を通知用テキストにフォーマット"""
    rent = prop.get("rent", 0)
    mgmt = prop.get("management_fee", 0)
    score = prop.get("affordability_score")
    estimated = prop.get("estimated_rent")

    score_text = ""
    if score and score <= 0.85:
        score_text = "🟢 お得!"
    elif score and score <= 1.0:
        score_text = "🔵 適正"
    elif score:
        score_text = "🔴 割高"

    lines = [
        f"\n🏠 {prop.get('name', '物件名不明')}",
        f"📍 {prop.get('address', '-')}",
        f"💰 {rent:,}円/月 (管理費: {mgmt:,}円)",
        f"🏗 {prop.get('floor_plan', '-')} / {prop.get('area_sqm', '-')}㎡ / 築{prop.get('building_age', '?')}年",
        f"🅿 駐車場: {'あり' if prop.get('parking_available') else 'なし'}",
    ]

    if estimated:
        lines.append(f"📊 推定賃料: {estimated:,}円 {score_text}")

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
        # 全件通知 (最大10件)
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
    """物件が検索条件に合致するかチェック"""
    rent = prop.get("rent", 0)
    if conditions.get("rent_min") and rent < conditions["rent_min"]:
        return False
    if conditions.get("rent_max") and rent > conditions["rent_max"]:
        return False

    if conditions.get("area_min") and prop.get("area_sqm"):
        if prop["area_sqm"] < conditions["area_min"]:
            return False

    if conditions.get("municipalities"):
        if prop.get("municipality") not in conditions["municipalities"]:
            return False

    if conditions.get("floor_plans"):
        if prop.get("floor_plan") not in conditions["floor_plans"]:
            return False

    if conditions.get("notify_bargains_only"):
        score = prop.get("affordability_score")
        if not score or score > 0.85:
            return False

    return True


def _send_batch(properties: list[dict], repo: PropertyRepository):
    """物件一覧をバッチ通知"""
    if not properties:
        return

    header = f"\n📋 沖縄賃貸ファインダー 新着通知\n本日の新着: {len(properties)}件\n{'─' * 20}"
    messages = [header]

    for prop in properties:
        messages.append(format_property_notification(prop))

    full_message = "\n".join(messages)

    # LINE Notifyの文字数制限 (1000文字)
    if len(full_message) > 1000:
        # 複数回に分けて送信
        current = header + "\n"
        for prop in properties:
            msg = format_property_notification(prop)
            if len(current) + len(msg) > 950:
                send_line_notification(current)
                current = ""
            current += msg + "\n"
        if current.strip():
            send_line_notification(current)
    else:
        send_line_notification(full_message)

    # 通知済みフラグ
    prop_ids = [p["id"] for p in properties]
    repo.mark_notified(prop_ids)
    logger.info(f"{len(prop_ids)}件の物件を通知済みにしました")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    check_and_notify()
