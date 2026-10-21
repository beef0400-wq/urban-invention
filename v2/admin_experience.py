"""Confirmed native-button membership management; admin authorization on every step."""
import store,membership,account_access,member_notifications
from legacy import baccarat as ba

def handle(g,text,uid,token):
    if text!='管理會員' and not text.startswith(('管理開通 ','管理天數 ','確認開通會員','取消會員操作')):return False
    if uid not in g.ADMIN_USER_IDS:
        g.reply_text(token,'此功能僅限管理員。',[('主選單','主選單')]);return True
    state=store.get_state(uid)
    if text=='管理會員':
        state.pop('member_action',None);store.put_state(uid,state)
        account_access.ensure(uid)
        candidates=[(a,account_access.profile(u)) for a,u in account_access.recent(bound_only=True)]
        msg='個人中心｜管理帳號\n\n最近綁定的帳號\n選帳號 → 選天數 → 確認。\n已開通的帳號也可延長期限。\n\n'+('\n'.join(p['username']+'｜'+p['status'] for a,p in candidates) if candidates else '目前沒有已綁定帳號。請會員先到「會員中心」輸入並確認帳號。')+'\n\n尚未綁定的會員不列入清單。\n也可輸入：管理開通 會員帳號'
        g.reply_text(token,msg,[(p['username'],'管理開通 '+p['username']) for a,p in candidates]+[('主選單','主選單')]);return True
    if text.startswith('管理開通 '):
        account=text.split(maxsplit=1)[1].upper();target_uid=account_access.resolve(account);target={'line_user_id':target_uid} if target_uid else None
        if not target:g.reply_text(token,'查無甦贏帳號，請對方先從LINE進入一次。',[('返回管理','管理會員')]);return True
        profile=account_access.profile(target_uid)
        account=profile['username'] or account
        display=profile['username'] or '尚未綁定'
        state['member_action']={'uid':target['line_user_id'],'account':account,'display':display};store.put_state(uid,state)
        g.reply_text(token,'會員中心｜選擇天數\n\n帳號：'+display+'\n'+membership.status_text(target['line_user_id']),[(f'{n}天',f'管理天數 {n}') for n in (3,7,30)]+[('取消','取消會員操作')]);return True
    if text=='取消會員操作':
        state.pop('member_action',None);store.put_state(uid,state);g.reply_text(token,'已取消會員操作。',[('返回管理','管理會員')]);return True
    action=state.get('member_action') or {}
    if not action:g.reply_text(token,'沒有待確認的會員操作。',[('返回管理','管理會員')]);return True
    display=account_access.profile(action['uid'])['username'] or '尚未綁定'
    if text.startswith('管理天數 '):
        try:days=int(text.split()[1]);assert days in (3,7,30)
        except (ValueError,IndexError,AssertionError):g.reply_text(token,'請使用3／7／30天按鈕。');return True
        action['days']=days;state['member_action']=action;store.put_state(uid,state)
        g.reply_text(token,f'會員中心｜開通確認\n\n帳號：{display}\n天數：{days}天\n範圍：百家＋539＋賓果\n有效正式會員會從原到期日延長，其他資格從現在起算。',[('確認開通','確認開通會員'),('取消','取消會員操作')]);return True
    if text=='確認開通會員' and action.get('days') in (3,7,30):
        target_uid=account_access.resolve(action['account']);target={'line_user_id':target_uid} if target_uid else None
        if not target or target['line_user_id']!=action['uid']:
            state.pop('member_action',None);store.put_state(uid,state);g.reply_text(token,'甦贏帳號已變更，請重新選擇。',[('返回管理','管理會員')]);return True
        renewed=membership.is_paid(action['uid'])
        exp=membership.grant_days(action['uid'],action['days'])
        state.pop('member_action',None);store.put_state(uid,state)
        store.record(uid,'admin',{'kind':'開通會員','account':action['account'],'days':action['days']})
        notification=member_notifications.send_grant(g,action['uid'],exp,renewed)
        g.reply_text(token,f'會員中心｜已開通\n\n帳號：{display}\n到期：{exp.strftime("%Y-%m-%d %H:%M")}\n三種模式共用權限。\n'+member_notifications.status_text(notification),[('返回管理','管理會員'),('主選單','主選單')]);return True
    g.reply_text(token,'請先選天數，再確認開通。',[('返回管理','管理會員')]);return True
