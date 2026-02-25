from flask import Flask, request
import os
import json
import requests
import sqlite3

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "1234")  # 等下你會在 Render 改成自己的密碼
DB_PATH = "members.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS members (
            user_id TEXT PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()

def add_member(user_id: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO members (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def remove_member(user_id: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM members WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def is_member(user_id: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM members WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row is not None

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

            # 管理指令：加入會員 / 移除會員
            # 格式：加入會員 Uxxxx 密碼
            if text.startswith("加入會員 "):
                parts = text.split()
                if len(parts) != 3:
                    reply_text = "格式：加入會員 <userId> <管理密碼>"
                else:
                    _, target_id, secret = parts
                    if secret != ADMIN_SECRET:
                        reply_text = "管理密碼錯誤。"
                    else:
                        add_member(target_id)
                        reply_text = f"✅ 已加入會員：{target_id}"
                reply_message(reply_token, reply_text)
                continue

            if text.startswith("移除會員 "):
                parts = text.split()
                if len(parts) != 3:
                    reply_text = "格式：移除會員 <userId> <管理密碼>"
                else:
                    _, target_id, secret = parts
                    if secret != ADMIN_SECRET:
                        reply_text = "管理密碼錯誤。"
                    else:
                        remove_member(target_id)
                        reply_text = f"🗑 已移除會員：{target_id}"
                reply_message(reply_token, reply_text)
                continue

            # 使用者指令
            if text == "加入陪跑":
                reply_text = (
                    "🌿 理性陪跑研究室｜加入方式\n\n"
                    "請完成付款後，回覆我：『付款後五碼』\n"
                    "我會幫你加入會員名單。\n\n"
                    "（V1 版本先採人工加入）"
                )

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
                reply_text = "輸入：今日陪跑 / 加入陪跑"

            reply_message(reply_token, reply_text)

    except Exception as e:
        print("Webhook error:", e)

    return "OK"
