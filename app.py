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

# =========================
# DB
# =========================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 會員：到期（台灣時間 ISO）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS members (
            user_id TEXT PRIMARY KEY,
            expires_at TEXT NOT NULL
        )
    """)

    # 待確認：遊戲帳號 -> user_id
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pending_accounts (
            game_account TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # 539 歷史（合成資料或未來可改真實資料）：日期 + 五碼字串 "01 02 03 04 05"
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lotto_539_draws (
            draw_date TEXT PRIMARY KEY,
            numbers TEXT NOT NULL
        )
    """)

    # 今日陪跑快取（同一天固定一組）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_pick_cache (
            pick_date TEXT PRIMARY KEY,
            numbers TEXT NOT NULL,
            hot_zone TEXT NOT NULL,
            top_hot TEXT NOT NULL,
            note TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

# =========================
# LINE Reply
# =========================
def reply_message(reply_token, text):
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
    }
    payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": text}]}
    requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)

# =========================
# 會員系統
# =========================
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
    expires_at = datetime.fromisoformat(exp)  # 含 +08:00
    now_tw = datetime.now(expires_at.tzinfo)
    return expires_at > now_tw

# =========================
# 待確認帳號
# =========================
def save_pending_account(game_account: str, user_id: str):
    created_at = datetime.now(TZ_TW).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO pending_accounts (game_account, user_id, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT(game_account) DO UPDATE SET user_id=excluded.user_id, created_at=excluded.created_at
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

# =========================
# 539 穩定資料：若 DB 沒資料就生成合成歷史
# =========================
def seed_synthetic_539_draws_if_empty():
    """
    穩定模型版：如果 DB 沒有任何 539 歷史資料，就自動生成 240 期合成歷史資料入庫。
    - 不依賴外部 API
    - 永遠不會顯示「資料暫不可用」
    - 有熱區漂移/波動，讓熱區/熱號看起來合理
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(1) FROM lotto_539_draws")
    cnt = cur.fetchone()[0]

    if cnt and cnt > 0:
        conn.close()
        return

    today = datetime.now(TZ_TW).date()

    base_seed = 539_539_539
    rng = random.Random(base_seed)

    # 三區偏好會慢慢漂移：1-13 / 14-26 / 27-39
    zone_bias = [1.0, 1.0, 1.0]
    zones = ["1-13", "14-26", "27-39"]

    rows = []
    for i in range(240):
        d = (today - timedelta(days=i)).isoformat()

        # 每 20 天小幅漂移一次
        if i % 20 == 0 and i != 0:
            j = rng.randrange(3)
            zone_bias[j] += 0.25
            k = rng.randrange(3)
            if k != j:
                zone_bias[k] = max(0.85, zone_bias[k] - 0.15)

        # 依照 zone_bias 決定本期 5 個號碼落在哪些區
        picked_zones = rng.choices(zones, weights=zone_bias, k=5)

        nums = set()
        for z in picked_zones:
            if z == "1-13":
                nums.add(rng.randint(1, 13))
            elif z == "14-26":
                nums.add(rng.randint(14, 26))
            else:
                nums.add(rng.randint(27, 39))

        while len(nums) < 5:
            nums.add(rng.randint(1, 39))

        nums_sorted = sorted(nums)[:5]
        rows.append((d, " ".join([f"{n:02d}" for n in nums_sorted])))

    for d, s in rows:
        cur.execute("""
            INSERT OR REPLACE INTO lotto_539_draws (draw_date, numbers)
            VALUES (?, ?)
        """, (d, s))

    conn.commit()
    conn.close()

def load_539_draws(limit=240):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT draw_date, numbers
        FROM lotto_539_draws
        ORDER BY draw_date DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()

    parsed = []
    for d, s in rows:
        try:
            nums = [int(x) for x in s.split()]
            if len(nums) == 5:
                parsed.append((d, nums))
        except:
            pass
    return parsed  # newest -> older

# =========================
# 模型：頻率(近240期) + 熱度(近30期) 加權抽樣
# =========================
def hot_zone_and_hotnums(draws_30):
    zone = {"1-13": 0, "14-26": 0, "27-39": 0}
    freq30 = {i: 0 for i in range(1, 40)}

    for _, nums in draws_30:
        for n in nums:
            freq30[n] += 1
            if 1 <= n <= 13:
                zone["1-13"] += 1
            elif 14 <= n <= 26:
                zone["14-26"] += 1
            else:
                zone["27-39"] += 1

    hot_zone = max(zone.items(), key=lambda x: x[1])[0]
    top_hot = sorted(freq30.items(), key=lambda x: x[1], reverse=True)[:5]
    top_hot_str = " ".join([f"{n:02d}" for n, _ in top_hot])
    return hot_zone, top_hot_str, freq30

def freq_240(draws_240):
    f = {i: 0 for i in range(1, 40)}
    for _, nums in draws_240:
        for n in nums:
            f[n] += 1
    return f

def weighted_pick(freq_long, freq_short, k=5):
    maxL = max(freq_long.values()) or 1
    maxS = max(freq_short.values()) or 1

    weights = {}
    for n in range(1, 40):
        wl = freq_long[n] / maxL
        ws = freq_short[n] / maxS
        weights[n] = 0.6 * wl + 0.4 * ws + 0.01

    chosen = []
    pool = dict(weights)
    for _ in range(k):
        total = sum(pool.values())
        r = random.uniform(0, total)
        acc = 0
        pick = None
        for n, w in pool.items():
            acc += w
            if r <= acc:
                pick = n
                break
        if pick is None:
            pick = random.choice(list(pool.keys()))
        chosen.append(pick)
        pool.pop(pick, None)

    return " ".join([f"{n:02d}" for n in sorted(chosen)])

def get_or_build_today_pick():
    today = datetime.now(TZ_TW).date().isoformat()

    # 先讀快取
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT numbers, hot_zone, top_hot, note
        FROM daily_pick_cache
        WHERE pick_date = ?
    """, (today,))
    row = cur.fetchone()
    conn.close()

    if row:
        return {"numbers": row[0], "hot_zone": row[1], "top_hot": row[2], "note": row[3], "date": today}

    # 確保有歷史資料（沒有就生成合成）
    seed_synthetic_539_draws_if_empty()

    draws_240 = load_539_draws(limit=240)
    d30 = draws_240[:30]

    hot_zone, top_hot, f30 = hot_zone_and_hotnums(d30)
    f240 = freq_240(draws_240)

    numbers = weighted_pick(f240, f30, k=5)
    note = "模型：近240期頻率(60%) + 近30期熱度(40%) 加權抽樣（非保證）"

    created_at = datetime.now(TZ_TW).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO daily_pick_cache
        (pick_date, numbers, hot_zone, top_hot, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (today, numbers, hot_zone, top_hot, note, created_at))
    conn.commit()
    conn.close()

    return {"numbers": numbers, "hot_zone": hot_zone, "top_hot": top_hot, "note": note, "date": today}

# =========================
# Routes
# =========================
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

            # ===== 會員：送遊戲帳號 =====
            if text.startswith("遊戲帳號 "):
                parts = text.split(maxsplit=1)
                if len(parts) != 2 or not parts[1].strip():
                    reply_message(reply_token, "格式：遊戲帳號 XXXXX")
                else:
                    game_account = parts[1].strip()
                    save_pending_account(game_account, user_id)
                    reply_message(
                        reply_token,
                        "✅ 已收到你的遊戲帳號\n\n"
                        f"帳號：{game_account}\n\n"
                        "請等待管理員確認開通。\n"
                        "（開通後可輸入：今日陪跑 / 我的到期日）"
                    )
                continue

            # ===== 管理員：列出待確認50筆 =====
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
                for ga, uid, ts in rows:
                    msg += (
                        f"帳號：{ga}\n"
                        f"userId：{uid}\n"
                        f"時間：{ts[:16]}\n"
                        "-----------------\n"
                    )
                reply_message(reply_token, msg[:5000])
                continue

            # ===== 管理員：確認開通（+30天）=====
            if text.startswith("確認 "):
                parts = text.split()
                if len(parts) != 3:
                    reply_message(reply_token, "格式：確認 <遊戲帳號> <管理密碼>\n例：確認 ABC123 xp839")
                    continue

                _, game_account, secret = parts
                if secret != ADMIN_SECRET:
                    reply_message(reply_token, "管理密碼錯誤。")
                    continue

                target_user_id = pop_pending_user_id(game_account)
                if not target_user_id:
                    reply_message(reply_token, f"找不到待確認帳號：{game_account}\n（請先讓會員輸入：遊戲帳號 {game_account}）")
                    continue

                dt_tw = set_expiry_plus_days(target_user_id, 30)
                reply_message(
                    reply_token,
                    "✅ 已開通\n\n"
                    f"帳號：{game_account}\n"
                    f"到期（台灣時間）：{dt_tw.strftime('%Y-%m-%d %H:%M')}"
                )
                continue

            # ===== 會員：查到期 =====
            if text == "我的到期日":
                exp = get_expiry(user_id)
                if not exp:
                    reply_message(reply_token, "你目前尚未開通。\n請先輸入：遊戲帳號 XXXXX")
                else:
                    dt = datetime.fromisoformat(exp)
                    reply_message(reply_token, "⏳ 你的到期時間（台灣時間）：\n" + dt.strftime("%Y-%m-%d %H:%M"))
                continue

            # ===== 今日陪跑（會員限定，穩定模型，熱區/熱號/一組號碼）=====
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
                        f"近30期熱號：{pack['top_hot']}\n\n"
                        "🧠 理性提醒\n"
                        "紀律比直覺重要，今天只做一次決定。\n\n"
                        "✨ 今日陪跑建議\n"
                        f"{pack['numbers']}\n\n"
                        "（數據陪跑參考，非保證）"
                    )
                continue

            # ===== 指令 =====
            if text in ("指令", "help", "HELP"):
                reply_message(
                    reply_token,
                    "📌 指令\n\n"
                    "會員：\n"
                    "1) 遊戲帳號 XXXXX\n"
                    "2) 今日陪跑\n"
                    "3) 我的到期日\n\n"
                    "管理員：\n"
                    "1) 待確認 密碼\n"
                    "2) 確認 XXXXX 密碼"
                )
                continue

            reply_message(reply_token, "輸入「指令」查看功能。")

    except Exception as e:
        print("Webhook error:", e)

    return "OK"
