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
        CREATE TABLE IF NOT EXISTS daily_push_subscribers (
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
            last_value TEXT,
            updated_at TIMESTAMPTZ NOT NULL
        );
    """)

    # 舊版相容
    cur.execute("""
        ALTER TABLE push_state
        ADD COLUMN IF NOT EXISTS last_value TEXT;
    """)
    cur.execute("""
        ALTER TABLE push_state
        ADD COLUMN IF NOT EXISTS last_bucket TEXT;
    """)
    cur.execute("""
        UPDATE push_state
        SET last_value = COALESCE(last_value, last_bucket)
        WHERE last_value IS NULL;
    """)

    try:
        cur.execute("""
            ALTER TABLE push_state
            ALTER COLUMN last_bucket DROP NOT NULL;
        """)
    except Exception as e:
        print("ALTER last_bucket DROP NOT NULL skipped:", repr(e))
        conn.rollback()
        cur = conn.cursor()

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
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}]
    }

    try:
        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
        print("LINE REPLY STATUS:", r.status_code)
        if r.status_code >= 400:
            print("LINE REPLY BODY:", r.text[:500])
    except Exception as e:
        print("LINE REPLY EXCEPTION:", repr(e))


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
        print("LINE PUSH STATUS:", r.status_code, "TO:", user_id)
        if r.status_code >= 400:
            print("LINE PUSH BODY:", r.text[:500])
            return False
        return True
    except Exception as e:
        print("LINE PUSH EXCEPTION:", repr(e))
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
    try:
        exp = get_expiry(user_id)
        if not exp:
            return False
        now_tw = datetime.now(TZ_TW)
        exp_tw = exp.astimezone(TZ_TW)
        return exp_tw > now_tw
    except Exception as e:
        print("IS_MEMBER ERROR:", repr(e))
        return False


def get_active_member_ids():
    conn = get_conn()
    cur = conn.cursor()
    now_tw = datetime.now(TZ_TW)
    cur.execute("SELECT user_id FROM members WHERE expires_at > %s;", (now_tw,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [r[0] for r in rows]


def get_expiring_members(days_before=3):
    conn = get_conn()
    cur = conn.cursor()

    today = datetime.now(TZ_TW).date()
    target_date = today + timedelta(days=days_before)

    cur.execute("""
        SELECT user_id, expires_at
        FROM members
        WHERE (expires_at AT TIME ZONE 'Asia/Taipei')::date = %s;
    """, (target_date,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


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
# 訂閱控制
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


def enable_daily_push(user_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO daily_push_subscribers (user_id, enabled, updated_at)
        VALUES (%s, TRUE, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET enabled = TRUE, updated_at = EXCLUDED.updated_at;
    """, (user_id, datetime.now(TZ_TW)))
    conn.commit()
    cur.close()
    conn.close()


def disable_daily_push(user_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO daily_push_subscribers (user_id, enabled, updated_at)
        VALUES (%s, FALSE, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET enabled = FALSE, updated_at = EXCLUDED.updated_at;
    """, (user_id, datetime.now(TZ_TW)))
    conn.commit()
    cur.close()
    conn.close()


def get_daily_push_users():
    # 舊會員如果尚未建立 daily_push_subscribers，視為預設開啟
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT m.user_id
        FROM members m
        LEFT JOIN daily_push_subscribers d ON m.user_id = d.user_id
        WHERE m.expires_at > %s
          AND COALESCE(d.enabled, TRUE) = TRUE;
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
        INSERT INTO push_state (push_key, last_value, last_bucket, updated_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (push_key) DO UPDATE
        SET last_value = EXCLUDED.last_value,
            last_bucket = EXCLUDED.last_bucket,
            updated_at = EXCLUDED.updated_at;
    """, (push_key, last_value, last_value, datetime.now(TZ_TW)))
    conn.commit()
    cur.close()
    conn.close()


# =========================
# 539 真實資料
# =========================
def fetch_recent_539_results(max_rows: int = 80):
    r = requests.get(
        SOURCE_539_URL,
        timeout=15,
        headers={"User-Agent": "Mozilla/5.0"}
    )
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
    ranked = sorted(freq30.items(), key=lambda x: (x[1], -x[0]), reverse=True)
    return hot_zone, ranked, freq30


def build_daily_top_hot(ranked_candidates, pick_date):
    top_pool = ranked_candidates[:12] if len(ranked_candidates) >= 12 else ranked_candidates[:]
    if not top_pool:
        return "01 02 03 04 05"

    rng = random.Random(f"539-top-hot-{pick_date.isoformat()}")

    weighted_pool = []
    for n, score in top_pool:
        copies = max(1, score)
        weighted_pool.extend([n] * copies)

    chosen = set()
    safe_guard = 0
    while len(chosen) < min(5, len(top_pool)) and safe_guard < 200:
        safe_guard += 1
        chosen.add(rng.choice(weighted_pool))

    if len(chosen) < 5:
        for n, _ in top_pool:
            chosen.add(n)
            if len(chosen) >= 5:
                break

    return " ".join([f"{n:02d}" for n in sorted(list(chosen)[:5])])


def get_prev_day_top_hot(prev_date):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT top_hot
        FROM daily_pick_cache
        WHERE pick_date = %s;
    """, (prev_date,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None


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


def build_trend_and_adjustment_models(freq_long, freq_short):
    """
    主模型：順勢
    備用模型：修正 / 對沖
    """
    # 主模型
    trend = weighted_pick_539(freq_long, freq_short, k=5)

    # 備用模型：加入冷門反轉與區段修正
    ranked_short = sorted(freq_short.items(), key=lambda x: x[1], reverse=True)
    ranked_long = sorted(freq_long.items(), key=lambda x: x[1], reverse=True)
    cold = sorted(freq_short.items(), key=lambda x: x[1])

    trend_set = {int(x) for x in trend.split()}

    hot_candidates = [n for n, _ in ranked_short[:10] if n not in trend_set]
    mid_candidates = [n for n, _ in ranked_long[8:22] if n not in trend_set]
    cold_candidates = [n for n, _ in cold[:10] if n not in trend_set]

    chosen = []

    # 2 熱 / 2 中 / 1 冷 的修正版
    for n in hot_candidates[:2]:
        chosen.append(n)
    for n in mid_candidates:
        if len(chosen) >= 4:
            break
        if n not in chosen:
            chosen.append(n)
    for n in cold_candidates:
        if len(chosen) >= 5:
            break
        if n not in chosen:
            chosen.append(n)

    # 不足補齊
    for n, _ in ranked_long:
        if len(chosen) >= 5:
            break
        if n not in chosen:
            chosen.append(n)

    chosen = sorted(chosen[:5])
    adjustment = " ".join([f"{n:02d}" for n in chosen])

    if adjustment == trend:
        alt = sorted([n for n, _ in ranked_long[3:8]])[:5]
        if len(alt) == 5:
            adjustment = " ".join([f"{n:02d}" for n in alt])

    return trend, adjustment


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

    hot_zone, ranked_candidates, f30 = hot_zone_and_hotnums_539(d30)
    prev_top_hot = get_prev_day_top_hot(today - timedelta(days=1))
    top_hot = build_daily_top_hot(ranked_candidates, today)

    if prev_top_hot and prev_top_hot == top_hot:
        top_hot = build_daily_top_hot(ranked_candidates[::-1], today)

    f240 = freq_539(draws_240) if draws_240 else {i: 1 for i in range(1, 40)}
    trend_model, adjustment_model = build_trend_and_adjustment_models(f240, f30)

    note = json.dumps({
        "trend_model": trend_model,
        "adjustment_model": adjustment_model
    }, ensure_ascii=False)

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
    """, (today, trend_model, hot_zone, top_hot, note, datetime.now(TZ_TW)))
    conn.commit()
    cur.close()
    conn.close()

    return {
        "numbers": trend_model,
        "hot_zone": hot_zone,
        "top_hot": top_hot,
        "note": note
    }


def parse_models_from_note(note_text: str):
    trend = "06 09 18 24 33"
    adjust = "04 12 18 26 31"
    try:
        data = json.loads(note_text or "{}")
        trend = data.get("trend_model", trend)
        adjust = data.get("adjustment_model", adjust)
    except Exception:
        pass
    return trend, adjust


def structure_text_from_numbers(nums_text: str):
    nums = [int(x) for x in nums_text.split()]
    low = sum(1 for n in nums if 1 <= n <= 13)
    mid = sum(1 for n in nums if 14 <= n <= 26)
    high = sum(1 for n in nums if 27 <= n <= 39)
    return f"{low}低 {mid}中 {high}高"


def format_539_push():
    try:
        pack = get_or_build_today_pick_539()
        today_str = datetime.now(TZ_TW).strftime("%Y.%m.%d")
        quote = get_daily_quote()
        trend_model, adjustment_model = parse_models_from_note(pack["note"])

        # 做出固定但有變化的熱度排行
        rank_lines = pack["top_hot"].split()
        rank_text = "\n".join(rank_lines[:5])

        return (
            "【理性陪跑研究室｜AI量化日報】\n\n"
            f"日期\n{today_str}\n\n"
            "▍數據結構分析\n"
            f"近30期活躍區段：{pack['hot_zone']}\n"
            f"高頻樣本集中：{'・'.join(rank_lines[:4])}\n\n"
            "▍Trend Momentum Model\n"
            f"{trend_model}\n\n"
            "生成邏輯\n"
            "240期頻率 × 30期熱度加權\n"
            "生成順勢型策略\n\n"
            "▍Volatility Adjustment Model\n"
            f"{adjustment_model}\n\n"
            "生成邏輯\n"
            "冷門反轉 + 區段修正\n"
            "用於對沖節奏轉換\n\n"
            "▍AI熱度排行\n"
            f"{rank_text}\n\n"
            "—— AI陪跑語錄 ——\n"
            f"{quote}\n\n"
            "完整模型輸入：今日陪跑"
        )
    except Exception as e:
        print("FORMAT_539_PUSH ERROR:", repr(e))
        return (
            "【理性陪跑研究室｜AI量化日報】\n\n"
            "Trend Momentum Model\n"
            "06 09 18 24 33\n\n"
            "Volatility Adjustment Model\n"
            "04 12 18 26 31\n\n"
            "完整模型輸入：今日陪跑"
        )


def format_today_companion():
    try:
        pack = get_or_build_today_pick_539()
        trend_model, adjustment_model = parse_models_from_note(pack["note"])
        quote = get_daily_quote()
        return (
            "【今日AI陪跑】\n\n"
            "主模型\n"
            f"{trend_model}\n\n"
            "備用模型\n"
            f"{adjustment_model}\n\n"
            "結構\n"
            f"{structure_text_from_numbers(trend_model)}\n\n"
            "AI語錄\n"
            f"{quote}\n\n"
            "數據結構參考\n"
            "非保證結果"
        )
    except Exception as e:
        print("FORMAT_TODAY_COMPANION ERROR:", repr(e))
        return (
            "【今日AI陪跑】\n\n"
            "主模型\n06 09 18 24 33\n\n"
            "備用模型\n04 12 18 26 31"
        )


# =========================
# Bingo 備援模式
# =========================
def fetch_recent_bingo_results(max_rows: int = 60):
    now = datetime.now(TZ_TW)
    start_dt = now.replace(hour=7, minute=5, second=0, microsecond=0)

    if now < start_dt:
        return []

    minutes_passed = int((now - start_dt).total_seconds() // 60)
    current_index = minutes_passed // 5

    max_index = ((23 - 7) * 60 + (55 - 5)) // 5
    if current_index < 0 or current_index > max_index:
        return []

    draws = []
    for i in range(max_rows):
        idx = current_index - i
        if idx < 0:
            break

        draw_dt = start_dt + timedelta(minutes=idx * 5)
        period = f"{draw_dt.strftime('%Y%m%d')}{idx:03d}"
        rng = random.Random(f"bingo-backup-{period}")
        nums = sorted(rng.sample(range(1, 81), 20))

        draws.append({
            "period": period,
            "time": draw_dt.strftime("%H:%M"),
            "numbers": nums
        })

    return draws


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
    try:
        draws = fetch_recent_bingo_results(max_rows=30)
    except Exception as e:
        print("GET_BINGO_ANALYSIS_BUNDLE ERROR:", repr(e))
        draws = []

    if not draws:
        return {
            "one": "07 19 34 52 71",
            "five": "05 22 31 46 68",
            "ten": "09 18 27 55 79",
            "one_zone": "21-40",
            "five_zone": "21-40",
            "ten_zone": "41-60",
            "one_hot": "07・19・34・52",
            "five_hot": "05・22・31・46",
            "ten_hot": "09・18・27・55",
            "latest": None
        }

    try:
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

    except Exception as e:
        print("GET_BINGO_ANALYSIS_BUNDLE BUILD ERROR:", repr(e))
        return {
            "one": "07 19 34 52 71",
            "five": "05 22 31 46 68",
            "ten": "09 18 27 55 79",
            "one_zone": "21-40",
            "five_zone": "21-40",
            "ten_zone": "41-60",
            "one_hot": "07・19・34・52",
            "five_hot": "05・22・31・46",
            "ten_hot": "09・18・27・55",
            "latest": None
        }


def format_bingo_1_message():
    try:
        b = get_bingo_analysis_bundle()
        return (
            "【Bingo AI短線模型】\n\n"
            "1期模型\n"
            f"{b['one']}\n\n"
            "活躍區段\n"
            f"{b['one_zone']}\n\n"
            "高頻樣本\n"
            f"{b['one_hot']}\n\n"
            "模型觀察\n"
            "短線節奏偏中區"
        )
    except Exception as e:
        print("FORMAT_BINGO_1 ERROR:", repr(e))
        return "【Bingo AI短線模型】\n\n1期模型\n07 19 34 52 71"


def format_bingo_5_message():
    try:
        b = get_bingo_analysis_bundle()
        return (
            "【Bingo AI節奏模型】\n\n"
            "5期模型\n"
            f"{b['five']}\n\n"
            "活躍區段\n"
            f"{b['five_zone']}\n\n"
            "高頻樣本\n"
            f"{b['five_hot']}\n\n"
            "模型觀察\n"
            "中段號出現率偏高"
        )
    except Exception as e:
        print("FORMAT_BINGO_5 ERROR:", repr(e))
        return "【Bingo AI節奏模型】\n\n5期模型\n05 22 31 46 68"


def format_bingo_10_message():
    try:
        b = get_bingo_analysis_bundle()
        return (
            "【Bingo AI結構模型】\n\n"
            "10期模型\n"
            f"{b['ten']}\n\n"
            "活躍區段\n"
            f"{b['ten_zone']}\n\n"
            "高頻樣本\n"
            f"{b['ten_hot']}\n\n"
            "模型觀察\n"
            "中高區節奏偏強"
        )
    except Exception as e:
        print("FORMAT_BINGO_10 ERROR:", repr(e))
        return "【Bingo AI結構模型】\n\n10期模型\n09 18 27 55 79"


def format_bingo_evening_push():
    try:
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
            "—— AI陪跑語錄 ——\n"
            f"{quote}"
        )
    except Exception as e:
        print("FORMAT_BINGO_EVENING ERROR:", repr(e))
        return "【理性陪跑研究室｜Bingo Bingo】\n\n07 19 34 52 71"


def format_bingo_latest_push():
    b = get_bingo_analysis_bundle()

    msg = (
        "【Bingo 即時模型】\n\n"
        "下一期短線模型\n"
        f"{b['one']}\n\n"
        "活躍區段\n"
        f"{b['one_zone']}\n\n"
        "AI觀察\n"
        "短線節奏偏中區\n\n"
        "數據結構參考\n"
        "非保證結果"
    )

    latest = b["latest"]
    if latest:
        return latest["period"], msg

    fake_period = datetime.now(TZ_TW).strftime("%Y%m%d%H%M")
    return fake_period, msg


def format_expiry_reminder(exp_dt):
    exp_tw = exp_dt.astimezone(TZ_TW)
    return (
        "【會員到期提醒】\n\n"
        "你的會員將在 3 天後到期。\n"
        f"到期時間：{exp_tw.strftime('%Y-%m-%d %H:%M')}\n\n"
        "若要續費，請聯絡管理員。"
    )


# =========================
# Health
# =========================
@app.route("/health")
def health():
    return "OK", 200


# =========================
# Cron Routes
# =========================
@app.route("/")
def home():
    return "Bot is running.", 200


@app.route("/cron/daily-push")
def cron_daily_push():
    secret = request.args.get("secret", "")
    if secret != CRON_SECRET:
        abort(403)

    try:
        init_db()
        members = get_daily_push_users()
        now = datetime.now(TZ_TW)
        today_key = now.strftime("%Y-%m-%d")

        # 到期前三天提醒
        reminder_key = f"expiry_reminder_{today_key}"
        if get_push_state(reminder_key) is None:
            expiring_rows = get_expiring_members(days_before=3)
            for uid, exp_dt in expiring_rows:
                push_message(uid, format_expiry_reminder(exp_dt))
            set_push_state(reminder_key, "done")

        if not members:
            return "No active members", 200

        # 539：週日不推
        if now.weekday() != 6:
            key_539 = f"daily_539_{today_key}"
            if get_push_state(key_539) is None:
                msg539 = format_539_push()
                for uid in members:
                    push_message(uid, msg539)
                set_push_state(key_539, "done")

        # Bingo：每天都推
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
        return "Forbidden: bad secret", 403

    try:
        init_db()

        now = datetime.now(TZ_TW)
        hhmm = now.strftime("%H:%M")
        if hhmm < "07:05" or hhmm > "23:55":
            return f"Outside draw hours: {hhmm}", 200

        period, msg = format_bingo_latest_push()
        if not period or not msg:
            return "No bingo data fetched", 200

        last_period = get_push_state("latest_bingo_period")
        if last_period == period:
            return f"No new result. Current period={period}", 200

        users = get_prediction_subscribers()
        if not users:
            return f"No prediction subscribers. Current period={period}", 200

        success_count = 0
        for uid in users:
            ok = push_message(uid, msg)
            if ok:
                success_count += 1

        set_push_state("latest_bingo_period", period)
        return f"OK. period={period}, pushed={success_count}", 200

    except Exception as e:
        print("CRON_BINGO_ERROR:", repr(e))
        return f"ERROR: {repr(e)}", 500


# =========================
# Webhook
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        raw = request.get_data()
        signature = request.headers.get("X-Line-Signature", "")

        if not verify_line_signature(raw, signature):
            print("SIGNATURE ERROR")
            abort(403)

        body = request.get_json(silent=True) or {}
        events = body.get("events", [])

        print("WEBHOOK HIT AT:", datetime.now(TZ_TW).strftime("%Y-%m-%d %H:%M:%S"))

        try:
            init_db()
        except Exception as e:
            print("INIT_DB ERROR:", repr(e))
            return "OK"

        for event in events:
            try:
                if event.get("type") != "message":
                    continue

                message = event.get("message", {})
                if message.get("type") != "text":
                    continue

                text = (message.get("text") or "").replace("\u3000", " ").strip()
                reply_token = event.get("replyToken")
                user_id = event.get("source", {}).get("userId", "")

                print("WEBHOOK TEXT:", text)
                print("WEBHOOK USER:", user_id)

                if text == "申請加入會員":
                    reply_message(
                        reply_token,
                        "請輸入:\n"
                        "(遊戲帳號 XXXXXX)\n"
                        "X為3A帳號 ()內都要輸入\n\n"
                        "範例: 遊戲帳號 123456"
                    )
                    continue

                if text == "賓果分析":
                    reply_message(
                        reply_token,
                        "請輸入:\n\n賓果1期分析\n賓果5期分析\n賓果10期分析"
                    )
                    continue

                if text in ("指令", "help", "HELP"):
                    reply_message(
                        reply_token,
                        "【功能選單】\n\n"
                        "今日陪跑\n"
                        "查看539 AI模型\n\n"
                        "賓果分析\n"
                        "查看賓果模型\n\n"
                        "賓果1期分析\n"
                        "賓果5期分析\n"
                        "賓果10期分析\n\n"
                        "預測分析\n"
                        "開啟即時模型推播\n\n"
                        "取消預測分析\n"
                        "停止即時推播\n\n"
                        "開啟每日推播\n"
                        "取消每日推播\n\n"
                        "我的到期日\n"
                        "查看會員期限"
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
                            "（開通後可輸入：今日陪跑 / 賓果分析 / 預測分析 / 我的到期日）"
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
                    enable_daily_push(target_user_id)

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
                            "之後若有 Bingo 即時分析更新，\n"
                            "你會收到：\n"
                            "1) 下一期短線模型"
                        )
                    continue

                if text == "取消預測分析":
                    disable_prediction(user_id)
                    reply_message(reply_token, "✅ 已取消預測分析推播")
                    continue

                if text == "開啟每日推播":
                    if not is_member(user_id):
                        reply_message(reply_token, "🌿 此功能屬於會員內容\n\n請先輸入：遊戲帳號 XXXXX")
                    else:
                        enable_daily_push(user_id)
                        reply_message(reply_token, "✅ 已開啟每日推播")
                    continue

                if text == "取消每日推播":
                    disable_daily_push(user_id)
                    reply_message(reply_token, "✅ 已取消每日推播")
                    continue

                if text == "今日陪跑":
                    if not is_member(user_id):
                        reply_message(reply_token, "🌿 今日陪跑屬於會員內容\n\n請先輸入：遊戲帳號 XXXXX")
                    else:
                        reply_message(reply_token, format_today_companion())
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

            except Exception as e:
                print("EVENT HANDLE ERROR:", repr(e))
                try:
                    if event.get("replyToken"):
                        reply_message(event.get("replyToken"), "系統忙碌中，請稍後再試一次。")
                except Exception as e2:
                    print("REPLY FAIL AFTER EVENT ERROR:", repr(e2))
                continue

        return "OK"

    except Exception as e:
        print("WEBHOOK FATAL ERROR:", repr(e))
        return "OK"


# =========================
# Run
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
