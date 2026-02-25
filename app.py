from flask import Flask, request
import os
import json
import requests

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")

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

            members_raw = os.getenv("MEMBER_LINE_IDS", "")
            member_ids = [x.strip() for x in members_raw.split(",") if x.strip()]
            is_member = user_id in member_ids

            if text == "加入陪跑":
                reply_text = (
                    "🌿 理性陪跑研究室｜加入方式\n\n"
                    "目前為小規模會員測試。\n"
                    "請回覆我：你的付款後五碼（或你的暱稱），我會幫你開通。\n\n"
                    "（下一步我們再把這段改成你的收款連結）"
                )
            elif text == "今日陪跑":
                if not is_member:
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
                reply_text = "輸入「今日陪跑」或「加入陪跑」🌿"

            if reply_token:
                reply_message(reply_token, reply_text)

    except Exception as e:
        print("Webhook error:", e)

    return "OK"
