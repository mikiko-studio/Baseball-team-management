import streamlit as st
import pandas as pd
from datetime import date
from utils import (check_password, load_players, load_events, load_attendance,
                   load_change_log, save_attendance_bulk, google_calendar_url,
                   WEEKDAYS)

st.set_page_config(layout="wide")

if not check_password():
    st.stop()

st.markdown("""
<div style="background-color:rgba(128,128,128,0.15); border-radius:8px; padding:6px 16px; display:inline-block;">
<h3 style="margin:0;">⚾ 少年野球チーム管理アプリ（カレンダー＋出欠一体型）</h3>
</div>
""", unsafe_allow_html=True)

# 直近1週間の変更ログサマリー
try:
    _log = load_change_log()
    _now_jst = pd.Timestamp.now() + pd.Timedelta(hours=9)
    _week_ago = _now_jst - pd.Timedelta(days=7)
    if not _log.empty and "日時dt" in _log.columns:
        _recent = _log[_log["日時dt"] >= _week_ago].sort_values("日時dt", ascending=False)
        if not _recent.empty:
            st.markdown("**📢 直近1週間の変更**")
            for _, r in _recent[_recent["種別"] == "イベント"].iterrows():
                _date = r["日時dt"].strftime("%m/%d %H:%M") if pd.notna(r["日時dt"]) else ""
                st.caption(f"📅 {_date}　{r['イベント情報']}　{r['変更項目']}: {r['変更前']} → {r['変更後']}")
            _attend = _recent[_recent["種別"] == "出欠"]
            if not _attend.empty:
                for _einfo, grp in _attend.groupby("イベント情報", sort=False):
                    _date = grp["日時dt"].max().strftime("%m/%d %H:%M")
                    st.caption(f"✅ {_date}　{_einfo}　出欠更新（{len(grp)}件）")
            st.markdown("")
        else:
            st.caption("📢 直近1週間の変更はありません")
    else:
        st.caption("📢 直近1週間の変更はありません")
except Exception as e:
    st.warning(f"変更ログの読み込みに失敗しました: {e}")

# URLパラメータからイベントID取得
query_params = st.query_params
if "event_id" in query_params:
    try:
        st.session_state["selected_event_id"] = int(query_params["event_id"])
    except:
        pass

events     = load_events()
attendance = load_attendance()
players    = load_players()

col_left, col_right = st.columns([1, 2])

# =========================
# 左：イベント一覧
# =========================
with col_left:
    st.markdown("#### 📋 イベント一覧（クリックで選択）")
    if not events.empty:
        today = pd.Timestamp(date.today())
        events_sorted = events[events["日付"] >= today].sort_values("日付")
        for _, e in events_sorted.iterrows():
            icon = "🔴" if e["種類"] == "試合" else "🔵" if e["種類"] == "練習" else "⚪"
            wd = WEEKDAYS[e["日付"].weekday()]
            label = f"{icon} {e['日付'].strftime('%m/%d')}({wd}) {e['種類']} {e['開始時間']}〜{e['終了時間']} {e['場所']}"
            is_selected = st.session_state.get("selected_event_id") == int(e["イベントID"])
            if st.button(label, key=f"list_{e['イベントID']}", type="primary" if is_selected else "secondary"):
                st.session_state["selected_event_id"] = int(e["イベントID"])
                st.rerun()

# =========================
# 右：出欠入力
# =========================
with col_right:
    event_id  = st.session_state.get("selected_event_id")
    event_row = (events[events["イベントID"] == event_id].iloc[0]
                 if (event_id and not events.empty and event_id in events["イベントID"].values)
                 else None)

    hd_col, btn_col = st.columns([3, 1])
    hd_col.markdown("#### ✅ イベント詳細＋出欠入力")
    if event_row is not None:
        gcal = google_calendar_url(
            event_row["種類"], event_row["日付"],
            event_row["開始時間"], event_row["終了時間"],
            event_row["場所"], event_row["メモ"]
        )
        if gcal:
            btn_col.link_button("📆 Googleカレンダー", gcal)

    if players.empty or events.empty:
        st.warning("先に選手・イベント登録")
    elif not event_id:
        st.info("左からイベントを選択してください")
    else:
        wd = WEEKDAYS[event_row["日付"].weekday()]
        st.write(f"📅 {event_row['日付'].strftime('%m/%d')}({wd}) {event_row['種類']} {event_row['開始時間']}〜{event_row['終了時間']} {event_row['場所']}")
        tanto_val = event_row.get("担当班", "")
        if tanto_val:
            st.write(f"👥 担当班: {tanto_val}")
        if event_row["メモ"]:
            st.write(f"📝 {event_row['メモ']}")

        haisha_flag = event_row.get("配車", False)
        if isinstance(haisha_flag, str):
            haisha_flag = haisha_flag.upper() in ("TRUE", "あり")

        if not attendance.empty:
            attendees = attendance[(attendance["イベントID"] == event_id) & (attendance["出欠"] == "出席")]
            pending   = attendance[(attendance["イベントID"] == event_id) & (attendance["出欠"] == "未定")]
            if not attendees.empty:
                if haisha_flag:
                    if "配車" in attendees.columns and attendees["配車"].astype(str).str.strip().ne("").any():
                        for car_num, grp in attendees.groupby("配車", sort=True):
                            st.write(f"🚗 {car_num}号車: " + "、".join(grp["名前"].tolist()))
                    else:
                        names = attendees["名前"].tolist()
                        for i, group in enumerate([names[j:j+4] for j in range(0, len(names), 4)], 1):
                            st.write(f"🚗 {i}号車: " + "、".join(group))
                else:
                    st.write("✅ 出席: " + "、".join(attendees["名前"].tolist()))
            if not pending.empty:
                st.write("❓ 未定: " + "、".join(pending["名前"].tolist()))

        # 自動配車割り振り
        auto_car_map = {}
        use_auto = True
        if haisha_flag:
            _idx = 0
            for _, _p in players.iterrows():
                _n = _p["名前"]
                _st = "未定"
                if not attendance.empty:
                    _r = attendance[(attendance["イベントID"] == event_id) & (attendance["名前"] == _n)]
                    if not _r.empty:
                        _st = _r.iloc[0]["出欠"]
                if _st == "出席":
                    auto_car_map[_n] = (_idx // 4) + 1
                    _idx += 1
            if not attendance.empty:
                _ev_att = attendance[(attendance["イベントID"] == event_id) & (attendance["出欠"] == "出席")]
                if not _ev_att.empty and "配車" in _ev_att.columns:
                    if _ev_att["配車"].astype(str).str.strip().nunique() > 1:
                        use_auto = False

        with st.form("attend"):
            status_dict = {}
            haisha_dict = {}

            for _, p in players.iterrows():
                name = p["名前"]
                default_status = "未定"
                default_car = ""
                if not attendance.empty:
                    row = attendance[(attendance["イベントID"] == event_id) & (attendance["名前"] == name)]
                    if not row.empty:
                        default_status = row.iloc[0]["出欠"]
                        if "配車" in row.columns:
                            default_car = str(row.iloc[0].get("配車", "") or "")

                if haisha_flag:
                    c1, c2, c3 = st.columns([1, 3, 1])
                    c1.write(name)
                    status = c2.radio("", ["未定","出席","欠席"],
                                      index=["未定","出席","欠席"].index(default_status),
                                      horizontal=True, key=f"{event_id}_{name}",
                                      label_visibility="collapsed")
                    car_val = (int(default_car) if (not use_auto and default_car.isdigit())
                               else auto_car_map.get(name, 1))
                    car_num = c3.number_input("号車", min_value=1, max_value=20, value=car_val,
                                              key=f"car_{event_id}_{name}", label_visibility="collapsed")
                    haisha_dict[name] = car_num
                else:
                    c1, c2 = st.columns([1, 3])
                    c1.write(name)
                    status = c2.radio("", ["未定","出席","欠席"],
                                      index=["未定","出席","欠席"].index(default_status),
                                      horizontal=True, key=f"{event_id}_{name}",
                                      label_visibility="collapsed")
                status_dict[name] = status

            if st.form_submit_button("保存"):
                _wd = WEEKDAYS[event_row["日付"].weekday()]
                _einfo = f"{event_row['日付'].strftime('%m/%d')}({_wd}) {event_row['種類']}"
                save_attendance_bulk(event_id, status_dict, haisha_dict if haisha_flag else None, _einfo)
                st.success("保存完了")
                st.rerun()
