import os, sys, json, base64, hmac, hashlib
from pathlib import Path
from datetime import datetime,date,timedelta
os.environ.pop('DATABASE_URL',None)
os.environ['CHANNEL_SECRET']='test-secret'
os.environ['LOCAL_DB_PATH']='/tmp/rational-v2-test.sqlite3'
Path(os.environ['LOCAL_DB_PATH']).unlink(missing_ok=True)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as g
import pytest
import membership, store, v2_flows as flow, verification
from legacy import baccarat as ba, lotto539 as lo

@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    with store.cursor(True) as c:
        for table in ('v2_records','v2_state','v2_public_539','v2_events','v2_bingo_provenance'): c.execute('DELETE FROM '+table)
    membership._MEMORY.clear();ba.MEMORY_USERS.clear();ba.MEMORY_LOGS.clear()
    messages=[]
    monkeypatch.setattr(g,'reply_text',lambda token,text,quick_items=None:messages.append((text,quick_items)))
    yield messages

def event(text,uid='U1',eid=None):
    e={'type':'message','source':{'userId':uid},'replyToken':'reply','message':{'type':'text','text':text}}
    if eid:e['webhookEventId']=eid
    return e

def send(text):g.process_event(event(text))
def paid():membership.ensure_user('U1');membership.grant_days('U1',30)
def road():return '紅藍紅紅藍藍紅藍紅藍紅紅藍紅藍和'

def test_batch_confirm_and_one_click(isolate):
    paid();send('百家 AI');send(road())
    assert not ba.ensure_user('U1')['analysis_active']
    send('修正 2 紅');assert store.get_state('U1')['pending']['sequence'][1]=='莊'
    send('確認開始');u=ba.get_user('U1');n=len(u['current_road']);assert u['analysis_active']
    send('紅');u=ba.get_user('U1');assert len(u['current_road'])==n+1 and u['pending_flow'] is None
    assert all(k in isolate[-1][0] for k in ('綜合判讀','訊號指數','模型共識','支持訊號','反向訊號','風險','路況','即時數據'))
    assert len(store.history('U1'))>=1

def test_button_import_starts_once():
    paid();send('百家 AI');send('匯入牌路')
    for _ in range(15):send('匯入莊')
    send('完成匯入');assert ba.get_user('U1')['analysis_active']

def test_global_navigation_clears_legacy_pending(isolate):
    paid();send('百家 AI');ba.ensure_user('U1');ba.update_user('U1',pending_flow='bind_account')
    for t in ('主選單','539 AI','Bingo AI','會員中心','百家 AI'):send(t)
    assert ba.get_user('U1')['pending_flow'] is None
    assert ba.get_user('U1')['bound_account'] is None

def test_free_cannot_use_alias_or_batch(isolate):
    send('百家 AI');send('牌路 '+road());send('紅')
    assert not ba.ensure_user('U1')['analysis_active']
    assert '體驗' in isolate[-1][0]

def test_trial_persists_and_no_repeat():
    membership.start_trial('U1');membership._MEMORY.clear()
    assert membership.is_trial('U1') and not membership.is_paid('U1')
    assert membership.start_trial('U1')[1]=='used'

def test_webhook_signature_and_dedupe():
    paid();send('百家 AI');send(road());send('確認開始');n=len(ba.get_user('U1')['current_road'])
    body=json.dumps({'events':[event('紅',eid='e1')]}).encode()
    sig=base64.b64encode(hmac.new(b'test-secret',body,hashlib.sha256).digest()).decode()
    with g.app.test_client() as c:
        assert c.post('/webhook',data=body).status_code==403
        for _ in range(2):assert c.post('/webhook',data=body,headers={'X-Line-Signature':sig,'Content-Type':'application/json'}).status_code==200
    assert len(ba.get_user('U1')['current_road'])==n+1

def pack(d,nums='01 02 03 04 05 06 07 08 09 10'):
    return {'numbers':nums,'note':json.dumps({'data_fresh':True,'latest_draw_date':(d-timedelta(days=1)).isoformat(),'motherboard':nums,'stable2':'01 02 03','attack3':'01 02 03 04 05 06','burst4':'01 02 03 04 05 06 07'}),'hot_zone':'低','top_hot':'01 02 03'}

def test_lock_is_immutable_cutoff_and_exact_date():
    d=date(2026,10,2);t=datetime(2026,10,2,10,tzinfo=lo.TZ_TW)
    one=verification.lock(pack(d),d,t)
    assert verification.lock(pack(d,'11 12 13 14 15 16 17 18 19 20'),d,t)==one
    with pytest.raises(ValueError):verification.lock(pack(d+timedelta(days=1)),d+timedelta(days=1),datetime(2026,10,3,21,tzinfo=lo.TZ_TW))
    # No forecast exists for previous date: never match today's locked forecast backwards.
    with store.cursor(True) as c:
        c.execute('UPDATE v2_public_539 SET actual=%s WHERE target_date=%s',(json.dumps([30,31,32,33,34]),d.isoformat()))
    report=verification.report(7)
    assert '母盤命中 0' in report and '中獎組合 0' in report

@pytest.mark.parametrize('value',['BPTBPPBB','紅藍和','牌路: 紅藍和'])
def test_batch_formats(value):assert flow.parse_batch(value)

@pytest.mark.parametrize('value',['red blue','紅請給我藍','BLAH','修正 3 紅'])
def test_no_accidental_text_parse(value):assert flow.parse_batch(value) is None

def test_bingo_no_fake_or_unproven_writes(monkeypatch):
    assert lo.fallback_bingo_results(100)==[]
    assert lo.build_bingo_model([], '1')['data_ok'] is False
    monkeypatch.setattr(lo,'db_cursor',lambda **kw: (_ for _ in ()).throw(AssertionError('must not write')))
    lo.upsert_bingo_draws([{'period':'fake','numbers':list(range(1,21)),'source':'fallback'}])

def test_bingo_failure_does_not_read_old_db(monkeypatch):
    monkeypatch.setattr(lo,'ensure_latest_bingo_in_db',lambda:False)
    monkeypatch.setattr(lo,'load_bingo_draws',lambda n:(_ for _ in ()).throw(AssertionError('old DB read')))
    assert '資料異常' in flow.bingo_board()

def test_bingo_all_windows(monkeypatch):
    now=lo.now_tw();draws=[{'period':str(1000-i),'date':now.date(),'time':now.strftime('%H:%M'),'numbers':list(range(1+(i%40),21+(i%40)))} for i in range(100)]
    monkeypatch.setattr(lo,'ensure_latest_bingo_in_db',lambda:True);monkeypatch.setattr(lo,'load_bingo_draws',lambda n:draws)
    text=flow.bingo_board()
    assert all(k in text for k in ('近20期','近50期','近100期','升溫','降溫','區段','大 ','單 '))

def test_539_core_diagnostics(monkeypatch):
    monkeypatch.setattr(lo,'recent_539_performance_state',lambda:'normal')
    draws=[(date(2026,10,1)-timedelta(days=i),[1+i%20,2+i%20,3+i%20,4+i%20,5+i%20]) for i in range(240)]
    m=lo.build_539_models(draws)
    assert len(lo.parse_nums_text(m['motherboard']))==10
    assert len(m['diagnostics'])==10 and len(lo.parse_nums_text(m['core5']))==5
    with pytest.raises(ValueError):lo.build_539_models([])

def test_image_requires_confirm(monkeypatch):
    from road_vision import RoadParseResult
    paid();send('百家 AI');seq=flow.parse_batch(road())
    monkeypatch.setattr(g,'fetch_line_image',lambda _:b'img')
    monkeypatch.setattr(g,'parse_baccarat_road_image',lambda *a,**k:RoadParseResult(True,.9,seq,'bead-plate',16,6,3,''))
    e=event('');e['message']={'type':'image','id':'image1'};g.process_event(e)
    assert not ba.ensure_user('U1')['analysis_active']
    send('確認開始');assert ba.get_user('U1')['analysis_active']

def test_cron_denied_without_secret():
    with g.app.test_client() as c:
        for path in ('/cron/daily-push','/cron/update-539-result','/cron/check-bingo'):assert c.get(path).status_code==403


def test_exact_date_reconciliation_and_zero_preserved(monkeypatch):
    d=date(2026,10,2);verification.lock(pack(d),d,datetime(2026,10,2,10,tzinfo=lo.TZ_TW))
    with store.cursor(True) as c:
        c.execute('CREATE TABLE IF NOT EXISTS model_results (result_date TEXT PRIMARY KEY,motherboard TEXT,actual_numbers TEXT,hit_count INTEGER,created_at TEXT)')
        c.execute('DELETE FROM model_results')
    monkeypatch.setattr(lo,'db_cursor',lambda commit=False:store.cursor(commit))
    verification.reconcile([(d-timedelta(days=1),[1,2,3,4,5])])
    with store.cursor() as c:
        c.execute('SELECT actual FROM v2_public_539');assert c.fetchone()[0] is None
    verification.reconcile([(d,[30,31,32,33,34])])
    assert '母盤命中 0' in verification.report(90)
    with store.cursor() as c:
        c.execute('SELECT hit_count FROM model_results');assert c.fetchone()[0]==0
    # Repeating reconciliation cannot change the locked prediction or its verified result.
    verification.reconcile([(d,[1,2,3,4,5])])
    assert '母盤命中 0' in verification.report(30)


def test_no_automatic_legacy_trial():
    assert ba.ensure_user('new')['trial_end_at'] is None


def test_opencv_bead_sequence_and_blank():
    import cv2, numpy as np
    from road_vision import parse_baccarat_road_image
    seq=['莊','閒','和','莊','閒','閒','莊','閒','莊','和','閒','莊','閒','莊','莊','閒','莊','閒','和','莊','閒','莊','閒','莊']
    img=np.full((210,180,3),255,dtype=np.uint8)
    colors={'莊':(0,0,255),'閒':(255,0,0),'和':(0,170,0)}
    for i,x in enumerate(seq):cv2.circle(img,(25+(i//6)*35,20+(i%6)*30),9,colors[x],-1)
    _,bytes_=cv2.imencode('.png',img)
    parsed=parse_baccarat_road_image(bytes_.tobytes())
    assert parsed.accepted and parsed.sequence==seq
    _,blank=cv2.imencode('.png',np.full((200,200,3),255,dtype=np.uint8))
    assert not parse_baccarat_road_image(blank.tobytes()).accepted
    assert not parse_baccarat_road_image(b'corrupt').accepted


def test_big_road_is_not_guessed():
    import cv2,numpy as np
    from road_vision import parse_baccarat_road_image
    img=np.full((210,180,3),255,dtype=np.uint8)
    for c in range(4):
        for r in range(6):cv2.circle(img,(25+c*35,20+r*30),9,(0,0,255) if c%2==0 else (255,0,0),-1)
    _,b=cv2.imencode('.png',img)
    assert not parse_baccarat_road_image(b.tobytes()).accepted


def test_v15_original_core_regression():
    import importlib.util,random
    source=Path(__file__).resolve().parent/'reference/baccarat_v15.py'
    if not source.exists():pytest.skip('Original ZIP source required for equivalence check')
    spec=importlib.util.spec_from_file_location('original_ba',source);original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
    rng=random.Random(42)
    for count in range(15,115):
        u=ba.default_user('reference');u['current_road']=[rng.choice(['莊','閒','和']) for _ in range(count+15)]
        a,b=original.analyze_v15(u),ba.analyze_v15(u)
        for key in a:assert a[key]==b[key]


def test_539_original_selection_regression(monkeypatch):
    import importlib.util
    source=Path(__file__).resolve().parent/'reference/lotto539_original.py'
    if not source.exists():pytest.skip('Original ZIP source required for equivalence check')
    spec=importlib.util.spec_from_file_location('original_539',source);original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
    draws=[(date(2026,10,1)-timedelta(days=i),[1+i%20,2+i%20,3+i%20,4+i%20,5+i%20]) for i in range(240)]
    for mode in ('normal','recovery'):
        monkeypatch.setattr(original,'recent_539_performance_state',lambda:mode)
        monkeypatch.setattr(lo,'recent_539_performance_state',lambda:mode)
        a,b=original.build_539_models(draws),lo.build_539_models(draws)
        for key in ('motherboard','stable2','attack3','burst4','cold_note','pattern_note'):assert a[key]==b[key]
