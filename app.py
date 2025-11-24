from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from dotenv import load_dotenv


# ---------------- 認証 ---------------- #

AUTH_PASSWORD = os.environ.get("APP_PASSWORD", "4090")


def check_password() -> bool:
    import streamlit as st

    def _pw_entered():
        if st.session_state.get("app_password", "") == AUTH_PASSWORD:
            st.session_state["password_ok"] = True
        else:
            st.session_state["password_ok"] = False

    if st.session_state.get("password_ok"):
        return True

    st.markdown("### 🔒 パスワードを入力してください")
    st.text_input("パスワード", type="password", key="app_password", on_change=_pw_entered)
    if st.session_state.get("password_ok") is False:
        st.error("パスワードが違います。")
    return False


# ---------------- 設定 ---------------- #

TZ = ZoneInfo("Asia/Tokyo")

# ---------- DB 接続設定（Supabase Session Pooler / SQLAlchemy） ----------

# .env の読み込み
# .env には Supabase の「Connect → ORMs → SQLAlchemy → Method: Session pooler」で
# 表示されている値をそのまま書いてください。
#
# 例:
# user=postgres.pvemwsmtudnxgcvzphoo
# password=あなたのDBパスワード
# host=aws-1-ap-south-1.pooler.supabase.com
# port=5432
# dbname=postgres
load_dotenv()

USER = os.getenv("user")
PASSWORD = os.getenv("password")
HOST = os.getenv("host")
PORT = os.getenv("port", "5432")
DBNAME = os.getenv("dbname", "postgres")

if not all([USER, PASSWORD, HOST, PORT, DBNAME]):
    raise RuntimeError("DB接続情報(.env の user/password/host/port/dbname)が不足しています。")

# Supabase が例示している SQLAlchemy 用の形式
DATABASE_URL = (
    f"postgresql+psycopg2://{USER}:{PASSWORD}@{HOST}:{PORT}/{DBNAME}?sslmode=require"
)

# Session Pooler を使うので、SQLAlchemy 側のプーリングは NullPool にしておく
engine = create_engine(DATABASE_URL, poolclass=NullPool)


# ---------------- DB helpers（PostgreSQL版） ---------------- #

def init_db():
    """PostgreSQL 上にテーブルがなければ作成"""
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS reservations (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        purpose TEXT NOT NULL,
        start_dt TIMESTAMPTZ NOT NULL,
        end_dt TIMESTAMPTZ NOT NULL,
        memory_gb DOUBLE PRECISION NOT NULL,
        created_at TIMESTAMPTZ NOT NULL
    );
    """
    with engine.begin() as conn:
        conn.execute(text(create_table_sql))


def add_reservation(name: str, purpose: str, start_dt: datetime, end_dt: datetime, memory_gb: float):
    sql = """
    INSERT INTO reservations (name, purpose, start_dt, end_dt, memory_gb, created_at)
    VALUES (:name, :purpose, :start_dt, :end_dt, :memory_gb, :created_at)
    """
    with engine.begin() as conn:
        conn.execute(
            text(sql),
            {
                "name": name,
                "purpose": purpose,
                "start_dt": start_dt.astimezone(TZ),
                "end_dt": end_dt.astimezone(TZ),
                "memory_gb": float(memory_gb),
                "created_at": datetime.now(tz=TZ),
            },
        )


def delete_reservation(res_id: int):
    sql = "DELETE FROM reservations WHERE id = :id"
    with engine.begin() as conn:
        conn.execute(text(sql), {"id": res_id})


def fetch_reservations(
    start_range: datetime | None = None,
    end_range: datetime | None = None,
) -> pd.DataFrame:
    """
    指定期間にかぶる予約をPostgreSQLから取得。
    start_range/end_range は tz-aware datetime を期待。
    """
    base_sql = "SELECT * FROM reservations"
    conditions = []
    params: dict[str, object] = {}

    if start_range is not None:
        conditions.append("end_dt > :start_range")
        params["start_range"] = start_range.astimezone(TZ)
    if end_range is not None:
        conditions.append("start_dt < :end_range")
        params["end_range"] = end_range.astimezone(TZ)

    if conditions:
        base_sql += " WHERE " + " AND ".join(conditions)

    base_sql += " ORDER BY start_dt, end_dt"

    with engine.connect() as conn:
        df = pd.read_sql(text(base_sql), conn, params=params)

    if df.empty:
        return df

    # 念のため Asia/Tokyo に揃える（すでに tz-aware のはずだが保険）
    for col in ["start_dt", "end_dt", "created_at"]:
        df[col] = pd.to_datetime(df[col]).dt.tz_convert(TZ)

    return df


# ----------------- Logic helpers ----------------- #

def time_bins_for_day(day: date, step_minutes: int = 30) -> list[tuple[datetime, datetime]]:
    start = datetime.combine(day, time(0, 0), tzinfo=TZ)
    bins: list[tuple[datetime, datetime]] = []
    cur = start
    while cur < start + timedelta(days=1):
        nxt = cur + timedelta(minutes=step_minutes)
        bins.append((cur, nxt))
        cur = nxt
    return bins


def total_memory_per_bin(res_df: pd.DataFrame, bins: list[tuple[datetime, datetime]]) -> pd.DataFrame:
    totals: list[dict] = []

    # 予約が一件もない場合は比較自体を行わず、すべて0で返す
    if res_df is None or res_df.empty:
        for b_start, b_end in bins:
            totals.append(
                {
                    "time_range": f"{b_start.strftime('%H:%M')}–{b_end.strftime('%H:%M')}",
                    "start": b_start,
                    "end": b_end,
                    "total_gb": 0.0,
                }
            )
        return pd.DataFrame(totals)

    for b_start, b_end in bins:
        mask = (res_df["start_dt"] < b_end) & (res_df["end_dt"] > b_start)
        total = res_df.loc[mask, "memory_gb"].sum()
        totals.append(
            {
                "time_range": f"{b_start.strftime('%H:%M')}–{b_end.strftime('%H:%M')}",
                    "start": b_start,
                    "end": b_end,
                    "total_gb": float(total),
            }
        )
    return pd.DataFrame(totals)


def current_total_memory(res_df: pd.DataFrame, now_dt: datetime) -> float:
    if res_df.empty:
        return 0.0
    mask = (res_df["start_dt"] <= now_dt) & (res_df["end_dt"] > now_dt)
    return float(res_df.loc[mask, "memory_gb"].sum())


# ----------------- UI ----------------- #

st.set_page_config(page_title="GPU予約アプリ", page_icon="🖥️", layout="wide")

if not check_password():
    st.stop()

st.title("GPU4090予約アプリ")

init_db()

with st.sidebar:
    st.header("設定")
    capacity = st.number_input(
        "GPUの合計メモリ容量 (GB)",
        min_value=1.0,
        max_value=1024.0,
        value=24.0,
        step=1.0,
        help="例: 24GB GPU",
    )
    step_minutes = st.selectbox("集計の時間粒度（分）", options=[15, 30, 60], index=1)
    st.divider()
    st.markdown("**管理**")
    if st.button("全予約をエクスポート (CSV)"):
        df_all = fetch_reservations()
        if df_all.empty:
            st.info("予約はありません。")
        else:
            st.download_button(
                "ダウンロード",
                data=df_all.to_csv(index=False).encode("utf-8-sig"),
                file_name="reservations_export.csv",
                mime="text/csv",
            )

tab_reserve, tab_view = st.tabs(["📝 予約する", "📊 状況を確認"])


with tab_reserve:
    st.subheader("予約フォーム")

    now_tz = datetime.now(TZ)
    # デフォルト値を session_state に保持して、再実行時も維持
    if "reserve_date" not in st.session_state:
        st.session_state.reserve_date = now_tz.date()
    if "reserve_start_t" not in st.session_state:
        st.session_state.reserve_start_t = (now_tz + timedelta(minutes=5)).time()
    if "reserve_end_t" not in st.session_state:
        st.session_state.reserve_end_t = (now_tz + timedelta(hours=1)).time()

    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input(
            "利用者の名前",
            placeholder="山田 太郎",
            max_chars=50,
            key="reserve_name",
        )
        purpose = st.text_input(
            "用途（例：学習ジョブ、推論、検証など）",
            placeholder="学習ジョブ",
            max_chars=100,
            key="reserve_purpose",
        )
        memory_gb = st.number_input(
            "必要メモリ量 (GB)",
            min_value=0.5,
            max_value=1024.0,
            value=8.0,
            step=0.5,
            key="reserve_mem",
        )
    with col2:
        d = st.date_input("日付", key="reserve_date")
        start_t = st.time_input("開始時刻", key="reserve_start_t")
        end_t = st.time_input("終了時刻", key="reserve_end_t")

    submit = st.button("予約を登録", key="reserve_submit")
    if submit:
        try:
            if not st.session_state.reserve_name or not st.session_state.reserve_purpose:
                st.error("名前と用途を入力してください。")
            else:
                start_dt = datetime.combine(
                    st.session_state.reserve_date,
                    st.session_state.reserve_start_t,
                    tzinfo=TZ,
                )
                end_dt = datetime.combine(
                    st.session_state.reserve_date,
                    st.session_state.reserve_end_t,
                    tzinfo=TZ,
                )
                if end_dt <= start_dt:
                    st.error("終了時刻は開始時刻より後にしてください。")
                else:
                    add_reservation(
                        st.session_state.reserve_name,
                        st.session_state.reserve_purpose,
                        start_dt,
                        end_dt,
                        float(st.session_state.reserve_mem),
                    )
                    st.success("予約を登録しました。")
        except Exception as e:
            st.error(f"入力の処理中にエラーが発生しました: {e}")


with tab_view:
    st.subheader("本日の状況")
    selected_day = st.date_input(
        "表示する日", value=datetime.now(TZ).date(), key="view_day"
    )
    bins = time_bins_for_day(selected_day, step_minutes=step_minutes)

    # 当日分の予約を取得
    day_start = datetime.combine(selected_day, time(0, 0), tzinfo=TZ)
    day_end = day_start + timedelta(days=1)
    df_day = fetch_reservations(day_start, day_end)

    # 現在時刻の合計使用量
    now_tz = datetime.now(TZ)
    now_total = current_total_memory(df_day, now_tz)
    over_now = now_total > capacity
    st.metric(
        label="現在の合計メモリ使用量 (GB)",
        value=f"{now_total:.1f}",
        delta="超過中" if over_now else "OK",
    )

    # 時間帯ごとの合計メモリ
    df_bins = total_memory_per_bin(df_day, bins)
    df_bins_display = df_bins[["time_range", "total_gb"]].rename(
        columns={"time_range": "時間帯", "total_gb": "合計メモリ(GB)"}
    )

    def highlight_exceeded(row):
        if row["合計メモリ(GB)"] > capacity:
            # 超過している行をピンクに
            return ["background-color: #ffd6e7", "background-color: #ffd6e7"]
        else:
            return ["", ""]

    styler = (
        df_bins_display.style.apply(highlight_exceeded, axis=1)
        .format({"合計メモリ(GB)": "{:.1f}"})
        .hide(axis="index")
    )
    st.dataframe(styler, use_container_width=True)

    # どこか1つでも超過していたら警告
    if not df_bins.empty and (df_bins["total_gb"] > capacity).any():
        st.error("⚠️ 一部の時間帯で合計メモリが上限を超えています。")

    st.divider()
    st.subheader("予約一覧（当日分）")
    if df_day.empty:
        st.info("当日の予約はありません。")
    else:
        for i, row in df_day.iterrows():
            over_flag = any(
                (row["start_dt"] < e)
                and (row["end_dt"] > s)
                and (total > capacity)
                for s, e, total in zip(
                    df_bins["start"], df_bins["end"], df_bins["total_gb"]
                )
            )
            badge = "❌超過帯あり" if over_flag else "✅"
            label = (
                f'{badge} {row["start_dt"].strftime("%H:%M")} - '
                f'{row["end_dt"].strftime("%H:%M")} | '
                f'{row["name"]} | {row["purpose"]} | {row["memory_gb"]:.1f}GB'
            )
            with st.expander(label):
                st.write(f"ID: {row['id']}")
                st.write(f"作成時刻: {row['created_at']}")
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("この予約を削除", key=f"del_{row['id']}"):
                        delete_reservation(int(row["id"]))
                        st.success("削除しました。ページを再読み込みしてください。")
                with col_b:
                    st.write("（※削除は即時反映されますが、表示は手動で更新してください）")

    st.caption("※ バックエンドには Supabase PostgreSQL（Session Pooler）を使用しています。")
