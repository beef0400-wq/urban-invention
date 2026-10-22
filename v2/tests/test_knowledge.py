"""Public content can be shared without exposing any member data or executing commands."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flask import Flask
import pytest
import knowledge


@pytest.fixture()
def client():
    app=Flask(__name__,template_folder=str(Path(__file__).resolve().parents[1]/'templates'))
    knowledge.install(app)
    return app.test_client()


def test_public_pages_render_without_identity_and_keep_csp(client):
    paths=['/discover','/learn']+['/guide/'+x for x in knowledge.MODES]+['/learn/'+x for x in knowledge.ARTICLES]
    for path in paths:
        response=client.get(path)
        assert response.status_code==200,path
        assert '<html lang="zh-Hant">' in response.text
        assert 'Content-Security-Policy' in response.headers
        assert 'Set-Cookie' not in response.headers
        assert 'suying_session' not in response.text
    assert '600' in client.get('/discover').text


def test_search_matches_article_body_and_category_and_escapes_input(client):
    page=client.get('/learn',query_string={'q':'4MB','category':'百家實戰'}).text
    assert '截圖怎麼傳' in page and '近20、50、100期，是歷史樣本數' not in page
    assert '還沒有符合的文章' in client.get('/learn?q=totally_missing_term').text
    page=client.get('/learn',query_string={'q':'<script>alert(1)</script>'}).text
    assert '<script>alert(1)</script>' not in page
    assert '&lt;script&gt;' in page


def test_invalid_content_paths_are_not_fallback_articles(client):
    assert client.get('/guide/unknown').status_code==404
    assert client.get('/learn/unknown').status_code==404
    assert client.post('/learn').status_code==405


def test_mode_guides_use_real_operation_routes_and_reading_boundaries(client):
    for mode in knowledge.MODES:
        page=client.get('/guide/'+mode).text
        assert '/#'+mode in page
        assert '實際操作介面' in page
        assert '示範帳號' in page
        assert knowledge.MODES[mode]['boundary'] in page
