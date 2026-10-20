import os
import sys
import json
from pathlib import Path

os.environ.pop('DATABASE_URL',None)
os.environ['LOCAL_DB_PATH']='/tmp/suying-point-engine-tests.sqlite3'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import pytest
import app as g
import membership, store, point_engine, line_ui, web_portal
from legacy import baccarat as ba


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    with store.cursor(True) as c:
        for table in ('v2_state','v2_records','v2_events'):
            c.execute('DELETE FROM '+table)
    ba.MEMORY_USERS.clear()
    membership._MEMORY.clear()
    replies=[]
    monkeypatch.setattr(g,'reply_text',lambda token,text,quick_items=None:replies.append((text,quick_items)))
    return replies


def send(text,uid='points-user'):
    g.process_event({'type':'message','source':{'userId':uid},'replyToken':'test',
                     'message':{'type':'text','text':text}})


def paid(uid='points-user'):
    membership.ensure_user(uid)
    membership.grant_days(uid,30)
    return ba.ensure_user(uid)


def configure(mode='標準',point_range='1000-3000',target='30%'):
    send('點數配置')
    send('點數區間 '+point_range)
    send('點數打法 '+mode)
    send('點數目標 '+target)


@pytest.mark.parametrize('mode',ba.PLAY_MODES)
def test_modes_complete_atomically_and_keep_live_table(mode,clean):
    paid()
    road=list('莊閒莊莊閒閒莊閒莊閒莊莊閒莊閒')
    ba.update_user('points-user',current_road=road,analysis_active=True,
                   imported_ready=True,last_prediction='莊',loss_streak=2)
    store.put_state('points-user',{'pending':{'sequence':['莊'],'kind':'edit'},'undo':{'keep':True}})
    send('點數配置');send('點數區間 1000-3000');send('點數打法 '+mode)
    assert ba.get_user('points-user')['point_range'] is None
    send('點數目標 30%')
    user=ba.get_user('points-user')
    assert (user['point_range'],user['play_mode'],user['target_profit']) == ('1000-3000',mode,'30%')
    assert user['current_road']==road and user['analysis_active'] and user['last_prediction']=='莊'
    assert user['loss_streak']==2
    assert store.get_state('points-user')['pending']['kind']=='edit'
    assert store.get_state('points-user')['undo']=={'keep':True}
    assert '本輪參考' in clean[-1][0]


def test_entry_routes_from_another_mode(clean):
    paid();membership.set_mode('points-user','539')
    send('點數引擎')
    assert membership.get_mode('points-user')=='baccarat'
    assert '點數引擎' in clean[-1][0]


def test_cancel_and_home_preserve_saved_profile():
    paid();configure()
    for cancel in ('取消點數設定','主選單'):
        send('點數配置');send('點數區間 30000以上');send(cancel)
        assert point_engine.KEY not in store.get_state('points-user')
        assert ba.get_user('points-user')['point_range']=='1000-3000'


def test_forged_or_expired_selection_cannot_save():
    paid();send('點數目標 100%');send('點數區間 30000以上')
    assert ba.get_user('points-user')['point_range'] is None


def test_expired_member_cannot_change_profile(clean):
    ba.ensure_user('points-user')
    send('點數配置')
    assert point_engine.KEY not in store.get_state('points-user')
    assert ba.get_user('points-user')['point_range'] is None
    assert '試用' in clean[-1][0] or '開通' in clean[-1][0]


def test_old_plain_text_choices_still_work():
    paid();send('點數配置');send('1000～3000點');send('保守');send('50%')
    assert ba.get_user('points-user')['target_profit']=='50%'
    assert ba.get_user('points-user')['play_mode']=='保守'


def test_mode_shortcut_uses_saved_range_but_requires_last_step():
    paid();configure();send('打法模式');send('點數打法 保守')
    assert ba.get_user('points-user')['play_mode']=='標準'
    send('點數目標 30%')
    assert ba.get_user('points-user')['play_mode']=='保守'


def test_tianmen_does_not_activate_invented_rules(clean):
    paid();configure();send('天門公式')
    assert '五關點數表' in clean[-1][0]
    assert '五關未中' in clean[-1][0]
    assert ba.get_user('points-user')['play_mode']=='標準'


@pytest.mark.parametrize('name,amounts,total',[
    ('豐田',(50,150,350,750,1550),2850),
    ('賓士',(100,300,700,1500,3100),5700),
    ('保時捷',(300,900,2100,4500,9300),17100),
    ('法拉利',(500,1500,3500,7500,15500),28500),
    ('勞斯',(1000,3000,7000,15000,31000),57000),
])
def test_owner_table_exact_and_read_only(name,amounts,total,clean):
    paid();configure()
    before=ba.get_user('points-user').copy()
    send('天門方案 '+name)
    assert point_engine.TIANMEN_PLANS[name]==amounts
    assert sum(amounts)==total
    assert f'五關累計：{total:,} 點' in clean[-1][0]
    for label,amount in zip(('天一','天二','天三','天四','天五'),amounts):
        assert f'{label}：{amount:,} 點' in clean[-1][0]
    assert ba.get_user('points-user')==before
    assert '天門方案 '+name in web_portal.COMMANDS


def test_settings_can_interrupt_binding():
    paid();store.put_state('points-user',{'account_binding':{'stage':'input'}})
    send('點數配置')
    state=store.get_state('points-user')
    assert 'account_binding' not in state and state[point_engine.KEY]['step']=='range'


def test_configured_points_visible_and_original_loss_pause():
    user=paid();configure()
    user=ba.update_user('points-user',current_road=list('莊閒'*10),analysis_active=True,loss_streak=3)
    analysis=ba.analyze_v15(user)
    assert ba.calculate_points(user,analysis)['high']==0
    assert '點數引擎' in ba.decision_card(user,analysis)
    assert '暫停' in point_engine.summary(user)


def test_point_section_has_its_own_flex_actions():
    paid();user=ba.update_user('points-user',current_road=list('莊閒'*10),analysis_active=True)
    messages=line_ui.build_messages(ba.detail_card(user,ba.analyze_v15(user)),g.baccarat_live_buttons())
    cards=[]
    for message in messages:
        content=message['contents']
        cards.extend(content['contents'] if content['type']=='carousel' else [content])
    point_card=next(card for card in cards if '點數引擎' in json.dumps(card['body'],ensure_ascii=False))
    assert '點數引擎' in json.dumps(point_card['footer'],ensure_ascii=False)
    assert '天門公式' in json.dumps(point_card['footer'],ensure_ascii=False)


def test_web_commands_complete_same_flow(monkeypatch):
    # Restore the capture transport used by the real web endpoint.
    def reply(token,text,quick_items=None):
        web_portal.CAPTURE.get().append((text,quick_items))
    monkeypatch.setattr(g,'reply_text',reply)
    uid='web-points';paid(uid)
    with g.app.test_client() as client:
        response=client.get(web_portal.issue_link(uid),base_url=web_portal.ORIGIN)
        assert response.status_code==302
        session=client.get('/api/portal',base_url=web_portal.ORIGIN).json
        for i,command in enumerate(('點數配置','點數區間 1000-3000','點數打法 標準','點數目標 30%','天門公式','天門方案 賓士')):
            response=client.post('/api/command',base_url=web_portal.ORIGIN,
                                 headers={'X-CSRF-Token':session['csrf']},
                                 json={'command':command,'mode':'baccarat','request_id':f'points-request-{i:04d}'})
            assert response.status_code==200
            assert response.json['replies']
            if i<3:
                assert response.json['replies'][0]['buttons']
    assert ba.get_user(uid)['point_range']=='1000-3000'


def tracker():
    return store.get_state('points-user')[point_engine.TIANMEN_KEY]


@pytest.mark.parametrize('plan',point_engine.TIANMEN_PLANS)
def test_tianmen_five_losses_stop_ties_do_not_reset(plan,clean,monkeypatch):
    paid();ba.update_user('points-user',current_road=list('莊閒'*10),analysis_active=True,last_prediction='莊')
    monkeypatch.setattr(point_engine,'observation_direction',lambda user,analysis:'莊')
    send('開始天門 '+plan)
    for i in range(5):
        assert tracker()['stage']==i and tracker()['active']
        send('和')
        assert tracker()['stage']==i and tracker()['losses']==i
        send('閒')
    assert not tracker()['active'] and tracker()['losses']==5
    before=tracker()
    send('閒');send('莊')
    assert tracker()==before
    assert '五關方向比對未中' in clean[-1][0]


def test_tianmen_win_resets_without_stop_and_preserves_legacy(monkeypatch):
    paid();configure()
    ba.update_user('points-user',current_road=list('莊閒'*10),analysis_active=True,last_prediction='莊')
    monkeypatch.setattr(point_engine,'observation_direction',lambda user,analysis:'莊')
    send('開始天門 賓士')
    for _ in range(8):
        for _ in range(4): send('閒')
        send('莊')
        assert tracker()['stage']==0 and tracker()['losses']==0 and tracker()['active']
    assert ba.get_user('points-user')['play_mode']=='標準'
    send('主選單');send('天門公式')
    assert tracker()['active']
    send('停止天門')
    assert not tracker()['active']


def test_tianmen_start_guard_undo_and_restart(monkeypatch):
    paid();ba.update_user('points-user',current_road=list('莊閒'*10),analysis_active=True,last_prediction='莊')
    monkeypatch.setattr(point_engine,'observation_direction',lambda user,analysis:'莊')
    send('開始天門 豐田');send('閒')
    send('開始天門 豐田')
    assert tracker()['plan']=='豐田' and tracker()['stage']==1
    send('撤回上一筆')
    assert tracker()['stage']==0
    send('撤回上一筆')
    assert tracker()['stage']==0
    send('停止天門');send('開始天門 勞斯')
    assert tracker()['plan']=='勞斯' and tracker()['active']


def test_tianmen_no_access_no_state():
    send('開始天門 賓士')
    assert point_engine.TIANMEN_KEY not in store.get_state('points-user')


def test_live_first_card_contains_points_and_only_one_result_input(clean):
    paid();ba.update_user('points-user',current_road=list('莊閒'*10),analysis_active=True)
    send('開始天門 賓士')
    text,buttons=clean[-1]
    assert '即時分析盤' in text and '100 點' in text
    assert {'莊','閒','和'} <= {cmd for _,cmd in buttons}
    assert not {'天門贏','天門輸','天門和'} & {cmd for _,cmd in buttons}
    messages=line_ui.build_messages(text,buttons)
    first=messages[0]['contents']
    if first['type']=='carousel':first=first['contents'][0]
    body=json.dumps(first['body'],ensure_ascii=False)
    assert '天門公式' in body and '100 點' in body and '本輪觀察' in body
    configure()
    assert store.get_state('points-user')['point_method']=='legacy'
    assert '即時分析盤' in clean[-1][0] and '打法：標準' in clean[-1][0]


def test_old_detached_buttons_no_longer_advance_and_observation_holds(monkeypatch):
    paid();ba.update_user('points-user',current_road=list('莊閒'*10),analysis_active=True)
    send('開始天門 賓士');before=tracker()
    for command in ('天門輸','天門贏','天門和','撤回天門'):send(command)
    assert tracker()==before
    monkeypatch.setattr(point_engine,'observation_direction',lambda user,analysis:None)
    send('莊');send('閒')
    assert tracker()==before


def test_undo_does_not_replace_a_newly_selected_plan(monkeypatch):
    paid();ba.update_user('points-user',current_road=list('莊閒'*10),analysis_active=True)
    monkeypatch.setattr(point_engine,'observation_direction',lambda user,analysis:'莊')
    send('開始天門 賓士');send('閒');send('開始天門 豐田');send('撤回上一筆')
    assert tracker()['plan']=='豐田' and tracker()['stage']==0


def test_live_web_tianmen_flow(monkeypatch):
    monkeypatch.setattr(g,'reply_text',lambda token,text,quick_items=None:web_portal.CAPTURE.get().append((text,quick_items)))
    uid='web-live-points';paid(uid)
    ba.update_user(uid,current_road=list('莊閒'*10),analysis_active=True)
    monkeypatch.setattr(point_engine,'observation_direction',lambda user,analysis:'莊')
    with g.app.test_client() as client:
        client.get(web_portal.issue_link(uid),base_url=web_portal.ORIGIN)
        csrf=client.get('/api/portal',base_url=web_portal.ORIGIN).json['csrf']
        for i,command in enumerate(('開始天門 賓士','閒','和','撤回上一筆','莊')):
            response=client.post('/api/command',base_url=web_portal.ORIGIN,
                headers={'X-CSRF-Token':csrf},json={'command':command,'mode':'baccarat','request_id':f'live-points-request-{i}'})
            assert response.status_code==200
            assert response.json['replies'][0]['buttons']
        assert store.get_state(uid)[point_engine.TIANMEN_KEY]['stage']==0
