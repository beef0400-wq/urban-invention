from flask import Flask, request
import os
import json
import requests
import sqlite3
from datetime import datetime, timezone, timedelta, date
import random

# 這個套件會去抓台灣彩券歷史資料
# pip: taiwanlottery
from taiwanlottery import DailyCash  # 今彩539

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "1234")
DB_PATH = "members.db"
TZ_TW = timezone(timedelta(hours=8))

# ==========
# DB
# ==========

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

    # 儲存歷史開獎（避免每次都去抓）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lotto_draws_539 (
            draw_date TEXT NOT NULL,
            n1 INTEGER NOT NULL,
            n2 INTEGER NOT NULL,
            n3 INTEGER NOT NULL,
            n4 INTEGER NOT NULL,
            n5 INTEGER NOT NULL,
            PRIMARY KEY (draw_date)
        )
    """)

    # 每日陪跑快取（同一天不要每次都重算）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_pick_539 (
            pick_date TEXT PRIMARY KEY,
            numbers TEXT NOT NULL,
            hot_zone TEXT NOT NULL,
            top_hot_numbers TEXT NOT NULL,
            model_note TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# ==========
# LINE reply
# ==========

def reply_message(reply_token, text):
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
    }
    payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": text}]}
    requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)


# ==========
# 會員系統
# ==========

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


# ==========
# 539 數據：抓資料 -> 入庫 -> 統計 -> 產生今日一組
# ==========

def upsert_draws(draw_rows):
    """
    draw_rows: list of dict {draw_date:'YYYY-MM-DD', nums:[...5 ints...]}
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for r in draw_rows:
        d = r["draw_date"]
        n = r["nums"]
        cur.execute("""
            INSERT OR REPLACE INTO lotto_draws_539 (draw_date, n1, n2, n3, n4, n5)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (d, n[0], n[1], n[2], n[3], n[4]))
    conn.commit()
    conn.close()


def load_draws(limit=240):
    """
    讀 DB 中最近 limit 期（用日期排序）
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT draw_date, n1, n2, n3, n4, n5
        FROM lotto_draws_539
        ORDER BY draw_date DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows  # newest -> older


def fetch_recent_draws_from_source(months_back=8):
    """
    用 taiwanlottery 套件抓近幾個月資料（今彩539）
    """
    dc = DailyCash()
    # 套件支援抓幾個月前（不同版本可能命名略差）
    # 這裡用最保守做法：逐月抓，失敗就略過
    results = []
    now_tw = datetime.now(TZ_TW)
    y = now_tw.year
    m = now_tw.month

    # 往回抓 months_back 個月（含本月）
    for i in range(months_back):
        yy = y
        mm = m - i
        while mm <= 0:
            mm += 12
            yy -= 1

        try:
            # 多數版本是 dc.month(year, month) or dc.fetch(year, month)
            # 這裡做兼容：嘗試不同方法
            if hasattr(dc, "month"):
                data = dc.month(yy, mm)
            elif hasattr(dc, "fetch"):
                data = dc.fetch(yy, mm)
            else:
                data = dc.get(yy, mm)

            # data 常見是 list[dict]，包含日期與號碼
            for item in data:
                # 兼容欄位：date/draw_date、numbers/num
                d = item.get("date") or item.get("draw_date") or item.get("開獎日期")
                nums = item.get("numbers") or item.get("nums") or item.get("num") or item.get("獎號")
                if not d or not nums:
                    continue

                # nums 可能是字串或 list
                if isinstance(nums, str):
                    nums = [int(x) for x in nums.replace(",", " ").split() if x.strip().isdigit()]
                nums = [int(x) for x in nums][:5]
                if len(nums) != 5:
                    continue

                # 日期格式統一 YYYY-MM-DD（若本來是民國或含斜線，簡單處理）
                d = str(d).replace("/", "-")
                if len(d) == 8 and d.isdigit():
                    d = f"{d[:4]}-{d[4:6]}-{d[6:8]}"

                results.append({"draw_date": d, "nums": sorted(nums)})
        except Exception:
            continue

    # 去重（同日期）
    uniq = {}
    for r in results:
        uniq[r["draw_date"]] = r
    return list(uniq.values())


def freq_count(draws):
    """
    draws: rows from DB newest->older: (date, n1..n5)
    """
    counts = {i: 0 for i in range(1, 40)}
    for _, a, b, c, d, e in draws:
        for n in (a, b, c, d, e):
            if 1 <= n <= 39:
                counts[n] += 1
    return counts


def hot_zone_stats(draws_last30):
    """
    1-13, 14-26, 27-39 三區
    """
    z = {"1-13": 0, "14-26": 0, "27-39": 0}
    for _, a, b, c, d, e in draws_last30:
        for n in (a, b, c, d, e):
            if 1 <= n <= 13:
                z["1-13"] += 1
            elif 14 <= n <= 26:
                z["14-26"] += 1
            else:
                z["27-39"] += 1
    hot = max(z.items(), key=lambda x: x[1])[0]
    return z, hot


def weighted_sample_without_replacement(weights_dict, k=5):
    """
    weights_dict: {num: weight}
    """
    chosen = []
    pool = weights_dict.copy()
    for _ in range(k):
        total = sum(pool.values())
        if total <= 0:
            break
        r = random.uniform(0, total)
        acc = 0
        pick = None
        for num, w in pool.items():
            acc += w
            if r <= acc:
                pick = num
                break
        if pick is None:
            pick = random.choice(list(pool.keys()))
        chosen.append(pick)
        pool.pop(pick, None)
    return sorted(chosen)


def get_or_build_today_pick():
    today = datetime.now(TZ_TW).date().isoformat()

    # 先看快取
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT numbers, hot_zone, top_hot_numbers, model_note
        FROM daily_pick_539
        WHERE pick_date = ?
    """, (today,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {
            "numbers": row[0],
            "hot_zone": row[1],
            "top_hot_numbers": row[2],
            "model_note": row[3],
            "pick_date": today
        }

    # 沒快取：抓資料入庫（近8個月）
    fetched = fetch_recent_draws_from_source(months_back=8)
    if fetched:
        upsert_draws(fetched)

    draws_240 = load_draws(limit=240)   # 近240期做長期頻率
    draws_30 = draws_240[:30]           # 近30期做熱度

    # 如果 DB 還是空的（抓不到）
    if not draws_240:
        return {
            "numbers": "03 14 22 31 39",
            "hot_zone": "（暫無資料）",
            "top_hot_numbers": "（暫無資料）",
            "model_note": "資料源暫時無法取得，回退為固定示範號碼",
            "pick_date": today
        }

    long_freq = freq_count(draws_240)
    short_freq = freq_count(draws_30)
    _, hot_zone = hot_zone_stats(draws_30)

    # 取近30期熱號 Top 5（用於文字提示）
    top_hot = sorted(short_freq.items(), key=lambda x: x[1], reverse=True)[:5]
    top_hot_numbers = " ".join([f"{n:02d}" for n, _ in top_hot])

    # 加權：長期頻率 60% + 近30期熱度 40%
    max_long = max(long_freq.values()) or 1
    max_short = max(short_freq.values()) or 1

    weights = {}
    for n in range(1, 40):
        wl = long_freq[n] / max_long
        ws = short_freq[n] / max_short
        weights[n] = 0.6 * wl + 0.4 * ws

    pick_nums = weighted_sample_without_replacement(weights, k=5)
    numbers_str = " ".join([f"{n:02d}" for n in pick_nums])

    model_note = "模型：近240期頻率(60%) + 近30期熱度(40%) 加權抽樣（非保證）"
    created_at = datetime.now(TZ_TW).isoformat()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO daily_pick_539
        (pick_date, numbers, hot_zone, top_hot_numbers, model_note, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (today, numbers_str, hot_zone, top_hot_numbers, model_note, created_at))
    conn.commit()
    conn.close()

    return {
        "numbers": numbers_str,
        "hot_zone": hot_zone,
        "top_hot_numbers": top_hot_numbers,
        "model_note": model_note,
        "pick_date": today
    }


# ==========
# Routes
# ==========

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

            # 會員提交遊戲帳號
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

            # 管理員：列出待確認50筆
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
                reply_message(reply_token, msg[:5000])
                continue

            # 管理員：確認開通 +30天
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
                    reply_message(reply_token, "找不到該遊戲帳號（請先讓會員輸入：遊戲帳號 XXXXX）")
                    continue

                dt_tw = set_expiry_plus_days(target_user_id, 30)
                reply_message(
                    reply_token,
                    f"✅ 已開通\n帳號：{game_account}\n到期（台灣時間）：{dt_tw.strftime('%Y-%m-%d %H:%M')}"
                )
                continue

            # 使用者：查到期
            if text == "我的到期日":
                exp = get_expiry(user_id)
                if not exp:
                    reply_message(reply_token, "你目前尚未開通。\n請先輸入：遊戲帳號 XXXXX")
                else:
                    dt = datetime.fromisoformat(exp)
                    reply_message(reply_token, "⏳ 到期時間（台灣時間）：\n" + dt.strftime("%Y-%m-%d %H:%M"))
                continue

            # 今日陪跑（自動日期 + 熱區 + 模型 + 只給一組號碼）
            if text == "今日陪跑":
                if not is_member(user_id):
                    reply_message(reply_token, "🌿 今日陪跑屬於會員內容\n\n請先輸入：遊戲帳號 XXXXX")
                else:
                    pack = get_or_build_today_pick()
                    today_str = datetime.now(TZ_TW).strftime("%m/%d")

                    reply_message(
                        reply_token,
                        "🌿 理性陪跑研究室｜" + today_str + "\n\n"
                        "📊 結構觀察\n"
                        f"近30期熱區：{pack['hot_zone']}\n"
                        f"近30期熱號：{pack['top_hot_numbers']}\n\n"
                        "🧠 理性提醒\n"
                        "紀律比直覺重要，今天只做一次決定。\n\n"
                        "✨ 今日陪跑建議\n"
                        f"{pack['numbers']}\n\n"
                        "（數據陪跑參考，非保證）"
                    )
                continue

            # 指令清單
            if text in ("指令", "指令表", "help", "HELP"):
                reply_message(
                    reply_token,
                    "📌 指令\n"
                    "會員：\n"
                    "1) 遊戲帳號 XXXXX\n"
                    "2) 今日陪跑\n"
                    "3) 我的到期日\n\n"
                    "管理員：\n"
                    "1) 待確認 密碼\n"
                    "2) 確認 XXXXX 密碼"
                )
                continue

            reply_message(reply_token, "輸入「指令」查看可用功能。")

    except Exception as e:
        print("Webhook error:", e)

    return "OK"
