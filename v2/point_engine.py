"""Expose existing point rules without changing their calculations.

Settings are drafted separately from road import/edit state and committed together.
Tianmen amounts and transitions follow the owner-supplied five-stage rules.
"""
import membership
import store
import account_access
from uuid import uuid4
from legacy import baccarat as ba

KEY = 'point_setup'
ENTRY = {'點數引擎', '查詢配置', '我的打法'}
CONFIG = {'點數配置', '設定點數'}
MODES = {'打法模式', '以前的打法模式'}
NAVIGATION = {'主選單','回主選單','首頁','開始','選單',
              '百家 AI','539 AI','Bingo AI','使用教學','會員中心','結束分析'}
COMMANDS = ENTRY | CONFIG | MODES | {'天門公式','取消點數設定'}
COMMANDS |= {'點數區間 '+key for key in ba.POINT_CONFIG}
COMMANDS |= {'點數打法 '+mode for mode in ba.PLAY_MODES}
COMMANDS |= {'點數目標 '+target for target in ba.TARGET_PROFIT_MULT}
TIANMEN_PLANS = {
    '豐田': (50, 150, 350, 750, 1550),
    '賓士': (100, 300, 700, 1500, 3100),
    '保時捷': (300, 900, 2100, 4500, 9300),
    '法拉利': (500, 1500, 3500, 7500, 15500),
    '勞斯': (1000, 3000, 7000, 15000, 31000),
}
COMMANDS |= {'天門方案 '+name for name in TIANMEN_PLANS}
COMMANDS |= {'開始天門 '+name for name in TIANMEN_PLANS}
COMMANDS |= {'天門贏','天門輸','天門和','停止天門','撤回天門','天門進度','天門選方案'}
TIANMEN_KEY = 'tianmen_tracker'


def live_reminder(user, analysis):
    state=store.get_state(user['line_user_id'])
    tracker=state.get(TIANMEN_KEY) or {}
    if state.get('point_method')=='tianmen' and tracker:
        if not tracker['active']:
            return '💰 點數引擎｜天門公式・'+tracker['plan']+'\n本輪已停止：'+tracker.get('reason','自行停止')+'\n點數提醒：停止，不再進關。'
        return (f"💰 點數引擎｜天門公式・{tracker['plan']}\n"
                f"目前第 {tracker['stage']+1} 注／5關｜本輪點數：{TIANMEN_PLANS[tracker['plan']][tracker['stage']]:,} 點\n"
                '依上一輪顯示方向比對開獎更新；觀望、和局不進關。不是實際輸贏紀錄。')
    points=ba.calculate_points(user,analysis)
    return ('💰 點數引擎｜實戰提醒\n'
            f"打法：{user.get('play_mode') or '尚未選擇'}｜區間：{ba.POINT_CONFIG.get(user.get('point_range'),{}).get('label','尚未設定')}\n"
            f"本輪參考：{points['text'] if points else '按「點數／打法」設定'}")


def observation_direction(user,analysis):
    idx=analysis.get('signal_index',ba.signal_index_from_analysis(analysis))
    if idx==0 or '暫停' in analysis.get('state','') or (analysis.get('signal','弱')=='弱' and analysis.get('risk','中') in ('中高','高')):
        return None
    return analysis.get('direction')


def advance_live(user,result):
    uid=user['line_user_id'];state=store.get_state(uid)
    tracker=state.get(TIANMEN_KEY)
    if state.get('point_method')!='tianmen' or not tracker or not tracker['active']:
        return
    direction=observation_direction(user,ba.analyze_v15(user))
    if not direction or result=='和':return
    if result==direction:
        tracker.update(stage=0,losses=0)
    else:
        tracker['losses']+=1
        if tracker['losses']>=5:
            tracker.update(active=False,reason='五關方向比對未中，本輪結束')
        else:tracker['stage']+=1
    state[TIANMEN_KEY]=tracker;store.put_state(uid,state)


def live_reply(g,token,uid,notice=''):
    user=ba.ensure_user(uid)
    if user.get('analysis_active'):
        g.reply_text(token,ba.decision_card(user,ba.analyze_v15(user)),g.baccarat_live_buttons())
    else:
        g.reply_text(token,'百家實戰｜點數／打法已套用\n\n'+notice+'\n傳本桌路單，開始後點數會直接顯示在實戰分析卡。',
                     [('傳路單截圖','傳路單截圖'),('手動匯入','匯入牌路'),('點數／打法','點數引擎')])


def tianmen_buttons():
    return [(f'{name}｜{points[0]:,}點起','天門方案 '+name)
            for name,points in TIANMEN_PLANS.items()] + [('回點數引擎','點數引擎')]


def tianmen_card(name=None):
    if name is None:
        return ('百家實戰｜天門公式\n\n原版五關點數表\n'
                '選一個方案，查看天一至天五的點數與五關累計。\n\n'
                '套用後直接在實戰卡顯示點數。\n回填紅／藍／和，比對上一輪方向：中回第1注，未中進下一關，和與觀望保留。\n五關未中或自行停止才結束；不會自動下注。')
    points=TIANMEN_PLANS[name]
    rows='\n'.join(f'{label}：{amount:,} 點' for label,amount in
                   zip(('天一','天二','天三','天四','天五'),points))
    return (f'百家實戰｜天門公式・{name}\n\n原版五關點數表\n{rows}'
            f'\n\n五關累計：{sum(points):,} 點\n這是五關點數加總，不是預期獲利。'
            '\n贏回第1注；輸進下一關；和局原關不動。五關全輸即停止。'
            '\n點數配置不會改變遊戲本身的機率，也不保證結果。')


def handle_tianmen(g,text,uid,token,state):
    tracker=state.get(TIANMEN_KEY)
    if text == '天門選方案':
        g.reply_text(token,tianmen_card(),tianmen_buttons())
        return
    if text.startswith('天門方案 '):
        name=text.split(' ',1)[1]
        g.reply_text(token,tianmen_card(name),[('套用到實戰','開始天門 '+name),('回實戰','繼續本桌'),('其他方案','天門選方案')])
        return
    if text.startswith('開始天門 '):
        name=text.split(' ',1)[1]
        if state.get('point_method')=='tianmen' and tracker and tracker['active'] and tracker['plan']==name:
            live_reply(g,token,uid);return
        tracker={'plan':name,'stage':0,'losses':0,'active':True,'config_id':uuid4().hex}
        state['point_method']='tianmen'
    elif text in {'天門公式','天門進度'}:
        g.reply_text(token,tianmen_card(),tianmen_buttons()+[('回實戰','繼續本桌'),('停止天門提醒','停止天門')])
        return
    elif not tracker:
        g.reply_text(token,tianmen_card(),tianmen_buttons())
        return
    elif text == '停止天門':
        tracker.update(active=False,reason='自行停止')
    else: # Old detached cards must not change the live reminder.
        live_reply(g,token,uid,'已整合到實戰，請使用紅／藍／和與撤回上一筆。');return
    state[TIANMEN_KEY]=tracker
    store.put_state(uid,state)
    live_reply(g,token,uid,'已套用天門公式・'+tracker['plan'])


def clear_draft(uid):
    state = store.get_state(uid)
    if KEY in state:
        state.pop(KEY)
        store.put_state(uid,state)


def menu_buttons(user):
    return [('修改點數設定' if user.get('point_range') else '設定點數','點數配置'),
            ('打法模式','打法模式'),('天門公式','天門公式'),
            ('回本桌分析' if user.get('analysis_active') else '傳路單截圖',
             '繼續本桌' if user.get('analysis_active') else '傳路單截圖'),
            ('主選單','主選單')]


def summary(user):
    pr = user.get('point_range')
    mode = user.get('play_mode')
    target = user.get('target_profit')
    configured = pr in ba.POINT_CONFIG and mode in ba.PLAY_MODES and target in ba.TARGET_PROFIT_MULT
    text = ('百家實戰｜點數引擎\n\n'
            f'點數區間：{ba.POINT_CONFIG.get(pr,{}).get("label","尚未設定")}\n'
            f'打法模式：{mode or "尚未設定"}\n'
            f'目標比例：{target or "尚未設定"}（舊版計算參數，非獲利保證）\n')
    if configured:
        base = ba.get_base_points(user)
        text += f'基礎區間：{base[0]}～{base[1]}點\n'
        if user.get('analysis_active'):
            points = ba.calculate_points(user,ba.analyze_v15(user))
            text += '本輪參考：'+(points['text'] if points else '暫無資料')+'\n'
        else:
            text += '本輪參考：開始本桌後顯示。\n'
    else:
        text += '按「設定點數」，依序選區間、打法與目標比例。\n'
    return text+'\n沿用原版計算與暫停規則。參考點數不是建議下注額；不保證結果。'


def handle(g, text, uid, token):
    if text in NAVIGATION:
        clear_draft(uid)
        return False
    prefixed = text.startswith(('點數區間 ','點數打法 ','點數目標 '))
    possible_choice = text in ba.POINT_RANGE_INPUT_MAP or text in ba.PLAY_MODES or text in ba.TARGET_PROFIT_MULT
    if text not in COMMANDS and not prefixed and not possible_choice:
        return False
    state = store.get_state(uid)
    draft = state.get(KEY) or {}
    plain_choice = bool(draft) and (text in ba.POINT_RANGE_INPUT_MAP or text in ba.PLAY_MODES or text in ba.TARGET_PROFIT_MULT)
    if text not in COMMANDS and not prefixed and not plain_choice:
        return False
    if not membership.has_access(uid):
        clear_draft(uid)
        g.reply_text(token,account_access.access_notice(uid),account_access.trial_buttons(uid)+[('主選單','主選單')])
        return True
    membership.set_mode(uid,'baccarat')
    user = ba.ensure_user(uid)
    if text in ENTRY:
        clear_draft(uid)
        g.reply_text(token,'百家實戰｜點數／打法\n\n'+live_reminder(user,ba.analyze_v15(user))+'\n\n設定完成會直接回實戰，紅／藍／和只需回填一次。',menu_buttons(user))
        return True
    if text.startswith(('天門','開始天門 ','停止天門','撤回天門')):
        clear_draft(uid)
        handle_tianmen(g,text,uid,token,store.get_state(uid))
        return True
    if text == '取消點數設定':
        clear_draft(uid)
        g.reply_text(token,'百家實戰｜已取消點數設定\n\n原有配置與本桌紀錄保留。',menu_buttons(user))
        return True
    if text in MODES:
        clear_draft(uid)
        g.reply_text(token,'百家實戰｜打法模式\n\n舊版四種模式都在：\n保守／標準／積極／極限。\n各模式使用不同的原版點數區間，不代表勝率不同。\n\n選模式後會帶你完成設定；完成前保留舊配置。',
                     [(mode,'點數打法 '+mode) for mode in ba.PLAY_MODES]+[('天門公式','天門公式'),('點數引擎','點數引擎')])
        return True
    if text in CONFIG:
        draft = {'step':'range'}
    elif text.startswith('點數區間 ') or (draft.get('step') == 'range' and text in ba.POINT_RANGE_INPUT_MAP):
        key = text.split(' ',1)[1] if text.startswith('點數區間 ') else ba.POINT_RANGE_INPUT_MAP[text]
        if key not in ba.POINT_CONFIG or draft.get('step') != 'range':
            g.reply_text(token,'百家實戰｜這份點數選單已過期\n\n請重新開啟設定。',[('設定點數','點數配置')]);return True
        draft.update(point_range=key,step='target' if draft.get('play_mode') else 'mode')
    elif text.startswith('點數打法 ') or (draft.get('step') == 'mode' and text in ba.PLAY_MODES):
        mode = text.split(' ',1)[1] if text.startswith('點數打法 ') else text
        if mode not in ba.PLAY_MODES:
            g.reply_text(token,'百家實戰｜請從四種原版打法選擇。',[('打法模式','打法模式')]);return True
        draft = dict(draft, play_mode=mode)
        if draft.get('point_range') not in ba.POINT_CONFIG and user.get('point_range') in ba.POINT_CONFIG:
            draft['point_range'] = user['point_range']
        draft['step'] = 'target' if draft.get('point_range') in ba.POINT_CONFIG else 'range'
    elif text.startswith('點數目標 ') or (draft.get('step') == 'target' and text in ba.TARGET_PROFIT_MULT):
        target = text.split(' ',1)[1] if text.startswith('點數目標 ') else text
        if (draft.get('step') != 'target' or target not in ba.TARGET_PROFIT_MULT or
                draft.get('point_range') not in ba.POINT_CONFIG or draft.get('play_mode') not in ba.PLAY_MODES):
            g.reply_text(token,'百家實戰｜請先完成區間與打法設定。',[('設定點數','點數配置')]);return True
        user = ba.update_user(uid,point_range=draft['point_range'],play_mode=draft['play_mode'],target_profit=target)
        state=store.get_state(uid);state['point_method']='legacy';store.put_state(uid,state)
        clear_draft(uid)
        live_reply(g,token,uid,'已套用'+draft['play_mode']+'打法。')
        return True
    state[KEY] = draft
    store.put_state(uid,state)
    cancel = [('取消設定','取消點數設定')]
    if draft['step'] == 'range':
        g.reply_text(token,'百家實戰｜點數設定 1/3\n\n選擇點數區間。完成三步後才會儲存。',
                     [(v['label'],'點數區間 '+key) for key,v in ba.POINT_CONFIG.items()]+cancel)
    elif draft['step'] == 'mode':
        g.reply_text(token,'百家實戰｜點數設定 2/3\n\n區間：'+ba.POINT_CONFIG[draft['point_range']]['label']+'\n選擇原版打法模式。',
                     [(mode,'點數打法 '+mode) for mode in ba.PLAY_MODES]+cancel)
    else:
        g.reply_text(token,'百家實戰｜點數設定 3/3\n\n區間：'+ba.POINT_CONFIG[draft['point_range']]['label']+'\n打法：'+draft['play_mode']+'\n選擇舊版目標比例參數。\n這是計算倍率設定，不是預測報酬或獲利承諾。',
                     [(target,'點數目標 '+target) for target in ba.TARGET_PROFIT_MULT]+cancel)
    return True
