"""管理ページ - スクレイピング実行・モデル学習"""

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

import streamlit as st
import yaml

from src.database.models import init_db


def get_db():
    settings_path = Path(__file__).parent.parent.parent.parent / "config" / "settings.yaml"
    with open(settings_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    db_path = Path(__file__).parent.parent.parent.parent / config["database"]["path"]
    return init_db(db_path)


def render_admin_page():
    st.header("⚙️ 管理パネル")

    conn = get_db()

    # --- DB統計 ---
    st.subheader("データベース統計")

    col1, col2, col3 = st.columns(3)
    with col1:
        count = conn.execute("SELECT COUNT(*) FROM properties WHERE is_active = 1").fetchone()[0]
        st.metric("アクティブ物件数", f"{count:,}")
    with col2:
        count = conn.execute("SELECT COUNT(*) FROM land_prices").fetchone()[0]
        st.metric("地価データ数", f"{count:,}")
    with col3:
        count = conn.execute("SELECT COUNT(*) FROM transaction_prices").fetchone()[0]
        st.metric("取引価格データ数", f"{count:,}")

    # ソース別件数
    st.subheader("ソース別物件数")
    sources = conn.execute(
        "SELECT source, COUNT(*) as cnt FROM properties WHERE is_active = 1 GROUP BY source"
    ).fetchall()
    if sources:
        for s in sources:
            st.write(f"**{s[0]}**: {s[1]:,}件")
    else:
        st.info("物件データなし")

    st.divider()

    # --- スクレイパー実行 ---
    st.subheader("スクレイパー実行")

    col1, col2 = st.columns(2)
    with col1:
        spider_name = st.selectbox(
            "対象サイト",
            ["goohome", "uchina", "suumo", "homes", "全サイト"],
        )
    with col2:
        st.markdown("&nbsp;")  # spacer
        if st.button("スクレイピング実行", type="primary"):
            with st.spinner("スクレイピング中..."):
                project_dir = str(Path(__file__).parent.parent.parent.parent)
                if spider_name == "全サイト":
                    for name in ["goohome", "uchina", "suumo", "homes"]:
                        _run_spider(project_dir, name)
                else:
                    _run_spider(project_dir, spider_name)
            st.success("スクレイピング完了")
            st.rerun()

    st.divider()

    # --- モデル学習 ---
    st.subheader("価格推定モデル")

    if st.button("モデル学習を実行"):
        with st.spinner("モデル学習中..."):
            try:
                from src.pricing.training import run_training_pipeline
                project_dir = str(Path(__file__).parent.parent.parent.parent)
                config_path = f"{project_dir}/config/settings.yaml"
                results = run_training_pipeline(config_path)
                if results and "error" not in results:
                    st.success(
                        f"学習完了 - R²: {results['random_forest']['r2']:.3f}, "
                        f"MAE: {results['random_forest']['mae']:,.0f}円"
                    )
                else:
                    st.warning(f"学習に問題がありました: {results}")
            except Exception:
                logger.exception("処理エラー")
                st.error("処理中にエラーが発生しました。ログを確認してください。")

    # --- 地価データ取得 ---
    st.subheader("地価データ取得")

    if st.button("地価データを更新"):
        with st.spinner("地価データ取得中..."):
            try:
                from src.pricing.land_price import fetch_and_store_land_prices
                settings_path = Path(__file__).parent.parent.parent.parent / "config" / "settings.yaml"
                with open(settings_path, encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                db_path = str(
                    Path(__file__).parent.parent.parent.parent / config["database"]["path"]
                )
                api_key = config.get("api_keys", {}).get("reinfolib")
                fetch_and_store_land_prices(db_path, api_key=api_key)
                st.success("地価データ更新完了")
                st.rerun()
            except Exception:
                logger.exception("処理エラー")
                st.error("処理中にエラーが発生しました。ログを確認してください。")

    conn.close()


def _run_spider(project_dir: str, spider_name: str):
    """Spiderを実行"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "scrapy", "crawl", spider_name],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            st.warning(f"{spider_name}: {result.stderr[:500]}")
    except subprocess.TimeoutExpired:
        st.warning(f"{spider_name}: タイムアウト (10分)")
    except Exception as e:
        st.warning(f"{spider_name}: {e}")
