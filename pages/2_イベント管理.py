import streamlit as st
import pandas as pd
from datetime import date, time
from utils import (get_ws, load_events, write_change_log, now_jst,
                   write_row_by_header, append_row_by_header,
                   WEEKDAYS, EVENT_SHEET)

KINDS = ["練習", "試合", "自主練習"]

def _bool(v):
    if isinstance(v, bool): return v
    if isinstance(v, str):  return v.upper() in ("TRUE", "あり", "1")
    return bool(v)

def _s(v):
    if v is None: return ""
    try:
        if pd.isna(v): return ""
    except: pass
    return str(v).strip()

# =========================
# イベント追加
# =========================
st.markdown("### ➕ イベント追加")

events = load_events()
today  = pd.Timestamp(date.today())

with st.form("event_form"):
    d      = st.date_input("日付", date.today())
    add_kind = st.selectbox("種類", KINDS, key="add_kind_form")
    c3, c4 = st.columns(2)
    start  = c3.time_input("開始", value=time(9, 0))
    end    = c4.time_input("終了", value=time(12, 0))
    loc    = st.text_input("場所")
    tanto  = st.text_input("担当班")
    memo   = st.text_area("メモ", height=80)
    haisha = st.checkbox("配車あり", value=False)

    st.markdown("**役割分担（試合の場合のみ選択）**")
    rc1, rc2, rc3 = st.columns(3)
    scorer    = rc1.checkbox("スコアラー", key="add_scorer")
    referee   = rc2.checkbox("審判",       key="add_referee")
    h_referee = rc3.checkbox("主審",       key="add_h_referee")

    if st.form_submit_button("登録"):
        ws = get_ws(EVENT_SHEET)
        load_events.clear()
        events_df = load_events()
        new_id = 1 if events_df.empty else int(events_df["イベントID"].max()) + 1
        ns = now_jst()
        append_row_by_header(ws, {
            "イベントID": new_id, "日付": str(d),
            "開始時間": start.strftime("%H:%M"), "終了時間": end.strftime("%H:%M"),
            "種類": add_kind, "場所": loc, "担当班": tanto, "配車": haisha,
            "メモ": memo, "更新日時": ns,
            "スコアラー": scorer, "審判": referee, "主審": h_referee,
        })
        _wd    = WEEKDAYS[pd.Timestamp(d).weekday()]
        _einfo = f"{d.strftime('%m/%d')}({_wd}) {add_kind}"
        write_change_log([[ns, "イベント", _einfo, "新規追加", "",
                           f"{loc} {start.strftime('%H:%M')}〜{end.strftime('%H:%M')}"]])
        load_events.clear()
        st.success("登録OK")
        st.rerun()

# =========================
# イベント編集・削除
# =========================
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

            cur_kind = er["種類"] if er["種類"] in KINDS else "練習"

            with st.form("edit_form"):
                ed = st.date_input("日付", value=er["日付"].date())
                et = st.selectbox("種類", KINDS, index=KINDS.index(cur_kind))
                ec3, ec4 = st.columns(2)
                try:
                    es = time(*[int(x) for x in er["開始時間"].split(":")])
                    ee = time(*[int(x) for x in er["終了時間"].split(":")])
                except:
                    es, ee = time(9, 0), time(12, 0)
                estart = ec3.time_input("開始", value=es)
                eend   = ec4.time_input("終了", value=ee)
                eloc   = st.text_input("場所",   value=_s(er["場所"]))
                etanto = st.text_input("担当班", value=_s(er.get("担当班", "")))
                ememo  = st.text_area("メモ", value=_s(er.get("メモ", "")), height=80)
                haisha_val = _bool(er.get("配車", False))
                ehaisha    = st.checkbox("配車あり", value=haisha_val)

                if et == "試合":
                    st.markdown("**役割分担（試合の場合のみ選択）**")
                    rc1, rc2, rc3 = st.columns(3)
                    scorer_val    = _bool(er.get("スコアラー", False))
                    referee_val   = _bool(er.get("審判",       False))
                    h_ref_val     = _bool(er.get("主審",       False))
                    escorer    = rc1.checkbox("スコアラー", value=scorer_val,  key="edit_scorer")
                    ereferee   = rc2.checkbox("審判",       value=referee_val, key="edit_referee")
                    eh_referee = rc3.checkbox("主審",       value=h_ref_val,   key="edit_h_ref")
                else:
                    escorer = ereferee = eh_referee = False

                col_save, col_del = st.columns(2)
                save_btn = col_save.form_submit_button("💾 保存")
                del_btn  = col_del.form_submit_button("🗑️ 削除", type="secondary")

                if save_btn:
                    ws  = get_ws(EVENT_SHEET)
                    ns  = now_jst()
                    all_rows = ws.get_all_records()
                    for i, row in enumerate(all_rows, start=2):
                        if int(row["イベントID"]) == edit_id:
                            write_row_by_header(ws, i, {
                                "イベントID": edit_id, "日付": str(ed),
                                "開始時間": estart.strftime("%H:%M"), "終了時間": eend.strftime("%H:%M"),
                                "種類": et, "場所": eloc, "担当班": etanto, "配車": ehaisha,
                                "メモ": ememo, "更新日時": ns,
                                "スコアラー": escorer, "審判": ereferee, "主審": eh_referee,
                            })
                            break

                    _wd    = WEEKDAYS[er["日付"].weekday()]
                    _einfo = f"{er['日付'].strftime('%m/%d')}({_wd}) {er['種類']}"
                    field_map = [
                        ("日付",      str(er["日付"].date()),          str(ed)),
                        ("種類",      _s(er["種類"]),                   et),
                        ("開始時間",  _s(er["開始時間"]),               estart.strftime("%H:%M")),
                        ("終了時間",  _s(er["終了時間"]),               eend.strftime("%H:%M")),
                        ("場所",      _s(er["場所"]),                   eloc),
                        ("担当班",    _s(er.get("担当班", "")),         etanto),
                        ("配車",      str(haisha_val),                  str(ehaisha)),
                        ("メモ",      _s(er.get("メモ", "")),           ememo),
                        ("スコアラー", str(_bool(er.get("スコアラー", False))), str(escorer)),
                        ("審判",      str(_bool(er.get("審判", False))),       str(ereferee)),
                        ("主審",      str(_bool(er.get("主審", False))),       str(eh_referee)),
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
