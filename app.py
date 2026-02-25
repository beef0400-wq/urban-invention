from flask import Flask, request
import os
import json
import requests
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "1234")  # 你等等會改成自己的密碼

DB_PATH = "members.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS members (
            user_id TEXT PRIMARY KEY,
            expires_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def set_member(user_id: str, days: int):
    expires_at = (datetime.utcnow() + timedelta(days=days)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO members (user_id, expires_at)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET expires_at=excluded.expires_at
    """, (user_id, expires_at))
    conn.commit()
    conn.close()
    return expires_at

def is_member(user_id: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT expires_at FROM members WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return False
    expires_at = datetime.fromisoformat(row[0])
    return expires_at > datetime.utcnow()

def get_expiry(user_id: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT expires_at FROM members WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return row[0]

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
            print("LINE userId:", user_id)

            # 會員指令：開通 <userId> <天數> <密碼>
            # 例：開通 Uxxxxxxxx 30 你的密碼
            if text.startswith("開通 "):
                parts = text.split()
                if len(parts) != 4:
                    reply_text = "格式：開通 <userId> <天數> <管理密碼>\n例：開通 Uxxxx 30 1234"
                else:
                    _, target_id, days_str, secret = parts
                    if secret != ADMIN_SECRET:
                        reply_text = "管理密碼錯誤。"
                    else:
                        try:
                            days = int(days_str)
                            expires = set_member(target_id, days)
                            reply_text = f"✅ 已開通：{target_id}\n到期：{expires}（UTC）"
                        except:
                            reply_text = "天數請填數字，例如 30"
                reply_message(reply_token, reply_text)
                continue

            # 使用者指令
            if text == "加入陪跑":
                reply_text = (
                    "🌿 理性陪跑研究室｜加入方式\n\n"
                    "請先完成付款後，回覆我：『付款後五碼』\n"
                    "我會幫你開通會員。\n\n"
                    "（之後我們可以再串金流自動開通）"
                )

            elif text == "我的到期日":
                exp = get_expiry(user_id)
                if not exp:
                    reply_text = "你目前不是會員。輸入「加入陪跑」了解加入方式。"
                else:
                    reply_text = f"⏳ 你的到期時間：\n{exp}（UTC）"

            elif text == "今日陪跑":
                if not is_member(user_id):
                    reply_text = (
                        "🌿 今日陪跑屬於會員內容\n\n"
                        "想加入『理性陪跑研究室』請輸入：加入陪跑"
                    )
                else:
                    reply_text = (
                        "🌿 理性陪跑研究室（會員版）\n\n"
                        "📊 今日觀察\n"
                        "先穩穩看趨勢，不追不壓。\n\n"
                        "🧠 理性提醒\n"
                        "數據只是方向，不是答案。\n\n"
                        "✨ 今日陪跑靈感\n"
                        "03 14 22 31 39\n"
                        "07 11 18 26 33\n"
                        "02 09 21 28 37\n\n"
                        "我們只是一起練習用理性看待運氣。"
                    )
            else:
                reply_text = "輸入：今日陪跑 / 加入陪跑 / 我的到期日"

            reply_message(reply_token, reply_text)

    except Exception as e:
        print("Webhook error:", e)

    return "OK"
