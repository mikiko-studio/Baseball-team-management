import streamlit as st
import pandas as pd
from utils import check_password, get_spreadsheet, STAFF_SHEET

st.set_page_config(layout="wide", initial_sidebar_state="expanded")

if not check_password():
    st.stop()

st.markdown("### 🏅 運営メンバー管理")

STAFF_ROLES = ["監督", "コーチ", "マネージャー", "会計", "その他"]


def load_staff():
    try:
        df = pd.DataFrame(get_spreadsheet().worksheet(STAFF_SHEET).get_all_records())
        return df
    except Exception:
        return pd.DataFrame(columns=["名前", "役割", "メモ"])


def ensure_staff_ws():
    try:
        return get_spreadsheet().worksheet(STAFF_SHEET)
    except Exception:
        ws = get_spreadsheet().add_worksheet(title=STAFF_SHEET, rows=200, cols=5)
        ws.append_row(["名前", "役割", "メモ"])
        return ws


staff_df = load_staff()
if not staff_df.empty:
    st.dataframe(staff_df, use_container_width=True)
else:
    st.info("運営メンバーが登録されていません")

st.divider()
st.markdown("##### メンバー追加")
with st.form("add_staff"):
    col1, col2, col3 = st.columns([2, 2, 2])
    name  = col1.text_input("名前")
    role  = col2.selectbox("役割", STAFF_ROLES)
    memo  = col3.text_input("メモ")
    submitted = st.form_submit_button("追加")

    if submitted and name:
        ws = ensure_staff_ws()
        ws.append_row([name, role, memo])
        st.success("登録OK")
        st.rerun()

if not staff_df.empty:
    st.divider()
    st.markdown("##### メンバー編集・削除")
    options   = staff_df["名前"].tolist()
    sel_name  = st.selectbox("メンバーを選択", options)
    sel_row   = staff_df[staff_df["名前"] == sel_name].iloc[0] if sel_name else None

    if sel_row is not None:
        with st.form("edit_staff"):
            ec1, ec2, ec3 = st.columns([2, 2, 2])
            new_name = ec1.text_input("名前", value=sel_row["名前"])
            new_role = ec2.selectbox("役割", STAFF_ROLES,
                                     index=STAFF_ROLES.index(sel_row["役割"])
                                     if sel_row["役割"] in STAFF_ROLES else 0)
            new_memo = ec3.text_input("メモ", value=str(sel_row.get("メモ", "") or ""))
            cs, cd = st.columns(2)
            save_btn = cs.form_submit_button("💾 保存")
            del_btn  = cd.form_submit_button("🗑️ 削除", type="secondary")

            if save_btn:
                ws       = ensure_staff_ws()
                all_rows = ws.get_all_values()
                for i, row in enumerate(all_rows, start=1):
                    if row and row[0] == sel_name:
                        ws.update(f"A{i}:C{i}", [[new_name, new_role, new_memo]])
                        break
                st.success("更新しました")
                st.rerun()

            if del_btn:
                ws       = ensure_staff_ws()
                all_rows = ws.get_all_values()
                for i, row in enumerate(all_rows, start=1):
                    if row and row[0] == sel_name:
                        ws.delete_rows(i)
                        break
                st.success(f"{sel_name} を削除しました")
                st.rerun()
