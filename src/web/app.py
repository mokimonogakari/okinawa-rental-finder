"""Streamlit メインアプリケーション"""

import streamlit as st
from pathlib import Path

st.set_page_config(
    page_title="沖縄賃貸ファインダー",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# カスタムCSS
st.markdown("""
<style>
    .main-header { font-size: 2rem; font-weight: bold; margin-bottom: 0.5rem; }
    .sub-header { color: #666; margin-bottom: 2rem; }
    .metric-card {
        background: #f8f9fa; border-radius: 8px; padding: 1rem;
        border-left: 4px solid #1f77b4;
    }
    .bargain { border-left-color: #2ecc71; background: #f0fff0; }
    .expensive { border-left-color: #e74c3c; background: #fff0f0; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">🏠 沖縄賃貸ファインダー</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">宅建士監修の検索条件 × AI価格推定で、沖縄の賃貸物件を賢く探す</div>',
    unsafe_allow_html=True,
)

# ページナビゲーション
page = st.sidebar.radio(
    "メニュー",
    ["🔍 物件検索", "📊 価格分析", "🔔 通知設定", "⚙️ 管理"],
    label_visibility="collapsed",
)

if page == "🔍 物件検索":
    from src.web.pages.search import render_search_page
    render_search_page()
elif page == "📊 価格分析":
    from src.web.pages.analysis import render_analysis_page
    render_analysis_page()
elif page == "🔔 通知設定":
    from src.web.pages.settings import render_settings_page
    render_settings_page()
elif page == "⚙️ 管理":
    from src.web.pages.admin import render_admin_page
    render_admin_page()
