"""Validate native message JSON with LINE without sending any message."""
import os
from concurrent.futures import ThreadPoolExecutor
import requests
from line_ui import build_messages

CASES=[
 ('🎲 AI 理性陪跑 V2\n\n目前：免費會員\n\n選一個模式直接開始。',[(a,a) for a in ('百家 AI','539 AI','Bingo AI','我的紀錄','使用教學','會員中心')]),
 ('🧠 百家 AI｜即時分析盤 V2\n\n🎯 綜合判讀：觀望\n📶 訊號指數：0/100（弱）\n⚠️ 風險：中\n\n🗳️ 訊號彙整｜五項訊號\n訊號指數是規則分數，不是勝率。',[('🔴紅','莊'),('🔵藍','閒'),('🟢和','和'),('詳細分析','詳細分析'),('結束本桌','結束分析')]),
 ('【539 AI｜今日決策盤 V2】\n\n🎯 今日母盤\n01 02 03 04 05 06 07 08 09 10\n\n⭐ 核心5碼\n01 02 03 04 05\n\n📊 母盤逐號依據\n測試內容\n\n🧩 結構\n測試內容',[('母盤追蹤','母盤追蹤'),('主選單','主選單')]),
 ('Bingo AI｜即時盤\n最新一期｜測試時間\n01 02 03 04 05\n\n近20期｜測試\n熱號 01 02\n\n近50期｜測試\n冷號 03 04\n\n近100期｜測試\n以上為已開獎統計，並非下期機率。',[('20期','20期'),('50期','50期'),('100期','100期'),('主選單','主選單')]),
 ('👤 會員中心\n\n免費會員',[('免費體驗','免費體驗'),('主選單','主選單')]),
 ('我的紀錄｜三模式共用\n尚無個人分析紀錄。',[('主選單','主選單')]),
 ('⚠️ 這張路單我沒有足夠把握自動帶入。\n\n原因：測試內容',[('手動匯入','匯入牌路'),('主選單','主選單')]),
 ('📊 詳細分析 V15\n\n'+ '\n\n'.join('測試段落\n'+('長內容'*100) for _ in range(10)),[('主選單','主選單')]),
]

def main():
    token=os.getenv('CHANNEL_ACCESS_TOKEN') or os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
    if not token:raise RuntimeError('Flex validation requires configured LINE channel')
    headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
    def validate(case):
        messages=build_messages(*case)
        response=requests.post('https://api.line.me/v2/bot/message/validate/reply',headers=headers,json={'messages':messages},timeout=20)
        if response.status_code!=200:
            # No token, private message, or complete payload is logged.
            details=response.json().get('details',[])
            raise RuntimeError('LINE Flex validation HTTP '+str(response.status_code)+' '+str(details))
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(validate,CASES))
    print('V2_FLEX_PREFLIGHT PASS: 8 message types validated by LINE; no messages sent',flush=True)

if __name__=='__main__':main()
