import streamlit as st
from utils import (get_spreadsheet, get_ws, load_staff,
                   STAFF_SHEET, append_row_by_header, write_row_by_header)

st.markdown("### 🏅 運営メンバー管理")

STAFF_ROLES = ["監督", "コーチ", "マネージャー", "会計", "その他"]


def ensure_staff_ws():
    try:
        return get_ws(STAFF_SHEET)
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
    role  = col2.selectbox("役割", [""] + STAFF_ROLES)
    memo  = col3.text_input("メモ")
    submitted = st.form_submit_button("追加")

    if submitted and name and role:
        ws = ensure_staff_ws()
        append_row_by_header(ws, {"名前": name, "役割": role, "メモ": memo}, sheet_name=STAFF_SHEET)
        load_staff.clear()
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
            _role_opts = [""] + STAFF_ROLES
            new_name = ec1.text_input("名前")
            new_role = ec2.selectbox("役割", _role_opts)
            new_memo = ec3.text_input("メモ")
            cs, cd = st.columns(2)
            save_btn = cs.form_submit_button("💾 保存")
            del_btn  = cd.form_submit_button("🗑️ 削除", type="secondary")

            if save_btn:
                save_name = new_name if new_name else sel_row["名前"]
                save_role = new_role if new_role else sel_row["役割"]
                save_memo = new_memo if new_memo else str(sel_row.get("メモ", "") or "")
                ws       = ensure_staff_ws()
                all_rows = ws.get_all_values()
                if all_rows:
                    headers  = all_rows[0]
                    name_col = headers.index("名前") if "名前" in headers else 0
                    for i, row in enumerate(all_rows[1:], start=2):
                        if row and len(row) > name_col and row[name_col] == sel_name:
                            write_row_by_header(ws, i, {"名前": save_name, "役割": save_role, "メモ": save_memo}, sheet_name=STAFF_SHEET)
                            break
                load_staff.clear()
                st.success("更新しました")
                st.rerun()

            if del_btn:
                ws       = ensure_staff_ws()
                all_rows = ws.get_all_values()
                if all_rows:
                    headers  = all_rows[0]
                    name_col = headers.index("名前") if "名前" in headers else 0
                    for i, row in enumerate(all_rows[1:], start=2):
                        if row and len(row) > name_col and row[name_col] == sel_name:
                            ws.delete_rows(i)
                            break
                load_staff.clear()
                st.success(f"{sel_name} を削除しました")
                st.rerun()
