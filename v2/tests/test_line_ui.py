import json
from line_ui import build_messages
from ui_preflight import CASES

def walk(node):
    if isinstance(node,dict):
        yield node
        for v in node.values():yield from walk(v)
    elif isinstance(node,list):
        for v in node:yield from walk(v)

def test_all_screens_have_native_actions_and_fit_line_limits():
    for text,items in CASES:
        messages=build_messages(text,items)
        assert 1<=len(messages)<=5
        assert all(m['type']=='flex' and len(m['altText'])<=400 for m in messages)
        for m in messages:
            assert len(json.dumps(m,ensure_ascii=False).encode())<50000
            for n in walk(m):
                if n.get('type')=='bubble':assert len(json.dumps(n,ensure_ascii=False).encode())<30000
                if n.get('type')=='text':assert n['wrap'] is True and n.get('maxLines') is None
        actions=[n for n in walk(messages) if n.get('type') in ('message','uri')]
        assert set(b for _,b in items)<=set(n.get('text') or n.get('uri') for n in actions)

def test_numeric_chip_content_and_long_report_are_preserved():
    nums='01 02 03 04 05 06 07 08 09 10'
    messages=build_messages('【539 AI】\n\n母盤\n'+nums)
    texts=[n['text'] for n in walk(messages) if n.get('type')=='text']
    assert all(n in texts for n in nums.split())
    paragraphs=['段落'+str(i)+'：'+('資料'*170) for i in range(15)]
    messages=build_messages('公開驗證\n\n'+'\n\n'.join(paragraphs))
    texts=[n['text'] for n in walk(messages) if n.get('type')=='text']
    assert all(p in texts for p in paragraphs)

def test_round_buttons_keep_internal_commands_and_show_public_names():
    messages=build_messages(*CASES[1]);buttons=[n for n in walk(messages) if n.get('type')=='button']
    assert [n['action']['text'] for n in buttons[:3]]==['莊','閒','和']
    assert [n['action']['label'] for n in buttons[:3]]==['🔴紅','🔵藍','🟢和']

def test_home_is_one_wide_card_and_labels_wrap():
    from app import main_menu_items
    messages=build_messages('🎲 甦贏\n\n目前：免費會員',main_menu_items())
    assert len(messages)==1 and messages[0]['contents']['type']=='bubble'
    assert messages[0]['contents']['size']=='mega'
    assert 'quickReply' not in messages[0]
    tiles=[n for n in walk(messages) if n.get('type')=='box' and n.get('action',{}).get('type')=='message']
    assert set(n['action']['text'] for n in tiles)==set(b for a,b in main_menu_items())
    tile=next(n for n in tiles if n['action']['text']=='539 AI')
    assert tile['contents'][0]['text']=='539 好懂看盤' and tile['contents'][0]['wrap']
