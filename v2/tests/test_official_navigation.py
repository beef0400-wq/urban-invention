"""Public navigation must not issue identity or change account access."""
import os
os.environ.pop('DATABASE_URL',None)
os.environ['LOCAL_DB_PATH']='/tmp/suying-navigation-test.sqlite3'
import app as g
import line_ui

def test_official_command_has_no_personal_token(monkeypatch):
    replies=[]
    monkeypatch.setattr(g,'reply_text',lambda *args:replies.append(args))
    monkeypatch.setattr(g.web_portal,'issue_link',lambda uid: (_ for _ in ()).throw(AssertionError('public link must not issue a login')))
    assert g._handle_global_text({},'甦贏官網','U_navigation','capture')
    assert ('開啟甦贏官網',g.OFFICIAL_SITE_URL) in replies[0][2]
    menu=line_ui.build_messages('🎲 甦贏\n\n目前：測試',g.main_menu_items())
    import json
    assert g.OFFICIAL_SITE_URL in json.dumps(menu)

def test_portal_outbound_link_does_not_expose_session():
    with g.app.test_client() as client:
        page=client.get('/').get_data(as_text=True)
        assert g.OFFICIAL_SITE_URL in page
        assert 'rel="noopener noreferrer"' in page
        assert '甦贏官網' in page
        assert client.get('/api/portal').status_code==401
