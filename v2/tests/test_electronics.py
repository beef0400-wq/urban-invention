import io
from datetime import timedelta
from PIL import Image
from test_web_portal import clean, login, g, web, membership, store


def save(c, h, **fields):
    raw = dict(action='save', kind='guide', game='thor', title='操作說明', body='介面操作',
               release_at=(membership.now_tw()-timedelta(days=1)).isoformat(), images=[])
    raw.update(fields)
    return c.post('/api/admin/electronics', base_url=web.ORIGIN, headers=h, json=raw)


def publish(c, h, item):
    return c.post('/api/admin/electronics', base_url=web.ORIGIN, headers=h,
                  json={'action':'publish', 'id':item['id']})


def test_admin_csrf_and_empty_state():
    with g.app.test_client() as c:
        assert c.get('/electronics').status_code == 200
        assert c.get('/api/electronics').json == {'guides':{'thor':[], 'seth':[]}, 'feedback':[]}
        assert save(c, {}).status_code == 401
        h = login(c)
        assert save(c, h).status_code == 403
        g.ADMIN_USER_IDS = {'U_web'}
        assert save(c, {}).status_code == 403
        item = save(c, h, body='').json
        assert publish(c, h, item).status_code == 400


def test_only_two_released_versions_and_future_hidden():
    with g.app.test_client() as c:
        h = login(c); g.ADMIN_USER_IDS = {'U_web'}
        versions = []
        for days in (5, 4, 3, -2):
            i = save(c,h,release_at=(membership.now_tw()-timedelta(days=days)).isoformat()).json
            assert publish(c,h,i).status_code == 200
            versions.append(i)
        rows = c.get('/api/electronics').json['guides']['thor']
        assert [r['id'] for r in rows] == [versions[2]['id'],versions[1]['id']]
        assert all('body' not in r for r in rows)
        assert c.get('/api/electronics/guides/'+versions[0]['id'],base_url=web.ORIGIN).status_code == 404
        assert c.get('/api/electronics/guides/'+versions[3]['id'],base_url=web.ORIGIN).status_code == 404
        assert c.get('/api/electronics/guides/'+versions[2]['id'],base_url=web.ORIGIN).status_code == 200
        assert save(c,h,id=versions[2]['id']).status_code == 409
        assert save(c,h,release_at='invalid').status_code == 400
    with g.app.test_client() as anon:
        assert anon.get('/api/electronics/guides/'+versions[2]['id']).status_code == 401


def test_feedback_consent_upload_and_private_draft():
    with g.app.test_client() as c:
        h = login(c);g.ADMIN_USER_IDS = {'U_web'}
        assert c.post('/api/admin/electronics/images',base_url=web.ORIGIN,headers=h,
                      data={'image':(io.BytesIO(b'<svg/>'),'image.png')}).status_code == 400
        data=io.BytesIO();Image.new('RGB',(12,12)).save(data,format='PNG');data.seek(0)
        r=c.post('/api/admin/electronics/images',base_url=web.ORIGIN,headers=h,
                 data={'image':(data,'image.png')})
        assert r.status_code == 200
        url=r.json['url']
        item=save(c,h,kind='feedback',images=[url]).json
        assert publish(c,h,item).status_code == 400
        with g.app.test_client() as anon:
            assert anon.get(url).status_code == 401
        item=save(c,h,id=item['id'],kind='feedback',images=[url],consent=True).json
        assert publish(c,h,item).status_code == 200
        with g.app.test_client() as anon:
            assert anon.get(url).status_code == 200
            assert len(anon.get('/api/electronics').json['feedback']) == 1
        c.post('/api/admin/electronics',base_url=web.ORIGIN,headers=h,json={'action':'hide','id':item['id']})
        with g.app.test_client() as anon:
            assert anon.get(url).status_code == 401


def test_line_target_and_no_open_redirect():
    with g.app.test_client() as c:
        link=web.issue_link('U_electronics','/electronics#guides')
        assert c.get(link,base_url=web.ORIGIN).headers['Location'] == '/electronics#guides'
        link=web.issue_link('U_electronics','https://example.com')
        assert c.get(link,base_url=web.ORIGIN).headers['Location'] == '/'


def test_line_menu_has_exact_two_entries(monkeypatch):
    calls=[]
    monkeypatch.setattr(g,'reply_text',lambda *a: calls.append(a))
    assert g._handle_global_text({},'電子專區','U_electronics','token')
    assert [v[0] for v in calls[0][2]] == ['領取打法專區','反饋專區']
