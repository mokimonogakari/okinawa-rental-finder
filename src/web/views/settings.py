"""通知設定ページ"""

import json
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


def render_settings_page():
    st.header("🔔 通知設定")

    conn = get_db()
    repo = SavedSearchRepository(conn)

    # --- 保存済み検索条件一覧 ---
    st.subheader("保存済み検索条件")
    saved = repo.get_all()

    if not saved:
        st.info("保存済みの検索条件がありません。物件検索ページで条件を保存してください。")
    else:
        for s in saved:
            with st.expander(f"📋 {s['name']} (作成: {s['created_at']})"):
                conds = s.get("conditions", {})
                st.json(conds)

                col1, col2 = st.columns(2)
                with col1:
                    notify = st.toggle(
                        "通知ON",
                        value=bool(s.get("notify_enabled")),
                        key=f"notify_{s['id']}",
                    )
                with col2:
                    if st.button("削除", key=f"del_{s['id']}", type="secondary"):
                        repo.delete(s["id"])
                        st.rerun()

    st.divider()

    # --- 新規検索条件保存 ---
    st.subheader("新規検索条件を保存")

    with st.form("save_search"):
        name = st.text_input("条件名", placeholder="例: 那覇市2LDK 10万以下")

        col1, col2 = st.columns(2)
        with col1:
            rent_min = st.number_input("賃料下限 (円)", value=30000, step=5000)
            rent_max = st.number_input("賃料上限 (円)", value=80000, step=5000)
        with col2:
            area_min = st.number_input("面積下限 (㎡)", value=25.0, step=5.0)
            municipalities = st.text_input(
                "市町村 (カンマ区切り)", placeholder="那覇市, 浦添市"
            )

        floor_plans = st.multiselect(
            "間取り",
            ["1R", "1K", "1DK", "1LDK", "2K", "2DK", "2LDK", "3K", "3DK", "3LDK"],
        )

        notify_bargains = st.checkbox("お得物件のみ通知 (割安度0.85以下)", value=False)

        if st.form_submit_button("保存"):
            if not name:
                st.error("条件名を入力してください")
            else:
                conditions = {
                    "rent_min": rent_min,
                    "rent_max": rent_max,
                    "area_min": area_min,
                    "municipalities": [
                        m.strip() for m in municipalities.split(",") if m.strip()
                    ],
                    "floor_plans": floor_plans,
                    "notify_bargains_only": notify_bargains,
                }
                repo.save(name, conditions)
                st.success(f"「{name}」を保存しました")
                st.rerun()

    st.divider()

    # --- LINE Messaging API 設定 ---
    st.subheader("LINE Messaging API 設定")
    st.markdown("""
    設定手順は [docs/line-messaging-api-setup.md](https://github.com/mokimonogakari/okinawa-rental-finder/blob/main/docs/line-messaging-api-setup.md) を参照してください。

    必要な環境変数:
    - `LINE_CHANNEL_ACCESS_TOKEN`: チャネルアクセストークン（長期）
    - `LINE_USER_IDS`: 送信先ユーザーID（カンマ区切り）
    """)

    import os
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
