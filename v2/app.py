import os
import json
import hmac
import base64
import hashlib
import requests
from flask import Flask, request, abort, render_template

import membership
import store
import verification
import v2_flows
import line_ui
import experience
import admin_experience, account_access
import web_portal
import sys
import threading
from contextlib import contextmanager
from legacy import lotto539
from legacy import baccarat
from road_vision import parse_baccarat_road_image

app = Flask(__name__)
APP_VERSION = "SUYING-V2.7.1-ADMIN-TEST"
_USER_LOCKS = {}
_LOCK_GUARD = threading.Lock()

@contextmanager
def user_lock(uid):
    with _LOCK_GUARD:
        lock = _USER_LOCKS.setdefault(uid, threading.RLock())
    with lock: yield
CHANNEL_ACCESS_TOKEN = (os.getenv("CHANNEL_ACCESS_TOKEN") or os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or "").strip()
CHANNEL_SECRET = (os.getenv("CHANNEL_SECRET") or os.getenv("LINE_CHANNEL_SECRET") or "").strip()
CRON_SECRET = os.getenv("CRON_SECRET", "").strip()
ADMIN_USER_IDS = {x.strip() for x in (os.getenv("ADMIN_USER_IDS", "") + "," + os.getenv("OWNER_ADMIN_USER_ID", "")).split(",") if x.strip()}
LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply"
LINE_CONTENT_API = "https://api-data.line.me/v2/bot/message"

BINGO_COMMANDS = {
    "賓果分析", "1期", "5期", "10期", "賓果1期分析", "賓果5期分析", "賓果10期分析",
    "預測分析", "取消預測分析"
}


def verify_signature(raw_body, signature):
    if not CHANNEL_SECRET:
        return False
    digest = hmac.new(CHANNEL_SECRET.encode("utf-8"), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(signature or "", expected)


def reply_text(reply_token, text, quick_items=None):
    captured = web_portal.CAPTURE.get()
    if captured is not None:
        captured.append((text, quick_items))
        return
    if not reply_token or not CHANNEL_ACCESS_TOKEN:
        return
    messages = line_ui.build_messages(text, quick_items)
    response = requests.post(
        LINE_REPLY_API,
        headers={"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}", "Content-Type": "application/json"},
        json={"replyToken": reply_token, "messages": messages},
        timeout=8,
    )
    response.raise_for_status()


def fetch_line_image(message_id):
    if not message_id or not CHANNEL_ACCESS_TOKEN:
        return None
    r = requests.get(
        f"{LINE_CONTENT_API}/{message_id}/content",
        headers={"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"},
        timeout=15,
    )
    if r.status_code != 200:
        return None
    return r.content

def baccarat_live_buttons():
    return [("🔴紅", "莊"), ("🔵藍", "閒"), ("🟢和", "和"), ("詳細分析", "詳細分析"), ("撤回上一筆", "撤回上一筆"), ("補漏／修正", "修正本桌"), ("主選單", "主選單"), ("結束本桌", "結束分析")]

def _road_preview(seq, limit=36):
    mapping = {"莊": "🔴", "閒": "🔵", "和": "🟢"}
    tail = seq[-limit:]
    return "".join(mapping.get(x, x) for x in tail)

def handle_baccarat_image(event, user_id, reply_token):
    if not membership.has_access(user_id):
        reply_text(reply_token, "這是會員／體驗功能。先開啟免費體驗即可使用百家路單截圖辨識。", [("免費體驗", "免費體驗"), ("會員中心", "會員中心")])
        return
    message_id = event.get("message", {}).get("id")
    image_bytes = fetch_line_image(message_id)
    if not image_bytes:
        reply_text(reply_token, "圖片下載失敗，請重新傳一次完整路單截圖。", mode_menu("baccarat"))
        return
    if len(image_bytes)>12*1024*1024:
        reply_text(reply_token,"圖片過大，請裁切路單區後再傳。",mode_menu("baccarat")); return
    parsed = parse_baccarat_road_image(image_bytes, min_main_results=baccarat.MIN_ROAD_LEN)
    if not parsed.accepted:
        reply_text(
            reply_token,
            "⚠️ 這張路單我沒有足夠把握自動帶入。\n\n"
            f"辨識信心：{round(parsed.confidence*100)}%\n"
            f"辨識主路：{sum(1 for x in parsed.sequence if x in ('莊','閒'))} 把\n"
            f"原因：{parsed.note}\n\n"
            "請重新截『完整路單區』，或用文字一次貼上：\n牌路 紅藍紅紅藍…",
            [("手動匯入", "匯入牌路"), ("主選單", "主選單")],
        )
        return
    choice=experience.stage_choices(user_id,parsed.sequence,'image',parsed.confidence)
    reply_text(reply_token, choice or v2_flows.pending(user_id, parsed.sequence, 'image', parsed.confidence), experience.choice_buttons(user_id) if choice else v2_flows.CONFIRM_BUTTONS)


def main_menu_items():
    return [
        ("開啟甦贏", "開啟甦贏"),
        ("百家實戰", "百家 AI"),
        ("539 好懂看盤", "539 AI"),
        ("賓果看盤", "Bingo AI"),
        ("我的紀錄", "我的紀錄"),
        ("使用教學", "使用教學"),
        ("會員中心", "會員中心"),
    ]


def mode_menu(mode):
    if mode == "baccarat":
        return [
            ("傳路單截圖", "傳路單截圖"), ("手動匯入", "匯入牌路"),
            ("詳細分析", "詳細分析"), ("結束本桌", "結束分析"),
            ("539 AI", "539 AI"), ("Bingo AI", "Bingo AI"),
        ]
    if mode == "bingo":
        return [
            ("即時盤", "即時盤"), ("20期", "20期"), ("50期", "50期"), ("100期", "100期"),
            ("539 AI", "539 AI"), ("百家 AI", "百家 AI"),
        ]
    return [
        ("今日分析", "今日陪跑"), ("今日追蹤", "今日追蹤"), ("母盤追蹤", "母盤追蹤"),
        ("Bingo AI", "Bingo AI"), ("百家 AI", "百家 AI"),
        ("會員中心", "會員中心"), ("主選單", "主選單"),
    ]


def welcome_text(user_id):
    return (
        "🎲 甦贏\n\n"
        "一個會員，同時使用：\n"
        "① 百家實戰｜路單截圖匯入＋即時多訊號分析\n"
        "② 539 好懂看盤｜每日模型＋母盤＋開獎後驗證\n"
        "③ 賓果看盤｜真實資料即時分析\n\n"
        f"目前：{membership.status_text(user_id)}\n\n"
        "選一個模式直接開始。"
    )


def patch_legacy_access():
    # 539 uses the unified membership service as its source of truth.
    lotto539.get_expiry = membership.get_expiry
    lotto539.is_member = membership.has_access
    lotto539.has_used_free_trial = membership.has_used_trial
    lotto539.start_free_trial = membership.start_trial
    lotto539.set_expiry_plus_days = membership.grant_days

    # Newly created legacy rows must not silently start a separate 3-hour trial.
    old_default = baccarat.default_user
    def default_without_trial(uid):
        user = old_default(uid)
        user.update(trial_started_at=None, trial_end_at=None)
        return user
    baccarat.default_user = default_without_trial

    # Baccarat state remains in its own users table, while access is unified.
    baccarat.is_vip = lambda user: bool(user and membership.is_paid(user.get("line_user_id")))
    baccarat.in_trial = lambda user: bool(user and membership.is_trial(user.get("line_user_id")))
    baccarat.has_full_access = lambda user: bool(user and membership.has_access(user.get("line_user_id")))
    baccarat.check_trial_transition = lambda user: (user, False)
    baccarat.get_status_text = lambda user: membership.status_text(user.get("line_user_id")) if user else "查無會員資料"

    # Requests reaching these internal Flask apps are already signature-verified by the gateway.
    lotto539.verify_line_signature = lambda raw, sig: True
    baccarat.verify_signature = lambda req: True


patch_legacy_access()


def _forward_to_legacy(engine, event, replacement_text=None):
    cloned = json.loads(json.dumps(event, ensure_ascii=False))
    uid=cloned.get('source',{}).get('userId')
    if replacement_text is not None: cloned['message']['text']=replacement_text
    text=cloned.get('message',{}).get('text','')
    if not membership.has_access(uid) and not (text in {'綁定帳號','/myid','我的ID','/adminhelp','/待開通','找管理員','申請加入會員'} or text.startswith(('綁定 ','遊戲帳號 ','確認 ','待確認'))):
        reply_text(cloned.get('replyToken'),'請先開啟免費體驗或會員。',[('免費體驗','免費體驗'),('主選單','主選單')]);return
    payload=json.dumps({'events':[cloned]},ensure_ascii=False).encode()
    if engine=='baccarat':
        before=baccarat.get_user(uid)
        before_snapshot=experience.snapshot(before) if before else None
        # Restore persisted road for local-only development mode.
        state=store.get_state(uid)
        if not baccarat.use_db() and uid not in baccarat.MEMORY_USERS and state.get('road'):
            baccarat.ensure_user(uid); baccarat.update_user(uid,current_road=state['road'],analysis_active=True)
        with baccarat.app.test_client() as client:
            resp=client.post('/callback',data=payload,content_type='application/json',headers={'X-Line-Signature':'internal'})
        user=baccarat.get_user(uid)
        if user:
            state=store.get_state(uid)
            if text=='結束分析':state.pop('undo',None);state.pop('pending',None)
            elif before_snapshot and before_snapshot['current_road']!=user.get('current_road'):
                state['undo']=before_snapshot
            state['road']=user.get('current_road',[]);store.put_state(uid,state)
            store.record(uid,"baccarat",{"kind":text,"sequence":user.get("current_road",[]),"analysis":baccarat.analyze_v15(user)})
    else:
        with lotto539.app.test_client() as client:
            resp=client.post('/webhook',data=payload,content_type='application/json',headers={'X-Line-Signature':'internal'})
    if resp.status_code>=400: raise RuntimeError('Legacy handler failed')


def legacy_ba_reply(token,text,quick_items=None):
    items=list(quick_items or [])
    for item in [('主選單','主選單'),('539 AI','539 AI'),('Bingo AI','Bingo AI')]:
        if item not in items: items.append(item)
    reply_text(token,text,items)

baccarat.reply_text=legacy_ba_reply
lotto539.reply_message=lambda token,text: reply_text(token,text,main_menu_items())



def _handle_global_text(event, text, user_id, reply_token):
    normalized = text.replace("　", " ").strip()

    if normalized in {"開啟甦贏", "甦贏", "手機主頁"}:
        link=web_portal.issue_link(user_id)
        reply_text(reply_token,"甦贏｜手機主頁\n\n從LINE或網頁查看歷史資料與個人紀錄。甦贏帳號自動建立，無須另外註冊。\n此連結10分鐘內有效，請勿轉傳。",[("進入甦贏",link),("主選單","主選單")])
        return True

    if normalized in {"開始", "主選單", "回主選單", "首頁", "選單"}:
        baccarat.ensure_user(user_id)
        baccarat.update_user(user_id, pending_flow=None, pending_main_result=None)
        reply_text(reply_token, welcome_text(user_id), main_menu_items())
        return True

    if normalized in {"539 AI", "539", "今彩539"}:
        membership.set_mode(user_id, "539")
        reply_text(
            reply_token,
            "已進入【539 AI】。\n\n以歷史開獎資料、統計結構與模型訊號作為決策輔助；未開獎結果仍屬未知。",
            mode_menu("539"),
        )
        return True

    if normalized in {"百家 AI", "百家AI", "百家", "百家樂 AI", "百家樂AI"}:
        membership.set_mode(user_id, "baccarat")
        baccarat.ensure_user(user_id)
        baccarat.update_user(user_id, pending_flow=None, pending_main_result=None)
        reply_text(
            reply_token,
            "🔴🔵 百家 AI｜快速開始\n\n"
            "最省事：直接把你目前那桌的『路單截圖』傳上來。\n"
            "系統辨識後先核對預覽與信心，按確認開始就立即分析。\n\n"
            "之後每開一局，只按一次【🔴紅／🔵藍／🟢和】即可重算。\n"
            "如果圖片辨識失敗，也可一次貼：牌路 紅藍紅紅藍…",
            mode_menu("baccarat"),
        )
        return True

    if normalized in {"Bingo AI", "Bingo", "賓果 AI", "賓果AI", "賓果"}:
        membership.set_mode(user_id, "bingo")
        reply_text(
            reply_token,
            "🟣 Bingo AI\n\n使用真實開獎資料做短線／節奏／結構分析。資料抓取失敗時不會產生模擬開獎。",
            mode_menu("bingo"),
        )
        return True

    if normalized in {"會員中心", "查詢資格", "我的到期日"}:
        reply_text(reply_token, "個人中心\n\n甦贏帳號：" + account_access.ensure(user_id) + "\n" + membership.status_text(user_id), [
            ("免費體驗", "免費體驗"), ("539 AI", "539 AI"), ("百家 AI", "百家 AI"), ("主選單", "主選單")
        ] + ([("管理會員", "管理會員")] if user_id in ADMIN_USER_IDS else []))
        return True

    if normalized in {"免費體驗", "免費試用", "試用一天", "免費使用1天", "免費使用一天"}:
        exp, status = membership.start_trial(user_id, 24)
        if status == "opened":
            reply_text(reply_token, "✅ 免費體驗已開通\n\n百家 AI＋539 AI＋Bingo AI 同時可使用。\n到期：" + exp.strftime("%Y-%m-%d %H:%M"), main_menu_items())
        elif status == "already_member":
            reply_text(reply_token, "你目前已有完整使用權限。\n\n" + membership.status_text(user_id), main_menu_items())
        else:
            reply_text(reply_token, "此 LINE 帳號已使用過免費體驗。\n\n" + membership.status_text(user_id), main_menu_items())
        return True

    if normalized == "使用教學":
        mode = membership.get_mode(user_id)
        if mode == "baccarat":
            reply_text(reply_token, "百家 AI：\n1. 進桌後截完整路單\n2. 直接把截圖傳給 LINE\n3. 確認辨識預覽\n4. 之後每局只按一次紅／藍／和\n5. 想看模型細節再按詳細分析", mode_menu(mode))
        elif mode == "bingo":
            reply_text(reply_token, "Bingo AI：選即時盤查看近20／50／100期真實資料統計。抓不到真實資料時系統不會造資料。", mode_menu(mode))
        else:
            reply_text(reply_token, "539 AI：查看今日模型、母盤與2／3／4星；開獎後再看母盤追蹤驗證。", mode_menu(mode))
        return True

    if normalized == "傳路單截圖":
        membership.set_mode(user_id, "baccarat")
        reply_text(reply_token, "直接把目前桌面的完整路單截圖傳到這裡即可。\n\n建議：路單區要完整、不要裁掉左右兩側；如果有多個路單區，盡量讓主路／珠盤路清楚。", mode_menu("baccarat"))
        return True

    if False and normalized == "今日 AI 分析":
        membership.set_mode(user_id, "539")
        _forward_to_legacy("539", event, "今日陪跑")
        return True

    if normalized.startswith(('/vip','/開通')):
        if user_id not in ADMIN_USER_IDS:
            reply_text(reply_token, '此指令僅限管理員。');return True
        reply_text(reply_token,'請使用「管理會員」，選擇甦贏帳號與期限後確認開通。',[('管理帳號','管理會員')])
        return True
    if normalized=='綁定帳號' or normalized.startswith(('綁定 ','遊戲帳號 ')):
        reply_text(reply_token,'甦贏帳號自動建立，無須綁定外部帳號。\n甦贏帳號：'+account_access.ensure(user_id),[('個人中心','會員中心'),('主選單','主選單')])
        return True

    return False


@app.get("/")
def home():
    return render_template("portal.html")


@app.get("/health")
def health():
    return {"ok": True, "version": APP_VERSION, "verification_scheduler": bool(VERIFICATION_SCHEDULER)}


@app.post("/webhook")
def webhook():
    raw = request.get_data()
    sig = request.headers.get("X-Line-Signature", "")
    if not verify_signature(raw, sig):
        abort(403)

    body = request.get_json(silent=True) or {}
    for event in body.get('events',[]):
        uid=event.get('source',{}).get('userId','')
        if not uid: continue
        with user_lock(uid):
            eid=event.get('webhookEventId') or event.get('message',{}).get('id')
            if eid:
                with store.cursor(True) as c:
                    c.execute('SELECT status FROM v2_events WHERE event_id=%s',(eid,))
                    row=c.fetchone()
                    if row and row[0]=='done': continue
            process_event(event)
            if eid:
                with store.cursor(True) as c:
                    c.execute("INSERT INTO v2_events VALUES (%s,'done',%s) ON CONFLICT(event_id) DO UPDATE SET status='done'",(eid,membership.now_tw().isoformat()))

    return "OK"



def process_event(event):
    user_id = event.get("source", {}).get("userId", "")
    reply_token = event.get("replyToken")
    if not user_id:
        return
    membership.ensure_user(user_id)

    if event.get("type") == "follow":
        reply_text(reply_token, welcome_text(user_id), main_menu_items())
        return

    if event.get("type") != "message":
        return

    message = event.get("message", {})
    message_type = message.get("type")
    mode = membership.get_mode(user_id)

    if message_type == "image":
        if mode == "baccarat":
            handle_baccarat_image(event, user_id, reply_token)
        else:
            reply_text(reply_token, "路單截圖辨識目前用在百家 AI。請先點【百家 AI】再傳圖片。", main_menu_items())
        return

    if message_type != "text":
        reply_text(reply_token, "目前支援文字與百家路單截圖。", main_menu_items())
        return

    text = (message.get("text") or "").strip()
    if admin_experience.handle(sys.modules[__name__],text,user_id,reply_token):
        return
    if v2_flows.handle(sys.modules[__name__], event, text, user_id, reply_token):
        return
    if _handle_global_text(event, text, user_id, reply_token):
        return

    mode = membership.get_mode(user_id)
    _forward_to_legacy("539" if mode in {"539", "bingo"} else "baccarat", event)

def _valid_cron():
    return bool(CRON_SECRET) and hmac.compare_digest(request.args.get("secret", ""), CRON_SECRET)


@app.get('/cron/update-539-result')
def cron_update_539_result():
    if not _valid_cron(): abort(403)
    lotto539.ensure_latest_539_in_db()
    count=verification.reconcile(lotto539.load_539_draws(240))
    return {'ok':True,'verified':count}

@app.get('/cron/daily-push')
def cron_daily_push():
    if not _valid_cron(): abort(403)
    try: pack=lotto539.get_or_build_today_pick_539()
    except ValueError as e: return {'ok':False,'reason':str(e)},409
    return {'ok':True,'locked':True}

@app.get('/cron/check-bingo')
def cron_check_bingo():
    if not _valid_cron(): abort(403)
    return {'ok':bool(lotto539.ensure_latest_bingo_in_db())}


def initialize():
    if os.getenv("RENDER") and not os.getenv("DATABASE_URL"):
        raise RuntimeError("Render test requires persistent Postgres DATABASE_URL")
    store.init_db()
    if os.getenv('DATABASE_URL'):
        lotto539.ensure_db_ready()
    membership.init_db()

initialize()
web_portal.install(sys.modules[__name__])
import scheduled_verification
VERIFICATION_SCHEDULER = scheduled_verification.start()

if __name__ == "__main__":
    membership.init_db()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
