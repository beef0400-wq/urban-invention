"""Confirmed native-button membership management; admin authorization on every step."""
import store,membership
from legacy import baccarat as ba

def handle(g,text,uid,token):
    if text!='管理會員' and not text.startswith(('管理開通 ','管理天數 ','確認開通會員','取消會員操作')):return False
    if uid not in g.ADMIN_USER_IDS:
        g.reply_text(token,'此功能僅限管理員。',[('主選單','主選單')]);return True
    state=store.get_state(uid)
    if text=='管理會員':
        state.pop('member_action',None);store.put_state(uid,state)
        if ba.use_db():
            with ba.db_conn() as conn:
                with conn.cursor() as c:
                    c.execute('SELECT line_user_id,bound_account FROM users WHERE bound_account IS NOT NULL ORDER BY updated_at DESC LIMIT 50');rows=c.fetchall()
        else:rows=[(k,v.get('bound_account')) for k,v in ba.MEMORY_USERS.items() if v.get('bound_account')]
        candidates=[(u,a) for u,a in rows if a and not membership.has_access(u)][:10]
        msg='會員中心｜管理會員\n\n選擇要開通的帳號，再選天數並確認。\n優先顯示最近綁定、目前無完整權限的10位。\n也可輸入：管理開通 帳號'
        g.reply_text(token,msg,[(a[:20],'管理開通 '+a) for _,a in candidates]+[('主選單','主選單')]);return True
    if text.startswith('管理開通 '):
        account=text.split(maxsplit=1)[1];target=ba.find_user_by_account(account)
        if not target:g.reply_text(token,'查無已綁定帳號，請會員先綁定。',[('返回管理','管理會員')]);return True
        state['member_action']={'uid':target['line_user_id'],'account':account};store.put_state(uid,state)
        g.reply_text(token,'會員中心｜選擇天數\n\n帳號：'+account+'\n'+membership.status_text(target['line_user_id']),[(f'{n}天',f'管理天數 {n}') for n in (3,7,30)]+[('取消','取消會員操作')]);return True
    if text=='取消會員操作':
        state.pop('member_action',None);store.put_state(uid,state);g.reply_text(token,'已取消會員操作。',[('返回管理','管理會員')]);return True
    action=state.get('member_action') or {}
    if not action:g.reply_text(token,'沒有待確認的會員操作。',[('返回管理','管理會員')]);return True
    if text.startswith('管理天數 '):
        try:days=int(text.split()[1]);assert days in (3,7,30)
        except (ValueError,IndexError,AssertionError):g.reply_text(token,'請使用3／7／30天按鈕。');return True
        action['days']=days;state['member_action']=action;store.put_state(uid,state)
        g.reply_text(token,f'會員中心｜開通確認\n\n帳號：{action["account"]}\n天數：{days}天\n範圍：百家＋539＋賓果\n有效正式會員會從原到期日延長，其他資格從現在起算。',[('確認開通','確認開通會員'),('取消','取消會員操作')]);return True
    if text=='確認開通會員' and action.get('days') in (3,7,30):
        target=ba.find_user_by_account(action['account'])
        if not target or target['line_user_id']!=action['uid']:
            state.pop('member_action',None);store.put_state(uid,state);g.reply_text(token,'帳號綁定已變更，請重新選擇。',[('返回管理','管理會員')]);return True
        exp=membership.grant_days(action['uid'],action['days'])
        state.pop('member_action',None);store.put_state(uid,state)
        store.record(uid,'admin',{'kind':'開通會員','account':action['account'],'days':action['days']})
        g.reply_text(token,f'會員中心｜已開通\n\n帳號：{action["account"]}\n到期：{exp.strftime("%Y-%m-%d %H:%M")}\n三種模式共用權限。',[('返回管理','管理會員'),('主選單','主選單')]);return True
    g.reply_text(token,'請先選天數，再確認開通。',[('返回管理','管理會員')]);return True
