"""Bounded reusable Postgres connections; no cached membership decisions."""
import threading
from psycopg2.pool import ThreadedConnectionPool

_pools = {}
_guard = threading.Lock()


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
            self.pool.putconn(self.conn, close=discard)

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        try:
            return self.conn.__exit__(kind, value, traceback)
        finally:
            self.close()


def connect(url, cursor_factory=None):
    with _guard:
        pool = _pools.get(url)
        if pool is None:
            pool = ThreadedConnectionPool(1, 12, url, sslmode='require',
                                          connect_timeout=5, application_name='suying-v2')
            _pools[url] = pool
    return Connection(pool, pool.getconn(), cursor_factory)
