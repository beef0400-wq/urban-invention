"""V2 additive storage. Postgres in deployed environments, SQLite for local tests."""
import os, json, sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
import psycopg2

@contextmanager
def cursor(write=False):
    url = os.getenv('DATABASE_URL', '')
    conn = psycopg2.connect(url, sslmode='require') if url else sqlite3.connect(os.getenv('LOCAL_DB_PATH', 'v2-local.sqlite3'))
    cur = conn.cursor()
    class Adapter:
        def execute(self, sql, args=()):
            return cur.execute(sql if url else sql.replace('%s', '?'), args if url else tuple(v.isoformat() if hasattr(v, "isoformat") else v for v in args))
        def fetchone(self): return cur.fetchone()
        def fetchall(self): return cur.fetchall()
    try:
        yield Adapter()
        if write: conn.commit()
    except Exception:
        conn.rollback(); raise
    finally: cur.close(); conn.close()

def init_db():
    with cursor(True) as c:
        c.execute('CREATE TABLE IF NOT EXISTS v2_state (user_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS v2_records (record_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, mode TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS v2_public_539 (target_date TEXT PRIMARY KEY, locked_at TEXT NOT NULL, digest TEXT NOT NULL, payload TEXT NOT NULL, actual TEXT, verified_at TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS v2_events (event_id TEXT PRIMARY KEY, status TEXT NOT NULL, created_at TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS v2_bingo_provenance (period TEXT PRIMARY KEY, source TEXT NOT NULL, fetched_at TEXT NOT NULL)')

def get_state(uid):
    with cursor() as c:
        c.execute('SELECT payload FROM v2_state WHERE user_id=%s', (uid,)); r=c.fetchone()
    return json.loads(r[0]) if r else {}

def put_state(uid, data):
    with cursor(True) as c:
        c.execute('INSERT INTO v2_state VALUES (%s,%s) ON CONFLICT(user_id) DO UPDATE SET payload=excluded.payload', (uid,json.dumps(data,ensure_ascii=False)))

def record(uid, mode, payload):
    import uuid
    with cursor(True) as c:
        c.execute('INSERT INTO v2_records VALUES (%s,%s,%s,%s,%s)', (uuid.uuid4().hex,uid,mode,datetime.now(timezone.utc).isoformat(),json.dumps(payload,ensure_ascii=False,default=str)))

def history(uid, limit=20):
    with cursor() as c:
        c.execute('SELECT mode,created_at,payload FROM v2_records WHERE user_id=%s ORDER BY created_at DESC LIMIT %s',(uid,limit));rows=c.fetchall()
    return [{'mode':r[0],'at':r[1],'data':json.loads(r[2])} for r in rows]
