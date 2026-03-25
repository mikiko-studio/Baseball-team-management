import streamlit as st
import pandas as pd
from datetime import date, time
from utils import (check_password, get_ws, get_spreadsheet, load_events, write_change_log,
                   now_jst, WEEKDAYS, EVENT_SHEET)

st.set_page_config(layout="wide", initial_sidebar_state="expanded")

if not check_password():
    st.stop()

st.markdown("### ➕ イベント追加")

events = load_events()
today  = pd.Timestamp(date.today())

with st.form("event_form"):
    c1, c2 = st.columns(2)
    d = c1.date_input("日付", date.today())
    t = c2.selectbox("種類", ["練習", "試合", "自主練習"])
    c3, c4 = st.columns(2)
    start = c3.time_input("開始", value=time(9, 0))
    end   = c4.time_input("終了", value=time(12, 0))
    loc   = st.text_input("場所")
    tanto = st.text_input("担当班")
    memo  = st.text_input("メモ")
    haisha = st.checkbox("配車あり", value=False)

    if st.form_submit_button("登録"):
        ws = get_ws(EVENT_SHEET)
        load_events.clear()
        events_df = load_events()
        new_id = 1 if events_df.empty else int(events_df["イベントID"].max()) + 1
        ns = now_jst()
        ws.append_row([new_id, str(d), start.strftime("%H:%M"), end.strftime("%H:%M"),
                       t, loc, tanto, haisha, memo, ns])
        _wd    = WEEKDAYS[pd.Timestamp(d).weekday()]
        _einfo = f"{d.strftime('%m/%d')}({_wd}) {t}"
        write_change_log([[ns, "イベント", _einfo, "新規追加", "",
                           f"{loc} {start.strftime('%H:%M')}〜{end.strftime('%H:%M')}"]])
        load_events.clear()
        st.success("登録OK")
        st.rerun()

st.divider()
st.markdown("### ✏️ イベント編集・削除")

events = load_events()
if events.empty:
    st.info("イベントがありません")
else:
    events_future = events[events["日付"] >= today].sort_values("日付")
    if events_future.empty:
        st.info("本日以降のイベントがありません")
    else:
        event_options = {
            int(e["イベントID"]): f"{e['日付'].strftime('%m/%d')}({WEEKDAYS[e['日付'].weekday()]}) {e['種類']} {e['メモ']}"
            for _, e in events_future.iterrows()
        }
        edit_id = st.selectbox("イベントを選択", options=list(event_options.keys()),
                               format_func=lambda x: event_options[x], key="edit_select")

        if edit_id:
            er = events[events["イベントID"] == edit_id].iloc[0]
            with st.form("edit_form"):
                ec1, ec2 = st.columns(2)
                ed = ec1.date_input("日付", value=er["日付"].date())
                et = ec2.selectbox("種類", ["練習","試合","自主練習"],
                                   index=["練習","試合","自主練習"].index(er["種類"]))
                ec3, ec4 = st.columns(2)
                try:
                    es = time(*[int(x) for x in er["開始時間"].split(":")])
                    ee = time(*[int(x) for x in er["終了時間"].split(":")])
                except:
                    es, ee = time(9, 0), time(12, 0)
                estart = ec3.time_input("開始", value=es)
                eend   = ec4.time_input("終了", value=ee)
                eloc   = st.text_input("場所", value=er["場所"])
                etanto = st.text_input("担当班", value=str(er.get("担当班", "") or ""))
                ememo  = st.text_input("メモ", value=str(er.get("メモ", "") or ""))
                haisha_val = er.get("配車", False)
                if isinstance(haisha_val, str):
                    haisha_val = haisha_val.upper() in ("TRUE", "あり")
                ehaisha = st.checkbox("配車あり", value=bool(haisha_val))

                col_save, col_del = st.columns(2)
                save_btn = col_save.form_submit_button("💾 保存")
                del_btn  = col_del.form_submit_button("🗑️ 削除", type="secondary")

                if save_btn:
                    ws = get_ws(EVENT_SHEET)
                    all_rows = ws.get_all_records()
                    ns = now_jst()
                    for i, row in enumerate(all_rows, start=2):
                        if int(row["イベントID"]) == edit_id:
                            ws.update(f"A{i}:J{i}", [[edit_id, str(ed),
                                estart.strftime("%H:%M"), eend.strftime("%H:%M"),
                                et, eloc, etanto, ehaisha, ememo, ns]])
                            break

                    def _s(v):
                        if v is None: return ""
                        try:
                            if pd.isna(v): return ""
                        except: pass
                        return str(v).strip()

                    _wd    = WEEKDAYS[er["日付"].weekday()]
                    _einfo = f"{er['日付'].strftime('%m/%d')}({_wd}) {er['種類']}"
                    field_map = [
                        ("日付",    str(er["日付"].date()),    str(ed)),
                        ("種類",    _s(er["種類"]),             et),
                        ("開始時間", _s(er["開始時間"]),         estart.strftime("%H:%M")),
                        ("終了時間", _s(er["終了時間"]),         eend.strftime("%H:%M")),
                        ("場所",    _s(er["場所"]),             eloc),
                        ("担当班",  _s(er.get("担当班", "")),   etanto),
                        ("配車",    str(bool(haisha_val)),     str(ehaisha)),
                        ("メモ",    _s(er.get("メモ", "")),     ememo),
                    ]
                    log_entries = [
                        [ns, "イベント", _einfo, f, o, n]
                        for f, o, n in field_map if o != _s(n)
                    ]
                    write_change_log(log_entries)
                    load_events.clear()
                    st.success(f"更新しました（変更{len(log_entries)}件をログに記録）")
                    st.rerun()

                if del_btn:
                    ws = get_ws(EVENT_SHEET)
                    all_rows = ws.get_all_records()
                    for i, row in enumerate(all_rows, start=2):
                        if int(row["イベントID"]) == edit_id:
                            ws.delete_rows(i)
                            break
                    ns     = now_jst()
                    _wd    = WEEKDAYS[er["日付"].weekday()]
                    _einfo = f"{er['日付'].strftime('%m/%d')}({_wd}) {er['種類']}"
                    write_change_log([[ns, "イベント", _einfo, "削除", _einfo, ""]])
                    load_events.clear()
                    st.success("削除しました")
                    st.rerun()
