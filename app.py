from flask import Flask, request, abort
import os
import json
import requests
import random
import base64
import hashlib
import hmac
import re
from datetime import datetime, timedelta, timezone, date
import psycopg2

app = Flask(__name__)

# ========= 環境變數 =========
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN", "").strip()
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET", "").strip()
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "1234").strip()
CRON_SECRET = os.getenv("CRON_SECRET", "push8899").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

TZ_TW = timezone(timedelta(hours=8))

# =========================
# 每日陪跑語錄
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
# LINE Signature 驗證
# =========================
def verify_line_signature(raw_body: bytes, signature: str) -> bool:
    if not CHANNEL_SECRET:
        return False
    mac = hmac.new(CHANNEL_SECRET.encode("utf-8"), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(mac).decode("utf-8")
    return hmac.compare_digest(expected, signature or "")

# =========================
# Postgres
# =========================
def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL 未設定")
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS members (
            user_id TEXT PRIMARY KEY,
            expires_at TIMESTAMPTZ NOT NULL
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pending_accounts (
            game_account TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lotto_539_draws (
            draw_date DATE PRIMARY KEY,
            numbers TEXT NOT NULL
        );
    """)

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

    # 賓果推播去重
    cur.execute("""
        CREATE TABLE IF NOT EXISTS push_state (
            push_key TEXT PRIMARY KEY,
            last_bucket TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        );
    """)

    conn.commit()
    cur.close()
    conn.close()

# =========================
# LINE Reply / Push
# =========================
def reply_message(reply_token: str, text: str):
    if not CHANNEL_ACCESS_TOKEN:
        print("CHANNEL_ACCESS_TOKEN empty")
        return

    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
    }
    payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": text}]}

    try:
        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
        if r.status_code >= 400:
            print("LINE reply failed:", r.status_code, r.text[:300])
    except Exception as e:
        print("LINE reply exception:", repr(e))

def push_message(user_id: str, text: str):
    if not CHANNEL_ACCESS_TOKEN:
        print("CHANNEL_ACCESS_TOKEN empty")
        return False

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": text}]
    }

    try:
        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
        if r.status_code >= 400:
            print("LINE push failed:", user_id, r.status_code, r.text[:300])
            return False
        return True
    except Exception as e:
        print("LINE push exception:", repr(e))
        return False

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
    return row[0] if row else None

def is_member(user_id: str) -> bool:
    exp = get_expiry(user_id)
    if not exp:
        return False
    now_tw = datetime.now(TZ_TW)
    exp_tw = exp.astimezone(TZ_TW)
    return exp_tw > now_tw

def get_active_member_ids():
    conn = get_conn()
    cur = conn.cursor()
    now_tw = datetime.now(TZ_TW)
    cur.execute("""
        SELECT user_id
        FROM members
        WHERE expires_at > %s;
    """, (now_tw,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [r[0] for r in rows]

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
    return rows

# =========================
# 真實539資料抓取
# =========================
SOURCE_539_URL = "https://www.pilio.idv.tw/lto539/list539BIG.asp"

def fetch_recent_539_results(max_rows: int = 80):
    r = requests.get(SOURCE_539_URL, timeout=10)
    r.encoding = "utf-8"
    html = r.text

    pattern = re.compile(
        r"開獎日期:(\d{4})/(\d{2})/(\d{2}).{0,20}?\s+(\d{2})[,\s]+(\d{2})[,\s]+(\d{2})[,\s]+(\d{2})[,\s]+(\d{2})",
        re.MULTILINE
    )

    out = []
    for m in pattern.finditer(html):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        nums = [int(m.group(i)) for i in range(4, 9)]
        nums_sorted = sorted(nums)
        s = " ".join([f"{n:02d}" for n in nums_sorted])
        out.append((date(y, mo, d), s))
        if len(out) >= max_rows:
            break
    return out

def upsert_539_draws(rows):
    if not rows:
        return 0
    conn = get_conn()
    cur = conn.cursor()
    cur.executemany("""
        INSERT INTO lotto_539_draws (draw_date, numbers)
        VALUES (%s, %s)
        ON CONFLICT (draw_date) DO UPDATE SET numbers = EXCLUDED.numbers;
    """, rows)
    conn.commit()
    cur.close()
    conn.close()
    return len(rows)

def ensure_latest_539_in_db():
    try:
        rows = fetch_recent_539_results(max_rows=60)
        upsert_539_draws(rows)
    except Exception as e:
        print("FETCH_539_ERROR:", repr(e))

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
    return parsed

# =========================
# 539 模型
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

    ensure_latest_539_in_db()
    draws_240 = load_539_draws(limit=240)
    d30 = draws_240[:30] if len(draws_240) >= 30 else draws_240
    hot_zone, top_hot, f30 = hot_zone_and_hotnums(d30)
    f240 = freq_240(draws_240) if draws_240 else {i: 1 for i in range(1, 40)}

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
# 賓果模型
# 1期 / 5期 / 10期 都只回5顆號碼
# 同一時間桶固定，時間過了自動換
# =========================
def _time_bucket(minutes_step: int):
    now = datetime.now(TZ_TW)
    total_minutes = int(now.timestamp() // 60)
    return total_minutes // minutes_step

def _bingo_pick(seed_text: str):
    rng = random.Random(seed_text)
    nums = rng.sample(range(1, 81), 5)
    nums.sort()
    return " ".join([f"{n:02d}" for n in nums])

def get_bingo_1_pick():
    bucket = _time_bucket(5)
    return _bingo_pick(f"bingo1-{bucket}")

def get_bingo_5_pick():
    bucket = _time_bucket(15)
    return _bingo_pick(f"bingo5-{bucket}")

def get_bingo_10_pick():
    bucket = _time_bucket(25)
    return _bingo_pick(f"bingo10-{bucket}")

def format_bingo_1_message():
    nums = get_bingo_1_pick()
    quote = get_daily_quote()
    return (
        "【賓果賓果｜1期分析】\n"
        f"{datetime.now(TZ_TW).strftime('%Y.%m.%d %H:%M')}\n\n"
        "▍短線觀察\n"
        "即時節奏模型\n\n"
        "▍建議號碼\n"
        f"{nums}\n\n"
        "—— 今日陪跑語錄 ——\n"
        f"{quote}"
    )

def format_bingo_5_message():
    nums = get_bingo_5_pick()
    quote = get_daily_quote()
    return (
        "【賓果賓果｜5期分析】\n"
        f"{datetime.now(TZ_TW).strftime('%Y.%m.%d %H:%M')}\n\n"
        "▍短週期結構\n"
        "近5期節奏模型\n\n"
        "▍建議號碼\n"
        f"{nums}\n\n"
        "—— 今日陪跑語錄 ——\n"
        f"{quote}"
    )

def format_bingo_10_message():
    nums = get_bingo_10_pick()
    quote = get_daily_quote()
    return (
        "【賓果賓果｜10期分析】\n"
        f"{datetime.now(TZ_TW).strftime('%Y.%m.%d %H:%M')}\n\n"
        "▍結構分析\n"
        "近10期熱區模型\n\n"
        "▍建議號碼\n"
        f"{nums}\n\n"
        "—— 今日陪跑語錄 ——\n"
        f"{quote}"
    )

# =========================
# Push state（避免同一桶重複推）
# =========================
def get_push_state(push_key: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT last_bucket FROM push_state WHERE push_key = %s;", (push_key,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None

def set_push_state(push_key: str, last_bucket: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO push_state (push_key, last_bucket, updated_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (push_key) DO UPDATE
        SET last_bucket = EXCLUDED.last_bucket,
            updated_at = EXCLUDED.updated_at;
    """, (push_key, last_bucket, datetime.now(TZ_TW)))
    conn.commit()
    cur.close()
    conn.close()

# =========================
# 推播內容
# =========================
def format_539_push():
    pack = get_or_build_today_pick()
    today_str = datetime.now(TZ_TW).strftime("%Y.%m.%d")
    quote = get_daily_quote()
    return (
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

# =========================
# Routes
# =========================
@app.route("/")
def home():
    return "Bot is running."

@app.route("/cron/push-all")
def cron_push_all():
    secret = request.args.get("secret", "")
    if secret != CRON_SECRET:
        abort(403)

    try:
        init_db()
        members = get_active_member_ids()
        if not members:
            return "No active members", 200

        now = datetime.now(TZ_TW)

        # 539：每天固定 19:00 推一次
        if now.hour == 19 and now.minute < 5:
            bucket_539 = now.strftime("%Y-%m-%d-19")
            if get_push_state("push_539_daily") != bucket_539:
                msg = format_539_push()
                for uid in members:
                    push_message(uid, msg)
                set_push_state("push_539_daily", bucket_539)

        # 賓果1期：每5分鐘
        bucket1 = str(_time_bucket(5))
        if get_push_state("push_bingo_1") != bucket1:
            msg = format_bingo_1_message()
            for uid in members:
                push_message(uid, msg)
            set_push_state("push_bingo_1", bucket1)

        # 賓果5期：每15分鐘
        bucket5 = str(_time_bucket(15))
        if get_push_state("push_bingo_5") != bucket5:
            msg = format_bingo_5_message()
            for uid in members:
                push_message(uid, msg)
            set_push_state("push_bingo_5", bucket5)

        # 賓果10期：每25分鐘
        bucket10 = str(_time_bucket(25))
        if get_push_state("push_bingo_10") != bucket10:
            msg = format_bingo_10_message()
            for uid in members:
                push_message(uid, msg)
            set_push_state("push_bingo_10", bucket10)

        return "OK", 200
    except Exception as e:
        print("CRON_PUSH_ERROR:", repr(e))
        return "ERROR", 500

@app.route("/webhook", methods=["POST"])
def webhook():
    raw = request.get_data()
    signature = request.headers.get("X-Line-Signature", "")

    if not verify_line_signature(raw, signature):
        abort(403)

    body = request.get_json(silent=True) or {}
    events = body.get("events", [])

    try:
        init_db()
    except Exception as e:
        print("INIT_DB ERROR:", repr(e))
        return "OK"

    for event in events:
        if event.get("type") != "message":
            continue
        message = event.get("message", {})
        if message.get("type") != "text":
            continue

        text = (message.get("text") or "").strip()
        reply_token = event.get("replyToken")
        user_id = event.get("source", {}).get("userId", "")

        if text == "申請加入會員":
            reply_message(
                reply_token,
                "請輸入:\n"
                "(遊戲帳號 XXXXXX)\n"
                "X為3A帳號 ()內都要輸入\n\n"
                "範例: 遊戲帳號 123456"
            )
            continue

        if text in ("指令", "help", "HELP"):
            reply_message(
                reply_token,
                "📌 指令\n\n"
                "會員：\n"
                "1) 申請加入會員\n"
                "2) 遊戲帳號 XXXXX\n"
                "3) 今日陪跑\n"
                "4) 賓果1期分析\n"
                "5) 賓果5期分析\n"
                "6) 賓果10期分析\n"
                "7) 我的到期日\n\n"
                "管理員：\n"
                "1) 待確認 密碼\n"
                "2) 確認 XXXXX 密碼"
            )
            continue

        if text.startswith("遊戲帳號 "):
            parts = text.split(maxsplit=1)
            if len(parts) != 2 or not parts[1].strip():
                reply_message(reply_token, "格式：遊戲帳號 XXXXX")
            else:
                game_account = parts[1].strip()
                save_pending_account(game_account, user_id)
                reply_message(
                    reply_token,
                    "✅ 已收到你的申請加入會員\n\n"
                    f"帳號：{game_account}\n\n"
                    "請等待管理員確認開通。\n"
                    "（開通後可輸入：今日陪跑 / 賓果1期分析 / 賓果5期分析 / 賓果10期分析 / 我的到期日）"
                )
            continue

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
                ts_str = ts.astimezone(TZ_TW).strftime("%Y-%m-%d %H:%M")
                msg += f"帳號：{ga}\nuserId：{uid}\n時間：{ts_str}\n-----------------\n"
            reply_message(reply_token, msg[:5000])
            continue

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

        if text == "我的到期日":
            exp = get_expiry(user_id)
            if not exp:
                reply_message(reply_token, "你目前尚未開通。\n請先輸入：遊戲帳號 XXXXX")
            else:
                exp_tw = exp.astimezone(TZ_TW)
                reply_message(reply_token, "⏳ 你的到期時間（台灣時間）：\n" + exp_tw.strftime("%Y-%m-%d %H:%M"))
            continue

        if text == "今日陪跑":
            if not is_member(user_id):
                reply_message(reply_token, "🌿 今日陪跑屬於會員內容\n\n請先輸入：遊戲帳號 XXXXX")
            else:
                reply_message(reply_token, format_539_push())
            continue

        if text == "賓果1期分析":
            if not is_member(user_id):
                reply_message(reply_token, "🌿 賓果1期分析屬於會員內容\n\n請先輸入：遊戲帳號 XXXXX")
            else:
                reply_message(reply_token, format_bingo_1_message())
            continue

        if text == "賓果5期分析":
            if not is_member(user_id):
                reply_message(reply_token, "🌿 賓果5期分析屬於會員內容\n\n請先輸入：遊戲帳號 XXXXX")
            else:
                reply_message(reply_token, format_bingo_5_message())
            continue

        if text == "賓果10期分析":
            if not is_member(user_id):
                reply_message(reply_token, "🌿 賓果10期分析屬於會員內容\n\n請先輸入：遊戲帳號 XXXXX")
            else:
                reply_message(reply_token, format_bingo_10_message())
            continue

        reply_message(reply_token, "輸入「指令」查看功能。")

    return "OK"
