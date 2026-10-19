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
    assert '未啟用' in clean[-1][0]
    assert ba.get_user('points-user')['play_mode']=='標準'


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
        for i,command in enumerate(('點數配置','點數區間 1000-3000','點數打法 標準','點數目標 30%','天門公式')):
            response=client.post('/api/command',base_url=web_portal.ORIGIN,
                                 headers={'X-CSRF-Token':session['csrf']},
                                 json={'command':command,'mode':'baccarat','request_id':f'points-request-{i:04d}'})
            assert response.status_code==200
            assert response.json['replies']
            if i<3:
                assert response.json['replies'][0]['buttons']
    assert ba.get_user(uid)['point_range']=='1000-3000'
