import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import date, time
import requests
import os

# --- 定数 ---
SPREADSHEET_ID = "17s98-7sAmcom90WjoHcwrPuz8IgKGFSI1c8quT4iteg"
PLAYER_SHEET = "選手名簿"
EVENT_SHEET = "イベント"
ATTEND_SHEET = "出席管理"
WEEKDAYS = ["月","火","水","木","金","土","日"]

GRADES = ["1年","2年","3年","4年","5年","6年"]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

@st.cache_resource
def get_spreadsheet():
    import json, base64
    if "gcp_service_account_b64" in st.secrets:
        info = json.loads(base64.b64decode(st.secrets["gcp_service_account_b64"]).decode("utf-8"))
        client = gspread.service_account_from_dict(info)
    else:
        client = gspread.service_account(filename="service_account.json")
    return client.open_by_key(SPREADSHEET_ID)

@st.cache_resource
def get_ws(name):
    return get_spreadsheet().worksheet(name)

@st.cache_data(ttl=10)
def load_players():
    return pd.DataFrame(get_ws(PLAYER_SHEET).get_all_records())

@st.cache_data(ttl=10)
def load_events():
    df = pd.DataFrame(get_ws(EVENT_SHEET).get_all_records())
    if not df.empty:
        df["日付"] = pd.to_datetime(df["日付"])
    return df

@st.cache_data(ttl=10)
def load_attendance():
    df = pd.DataFrame(get_ws(ATTEND_SHEET).get_all_records())

    if not df.empty:
        cols = list(df.columns)
        if "出欠" not in cols:
            if "ステータス" in cols:
                df = df.rename(columns={"ステータス": "出欠"})
            elif "status" in cols:
                df = df.rename(columns={"status": "出欠"})

        required = ["イベントID", "名前", "出欠"]
        for c in required:
            if c not in df.columns:
                return pd.DataFrame(columns=required)

    return df

# 上書き保存
def save_attendance_bulk(event_id, status_dict):
    ws = get_ws(ATTEND_SHEET)
    load_attendance.clear()  # キャッシュを破棄して最新データを取得
    df = load_attendance()

    if not df.empty:
        # 重複排除してから対象イベントを除外
        df = df.drop_duplicates(subset=["イベントID", "名前"], keep="last")
        df = df[df["イベントID"] != event_id]
        ws.clear()
        ws.append_row(["イベントID", "名前", "出欠"])
        if not df.empty:
            ws.append_rows(df.values.tolist())

    rows = [[int(event_id), name, status] for name, status in status_dict.items()]
    ws.append_rows(rows)
    load_attendance.clear()  # 保存後もキャッシュをリセット

# LINE Messaging API 通知
def send_line_message(message):
    token = st.secrets.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token:
        return False, "LINE_CHANNEL_ACCESS_TOKENが未設定"
    group_id = st.secrets.get("LINE_GROUP_ID", "")
    if group_id:
        url = "https://api.line.me/v2/bot/message/push"
        body = {"to": group_id, "messages": [{"type": "text", "text": message}]}
    else:
        url = "https://api.line.me/v2/bot/message/broadcast"
        body = {"messages": [{"type": "text", "text": message}]}
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.post(url, headers=headers, json=body)
    return r.status_code == 200, r.text

# Googleカレンダー追加URL生成
def google_calendar_url(title, dt, start_str, end_str, location, details=""):
    from urllib.parse import quote
    try:
        sh, sm = [int(x) for x in start_str.split(":")]
        eh, em = [int(x) for x in end_str.split(":")]
    except:
        return ""
    start = f"{dt.strftime('%Y%m%d')}T{sh:02d}{sm:02d}00"
    end   = f"{dt.strftime('%Y%m%d')}T{eh:02d}{em:02d}00"
    url = f"https://calendar.google.com/calendar/render?action=TEMPLATE&text={quote(title)}&dates={start}/{end}&location={quote(location)}"
    if details:
        url += f"&details={quote(details)}"
    return url

st.set_page_config(layout="wide")
st.markdown("""
<div style="border:2px solid #4a9eda; border-radius:8px; padding:6px 16px; display:inline-block;">
<h3 style="margin:0;">⚾ 少年野球チーム管理アプリ（カレンダー＋出欠一体型）</h3>
</div>
""", unsafe_allow_html=True)

# =========================
# メインデータ
# =========================
events = load_events()

# URLパラメータからイベントID取得（LINE直リンク対応）
query_params = st.query_params
if "event_id" in query_params:
    try:
        st.session_state["selected_event_id"] = int(query_params["event_id"])
    except:
        pass
attendance = load_attendance()
players = load_players()

col_left, col_right = st.columns([1,2])

# =========================
# 左：カレンダー＋一覧
# =========================
with col_left:
    

    st.markdown("#### 📋 イベント一覧（クリックで選択）")

    if not events.empty:
        events_sorted = events.sort_values("日付")

        for _, e in events_sorted.iterrows():
            if e['種類'] == '試合':
                icon = "🔴"
            elif e['種類'] == '練習':
                icon = "🔵"
            else:
                icon = "⚪"
            wd = WEEKDAYS[e['日付'].weekday()]
            label = f"{icon} {e['日付'].strftime('%m/%d')}({wd}) {e['種類']} {e['開始時間']}〜{e['終了時間']} {e['場所']}"

            if st.button(label, key=f"list_{e['イベントID']}"):
                st.session_state["selected_event_id"] = int(e["イベントID"])
                st.session_state.pop("edit_event_id", None)

    st.divider()

    with st.expander("➕ イベント追加"):
        with st.form("event_form"):
            c1, c2 = st.columns(2)
            d = c1.date_input("日付", date.today())
            t = c2.selectbox("種類", ["練習", "試合", "自主練習"])
            c3, c4 = st.columns(2)
            start = c3.time_input("開始", value=time(9,0))
            end = c4.time_input("終了", value=time(12,0))
            loc = st.text_input("場所")
            tanto = st.text_input("担当班")
            title = st.text_input("メモ")

            if st.form_submit_button("登録"):
                ws = get_ws(EVENT_SHEET)
                load_events.clear()
                events_df = load_events()
                new_id = 1 if events_df.empty else int(events_df["イベントID"].max()) + 1
                ws.append_row([new_id, str(d), start.strftime("%H:%M"), end.strftime("%H:%M"), t, title, loc, tanto])
                app_url = st.secrets.get("APP_URL", "")
                link = f"{app_url}?event_id={new_id}" if app_url else ""
                wd = WEEKDAYS[pd.Timestamp(d).weekday()]
                msg = f"【新イベント】\n{d}({wd}) {title}\n{start.strftime('%H:%M')}〜{end.strftime('%H:%M')}\n📍{loc}\n{link}"
                send_line_message(msg)
                load_events.clear()
                st.success("登録OK")
                st.rerun()

    # =========================
    # イベント編集・削除
    # =========================
    with st.expander("✏️ イベント編集・削除"):
        if events.empty:
            st.info("イベントがありません")
        else:
            events_sorted2 = events.sort_values("日付")
            event_options = {
                int(e["イベントID"]): f"{e['日付'].strftime('%m/%d')}({WEEKDAYS[e['日付'].weekday()]}) {e['メモ']}"
                for _, e in events_sorted2.iterrows()
            }
            edit_id = st.selectbox("イベントを選択", options=list(event_options.keys()), format_func=lambda x: event_options[x], key="edit_select")

            if edit_id:
                er = events[events["イベントID"] == edit_id].iloc[0]
                with st.form("edit_form"):
                    ec1, ec2 = st.columns(2)
                    ed = ec1.date_input("日付", value=er["日付"].date())
                    et = ec2.selectbox("種類", ["練習", "試合", "自主練習"], index=["練習","試合","自主練習"].index(er["種類"]))
                    ec3, ec4 = st.columns(2)
                    try:
                        es = time(*[int(x) for x in er["開始時間"].split(":")])
                        ee = time(*[int(x) for x in er["終了時間"].split(":")])
                    except:
                        es, ee = time(9,0), time(12,0)
                    estart = ec3.time_input("開始", value=es)
                    eend = ec4.time_input("終了", value=ee)
                    eloc = st.text_input("場所", value=er["場所"])
                    etanto = st.text_input("担当班", value=er.get("担当班", ""))
                    etitle = st.text_input("メモ", value=er["メモ"])

                    col_save, col_del = st.columns(2)
                    save_btn = col_save.form_submit_button("💾 保存")
                    del_btn = col_del.form_submit_button("🗑️ 削除", type="secondary")

                    if save_btn:
                        ws = get_ws(EVENT_SHEET)
                        all_rows = ws.get_all_records()
                        for i, row in enumerate(all_rows, start=2):
                            if int(row["イベントID"]) == edit_id:
                                ws.update(f"A{i}:H{i}", [[edit_id, str(ed), estart.strftime("%H:%M"), eend.strftime("%H:%M"), et, etitle, eloc, etanto]])
                                break
                        load_events.clear()
                        st.success("更新しました")
                        st.rerun()

                    if del_btn:
                        ws = get_ws(EVENT_SHEET)
                        all_rows = ws.get_all_records()
                        for i, row in enumerate(all_rows, start=2):
                            if int(row["イベントID"]) == edit_id:
                                ws.delete_rows(i)
                                break
                        load_events.clear()
                        if st.session_state.get("selected_event_id") == edit_id:
                            st.session_state.pop("selected_event_id", None)
                        st.success("削除しました")
                        st.rerun()

# =========================
# 右：出欠
# =========================
with col_right:
    st.markdown("#### ✅ 出欠入力")

    if players.empty or events.empty:
        st.warning("先に選手・イベント登録")
    else:
        event_id = st.session_state.get("selected_event_id")

        if not event_id:
            st.info("左からイベントを選択してください")
        else:
            event_row = events[events["イベントID"] == event_id].iloc[0]

            wd = WEEKDAYS[event_row['日付'].weekday()]
            st.write(f"📅 {event_row['日付'].strftime('%m/%d')}({wd}) {event_row['種類']} {event_row['開始時間']}〜{event_row['終了時間']} {event_row['場所']}")
            tanto_val = event_row.get('担当班', '')
            if tanto_val:
                st.write(f"👥 担当班: {tanto_val}")
            if event_row['メモ']:
                st.write(f"📝 {event_row['メモ']}")

            btn_col1, btn_col2 = st.columns(2)
            gcal = google_calendar_url(event_row['種類'], event_row['日付'], event_row['開始時間'], event_row['終了時間'], event_row['場所'], event_row['メモ'])
            if gcal:
                btn_col1.link_button("📆 Googleカレンダーに追加", gcal)
            if btn_col2.button("📣 LINEに出欠状況を通知", key="line_notify"):
                if not attendance.empty:
                    att = attendance[attendance["イベントID"] == event_id]
                    出席 = ", ".join(att[att["出欠"]=="出席"]["名前"].tolist()) or "なし"
                    欠席 = ", ".join(att[att["出欠"]=="欠席"]["名前"].tolist()) or "なし"
                    未定 = ", ".join(att[att["出欠"]=="未定"]["名前"].tolist()) or "なし"
                    msg = f"【出欠状況】{event_row['日付'].strftime('%m/%d')}({wd}) {event_row['メモ']}\n✅出席: {出席}\n❌欠席: {欠席}\n❓未定: {未定}"
                    ok, detail = send_line_message(msg)
                    st.success("LINE送信OK") if ok else st.error(f"送信失敗: {detail}")

            if not attendance.empty:
                attendees = attendance[(attendance["イベントID"] == event_id) & (attendance["出欠"] == "出席")]
                pending = attendance[(attendance["イベントID"] == event_id) & (attendance["出欠"] == "未定")]
                if not attendees.empty:
                    st.write("✅ 出席: " + ", ".join(attendees["名前"].tolist()))
                if not pending.empty:
                    st.write("❓ 未定: " + ", ".join(pending["名前"].tolist()))

            with st.form("attend"):
                status_dict = {}

                for _, p in players.iterrows():
                    name = p["名前"]

                    default = "未定"
                    if not attendance.empty:
                        row = attendance[(attendance["イベントID"] == event_id) & (attendance["名前"] == name)]
                        if not row.empty:
                            default = row.iloc[0]["出欠"]

                    c1, c2 = st.columns([1, 3])
                    c1.write(name)
                    status = c2.radio(
                        "",
                        ["未定", "出席", "欠席"],
                        index=["未定","出席","欠席"].index(default),
                        horizontal=True,
                        key=f"{event_id}_{name}",
                        label_visibility="collapsed"
                    )

                    status_dict[name] = status

                if st.form_submit_button("保存"):
                    save_attendance_bulk(event_id, status_dict)
                    st.success("保存完了")
                    st.rerun()

# =========================
# 🔧 LINE設定
# =========================
st.divider()
with st.expander("🔧 LINE設定・テスト"):
    token_set = bool(st.secrets.get("LINE_CHANNEL_ACCESS_TOKEN", ""))
    group_set = bool(st.secrets.get("LINE_GROUP_ID", ""))
    st.write(f"Channel Access Token: {'✅ 設定済み' if token_set else '❌ 未設定'}")
    st.write(f"LINE_GROUP_ID: {'✅ 設定済み（グループ送信）' if group_set else '⚠️ 未設定（ブロードキャスト送信）'}")
    st.caption("Streamlit CloudのSecretsに `LINE_CHANNEL_ACCESS_TOKEN` と `LINE_GROUP_ID` を設定してください。")
    if st.button("📨 テストメッセージを送信"):
        ok, detail = send_line_message("【テスト】野球チーム管理アプリからの送信テストです。")
        st.success("送信OK") if ok else st.error(f"送信失敗: {detail}")

# =========================
# 👤 選手管理
# =========================
st.divider()
st.markdown("#### 👤 選手管理")
players_df = load_players()
if not players_df.empty:
    st.dataframe(players_df, use_container_width=True)

with st.form("add_player"):
    col1, col2, col3 = st.columns([2,2,1])
    name = col1.text_input("名前")
    grade = col2.selectbox("学年", GRADES)
    submitted = col3.form_submit_button("追加")

    if submitted:
        get_ws(PLAYER_SHEET).append_row([name, grade])
        st.success("登録OK")
        st.rerun()
