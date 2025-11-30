# GPU リモートサーバー予約アプリ（4090reservation）

このリポジトリは、
**Streamlit を使った GPU 予約管理アプリ** と
**GitHub Actions による自動予約スクリプト（auto_reserve.py）** をまとめたプロジェクトです。

アプリは **PostgreSQL（Supabase）** をバックエンド DB として利用し、
Web UI と自動バッチ処理のどちらからも予約データを扱える構成になっています。

---

## 📌 概要

### ✨ Streamlit アプリ

* ブラウザから GPU 予約を登録・管理
* 用途・必要メモリ・開始/終了時間を指定して予約
* 30分粒度（変更可）で全ユーザーのメモリ合計を集計
* 上限メモリを超える時間帯を可視化
* 現在のメモリ使用量をリアルタイム表示

### ⚡ 自動予約スクリプト（auto_reserve.py）

* GitHub Actions 上で定期的に実行
* Streamlit のスリープ状態に依存せずバックエンド処理が実行可能
* Supabase(PostgreSQL) に直接接続し、定期予約処理を実施

---

## 🗂 ディレクトリ構造

```
4090reservation/
│
├── app.py                # Streamlit アプリ本体（PostgreSQL を利用）
├── auto_reserve.py       # GitHub Actions で定期実行される予約処理スクリプト
├── db_core.py            # PostgreSQL への接続と共通関数
├── requirements.txt      # 使用ライブラリ
│
└── .github/
    └── workflows/
        └── auto-reserve.yml   # GitHub Actions のスケジュールワークフロー
```

---

## 🚀 Streamlit アプリの実行方法

### 1. 依存パッケージのインストール

```
pip install -r requirements.txt
```

### 2. 必要な環境変数を `.env` に記載

```
DB_USER=xxxxxxxx
DB_PASSWORD=xxxxxxxx
DB_HOST=xxxxxxxx
DB_PORT=5432
DB_NAME=postgres
```

### 3. アプリの起動

```
streamlit run app.py
```

---

## 🗄 データベース構成（PostgreSQL / Supabase）

本アプリは全データを **PostgreSQL** に保存します。

Streamlit アプリも GitHub Actions も、
同じ DB に接続することで **UI とバックグラウンド処理が完全に同期**します。

---

## ⚙️ GitHub Actions（定期実行）

`.github/workflows/auto-reserve.yml` にて自動実行を設定しています。

### 📅 スケジュール例（3時間ごと）

```
schedule:
  - cron: "0 */3 * * *"
```

### 🧪 手動実行も可能

GitHub Actions → Auto reserve GPU → “Run workflow”

---

## 🔐 必須の GitHub Secrets

リポジトリ → Settings → Secrets → Actions に以下を追加：

| Name          | 内容                |
| ------------- | ----------------- |
| `DB_USER`     | Supabase user     |
| `DB_PASSWORD` | Supabase password |
| `DB_HOST`     | Supabase host     |
| `DB_PORT`     | `5432`            |
| `DB_NAME`     | 通常 `postgres`     |

### ワークフローでの渡し方

```yaml
env:
  user: ${{ secrets.DB_USER }}
  password: ${{ secrets.DB_PASSWORD }}
  host: ${{ secrets.DB_HOST }}
  port: ${{ secrets.DB_PORT }}
  dbname: ${{ secrets.DB_NAME }}
```

---

## 🧩 auto_reserve.py の役割

* PostgreSQL に接続し、必要な予約処理を自動実行
* Streamlit Cloud がスリープしていても動作（GitHub Actions 上で動くため）
* 定期的な予約やスケジュール確認などに利用可能

---

## 📦 主な使用ライブラリ

`requirements.txt` に記載：

* streamlit
* pandas
* psycopg2
* python-dateutil
* その他アプリで利用するツール

---

## 📄 ライセンス

MIT License
