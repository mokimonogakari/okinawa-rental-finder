"""価格分析ダッシュボード"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yaml

from src.database.models import get_connection, init_db
from src.database.repository import LandPriceRepository, PropertyRepository


def get_db():
    settings_path = Path(__file__).parent.parent.parent.parent / "config" / "settings.yaml"
    with open(settings_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    db_path = Path(__file__).parent.parent.parent.parent / config["database"]["path"]
    return init_db(db_path)


def render_analysis_page():
    st.header("📊 価格分析ダッシュボード")

    conn = get_db()
    repo = PropertyRepository(conn)
    land_repo = LandPriceRepository(conn)

    # 全物件データ取得
    all_props = repo.search(limit=5000, sort_by="rent", sort_order="ASC")
    if not all_props:
        st.info("物件データがありません。スクレイピングを実行してください。")
        conn.close()
        return

    df = pd.DataFrame(all_props)

    # --- サマリメトリクス ---
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("総物件数", f"{len(df):,}")
    with col2:
        st.metric("平均賃料", f"{df['rent'].mean():,.0f}円")
    with col3:
        st.metric("中央値賃料", f"{df['rent'].median():,.0f}円")
    with col4:
        bargains = df[df["affordability_score"].notna() & (df["affordability_score"] <= 0.85)]
        st.metric("お得物件数", f"{len(bargains)}")

    tab1, tab2, tab3, tab4 = st.tabs([
        "市町村別相場", "賃料分布", "割安度分析", "モデル性能"
    ])

    with tab1:
        _render_municipality_chart(df)

    with tab2:
        _render_rent_distribution(df)

    with tab3:
        _render_affordability_analysis(df)

    with tab4:
        _render_model_performance(conn)

    conn.close()


def _render_municipality_chart(df: pd.DataFrame):
    """市町村別の賃料相場チャート"""
    st.subheader("市町村別 平均賃料")

    if "municipality" not in df.columns or df["municipality"].isna().all():
        st.info("市町村データがありません")
        return

    muni_stats = df.groupby("municipality").agg(
        avg_rent=("rent", "mean"),
        median_rent=("rent", "median"),
        count=("rent", "count"),
        avg_area=("area_sqm", "mean"),
    ).reset_index()
    muni_stats = muni_stats[muni_stats["count"] >= 3].sort_values("avg_rent", ascending=True)

    if muni_stats.empty:
        st.info("十分なデータがある市町村がありません")
        return

    fig = px.bar(
        muni_stats,
        x="avg_rent",
        y="municipality",
        orientation="h",
        title="市町村別 平均賃料 (3件以上のエリアのみ)",
        labels={"avg_rent": "平均賃料 (円)", "municipality": "市町村", "count": "物件数"},
        hover_data=["median_rent", "count", "avg_area"],
        color="avg_rent",
        color_continuous_scale="Blues",
    )
    fig.update_layout(height=max(400, len(muni_stats) * 30))
    st.plotly_chart(fig, use_container_width=True)

    # 面積あたり単価
    st.subheader("市町村別 ㎡単価")
    muni_stats["rent_per_sqm"] = muni_stats["avg_rent"] / muni_stats["avg_area"].clip(lower=1)
    fig2 = px.bar(
        muni_stats.sort_values("rent_per_sqm", ascending=True),
        x="rent_per_sqm",
        y="municipality",
        orientation="h",
        title="市町村別 ㎡あたり賃料",
        labels={"rent_per_sqm": "㎡単価 (円)", "municipality": "市町村"},
        color="rent_per_sqm",
        color_continuous_scale="Reds",
    )
    fig2.update_layout(height=max(400, len(muni_stats) * 30))
    st.plotly_chart(fig2, use_container_width=True)


def _render_rent_distribution(df: pd.DataFrame):
    """賃料分布"""
    st.subheader("賃料分布")

    fig = px.histogram(
        df,
        x="rent",
        nbins=50,
        title="賃料ヒストグラム",
        labels={"rent": "賃料 (円)", "count": "物件数"},
        color_discrete_sequence=["#1f77b4"],
    )
    fig.add_vline(x=df["rent"].median(), line_dash="dash", line_color="red",
                  annotation_text=f"中央値: {df['rent'].median():,.0f}円")
    st.plotly_chart(fig, use_container_width=True)

    # 間取り別
    if "floor_plan" in df.columns:
        st.subheader("間取り別 賃料")
        fig2 = px.box(
            df[df["floor_plan"].notna()],
            x="floor_plan",
            y="rent",
            title="間取り別 賃料分布",
            labels={"floor_plan": "間取り", "rent": "賃料 (円)"},
            color="floor_plan",
        )
        st.plotly_chart(fig2, use_container_width=True)

    # 築年数 vs 賃料
    if "building_age" in df.columns:
        st.subheader("築年数 × 賃料")
        valid = df[df["building_age"].notna() & df["area_sqm"].notna()]
        if not valid.empty:
            fig3 = px.scatter(
                valid,
                x="building_age",
                y="rent",
                size="area_sqm",
                color="structure",
                title="築年数と賃料の関係",
                labels={
                    "building_age": "築年数", "rent": "賃料 (円)",
                    "area_sqm": "面積 (㎡)", "structure": "構造"
                },
                hover_data=["name", "municipality", "floor_plan"],
            )
            st.plotly_chart(fig3, use_container_width=True)


def _render_affordability_analysis(df: pd.DataFrame):
    """割安度分析"""
    st.subheader("割安度分析")

    scored = df[df["affordability_score"].notna() & (df["affordability_score"] > 0)]
    if scored.empty:
        st.info("価格推定モデルを実行して割安度スコアを算出してください。")
        return

    # 割安度ヒストグラム
    fig = px.histogram(
        scored,
        x="affordability_score",
        nbins=40,
        title="割安度スコア分布 (1.0未満 = お得, 1.0以上 = 割高)",
        labels={"affordability_score": "割安度スコア", "count": "物件数"},
        color_discrete_sequence=["#2ecc71"],
    )
    fig.add_vline(x=1.0, line_dash="dash", line_color="red", annotation_text="適正価格")
    fig.add_vline(x=0.85, line_dash="dot", line_color="green", annotation_text="お得ライン")
    st.plotly_chart(fig, use_container_width=True)

    # お得物件ランキング
    st.subheader("🏆 お得物件 TOP10")
    bargains = scored.nsmallest(10, "affordability_score")
    for _, prop in bargains.iterrows():
        score = prop["affordability_score"]
        est = prop.get("estimated_rent", 0)
        actual = prop["rent"]
        savings = est - actual if est else 0
        st.markdown(
            f"**{prop.get('name', '不明')}** — "
            f"💰 {actual:,.0f}円 (推定: {est:,.0f}円, **{savings:+,.0f}円お得**) "
            f"| {prop.get('floor_plan', '')} | {prop.get('area_sqm', '')}㎡ "
            f"| 📍 {prop.get('municipality', '')}"
        )


def _render_model_performance(conn):
    """モデル性能表示"""
    st.subheader("モデル性能")

    rows = conn.execute(
        "SELECT * FROM model_metadata ORDER BY trained_at DESC LIMIT 5"
    ).fetchall()

    if not rows:
        st.info("まだモデルが学習されていません。")
        return

    for row in rows:
        row = dict(row)
        active = "✅ 使用中" if row["is_active"] else ""
        st.markdown(f"**{row['model_type']}** v{row['version']} {active}")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("R²スコア", f"{row['r2_score']:.3f}" if row['r2_score'] else "N/A")
        with col2:
            st.metric("MAE", f"{row['mae']:,.0f}円" if row['mae'] else "N/A")
        with col3:
            st.metric("RMSE", f"{row['rmse']:,.0f}円" if row['rmse'] else "N/A")
        with col4:
            st.metric("学習データ数", f"{row['training_samples']}件" if row['training_samples'] else "N/A")
        st.divider()
