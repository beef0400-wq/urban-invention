"""Bounded reusable Postgres connections; no cached membership decisions."""
import os
import threading
import time
import psycopg2
from psycopg2.pool import ThreadedConnectionPool

_pools = {}
_guard = threading.Lock()
_returned_at = {}


class Connection:
    def __init__(self, pool, conn, cursor_factory=None):
        self.pool, self.conn, self.cursor_factory = pool, conn, cursor_factory
        self.released = False

    def __getattr__(self, name):
        return getattr(self.conn, name)

    def cursor(self, *args, **kwargs):
        if self.cursor_factory is not None:
            kwargs.setdefault('cursor_factory', self.cursor_factory)
        return self.conn.cursor(*args, **kwargs)

    def rollback(self):
        # Cleanup must not hide the original error after a severed SSL socket.
        if not self.conn.closed:
            return self.conn.rollback()

    def close(self):
        if self.released:
            return
        self.released = True
        discard = bool(self.conn.closed)
        try:
            if not discard:
                self.conn.rollback()
        except Exception:
            discard = True
        finally:
            with _guard:
                if discard:
                    _returned_at.pop(self.conn, None)
                else:
                    _returned_at[self.conn] = time.monotonic()
            self.pool.putconn(self.conn, close=discard)

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        try:
            return self.conn.__exit__(kind, value, traceback)
        finally:
            self.close()


def connect(url, cursor_factory=None):
    key = (os.getpid(), url)
    with _guard:
        pool = _pools.get(key)
        if pool is None:
            pool = ThreadedConnectionPool(1, 12, url, sslmode='require',
                                          connect_timeout=5, application_name='suying-v2',
                                          keepalives=1, keepalives_idle=30,
                                          keepalives_interval=10, keepalives_count=3)
            _pools[key] = pool
    # Probe idle connections BEFORE handing them to application code. Never
    # retry an application transaction: its writes may already have committed.
    for attempt in range(2):
        conn = pool.getconn()
        with _guard:
            returned = _returned_at.pop(conn, None)
        try:
            if conn.closed:
                raise psycopg2.InterfaceError('closed pooled connection')
            if returned is None or time.monotonic() - returned >= 30:
                with conn.cursor() as cur:
                    cur.execute('SELECT 1')
                conn.rollback()
            return Connection(pool, conn, cursor_factory)
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            pool.putconn(conn, close=True)
            if attempt:
                raise
