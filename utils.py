import streamlit as st
import gspread
import pandas as pd
import hashlib

SPREADSHEET_ID = "17s98-7sAmcom90WjoHcwrPuz8IgKGFSI1c8quT4iteg"
PLAYER_SHEET  = "選手名簿"
EVENT_SHEET   = "イベント"
ATTEND_SHEET  = "出席管理"
LOG_SHEET     = "変更ログ"
STAFF_SHEET   = "運営者名簿"
WEEKDAYS = ["月","火","水","木","金","土","日"]
GRADES   = ["1年","2年","3年","4年","5年","6年"]
LOG_COLS = ["日時", "種別", "イベント情報", "変更項目", "変更前", "変更後"]
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def check_password():
    correct_hash = hashlib.sha256(
        st.secrets.get("APP_PASSWORD", "").encode()
    ).hexdigest()
    if st.session_state.get("authenticated"):
        return True
    st.markdown("""
    <div style="background-color:rgba(128,128,128,0.15); border-radius:8px; padding:6px 16px; display:inline-block;">
    <h3 style="margin:0;">⚾ 少年野球チーム管理アプリ</h3>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("")
    pw = st.text_input("パスワードを入力してください", type="password")
    if st.button("ログイン"):
        if hashlib.sha256(pw.encode()).hexdigest() == correct_hash:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("パスワードが違います")
    return False


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


def load_change_log():
    vals = get_spreadsheet().worksheet(LOG_SHEET).get_all_values()
    if not vals:
        return pd.DataFrame(columns=LOG_COLS + ["日時dt"])
    rows = vals[1:] if vals[0][0] == "日時" else vals
    df = pd.DataFrame(rows, columns=LOG_COLS[:len(vals[0])] if rows else LOG_COLS)
    if "日時" in df.columns:
        df["日時dt"] = pd.to_datetime(df["日時"], errors="coerce")
    return df


def write_change_log(entries):
    if not entries:
        return
    try:
        ws = get_spreadsheet().worksheet(LOG_SHEET)
        vals = ws.get_all_values()
        if not vals or vals[0][0] != "日時":
            ws.insert_row(LOG_COLS, 1)
        ws.append_rows(entries)
    except Exception as e:
        st.warning(f"変更ログ書き込みエラー: {e}")


def now_jst():
    return (pd.Timestamp.now() + pd.Timedelta(hours=9)).strftime("%Y-%m-%d %H:%M")


ATTEND_COLS = ["イベントID", "名前", "出欠", "配車", "種別", "車出し", "役割"]


def load_staff():
    try:
        df = pd.DataFrame(get_spreadsheet().worksheet(STAFF_SHEET).get_all_records())
        return df
    except Exception:
        return pd.DataFrame(columns=["名前", "役割"])


def save_attendance_bulk(event_id, status_dict, haisha_dict=None, event_info="",
                         member_type_dict=None, sharsha_dict=None, role_dict=None):
    """
    status_dict      : {name: 出欠}
    haisha_dict      : {name: car_number}
    member_type_dict : {name: "選手" or "運営"}
    sharsha_dict     : {name: True/False}  車出し可否
    role_dict        : {name: role_str}    役割（試合時）
    """
    ws = get_ws(ATTEND_SHEET)
    load_attendance.clear()
    df = load_attendance()

    old_status = {}
    if not df.empty:
        ev_df = df[df["イベントID"] == event_id]
        for _, r in ev_df.iterrows():
            old_status[r["名前"]] = r["出欠"]

    # 他イベント分を残して書き直す
    if not df.empty:
        df = df.drop_duplicates(subset=["イベントID", "名前"], keep="last")
        df = df[df["イベントID"] != event_id]
        ws.clear()
        ws.append_row(ATTEND_COLS)
        if not df.empty:
            for c in ATTEND_COLS:
                if c not in df.columns:
                    df[c] = ""
            ws.append_rows(df[ATTEND_COLS].values.tolist())

    rows = [
        [int(event_id), name, status,
         (haisha_dict      or {}).get(name, ""),
         (member_type_dict or {}).get(name, "選手"),
         (sharsha_dict     or {}).get(name, False),
         (role_dict        or {}).get(name, "")]
        for name, status in status_dict.items()
    ]
    ws.append_rows(rows)
    load_attendance.clear()

    ns = now_jst()
    log_entries = []
    for name, new_st in status_dict.items():
        old_st = old_status.get(name, "未定")
        if old_st != new_st:
            log_entries.append([ns, "出欠", event_info, name, old_st, new_st])
    write_change_log(log_entries)


def write_row_by_header(ws, row_index, data_dict):
    """ヘッダー行の列名を基準に指定行へ書き込む（列順不問）"""
    headers = ws.row_values(1)
    row_data = [str(data_dict.get(h, "")) for h in headers]
    end_col = chr(ord("A") + len(headers) - 1)
    ws.update(f"A{row_index}:{end_col}{row_index}", [row_data])


def append_row_by_header(ws, data_dict):
    """ヘッダー行の列名を基準に末尾へ追記する（列順不問）"""
    headers = ws.row_values(1)
    row_data = [str(data_dict.get(h, "")) for h in headers]
    ws.append_row(row_data)


def google_calendar_url(title, dt, start_str, end_str, location, details=""):
    from urllib.parse import quote
    try:
        sh, sm = [int(x) for x in start_str.split(":")]
        eh, em = [int(x) for x in end_str.split(":")]
    except:
        return ""
    start = f"{dt.strftime('%Y%m%d')}T{sh:02d}{sm:02d}00"
    end   = f"{dt.strftime('%Y%m%d')}T{eh:02d}{em:02d}00"
    url = (f"https://calendar.google.com/calendar/render?action=TEMPLATE"
           f"&text={quote(title)}&dates={start}/{end}&location={quote(location)}")
    if details:
        url += f"&details={quote(details)}"
    return url
