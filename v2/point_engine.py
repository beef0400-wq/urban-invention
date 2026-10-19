"""Expose existing point rules without changing their calculations.

Settings are drafted separately from road import/edit state and committed together.
The historical Tianmen rules are not available: never invent a replacement.
"""
import membership
import store
import account_access
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
        g.reply_text(token,summary(user),menu_buttons(user))
        return True
    if text == '天門公式':
        clear_draft(uid)
        g.reply_text(token,'百家實戰｜天門公式\n\n原版完整規則尚未補齊，目前未啟用。\n需要原版點數序列、各關轉換、和局處理與停止條件。\n不會用其他方案代替，也不影響目前的四種打法。',menu_buttons(user))
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
        clear_draft(uid)
        g.reply_text(token,'百家實戰｜點數設定完成\n\n'+summary(user).split('\n\n',1)[1],menu_buttons(user))
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
