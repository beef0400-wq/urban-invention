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
    requests.post(url, headers=headers, data=json.dumps(payload))

@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.get_json(silent=True)
    if not body:
        return "OK"

    events = body.get("events", [])
    for event in events:
        if event.get("type") != "message":
            continue
        message = event.get("message", {})
        if message.get("type") != "text":
            continue

        text = message.get("text", "").strip()
        reply_token = event.get("replyToken")

        if text == "今日陪跑":
            reply_text = (
                "🌿 理性陪跑研究室\n\n"
                "📊 今日觀察\n"
                "先穩穩看趨勢，不追不壓。\n\n"
                "🧠 理性提醒\n"
                "數據只是方向，不是答案。\n\n"
                "✨ 今日陪跑靈感\n"
                "03 14 22 31 39\n\n"
                "我們只是一起練習用理性看待運氣。"
            )
        else:
            reply_text = "輸入「今日陪跑」我就會回你今天的陪跑內容 🌿"

        if reply_token:
            reply_message(reply_token, reply_text)

    return "OK"

@app.route("/")
def home():
    return "Bot is running."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
