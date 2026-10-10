import base64
from pathlib import Path
import cv2
import numpy as np
import road_vision as rv
import membership
import deployment_preflight as gate
from db_pool import Connection

EXPECTED = ['莊','閒','莊','莊','閒','閒','和','閒','莊','莊','莊','閒','莊','和','閒','莊','閒','閒','莊','閒','閒','和','莊','閒','閒','莊','和','莊','閒','莊']

def fixture():
    raw = base64.b64decode((Path(__file__).parent/'fixtures/road_30.b64').read_text())
    return cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)

def parse(img):
    _, raw = cv2.imencode('.png',img)
    return rv.parse_baccarat_road_image(raw.tobytes())

def test_real_multiroad_sequence_at_multiple_sizes():
    img = fixture()
    for scale in (1, .8, 1.5):
        p = parse(cv2.resize(img,None,fx=scale,fy=scale))
        assert p.accepted and p.sequence == EXPECTED
        assert p.sequence.count('莊')==13 and p.sequence.count('閒')==13 and p.sequence.count('和')==4

def test_multiroad_inside_large_phone_screenshot():
    img=fixture()
    screenshot=np.full((2532,1170,3),24,np.uint8)
    screenshot[651:951,385:1145]=img
    p=parse(screenshot)
    assert p.accepted and p.sequence==EXPECTED

def test_missing_middle_cell_is_rejected():
    img = fixture()
    img[133:172,90:132] = 255
    assert not parse(img).accepted

def test_clipped_board_is_rejected():
    assert not parse(fixture()[20:]).accepted

def test_two_real_boards_cannot_silently_choose_one():
    img=fixture()[:234,:207]
    board=np.full((500,800,3),255,np.uint8)
    board[20:254,20:227]=img
    board[260:494,550:757]=img
    assert not parse(board).accepted

def test_pending_totals_and_start_instructions():
    import store, v2_flows
    store.init_db()
    text=v2_flows.pending('road-fixture',EXPECTED,'image',.9)
    assert '共 30 局' in text and '紅 13／藍 13／和 4' in text
    assert '確認開始' in text and '每局開出' in text
    assert '%' not in text

def test_bootstrap_runs_once_per_event_not_across_events(monkeypatch):
    from contextlib import contextmanager
    calls=[]
    class Cursor:
        def execute(self,*args):pass
    @contextmanager
    def cursor(**kwargs):yield Cursor()
    monkeypatch.setattr(membership,'DATABASE_URL','test')
    monkeypatch.setattr(membership,'_cursor',cursor)
    monkeypatch.setattr(membership,'bootstrap_from_legacy',lambda uid:calls.append(uid))
    for _ in range(2):
        with membership.request_scope():
            membership.ensure_user('U-speed');membership.ensure_user('U-speed')
    assert calls==['U-speed','U-speed']

def test_pool_returns_connection_on_success_and_failure():
    class Raw:
        closed=False
        def __exit__(self,*args):return False
        def rollback(self):pass
    class Pool:
        def __init__(self):self.calls=[]
        def putconn(self,conn,close=False):self.calls.append(close)
    pool=Pool()
    conn=Connection(pool,Raw())
    with conn:pass
    conn.close()
    assert pool.calls==[False]
    broken=Raw();broken.closed=True
    Connection(pool,broken).close()
    assert pool.calls==[False,True]

def test_cold_restart_cache_only_for_identical_validated_release(monkeypatch):
    monkeypatch.setattr(gate,'release_digest',lambda:'identical')
    monkeypatch.setattr(gate,'cached_release',lambda url,digest:True)
    monkeypatch.setattr(gate,'main',lambda:(_ for _ in ()).throw(AssertionError('full gate repeated')))
    gate.run_release_checks()
