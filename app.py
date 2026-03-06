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

# ========= 資料來源 =========
SOURCE_539_URL = "https://www.pilio.idv.tw/lto539/list539BIG.asp"
SOURCE_BINGO_URL = "https://www.pilio.idv.tw/bingo/list.asp"

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
        CREATE TABLE IF NOT EXISTS prediction_subscribers (
            user_id TEXT PRIMARY KEY,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            updated_at TIMESTAMPTZ NOT NULL
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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS push_state (
            push_key TEXT PRIMARY KEY,
            last_value TEXT NOT NULL,
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


def push_message(user_id: str, text: str) -> bool:
    if not CHANNEL_ACCESS_TOKEN:
        print("CHANNEL_ACCESS_TOKEN empty")
        return False

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
    }
    payload = {"to": user_id, "messages": [{"type": "text", "text": text}]}

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
    cur.execute("SELECT user_id FROM members WHERE expires_at > %s;", (now_tw,))
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
# 預測分析訂閱
# =========================
def enable_prediction(user_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO prediction_subscribers (user_id, enabled, updated_at)
        VALUES (%s, TRUE, %s)
        ON CONFLICT (user_id) DO UPDATE
        SET enabled = TRUE,
            updated_at = EXCLUDED.updated_at;
    """, (user_id, datetime.now(TZ_TW)))
    conn.commit()
    cur.close()
    conn.close()


def disable_prediction(user_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO prediction_subscribers (user_id, enabled, updated_at)
        VALUES (%s, FALSE, %s)
        ON CONFLICT (user_id) DO UPDATE
        SET enabled = FALSE,
            updated_at = EXCLUDED.updated_at;
    """, (user_id, datetime.now(TZ_TW)))
    conn.commit()
    cur.close()
    conn.close()


def get_prediction_subscribers():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.user_id
        FROM prediction_subscribers p
        JOIN members m ON p.user_id = m.user_id
        WHERE p.enabled = TRUE
          AND m.expires_at > %s;
    """, (datetime.now(TZ_TW),))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [r[0] for r in rows]


# =========================
# push state
# =========================
def get_push_state(push_key: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT last_value FROM push_state WHERE push_key = %s;", (push_key,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None


def set_push_state(push_key: str, last_value: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO push_state (push_key, last_value, updated_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (push_key) DO UPDATE
        SET last_value = EXCLUDED.last_value,
            updated_at = EXCLUDED.updated_at;
    """, (push_key, last_value, datetime.now(TZ_TW)))
    conn.commit()
    cur.close()
    conn.close()


# =========================
# 539 真實資料
# =========================
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
        return
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


def ensure_latest_539_in_db():
    try:
        rows = fetch_recent_539_results(max_rows=80)
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
        except Exception:
            pass
    return parsed


def hot_zone_and_hotnums_539(draws_30):
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


def freq_539(draws_240):
    f = {i: 0 for i in range(1, 40)}
    for _, nums in draws_240:
        for n in nums:
            f[n] += 1
    return f


def weighted_pick_539(freq_long, freq_short, k=5):
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


def get_or_build_today_pick_539():
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
        return {"numbers": row[0], "hot_zone": row[1], "top_hot": row[2], "note": row[3]}

    ensure_latest_539_in_db()
    draws_240 = load_539_draws(limit=240)
    d30 = draws_240[:30] if len(draws_240) >= 30 else draws_240
    hot_zone, top_hot, f30 = hot_zone_and_hotnums_539(d30)
    f240 = freq_539(draws_240) if draws_240 else {i: 1 for i in range(1, 40)}
    numbers = weighted_pick_539(f240, f30, k=5)
    note = "模型：近240期頻率 × 近30期熱度加權"

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO daily_pick_cache (pick_date, numbers, hot_zone, top_hot, note, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (pick_date) DO UPDATE
        SET numbers = EXCLUDED.numbers,
            hot_zone = EXCLUDED.hot_zone,
            top_hot = EXCLUDED.top_hot,
            note = EXCLUDED.note,
            created_at = EXCLUDED.created_at;
    """, (today, numbers, hot_zone, top_hot, note, datetime.now(TZ_TW)))
    conn.commit()
    cur.close()
    conn.close()

    return {"numbers": numbers, "hot_zone": hot_zone, "top_hot": top_hot, "note": note}


def format_539_push():
    pack = get_or_build_today_pick_539()
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
# Bingo 真實資料
# =========================
def fetch_recent_bingo_results(max_rows: int = 60):
    r = requests.get(SOURCE_BINGO_URL, timeout=10)
    r.encoding = "utf-8"
    html = r.text.replace("\xa0", " ")

    pattern = re.compile(
        r"〖期別:\s*(\d+)〗\s*([0-9,\s]+?)\s*超級獎號.*?\((\d{2}:\d{2})\)",
        re.S
    )

    out = []
    for m in pattern.finditer(html):
        period = m.group(1)
        numbers_block = m.group(2)
        draw_time = m.group(3)
        nums = [int(x) for x in re.findall(r"\d{2}", numbers_block)]
        nums = nums[:20]
        if len(nums) == 20:
            out.append({
                "period": period,
                "time": draw_time,
                "numbers": sorted(nums)
            })
        if len(out) >= max_rows:
            break
    return out


def bingo_zone_summary(draws):
    zones = {"1-20": 0, "21-40": 0, "41-60": 0, "61-80": 0}
    freq = {i: 0 for i in range(1, 81)}

    for draw in draws:
        for n in draw["numbers"]:
            freq[n] += 1
            if 1 <= n <= 20:
                zones["1-20"] += 1
            elif 21 <= n <= 40:
                zones["21-40"] += 1
            elif 41 <= n <= 60:
                zones["41-60"] += 1
            else:
                zones["61-80"] += 1

    hot_zone = max(zones.items(), key=lambda x: x[1])[0]
    hot_samples = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:4]
    hot_samples_str = "・".join([f"{n:02d}" for n, _ in hot_samples])
    return hot_zone, hot_samples_str, freq


def _time_bucket(minutes_step: int):
    now = datetime.now(TZ_TW)
    return int(now.timestamp() // 60) // minutes_step


def _weighted_pick_bingo(freq_dict, seed_text: str):
    rng = random.Random(seed_text)

    max_f = max(freq_dict.values()) or 1
    weights = {}
    for n in range(1, 81):
        weights[n] = (freq_dict[n] / max_f) + 0.05

    chosen = []
    pool = dict(weights)
    while len(chosen) < 5 and pool:
        total = sum(pool.values())
        r = rng.uniform(0, total)
        acc = 0
        pick = None
        for n, w in pool.items():
            acc += w
            if r <= acc:
                pick = n
                break
        if pick is None:
            pick = rng.choice(list(pool.keys()))
        chosen.append(pick)
        pool.pop(pick, None)

    chosen = sorted(chosen[:5])
    return " ".join([f"{n:02d}" for n in chosen])


def get_bingo_analysis_bundle():
    draws = fetch_recent_bingo_results(max_rows=30)
    if not draws:
        return {
            "one": "07 19 34 52 71",
            "five": "05 22 31 46 68",
            "ten": "09 18 27 55 79",
            "one_zone": "中高段",
            "five_zone": "中段",
            "ten_zone": "高段",
            "one_hot": "07・19・34・52",
            "five_hot": "05・22・31・46",
            "ten_hot": "09・18・27・55",
            "latest": None
        }

    latest = draws[0]
    d1 = draws[:1]
    d5 = draws[:5]
    d10 = draws[:10]

    zone1, hot1, freq1 = bingo_zone_summary(d1)
    zone5, hot5, freq5 = bingo_zone_summary(d5)
    zone10, hot10, freq10 = bingo_zone_summary(d10)

    seed_base = datetime.now(TZ_TW).strftime("%Y%m%d")
    one = _weighted_pick_bingo(freq1, f"{seed_base}-b1-{_time_bucket(5)}")
    five = _weighted_pick_bingo(freq5, f"{seed_base}-b5-{_time_bucket(15)}")
    ten = _weighted_pick_bingo(freq10, f"{seed_base}-b10-{_time_bucket(25)}")

    seen = {one}
    if five in seen:
        five = _weighted_pick_bingo(freq5, f"{seed_base}-b5-alt-{_time_bucket(15)}")
    seen.add(five)
    if ten in seen:
        ten = _weighted_pick_bingo(freq10, f"{seed_base}-b10-alt-{_time_bucket(25)}")

    return {
        "one": one,
        "five": five,
        "ten": ten,
        "one_zone": zone1,
        "five_zone": zone5,
        "ten_zone": zone10,
        "one_hot": hot1,
        "five_hot": hot5,
        "ten_hot": hot10,
        "latest": latest
    }


def format_bingo_1_message():
    b = get_bingo_analysis_bundle()
    quote = get_daily_quote()
    return (
        "【理性陪跑研究室｜Bingo Bingo】\n"
        f"{datetime.now(TZ_TW).strftime('%Y.%m.%d %H:%M')}\n\n"
        "▍1期短線模型\n"
        f"活躍區段：{b['one_zone']}\n"
        f"高頻樣本：{b['one_hot']}\n\n"
        "▍陪跑建議\n"
        f"{b['one']}\n\n"
        "—— 今日陪跑語錄 ——\n"
        f"{quote}\n\n"
        "（模型結構參考，非保證）"
    )


def format_bingo_5_message():
    b = get_bingo_analysis_bundle()
    quote = get_daily_quote()
    return (
        "【理性陪跑研究室｜Bingo Bingo】\n"
        f"{datetime.now(TZ_TW).strftime('%Y.%m.%d %H:%M')}\n\n"
        "▍5期節奏模型\n"
        f"活躍區段：{b['five_zone']}\n"
        f"高頻樣本：{b['five_hot']}\n\n"
        "▍陪跑建議\n"
        f"{b['five']}\n\n"
        "—— 今日陪跑語錄 ——\n"
        f"{quote}\n\n"
        "（模型結構參考，非保證）"
    )


def format_bingo_10_message():
    b = get_bingo_analysis_bundle()
    quote = get_daily_quote()
    return (
        "【理性陪跑研究室｜Bingo Bingo】\n"
        f"{datetime.now(TZ_TW).strftime('%Y.%m.%d %H:%M')}\n\n"
        "▍10期結構模型\n"
        f"活躍區段：{b['ten_zone']}\n"
        f"高頻樣本：{b['ten_hot']}\n\n"
        "▍陪跑建議\n"
        f"{b['ten']}\n\n"
        "—— 今日陪跑語錄 ——\n"
        f"{quote}\n\n"
        "（模型結構參考，非保證）"
    )


def format_bingo_evening_push():
    b = get_bingo_analysis_bundle()
    quote = get_daily_quote()
    return (
        "【理性陪跑研究室｜Bingo Bingo】\n"
        f"{datetime.now(TZ_TW).strftime('%Y.%m.%d')} 晚間模型\n\n"
        "▍1期短線模型\n"
        f"{b['one']}\n\n"
        "▍5期節奏模型\n"
        f"{b['five']}\n\n"
        "▍10期結構模型\n"
        f"{b['ten']}\n\n"
        "—— 今日陪跑語錄 ——\n"
        f"{quote}\n\n"
        "（模型結構參考，非保證）"
    )


def format_bingo_latest_push():
    b = get_bingo_analysis_bundle()
    latest = b["latest"]
    if not latest:
        return None, None

    latest_numbers = " ".join([f"{n:02d}" for n in latest["numbers"]])

    msg = (
        "【理性陪跑研究室｜Bingo Bingo 即時分析】\n\n"
        f"最新期別：{latest['period']}\n"
        f"開獎時間：{latest['time']}\n\n"
        "▍剛開獎結果\n"
        f"{latest_numbers}\n\n"
        "▍下一期短線模型\n"
        f"建議號碼：{b['one']}\n"
        f"活躍區段：{b['one_zone']}\n"
        f"高頻樣本：{b['one_hot']}\n\n"
        "—— 理性陪跑提醒 ——\n"
        "不要因為上一期改變節奏。"
    )
    return latest["period"], msg


# =========================
# Cron Routes
# =========================
@app.route("/")
def home():
    return "Bot is running."

@app.route("/cron/daily-push")
def cron_daily_push():
    secret = request.args.get("secret", "")
    if secret != CRON_SECRET:
        abort(403)

    try:
        init_db()
        members = get_active_member_ids()
        if not members:
            return "No active members", 200

        now = datetime.now(TZ_TW)
        today_key = now.strftime("%Y-%m-%d")

        if now.weekday() != 6:
            key_539 = f"daily_539_{today_key}"
            if get_push_state(key_539) is None:
                msg539 = format_539_push()
                for uid in members:
                    push_message(uid, msg539)
                set_push_state(key_539, "done")

        key_bingo = f"daily_bingo_{today_key}"
        if get_push_state(key_bingo) is None:
            msg_bingo = format_bingo_evening_push()
            for uid in members:
                push_message(uid, msg_bingo)
            set_push_state(key_bingo, "done")

        return "OK", 200
    except Exception as e:
        print("CRON_DAILY_ERROR:", repr(e))
        return "ERROR", 500


@app.route("/cron/check-bingo")
def cron_check_bingo():
    secret = request.args.get("secret", "")
    if secret != CRON_SECRET:
        abort(403)

    try:
        init_db()

        now = datetime.now(TZ_TW)
        hhmm = now.strftime("%H:%M")
        if hhmm < "07:05" or hhmm > "23:55":
            return "Outside draw hours", 200

        period, msg = format_bingo_latest_push()
        if not period or not msg:
            return "No latest bingo result", 200

        last_period = get_push_state("latest_bingo_period")
        if last_period == period:
            return "No new result", 200

        users = get_prediction_subscribers()
        for uid in users:
            push_message(uid, msg)

        set_push_state("latest_bingo_period", period)
        return "OK", 200
    except Exception as e:
        print("CRON_BINGO_ERROR:", repr(e))
        return "ERROR", 500


# =========================
# Webhook
# =========================
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
                "7) 預測分析\n"
                "8) 取消預測分析\n"
                "9) 我的到期日\n\n"
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
                    "（開通後可輸入：今日陪跑 / 賓果1期分析 / 賓果5期分析 / 賓果10期分析 / 預測分析 / 我的到期日）"
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
                reply_message(reply_token, "格式：確認 <遊戲帳號> <管理密碼>\n例：確認 123456 aaa888")
                continue

            _, game_account, secret = parts
            if secret != ADMIN_SECRET:
                reply_message(reply_token, "管理密碼錯誤。")
                continue

            target_user_id = pop_pending_user_id(game_account)
            if not target_user_id:
                reply_message(reply_token, f"找不到待確認帳號：{game_account}")
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

        if text == "預測分析":
            if not is_member(user_id):
                reply_message(reply_token, "🌿 預測分析屬於會員內容\n\n請先輸入：遊戲帳號 XXXXX")
            else:
                enable_prediction(user_id)
                reply_message(
                    reply_token,
                    "✅ 已開啟預測分析\n\n"
                    "之後若有 Bingo 最新開獎，\n"
                    "你會收到：\n"
                    "1) 剛開獎結果\n"
                    "2) 下一期分析"
                )
            continue

        if text == "取消預測分析":
            disable_prediction(user_id)
            reply_message(reply_token, "✅ 已取消預測分析推播")
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
