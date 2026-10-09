import os, sys, json, io
from pathlib import Path
os.environ.pop('DATABASE_URL',None)
os.environ['LOCAL_DB_PATH']='/tmp/rational-v2-test.sqlite3'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest, cv2, numpy as np
import app as g, web_portal as web, store, membership
from legacy import baccarat as ba
from datetime import timedelta

@pytest.fixture(autouse=True)
def clean():
    with store.cursor(True) as c:
        for table in ('v2_state','v2_records','v2_events'):c.execute('DELETE FROM '+table)
    membership._MEMORY.clear();ba.MEMORY_USERS.clear();g.ADMIN_USER_IDS=set()
    yield

def login(client,uid='U_web'):
    url=web.issue_link(uid)
    assert client.get(url,base_url=web.ORIGIN).status_code==302
    assert client.get(url,base_url=web.ORIGIN).status_code==401
    data=client.get('/api/portal',base_url=web.ORIGIN).json
    return {'X-CSRF-Token':data['csrf']}

def command(client,headers,cmd,rid='01234567890123456789',mode='baccarat'):
    return client.post('/api/command',base_url=web.ORIGIN,headers=headers,json={'command':cmd,'mode':mode,'request_id':rid})

def test_public_page_and_protected_data():
    with g.app.test_client() as c:
        assert '甦贏'.encode() in c.get('/').data
        assert c.get('/api/portal').status_code==401
        assert c.get('/api/activities').json['items']==[]
        h=login(c)
        assert command(c,{},'免費體驗').status_code==403
        assert command(c,h,'/vip x 30').status_code==400
        assert 'HttpOnly' in c.get(web.issue_link('another'),base_url=web.ORIGIN).headers['Set-Cookie']

def test_expired_login_and_session():
    with g.app.test_client() as c:
        link=web.issue_link('U_web');token=link.split('token=')[1]
        store.put_state('web:login:'+web.hashed(token),{'uid':'U_web','expires':(membership.now_tw()-timedelta(minutes=1)).isoformat()})
        assert c.get(link).status_code==401
        h=login(c);cookie=c.get_cookie(web.COOKIE,domain='ai-rational-companion-v1-test.onrender.com').value
        data=store.get_state(web.session_key(cookie));data['expires']=(membership.now_tw()-timedelta(minutes=1)).isoformat();store.put_state(web.session_key(cookie),data)
        assert c.get('/api/portal',base_url=web.ORIGIN).status_code==401

def test_trial_batch_confirmation_dedupe_and_shared_road():
    with g.app.test_client() as c:
        h=login(c)
        assert command(c,h,'免費體驗','trial012345678901234').status_code==200
        assert command(c,h,'牌路 紅藍紅紅藍藍紅藍紅藍紅紅藍紅藍和','batch012345678901234').status_code==200
        assert not ba.get_user('U_web')['analysis_active']
        r=command(c,h,'確認開始','start012345678901234');assert 'replies' in r.json
        assert len(ba.get_user('U_web')['current_road'])==16
        for _ in range(2):assert command(c,h,'紅','round012345678901234').status_code==200
        assert len(ba.get_user('U_web')['current_road'])==17
        assert c.get('/api/portal',base_url=web.ORIGIN).json['road'][-1]=='紅'
        assert command(c,h,'撤回上一筆','undo012345678901234').status_code==200
        assert len(ba.get_user('U_web')['current_road'])==16

def test_account_binding_and_cross_user_isolation():
    with g.app.test_client() as c:
        h=login(c)
        assert command(c,h,'綁定 hello_123',mode='539').status_code==200
        assert ba.get_user('U_web')['bound_account']=='hello_123'
    with g.app.test_client() as other:
        h=login(other,'U_other')
        assert other.get('/api/portal',base_url=web.ORIGIN).json['road']==[]
        assert command(other,h,'紅').status_code==200
        assert not membership.has_access('U_other')

def image():
    _,buf=cv2.imencode('.png',np.full((40,100,3),100,dtype=np.uint8));return io.BytesIO(buf.tobytes())

def save(c,h,title='Test campaign'):
    now=membership.now_tw()
    return c.post('/api/admin/activities',base_url=web.ORIGIN,headers=h,data={'kind':'month','title':title,'content':'內容','start':(now-timedelta(minutes=1)).isoformat()[:16],'end':(now+timedelta(days=1)).isoformat()[:16],'target':'539','image':(image(),'a.png')})

def publish(c,h):return c.post('/api/admin/activities',base_url=web.ORIGIN,headers=h,json={'kind':'month','action':'publish'})

def test_campaign_admin_preview_publish_and_preserve_live_during_edit():
    g.ADMIN_USER_IDS={'U_web'}
    with g.app.test_client() as c:
        h=login(c);r=save(c,h);assert r.status_code==200
        draft=r.json['item'];assert c.get(draft['image_url'],base_url=web.ORIGIN).status_code==200
        assert c.get('/api/activities').json['items']==[]
        with g.app.test_client() as public:assert public.get(draft['image_url']).status_code==401
        assert publish(c,h).status_code==200
        assert c.get('/api/activities').json['items'][0]['title']=='Test campaign'
        assert save(c,h,'Replacement').status_code==200
        assert c.get('/api/activities').json['items'][0]['title']=='Test campaign'
        assert publish(c,h).status_code==200
        assert c.get('/api/activities').json['items'][0]['title']=='Replacement'
        g.ADMIN_USER_IDS.clear()
        assert c.get('/api/admin/activities',base_url=web.ORIGIN).status_code==403

def test_campaign_end_schedule_image_and_invalid_input():
    with g.app.test_client() as c:
        h=login(c)
        assert c.get('/api/admin/activities',base_url=web.ORIGIN).status_code==403
        g.ADMIN_USER_IDS={'U_web'}
        r=save(c,h);assert r.status_code==200;publish(c,h)
        items=store.get_state(web.CAMPAIGNS);items['month']['end']=(membership.now_tw()-timedelta(seconds=1)).isoformat();store.put_state(web.CAMPAIGNS,items)
        assert c.get('/api/activities').json['items']==[]
        assert c.post('/api/admin/activities',base_url=web.ORIGIN,headers=h,json={'kind':'month','title':'a','start':'invalid'}).status_code==400
        assert c.post('/api/admin/activities',base_url=web.ORIGIN,json={'kind':'month','action':'hide'}).status_code==403

def test_capture_is_request_local_and_does_not_send_line(monkeypatch):
    def fail(*args,**kwargs):raise AssertionError('web command must not call LINE reply')
    monkeypatch.setattr(g.requests,'post',fail)
    with g.app.test_client() as c:
        h=login(c);assert command(c,h,'會員中心').json['replies']
        assert web.CAPTURE.get() is None
        assert c.post('/api/logout',base_url=web.ORIGIN,headers=h).status_code==200
        assert c.get('/api/portal',base_url=web.ORIGIN).status_code==401


def test_favorites_limits_persist_and_season_permissions():
    with g.app.test_client() as c:
        h=login(c)
        assert c.post('/api/favorites',base_url=web.ORIGIN,headers=h,json={'numbers':[1,39]}).status_code==200
        assert c.get('/api/portal',base_url=web.ORIGIN).json['favorites']==[1,39]
        for nums in ([0],[40],[True],list(range(1,12))):
            assert c.post('/api/favorites',base_url=web.ORIGIN,headers=h,json={'numbers':nums}).status_code==400
        assert c.post('/api/admin/activities',base_url=web.ORIGIN,headers=h,json={'action':'season','bingo_featured':True}).status_code==403
        g.ADMIN_USER_IDS={'U_web'}
        assert c.post('/api/admin/activities',base_url=web.ORIGIN,headers=h,json={'action':'season','bingo_featured':True}).status_code==200
        assert c.get('/api/activities').json['bingo_featured'] is True


def test_new_table_discards_live_progress_but_preserves_membership_and_records():
    with g.app.test_client() as c:
        h=login(c)
        command(c,h,'免費體驗','trialfresh012345678901')
        command(c,h,'牌路 紅藍紅紅藍藍紅藍紅藍紅紅藍紅藍和','batchfresh012345678901')
        command(c,h,'確認開始','startfresh012345678901')
        command(c,h,'紅','roundfresh012345678901')
        saved=store.get_state('U_web');saved['favorites_539']=[1,2];store.put_state('U_web',saved)
        assert command(c,h,'開始新桌','resetfresh012345678901').status_code==200
        data=c.get('/api/portal',base_url=web.ORIGIN).json
        assert data['active'] is False and data['road']==[] and not data['pending']
        assert data['access'] is True and data['favorites']==[1,2]
        assert store.history('U_web')
        assert 'undo' not in store.get_state('U_web')


def test_539_overview_separates_actual_and_forecast(monkeypatch):
    from legacy import lotto539 as engine
    import verification
    from datetime import date, datetime
    monkeypatch.setattr(membership, 'now_tw', lambda: datetime(2026,10,9,13,tzinfo=membership.TZ_TW))
    monkeypatch.setattr(engine, 'load_539_draws', lambda limit: [(date(2026,10,9),[2,4,6,8,10]),(date(2026,10,8),[1,3,5,7,9])])
    monkeypatch.setattr(verification,'locked_pack',lambda target: {'note':json.dumps({'motherboard':'11 12 13 14 15'})})
    with g.app.test_client() as c:
        data=c.get('/api/539/overview').json
        assert data['previous']=={'date':'2026-10-08','numbers':[1,3,5,7,9]}
        assert data['latest']['date']=='2026-10-09'
        assert data['prediction'] is None
        login(c)
        monkeypatch.setattr(membership,'has_access',lambda uid: True)
        data=c.get('/api/539/overview',base_url=web.ORIGIN).json
        assert data['prediction']['motherboard']==[11,12,13,14,15]
        assert '已開獎' in data['status']
        assert 'no-store' in c.get('/api/539/overview').headers['Cache-Control']
