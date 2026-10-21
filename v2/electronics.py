"""Editorial library for non-monetary game controls and member experiences."""
import base64
import io
import uuid
from datetime import datetime
from PIL import Image, UnidentifiedImageError
from flask import abort, jsonify, render_template, request, Response
import membership
import store
import web_portal as web

KEY = '__electronics_editorial_v1__'
GAMES = {'thor': '雷神', 'seth': '賽特'}


def document():
    return store.get_state(KEY) or {'items': []}


def released(items, kind, game=None):
    now = membership.now_tw()
    return sorted([i for i in items if i['kind'] == kind and i.get('published')
                   and (not game or i['game'] == game)
                   and datetime.fromisoformat(i['release_at']) <= now],
                  key=lambda i: (i['release_at'], i['id']), reverse=True)


def clean(raw):
    kind = raw.get('kind')
    game = raw.get('game')
    if kind not in ('guide', 'feedback') or game not in GAMES:
        raise ValueError('請選擇內容類型與遊戲。')
    title = str(raw.get('title', '')).strip()
    body = str(raw.get('body', '')).strip()
    if not 1 <= len(title) <= 80 or len(body) > 20000:
        raise ValueError('標題需1～80字，內文最多20,000字。')
    release = datetime.fromisoformat(raw.get('release_at', ''))
    if release.tzinfo is None:
        release = release.replace(tzinfo=membership.TZ_TW)
    images = raw.get('images', [])
    if not isinstance(images, list) or len(images) > 8:
        raise ValueError('每篇最多8張圖片。')
    for image in images:
        if not isinstance(image, str) or not image.startswith('/api/electronics/images/'):
            raise ValueError('請使用專區上傳的圖片。')
        asset = image.rsplit('/', 1)[-1]
        if len(asset) != 32 or not all(c in '0123456789abcdef' for c in asset):
            raise ValueError('圖片格式錯誤。')
        if not store.get_state('electronics:image:' + asset):
            raise ValueError('圖片已不存在，請重新上傳。')
    return dict(kind=kind, game=game, title=title, body=body, images=images,
                release_at=release.isoformat(), consent=raw.get('consent') is True)


def install(g):
    app = g.app

    def admin():
        data = web.identity()
        if data['uid'] not in g.ADMIN_USER_IDS:
            abort(403)
        if request.method != 'GET':
            web.csrf(data)
        return data

    @app.get('/electronics')
    def electronics_page():
        return render_template('electronics.html')

    @app.get('/api/electronics')
    def electronics_index():
        items = document()['items']
        guides = {}
        for game in GAMES:
            rows = released(items, 'guide', game)[:2]
            guides[game] = [{k: i[k] for k in ('id', 'title', 'release_at')} for i in rows]
        feedback = released(items, 'feedback')[:100]
        return jsonify(guides=guides, feedback=feedback)

    @app.get('/api/electronics/guides/<item_id>')
    def electronics_guide(item_id):
        web.identity()
        items = document()['items']
        for game in GAMES:
            for item in released(items, 'guide', game)[:2]:
                if item['id'] == item_id:
                    return jsonify(item)
        abort(404)

    @app.route('/api/admin/electronics', methods=['GET', 'POST'])
    def electronics_admin():
        admin()
        if request.method == 'GET':
            return jsonify(document())
        raw = request.get_json(silent=True) or {}
        if not isinstance(raw, dict):
            return jsonify(error='請提供內容物件。'), 400
        with g.user_lock(KEY):
            doc = document()
            item = next((i for i in doc['items'] if i['id'] == raw.get('id')), None)
            action = raw.get('action')
            if action == 'save':
                try:
                    data = clean(raw)
                except (ValueError, TypeError):
                    return jsonify(error='請檢查標題、日期與圖片；每篇最多8張圖、內文最多20,000字。'), 400
                if item and item.get('published'):
                    return jsonify(error='已發布版本不可直接覆寫，請建立新版或先下架。'), 409
                if raw.get('id') and not item:
                    abort(404)
                if item:
                    item.update(data)
                else:
                    item = dict(data, id=uuid.uuid4().hex, published=False)
                    doc['items'].append(item)
            elif action in ('publish', 'hide'):
                if not item:
                    abort(404)
                if action == 'publish':
                    if not item['body'] and not item['images']:
                        return jsonify(error='請先提供內文或圖片，空白內容不能發布。'), 400
                    if item['kind'] == 'feedback' and not item.get('consent'):
                        return jsonify(error='請先確認公開同意並遮蔽個資。'), 400
                item['published'] = action == 'publish'
            else:
                return jsonify(error='不支援的操作。'), 400
            store.put_state(KEY, doc)
        return jsonify(item)

    @app.post('/api/admin/electronics/images')
    def electronics_upload():
        admin()
        file = request.files.get('image')
        if not file:
            return jsonify(error='請選擇圖片。'), 400
        raw = file.read(3 * 1024 * 1024 + 1)
        if len(raw) > 3 * 1024 * 1024:
            return jsonify(error='圖片上限3MB。'), 413
        try:
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in ('PNG', 'JPEG', 'WEBP') or source.width * source.height > 16000000:
                    raise ValueError()
                source.load()
                source.thumbnail((2400, 4000))
                output = io.BytesIO()
                source.convert('RGB').save(output, format='JPEG', quality=88)
        except (UnidentifiedImageError, ValueError, OSError, Image.DecompressionBombError):
            return jsonify(error='請上傳有效的 JPG、PNG 或 WebP，最多1600萬像素。'), 400
        asset = uuid.uuid4().hex
        store.put_state('electronics:image:' + asset, {'data': base64.b64encode(output.getvalue()).decode()})
        return jsonify(url='/api/electronics/images/' + asset)

    @app.get('/api/electronics/images/<asset>')
    def electronics_image(asset):
        url = '/api/electronics/images/' + asset
        items = document()['items']
        visible = released(items, 'feedback')[:100]
        for game in GAMES:
            visible += released(items, 'guide', game)[:2]
        public = any(url in i['images'] for i in visible if i['kind'] == 'feedback')
        if not public:
            data = web.identity()
            if data['uid'] not in g.ADMIN_USER_IDS and not any(url in i['images'] for i in visible):
                abort(404)
        image = store.get_state('electronics:image:' + asset)
        if not image:
            abort(404)
        return Response(base64.b64decode(image['data']), mimetype='image/jpeg')

    @app.after_request
    def electronics_headers(response):
        if request.path == '/electronics':
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Referrer-Policy'] = 'no-referrer'
            response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response
