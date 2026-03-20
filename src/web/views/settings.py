"""通知設定ページ"""

import os
from pathlib import Path

import streamlit as st
import yaml

from src.database.models import init_db
from src.database.repository import SavedSearchRepository


def get_db():
    settings_path = Path(__file__).parent.parent.parent.parent / "config" / "settings.yaml"
    with open(settings_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    db_path = Path(__file__).parent.parent.parent.parent / config["database"]["path"]
    return init_db(db_path)


def _summarize_conditions(conds: dict) -> str:
    """保存済み条件を日本語サマリにする"""
    parts = []

    if conds.get("municipality_codes"):
        codes = conds["municipality_codes"]
        # コード→市町村名の変換テーブル
        config_path = Path(__file__).parent.parent.parent.parent / "config" / "search_conditions.yaml"
        try:
            with open(config_path, encoding="utf-8") as f:
                sc = yaml.safe_load(f)
            code_to_name = {}
            for cities in sc.get("areas", {}).values():
                for c in cities:
                    code_to_name[c["code"]] = c["name"]
            names = [code_to_name.get(c, c) for c in codes]
            parts.append(f"📍 {', '.join(names)}")
        except Exception:
            parts.append(f"📍 {len(codes)}市町村")

    if conds.get("address_keywords"):
        parts.append(f"🏘 地域: {', '.join(conds['address_keywords'])}")

    rent_min = conds.get("rent_min")
    rent_max = conds.get("rent_max")
    if rent_min or rent_max:
        parts.append(f"💰 {rent_min:,}〜{rent_max:,}円")

    if conds.get("floor_plans"):
        parts.append(f"🏠 {', '.join(conds['floor_plans'])}")

    area_min = conds.get("area_min")
    area_max = conds.get("area_max")
    if area_min or area_max:
        parts.append(f"📐 {area_min}〜{area_max}㎡")

    if conds.get("building_age_max") is not None:
        parts.append(f"🏗 築{conds['building_age_max']}年以内")

    if conds.get("structures"):
        parts.append(f"🧱 {', '.join(conds['structures'])}")

    if conds.get("parking_required"):
        parts.append("🚗 駐車場あり")

    if conds.get("equipment_keys"):
        parts.append(f"⚙️ 設備{len(conds['equipment_keys'])}項目")

    return "\n".join(parts) if parts else "条件なし（全物件対象）"


def render_settings_page():
    st.header("🔔 通知設定")

    st.info("💡 物件検索ページで条件を設定し「🔔 この条件で通知」ボタンから保存できます。")

    conn = get_db()
    repo = SavedSearchRepository(conn)

    # --- 保存済み検索条件一覧 ---
    st.subheader("保存済み通知条件")
    saved = repo.get_all()

    if not saved:
        st.warning("通知条件が未設定です。物件検索ページで条件を保存してください。")
    else:
        for s in saved:
            conds = s.get("conditions", {})
            summary = _summarize_conditions(conds)
            with st.expander(f"📋 {s['name']}", expanded=True):
                st.text(summary)

                col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
                with col1:
                    if st.button("🔍 検索", key=f"search_{s['id']}", type="primary", use_container_width=True):
                        st.session_state["applied_saved"] = s["conditions"]
                        st.session_state["nav_page"] = "🔍 物件検索"
                        st.rerun()
                with col2:
                    new_val = st.toggle(
                        "通知ON",
                        value=bool(s.get("notify_enabled")),
                        key=f"notify_{s['id']}",
                    )
                    if new_val != bool(s.get("notify_enabled")):
                        repo.update_notify_enabled(s["id"], new_val)
                        st.rerun()
                with col3:
                    if st.button("削除", key=f"del_{s['id']}", type="secondary"):
                        repo.delete(s["id"])
                        st.rerun()
                with col4:
                    st.caption(f"作成: {s['created_at'][:10]}")

    st.divider()

    # --- LINE Messaging API 設定 ---
    st.subheader("LINE Messaging API 設定")
    st.markdown("""
    設定手順は [docs/line-messaging-api-setup.md](https://github.com/mokimonogakari/okinawa-rental-finder/blob/main/docs/line-messaging-api-setup.md) を参照してください。
    """)

    token_set = bool(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
    user_ids_set = bool(os.getenv("LINE_USER_IDS"))
    st.markdown(f"- チャネルアクセストークン: {'✅ 設定済み' if token_set else '❌ 未設定'}")
    st.markdown(f"- ユーザーID: {'✅ 設定済み' if user_ids_set else '❌ 未設定'}")

    # 通知テスト
    if st.button("テスト通知を送信"):
        try:
            from src.notification.line_notify import send_test_notification
            result = send_test_notification()
            if result:
                st.success("テスト通知を送信しました")
            else:
                st.error("通知の送信に失敗しました。環境変数を確認してください。")
        except Exception as e:
            st.error(f"エラー: {e}")

    conn.close()
