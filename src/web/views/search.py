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


def _load_saved_conditions(conn):
    """保存済み通知条件をロードし、選択された条件をsession_stateに適用"""
    repo = SavedSearchRepository(conn)
    saved = repo.get_all()
    if not saved:
        return
    # 保存済み条件をボタンとして表示
    st.markdown("**保存済み条件で検索:**")
    cols = st.columns(min(len(saved), 4))
    for i, s in enumerate(saved[:4]):
        with cols[i % 4]:
            if st.button(f"📋 {s['name']}", key=f"quick_{s['id']}", use_container_width=True):
                st.session_state["applied_saved"] = s["conditions"]
                st.rerun()

    # リセットボタン
    if "applied_saved" in st.session_state:
        if st.button("✕ 条件をリセット", key="reset_saved", type="secondary"):
            del st.session_state["applied_saved"]
            st.rerun()


def render_search_page():
    st.header("🔍 物件検索")

    conditions = load_conditions()

    # --- 保存済み条件のクイック検索 ---
    conn_for_saved = get_db_connection()
    _load_saved_conditions(conn_for_saved)
    conn_for_saved.close()

    # 保存済み条件が適用されている場合、デフォルト値を上書き
    applied = st.session_state.get("applied_saved", {})

    # --- サイドバーに検索フィルタ ---
    with st.sidebar:
        st.subheader("検索条件")

        # エリア選択
        st.markdown("**エリア**")
        selected_areas = []
        selected_address_keywords = []
        sub_areas_config = conditions.get("sub_areas", {})

        # 保存済み条件から市町村コード→名前のデフォルト値を構築
        applied_codes = set(applied.get("municipality_codes", []))
        code_to_name = {}
        for cities_list in conditions["areas"].values():
            for c in cities_list:
                code_to_name[c["code"]] = c["name"]

        for region, cities in conditions["areas"].items():
            with st.expander(f"📍 {region}", expanded=(region in ["南部", "中部"])):
                city_names = [c["name"] for c in cities]
                # 保存済み条件のデフォルト値
                default_cities = [c["name"] for c in cities if c["code"] in applied_codes]
                selected = st.multiselect(
                    f"{region}の市町村",
                    city_names,
                    default=default_cities,
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
        default_rent = (
            applied.get("rent_min", 30000),
            applied.get("rent_max", 100000),
        )
        rent_range = st.slider(
            "賃料範囲",
            min_value=conditions["rent"]["min"],
            max_value=conditions["rent"]["max"],
            value=default_rent,
            step=conditions["rent"]["step"],
            label_visibility="collapsed",
        )

        st.divider()

        # 間取り
        st.markdown("**間取り**")
        default_plans = [
            p for p in applied.get("floor_plans", [])
            if p in conditions["floor_plan"]["options"]
        ]
        selected_plans = st.multiselect(
            "間取り選択",
            conditions["floor_plan"]["options"],
            default=default_plans,
            label_visibility="collapsed",
        )

        # 面積
        st.markdown("**専有面積 (㎡)**")
        default_area = (
            float(applied.get("area_min", 20.0)),
            float(applied.get("area_max", 100.0)),
        )
        area_range = st.slider(
            "面積範囲",
            min_value=float(conditions["area_size"]["min"]),
            max_value=float(conditions["area_size"]["max"]),
            value=default_area,
            step=5.0,
            label_visibility="collapsed",
        )

        st.divider()

        # 築年数
        age_options = conditions["building_age"]["options"]
        age_labels = [a["label"] for a in age_options]
        # 保存済み条件の築年数をデフォルトに
        _age_default_idx = len(age_labels) - 1
        if applied.get("building_age_max") is not None:
            for _ai, _ao in enumerate(age_options):
                if _ao["value"] == applied["building_age_max"]:
                    _age_default_idx = _ai
                    break
        selected_age = st.selectbox("築年数", age_labels, index=_age_default_idx)
        max_age = None
        for a in age_options:
            if a["label"] == selected_age and a["value"] is not None:
                max_age = a["value"]

        # 構造
        st.markdown("**構造**")
        structure_options = conditions["structure"]["options"]
        _default_structures = []
        if applied.get("structures"):
            _struct_val_to_label = {s["value"]: s["label"] for s in structure_options}
            _default_structures = [_struct_val_to_label[v] for v in applied["structures"] if v in _struct_val_to_label]
        selected_structures = st.multiselect(
            "構造選択",
            [s["label"] for s in structure_options],
            default=_default_structures,
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
        _parking_idx = 1 if applied.get("parking_required") else 0
        parking_sel = st.radio(
            "🚗 駐車場",
            [p["label"] for p in parking_opts],
            index=_parking_idx,
            help=conditions["parking"]["note"],
        )
        parking_required = parking_sel == "必須"

        # 設備
        st.markdown("**設備条件**")
        selected_equip = []
        _applied_equip = set(applied.get("equipment_keys", []))
        with st.expander("沖縄で重要な設備", expanded=True):
            for eq in conditions["equipment"]["essential"]:
                if st.checkbox(f"{eq['priority']} {eq['label']}", key=f"eq_{eq['key']}", value=eq["key"] in _applied_equip):
                    selected_equip.append(eq["key"])
                if st.checkbox.__name__:  # always true, just to add caption
                    st.caption(eq.get("note", ""))

        with st.expander("その他の設備"):
            for eq in conditions["equipment"]["comfort"]:
                if st.checkbox(eq["label"], key=f"eq_{eq['key']}", value=eq["key"] in _applied_equip):
                    selected_equip.append(eq["key"])

        with st.expander("ペット"):
            for eq in conditions["equipment"]["pet"]:
                if st.checkbox(eq["label"], key=f"eq_{eq['key']}", value=eq["key"] in _applied_equip):
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


SOURCE_LABELS = {
    "uchina": ("うちなーらいふ", "#f97316"),
    "goohome": ("グーホーム", "#3b82f6"),
    "suumo": ("SUUMO", "#22c55e"),
    "homes": ("HOME'S", "#a855f7"),
}


def _render_property_card(prop: dict):
    """物件カードを表示"""
    rent = prop.get("rent", 0)
    est = prop.get("estimated_rent")
    score = prop.get("affordability_score")
    mgmt = prop.get("management_fee", 0)

    # 掲載媒体バッジ
    source = prop.get("source", "")
    src_label, src_color = SOURCE_LABELS.get(source, (source, "#6b7280"))
    source_badge = (
        f'<span style="background:{src_color};color:#fff;padding:1px 6px;'
        f'border-radius:3px;font-size:0.7em;margin-right:4px;">{src_label}</span>'
    )

    # 割安度バッジ
    if score and score <= 0.85:
        badge = '<span style="background:#10b981;color:#fff;padding:2px 8px;border-radius:4px;font-size:0.8em;">お得</span>'
    elif score and score >= 1.15:
        badge = '<span style="background:#ef4444;color:#fff;padding:2px 8px;border-radius:4px;font-size:0.8em;">割高</span>'
    else:
        badge = ""

    # 築年数表示（None対応）
    age = prop.get("building_age")
    age_text = f"築{age}年" if age is not None else ""

    with st.container():
        # 上段: 物件名 + 賃料（大きく目立つ）
        left, right = st.columns([3, 2])

        with left:
            name = prop.get("name", "物件名不明")
            st.markdown(f"{source_badge}**{name}** {badge}", unsafe_allow_html=True)
            # 物件スペック
            specs_parts = [prop.get("floor_plan", "-")]
            area = prop.get("area_sqm")
            if area:
                specs_parts.append(f"{area}㎡")
            if age_text:
                specs_parts.append(age_text)
            specs_parts.append(prop.get("structure") or "-")
            st.caption(" / ".join(specs_parts))
            st.caption(
                f"📍 {prop.get('address', '-')} "
                f"| 🚗 {'あり' if prop.get('parking_available') else 'なし'}"
            )
            if prop.get("nearest_station"):
                icon = "🚝" if prop.get("transport_type") == "monorail" else "🚌"
                st.caption(
                    f"{icon} {prop['nearest_station']} 徒歩{prop.get('station_walk_minutes', '?')}分"
                )

        with right:
            # 実際の賃料を大きく表示
            rent_man = rent / 10000
            if rent_man == int(rent_man):
                rent_display = f"{int(rent_man)}"
            else:
                rent_display = f"{rent_man:.2f}"
            st.markdown(
                f'<div style="text-align:right;">'
                f'<span style="font-size:2em;font-weight:bold;color:#1e40af;">{rent_display}</span>'
                f'<span style="font-size:0.9em;color:#1e40af;">万円/月</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if mgmt:
                st.markdown(
                    f'<div style="text-align:right;margin-top:-10px;">'
                    f'<span style="font-size:0.75em;color:#6b7280;">管理費 {mgmt:,}円</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            # 相場比較（小さく補足表示）
            if est:
                savings = est - rent
                if savings > 0:
                    st.markdown(
                        f'<div style="text-align:right;">'
                        f'<span style="font-size:0.8em;color:#10b981;">相場より {savings:,}円 お得</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                elif savings < 0:
                    st.markdown(
                        f'<div style="text-align:right;">'
                        f'<span style="font-size:0.8em;color:#ef4444;">相場より {-savings:,}円 割高</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            if prop.get("source_url"):
                st.link_button(
                    "📄 詳細を見る",
                    prop["source_url"],
                    use_container_width=True,
                )

        st.divider()
