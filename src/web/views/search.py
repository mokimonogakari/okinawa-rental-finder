"""物件検索ページ"""

from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from src.database.models import get_connection, init_db
from src.database.repository import PropertyRepository, SavedSearchRepository


def load_conditions():
    """検索条件YAMLを読み込み"""
    config_path = Path(__file__).parent.parent.parent.parent / "config" / "search_conditions.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_db_connection():
    settings_path = Path(__file__).parent.parent.parent.parent / "config" / "settings.yaml"
    with open(settings_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    db_path = Path(__file__).parent.parent.parent.parent / config["database"]["path"]
    return init_db(db_path)


def render_search_page():
    st.header("🔍 物件検索")

    conditions = load_conditions()

    # --- サイドバーに検索フィルタ ---
    with st.sidebar:
        st.subheader("検索条件")

        # エリア選択
        st.markdown("**エリア**")
        selected_areas = []
        selected_address_keywords = []
        sub_areas_config = conditions.get("sub_areas", {})

        for region, cities in conditions["areas"].items():
            with st.expander(f"📍 {region}", expanded=(region in ["南部", "中部"])):
                city_names = [c["name"] for c in cities]
                selected = st.multiselect(
                    f"{region}の市町村",
                    city_names,
                    key=f"area_{region}",
                    label_visibility="collapsed",
                )
                for name in selected:
                    for c in cities:
                        if c["name"] == name:
                            selected_areas.append(c["code"])

                # サブエリア選択（対象市町村が選択されている場合のみ表示）
                for c in cities:
                    if c["name"] in selected and c["code"] in sub_areas_config:
                        for sa in sub_areas_config[c["code"]]:
                            if st.checkbox(
                                f"  └ {sa['name']}",
                                key=f"sub_{c['code']}_{sa['name']}",
                                help=sa.get("note", ""),
                            ):
                                selected_address_keywords.extend(sa["keywords"])

        st.divider()

        # 賃料
        st.markdown("**賃料 (円/月)**")
        rent_range = st.slider(
            "賃料範囲",
            min_value=conditions["rent"]["min"],
            max_value=conditions["rent"]["max"],
            value=(30000, 100000),
            step=conditions["rent"]["step"],
            label_visibility="collapsed",
        )

        st.divider()

        # 間取り
        st.markdown("**間取り**")
        selected_plans = st.multiselect(
            "間取り選択",
            conditions["floor_plan"]["options"],
            label_visibility="collapsed",
        )

        # 面積
        st.markdown("**専有面積 (㎡)**")
        area_range = st.slider(
            "面積範囲",
            min_value=float(conditions["area_size"]["min"]),
            max_value=float(conditions["area_size"]["max"]),
            value=(20.0, 100.0),
            step=5.0,
            label_visibility="collapsed",
        )

        st.divider()

        # 築年数
        age_options = conditions["building_age"]["options"]
        age_labels = [a["label"] for a in age_options]
        selected_age = st.selectbox("築年数", age_labels, index=len(age_labels) - 1)
        max_age = None
        for a in age_options:
            if a["label"] == selected_age and a["value"] is not None:
                max_age = a["value"]

        # 構造
        st.markdown("**構造**")
        structure_options = conditions["structure"]["options"]
        selected_structures = st.multiselect(
            "構造選択",
            [s["label"] for s in structure_options],
            label_visibility="collapsed",
        )
        structure_values = [
            s["value"] for s in structure_options
            if s["label"] in selected_structures
        ]

        # 沖縄の構造アドバイス表示
        for s in structure_options:
            if s["label"] in selected_structures:
                st.caption(f"💡 {s['okinawa_note']}")

        st.divider()

        # 駐車場
        parking_opts = conditions["parking"]["options"]
        parking_sel = st.radio(
            "🚗 駐車場",
            [p["label"] for p in parking_opts],
            index=0,
            help=conditions["parking"]["note"],
        )
        parking_required = parking_sel == "必須"

        # 設備
        st.markdown("**設備条件**")
        selected_equip = []
        with st.expander("沖縄で重要な設備", expanded=True):
            for eq in conditions["equipment"]["essential"]:
                if st.checkbox(f"{eq['priority']} {eq['label']}", key=f"eq_{eq['key']}"):
                    selected_equip.append(eq["key"])
                if st.checkbox.__name__:  # always true, just to add caption
                    st.caption(eq.get("note", ""))

        with st.expander("その他の設備"):
            for eq in conditions["equipment"]["comfort"]:
                if st.checkbox(eq["label"], key=f"eq_{eq['key']}"):
                    selected_equip.append(eq["key"])

        with st.expander("ペット"):
            for eq in conditions["equipment"]["pet"]:
                if st.checkbox(eq["label"], key=f"eq_{eq['key']}"):
                    selected_equip.append(eq["key"])

        st.divider()

        # ソート
        sort_options = {
            "賃料が安い順": ("rent", "ASC"),
            "賃料が高い順": ("rent", "DESC"),
            "面積が広い順": ("area_sqm", "DESC"),
            "築年数が新しい順": ("building_age", "ASC"),
            "お得度順": ("affordability_score", "ASC"),
            "新着順": ("scraped_at", "DESC"),
        }
        sort_label = st.selectbox("並び替え", list(sort_options.keys()))
        sort_by, sort_order = sort_options[sort_label]

    # --- 現在の検索条件を辞書として構築 ---
    current_conditions = {
        "municipality_codes": selected_areas,
        "address_keywords": selected_address_keywords,
        "rent_min": rent_range[0],
        "rent_max": rent_range[1],
        "floor_plans": selected_plans,
        "area_min": area_range[0],
        "area_max": area_range[1],
        "building_age_max": max_age,
        "structures": structure_values,
        "parking_required": parking_required,
        "equipment_keys": selected_equip,
    }

    # --- メインコンテンツ: 検索結果 ---
    conn = get_db_connection()
    repo = PropertyRepository(conn)

    results = repo.search(
        **current_conditions,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=100,
    )

    # 件数表示
    total = repo.count(
        municipality_codes=selected_areas or None,
        rent_min=rent_range[0],
        rent_max=rent_range[1],
    )

    col1, col2, col3, col4 = st.columns([1, 1, 1, 1.5])
    with col1:
        st.metric("検索結果", f"{len(results)}件")
    with col2:
        st.metric("全物件数", f"{total}件")
    with col3:
        stats = repo.get_statistics()
        avg_rent = stats.get("avg_rent")
        st.metric("平均賃料", f"{avg_rent:,.0f}円" if avg_rent else "データなし")
    with col4:
        st.markdown("&nbsp;")  # spacer
        _render_save_button(conn, current_conditions)

    if not results:
        st.info("条件に合う物件が見つかりませんでした。条件を変更してお試しください。")
        st.caption("💡 ヒント: スクレイピングを実行して物件データを蓄積してください。")
        conn.close()
        return

    # 物件カード表示
    for prop in results:
        _render_property_card(prop)

    conn.close()


def _render_save_button(conn, conditions: dict):
    """通知条件として保存するポップオーバー"""
    with st.popover("🔔 この条件で通知"):
        name = st.text_input("条件名", placeholder="例: 新都心2LDK 10万以下", key="save_cond_name")
        if st.button("保存", key="save_cond_btn", type="primary"):
            if not name:
                st.error("条件名を入力してください")
            else:
                # None値や空リストを除去して保存
                save_data = {k: v for k, v in conditions.items() if v}
                search_repo = SavedSearchRepository(conn)
                search_repo.save(name, save_data)
                st.success(f"「{name}」を保存しました")
                st.rerun()


def _render_property_card(prop: dict):
    """物件カードを表示"""
    # 割安度に応じたスタイル
    score = prop.get("affordability_score")
    if score and score <= 0.85:
        badge = "🟢 お得"
        card_class = "bargain"
    elif score and score >= 1.15:
        badge = "🔴 割高"
        card_class = "expensive"
    else:
        badge = ""
        card_class = ""

    with st.container():
        col1, col2 = st.columns([3, 1])

        with col1:
            name = prop.get("name", "物件名不明")
            rent = prop.get("rent", 0)
            mgmt = prop.get("management_fee", 0)
            st.markdown(f"### {name} {badge}")
            st.markdown(
                f"**💰 {rent:,}円/月** "
                f"(管理費: {mgmt:,}円) "
                f"| **{prop.get('floor_plan', '-')}** "
                f"| **{prop.get('area_sqm', '-')}㎡** "
                f"| 築{prop.get('building_age', '?')}年"
            )
            st.caption(
                f"📍 {prop.get('address', '-')} "
                f"| 🏗 {prop.get('structure', '-')} "
                f"| 🚗 {'あり' if prop.get('parking_available') else 'なし'}"
            )
            if prop.get("nearest_station"):
                icon = "🚝" if prop.get("transport_type") == "monorail" else "🚌"
                st.caption(
                    f"{icon} {prop['nearest_station']} 徒歩{prop.get('station_walk_minutes', '?')}分"
                )

        with col2:
            if prop.get("estimated_rent"):
                est = prop["estimated_rent"]
                diff = rent - est
                st.metric(
                    "推定賃料",
                    f"{est:,}円",
                    delta=f"{diff:+,}円",
                    delta_color="inverse",
                )
                if score:
                    st.caption(f"割安度: {score:.2f}")
            if prop.get("source_url"):
                st.link_button("詳細を見る", prop["source_url"])

        st.divider()
