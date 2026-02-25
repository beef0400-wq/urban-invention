from flask import Flask, request
import os
import json
import requests
import sqlite3
from datetime import datetime, timezone, timedelta

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "1234")
DB_PATH = "members.db"

TZ_TW = timezone(timedelta(hours=8))


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS members (
            user_id TEXT PRIMARY KEY,
            expires_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pending_accounts (
            game_account TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def reply_message(reply_token, text):
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
    }
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}],
    }
    requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)


# ========================
# 會員相關
# ========================

def set_expiry_plus_days(user_id: str, days: int = 30):
    now_tw = datetime.now(TZ_TW)
    target_date = (now_tw + timedelta(days=days)).date()
    dt_tw = datetime.strptime(target_date.strftime("%Y-%m-%d"), "%Y-%m-%d").replace(
        hour=23, minute=59, second=59, tzinfo=TZ_TW
    )

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO members (user_id, expires_at)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET expires_at=excluded.expires_at
    """, (user_id, dt_tw.isoformat()))
    conn.commit()
    conn.close()
    return dt_tw


def get_expiry(user_id: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT expires_at FROM members WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def is_member(user_id: str) -> bool:
    exp = get_expiry(user_id)
    if not exp:
        return False
    expires_at = datetime.fromisoformat(exp)
    now_tw = datetime.now(expires_at.tzinfo)
    return expires_at > now_tw


# ========================
# 待確認帳號
# ========================

def save_pending_account(game_account: str, user_id: str):
    created_at = datetime.now(TZ_TW).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO pending_accounts (game_account, user_id, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT(game_account)
        DO UPDATE SET user_id=excluded.user_id, created_at=excluded.created_at
    """, (game_account, user_id, created_at))
    conn.commit()
    conn.close()


def pop_pending_user_id(game_account: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM pending_accounts WHERE game_account = ?", (game_account,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return None

    user_id = row[0]
    cur.execute("DELETE FROM pending_accounts WHERE game_account = ?", (game_account,))
    conn.commit()
    conn.close()
    return user_id


def get_latest_pending(limit=50):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT game_account, user_id, created_at
        FROM pending_accounts
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows


# ========================
# 路由
# ========================

@app.route("/")
def home():
    return "Bot is running."


@app.route("/webhook", methods=["POST"])
def webhook():
    init_db()
    body = request.get_json(silent=True) or {}
    events = body.get("events", [])

    try:
        for event in events:
            if event.get("type") != "message":
                continue

            message = event.get("message", {})
            if message.get("type") != "text":
                continue

            text = (message.get("text") or "").strip()
            reply_token = event.get("replyToken")
            user_id = event.get("source", {}).get("userId", "")

            # -----------------------
            # 使用者：提交遊戲帳號
            # -----------------------
            if text.startswith("遊戲帳號 "):
                parts = text.split(maxsplit=1)
                if len(parts) != 2:
                    reply_text = "格式：遊戲帳號 XXXXX"
                else:
                    game_account = parts[1].strip()
                    save_pending_account(game_account, user_id)
                    reply_text = (
                        "✅ 已收到你的遊戲帳號\n\n"
                        f"帳號：{game_account}\n\n"
                        "請等待管理員確認。"
                    )
                reply_message(reply_token, reply_text)
                continue

            # -----------------------
            # 管理員：列出最近 50 筆
            # -----------------------
            if text.startswith("待確認 "):
                parts = text.split()
                if len(parts) != 2 or parts[1] != ADMIN_SECRET:
                    reply_message(reply_token, "管理密碼錯誤。")
                    continue

                rows = get_latest_pending(50)

                if not rows:
                    reply_message(reply_token, "目前沒有待確認帳號。")
                    continue

                msg = "📋 最近待確認帳號（最多50筆）\n\n"
                for r in rows:
                    msg += (
                        f"帳號：{r[0]}\n"
                        f"userId：{r[1]}\n"
                        f"時間：{r[2][:16]}\n"
                        "-----------------\n"
                    )

                reply_message(reply_token, msg[:5000])  # LINE 單則上限
                continue

            # -----------------------
            # 管理員：確認開通
            # -----------------------
            if text.startswith("確認 "):
                parts = text.split()
                if len(parts) != 3:
                    reply_message(reply_token, "格式：確認 <遊戲帳號> <管理密碼>")
                    continue

                _, game_account, secret = parts

                if secret != ADMIN_SECRET:
                    reply_message(reply_token, "管理密碼錯誤。")
                    continue

                target_user_id = pop_pending_user_id(game_account)
                if not target_user_id:
                    reply_message(reply_token, "找不到該遊戲帳號。")
                    continue

                dt_tw = set_expiry_plus_days(target_user_id, 30)

                reply_message(
                    reply_token,
                    f"✅ 已開通\n帳號：{game_account}\n到期：{dt_tw.strftime('%Y-%m-%d %H:%M')}"
                )
                continue

            # -----------------------
            # 使用者：查到期
            # -----------------------
            if text == "我的到期日":
                exp = get_expiry(user_id)
                if not exp:
                    reply_message(reply_token, "你目前尚未開通。")
                else:
                    dt = datetime.fromisoformat(exp)
                    reply_message(reply_token, "⏳ 到期時間：\n" + dt.strftime("%Y-%m-%d %H:%M"))
                continue

            # -----------------------
            # 今日陪跑
            # -----------------------
            if text == "今日陪跑":
                if not is_member(user_id):
                    reply_message(reply_token, "請先輸入：遊戲帳號 XXXXX")
                else:
                    reply_message(
                        reply_token,
                        "🌿 今日陪跑內容\n\n03 14 22 31 39\n07 11 18 26 33\n02 09 21 28 37"
                    )
                continue

            reply_message(reply_token, "指令：\n1️⃣ 遊戲帳號 XXXXX\n2️⃣ 今日陪跑\n3️⃣ 我的到期日")

    except Exception as e:
        print("Webhook error:", e)

    return "OK"
