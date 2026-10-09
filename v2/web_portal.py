"""Same-service mobile portal. Identity is issued only by the signed LINE gateway."""
import base64, hashlib, secrets, re, json
from datetime import timedelta, datetime
from urllib.parse import urlparse
from contextvars import ContextVar
import cv2, numpy as np
from flask import request, abort, jsonify, render_template, redirect, make_response
import membership, store, line_ui, experience, v2_flows
from legacy import baccarat as ba

CAPTURE = ContextVar('web_reply_capture', default=None)
ORIGIN = 'https://ai-rational-companion-v1-test.onrender.com'
COOKIE = 'suying_session'
CAMPAIGNS = '__suying_campaigns__'
DRAFTS = '__suying_campaign_drafts__'
SETTINGS = '__suying_home_settings__'
COMMANDS = {'主選單','百家 AI','539 AI','Bingo AI','今日陪跑','今日追蹤','驗證7','驗證30','驗證90','即時盤','20期','50期','100期','會員中心','免費體驗','我的紀錄','使用教學','繼續本桌','詳細分析','撤回上一筆','修正本桌','確認修正','取消更新','更新本桌','換新桌','結束分析','匯入牌路','匯入莊','匯入閒','匯入和','撤回匯入','清空匯入','確認開始','完成匯入','修正牌路','莊','閒','和','紅','藍','綁定帳號','查看待確認牌路','開始新桌'}

def hashed(token): return hashlib.sha256(token.encode()).hexdigest()
def session_key(token): return 'web:session:'+hashed(token)
def issue_link(uid):
    token = secrets.token_urlsafe(32)
    store.put_state('web:login:'+hashed(token), {'uid':uid,'expires':(membership.now_tw()+timedelta(minutes=10)).isoformat()})
    return ORIGIN+'/enter?token='+token

def identity():
    token=request.cookies.get(COOKIE,'')
    data=store.get_state(session_key(token)) if token else {}
    if not data or datetime.fromisoformat(data['expires']) <= membership.now_tw(): abort(401)
    return data

def csrf(data):
    if not secrets.compare_digest(request.headers.get('X-CSRF-Token',''),data['csrf']): abort(403)

def clean_campaign(raw):
    kind=raw.get('kind','')
    if kind not in ('month','week'): raise ValueError('請選擇月活動或週活動。')
    title=str(raw.get('title','')).strip()
    if not title or len(title)>60: raise ValueError('活動名稱請填1至60字。')
    content=str(raw.get('content','')).strip()
    if len(content)>3000: raise ValueError('活動內容最多3000字。')
    start=datetime.fromisoformat(raw.get('start','')).replace(tzinfo=membership.TZ_TW)
    end=datetime.fromisoformat(raw.get('end','')).replace(tzinfo=membership.TZ_TW)
    if end<=start: raise ValueError('結束時間必須晚於開始時間。')
    target=raw.get('target','member')
    if target not in ('member','baccarat','539','bingo','register'): raise ValueError('請選擇有效活動入口。')
    return dict(kind=kind,title=title,content=content,start=start.isoformat(),end=end.isoformat(),target=target)

def active_campaigns():
    items=store.get_state(CAMPAIGNS)
    now=membership.now_tw()
    return [{k:v for k,v in item.items() if k!='image'} for item in items.values() if item.get('published') and datetime.fromisoformat(item['start'])<=now<datetime.fromisoformat(item['end'])]

def install(g):
    app=g.app
    app.config['MAX_CONTENT_LENGTH']=5*1024*1024

    @app.get('/enter')
    def enter():
        token=request.args.get('token','')
        if not re.fullmatch(r'[A-Za-z0-9_-]{40,60}',token): return render_template('enter_error.html'),400
        with g.user_lock('__web_login__'):
            key='web:login:'+hashed(token);data=store.get_state(key)
            if not data or datetime.fromisoformat(data['expires'])<=membership.now_tw():return render_template('enter_error.html'),401
            store.put_state(key,{})
            session=secrets.token_urlsafe(32)
            store.put_state(session_key(session),{'uid':data['uid'],'csrf':secrets.token_urlsafe(32),'expires':(membership.now_tw()+timedelta(hours=8)).isoformat()})
        response=make_response(redirect('/'))
        response.set_cookie(COOKIE,session,max_age=28800,httponly=True,secure=True,samesite='Lax')
        response.headers['Cache-Control']='no-store';response.headers['Referrer-Policy']='no-referrer'
        return response

    @app.get('/api/portal')
    def portal():
        data=identity();uid=data['uid'];membership.ensure_user(uid)
        user=ba.get_user(uid) or {};state=store.get_state(uid)
        return jsonify(csrf=data['csrf'],member=membership.status_text(uid),access=membership.has_access(uid),admin=uid in g.ADMIN_USER_IDS,
                       road=[{'莊':'紅','閒':'藍','和':'和'}.get(x,x) for x in user.get('current_road',[])],active=bool(user.get('analysis_active')),
                       favorites=state.get('favorites_539',[]),bingo_featured=bool(store.get_state(SETTINGS).get('bingo_featured')),pending=bool(state.get('pending')),campaigns=active_campaigns(),register='https://AI001.aaawin88.com',line='https://line.me/R/ti/p/@957ridwt')

    @app.get('/api/539/overview')
    def lotto_overview():
        from legacy import lotto539 as engine
        import verification
        today = membership.now_tw().date()
        draws = engine.load_539_draws(10)
        previous = next(((d, n) for d, n in draws if d < today), None)
        latest = draws[0] if draws else None
        data = dict(target_date=today.isoformat(), previous=None, latest=None, prediction=None,
                    status='登入會員／試用後查看' if today.weekday()!=6 else '今日休市')
        def draw_json(row):
            return dict(date=row[0].isoformat(), numbers=sorted(row[1])) if row else None
        data['previous'] = draw_json(previous)
        data['latest'] = draw_json(latest)
        token = request.cookies.get(COOKIE, '')
        session = store.get_state(session_key(token)) if token else {}
        if session and datetime.fromisoformat(session['expires']) > membership.now_tw() and membership.has_access(session['uid']):
            pack = verification.locked_pack(today)
            data['status'] = '本期分析尚未鎖定' if today.weekday()!=6 else '今日休市'
            if pack:
                model = json.loads(pack['note'])
                data['prediction'] = {key: engine.parse_nums_text(model.get(key,'')) for key in ('motherboard','core5','stable2','attack3','burst4')}
                data['status'] = '開獎前已鎖定 · 待開獎' if not latest or latest[0] < today else '本期已開獎 · 分析保留不改號'
        response = jsonify(data)
        response.headers['Cache-Control'] = 'private, no-store'
        return response

    @app.get('/api/activities')
    def activities(): return jsonify(items=active_campaigns(),bingo_featured=bool(store.get_state(SETTINGS).get('bingo_featured')))

    @app.get('/activities/image/<kind>/<image_id>')
    def activity_image(kind,image_id):
        item=store.get_state(CAMPAIGNS).get(kind,{})
        draft=store.get_state(DRAFTS).get(kind,{})
        if draft.get('image_id')==image_id:item=draft
        # Draft preview only to an authenticated admin. No draft leakage.
        if item.get('image_id')!=image_id or not item.get('image'):abort(404)
        active=item.get('published') and datetime.fromisoformat(item['start'])<=membership.now_tw()<datetime.fromisoformat(item['end'])
        if not active and identity()['uid'] not in g.ADMIN_USER_IDS:abort(403)
        response=make_response(base64.b64decode(item['image']));response.mimetype='image/jpeg'
        response.headers['Cache-Control']='private, no-store';return response

    def result(uid,action):
        captured=[];handle=CAPTURE.set(captured)
        try: action()
        finally: CAPTURE.reset(handle)
        return {'replies':[{'text':line_ui.public_text(text),'buttons':[{'label':line_ui.public_text(a),'command':b} for a,b in (buttons or []) if b in COMMANDS]} for text,buttons in captured]}

    @app.post('/api/command')
    def command():
        data=identity();csrf(data);uid=data['uid'];raw=request.get_json(silent=True) or {};cmd=str(raw.get('command','')).strip()
        if cmd not in COMMANDS and not re.fullmatch(r'(?:牌路 [紅藍和\s]{1,600}|追加 [紅藍和\s]{1,600}|修正 \d{1,3} [紅藍和]|刪除 \d{1,3}|綁定 [A-Za-z0-9_-]{1,40})',cmd):abort(400)
        rid=str(raw.get('request_id',''))
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,80}',rid):abort(400)
        with g.user_lock(uid):
            key='web:request:'+hashed(request.cookies[COOKIE]+rid);cached=store.get_state(key)
            if cached:return jsonify(cached)
            mode=raw.get('mode')
            if cmd.startswith('綁定 '):membership.set_mode(uid,'baccarat')
            elif mode in ('baccarat','539','bingo'):membership.set_mode(uid,mode)
            if membership.get_mode(uid)=='baccarat':ba.ensure_user(uid)
            if cmd=='開始新桌':
                experience.clear_live_table(uid)
                out={'replies':[{'text':'百家實戰｜傳目前路單，核對後開始。','buttons':[]}]}
                store.put_state(key,out)
                return jsonify(out)
            if cmd=='查看待確認牌路':
                p=store.get_state(uid).get('pending')
                if not p:return jsonify(replies=[{'text':'目前没有待確認牌路。','buttons':[]}])
                buttons=experience.choice_buttons(uid) if p.get('kind')=='choice' else [('確認修正','確認修正'),('取消更新','取消更新')] if p.get('kind')=='edit' else v2_flows.CONFIRM_BUTTONS
                return jsonify(replies=[{'text':'請核對牌路\n'+v2_flows.preview(p['sequence']),'buttons':[{'label':line_ui.public_text(a),'command':b} for a,b in buttons]}])
            out=result(uid,lambda:g.process_event({'type':'message','source':{'userId':uid},'replyToken':'web','message':{'type':'text','text':cmd}}))
            store.put_state(key,out)
        return jsonify(out)

    @app.post('/api/road-image')
    def road_image():
        data=identity();csrf(data);uid=data['uid']
        if not membership.has_access(uid):abort(403)
        upload=request.files.get('image')
        if not upload:abort(400)
        image=upload.read(4*1024*1024+1)
        if len(image)>4*1024*1024:abort(413)
        parsed=g.parse_baccarat_road_image(image,min_main_results=ba.MIN_ROAD_LEN)
        with g.user_lock(uid):
            membership.set_mode(uid,'baccarat')
            if not parsed.accepted:
                return jsonify(replies=[{'text':f'這張路單還不能可靠辨識。\n辨識信心：{round(parsed.confidence*100)}%\n原因：{parsed.note}\n請重傳完整珠盤路，或改用手動輸入。','buttons':[]}])
            choice=experience.stage_choices(uid,parsed.sequence,'image',parsed.confidence)
            text=choice or v2_flows.pending(uid,parsed.sequence,'image',parsed.confidence)
            buttons=experience.choice_buttons(uid) if choice else v2_flows.CONFIRM_BUTTONS
            return jsonify(replies=[{'text':line_ui.public_text(text),'buttons':[{'label':line_ui.public_text(a),'command':b} for a,b in buttons]}])

    @app.route('/api/admin/activities',methods=['GET','POST'])
    def admin_activities():
        data=identity()
        if data['uid'] not in g.ADMIN_USER_IDS:abort(403)
        if request.method=='GET':
            items=store.get_state(CAMPAIGNS);items.update(store.get_state(DRAFTS))
            return jsonify(items=[{k:v for k,v in x.items() if k!='image'} for x in items.values()])
        csrf(data)
        raw=request.form if request.form else request.get_json(silent=True) or {}
        if raw.get('action')=='season':
            value=raw.get('bingo_featured')
            if not isinstance(value,bool):abort(400)
            store.put_state(SETTINGS,{'bingo_featured':value})
            return jsonify(ok=True)
        with g.user_lock('__campaigns__'):
            items=store.get_state(CAMPAIGNS);drafts=store.get_state(DRAFTS);kind=raw.get('kind','');action=raw.get('action','save')
            if action in ('publish','hide'):
                if action=='publish':
                    if kind not in drafts:abort(404)
                    if not drafts[kind].get('image'):return jsonify(error='請先上傳活動圖片。'),400
                    items[kind]=drafts.pop(kind);items[kind]['published']=True
                    store.put_state(DRAFTS,drafts)
                else:
                    if kind not in items:abort(404)
                    items[kind]['published']=False
                store.put_state(CAMPAIGNS,items);return jsonify(ok=True)
            try:item=clean_campaign(raw)
            except (ValueError,TypeError):return jsonify(error='請確認活動名稱、開始與結束時間。'),400
            old=drafts.get(kind) or items.get(kind,{})
            item.update(published=False,image=old.get('image',''),image_id=old.get('image_id',''))
            upload=request.files.get('image')
            if upload and upload.filename:
                image=upload.read(3*1024*1024+1)
                if len(image)>3*1024*1024:return jsonify(error='活動圖片請小於3MB。'),400
                # Re-encode raster images: no SVG/script, metadata, or uploaded path serving.
                decoded=cv2.imdecode(np.frombuffer(image,np.uint8),cv2.IMREAD_COLOR)
                if decoded is None:return jsonify(error='請上傳JPG、PNG或WebP圖片。'),400
                height,width=decoded.shape[:2]
                if height*width>24000000:return jsonify(error='圖片尺寸過大。'),400
                if width>1600:decoded=cv2.resize(decoded,(1600,round(height*1600/width)))
                ok,encoded=cv2.imencode('.jpg',decoded,[cv2.IMWRITE_JPEG_QUALITY,88])
                if not ok:abort(400)
                item['image']=base64.b64encode(encoded.tobytes()).decode();item['image_id']=secrets.token_hex(12)
            if not item.get('image'):return jsonify(error='請上傳活動圖片。'),400
            item['image_url']=f'/activities/image/{kind}/{item["image_id"]}'
            drafts[kind]=item;store.put_state(DRAFTS,drafts)
            return jsonify(ok=True,item={k:v for k,v in item.items() if k!='image'})

    @app.post('/api/favorites')
    def favorites():
        data=identity();csrf(data);nums=(request.get_json(silent=True) or {}).get('numbers')
        if not isinstance(nums,list) or len(nums)>10 or any(type(n) is not int or not 1<=n<=39 for n in nums):abort(400)
        with g.user_lock(data['uid']):
            state=store.get_state(data['uid']);state['favorites_539']=sorted(set(nums));store.put_state(data['uid'],state)
        return jsonify(ok=True,numbers=state['favorites_539'])

    @app.post('/api/logout')
    def logout():
        data=identity();csrf(data);store.put_state(session_key(request.cookies[COOKIE]),{})
        response=jsonify(ok=True);response.delete_cookie(COOKIE,secure=True,httponly=True,samesite='Lax');return response

    @app.after_request
    def portal_headers(response):
        if request.path.startswith(('/api/','/enter')) or request.path=='/':
            response.headers['Cache-Control']='no-store';response.headers['Referrer-Policy']='no-referrer'
            response.headers['X-Content-Type-Options']='nosniff'
            response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response
