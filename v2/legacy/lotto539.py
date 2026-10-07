from flask import Flask, request, abort
import os
import json
import re
import hmac
import base64
import hashlib
import random
import requests
import psycopg2
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone, date
from itertools import combinations

app = Flask(__name__)
APP_VERSION = "2026-10-02-V2-locked"

# ========= 環境變數 =========
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN", "").strip()
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET", "").strip()
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "1234").strip()
CRON_SECRET = os.getenv("CRON_SECRET", "push8899").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ADMIN_USER_IDS = [x.strip() for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip()]

TZ_TW = timezone(timedelta(hours=8))
HTTP = requests.Session()

SOURCE_539_URL = "https://www.pilio.idv.tw/lto539/list539BIG.asp"
SOURCE_BINGO_OFFICIAL_URL = "https://www.taiwanlottery.com/lotto/result/bingo_bingo"
SOURCE_BINGO_PILIO_URL = "https://www.pilio.idv.tw/bingo/list.asp"

MAX_539_STALE_DAYS = 10
_DB_READY = False

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
]


def now_tw():
    return datetime.now(TZ_TW)


def today_tw():
    return now_tw().date()


def log(*args):
    print(*args, flush=True)


def get_daily_quote():
    return QUOTES[today_tw().toordinal() % len(QUOTES)]


# ========= DB =========
@contextmanager
def db_cursor(commit=False):
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL 未設定")
    conn = psycopg2.connect(DATABASE_URL, sslmode="require")
    cur = conn.cursor()
    try:
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def init_db():
    with db_cursor(commit=True) as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS members (
                user_id TEXT PRIMARY KEY,
                expires_at TIMESTAMPTZ NOT NULL
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS free_trials (
                user_id TEXT PRIMARY KEY,
                started_at TIMESTAMPTZ NOT NULL,
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
            CREATE TABLE IF NOT EXISTS model_results (
                result_date DATE PRIMARY KEY,
                motherboard TEXT NOT NULL,
                actual_numbers TEXT,
                hit_count INTEGER,
                created_at TIMESTAMPTZ NOT NULL
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bingo_draws (
                period TEXT PRIMARY KEY,
                draw_date DATE,
                draw_time TEXT,
                numbers TEXT NOT NULL,
                super_number TEXT,
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
        cur.execute("ALTER TABLE push_state ADD COLUMN IF NOT EXISTS last_bucket TEXT;")
        cur.execute("ALTER TABLE push_state ADD COLUMN IF NOT EXISTS last_value TEXT;")


def ensure_db_ready():
    global _DB_READY
    if _DB_READY:
        return
    init_db()
    _DB_READY = True


# ========= LINE =========
def verify_line_signature(raw_body: bytes, signature: str) -> bool:
    if not CHANNEL_SECRET:
        return False
    mac = hmac.new(CHANNEL_SECRET.encode("utf-8"), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(mac).decode("utf-8")
    return hmac.compare_digest(expected, signature or "")


def line_headers():
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
    }


def reply_message(reply_token: str, text: str):
    if not CHANNEL_ACCESS_TOKEN:
        log("CHANNEL_ACCESS_TOKEN empty")
        return
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": str(text)[:5000]}]
    }
    try:
        r = HTTP.post(
            "https://api.line.me/v2/bot/message/reply",
            headers=line_headers(),
            json=payload,
            timeout=10
        )
        log("LINE REPLY:", r.status_code)
        if r.status_code >= 400:
            log("LINE REPLY BODY:", r.text[:500])
    except Exception as e:
        log("LINE REPLY ERROR:", repr(e))


def push_message(user_id: str, text: str) -> bool:
    if not CHANNEL_ACCESS_TOKEN:
        log("CHANNEL_ACCESS_TOKEN empty")
        return False
    payload = {"to": user_id, "messages": [{"type": "text", "text": str(text)[:5000]}]}
    try:
        r = HTTP.post(
            "https://api.line.me/v2/bot/message/push",
            headers=line_headers(),
            json=payload,
            timeout=10
        )
        log("LINE PUSH:", r.status_code, user_id)
        if r.status_code >= 400:
            log("LINE PUSH BODY:", r.text[:500])
            return False
        return True
    except Exception as e:
        log("LINE PUSH ERROR:", repr(e))
        return False


def reply_template(reply_token, alt_text, title, text, actions):
    payload = {
        "replyToken": reply_token,
        "messages": [{
            "type": "template",
            "altText": alt_text,
            "template": {
                "type": "buttons",
                "title": title[:40],
                "text": text[:60],
                "actions": actions[:4],
            }
        }]
    }
    try:
        r = HTTP.post(
            "https://api.line.me/v2/bot/message/reply",
            headers=line_headers(),
            json=payload,
            timeout=10
        )
        log("LINE TEMPLATE:", r.status_code)
        if r.status_code >= 400:
            log("LINE TEMPLATE BODY:", r.text[:500])
    except Exception as e:
        log("LINE TEMPLATE ERROR:", repr(e))


def reply_bingo_menu(reply_token):
    reply_template(
        reply_token,
        "Bingo分析選單",
        "Bingo 分析",
        "請選擇期數",
        [
            {"type": "message", "label": "1期", "text": "1期"},
            {"type": "message", "label": "5期", "text": "5期"},
            {"type": "message", "label": "10期", "text": "10期"},
        ],
    )


def reply_bet_plan_menu(reply_token):
    reply_template(
        reply_token,
        "539點數配置",
        "539 點數配置",
        "請選擇配置模式",
        [
            {"type": "message", "label": "穩健1000", "text": "穩健 1000"},
            {"type": "message", "label": "均衡3000", "text": "均衡 3000"},
            {"type": "message", "label": "爆發5000", "text": "爆發 5000"},
            {"type": "message", "label": "爆發10000", "text": "爆發 10000"},
        ],
    )


# ========= 權限 / 會員 =========
def is_admin(user_id, secret=""):
    if user_id and ADMIN_USER_IDS and user_id in ADMIN_USER_IDS:
        return True
    return secret == ADMIN_SECRET


def get_expiry(user_id):
    with db_cursor() as cur:
        cur.execute("SELECT expires_at FROM members WHERE user_id=%s;", (user_id,))
        row = cur.fetchone()
    return row[0] if row else None


def is_member(user_id):
    try:
        exp = get_expiry(user_id)
        return bool(exp and exp.astimezone(TZ_TW) > now_tw())
    except Exception as e:
        log("IS_MEMBER ERROR:", repr(e))
        return False


def set_expiry_plus_days(user_id, days=30):
    target_date = (now_tw() + timedelta(days=days)).date()
    exp = datetime.strptime(str(target_date), "%Y-%m-%d").replace(
        hour=23, minute=59, second=59, tzinfo=TZ_TW
    )
    with db_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO members (user_id, expires_at)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET expires_at=EXCLUDED.expires_at;
        """, (user_id, exp))
    return exp


def has_used_free_trial(user_id):
    with db_cursor() as cur:
        cur.execute("SELECT 1 FROM free_trials WHERE user_id=%s;", (user_id,))
        row = cur.fetchone()
    return row is not None


def start_free_trial(user_id, hours=24):
    if not user_id:
        return None, "no_user"
    if is_member(user_id):
        return get_expiry(user_id), "already_member"
    if has_used_free_trial(user_id):
        return None, "used"

    started = now_tw()
    exp = started + timedelta(hours=hours)
    with db_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO members (user_id, expires_at)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET expires_at=EXCLUDED.expires_at;
        """, (user_id, exp))
        cur.execute("""
            INSERT INTO free_trials (user_id, started_at, expires_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING;
        """, (user_id, started, exp))
        cur.execute("""
            INSERT INTO daily_push_subscribers (user_id, enabled, updated_at)
            VALUES (%s, TRUE, %s)
            ON CONFLICT (user_id) DO UPDATE SET enabled=TRUE, updated_at=EXCLUDED.updated_at;
        """, (user_id, started))
    return exp, "opened"


def save_pending_account(game_account, user_id):
    with db_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO pending_accounts (game_account, user_id, created_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (game_account) DO UPDATE
            SET user_id=EXCLUDED.user_id, created_at=EXCLUDED.created_at;
        """, (game_account, user_id, now_tw()))


def pop_pending_user_id(game_account):
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT user_id FROM pending_accounts WHERE game_account=%s;", (game_account,))
        row = cur.fetchone()
        if not row:
            return None
        uid = row[0]
        cur.execute("DELETE FROM pending_accounts WHERE game_account=%s;", (game_account,))
    return uid


def get_latest_pending(limit=50):
    with db_cursor() as cur:
        cur.execute("""
            SELECT game_account, user_id, created_at
            FROM pending_accounts
            ORDER BY created_at DESC
            LIMIT %s;
        """, (limit,))
        rows = cur.fetchall()
    return rows


def enable_daily_push(user_id):
    with db_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO daily_push_subscribers (user_id, enabled, updated_at)
            VALUES (%s, TRUE, %s)
            ON CONFLICT (user_id) DO UPDATE SET enabled=TRUE, updated_at=EXCLUDED.updated_at;
        """, (user_id, now_tw()))


def disable_daily_push(user_id):
    with db_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO daily_push_subscribers (user_id, enabled, updated_at)
            VALUES (%s, FALSE, %s)
            ON CONFLICT (user_id) DO UPDATE SET enabled=FALSE, updated_at=EXCLUDED.updated_at;
        """, (user_id, now_tw()))


def enable_prediction(user_id):
    with db_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO prediction_subscribers (user_id, enabled, updated_at)
            VALUES (%s, TRUE, %s)
            ON CONFLICT (user_id) DO UPDATE SET enabled=TRUE, updated_at=EXCLUDED.updated_at;
        """, (user_id, now_tw()))


def disable_prediction(user_id):
    with db_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO prediction_subscribers (user_id, enabled, updated_at)
            VALUES (%s, FALSE, %s)
            ON CONFLICT (user_id) DO UPDATE SET enabled=FALSE, updated_at=EXCLUDED.updated_at;
        """, (user_id, now_tw()))


def get_prediction_subscribers():
    with db_cursor() as cur:
        cur.execute("""
            SELECT p.user_id
            FROM prediction_subscribers p
            JOIN members m ON p.user_id=m.user_id
            WHERE p.enabled=TRUE AND m.expires_at>%s;
        """, (now_tw(),))
        rows = cur.fetchall()
    return [r[0] for r in rows]


def get_daily_push_users():
    with db_cursor() as cur:
        cur.execute("""
            SELECT m.user_id
            FROM members m
            LEFT JOIN daily_push_subscribers d ON m.user_id=d.user_id
            WHERE m.expires_at>%s AND COALESCE(d.enabled, TRUE)=TRUE;
        """, (now_tw(),))
        rows = cur.fetchall()
    return [r[0] for r in rows]


def get_expiring_members(days_before=3):
    target = today_tw() + timedelta(days=days_before)
    with db_cursor() as cur:
        cur.execute("""
            SELECT user_id, expires_at
            FROM members
            WHERE (expires_at AT TIME ZONE 'Asia/Taipei')::date=%s;
        """, (target,))
        rows = cur.fetchall()
    return rows


def get_push_state(push_key):
    with db_cursor() as cur:
        cur.execute("SELECT last_value FROM push_state WHERE push_key=%s;", (push_key,))
        row = cur.fetchone()
    return row[0] if row else None


def set_push_state(push_key, last_value):
    with db_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO push_state (push_key, last_value, last_bucket, updated_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (push_key) DO UPDATE
            SET last_value=EXCLUDED.last_value,
                last_bucket=EXCLUDED.last_bucket,
                updated_at=EXCLUDED.updated_at;
        """, (push_key, last_value, last_value, now_tw()))


# ========= 通用模型工具 =========
def fmt_nums(nums):
    return " ".join(f"{int(n):02d}" for n in sorted(set(nums)))


def parse_nums_text(text):
    nums = []
    for x in re.findall(r"\d{1,2}", text or ""):
        n = int(x)
        nums.append(n)
    return nums


def normalize(score):
    vals = list(score.values())
    if not vals:
        return {}
    mn, mx = min(vals), max(vals)
    if mx == mn:
        return {k: 0.5 for k in score}
    return {k: (v - mn) / (mx - mn) for k, v in score.items()}


def weighted_sample(items, weights, k, seed):
    rng = random.Random(seed)
    pool = list(dict.fromkeys(items))
    chosen = []
    while pool and len(chosen) < k:
        total = sum(max(0.001, weights.get(n, 0.001)) for n in pool)
        r = rng.uniform(0, total)
        acc = 0
        pick = pool[-1]
        for n in pool:
            acc += max(0.001, weights.get(n, 0.001))
            if r <= acc:
                pick = n
                break
        chosen.append(pick)
        pool.remove(pick)
    return chosen


# ========= 539 真實資料 =========
def fetch_recent_539_results(max_rows=100):
    r = HTTP.get(SOURCE_539_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    r.encoding = r.apparent_encoding or "utf-8"
    html = r.text.replace("&nbsp;", " ").replace("\u3000", " ")

    out = []
    seen = set()

    pattern = re.compile(
        r"開獎日期[:：]\s*(\d{4})/(\d{1,2})/(\d{1,2}).{0,160}?"
        r"(\d{2})[,\s]+(\d{2})[,\s]+(\d{2})[,\s]+(\d{2})[,\s]+(\d{2})",
        re.S
    )
    for m in pattern.finditer(html):
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            nums = [int(m.group(i)) for i in range(4, 9)]
            if len(set(nums)) != 5 or not all(1 <= n <= 39 for n in nums):
                continue
            if d in seen:
                continue
            seen.add(d)
            out.append((d, fmt_nums(nums)))
            if len(out) >= max_rows:
                return out
        except Exception:
            continue

    dates = list(re.finditer(r"(\d{4})/(\d{1,2})/(\d{1,2})", html))
    for idx, dm in enumerate(dates):
        try:
            d = date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
            if d in seen:
                continue
            start = dm.end()
            end = dates[idx + 1].start() if idx + 1 < len(dates) else start + 800
            chunk = html[start:end]
            nums = []
            for x in re.findall(r"\b\d{2}\b", chunk):
                n = int(x)
                if 1 <= n <= 39 and n not in nums:
                    nums.append(n)
                if len(nums) == 5:
                    break
            if len(nums) == 5:
                seen.add(d)
                out.append((d, fmt_nums(nums)))
                if len(out) >= max_rows:
                    break
        except Exception:
            continue

    return out


def upsert_539_draws(rows):
    if not rows:
        return
    with db_cursor(commit=True) as cur:
        cur.executemany("""
            INSERT INTO lotto_539_draws (draw_date, numbers)
            VALUES (%s, %s)
            ON CONFLICT (draw_date) DO UPDATE SET numbers=EXCLUDED.numbers;
        """, rows)


def ensure_latest_539_in_db():
    try:
        rows = fetch_recent_539_results(max_rows=100)
        upsert_539_draws(rows)
    except Exception as e:
        log("FETCH_539_ERROR:", repr(e))


def load_539_draws(limit=240):
    with db_cursor() as cur:
        cur.execute("""
            SELECT draw_date, numbers
            FROM lotto_539_draws
            ORDER BY draw_date DESC
            LIMIT %s;
        """, (limit,))
        rows = cur.fetchall()
    parsed = []
    for d, s in rows:
        nums = [int(x) for x in s.split()]
        if len(nums) == 5:
            parsed.append((d, nums))
    return parsed


def is_539_data_fresh(draws=None):
    if draws is None:
        draws = load_539_draws(limit=1)
    if not draws:
        return False, None, 9999
    latest = draws[0][0]
    stale_days = (today_tw() - latest).days
    return stale_days <= MAX_539_STALE_DAYS, latest, stale_days


def freq_539(draws):
    f = {i: 0 for i in range(1, 40)}
    for _, nums in draws:
        for n in nums:
            f[n] += 1
    return f


def gap_539(draws):
    gap = {i: len(draws) + 5 for i in range(1, 40)}
    for idx, (_, nums) in enumerate(draws):
        for n in nums:
            if gap[n] == len(draws) + 5:
                gap[n] = idx
    score = {}
    for n, g in gap.items():
        if g <= 1:
            score[n] = 0.10
        elif 2 <= g <= 5:
            score[n] = 0.55
        elif 6 <= g <= 14:
            score[n] = 1.00
        elif 15 <= g <= 28:
            score[n] = 0.78
        else:
            score[n] = 0.62
    return score, gap


def zone_539(n):
    if 1 <= n <= 13:
        return "低"
    if 14 <= n <= 26:
        return "中"
    return "高"


def structure_539(nums_text):
    nums = [int(x) for x in nums_text.split()]
    low = sum(1 for n in nums if 1 <= n <= 13)
    mid = sum(1 for n in nums if 14 <= n <= 26)
    high = sum(1 for n in nums if 27 <= n <= 39)
    return f"低區{low}｜中區{mid}｜高區{high}"


def hot_zone_539(draws):
    zone_count = {"1-13": 0, "14-26": 0, "27-39": 0}
    f = freq_539(draws)
    for _, nums in draws:
        for n in nums:
            if n <= 13:
                zone_count["1-13"] += 1
            elif n <= 26:
                zone_count["14-26"] += 1
            else:
                zone_count["27-39"] += 1
    hot_zone = max(zone_count.items(), key=lambda x: x[1])[0] if draws else "資料不足"
    ranked = sorted(f.items(), key=lambda x: (x[1], -x[0]), reverse=True)
    return hot_zone, ranked



def recent_539_performance_state():
    """依最近母盤命中狀態切換模型。
    - recovery：最近母盤命中偏低，隔日加強反轉/冷號/遺漏值。
    - normal：一般狀態。
    """
    try:
        with db_cursor() as cur:
            cur.execute("""
                SELECT hit_count
                FROM model_results
                WHERE hit_count IS NOT NULL
                ORDER BY result_date DESC
                LIMIT 5;
            """)
            rows = cur.fetchall()
        vals = [int(r[0]) for r in rows if r and r[0] is not None]
        if len(vals) >= 3 and (sum(vals) / len(vals)) < 2.0:
            return "recovery"
        return "normal"
    except Exception as e:
        log("RECENT_539_PERFORMANCE_STATE_ERROR:", repr(e))
        return "normal"


def ensure_len_unique(nums, source, need):
    out = []
    for n in nums:
        if 1 <= int(n) <= 39 and int(n) not in out:
            out.append(int(n))
        if len(out) >= need:
            return out[:need]
    for n in source:
        if 1 <= int(n) <= 39 and int(n) not in out:
            out.append(int(n))
        if len(out) >= need:
            return out[:need]
    for n in range(1, 40):
        if n not in out:
            out.append(n)
        if len(out) >= need:
            return out[:need]
    return out[:need]

def build_539_models(draws):
    """539 強化縮盤版：
    母盤 10 碼、2星 3 碼、3星 6 碼、4星 7 碼。
    最近母盤命中偏低時，自動切換 recovery 模式，加重遺漏值/冷號與反轉補位。
    """
    mode = recent_539_performance_state()
    seed = f"539-tight-{today_tw().isoformat()}-{mode}"

    if not draws:
        raise ValueError("539 真實資料不足")

    d30, d60, d120, d240 = draws[:30], draws[:60], draws[:120], draws[:240]
    f30, f60, f120, f240 = freq_539(d30), freq_539(d60), freq_539(d120), freq_539(d240)
    gap_score, gap_raw = gap_539(d240)

    nf30, nf60, nf120, nf240 = normalize(f30), normalize(f60), normalize(f120), normalize(f240)
    ngap = normalize(gap_score)

    latest_set = set(draws[0][1])
    prev3 = set()
    for _, nums in draws[:3]:
        prev3.update(nums)

    score = {}
    for n in range(1, 40):
        repeat_penalty = -0.12 if n in latest_set else 0
        short_repeat_penalty = -0.05 if n in prev3 else 0
        if mode == "recovery":
            score[n] = (
                0.22 * nf30[n] +
                0.12 * nf60[n] +
                0.12 * nf120[n] +
                0.06 * nf240[n] +
                0.38 * ngap[n] +
                repeat_penalty +
                short_repeat_penalty
            )
        else:
            score[n] = (
                0.36 * nf30[n] +
                0.18 * nf60[n] +
                0.14 * nf120[n] +
                0.06 * nf240[n] +
                0.18 * ngap[n] +
                repeat_penalty
            )

    ranked = [n for n, _ in sorted(score.items(), key=lambda x: x[1], reverse=True)]
    cold_ranked = [n for n, _ in sorted(gap_raw.items(), key=lambda x: x[1], reverse=True)]

    pool = ranked[:24]
    for n in cold_ranked[:6 if mode == "recovery" else 3]:
        if n not in pool:
            pool.append(n)

    mother = weighted_sample(pool, score, 10, seed)

    # 區段平衡：10碼至少低/中/高各2顆，避免偏盤太極端。
    for predicate in [lambda x: 1 <= x <= 13, lambda x: 14 <= x <= 26, lambda x: 27 <= x <= 39]:
        while sum(1 for n in mother if predicate(n)) < 2:
            add = next((n for n in ranked if predicate(n) and n not in mother), None)
            if add is None:
                break
            # 移除目前最多區裡分數最低的號碼
            groups = [
                [x for x in mother if x <= 13],
                [x for x in mother if 14 <= x <= 26],
                [x for x in mother if x >= 27],
            ]
            over = max(groups, key=len)
            remove = min(over, key=lambda x: score.get(x, 0))
            mother.remove(remove)
            mother.append(add)

    mother = ensure_len_unique(sorted(mother), ranked + cold_ranked, 10)
    mb_ranked = sorted(mother, key=lambda n: score.get(n, 0), reverse=True)

    # 2星主軸：3碼，盡量跨區，保持集中。
    stable = []
    used_zone = set()
    for n in mb_ranked:
        z = zone_539(n)
        if z not in used_zone:
            stable.append(n)
            used_zone.add(z)
        if len(stable) >= 3:
            break
    stable = ensure_len_unique(stable, mb_ranked, 3)

    # 3星主攻：6碼，主軸 + 高分延伸。
    attack = ensure_len_unique(stable, mb_ranked, 6)

    # 4星爆發：7碼，主攻 + 1~2 顆冷號補位。
    burst = list(attack)
    for n in cold_ranked:
        if n in mother and n not in burst:
            burst.append(n)
        if len(burst) >= 7:
            break
    burst = ensure_len_unique(burst, mb_ranked + cold_ranked, 7)

    cold_note_nums = [n for n in mother if gap_raw.get(n, 0) >= 8]
    cold_note = fmt_nums(cold_note_nums[:4]) if cold_note_nums else fmt_nums(cold_ranked[:3])

    # V2 diagnostics: expose why each motherboard number is present without changing the pick algorithm.
    score_norm = normalize(score)
    diagnostics = {}
    for n in mother:
        tags = []
        if f30.get(n, 0) >= sorted(f30.values(), reverse=True)[9]:
            tags.append("短期熱")
        if gap_raw.get(n, 0) >= 8:
            tags.append("遺漏回補")
        if n not in prev3:
            tags.append("避短期重複")
        diagnostics[str(n)] = {
            "score": round(score_norm.get(n, 0) * 100),
            "freq30": f30.get(n, 0),
            "freq60": f60.get(n, 0),
            "gap": gap_raw.get(n, 0),
            "zone": zone_539(n),
            "tags": tags[:3],
        }
    core5 = sorted(mother, key=lambda n: score.get(n, 0), reverse=True)[:5]
    top3 = sorted(mother, key=lambda n: score.get(n, 0), reverse=True)[:3]

    latest_nums = draws[0][1]
    head_note = "｜".join([f"{h}頭{sum(1 for n in latest_nums if n//10==h)}顆" for h in range(4)])
    tail_count = {}
    for n in latest_nums:
        tail_count[n % 10] = tail_count.get(n % 10, 0) + 1
    tail_note = "｜".join(f"{t}尾{c}顆" for t, c in sorted(tail_count.items()))
    mode_text = "回補修正盤：近期母盤命中偏低，今日加重冷號/遺漏值。" if mode == "recovery" else "一般縮盤：短期熱度搭配遺漏值，降低號碼分散。"

    return {
        "model_version": APP_VERSION,
        "model_mode": mode,
        "motherboard": fmt_nums(mother),
        "core5": fmt_nums(core5),
        "top3": fmt_nums(top3),
        "diagnostics": diagnostics,
        "stable2": fmt_nums(stable),
        "attack3": fmt_nums(attack),
        "burst4": fmt_nums(burst),
        "cold_note": cold_note,
        "pattern_note": (
            f"模式：{mode_text}\n"
            f"頭數：{head_note}\n"
            f"尾數：{tail_note}\n"
            f"區段：{structure_539(fmt_nums(mother))}\n"
            "策略：10碼縮盤；2星抓3碼主軸，3星用6碼主攻，4星用7碼爆發。"
        ),
    }

def get_or_build_today_pick_539():
    """
    取得今日539模型。
    cache 修正版：
    - 如果 daily_pick_cache 是舊版本，直接重建。
    - 避免畫面標題已更新，但 2星/3星/4星仍吃舊 note。
    """
    import verification
    locked = verification.locked_pack(today_tw())
    if locked: return locked
    if today_tw().weekday()==6 or now_tw().hour>=20:
        raise ValueError("今日休市或已過鎖盤時間；不建立事後分析")
    ensure_latest_539_in_db()
    draws = load_539_draws(limit=240)
    fresh, latest_date, stale_days = is_539_data_fresh(draws[:1])

    with db_cursor() as cur:
        cur.execute("""
            SELECT numbers, hot_zone, top_hot, note
            FROM daily_pick_cache
            WHERE pick_date=%s;
        """, (today_tw(),))
        row = cur.fetchone()

    if row and fresh:
        try:
            cached_note = json.loads(row[3] or "{}")
            if cached_note.get("model_version") == APP_VERSION:
                return verification.lock({"numbers": row[0], "hot_zone": row[1], "top_hot": row[2], "note": row[3]})
            else:
                log("539_CACHE_VERSION_MISMATCH_REBUILD:", cached_note.get("model_version"), APP_VERSION)
        except Exception:
            log("539_CACHE_NOTE_PARSE_FAIL_REBUILD")

    d30 = draws[:30]
    hot_zone, ranked = hot_zone_539(d30)
    top_hot = fmt_nums([n for n, _ in ranked[:5]])

    models = build_539_models(draws)
    models["model_version"] = APP_VERSION
    models["data_fresh"] = bool(fresh)
    models["latest_draw_date"] = latest_date.strftime("%Y-%m-%d") if latest_date else "無"
    models["data_stale_days"] = stale_days

    # 硬性防呆：確保輸出顆數一定是 10 / 3 / 6 / 7
    mother = parse_nums_text(models.get("motherboard", ""))
    stable = parse_nums_text(models.get("stable2", ""))
    attack = parse_nums_text(models.get("attack3", ""))
    burst = parse_nums_text(models.get("burst4", ""))

    for n in mother:
        if len(stable) < 3 and n not in stable:
            stable.append(n)
        if len(attack) < 6 and n not in attack:
            attack.append(n)
        if len(burst) < 7 and n not in burst:
            burst.append(n)

    for n in range(1, 40):
        if len(mother) < 10 and n not in mother:
            mother.append(n)
        if len(stable) < 3 and n not in stable:
            stable.append(n)
        if len(attack) < 6 and n not in attack:
            attack.append(n)
        if len(burst) < 7 and n not in burst:
            burst.append(n)
        if len(mother) >= 10 and len(stable) >= 3 and len(attack) >= 6 and len(burst) >= 7:
            break

    models["motherboard"] = fmt_nums(mother[:10])
    models["stable2"] = fmt_nums(stable[:3])
    models["attack3"] = fmt_nums(attack[:6])
    models["burst4"] = fmt_nums(burst[:7])

    note = json.dumps(models, ensure_ascii=False)

    with db_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO daily_pick_cache (pick_date, numbers, hot_zone, top_hot, note, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (pick_date) DO UPDATE
            SET numbers=EXCLUDED.numbers,
                hot_zone=EXCLUDED.hot_zone,
                top_hot=EXCLUDED.top_hot,
                note=EXCLUDED.note,
                created_at=EXCLUDED.created_at;
        """, (today_tw(), models["motherboard"], hot_zone, top_hot, note, now_tw()))

    return verification.lock({"numbers": models["motherboard"], "hot_zone": hot_zone, "top_hot": top_hot, "note": note})


def parse_models_from_note(note):
    data=json.loads(note or '{}')
    for key,count in [('motherboard',10),('stable2',3),('attack3',6),('burst4',7)]:
        nums=parse_nums_text(data.get(key,''))
        if len(nums)!=count or len(set(nums))!=count or any(n<1 or n>39 for n in nums):
            raise ValueError('539 模型內容不完整')
    return data


def update_latest_model_result():
    import verification
    ensure_latest_539_in_db()
    verification.reconcile(load_539_draws(limit=240))
    return None


def latest_model_result_text():
    import verification
    return '\n'+verification.report(7)+'\n'

def format_today_companion():
    try:
        pack = get_or_build_today_pick_539()
        m = parse_models_from_note(pack["note"])
        result_text = latest_model_result_text()
        stale_note = ""
        if not m.get("data_fresh", True):
            stale_note = (
                "\n⚠️ 資料提醒\n"
                f"最新資料：{m.get('latest_draw_date', '無')}｜距今約 {m.get('data_stale_days', '未知')} 天\n"
            )

        diag = m.get("diagnostics") or {}
        mother = parse_nums_text(m.get("motherboard", ""))
        if not m.get("core5"):
            ranked = sorted(mother, key=lambda n: (diag.get(str(n), {}).get("score", 0), -n), reverse=True)
            m["core5"] = fmt_nums(ranked[:5] or mother[:5])
        if not m.get("top3"):
            m["top3"] = fmt_nums(parse_nums_text(m["core5"])[:3])

        detail_lines = []
        for n in sorted(mother, key=lambda x: diag.get(str(x), {}).get("score", 0), reverse=True):
            d = diag.get(str(n), {})
            if not d:
                continue
            tags = "・".join(d.get("tags") or []) or "均衡"
            detail_lines.append(
                f"{n:02d}｜{d.get('score',0):>3}分｜30期{d.get('freq30',0)}次｜遺漏{d.get('gap',0)}期｜{tags}"
            )
        number_details = "\n".join(detail_lines[:10]) if detail_lines else "本次快取尚無逐號診斷；下一次模型重建後自動補上。"

        return (
            "【539 AI｜今日決策盤 V2】\n\n"
            "🎯 今日母盤 10碼\n"
            f"{m['motherboard']}\n\n"
            "⭐ 核心5碼\n"
            f"{m.get('core5','—')}\n"
            f"🔥 AI熱度 Top3｜{m.get('top3','—')}\n\n"
            "━━━━━━━━━━━━━━━\n"
            "2星主軸（3碼）\n"
            f"{m['stable2']}\n"
            "3星主攻（6碼）\n"
            f"{m['attack3']}\n"
            "4星延伸（7碼）\n"
            f"{m['burst4']}\n\n"
            "━━━━━━━━━━━━━━━\n"
            "📊 母盤逐號依據\n"
            f"{number_details}\n\n"
            "━━━━━━━━━━━━━━━\n"
            "🧩 結構\n"
            f"{structure_539(m['motherboard'])}\n"
            f"活躍區段：{pack['hot_zone']}\n"
            f"冷號／遺漏補位：{m.get('cold_note', '無')}\n"
            f"模型狀態：{'回補修正' if m.get('model_mode') == 'recovery' else '一般縮盤'}\n"
            f"{result_text}"
            f"{stale_note}\n"
            "📌 模型說明\n"
            f"{m.get('pattern_note', '')}\n\n"
            "所有數字為歷史資料模型輸出，開獎結果仍屬未知；開獎後系統會保留結果供追蹤。"
        )
    except Exception as e:
        log("FORMAT_539_ERROR:", repr(e))
        return "【539 AI】\n\n目前無法完成今日模型，請稍後重試；系統不會用假資料冒充今日分析。"

def format_539_push():
    return format_today_companion().replace("【539 AI｜今日決策盤 V2】", "【AI理性陪跑｜539 今日決策盤】")


# ========= Bingo 真實資料版 =========
def fallback_bingo_results(max_rows=60):
    # V2 safety rule: never fabricate Bingo draws.
    # Keep the function for compatibility, but return no rows when the real source is unavailable.
    return []


def fetch_real_bingo_results(max_rows=120):
    return fetch_recent_bingo_results(max_rows=max_rows)


def fetch_recent_bingo_results(max_rows=120):
    try:
        try:
            HTTP.get(SOURCE_BINGO_OFFICIAL_URL, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        except Exception:
            pass

        r = HTTP.get(SOURCE_BINGO_PILIO_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        html = r.text.replace("&nbsp;", " ").replace("\u3000", " ")

        page_date = today_tw()
        dm = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})\s*BINGO", html)
        if dm:
            page_date = date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))

        pattern = re.compile(
            r"[〖【]\s*期別:\s*(\d+)\s*[〗】]\s*"
            r"((?:\d{2}\s*,\s*){19}\d{2})"
            r".{0,200}?超級獎號:\s*(\d{2})"
            r".{0,160}?\((\d{2}:\d{2})\)",
            re.S
        )

        out = []
        seen = set()
        for m in pattern.finditer(html):
            period = m.group(1)
            if period in seen:
                continue
            nums = [int(x) for x in re.findall(r"\d{2}", m.group(2))]
            if len(set(nums)) != 20 or not all(1<=n<=80 for n in nums):
                continue
            seen.add(period)
            out.append({
                "period": period,
                "date": page_date,
                "time": m.group(4),
                "numbers": sorted(nums),
                "super_number": m.group(3),
                "source": "pilio"
            })
            if len(out) >= max_rows:
                break

        return out
    except Exception as e:
        log("FETCH_BINGO_ERROR:", repr(e))
        return []


def upsert_bingo_draws(draws):
    if not draws:
        return
    rows = []
    for d in draws:
        nums = fmt_nums(d.get("numbers", []))
        if (d.get("source") in {"pilio", "taiwanlottery"} and d.get("period")
            and len(set(d.get("numbers", []))) == 20
            and all(1 <= n <= 80 for n in d.get("numbers", []))
            and d.get("date") and d.get("time")):
            rows.append((
                str(d["period"]),
                d.get("date") or today_tw(),
                d.get("time") or "",
                nums,
                d.get("super_number"),
                now_tw()
            ))
    if not rows:
        return
    with db_cursor(commit=True) as cur:
        cur.executemany("""
            INSERT INTO bingo_draws (period, draw_date, draw_time, numbers, super_number, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (period) DO UPDATE
            SET draw_date=EXCLUDED.draw_date,
                draw_time=EXCLUDED.draw_time,
                numbers=EXCLUDED.numbers,
                super_number=EXCLUDED.super_number,
                created_at=EXCLUDED.created_at;
        """, rows)


def ensure_latest_bingo_in_db():
    try:
        draws = fetch_recent_bingo_results(max_rows=120)
        upsert_bingo_draws(draws)
        import store
        with store.cursor(True) as c:
            for d in draws:
                if d.get("source") in {"pilio", "taiwanlottery"} and len(set(d.get("numbers",[])))==20 and all(1<=n<=80 for n in d["numbers"]):
                    c.execute("INSERT INTO v2_bingo_provenance VALUES (%s,%s,%s) ON CONFLICT(period) DO UPDATE SET source=excluded.source,fetched_at=excluded.fetched_at",(str(d["period"]),d["source"],now_tw().isoformat()))
        return bool(draws)
    except Exception as e:
        log("ENSURE_BINGO_ERROR:", repr(e))


def load_bingo_draws(limit=120):
    with db_cursor() as cur:
        cur.execute("""
            SELECT period, draw_date, draw_time, numbers, super_number
            FROM bingo_draws
            ORDER BY period DESC
            LIMIT %s;
        """, (limit,))
        rows = cur.fetchall()
    out = []
    import store
    with store.cursor() as c:
        c.execute("SELECT period FROM v2_bingo_provenance"); trusted={r[0] for r in c.fetchall()}
    for period, d, t, nums_text, super_number in rows:
        if str(period) not in trusted: continue
        nums = [int(x) for x in nums_text.split()]
        if len(set(nums)) == 20 and all(1<=n<=80 for n in nums):
            out.append({
                "period": str(period),
                "date": d,
                "time": t,
                "numbers": nums,
                "super_number": super_number,
            })
    return out


def bingo_zone(n):
    if n <= 20:
        return "1-20"
    if n <= 40:
        return "21-40"
    if n <= 60:
        return "41-60"
    return "61-80"


def bingo_freq(draws):
    f = {i: 0 for i in range(1, 81)}
    for d in draws:
        for n in d["numbers"]:
            f[n] += 1
    return f


def bingo_gap(draws):
    gap = {i: len(draws) + 5 for i in range(1, 81)}
    for idx, d in enumerate(draws):
        for n in d["numbers"]:
            if gap[n] == len(draws) + 5:
                gap[n] = idx
    score = {}
    for n, g in gap.items():
        if g <= 1:
            score[n] = 0.12
        elif 2 <= g <= 4:
            score[n] = 0.45
        elif 5 <= g <= 12:
            score[n] = 1.00
        elif 13 <= g <= 25:
            score[n] = 0.78
        else:
            score[n] = 0.58
    return score, gap


def bingo_summary(draws):
    zones = {"1-20": 0, "21-40": 0, "41-60": 0, "61-80": 0}
    f = bingo_freq(draws)
    for d in draws:
        for n in d["numbers"]:
            zones[bingo_zone(n)] += 1
    hot_zone = max(zones.items(), key=lambda x: x[1])[0] if draws else "資料不足"
    hot = sorted(f.items(), key=lambda x: (x[1], -x[0]), reverse=True)[:4]
    return hot_zone, "・".join(f"{n:02d}" for n, _ in hot), f


def build_bingo_model(draws, label):
    if not draws:
        return {
            "pick": "—",
            "zone": "—",
            "hot": "—",
            "tail": "—",
            "note": "⚠️ 真實開獎資料暫時不可用，本次不產生分析結果。",
            "data_ok": False,
        }

    d10, d30, d80 = draws[:10], draws[:30], draws[:80]
    zone, hot, f10 = bingo_summary(d10)
    zone30, _, f30 = bingo_summary(d30)
    _, _, f80 = bingo_summary(d80)
    gap_score, gap_raw = bingo_gap(d80)

    nf10, nf30, nf80, ngap = normalize(f10), normalize(f30), normalize(f80), normalize(gap_score)
    latest_set = set(draws[0]["numbers"])

    score = {}
    for n in range(1, 81):
        repeat_penalty = -0.10 if n in latest_set else 0
        zone_boost = 0.10 if bingo_zone(n) == zone30 else 0
        score[n] = 0.34 * nf10[n] + 0.26 * nf30[n] + 0.12 * nf80[n] + 0.20 * ngap[n] + zone_boost + repeat_penalty

    pick = weighted_sample(range(1, 81), score, 5, f"bingo-real-{today_tw()}-{draws[0]['period']}-{label}")
    tail_count = {}
    for n in draws[0]["numbers"]:
        tail_count[n % 10] = tail_count.get(n % 10, 0) + 1
    tail = "｜".join(f"{t}尾{c}顆" for t, c in sorted(tail_count.items()) if c >= 2) or "尾數分散"
    cold = "・".join(f"{n:02d}" for n, _ in sorted(gap_raw.items(), key=lambda x: x[1], reverse=True)[:3])

    latest_nums = " ".join(f"{n:02d}" for n in draws[0]["numbers"])
    source_name = "真實開獎"
    note = (
        f"資料源：{source_name}\n"
        f"最新期別：{draws[0]['period']}（{draws[0].get('time', '')}）\n"
        f"最新開獎：{latest_nums}\n"
        f"超級獎號：{draws[0].get('super_number') or '無'}\n"
        f"冷號觀察：{cold}"
    )

    return {
        "pick": fmt_nums(pick),
        "zone": zone30,
        "hot": hot,
        "tail": tail,
        "note": note,
        "data_ok": True,
    }


def get_bingo_analysis_bundle():
    ensure_latest_bingo_in_db()
    draws = load_bingo_draws(limit=120)

    one = build_bingo_model(draws[:30], "1期")
    five = build_bingo_model(draws[:60], "5期")
    ten = build_bingo_model(draws[:120], "10期")

    return {
        "one": one,
        "five": five,
        "ten": ten,
        "latest": draws[0] if draws else None,
    }


def format_bingo_message(kind):
    b = get_bingo_analysis_bundle()
    if not b.get("latest"):
        return (
            "【Bingo AI｜資料狀態】\n\n"
            "⚠️ 目前抓不到可信的真實開獎資料，因此本次不產生號碼或模型結果。\n"
            "系統不會用模擬資料代替真實開獎。請稍後再試。"
        )
    if kind == "1":
        title, label, model, conclusion = "【Bingo AI短線分析｜真實資料版】", "1期分析", b["one"], "短線模型以近10期頻率、遺漏值、區段與尾數結構加權。"
    elif kind == "5":
        title, label, model, conclusion = "【Bingo AI節奏分析｜真實資料版】", "5期分析", b["five"], "節奏模型以近30期熱度、回補值與區段偏移為主。"
    else:
        title, label, model, conclusion = "【Bingo AI結構分析｜真實資料版】", "10期分析", b["ten"], "結構模型以近80期頻率、遺漏值、鄰號補位與尾數型態加權。"

    return (
        f"{title}\n\n"
        f"{label}\n"
        f"{model['pick']}\n\n"
        "活躍區段\n"
        f"{model['zone']}\n\n"
        "高頻樣本\n"
        f"{model['hot']}\n\n"
        "尾數型態\n"
        f"{model['tail']}\n\n"
        "資料追蹤\n"
        f"{model['note']}\n\n"
        "分析結論\n"
        f"{conclusion}\n\n"
        "（真實開獎資料建模，非保證結果）"
    )


def format_bingo_1_message():
    return format_bingo_message("1")


def format_bingo_5_message():
    return format_bingo_message("5")


def format_bingo_10_message():
    return format_bingo_message("10")


def format_bingo_evening_push():
    b = get_bingo_analysis_bundle()
    latest = b.get("latest") or {}
    latest_line = f"最新期別：{latest.get('period')}｜{latest.get('time')}\n" if latest else ""
    return (
        "【理性陪跑研究室｜Bingo Bingo 真實資料版】\n"
        f"{now_tw().strftime('%Y.%m.%d')} 晚間模型\n"
        f"{latest_line}\n"
        "▍1期短線模型\n"
        f"{b['one']['pick']}\n\n"
        "▍5期節奏模型\n"
        f"{b['five']['pick']}\n\n"
        "▍10期結構模型\n"
        f"{b['ten']['pick']}\n\n"
        "資料基礎：真實開獎、頻率、遺漏值、區段、尾數。\n\n"
        "—— AI陪跑語錄 ——\n"
        f"{get_daily_quote()}"
    )


def format_bingo_latest_push():
    b = get_bingo_analysis_bundle()
    latest = b.get("latest") or {}
    period = latest.get("period") or now_tw().strftime("%Y%m%d%H%M")
    msg = (
        "【Bingo 即時模型｜真實資料版】\n\n"
        "下一期短線模型\n"
        f"{b['one']['pick']}\n\n"
        "活躍區段\n"
        f"{b['one']['zone']}\n\n"
        "資料追蹤\n"
        f"{b['one']['note']}\n\n"
        "數據結構參考，非保證結果"
    )
    return period, msg


# ========= 點數配置 =========
def money(x):
    return f"{int(x):,}"


def build_bet_plan(total, mode="balanced"):
    try:
        total = int(total)
    except Exception:
        total = 3000
    if total <= 0:
        total = 3000

    cfgs = {
        "safe": ("穩健模式", "2星回補為主｜3星主攻｜4星小注爆發", 0.45, 0.40, 0.15),
        "balanced": ("均衡模式", "2星回補｜3星主攻｜4星爆發", 0.30, 0.50, 0.20),
        "burst": ("爆發模式", "降低2星配置，提高3星與4星攻擊", 0.20, 0.50, 0.30),
    }
    name, desc, p2, p3, p4 = cfgs.get(mode, cfgs["balanced"])

    pack = get_or_build_today_pick_539()
    m = parse_models_from_note(pack["note"])
    two = parse_nums_text(m["stable2"])[:3]
    three = parse_nums_text(m["attack3"])[:6]
    four = parse_nums_text(m["burst4"])[:7]

    c2 = len(list(combinations(two, 2)))
    c3 = len(list(combinations(three, 3)))
    c4 = len(list(combinations(four, 4)))
    amt2 = int(total * p2)
    amt3 = int(total * p3)
    amt4 = total - amt2 - amt3

    per2 = max(1, amt2 // max(1, c2))
    per3 = max(1, amt3 // max(1, c3))
    per4 = max(1, amt4 // max(1, c4))

    real2, real3, real4 = per2 * c2, per3 * c3, per4 * c4
    pairs = "\n".join(f"{a:02d}-{b:02d}" for a, b in combinations(two, 2))

    return (
        f"【539 點數配置｜{money(total)}點】\n\n"
        f"模式：{name}\n"
        f"策略：{desc}\n\n"
        "▍今日建議打法\n"
        "小本金：主打2星＋3星\n"
        "中本金：3星主攻，4星小注\n"
        "高本金：4星放大，但不追單\n\n"
        "▍使用號碼（直接照下）\n\n"
        f"2星：{fmt_nums(two)}\n"
        "👉 選3顆，全碰\n"
        f"{pairs}\n"
        f"共{c2}碰\n\n"
        f"3星：{fmt_nums(three)}\n"
        f"👉 任選3顆組合，共{c3}碰\n\n"
        f"4星：{fmt_nums(four)}\n"
        f"👉 任選4顆組合，共{c4}碰\n\n"
        "━━━━━━━━━━━━━━━\n\n"
        "▍點數分配\n\n"
        f"2星：每碰 {money(per2)} × {c2}碰 = {money(real2)}\n"
        f"3星：每碰 {money(per3)} × {c3}碰 = {money(real3)}\n"
        f"4星：每碰 {money(per4)} × {c4}碰 = {money(real4)}\n\n"
        f"實際投入：約 {money(real2 + real3 + real4)} 點\n\n"
        "縮盤版本碰數較少，點數更集中。\n"
        "（點數配置僅供策略參考）"
    )

def format_help_message():
    return (
        "【功能選單】\n\n"
        "今日陪跑\n"
        "查看539 AI強化母盤\n\n"
        "母盤追蹤\n"
        "查看最近539追蹤\n\n"
        "免費試用\n"
        "免費體驗24小時（每人一次）\n\n"
        "點數配置\n"
        "539 2星/3星/4星智能配置\n\n"
        "賓果分析\n"
        "查看賓果真實資料版模型\n\n"
        "1期 / 5期 / 10期\n"
        "快速取得賓果分析\n\n"
        "預測分析 / 取消預測分析\n"
        "開啟或停止Bingo即時推播\n\n"
        "開啟每日推播 / 取消每日推播\n\n"
        "我的到期日\n"
        "查看會員期限\n\n"
        "版本檢查\n"
        "確認目前程式版本"
    )


def format_welcome(exp=None):
    exp_line = f"\n到期時間：{exp.astimezone(TZ_TW).strftime('%Y-%m-%d %H:%M')}\n" if exp else ""
    return (
        "✅ 會員已開通\n"
        f"{exp_line}\n"
        "你現在可以使用：\n\n"
        "1. 今日陪跑\n"
        "查看539強化母盤\n\n"
        "2. 點數配置\n"
        "依本金產生配置\n\n"
        "3. 賓果分析\n"
        "查看1期、5期、10期真實資料版模型\n\n"
        "4. 預測分析\n"
        "開啟Bingo即時推播\n\n"
        "建議先輸入：今日陪跑"
    )


def format_expiry_reminder(exp_dt):
    exp_tw = exp_dt.astimezone(TZ_TW)
    return (
        "【會員到期提醒】\n\n"
        "你的會員將在 3 天後到期。\n"
        f"到期時間：{exp_tw.strftime('%Y-%m-%d %H:%M')}\n\n"
        "若要續費，請聯絡管理員。"
    )


# ========= Routes =========
@app.route("/")
def home():
    return f"Bot is running. VERSION={APP_VERSION}", 200


@app.route("/health")
def health():
    return f"OK VERSION={APP_VERSION}", 200


@app.route("/cron/update-539-result")
def cron_update_539_result():
    if request.args.get("secret", "") != CRON_SECRET:
        return "Forbidden", 403
    ensure_db_ready()
    result = update_latest_model_result()
    return f"OK {result}", 200


@app.route("/cron/daily-push")
def cron_daily_push():
    if request.args.get("secret", "") != CRON_SECRET:
        abort(403)
    try:
        ensure_db_ready()
        update_latest_model_result()
        users = get_daily_push_users()
        today_key = today_tw().strftime("%Y-%m-%d")

        reminder_key = f"expiry_reminder_{today_key}"
        if get_push_state(reminder_key) is None:
            for uid, exp_dt in get_expiring_members(3):
                push_message(uid, format_expiry_reminder(exp_dt))
            set_push_state(reminder_key, "done")

        if not users:
            return "No active members", 200

        if now_tw().weekday() != 6:
            key_539 = f"daily_539_{today_key}"
            if get_push_state(key_539) is None:
                msg = format_539_push()
                for uid in users:
                    push_message(uid, msg)
                set_push_state(key_539, "done")

        key_bingo = f"daily_bingo_{today_key}"
        if get_push_state(key_bingo) is None:
            msg = format_bingo_evening_push()
            for uid in users:
                push_message(uid, msg)
            set_push_state(key_bingo, "done")

        return "OK", 200
    except Exception as e:
        log("CRON_DAILY_ERROR:", repr(e))
        return "ERROR", 500


@app.route("/cron/check-bingo")
def cron_check_bingo():
    if request.args.get("secret", "") != CRON_SECRET:
        return "Forbidden", 403
    try:
        ensure_db_ready()
        hhmm = now_tw().strftime("%H:%M")
        if hhmm < "07:05" or hhmm > "23:55":
            return f"Outside draw hours: {hhmm}", 200

        period, msg = format_bingo_latest_push()
        if get_push_state("latest_bingo_period") == period:
            return f"No new result. period={period}", 200

        users = get_prediction_subscribers()
        count = 0
        for uid in users:
            if push_message(uid, msg):
                count += 1
        set_push_state("latest_bingo_period", period)
        return f"OK period={period} pushed={count}", 200
    except Exception as e:
        log("CRON_BINGO_ERROR:", repr(e))
        return f"ERROR {repr(e)}", 500


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        raw = request.get_data()
        sig = request.headers.get("X-Line-Signature", "")
        if not verify_line_signature(raw, sig):
            log("SIGNATURE ERROR")
            abort(403)

        body = request.get_json(silent=True) or {}
        events = body.get("events", [])

        try:
            ensure_db_ready()
        except Exception as e:
            log("INIT_DB ERROR:", repr(e))
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

                log("TEXT:", text, "USER:", user_id)

                if text == "版本檢查":
                    reply_message(
                        reply_token,
                        "【版本檢查】\n"
                        f"VERSION：{APP_VERSION}\n"
                        "539：強化母盤12碼\n"
                        "2星主軸：5碼\n"
                        "3星主攻：8碼\n"
                        "4星爆發：10碼\n"
                        "Bingo：真實資料版\n"
                        "如果你看不到這段，代表LINE webhook打到舊服務。"
                    )
                    continue

                if text == "指令" or text.lower() == "help":
                    reply_message(reply_token, format_help_message())
                    continue

                if text == "申請加入會員":
                    reply_message(reply_token, "請輸入:\n(遊戲帳號 XXXXXX)\nX為3A帳號 ()內都要輸入\n\n範例: 遊戲帳號 123456")
                    continue

                if text.startswith("遊戲帳號 "):
                    parts = text.split(maxsplit=1)
                    if len(parts) != 2 or not parts[1].strip():
                        reply_message(reply_token, "格式：遊戲帳號 XXXXX")
                    else:
                        ga = parts[1].strip()
                        save_pending_account(ga, user_id)
                        reply_message(reply_token, f"✅ 已收到你的申請加入會員\n\n帳號：{ga}\n\n請等待管理員確認開通。")
                    continue

                if text.startswith("待確認"):
                    parts = text.split()
                    secret = parts[1] if len(parts) >= 2 else ""
                    if not is_admin(user_id, secret):
                        reply_message(reply_token, "管理權限不足。")
                        continue
                    rows = get_latest_pending(50)
                    if not rows:
                        reply_message(reply_token, "目前沒有待確認帳號。")
                        continue
                    msg = "📋 最近待確認帳號（最多50筆）\n\n"
                    for ga, uid, ts in rows:
                        msg += f"帳號：{ga}\nuserId：{uid}\n時間：{ts.astimezone(TZ_TW).strftime('%Y-%m-%d %H:%M')}\n-----------------\n"
                    reply_message(reply_token, msg[:5000])
                    continue

                if text.startswith("確認 "):
                    parts = text.split()
                    if len(parts) not in (2, 3):
                        reply_message(reply_token, "格式：確認 <遊戲帳號> <管理密碼>\n例：確認 123456 1234")
                        continue
                    ga = parts[1]
                    secret = parts[2] if len(parts) == 3 else ""
                    if not is_admin(user_id, secret):
                        reply_message(reply_token, "管理權限不足。")
                        continue
                    target = pop_pending_user_id(ga)
                    if not target:
                        reply_message(reply_token, f"找不到待確認帳號：{ga}")
                        continue
                    exp = set_expiry_plus_days(target, 30)
                    enable_daily_push(target)
                    reply_message(reply_token, f"✅ 已開通\n\n帳號：{ga}\n到期（台灣時間）：{exp.strftime('%Y-%m-%d %H:%M')}")
                    push_message(target, format_welcome(exp))
                    continue

                if text in ("免費試用", "免費體驗", "試用一天", "免費使用1天", "免費使用一天"):
                    exp, status = start_free_trial(user_id, 24)
                    if status == "opened":
                        reply_message(reply_token, f"✅ 免費試用已開通\n\n可使用時間：24小時\n到期時間：{exp.astimezone(TZ_TW).strftime('%Y-%m-%d %H:%M')}\n\n可輸入：今日陪跑 / 點數配置 / 賓果分析 / 預測分析")
                    elif status == "already_member":
                        reply_message(reply_token, f"✅ 你目前已經是會員\n\n到期時間：{exp.astimezone(TZ_TW).strftime('%Y-%m-%d %H:%M')}")
                    elif status == "used":
                        reply_message(reply_token, "你已使用過免費試用。\n\n若要繼續使用完整模型，請輸入：申請加入會員")
                    else:
                        reply_message(reply_token, "暫時無法開通試用，請稍後再試。")
                    continue

                if text == "我的到期日":
                    exp = get_expiry(user_id)
                    if not exp:
                        reply_message(reply_token, "你目前尚未開通。\n請先輸入：遊戲帳號 XXXXX")
                    else:
                        reply_message(reply_token, "⏳ 你的到期時間（台灣時間）：\n" + exp.astimezone(TZ_TW).strftime("%Y-%m-%d %H:%M"))
                    continue

                if text == "今日陪跑":
                    if not is_member(user_id):
                        reply_message(reply_token, "🌿 今日陪跑屬於會員內容\n\n請先輸入：免費試用 或 遊戲帳號 XXXXX")
                    else:
                        reply_message(reply_token, format_today_companion())
                    continue

                if text == "母盤追蹤":
                    if not is_member(user_id):
                        reply_message(reply_token, "🌿 母盤追蹤屬於會員內容\n\n請先輸入：免費試用 或 遊戲帳號 XXXXX")
                    else:
                        reply_message(reply_token, latest_model_result_text().strip() or "目前尚無可追蹤資料。")
                    continue

                if text == "點數配置":
                    if not is_member(user_id):
                        reply_message(reply_token, "🌿 點數配置屬於會員內容\n\n請先輸入：免費試用 或 遊戲帳號 XXXXX")
                    else:
                        reply_bet_plan_menu(reply_token)
                    continue

                if text.startswith(("穩健", "均衡", "爆發")):
                    if not is_member(user_id):
                        reply_message(reply_token, "🌿 點數配置屬於會員內容\n\n請先輸入：免費試用 或 遊戲帳號 XXXXX")
                        continue
                    try:
                        parts = text.split()
                        mode_map = {"穩健": "safe", "均衡": "balanced", "爆發": "burst"}
                        reply_message(reply_token, build_bet_plan(int(parts[1]), mode_map.get(parts[0], "balanced")))
                    except Exception:
                        reply_message(reply_token, "格式錯誤\n例如：穩健 3000 / 均衡 3000 / 爆發 5000")
                    continue

                if text.startswith("下注"):
                    if not is_member(user_id):
                        reply_message(reply_token, "🌿 點數配置屬於會員內容\n\n請先輸入：免費試用 或 遊戲帳號 XXXXX")
                        continue
                    try:
                        amount = int(text.replace("下注", "").strip())
                        reply_message(reply_token, build_bet_plan(amount, "balanced"))
                    except Exception:
                        reply_message(reply_token, "格式錯誤\n例如：下注 3000")
                    continue

                if text == "賓果分析":
                    reply_bingo_menu(reply_token)
                    continue

                if text in ("1期", "賓果1期分析"):
                    if not is_member(user_id):
                        reply_message(reply_token, "🌿 賓果1期分析屬於會員內容\n\n請先輸入：免費試用 或 遊戲帳號 XXXXX")
                    else:
                        reply_message(reply_token, format_bingo_1_message())
                    continue

                if text in ("5期", "賓果5期分析"):
                    if not is_member(user_id):
                        reply_message(reply_token, "🌿 賓果5期分析屬於會員內容\n\n請先輸入：免費試用 或 遊戲帳號 XXXXX")
                    else:
                        reply_message(reply_token, format_bingo_5_message())
                    continue

                if text in ("10期", "賓果10期分析"):
                    if not is_member(user_id):
                        reply_message(reply_token, "🌿 賓果10期分析屬於會員內容\n\n請先輸入：免費試用 或 遊戲帳號 XXXXX")
                    else:
                        reply_message(reply_token, format_bingo_10_message())
                    continue

                if text == "預測分析":
                    if not is_member(user_id):
                        reply_message(reply_token, "🌿 預測分析屬於會員內容\n\n請先輸入：免費試用 或 遊戲帳號 XXXXX")
                    else:
                        enable_prediction(user_id)
                        reply_message(reply_token, "✅ 已開啟預測分析\n\n之後若有 Bingo 即時分析更新，你會收到下一期短線模型。")
                    continue

                if text == "取消預測分析":
                    disable_prediction(user_id)
                    reply_message(reply_token, "✅ 已取消預測分析推播")
                    continue

                if text == "開啟每日推播":
                    if not is_member(user_id):
                        reply_message(reply_token, "🌿 此功能屬於會員內容\n\n請先輸入：免費試用 或 遊戲帳號 XXXXX")
                    else:
                        enable_daily_push(user_id)
                        reply_message(reply_token, "✅ 已開啟每日推播")
                    continue

                if text == "取消每日推播":
                    disable_daily_push(user_id)
                    reply_message(reply_token, "✅ 已取消每日推播")
                    continue

                reply_message(reply_token, "輸入「指令」查看功能。")

            except Exception as e:
                log("EVENT ERROR:", repr(e))
                try:
                    reply_message(event.get("replyToken"), "系統忙碌中，請稍後再試一次。")
                except Exception:
                    pass
                continue

        return "OK"
    except Exception as e:
        log("WEBHOOK FATAL:", repr(e))
        return "OK"


if __name__ == "__main__":
    try:
        ensure_db_ready()
    except Exception as e:
        log("START INIT_DB ERROR:", repr(e))
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
