"""Progress and recoverable road editing. No model algorithm changes."""
import membership,store,verification
from copy import deepcopy
from legacy import baccarat as ba
SNAPSHOT_KEYS=('current_road','tie_count','high_count','low_count','banker_pair_count','player_pair_count',
 'analysis_active','imported_ready','pending_flow','pending_main_result','last_prediction','last_treasure_round',
 'round_win','round_loss','win_streak','loss_streak','max_win_streak','max_loss_streak')

def snapshot(user):return deepcopy({k:user.get(k) for k in SNAPSHOT_KEYS})

def home_progress(uid):
    user=ba.get_user(uid) or {};state=store.get_state(uid)
    road=user.get('current_road') or state.get('road') or []
    desk=f'進行中 · {len(road)}局，可按繼續本桌' if user.get('analysis_active') else '尚未開始，傳路單即可開始'
    if state.get('pending'):desk+=' · 有待確認的匯入'
    target=membership.now_tw().date().isoformat()
    with store.cursor() as c:
        c.execute('SELECT actual FROM v2_public_539 WHERE target_date=%s',(target,));row=c.fetchone()
        c.execute('SELECT created_at,payload FROM v2_records WHERE user_id=%s AND mode=%s ORDER BY created_at DESC LIMIT 1',(uid,'bingo'));b=c.fetchone()
    today='已鎖定 · 已對帳' if row and row[0] else '已鎖定 · 待開獎／對帳' if row else '今天尚無事前鎖定分析'
    bingo='尚未讀取，點即時盤更新'
    if b:
        import json
        lines=json.loads(b[1]).get('text','').splitlines()
        bingo=next((x for x in lines if x.startswith('最新一期')), '上次讀取異常，請重新更新')+'\n這是上次讀取狀態，非背景即時更新。'
    return f'\n\n目前進度\n百家：{desk}\n539：{today}\n賓果：{bingo}'

def align_road(old,new):
    """Only accept a full prefix or a unique long suffix-prefix overlap."""
    if len(new)>=len(old) and new[:len(old)]==old:return list(new),len(new)-len(old)
    matches=[k for k in range(12,min(len(old),len(new))+1) if old[-k:]==new[:k]]
    if len(matches)!=1:return None,None
    k=matches[0];return list(old)+list(new[k:]),len(new)-k

def stage_choices(uid,seq,source,confidence=None):
    user=ba.get_user(uid) or {};old=list(user.get('current_road') or [])
    if not user.get('analysis_active') or not old:return None
    merged,added=align_road(old,seq)
    state=store.get_state(uid)
    state['pending']={'sequence':list(seq),'source':source,'confidence':confidence,'kind':'choice',
      'base_road':old,'merged':merged,'added':added}
    store.put_state(uid,state)
    note=f'可對齊目前牌路，預計新增 {added} 局。' if merged is not None else '無法唯一對齊目前牌路；不會自動合併。可換新桌，或取消後重新截完整牌路。'
    readable=' '.join(f'{i+1}:{ {"莊":"紅","閒":"藍","和":"和"}[x] }' for i,x in enumerate(seq))
    confidence_note=f'共 {len(seq)} 局｜紅 {seq.count("莊")}／藍 {seq.count("閒")}／和 {seq.count("和")}\n' if confidence is not None else ''
    return '百家 AI｜核對本桌更新\n\n'+confidence_note+note+'\n\n新匯入牌路\n'+readable+'\n\n請核對新截圖／牌路，再選更新本桌或換新桌。'

def choice_buttons(uid):
    p=store.get_state(uid).get('pending') or {}
    items=[]
    if p.get('merged') is not None:items.append(('更新本桌','更新本桌'))
    return items+[('換新桌','換新桌'),('取消更新','取消更新'),('主選單','主選單')]

def apply_road(uid,seq,kind):
    user=ba.get_user(uid);state=store.get_state(uid)
    state['undo']=snapshot(user)
    updated=ba.update_user(uid,current_road=list(seq),tie_count=seq.count('和'),analysis_active=True,imported_ready=True,pending_flow=None,pending_main_result=None)
    a=ba.analyze_v15(updated);ba.update_user(uid,last_prediction=a['direction'])
    state.pop('pending',None);state['road']=list(seq);store.put_state(uid,state)
    store.record(uid,'baccarat',{'kind':kind,'sequence':list(seq),'analysis':a})
    return ba.decision_card(updated,a)

def undo(uid):
    state=store.get_state(uid);old=state.pop('undo',None)
    if not old:return '百家 AI｜沒有可撤回的更新\n\n尚未回填新局，或上一筆已撤回。'
    user=ba.update_user(uid,**old);state.pop('pending',None);state['road']=user.get('current_road') or [];store.put_state(uid,state)
    store.record(uid,'baccarat',{'kind':'撤回上一筆','sequence':state['road']})
    return '已撤回上一筆更新。\n\n'+ba.decision_card(user,ba.analyze_v15(user))

def clear_live_table(uid):
    """Start a fresh viewing session; keep membership and historical records."""
    ba.ensure_user(uid)
    ba.update_user(uid,current_road=[],analysis_active=False,imported_ready=False,
                   pending_flow=None,pending_main_result=None,last_prediction=None,
                   tie_count=0,high_count=0,low_count=0,banker_pair_count=0,player_pair_count=0,
                   round_win=0,round_loss=0,win_streak=0,loss_streak=0,max_win_streak=0,max_loss_streak=0)
    state=store.get_state(uid)
    for key in ('road','pending','undo'):state.pop(key,None)
    store.put_state(uid,state)
