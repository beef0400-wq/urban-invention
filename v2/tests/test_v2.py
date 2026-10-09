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
    assert all(k in isolate[-1][0] for k in ('綜合判讀','訊號指數','訊號彙整','支持訊號','反向訊號','風險','路況','即時數據'))
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
    assert '試用' in isolate[-1][0]

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


def test_real_source_markup_is_not_style_numbers():
    markup = '<style>.card {font-size: 24px}</style>開獎日期:2026/10/07(三)<span style="font-size:24px">05</span>, <span>11</span>, <span>14</span>, <span>18</span>, <span>19</span>'
    assert lo.parse_539_page(markup) == [(date(2026,10,7), '05 11 14 18 19')]
    assert lo.parse_539_page('開獎日期:2026/10/07(三) 05, 05, 14, 18, 19') == []
    assert lo.parse_539_page('開獎日期:2026/10/07(三) 資料更新中 font-size:24px') == []


def test_bingo_markup_and_date_required(monkeypatch):
    class Response:
        apparent_encoding = 'utf-8'
        def raise_for_status(self): pass
    nums = ',&nbsp;'.join(f'<span style="font-size:6vmin">{n:02d}</span>' for n in range(1,21))
    response = Response()
    response.text = '2026/10/8 BINGO <span>【期別: 115056947】</span><br/>'+nums+' 超級獎號: 01 (15:55)'
    monkeypatch.setattr(lo.HTTP,'get',lambda *a,**k:response)
    rows = lo.fetch_recent_bingo_results()
    assert len(rows)==1 and rows[0]['numbers']==list(range(1,21)) and rows[0]['date']==date(2026,10,8)
    response.text = response.text.replace('2026/10/8 BINGO', '')
    assert lo.fetch_recent_bingo_results()==[]


def test_new_postgres_member_has_no_separate_trial(monkeypatch):
    from contextlib import contextmanager
    class Cursor:
        def __init__(self): self.inserted=False; self.args=None
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def execute(self,sql,args):
            if 'INSERT INTO users' in sql:
                self.inserted=True; self.args=args
        def fetchone(self): return ba.default_user('db-new') if self.inserted else None
    cur=Cursor()
    class Connection:
        def cursor(self): return cur
        def commit(self): pass
    @contextmanager
    def connection(): yield Connection()
    monkeypatch.setattr(ba,'use_db',lambda:True)
    monkeypatch.setattr(ba,'db_conn',connection)
    user=ba.ensure_user('db-new')
    assert cur.args[1:3]==(None,None)
    assert user['trial_started_at'] is None and user['trial_end_at'] is None



def test_scheduler_cutoff_and_catchup(monkeypatch):
    import scheduled_verification as scheduler
    calls=[]
    monkeypatch.setattr(verification,'locked_pack',lambda d:None)
    monkeypatch.setattr(lo,'get_or_build_today_pick_539',lambda:calls.append('lock'))
    monkeypatch.setattr(lo,'ensure_latest_539_in_db',lambda:calls.append('refresh'))
    monkeypatch.setattr(lo,'load_539_draws',lambda n:[])
    monkeypatch.setattr(verification,'reconcile',lambda rows:calls.append('verify') or 0)
    scheduler.tick(datetime(2026,10,8,17,tzinfo=lo.TZ_TW))
    assert calls==[]
    scheduler.tick(datetime(2026,10,8,18,tzinfo=lo.TZ_TW))
    assert calls==['lock']
    scheduler.tick(datetime(2026,10,8,18,1,tzinfo=lo.TZ_TW))
    assert calls==['lock']
    scheduler.tick(datetime(2026,10,8,20,30,tzinfo=lo.TZ_TW))
    assert calls==['lock']
    scheduler.tick(datetime(2026,10,8,22,tzinfo=lo.TZ_TW))
    assert calls==['lock','refresh','verify']


def test_zero_signal_card_observes_and_uses_public_labels():
    user={'current_road':['莊','閒']*8}
    analysis={'signal_index':0,'signal':'弱','risk':'中','direction':'莊',
              'state':'中性','evidence':[('近期比例','閒','莊7 / 閒10')],
              'consensus':{'莊':0,'閒':1,'中性':0},'metrics':{'莊':7,'閒':10,'和':1}}
    card=ba.decision_card(user,analysis)
    assert '綜合判讀：觀望' in card
    assert '莊' not in card and '閒' not in card
    assert '紅7 / 藍10' in card and '訊號彙整' in card
    assert analysis['direction']=='莊'

def test_live_undo_restores_entire_round_and_only_once(isolate):
    import experience
    paid();send('百家 AI');send(road());send('確認開始')
    old=experience.snapshot(ba.get_user('U1'))
    send('藍');assert len(ba.get_user('U1')['current_road'])==len(old['current_road'])+1
    send('撤回上一筆');assert experience.snapshot(ba.get_user('U1'))==old
    send('撤回上一筆');assert experience.snapshot(ba.get_user('U1'))==old
    assert '沒有可撤回' in isolate[-1][0]

def test_live_correction_is_previewed_and_can_cancel(isolate):
    paid();send('百家 AI');send(road());send('確認開始');old=list(ba.get_user('U1')['current_road'])
    send('追加 紅藍和');assert ba.get_user('U1')['current_road']==old
    send('確認修正');assert ba.get_user('U1')['current_road']==old+['莊','閒','和']
    send('撤回上一筆');assert ba.get_user('U1')['current_road']==old
    send('修正 1 藍');send('取消更新');assert ba.get_user('U1')['current_road']==old

def test_table_choice_preserves_existing_road_and_stale_preview(isolate):
    paid();send('百家 AI');send(road());send('確認開始');old=list(ba.get_user('U1')['current_road'])
    send(road()+'紅藍');assert ba.get_user('U1')['current_road']==old
    assert store.get_state('U1')['pending']['added']==2
    send('確認開始');assert ba.get_user('U1')['current_road']==old
    send('紅');send('更新本桌');assert ba.get_user('U1')['current_road']==old+['莊']
    assert '過期' in isolate[-1][0]

def test_unique_overlap_and_ambiguous_alignment():
    import experience
    old=['莊']*13+['閒']+['莊','閒','和','莊','莊','閒','和','閒','莊','和','閒','莊']
    assert experience.align_road(old,old[-12:]+['閒'])[0]==old+['閒']
    assert experience.align_road(['莊']*30,['莊']*15+['閒'])==(None,None)

def test_current_table_from_other_mode_and_home_has_no_resume(isolate):
    paid();send('百家 AI');send(road());send('確認開始');send('539 AI');send('繼續本桌')
    assert membership.get_mode('U1')=='baccarat' and '綜合判讀' in isolate[-1][0]
    send('主選單');assert '進行中' not in isolate[-1][0] and '目前進度' not in isolate[-1][0]
    assert ('繼續本桌','繼續本桌') not in isolate[-1][1]

def test_bingo_window_filter_preserves_freshness(monkeypatch):
    from datetime import datetime
    stamp=lo.now_tw()
    draws=[{'date':stamp.date(),'time':stamp.strftime('%H:%M'),'period':str(i),'numbers':list(range(1,21))} for i in range(120)]
    monkeypatch.setattr(lo,'ensure_latest_bingo_in_db',lambda:True)
    monkeypatch.setattr(lo,'load_bingo_draws',lambda n:draws)
    msg=flow.bingo_board(50)
    assert '近50期' in msg and '近20期' not in msg and '近100期' not in msg
    assert all('近'+str(n)+'期' in flow.bingo_board() for n in (20,50,100))

def test_admin_button_confirmation_checks_permission_every_step(isolate,monkeypatch):
    monkeypatch.setattr(g,'ADMIN_USER_IDS',{'U1'})
    import account_access
    paid();ba.ensure_user('U2');code=account_access.ensure('U2')
    send('管理開通 '+code);send('管理天數 7')
    assert not membership.has_access('U2')
    monkeypatch.setattr(g,'ADMIN_USER_IDS',set());send('確認開通會員')
    assert not membership.has_access('U2')
    monkeypatch.setattr(g,'ADMIN_USER_IDS',{'U1'});send('確認開通會員')
    expiry=membership.get_expiry('U2');assert membership.is_paid('U2')
    send('確認開通會員');assert membership.get_expiry('U2')==expiry


def test_admin_list_includes_trial_paid_and_new_accounts(isolate,monkeypatch):
    import account_access
    monkeypatch.setattr(g,'ADMIN_USER_IDS',{'U1'})
    for uid in ('Utrial','Upaid','Ufree'):
        g.process_event(event('會員中心',uid))
    membership.start_trial('Utrial',24)
    membership.grant_days('Upaid',30)
    send('管理會員')
    text,buttons=isolate[-1]
    for uid in ('Utrial','Upaid','Ufree','U1'):
        code=account_access.ensure(uid)
        assert any(command=='管理開通 '+code for _,command in buttons)
        assert code in text
    assert '試用中' in text and '已開通' in text and '待開通' in text


def test_first_message_creates_application_account(isolate):
    import account_access
    g.process_event(event('主選單','Unew'))
    assert any(uid=='Unew' for _,uid in account_access.recent())

def test_username_binding_confirmation_and_trial_shutdown(isolate):
    import account_access
    send('綁定帳號');send('player_123')
    assert not account_access.profile('U1')['username']
    send('確認綁定')
    assert account_access.profile('U1')['username']=='player_123'
    assert '請回小幫手驗證開通' in isolate[-1][0]
    assert not membership.has_access('U1')
    send('免費體驗');assert not membership.has_access('U1')
    send('會員中心');assert all(command!='免費體驗' for _,command in isolate[-1][1])
    assert account_access.resolve('PLAYER_123')=='U1'
    with pytest.raises(ValueError):account_access.bind('U2','Player_123')
    with pytest.raises(ValueError):account_access.bind('U1','changed_name')
    assert account_access.bind('U1','PLAYER_123')=='player_123'

def test_one_hour_trial_binding_keeps_expiry_and_enforces_all_modes(isolate,monkeypatch):
    import account_access
    start=membership.now_tw();monkeypatch.setattr(membership,'now_tw',lambda:start)
    send('免費體驗');assert membership.get_expiry('U1')==start+timedelta(hours=1)
    account_access.bind('U1','sample_123')
    assert membership.has_access('U1') and not account_access.profile('U1')['trial_available']
    monkeypatch.setattr(membership,'now_tw',lambda:start+timedelta(hours=1,seconds=1))
    assert not membership.has_access('U1')
    for mode,command in [('百家 AI','紅'),('539 AI','今日陪跑'),('Bingo AI','即時盤')]:
        send(mode);send(command)
        assert '到期' in isolate[-1][0] and '小幫手' in isolate[-1][0]
        assert all(cmd!='免費體驗' for _,cmd in isolate[-1][1])
    assert membership.start_trial('U1')[1]=='bound'

def test_binding_cancel_and_invalid(isolate):
    import account_access
    send('綁定帳號');send('<script>');assert '4～20' in isolate[-1][0]
    send('cancel_123');send('取消綁定');send('確認綁定')
    assert account_access.profile('U1')['username'] is None

def test_539_default_hides_details_and_preserves_locked_numbers(isolate,monkeypatch):
    d=date(2026,10,9);saved=pack(d)
    model=json.loads(saved['note']);model.update(core5='01 02 03 04 05',diagnostics={'1':{'score':80,'freq30':5,'gap':3,'tags':['短期熱']}},pattern_note='模型規則說明')
    saved['note']=json.dumps(model)
    monkeypatch.setattr(lo,'today_tw',lambda:d)
    monkeypatch.setattr(lo,'get_or_build_today_pick_539',lambda:saved)
    monkeypatch.setattr(lo,'load_539_draws',lambda *a,**k:[(d-timedelta(days=1),[11,12,13,14,15])])
    paid();send('539 AI');send('今日陪跑')
    text,buttons=isolate[-1]
    assert '上期開獎｜實際開出' in text and '本期分析預測' in text
    assert model['motherboard'] in text and model['stable2'] in text
    assert all(x not in text for x in ('逐號依據','模型規則說明','驗證碼','公開驗證'))
    assert ('看完整資訊','539完整資訊') in buttons
    before=len(store.history('U1'))
    send('539逐號依據');assert '近30期：5次' in isolate[-1][0]
    send('539完整資訊');assert '模型規則說明' in isolate[-1][0]
    assert len(store.history('U1'))==before
    assert json.loads(saved['note'])==model

def test_tutorials_cover_all_modes_without_access(isolate):
    send('百家 AI');send('使用教學')
    text,buttons=isolate[-1]
    assert all(x in text for x in ('百家','539','賓果'))
    for command,expected in [('教學百家','訊號指數'),('教學539','上期開獎'),('教學賓果','冷號')]:
        assert command in [b for a,b in buttons]
        send(command);assert expected in isolate[-1][0]

def test_personal_history_recent_five_days_and_five_entries(isolate):
    old=(membership.now_tw()-timedelta(days=10)).isoformat()
    with store.cursor(True) as c:c.execute('INSERT INTO v2_records VALUES (%s,%s,%s,%s,%s)',('oldrecord','U1','539',old,json.dumps({'kind':'舊紀錄'})))
    for i in range(8):store.record('U1','539',{'kind':'新紀錄'+str(i)})
    send('我的紀錄');text=isolate[-1][0]
    assert '舊紀錄' not in text and text.count('新紀錄')==5

def test_verification_compact_keeps_only_five_periods():
    for i in range(8):
        d=date(2026,10,9)-timedelta(days=i)
        with store.cursor(True) as c:c.execute('INSERT INTO v2_public_539(target_date,locked_at,digest,payload,actual) VALUES (%s,%s,%s,%s,%s)',(d.isoformat(),'2026-10-09T10:00:00+08:00','abc123',json.dumps(pack(d)),json.dumps([30,31,32,33,34])))
    text=verification.report(5,compact=True)
    assert text.count('事前分析｜母盤')==5 and text.count('實際開獎')==6
    assert '驗證碼' not in text and '2026-10-02' not in text
    assert '中獎組合' in verification.report(5)
