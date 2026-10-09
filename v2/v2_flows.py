import re
from datetime import datetime, timedelta
import account_access
import store, membership, verification, experience
from legacy import baccarat as ba, lotto539 as lo

IMPORT_BUTTONS=[('🔴紅','匯入莊'),('🔵藍','匯入閒'),('🟢和','匯入和'),('撤回','撤回匯入'),('確認開始','確認開始'),('清空','清空匯入'),('主選單','主選單')]
CONFIRM_BUTTONS=[('確認開始','確認開始'),('修正牌路','修正牌路'),('重新匯入','匯入牌路'),('主選單','主選單')]

def parse_batch(text):
    text=re.sub(r'^(?:快速牌路|牌路)\s*[:：]?\s*','',text)
    mapping={'紅':'莊','红':'莊','莊':'莊','庄':'莊','B':'莊','藍':'閒','蓝':'閒','閒':'閒','闲':'閒','P':'閒','和':'和','綠':'和','绿':'和','T':'和'}
    chars=[c.upper() for c in text if not c.isspace() and c not in ',，、|-🔴🔵🟢']
    if not chars or any(c not in mapping for c in chars): return None
    return [mapping[c] for c in chars] if len(chars)<=500 else None

def preview(seq):
    return '\n'.join(' '.join(f'{i+1}:{ {"莊":"紅","閒":"藍","和":"和"}[x] }' for i,x in enumerate(seq[start:start+20],start)) for start in range(0,len(seq),20))

def pending(uid, seq, source, confidence=None):
    state=store.get_state(uid);state['pending']={'sequence':seq,'source':source,'confidence':confidence};store.put_state(uid,state)
    return f'請核對辨識結果｜{len(seq)} 局\n'+(f'辨識信心 {round(confidence*100)}%（非正確率保證）\n' if confidence is not None else '')+preview(seq)+'\n\n正確就按確認開始；修正例：修正 3 藍／刪除 3／追加 紅藍和。'

def activate(uid,seq):
    ba.ensure_user(uid)
    user=ba.update_user(uid,current_road=list(seq),tie_count=seq.count('和'),high_count=0,low_count=0,banker_pair_count=0,player_pair_count=0,imported_ready=True,analysis_active=True,pending_flow=None,pending_main_result=None,last_prediction=None,last_treasure_round=-99,round_win=0,round_loss=0,win_streak=0,loss_streak=0,max_win_streak=0,max_loss_streak=0)
    a=ba.analyze_v15(user);ba.update_user(uid,last_prediction=a['direction'])
    state=store.get_state(uid);state.pop('pending',None);state.pop('undo',None);state['road']=list(seq);store.put_state(uid,state)
    store.record(uid,'baccarat',{'kind':'開始','sequence':seq,'analysis':a})
    return ba.decision_card(user,a)

def bingo_board(window=None):
    if not lo.ensure_latest_bingo_in_db(): return 'Bingo 資料異常：目前抓不到可信真實資料，本次不產生分析。'
    draws=lo.load_bingo_draws(120)
    if not draws: return 'Bingo 資料異常：沒有已驗證來源的資料。'
    latest=draws[0]
    try:
        stamp=datetime.combine(latest['date'],datetime.strptime(latest['time'],'%H:%M').time()).replace(tzinfo=lo.TZ_TW)
        age=(lo.now_tw()-stamp).total_seconds()
        if age<0 or age>900: return 'Bingo 資料異常：最新一期已超過15分鐘或時間錯誤，暫停即時分析。'
    except (ValueError,TypeError): return 'Bingo 資料異常：無法核對開獎時間。'
    lines=['Bingo AI｜即時盤',f'最新一期 {latest["period"]}｜{latest["date"]} {latest["time"]}',lo.fmt_nums(latest['numbers'])]
    for window in ((window,) if window in (20,50,100) else (20,50,100)):
        sample=draws[:window];f=lo.bingo_freq(sample)
        hot=sorted(f,key=lambda n:(-f[n],n))[:5];cold=sorted(f,key=lambda n:(f[n],n))[:5]
        current=sample[:min(10,len(sample))];previous=sample[10:20]
        rise=fall='樣本不足'
        if previous:
            fc,fp=lo.bingo_freq(current),lo.bingo_freq(previous)
            delta={n:fc[n]/len(current)-fp[n]/len(previous) for n in f}
            rise=lo.fmt_nums(sorted((n for n in f if delta[n]>0),key=lambda n:-delta[n])[:5]) or '無'
            fall=lo.fmt_nums(sorted((n for n in f if delta[n]<0),key=lambda n:delta[n])[:5]) or '無'
        allnums=[n for d in sample for n in d['numbers']];total=len(allnums)
        zones=[sum(lo.bingo_zone(n)==z for n in allnums) for z in ('1-20','21-40','41-60','61-80')]
        big=sum(n>40 for n in allnums);odd=sum(n%2 for n in allnums)
        lines += [f'\n近{window}期｜實際{len(sample)}期'+('（不足完整窗口）' if len(sample)<window else ''), '熱號 '+lo.fmt_nums(hot),'冷號 '+lo.fmt_nums(cold),'升溫 '+rise,'降溫 '+fall,'區段 1–20／21–40／41–60／61–80：'+'/'.join(map(str,zones)),f'大 {big/total:.1%}｜小 {1-big/total:.1%}｜單 {odd/total:.1%}｜雙 {1-odd/total:.1%}']
    lines.append('\n怎麼看：熱冷描述已開獎次數；升降溫比較最近兩段各10期，並非所選窗口的整段變化。')
    lines.append('\n以上為已開獎統計，並非下期機率。')
    return '\n'.join(lines)

def handle(g,event,text,uid,token):
    # Global commands always precede pending flows.
    if text in ('我的紀錄','分析紀錄'):
        rows=[r for r in store.history(uid,100) if datetime.fromisoformat(r['at']).astimezone(membership.TZ_TW).date()>=(membership.now_tw()-timedelta(days=4)).date()][:5]
        msg='我的紀錄｜最近5天（最多5筆）\n'+'\n'.join(f'{datetime.fromisoformat(r['at']).astimezone(membership.TZ_TW).strftime('%m/%d %H:%M')}｜{r["mode"]}｜{r["data"].get("kind","分析")}' for r in rows)
        g.reply_text(token,msg if rows else '尚無個人分析紀錄。',g.main_menu_items());return True
    if text in ('公開驗證','母盤追蹤','驗證5','539完整紀錄','驗證7','驗證30','驗證90'):
        g.reply_text(token,verification.report(int(text[2:]) if text.startswith('驗證') else 5,compact=text in ('公開驗證','母盤追蹤','驗證5')),[('看完整紀錄','539完整紀錄'),('返回本期分析','今日陪跑'),('主選單','主選單')]);return True
    if text=='今日追蹤':
        g.reply_text(token,verification.today_report(),[('最近5期紀錄','驗證5'),('主選單','主選單')]);return True
    if text in ('539完整資訊','539逐號依據'):membership.set_mode(uid,'539')
    if text=='繼續本桌':membership.set_mode(uid,'baccarat')
    mode=membership.get_mode(uid)
    is_bingo=text in ('即時盤','Bingo分析','賓果分析','20期','50期','100期','1期','5期','10期','賓果1期分析','賓果5期分析','賓果10期分析')
    batch=parse_batch(text) if mode=='baccarat' else None
    handled=is_bingo or (mode=='539' and text in ('今日陪跑','今日分析','今日 AI 分析','539完整資訊','539逐號依據')) or (mode=='baccarat' and (batch is not None or text in ('匯入牌路','確認開始','完成匯入','撤回匯入','清空匯入','修正牌路','匯入莊','匯入閒','匯入和','繼續本桌','修正本桌','撤回上一筆','更新本桌','換新桌','取消更新','確認修正') or text.startswith(('修正 ','刪除 ','追加 ','牌路','快速牌路'))))
    if not handled:return False
    if not membership.has_access(uid):g.reply_text(token,account_access.access_notice(uid),account_access.trial_buttons(uid)+[('綁定帳號','綁定帳號'),('會員中心','會員中心')]);return True
    if is_bingo:
        membership.set_mode(uid,'bingo');msg=bingo_board(int(text[:-1]) if text in ('20期','50期','100期') else None);store.record(uid,'bingo',{'kind':'即時盤','text':msg});g.reply_text(token,msg,g.mode_menu('bingo'));return True
    if mode=='539':
        view={'539完整資訊':'full','539逐號依據':'basis'}.get(text,'summary')
        msg=lo.format_today_companion(view)
        if view=='summary':store.record(uid,'539',{'kind':'今日分析','text':msg})
        items=[('看完整資訊','539完整資訊'),('母盤逐號依據','539逐號依據'),('最近5期紀錄','驗證5'),('539操作教學','教學539'),('主選單','主選單')] if view=='summary' else [('返回本期分析','今日陪跑'),('主選單','主選單')]
        g.reply_text(token,msg,items);return True
    state=store.get_state(uid);p=state.get('pending');seq=list(p['sequence']) if p else []
    user=ba.get_user(uid) or {}
    if text=='繼續本桌':
        msg=ba.decision_card(user,ba.analyze_v15(user)) if user.get('analysis_active') else '百家 AI｜尚未開始本桌，請先匯入牌路。'
        g.reply_text(token,msg,g.baccarat_live_buttons() if user.get('analysis_active') else g.mode_menu('baccarat'));return True
    if text=='撤回上一筆':g.reply_text(token,experience.undo(uid),g.baccarat_live_buttons());return True
    if text=='取消更新':
        state.pop('pending',None);store.put_state(uid,state);g.reply_text(token,'已取消，本桌牌路保留。',g.baccarat_live_buttons());return True
    if text in ('更新本桌','換新桌','確認修正'):
        if not p:g.reply_text(token,'目前沒有待確認更新。',g.baccarat_live_buttons());return True
        if p.get('base_road') is not None and p['base_road']!=user.get('current_road'):
            state.pop('pending',None);store.put_state(uid,state);g.reply_text(token,'本桌已更新，這份預覽已過期。請重新傳截圖或修正。',g.baccarat_live_buttons());return True
        if text=='更新本桌' and p.get('kind')=='choice' and p.get('merged') is not None:
            if len(p['merged'])>500:g.reply_text(token,'牌路超過500局，請換新桌。',experience.choice_buttons(uid));return True
            msg=experience.apply_road(uid,p['merged'],'截圖更新本桌')
        elif text=='換新桌' and p.get('kind')=='choice':
            if len(ba.main_only(seq))<ba.MIN_ROAD_LEN:g.reply_text(token,'新桌至少需15局紅／藍結果。',experience.choice_buttons(uid));return True
            msg=activate(uid,seq)
        elif text=='確認修正' and p.get('kind')=='edit':
            if len(ba.main_only(seq))<ba.MIN_ROAD_LEN:g.reply_text(token,'修正後至少需15局紅／藍結果。',[('取消更新','取消更新')]);return True
            msg=experience.apply_road(uid,seq,'修正本桌')
        else:g.reply_text(token,'請使用目前預覽上的確認按鈕。',experience.choice_buttons(uid));return True
        g.reply_text(token,msg,g.baccarat_live_buttons());return True
    if text=='修正本桌' or (not p and user.get('analysis_active') and text.startswith(('追加 ','修正 ','刪除 '))):
        state['pending']={'sequence':list(user['current_road']),'source':'edit','kind':'edit','base_road':list(user['current_road'])}
        store.put_state(uid,state);p=state['pending'];seq=list(p['sequence'])
        if text=='修正本桌':
            g.reply_text(token,'百家 AI｜補漏與修正\n\n'+preview(seq)+'\n\n追加 紅藍和：補上漏掉的局\n修正 3 藍：改第3局\n刪除 3：刪第3局\n核對後按確認修正，才會更新本桌。',[('確認修正','確認修正'),('取消更新','取消更新')]);return True
    if p and p.get('kind')=='choice' and text in ('確認開始','完成匯入'):
        g.reply_text(token,'請先選更新本桌或換新桌，不會直接覆蓋本桌。',experience.choice_buttons(uid));return True
    if p and p.get('kind')=='edit' and text in ('確認開始','完成匯入'):
        g.reply_text(token,'本桌修正請按確認修正。',[('確認修正','確認修正'),('取消更新','取消更新')]);return True

    if p and p.get('kind')=='choice' and (text.startswith(('修正 ','刪除 ','追加 ')) or (batch and len(batch)==1)):
        if batch and len(batch)==1:return False
        g.reply_text(token,'請先取消更新，再修正本桌或重新匯入。',experience.choice_buttons(uid));return True
    if text=='匯入牌路' or text=='清空匯入':
        msg=pending(uid,[],'manual');g.reply_text(token,msg,IMPORT_BUTTONS);return True
    if batch is not None and len(batch)>1:
        choice=experience.stage_choices(uid,batch,'batch')
        g.reply_text(token,choice or pending(uid,batch,'batch'),experience.choice_buttons(uid) if choice else CONFIRM_BUTTONS);return True
    if text in ('修正牌路',):
        g.reply_text(token,'輸入：修正 3 藍／刪除 3／追加 紅藍和\n'+preview(seq),CONFIRM_BUTTONS);return True
    if text in ('確認開始','完成匯入'):
        if len(ba.main_only(seq))<ba.MIN_ROAD_LEN:g.reply_text(token,f'目前主路 {len(ba.main_only(seq))} 局，至少需15局；可一次貼上現有牌路。',IMPORT_BUTTONS)
        else:g.reply_text(token,activate(uid,seq),g.baccarat_live_buttons())
        return True
    if not p:
        if batch and len(batch)==1:return False
        g.reply_text(token,'請先匯入牌路或傳截圖。',g.mode_menu('baccarat'));return True
    try:
        if text.startswith('修正 '):
            _,num,value=text.split();idx=int(num)-1;replacement=parse_batch(value)
            if idx<0 or idx>=len(seq) or not replacement or len(replacement)!=1:raise ValueError()
            seq[idx]=replacement[0]
        elif text.startswith('刪除 '):
            idx=int(text.split()[1])-1
            if idx<0 or idx>=len(seq):raise ValueError()
            seq.pop(idx)
        elif text.startswith('追加 '):
            extra=parse_batch(text.split(maxsplit=1)[1])
            if not extra:raise ValueError()
            seq+=extra
        elif text=='撤回匯入':seq=seq[:-1]
        elif text.startswith('匯入'):seq.append({'匯入莊':'莊','匯入閒':'閒','匯入和':'和'}[text])
        elif batch:seq+=batch
        else:raise ValueError()
        if len(seq)>500:raise ValueError()
        if p.get('kind')=='edit':
            p['sequence']=seq;state['pending']=p;store.put_state(uid,state)
            g.reply_text(token,'百家 AI｜修正預覽\n\n'+preview(seq)+'\n\n核對後按確認修正。',[('確認修正','確認修正'),('取消更新','取消更新')])
        else:g.reply_text(token,pending(uid,seq,p['source'],p.get('confidence')),IMPORT_BUTTONS)
    except (ValueError,KeyError,IndexError):g.reply_text(token,'格式不正確；例：修正 3 藍／刪除 3／追加 紅藍和。',CONFIRM_BUTTONS)
    return True
