import streamlit as st
from utils import check_password

st.set_page_config(layout="wide", initial_sidebar_state="expanded")

if not check_password():
    st.stop()

pg = st.navigation([
    st.Page("pages/1_メイン.py",           title="出欠管理",         icon="🏠"),
    st.Page("pages/2_イベント管理.py",      title="イベント管理",     icon="📅"),
    st.Page("pages/3_選手管理.py",          title="選手管理",         icon="👤"),
    st.Page("pages/4_運営メンバー管理.py",  title="運営メンバー管理", icon="🏅"),
])
pg.run()
