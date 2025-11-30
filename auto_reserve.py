# auto_reserve.py
from datetime import datetime, time, timedelta
from db_core import TZ, init_db, add_reservation

def main():
    # 念のためテーブルを作成
    init_db()

    today = datetime.now(TZ).date()

    # 例: 今日の 09:00〜18:00 を 8GB で予約
    start_dt = datetime.combine(today, time(9, 0), tzinfo=TZ)
    end_dt = datetime.combine(today, time(18, 0), tzinfo=TZ)

    add_reservation(
        name="自動予約ユーザ",
        purpose="定期ジョブ",
        start_dt=start_dt,
        end_dt=end_dt,
        memory_gb=0.0,
    )

    print(f"[auto_reserve] {start_dt} - {end_dt} を予約しました。")


if __name__ == "__main__":
    main()
