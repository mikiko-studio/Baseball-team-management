import streamlit as st
import pandas as pd
from datetime import date
from utils import (load_players, load_events, load_attendance, load_staff,
                   load_change_log, save_attendance_bulk, google_calendar_url,
                   compute_car_allocation, WEEKDAYS)

ROLES = ["", "スコアラー", "審判", "主審", "観覧のみ"]

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
                _d = r["日時dt"].strftime("%m/%d %H:%M") if pd.notna(r["日時dt"]) else ""
                st.caption(f"📅 {_d}　{r['イベント情報']}　{r['変更項目']}: {r['変更前']} → {r['変更後']}")
            _att = _recent[_recent["種別"] == "出欠"]
            if not _att.empty:
                for _ei, grp in _att.groupby("イベント情報", sort=False):
                    st.caption(f"✅ {grp['日時dt'].max().strftime('%m/%d %H:%M')}　{_ei}　出欠更新（{len(grp)}件）")
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
staff_df   = load_staff()

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
            _haisha = e.get("配車", False)
            if isinstance(_haisha, str): _haisha = _haisha.upper() in ("TRUE", "あり")
            car_icon = " 🚗" if _haisha else ""
            label = f"{icon} {e['日付'].strftime('%m/%d')}({wd}) {e['種類']} {e['開始時間']}〜{e['終了時間']} {e['場所']}{car_icon}"
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
        st.write(f"📅 {event_row['日付'].strftime('%m/%d')}({wd}) {event_row['種類']} "
                 f"{event_row['開始時間']}〜{event_row['終了時間']} {event_row['場所']}")
        tanto_val = event_row.get("担当班", "")
        if tanto_val:
            st.write(f"👥 担当班: {tanto_val}")
        if event_row["メモ"]:
            st.write(f"📝 {event_row['メモ']}")

        haisha_flag = event_row.get("配車", False)
        if isinstance(haisha_flag, str):
            haisha_flag = haisha_flag.upper() in ("TRUE", "あり")
        is_game = event_row["種類"] == "試合"

        # ---- 出席サマリー表示 ----
        if not attendance.empty:
            att_ev = attendance[attendance["イベントID"] == event_id]
            attendees = att_ev[att_ev["出欠"] == "出席"]
            pending   = att_ev[att_ev["出欠"] == "未定"]
            if not attendees.empty:
                if haisha_flag:
                    has_car_col = "配車" in attendees.columns and \
                                  attendees["配車"].astype(str).str.strip().ne("").any()
                    if has_car_col:
                        # 配車番号でソート（数値として）
                        attendees = attendees.copy()
                        attendees["_car_n"] = pd.to_numeric(
                            attendees["配車"].astype(str).str.strip(), errors="coerce"
                        ).fillna(99)
                        for car_num, grp in attendees.sort_values("_car_n").groupby("配車", sort=False):
                            driver_mark = lambda r: "🚗" if str(r.get("車出し","")).upper() == "TRUE" else ""
                            members = "、".join(
                                f"{r['名前']}{driver_mark(r)}" for _, r in grp.iterrows()
                            )
                            st.write(f"🚗 {car_num}号車: {members}")
                    else:
                        names = attendees["名前"].tolist()
                        for i, group in enumerate([names[j:j+4] for j in range(0, len(names), 4)], 1):
                            st.write(f"🚗 {i}号車: " + "、".join(group))
                else:
                    st.write("✅ 出席: " + "、".join(attendees["名前"].tolist()))
            if not pending.empty:
                st.write("❓ 未定: " + "、".join(pending["名前"].tolist()))

        # ---- 自動配車割り振り計算（選手＋運営の合算） ----
        def get_saved(name):
            if attendance.empty:
                return {"出欠": "未定", "配車": "", "車出し": False, "役割": ""}
            row = attendance[(attendance["イベントID"] == event_id) & (attendance["名前"] == name)]
            if row.empty:
                return {"出欠": "未定", "配車": "", "車出し": False, "役割": ""}
            r = row.iloc[0]
            return {
                "出欠": r.get("出欠", "未定"),
                "配車": str(r.get("配車", "") or ""),
                "車出し": str(r.get("車出し", "")).upper() == "TRUE",
                "役割": str(r.get("役割", "") or ""),
            }

        auto_car_map = {}
        car_warnings = []
        use_auto = True
        if haisha_flag:
            player_names = players["名前"].tolist() if not players.empty else []
            staff_names  = staff_df["名前"].tolist() if not staff_df.empty and "名前" in staff_df.columns else []
            all_names    = player_names + staff_names

            attend_names = [n for n in all_names if get_saved(n)["出欠"] == "出席"]
            drivers_set  = {n for n in attend_names if get_saved(n)["車出し"]}
            auto_car_map, car_warnings = compute_car_allocation(attend_names, drivers_set, max_per_car=5)

            if not attendance.empty:
                _ev_att = attendance[(attendance["イベントID"] == event_id) & (attendance["出欠"] == "出席")]
                if not _ev_att.empty and "配車" in _ev_att.columns:
                    if _ev_att["配車"].astype(str).str.strip().nunique() > 1:
                        use_auto = False

        for w in car_warnings:
            st.warning(w)

        # ---- 入力フォーム ----
        with st.form("attend"):
            status_dict      = {}
            haisha_dict      = {}
            member_type_dict = {}
            sharsha_dict     = {}
            role_dict        = {}

            def render_player_row(name):
                """選手行：出欠 (+号車)"""
                saved    = get_saved(name)
                d_status = saved["出欠"]
                d_car    = saved["配車"]

                if haisha_flag:
                    c1, c2, c3 = st.columns([2, 4, 1])
                else:
                    c1, c2 = st.columns([1, 3])

                c1.write(name)
                status = c2.radio("", ["未定", "出席", "欠席"],
                                  index=["未定", "出席", "欠席"].index(d_status),
                                  horizontal=True, key=f"{event_id}_{name}",
                                  label_visibility="collapsed")
                if haisha_flag:
                    car_val = (int(d_car) if (not use_auto and d_car.isdigit())
                               else auto_car_map.get(name, 1))
                    car_num = c3.number_input("号車", min_value=1, max_value=20, value=car_val,
                                              key=f"car_{event_id}_{name}",
                                              label_visibility="collapsed")
                    haisha_dict[name] = car_num

                status_dict[name]      = status
                member_type_dict[name] = "選手"

            def render_staff_row(name):
                """運営行：出欠 (+車出し +号車 +役割)"""
                saved     = get_saved(name)
                d_status  = saved["出欠"]
                d_car     = saved["配車"]
                d_sharsha = saved["車出し"]
                d_role    = saved["役割"] if saved["役割"] in ROLES else ""

                if haisha_flag and is_game:
                    c1, c2, c3, c4, c5 = st.columns([2, 4, 1, 1, 2])
                elif haisha_flag:
                    c1, c2, c3, c4 = st.columns([2, 4, 1, 1])
                elif is_game:
                    c1, c2, c3 = st.columns([2, 4, 2])
                else:
                    c1, c2 = st.columns([1, 3])

                c1.write(name)
                status = c2.radio("", ["未定", "出席", "欠席"],
                                  index=["未定", "出席", "欠席"].index(d_status),
                                  horizontal=True, key=f"{event_id}_{name}",
                                  label_visibility="collapsed")
                if haisha_flag:
                    sharsha = c3.checkbox("🚗", value=d_sharsha,
                                          key=f"sh_{event_id}_{name}", help="車出し可")
                    car_val = (int(d_car) if (not use_auto and d_car.isdigit())
                               else auto_car_map.get(name, 1))
                    car_num = c4.number_input("号車", min_value=1, max_value=20, value=car_val,
                                              key=f"car_{event_id}_{name}",
                                              label_visibility="collapsed")
                    haisha_dict[name]  = car_num
                    sharsha_dict[name] = sharsha
                    if is_game:
                        role = c5.selectbox("", ROLES,
                                            index=ROLES.index(d_role) if d_role in ROLES else 0,
                                            key=f"role_{event_id}_{name}",
                                            label_visibility="collapsed")
                        role_dict[name] = role
                elif is_game:
                    role = c3.selectbox("", ROLES,
                                        index=ROLES.index(d_role) if d_role in ROLES else 0,
                                        key=f"role_{event_id}_{name}",
                                        label_visibility="collapsed")
                    role_dict[name] = role

                status_dict[name]      = status
                member_type_dict[name] = "運営"

            # 選手セクション
            st.markdown("**⚾ 選手**")
            if haisha_flag:
                h1, h2, h3 = st.columns([2, 4, 1])
                h3.caption("号車")
            for _, p in players.iterrows():
                render_player_row(p["名前"])

            # 運営セクション
            if not staff_df.empty and "名前" in staff_df.columns:
                st.markdown("**🏅 運営**")
                if haisha_flag and is_game:
                    h1, h2, h3, h4, h5 = st.columns([2, 4, 1, 1, 2])
                    h3.caption("車出し"); h4.caption("号車"); h5.caption("役割")
                elif haisha_flag:
                    h1, h2, h3, h4 = st.columns([2, 4, 1, 1])
                    h3.caption("車出し"); h4.caption("号車")
                elif is_game:
                    h1, h2, h3 = st.columns([2, 4, 2])
                    h3.caption("役割")
                for _, s in staff_df.iterrows():
                    render_staff_row(s["名前"])

            if st.form_submit_button("保存"):
                _wd    = WEEKDAYS[event_row["日付"].weekday()]
                _einfo = f"{event_row['日付'].strftime('%m/%d')}({_wd}) {event_row['種類']}"
                save_attendance_bulk(
                    event_id, status_dict,
                    haisha_dict      if haisha_flag else None,
                    _einfo,
                    member_type_dict,
                    sharsha_dict     if haisha_flag else None,
                    role_dict        if is_game     else None,
                )
                st.success("保存完了")
                st.rerun()
