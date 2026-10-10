import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from contextvars import ContextVar
import db_pool

_ensured = ContextVar('membership_ensured', default=None)

@contextmanager
def request_scope():
    token = _ensured.set(set())
    try:
        yield
    finally:
        _ensured.reset(token)

try:
    import psycopg2
except Exception:
    psycopg2 = None

TZ_TW = timezone(timedelta(hours=8))
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

_MEMORY = {}


def now_tw():
    return datetime.now(TZ_TW)


@contextmanager
def _cursor(commit=False):
    if not DATABASE_URL or not psycopg2:
        yield None
        return
    conn = db_pool.connect(DATABASE_URL)
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
    if not DATABASE_URL or not psycopg2:
        return
    with _cursor(commit=True) as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS platform_users (
                line_user_id TEXT PRIMARY KEY,
                active_mode TEXT NOT NULL DEFAULT '539',
                interest_539 BOOLEAN NOT NULL DEFAULT FALSE,
                interest_baccarat BOOLEAN NOT NULL DEFAULT FALSE,
                interest_bingo BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            );
        """)
        cur.execute("ALTER TABLE platform_users ADD COLUMN IF NOT EXISTS interest_bingo BOOLEAN NOT NULL DEFAULT FALSE;")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS platform_memberships (
                line_user_id TEXT PRIMARY KEY,
                plan_status TEXT NOT NULL DEFAULT 'FREE',
                access_expires_at TIMESTAMPTZ,
                trial_used BOOLEAN NOT NULL DEFAULT FALSE,
                trial_started_at TIMESTAMPTZ,
                trial_expires_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ NOT NULL
            );
        """)
        # Preserve compatibility with the current 539 cron/subscriber queries.
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


def ensure_user(user_id):
    if not user_id:
        return
    ensured = _ensured.get()
    if ensured is not None and user_id in ensured:
        return
    t = now_tw()
    if not DATABASE_URL or not psycopg2:
        import store
        saved = store.get_state("membership:" + user_id)
        for key in ("access_expires_at", "trial_started_at", "trial_expires_at"):
            if saved.get(key): saved[key] = datetime.fromisoformat(saved[key])
        if saved: _MEMORY.setdefault(user_id, saved)
        _MEMORY.setdefault(user_id, {
            "active_mode": "539",
            "plan_status": "FREE",
            "access_expires_at": None,
            "trial_used": False,
            "trial_started_at": None,
            "trial_expires_at": None,
        })
        if ensured is not None: ensured.add(user_id)
        return
    with _cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO platform_users (line_user_id, active_mode, created_at, updated_at)
            VALUES (%s, '539', %s, %s)
            ON CONFLICT (line_user_id) DO UPDATE SET updated_at=EXCLUDED.updated_at;
        """, (user_id, t, t))
        cur.execute("""
            INSERT INTO platform_memberships (line_user_id, plan_status, updated_at)
            VALUES (%s, 'FREE', %s)
            ON CONFLICT (line_user_id) DO NOTHING;
        """, (user_id, t))
    bootstrap_from_legacy(user_id)
    if ensured is not None: ensured.add(user_id)


def bootstrap_from_legacy(user_id):
    """Read legacy paid/trial separately. Never convert mirrored trials into paid."""
    if not DATABASE_URL or not psycopg2 or not user_id:
        return
    paid = []; trials = []
    with _cursor() as cur:
        cur.execute("SELECT to_regclass('public.users')")
        has_users = cur.fetchone()[0] is not None
        cur.execute("SELECT expires_at FROM free_trials WHERE user_id=%s", (user_id,))
        trial = cur.fetchone()
        if trial: trials.append(trial[0])
        cur.execute("SELECT expires_at FROM members WHERE user_id=%s", (user_id,))
        member = cur.fetchone()
        if member and (not trial or member[0] > trial[0]): paid.append(member[0])
        if has_users:
            cur.execute("SELECT vip_expire_at, trial_end_at FROM users WHERE line_user_id=%s", (user_id,))
            row = cur.fetchone()
            if row:
                if row[0]: paid.append(row[0].replace(tzinfo=TZ_TW) if row[0].tzinfo is None else row[0])
                if row[1]: trials.append(row[1].replace(tzinfo=TZ_TW) if row[1].tzinfo is None else row[1])
    with _cursor(commit=True) as cur:
        if paid:
            exp=max(paid)
            cur.execute("UPDATE platform_memberships SET plan_status='PAID', access_expires_at=GREATEST(access_expires_at,%s) WHERE line_user_id=%s", (exp,user_id))
        if trials:
            exp=max(trials)
            cur.execute("UPDATE platform_memberships SET trial_used=TRUE, trial_expires_at=GREATEST(trial_expires_at,%s) WHERE line_user_id=%s", (exp,user_id))


def get_mode(user_id):
    ensure_user(user_id)
    if not DATABASE_URL or not psycopg2:
        return _MEMORY[user_id]["active_mode"]
    with _cursor() as cur:
        cur.execute("SELECT active_mode FROM platform_users WHERE line_user_id=%s", (user_id,))
        row = cur.fetchone()
    return (row[0] if row else "539") or "539"


def set_mode(user_id, mode):
    mode = mode if mode in {"539", "baccarat", "bingo"} else "539"
    ensure_user(user_id)
    t = now_tw()
    if not DATABASE_URL or not psycopg2:
        _MEMORY[user_id]["active_mode"] = mode
        _persist_memory(user_id)
        return mode
    with _cursor(commit=True) as cur:
        interest_col = {"baccarat": "interest_baccarat", "bingo": "interest_bingo"}.get(mode, "interest_539")
        cur.execute(
            f"UPDATE platform_users SET active_mode=%s, {interest_col}=TRUE, updated_at=%s WHERE line_user_id=%s",
            (mode, t, user_id),
        )
    return mode


def _membership_row(user_id):
    ensure_user(user_id)
    if not DATABASE_URL or not psycopg2:
        return _MEMORY[user_id]
    with _cursor() as cur:
        cur.execute("""
            SELECT plan_status, access_expires_at, trial_used, trial_started_at, trial_expires_at
            FROM platform_memberships WHERE line_user_id=%s
        """, (user_id,))
        row = cur.fetchone()
    if not row:
        return {"plan_status": "FREE", "access_expires_at": None, "trial_used": False,
                "trial_started_at": None, "trial_expires_at": None}
    return {
        "plan_status": row[0], "access_expires_at": row[1], "trial_used": row[2],
        "trial_started_at": row[3], "trial_expires_at": row[4],
    }


def get_status(user_id):
    row = _membership_row(user_id)
    t = now_tw()
    paid_exp = row.get("access_expires_at")
    trial_exp = row.get("trial_expires_at")
    if paid_exp and paid_exp > t:
        return "PAID", paid_exp
    if trial_exp and trial_exp > t:
        return "TRIAL", trial_exp
    if row.get("plan_status") == "PAID" or paid_exp:
        return "EXPIRED", paid_exp
    if trial_exp:
        return "EXPIRED", trial_exp
    return "FREE", None


def is_paid(user_id):
    return get_status(user_id)[0] == "PAID"


def is_trial(user_id):
    return get_status(user_id)[0] == "TRIAL"


def has_access(user_id):
    return get_status(user_id)[0] in ("PAID", "TRIAL")


def get_expiry(user_id):
    return get_status(user_id)[1]


def has_used_trial(user_id):
    return bool(_membership_row(user_id).get("trial_used"))


def start_trial(user_id, hours=1):
    ensure_user(user_id)
    status, expiry = get_status(user_id)
    if status == "PAID":
        return expiry, "already_member"
    import account_access
    if account_access.profile(user_id).get('username'):
        return None, 'bound'
    if has_used_trial(user_id):
        return None, "used"
    started = now_tw()
    exp = started + timedelta(hours=hours)
    if not DATABASE_URL or not psycopg2:
        m = _MEMORY[user_id]
        m.update({"trial_used": True, "trial_started_at": started, "trial_expires_at": exp})
        _persist_memory(user_id)
        return exp, "opened"
    with _cursor(commit=True) as cur:
        cur.execute("""
            UPDATE platform_memberships
            SET trial_used=TRUE, trial_started_at=%s, trial_expires_at=%s, updated_at=%s
            WHERE line_user_id=%s
        """, (started, exp, started, user_id))
        cur.execute("""
            INSERT INTO free_trials (user_id, started_at, expires_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (user_id, started, exp))
        # Legacy 539 checks members for both paid and active trial.
        cur.execute("""
            INSERT INTO members (user_id, expires_at) VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET expires_at=EXCLUDED.expires_at
        """, (user_id, exp))
        cur.execute("""
                UPDATE users SET trial_started_at=%s, trial_end_at=%s, trial_expired_notice_sent=FALSE, updated_at=NOW()
                WHERE line_user_id=%s
        """, (started.replace(tzinfo=None), exp.replace(tzinfo=None), user_id))
    return exp, "opened"


def _set_paid_expiry(user_id, exp):
    t = now_tw()
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=TZ_TW)
    if not DATABASE_URL or not psycopg2:
        _MEMORY[user_id].update({"plan_status": "PAID", "access_expires_at": exp})
        _persist_memory(user_id)
        return exp
    with _cursor(commit=True) as cur:
        cur.execute("""
            UPDATE platform_memberships
            SET plan_status='PAID', access_expires_at=%s, updated_at=%s
            WHERE line_user_id=%s
        """, (exp, t, user_id))
        cur.execute("""
            INSERT INTO members (user_id, expires_at) VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET expires_at=EXCLUDED.expires_at
        """, (user_id, exp))
        cur.execute("""
                UPDATE users SET vip_expire_at=%s, updated_at=NOW() WHERE line_user_id=%s
        """, (exp.astimezone(TZ_TW).replace(tzinfo=None), user_id))
    return exp


def grant_days(user_id, days=30):
    ensure_user(user_id)
    current_status, current_exp = get_status(user_id)
    base = current_exp if current_status == "PAID" and current_exp and current_exp > now_tw() else now_tw()
    return _set_paid_expiry(user_id, base + timedelta(days=int(days)))


def status_text(user_id):
    status, exp = get_status(user_id)
    if status == "PAID":
        return f"正式會員｜百家 AI＋539 AI＋Bingo AI 全功能\n到期：{exp.astimezone(TZ_TW).strftime('%Y-%m-%d %H:%M')}"
    if status == "TRIAL":
        return f"免費體驗中｜百家 AI＋539 AI＋Bingo AI 可使用\n到期：{exp.astimezone(TZ_TW).strftime('%Y-%m-%d %H:%M')}"
    if status == "EXPIRED":
        return "會員已到期｜重新開通後，百家 AI＋539 AI＋Bingo AI 會同時恢復。"
    return "免費會員｜可進入三種模式；完整功能依免費體驗／會員權限開放。"


def _persist_memory(uid):
    import store
    data={k: v.isoformat() if isinstance(v,datetime) else v for k,v in _MEMORY[uid].items()}
    store.put_state('membership:'+uid,data)
