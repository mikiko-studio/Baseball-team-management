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
LINE_NOTIFY_TOKEN = os.getenv("LINE_NOTIFY_TOKEN")

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
    df = load_attendance()

    if not df.empty:
        df = df[df["イベントID"] != event_id]
        ws.clear()
        ws.append_row(["イベントID", "名前", "出欠"])
        ws.append_rows(df.values.tolist())

    rows = [[int(event_id), name, status] for name, status in status_dict.items()]
    ws.append_rows(rows)

# LINE通知
def send_line_notify(message):
    if not LINE_NOTIFY_TOKEN:
        return
    url = "https://notify-api.line.me/api/notify"
    headers = {"Authorization": f"Bearer {LINE_NOTIFY_TOKEN}"}
    data = {"message": message}
    requests.post(url, headers=headers, data=data)

st.set_page_config(layout="wide")
st.title("⚾ 少年野球チーム管理アプリ（カレンダー＋出欠一体型）")

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
    

    st.subheader("📋 イベント一覧（クリックで選択）")

    # 未回答フィルタ
    show_only_pending = st.checkbox("未回答のみ表示")
    if not events.empty:
        events_sorted = events.sort_values("日付")

        # 未回答フィルタ適用
        if show_only_pending and not attendance.empty:
            pending_ids = []
            for _, e in events_sorted.iterrows():
                event_id = int(e["イベントID"])
                answered = attendance[attendance["イベントID"] == event_id]
                if len(answered) < len(players):
                    pending_ids.append(event_id)
            events_sorted = events_sorted[events_sorted["イベントID"].isin(pending_ids)]

        for _, e in events_sorted.iterrows():
            # 種類ごとに色分け
            if e['種類'] == '試合':
                icon = "🔴"
            elif e['種類'] == '練習':
                icon = "🔵"
            else:
                icon = "⚪"

            label = f"{icon} {e['日付'].strftime('%m/%d')} {e['タイトル']} ({e['開始時間']}〜{e['終了時間']}) @ {e['場所']}"

            if st.button(label, key=f"list_{e['イベントID']}"):
                st.session_state["selected_event_id"] = int(e["イベントID"])

    st.divider()

    st.subheader("➕ イベント追加")
    with st.form("event_form"):
        d = st.date_input("日付", date.today())
        start = st.time_input("開始", value=time(9,0))
        end = st.time_input("終了", value=time(12,0))
        t = st.selectbox("種類", ["練習", "試合", "自主練習"])
        title = st.text_input("タイトル")
        loc = st.text_input("場所")

        if st.form_submit_button("登録"):
            ws = get_ws(EVENT_SHEET)
            events_df = load_events()
            new_id = 1 if events_df.empty else int(events_df["イベントID"].max()) + 1

            ws.append_row([new_id, str(d), start.strftime("%H:%M"), end.strftime("%H:%M"), t, title, loc])

            app_url = st.secrets.get("APP_URL", "")
            link = f"{app_url}?event_id={new_id}" if app_url else ""

            msg = f"""新イベント
{d} {title}
{start.strftime('%H:%M')}〜{end.strftime('%H:%M')}
{loc}
{link}"""
            send_line_notify(msg)

            st.success("登録＆通知OK")
            st.rerun()

# =========================
# 右：出欠
# =========================
with col_right:
    st.subheader("✅ 出欠入力")

    if players.empty or events.empty:
        st.warning("先に選手・イベント登録")
    else:
        event_id = st.session_state.get("selected_event_id")

        if not event_id:
            st.info("左からイベントを選択してください")
        else:
            event_row = events[events["イベントID"] == event_id].iloc[0]

            st.write(f"📅 {event_row['日付'].strftime('%m/%d')} {event_row['タイトル']}")
            st.write(f"📍 {event_row['場所']} / {event_row['開始時間']}〜{event_row['終了時間']}")

            if not attendance.empty:
                attendees = attendance[(attendance["イベントID"] == event_id) & (attendance["出欠"] == "出席")]
                if not attendees.empty:
                    st.write("出席: " + ", ".join(attendees["名前"].tolist()))

            with st.form("attend"):
                status_dict = {}

                for _, p in players.iterrows():
                    name = p["名前"]

                    default = "未定"
                    if not attendance.empty:
                        row = attendance[(attendance["イベントID"] == event_id) & (attendance["名前"] == name)]
                        if not row.empty:
                            default = row.iloc[0]["出欠"]

                    status = st.radio(
                        name,
                        ["未定", "出席", "欠席"],
                        index=["未定","出席","欠席"].index(default),
                        horizontal=True,
                        key=f"{event_id}_{name}"
                    )

                    status_dict[name] = status

                if st.form_submit_button("保存"):
                    save_attendance_bulk(event_id, status_dict)
                    st.success("保存完了")
                    st.rerun()

# =========================
# 👤 選手管理
# =========================
st.divider()
st.subheader("👤 選手管理")
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
