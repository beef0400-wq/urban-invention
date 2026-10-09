"""Isolated startup smoke for shared Postgres portal. Sends no LINE messages."""
import uuid, io
from datetime import timedelta
import cv2, numpy as np
import app as g, membership, store, web_portal as web

def main():
    marker='__SUYING_PORTAL_V27_VERIFIED__'
    if store.get_state(marker).get('passed'):
        print('SUYING_PORTAL_SMOKE already verified; skips repeated smoke',flush=True);return
    uid='__SUYING_PORTAL_SMOKE__'+uuid.uuid4().hex
    keys=[]
    try:
        with g.app.test_client() as c:
            link=web.issue_link(uid);token=link.split('token=')[1];keys.append('web:login:'+web.hashed(token))
            assert c.get(link,base_url=web.ORIGIN).status_code==302
            assert c.get(link,base_url=web.ORIGIN).status_code==401
            cookie=c.get_cookie(web.COOKIE,domain='ai-rational-companion-v1-test.onrender.com').value;keys.append(web.session_key(cookie))
            data=c.get('/api/portal',base_url=web.ORIGIN).json
            keys.append('suying:account:'+data['account']['code'])
            assert data['account']['code'].startswith('SY-') and 'register' not in data
            headers={'X-CSRF-Token':data['csrf']}
            assert c.post('/api/command',base_url=web.ORIGIN,json={'command':'免費體驗','request_id':uuid.uuid4().hex}).status_code==403
            for cmd in ('免費體驗','牌路 紅藍紅紅藍藍紅藍紅藍紅紅藍紅藍和','確認開始','紅','撤回上一筆','今日追蹤'):
                rid=uuid.uuid4().hex;keys.append('web:request:'+web.hashed(cookie+rid))
                response=c.post('/api/command',base_url=web.ORIGIN,headers=headers,json={'command':cmd,'mode':'baccarat','request_id':rid})
                assert response.status_code==200 and response.json.get('replies')
            data=c.get('/api/portal',base_url=web.ORIGIN).json
            assert data['active'] and len(data['road'])==16
            rid=uuid.uuid4().hex;keys.append('web:request:'+web.hashed(cookie+rid))
            response=c.post('/api/command',base_url=web.ORIGIN,headers=headers,json={'command':'開始新桌','mode':'baccarat','request_id':rid})
            assert response.status_code==200
            data=c.get('/api/portal',base_url=web.ORIGIN).json
            assert data['road']==[] and not data['active'] and data['access']
            assert 'progress' not in data
            assert c.get('/api/admin/activities',base_url=web.ORIGIN).status_code==403
            assert c.get('/').status_code==200
            assert c.post('/api/logout',base_url=web.ORIGIN,headers=headers).status_code==200
            assert c.get('/api/portal',base_url=web.ORIGIN).status_code==401
        store.put_state(marker,{'passed':True,'at':membership.now_tw().isoformat()})
        print('SUYING_PORTAL_SMOKE PASS: Postgres one-use login, CSRF, shared trial/road/undo, fresh table reset, tracking and logout; no messages sent',flush=True)
    finally:
        with store.cursor(True) as c:
            for key in keys+[uid,'membership:'+uid]:c.execute('DELETE FROM v2_state WHERE user_id=%s',(key,))
            c.execute('DELETE FROM v2_records WHERE user_id=%s',(uid,))
            for table,column in [('users','line_user_id'),('platform_users','line_user_id'),('platform_memberships','line_user_id'),('members','user_id'),('free_trials','user_id')]:
                c.execute('DELETE FROM '+table+' WHERE '+column+'=%s',(uid,))

if __name__=='__main__':main()
