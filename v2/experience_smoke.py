"""Isolated Postgres experience smoke; synthetic identity, replies captured only."""
import os,uuid
from deployment_preflight import validate_database_url

def main():
    validate_database_url(os.environ.get('DATABASE_URL',''))
    import app as g,store,membership,experience
    from legacy import baccarat as ba
    release_key='__V2_EXPERIENCE_V23_VERIFIED__'
    if store.get_state(release_key).get('passed'):
        print('V2_EXPERIENCE_SMOKE already verified; startup skips repeated smoke',flush=True)
        return
    uid='__V2_EXPERIENCE_SMOKE__'+uuid.uuid4().hex
    responses=[];original=g.reply_text
    def capture(token,text,quick_items=None):responses.append((text,quick_items))
    g.reply_text=capture
    def send(text):g.process_event({'type':'message','source':{'userId':uid},'replyToken':'synthetic','message':{'type':'text','text':text}})
    try:
        send('免費體驗');send('百家 AI');send('牌路 紅藍紅紅藍藍紅藍紅藍紅紅藍紅藍和');send('確認開始')
        old=experience.snapshot(ba.get_user(uid))
        send('紅');send('撤回上一筆');assert experience.snapshot(ba.get_user(uid))==old
        send('追加 藍和');assert ba.get_user(uid)['current_road']==old['current_road']
        send('確認修正');assert ba.get_user(uid)['current_road']==old['current_road']+['閒','和']
        send('撤回上一筆');send('539 AI');send('繼續本桌');assert membership.get_mode(uid)=='baccarat'
        send('主選單');assert '甦贏' in responses[-1][0] and '目前進度' not in responses[-1][0]
        send('今日追蹤');assert '今日追蹤' in responses[-1][0]
        # Validate real router output JSON through LINE; no delivery endpoint is used.
        import line_ui,requests
        headers={'Authorization':'Bearer '+g.CHANNEL_ACCESS_TOKEN,'Content-Type':'application/json'}
        for text,items in responses[-3:]:
            r=requests.post('https://api.line.me/v2/bot/message/validate/reply',headers=headers,json={'messages':line_ui.build_messages(text,items)},timeout=20)
            assert r.status_code==200,'LINE actual-router UI validation HTTP '+str(r.status_code)
        store.put_state(release_key,{'passed':True,'verified_at':membership.now_tw().isoformat()})
        print('V2_EXPERIENCE_SMOKE PASS: Postgres undo/correction/resume/home/tracking and actual-router LINE format; no messages sent',flush=True)
    finally:
        g.reply_text=original
        # Only the unique synthetic identity created by this run is removed.
        with store.cursor(True) as c:
            for table,col in [('v2_state','user_id'),('v2_records','user_id'),('users','line_user_id'),('platform_users','line_user_id'),('platform_memberships','line_user_id'),('members','user_id'),('free_trials','user_id')]:
                c.execute(f'DELETE FROM {table} WHERE {col}=%s',(uid,))

if __name__=='__main__':main()
