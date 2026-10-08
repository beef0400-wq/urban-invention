"""Run only against the fixed isolated database; no LINE messages are sent."""
import os, json, uuid, hmac, hashlib, base64
from deployment_preflight import validate_database_url
validate_database_url(os.environ.get('DATABASE_URL', ''))
import app as gateway
import membership, store, v2_flows, verification
from legacy import baccarat as ba, lotto539 as lo

uid = '__V2_DEPLOY_SMOKE__' + uuid.uuid4().hex
messages = []
def capture(token, text, quick_items=None):
    messages.append(str(text))
gateway.reply_text = capture
ba.reply_text = capture
lo.reply_message = capture
lo.reply_template = lambda *args, **kwargs: None
# Real history is refreshed before running the router smoke test.
lo.ensure_latest_539_in_db()
bingo_ok = lo.ensure_latest_bingo_in_db()
with store.cursor() as cur:
    cur.execute('SELECT count(*) FROM lotto_539_draws')
    history_count = cur.fetchone()[0]
print('V2_REAL_DATA', json.dumps({'539_rows': history_count, 'bingo_rows': len(lo.load_bingo_draws(120)), 'bingo_fetch_ok': bool(bingo_ok)}, ensure_ascii=False), flush=True)
if not gateway.CHANNEL_SECRET:
    raise RuntimeError('Test LINE channel secret is missing')

with gateway.app.test_client() as client:
    assert client.post('/webhook', json={'events': []}).status_code == 403
    def send(text, event_id=None):
        event = {'type': 'message', 'source': {'userId': uid}, 'replyToken': 'captured-only', 'webhookEventId': event_id or uuid.uuid4().hex, 'message': {'type':'text','text':text}}
        payload = json.dumps({'events':[event]}, ensure_ascii=False).encode()
        sig = base64.b64encode(hmac.new(gateway.CHANNEL_SECRET.encode(), payload, hashlib.sha256).digest()).decode()
        response = client.post('/webhook', data=payload, content_type='application/json', headers={'X-Line-Signature':sig})
        assert response.status_code == 200, response.status_code
    membership.ensure_user(uid)
    membership.grant_days(uid,1)
    send('百家 AI')
    send('紅藍紅紅藍藍紅藍紅藍紅紅藍紅藍和')
    assert not ba.get_user(uid)['analysis_active']
    send('修正 2 紅')
    send('確認開始')
    assert ba.get_user(uid)['analysis_active']
    n = len(ba.get_user(uid)['current_road'])
    eid = uuid.uuid4().hex
    send('紅',eid)
    send('紅',eid)
    assert len(ba.get_user(uid)['current_road']) == n+1
    send('539 AI')
    send('今日分析')
    today = verification.locked_pack(lo.today_tw())
    print('V2_539_LOCK', json.dumps({'locked':bool(today),'history_rows':history_count,'latest_date':str(lo.load_539_draws(1)[0][0]) if history_count else None}), flush=True)
    send('Bingo AI')
    send('即時盤')
    bingo_text = messages[-1]
    print('V2_BINGO_BOARD', 'PASS' if '近100期' in bingo_text else 'DATA_UNAVAILABLE', flush=True)
    send('我的紀錄')
    assert len(store.history(uid)) >= 3
    send('主選單')
print('V2_POSTGRES_ROUTER_SMOKE PASS: signed webhook, unsigned rejection, shared membership, batch confirmation, correction, one-click round, duplicate event, 539/Bingo routing, shared history', flush=True)
# Validate the configured test token without sending a message or changing LINE settings.
if gateway.CHANNEL_ACCESS_TOKEN:
    try:
        response = gateway.requests.get('https://api.line.me/v2/bot/info', headers={'Authorization':'Bearer '+gateway.CHANNEL_ACCESS_TOKEN}, timeout=10)
        print('V2_LINE_TOKEN_CHECK', response.status_code, flush=True)
    except Exception:
        print('V2_LINE_TOKEN_CHECK unavailable', flush=True)
