# db_core.py
from datetime import datetime
from zoneinfo import ZoneInfo
import os

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from dotenv import load_dotenv

# タイムゾーン
TZ = ZoneInfo("Asia/Tokyo")

# .env (ローカル) または 環境変数 (GitHub Actions の secrets) から読み込み
# .env には Supabase の「Connect → ORMs → SQLAlchemy → Session pooler」で表示される
# user/password/host/port/dbname をそのまま書く
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
    raise RuntimeError("DB接続情報(user/password/host/port/dbname)が不足しています。")

# Supabase が例示している SQLAlchemy 用の形式
DATABASE_URL = (
    f"postgresql+psycopg2://{USER}:{PASSWORD}@{HOST}:{PORT}/{DBNAME}?sslmode=require"
)

# Session Pooler を使うので、SQLAlchemy 側のプーリングは NullPool にしておく
engine = create_engine(DATABASE_URL, poolclass=NullPool)


# ---------------- DB helpers ---------------- #

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


def add_reservation(
    name: str,
    purpose: str,
    start_dt: datetime,
    end_dt: datetime,
    memory_gb: float,
):
    """予約を1件追加"""
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
    """id を指定して予約を削除"""
    sql = "DELETE FROM reservations WHERE id = :id"
    with engine.begin() as conn:
        conn.execute(text(sql), {"id": res_id})


def fetch_reservations(
    start_range: datetime | None = None,
    end_range: datetime | None = None,
) -> pd.DataFrame:
    """
    指定期間にかぶる予約を PostgreSQL から取得。
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