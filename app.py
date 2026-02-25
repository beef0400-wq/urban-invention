# ====== 穩定 AI 數據陪跑版本 ======

from flask import Flask, request
import os
import json
import requests
import sqlite3
import random
from datetime import datetime, timezone, timedelta

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "1234")
DB_PATH = "members.db"
TZ_TW = timezone(timedelta(hours=8))

# ===== DB 初始化 =====
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
        CREATE TABLE IF NOT EXISTS daily_cache (
            pick_date TEXT PRIMARY KEY,
            numbers TEXT,
            hot_zone TEXT,
            top_hot TEXT
        )
    """)

    conn.commit()
    conn.close()

# ====== 取得歷史資料（官方API）======
def fetch_539_data():
    try:
        url = "https://api.taiwanlottery.com/TLCAPIWeB/Lottery/LottoResult"
        res = requests.get(url, timeout=10)
        data = res.json()

        results = []
        for item in data["Lotto539Res"]:
            nums = item["DrawNumberAppear"].split(",")
            nums = [int(n) for n in nums]
            results.append(nums)

        return results[:200]  # 取近200期
    except:
        return []

# ====== 計算模型 ======
def generate_today_pick():
    today = datetime.now(TZ_TW).date().isoformat()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT numbers, hot_zone, top_hot FROM daily_cache WHERE pick_date=?", (today,))
    row = cur.fetchone()

    if row:
        conn.close()
        return row

    draws = fetch_539_data()

    if not draws:
        return ("03 14 22 31 39", "資料暫時無法取得", "無")

    freq = {i:0 for i in range(1,40)}
    recent = draws[:30]

    for draw in draws:
        for n in draw:
            freq[n]+=1

    # 熱號前5
    top_hot = sorted(freq.items(), key=lambda x:x[1], reverse=True)[:5]
    top_hot_str = " ".join([f"{n:02d}" for n,_ in top_hot])

    # 熱區
    zone = {"1-13":0,"14-26":0,"27-39":0}
    for draw in recent:
        for n in draw:
            if n<=13: zone["1-13"]+=1
            elif n<=26: zone["14-26"]+=1
            else: zone["27-39"]+=1

    hot_zone = max(zone,key=zone.get)

    # 加權隨機
    weights = []
    for i in range(1,40):
        weights.append(freq[i]+1)

    numbers = random.choices(range(1,40), weights=weights, k=8)
    numbers = sorted(list(set(numbers)))[:5]

    while len(numbers)<5:
        numbers.append(random.randint(1,39))
        numbers = sorted(list(set(numbers)))

    numbers_str = " ".join([f"{n:02d}" for n in numbers[:5]])

    cur.execute("INSERT OR REPLACE INTO daily_cache VALUES (?,?,?,?)",
                (today,numbers_str,hot_zone,top_hot_str))
    conn.commit()
    conn.close()

    return (numbers_str, hot_zone, top_hot_str)

# ====== LINE Reply ======
def reply(reply_token,text):
    url="https://api.line.me/v2/bot/message/reply"
    headers={
        "Content-Type":"application/json",
        "Authorization":f"Bearer {CHANNEL_ACCESS_TOKEN}"
    }
    payload={
        "replyToken":reply_token,
        "messages":[{"type":"text","text":text}]
    }
    requests.post(url,headers=headers,data=json.dumps(payload))

# ====== 路由 ======
@app.route("/")
def home():
    return "Bot is running"

@app.route("/webhook",methods=["POST"])
def webhook():
    init_db()
    body=request.get_json()
    events=body.get("events",[])

    for event in events:
        if event["type"]!="message":
            continue

        text=event["message"]["text"].strip()
        reply_token=event["replyToken"]
        user_id=event["source"]["userId"]

        if text=="今日陪跑":
            numbers,hot_zone,top_hot=generate_today_pick()

            today_str=datetime.now(TZ_TW).strftime("%m/%d")

            msg=(
                f"🌿 理性陪跑研究室｜{today_str}\n\n"
                f"📊 近30期熱區：{hot_zone}\n"
                f"🔥 熱號觀察：{top_hot}\n\n"
                "🧠 理性提醒\n"
                "紀律比直覺重要，今天只做一次決定。\n\n"
                "✨ 今日陪跑建議\n"
                f"{numbers}\n\n"
                "（數據陪跑參考，非保證）"
            )

            reply(reply_token,msg)
        else:
            reply(reply_token,"輸入：今日陪跑")

    return "OK"
