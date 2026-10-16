import v2_flows as flow

def test_image_preview_keeps_visible_count_and_explicit_scope():
    seq=['莊','閒']*20+['和']*5
    text=flow.pending_text(seq,'image')
    assert '本次讀取共 45 局' in text
    assert '尚未自動核對' in text and '分析僅依已讀取資料' in text
    assert '51' not in text
    buttons=flow.pending_buttons(seq,'image')
    assert ('使用這 45 局繼續','確認開始') in buttons
    assert ('重新上傳','傳路單截圖') in buttons
    assert ('換房後重傳','換房後重傳') in buttons

def test_manual_preview_does_not_claim_image_history():
    assert '部分歷史提醒' not in flow.pending_text(['莊']*15,'manual')
    assert flow.pending_buttons(['莊']*15,'manual')==flow.CONFIRM_BUTTONS

def test_change_room_discards_preview_without_erasing_live_road(monkeypatch):
    state={'pending':{'sequence':['莊']*15},'road':['閒']*20}
    monkeypatch.setattr(flow.store,'get_state',lambda uid:state)
    monkeypatch.setattr(flow.store,'put_state',lambda uid,value:None)
    monkeypatch.setattr(flow.membership,'set_mode',lambda *a:None)
    replies=[]
    class Gateway:
        def reply_text(self,*args):replies.append(args)
    assert flow.handle(Gateway(),{},'換房後重傳','user','token')
    assert 'pending' not in state and state['road']==['閒']*20
    assert '不會替你切換' in replies[0][1]
