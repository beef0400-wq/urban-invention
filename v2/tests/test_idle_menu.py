import psycopg2
import pytest
import db_pool


class Raw:
    def __init__(self, broken=False):
        self.closed = False
        self.broken = broken
        self.probes = 0
        self.rollbacks = 0

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, sql):
        assert sql == 'SELECT 1'
        self.probes += 1
        if self.broken:
            self.closed = True
            raise psycopg2.OperationalError('SSL socket lost')

    def rollback(self):
        self.rollbacks += 1


class Pool:
    def __init__(self, connections):
        self.connections = list(connections)
        self.returned = []

    def getconn(self):
        return self.connections.pop(0)

    def putconn(self, conn, close=False):
        self.returned.append((conn, close))
        if not close:
            self.connections.append(conn)


def install(monkeypatch, connections):
    pool = Pool(connections)
    monkeypatch.setattr(db_pool, '_pools', {})
    monkeypatch.setattr(db_pool, '_returned_at', {})
    monkeypatch.setattr(db_pool, 'ThreadedConnectionPool', lambda *a, **kw: pool)
    return pool


def test_idle_ssl_socket_replaced_before_application_query(monkeypatch):
    stale, fresh = Raw(True), Raw()
    pool = install(monkeypatch, [stale, fresh])
    c = db_pool.connect('test')
    assert c.conn is fresh
    assert pool.returned == [(stale, True)]
    c.close()
    # A recently returned socket avoids another health-query round trip.
    c = db_pool.connect('test')
    assert c.conn is fresh and fresh.probes == 1
    c.close()


def test_connection_recovery_is_bounded(monkeypatch):
    a, b = Raw(True), Raw(True)
    pool = install(monkeypatch, [a, b])
    with pytest.raises(psycopg2.OperationalError):
        db_pool.connect('test')
    assert pool.returned == [(a, True), (b, True)]


def test_application_transaction_is_never_retried(monkeypatch):
    raw = Raw()
    pool = install(monkeypatch, [raw])
    c = db_pool.connect('test')
    raw.closed = True
    # Cleanup preserves the triggering error instead of masking it.
    c.rollback()
    c.close()
    assert pool.returned == [(raw, True)]


def test_home_alias_bypasses_analysis_and_cancels_binding(monkeypatch):
    import app as g, store, membership
    from legacy import baccarat as ba
    uid = 'U_fast_menu'
    store.init_db()
    membership.ensure_user(uid)
    ba.ensure_user(uid)
    store.put_state(uid, {'account_binding': {'stage': 'input'}, 'keep': 42})
    ba.update_user(uid, pending_flow='bind_account')
    captured = []
    monkeypatch.setattr(g, 'reply_text', lambda *a: captured.append(a))
    monkeypatch.setattr(g.v2_flows, 'handle', lambda *a: pytest.fail('home entered analysis router'))
    monkeypatch.setattr(membership, 'get_mode', lambda *a: pytest.fail('home queried mode'))
    g.process_event({'type': 'message', 'source': {'userId': uid},
                     'replyToken': 'test', 'message': {'type': 'text', 'text': '回主選單'}})
    assert len(captured) == 1 and '甦贏' in captured[0][1]
    assert store.get_state(uid) == {'keep': 42}
    assert ba.get_user(uid)['pending_flow'] is None
    monkeypatch.setattr(ba, 'update_user', lambda *a, **kw: pytest.fail('home rewrote whole table'))
    monkeypatch.setattr(store, 'put_state', lambda *a: pytest.fail('home rewrote binding state'))
    g.process_event({'type': 'message', 'source': {'userId': uid},
                     'replyToken': 'test', 'message': {'type': 'text', 'text': '主選單'}})
