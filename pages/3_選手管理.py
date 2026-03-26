import streamlit as st
from utils import get_ws, load_players, PLAYER_SHEET, GRADES, append_row_by_header

st.markdown("### 👤 選手管理")

players_df = load_players()
if not players_df.empty:
    st.dataframe(players_df, use_container_width=True)
else:
    st.info("選手が登録されていません")

st.divider()
st.markdown("##### 選手追加")
with st.form("add_player"):
    col1, col2, col3 = st.columns([2, 2, 1])
    name      = col1.text_input("名前")
    grade     = col2.selectbox("学年", [""] + GRADES)
    submitted = col3.form_submit_button("追加")

    if submitted and name and grade:
        append_row_by_header(get_ws(PLAYER_SHEET), {"名前": name, "学年": grade})
        load_players.clear()
        st.success("登録OK")
        st.rerun()

if not players_df.empty:
    st.divider()
    st.markdown("##### 選手削除")
    del_name = st.selectbox("削除する選手を選択", players_df["名前"].tolist())
    if st.button("削除", type="secondary"):
        ws       = get_ws(PLAYER_SHEET)
        all_rows = ws.get_all_values()
        if all_rows:
            headers  = all_rows[0]
            name_col = headers.index("名前") if "名前" in headers else 0
            for i, row in enumerate(all_rows[1:], start=2):
                if row and len(row) > name_col and row[name_col] == del_name:
                    ws.delete_rows(i)
                    break
        load_players.clear()
        st.success(f"{del_name} を削除しました")
        st.rerun()
