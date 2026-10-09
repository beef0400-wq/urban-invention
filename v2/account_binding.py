"""User-owned binding flow. Binding never grants access."""
import store,account_access

def handle(g,text,uid,token):
    state=store.get_state(uid);pending=state.get('account_binding')
    buttons=[('取消綁定','取消綁定'),('個人中心','會員中心')]
    if text in ('取消綁定','主選單','會員中心','開啟甦贏','百家 AI','539 AI','Bingo AI','免費體驗'):
        state.pop('account_binding',None);store.put_state(uid,state)
        if text=='取消綁定':g.reply_text(token,'已取消綁定。',[('綁定帳號','綁定帳號')]);return True
        return False
    if text=='綁定帳號':
        profile=account_access.profile(uid)
        if profile['username']:
            g.reply_text(token,'已綁定帳號：'+profile['username']+'\n'+account_access.SUCCESS,[('個人中心','會員中心')]);return True
        state['account_binding']={'stage':'input'};store.put_state(uid,state)
        g.reply_text(token,'綁定帳號\n\n請輸入你的帳號（4～20個英文字母、數字或底線）。\n綁定後仍需回小幫手驗證，才會開通正式使用資格。',buttons);return True
    if text=='確認綁定':
        if not pending or pending.get('stage')!='confirm':
            g.reply_text(token,'請先輸入要綁定的帳號。',[('綁定帳號','綁定帳號')]);return True
        try:name=account_access.bind(uid,pending['name'])
        except ValueError as e:g.reply_text(token,str(e),buttons);return True
        state.pop('account_binding',None);store.put_state(uid,state)
        g.reply_text(token,'帳號：'+name+'\n\n'+account_access.SUCCESS,[('個人中心','會員中心'),('主選單','主選單')]);return True
    if pending or text.startswith('綁定 '):
        value=text.split(maxsplit=1)[1] if text.startswith('綁定 ') else text
        try:name=account_access.validate_username(value)
        except ValueError as e:g.reply_text(token,str(e),buttons);return True
        state['account_binding']={'stage':'confirm','name':name};store.put_state(uid,state)
        g.reply_text(token,'確認綁定帳號：'+name+'\n請確認拼字，綁定後需由小幫手協助更換。',[('確認綁定','確認綁定')]+buttons);return True
    return False
