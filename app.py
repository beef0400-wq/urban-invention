from flask import Flask, request
import os
import json
import requests
import random
from datetime import datetime, timedelta, timezone
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "1234")
DATABASE_URL = os.getenv("DATABASE_URL")  # Render Postgres 給你的那串

TZ_TW = timezone(timedelta(hours=8))

# =========================
# 每日陪跑語錄（同一天固定一句）
# =========================
QUOTES = [
    "紀律，是把波動變成機會的方法。",
    "穩定，比爆發更有力量。",
    "情緒會波動，紀律不應該。",
    "真正的優勢來自長期執行。",
    "不是追高，而是守住節奏。",
    "理性，是對抗不確定性的武器。",
    "慢，比快更接近成功。",
    "不要因為上一期改變原則。",
    "決策只做一次，紀律每天重複。",
    "運氣會變，結構會留下痕跡。",
    "短期波動，不代表長期方向。",
    "真正的陪跑，是控制風險。",
    "穩定，是最高級的策略。",
    "冷靜，是最大的勝率。",
    "模型給方向，紀律給結果。",
    "不追連莊，不補情緒。",
    "節奏，比衝動重要。",
    "數據說話，情緒沉默。",
    "長期主義，永遠勝出。",
    "看清結構，再做決定。",
    "不要被上一期牽著走。",
    "一次選擇，一次紀律。",
    "堅持模型，拒絕焦躁。",
    "穩住，是最高級操作。",
    "把風險留在門外。",
    "不是賭，是紀律實驗。",
    "決策清晰，結果自然。",
    "耐心，是隱形優勢。",
    "陪跑，是為了穩定。",
    "今天也只做一個決定。"
]

def get_daily_quote():
    today = datetime.now(TZ_TW).date()
    idx = today.toordinal() % len(QUOTES)
    return QUOTES[idx]

# =========================
# Postgres 連線 & 建表
# =========================
def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL 未設定。請到 Render 環境變數加入 DATABASE_URL")
    # Render 多數情況需要 SSL
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    # members
    cur.execute("""
        CREATE TABLE IF NOT EXISTS members (
            user_id TEXT PRIMARY KEY,
            expires_at TIMESTAMPTZ NOT NULL
        );
    """)
    # pending_accounts
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pending_accounts (
            game_account TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        );
    """)
    # lotto_539_draws（穩定模型合成資料）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lotto_539_draws (
            draw_date DATE PRIMARY KEY,
            numbers TEXT NOT NULL
        );
    """)
    # daily_pick_cache
    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_pick_cache (
            pick_date DATE PRIMARY KEY,
            numbers TEXT NOT NULL,
            hot_zone TEXT NOT NULL,
            top_hot TEXT NOT NULL,
            note TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        );
    """)
    conn.commit()
    cur.close()
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

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO members (user_id, expires_at)
        VALUES (%s, %s)
        ON CONFLICT (user_id) DO UPDATE SET expires_at = EXCLUDED.expires_at;
    """, (user_id, dt_tw))
    conn.commit()
    cur.close()
    conn.close()
    return dt_tw

def get_expiry(user_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT expires_at FROM members WHERE user_id = %s;", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None  # datetime

def is_member(user_id: str) -> bool:
    exp = get_expiry(user_id)
    if not exp:
        return False
    # exp 是 timestamptz（帶 tz），用台灣時間比較
    now_tw = datetime.now(TZ_TW)
    # exp 轉到台灣時區比較
    exp_tw = exp.astimezone(TZ_TW)
    return exp_tw > now_tw

# =========================
# 待確認帳號
# =========================
def save_pending_account(game_account: str, user_id: str):
    created_at = datetime.now(TZ_TW)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO pending_accounts (game_account, user_id, created_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (game_account) DO UPDATE
        SET user_id = EXCLUDED.user_id,
            created_at = EXCLUDED.created_at;
    """, (game_account, user_id, created_at))
    conn.commit()
    cur.close()
    conn.close()

def pop_pending_user_id(game_account: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM pending_accounts WHERE game_account = %s;", (game_account,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return None

    user_id = row[0]
    cur.execute("DELETE FROM pending_accounts WHERE game_account = %s;", (game_account,))
    conn.commit()
    cur.close()
    conn.close()
    return user_id

def get_latest_pending(limit=50):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT game_account, user_id, created_at
        FROM pending_accounts
        ORDER BY created_at DESC
        LIMIT %s;
    """, (limit,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows  # list of tuples

# =========================
# 539 穩定資料：若 DB 沒資料就生成合成歷史
# =========================
def seed_synthetic_539_draws_if_empty():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(1) FROM lotto_539_draws;")
    cnt = cur.fetchone()[0]
    if cnt and cnt > 0:
        cur.close()
        conn.close()
        return

    today = datetime.now(TZ_TW).date()
    rng = random.Random(539_539_539)

    zone_bias = [1.0, 1.0, 1.0]
    zones = ["1-13", "14-26", "27-39"]

    rows = []
    for i in range(240):
        d = today - timedelta(days=i)

        if i % 20 == 0 and i != 0:
            j = rng.randrange(3)
            zone_bias[j] += 0.25
            k = rng.randrange(3)
            if k != j:
                zone_bias[k] = max(0.85, zone_bias[k] - 0.15)

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
        s = " ".join([f"{n:02d}" for n in nums_sorted])
        rows.append((d, s))

    cur.executemany("""
        INSERT INTO lotto_539_draws (draw_date, numbers)
        VALUES (%s, %s)
        ON CONFLICT (draw_date) DO UPDATE SET numbers = EXCLUDED.numbers;
    """, rows)
    conn.commit()
    cur.close()
    conn.close()

def load_539_draws(limit=240):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT draw_date, numbers
        FROM lotto_539_draws
        ORDER BY draw_date DESC
        LIMIT %s;
    """, (limit,))
    rows = cur.fetchall()
    cur.close()
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
    today = datetime.now(TZ_TW).date()

    # 先讀快取
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT numbers, hot_zone, top_hot, note
        FROM daily_pick_cache
        WHERE pick_date = %s;
    """, (today,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if row:
        return {"numbers": row[0], "hot_zone": row[1], "top_hot": row[2], "note": row[3], "date": today}

    # 確保有歷史資料（沒有就生成）
    seed_synthetic_539_draws_if_empty()

    draws_240 = load_539_draws(limit=240)
    d30 = draws_240[:30]

    hot_zone, top_hot, f30 = hot_zone_and_hotnums(d30)
    f240 = freq_240(draws_240)
    numbers = weighted_pick(f240, f30, k=5)

    note = "模型：近240期頻率(60%) + 近30期熱度(40%) 加權抽樣（非保證）"
    created_at = datetime.now(TZ_TW)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO daily_pick_cache (pick_date, numbers, hot_zone, top_hot, note, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (pick_date) DO UPDATE SET
            numbers = EXCLUDED.numbers,
            hot_zone = EXCLUDED.hot_zone,
            top_hot = EXCLUDED.top_hot,
            note = EXCLUDED.note,
            created_at = EXCLUDED.created_at;
    """, (today, numbers, hot_zone, top_hot, note, created_at))
    conn.commit()
    cur.close()
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

            # 會員：送遊戲帳號
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
                return "OK"

            # 管理員：列出待確認50筆
            if text.startswith("待確認 "):
                parts = text.split()
                if len(parts) != 2 or parts[1] != ADMIN_SECRET:
                    reply_message(reply_token, "管理密碼錯誤。")
                    return "OK"

                rows = get_latest_pending(50)
                if not rows:
                    reply_message(reply_token, "目前沒有待確認帳號。")
                    return "OK"

                msg = "📋 最近待確認帳號（最多50筆）\n\n"
                for ga, uid, ts in rows:
                    # ts 是 datetime
                    ts_str = ts.astimezone(TZ_TW).strftime("%Y-%m-%d %H:%M")
                    msg += (
                        f"帳號：{ga}\n"
                        f"userId：{uid}\n"
                        f"時間：{ts_str}\n"
                        "-----------------\n"
                    )
                reply_message(reply_token, msg[:5000])
                return "OK"

            # 管理員：確認開通（+30天）
            if text.startswith("確認 "):
                parts = text.split()
                if len(parts) != 3:
                    reply_message(reply_token, "格式：確認 <遊戲帳號> <管理密碼>\n例：確認 ABC123 xp839")
                    return "OK"

                _, game_account, secret = parts
                if secret != ADMIN_SECRET:
                    reply_message(reply_token, "管理密碼錯誤。")
                    return "OK"

                target_user_id = pop_pending_user_id(game_account)
                if not target_user_id:
                    reply_message(reply_token, f"找不到待確認帳號：{game_account}\n（請先讓會員輸入：遊戲帳號 {game_account}）")
                    return "OK"

                dt_tw = set_expiry_plus_days(target_user_id, 30)
                reply_message(
                    reply_token,
                    "✅ 已開通\n\n"
                    f"帳號：{game_account}\n"
                    f"到期（台灣時間）：{dt_tw.strftime('%Y-%m-%d %H:%M')}"
                )
                return "OK"

            # 會員：查到期
            if text == "我的到期日":
                exp = get_expiry(user_id)
                if not exp:
                    reply_message(reply_token, "你目前尚未開通。\n請先輸入：遊戲帳號 XXXXX")
                else:
                    exp_tw = exp.astimezone(TZ_TW)
                    reply_message(reply_token, "⏳ 你的到期時間（台灣時間）：\n" + exp_tw.strftime("%Y-%m-%d %H:%M"))
                return "OK"

            # 今日陪跑（會員限定，高端研究室風 + 每日語錄）
            if text == "今日陪跑":
                if not is_member(user_id):
                    reply_message(reply_token, "🌿 今日陪跑屬於會員內容\n\n請先輸入：遊戲帳號 XXXXX")
                else:
                    pack = get_or_build_today_pick()
                    today_str = datetime.now(TZ_TW).strftime("%Y.%m.%d")
                    quote = get_daily_quote()

                    reply_message(
                        reply_token,
                        "【理性陪跑研究室】\n"
                        f"{today_str}\n\n"
                        "▍結構分析\n"
                        f"近30期活躍區段：{pack['hot_zone']}\n"
                        f"高頻樣本集中：{pack['top_hot']}\n\n"
                        "▍本日模型建議\n"
                        f"{pack['numbers']}\n\n"
                        "模型來源：\n"
                        "240期頻率 × 30期熱度加權\n\n"
                        "—— 今日陪跑語錄 ——\n"
                        f"{quote}\n\n"
                        "（數據結構參考，非保證）"
                    )
                return "OK"

            # 指令
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
                return "OK"

            reply_message(reply_token, "輸入「指令」查看功能。")
            return "OK"

    except Exception as e:
        print("Webhook error:", e)

    return "OK"
