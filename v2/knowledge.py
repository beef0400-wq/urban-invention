"""Public product documentation grounded in the current portal's actual controls."""
from flask import abort, render_template, request

UPDATED = '2026-10-22'
MODES = {
    'baccarat': dict(title='百家實戰', label='路單整理與接續記錄', color='red',
        intro='把目前路單帶進來，先核對，再接著記。每局只要按紅、藍或和，分析就會隨紀錄更新。',
        image='baccarat.jpg', image_alt='甦贏百家實戰的路單上傳與手動輸入介面',
        inputs='完整珠盤路截圖，或依順序輸入的紅、藍、和紀錄。',
        outputs='路單結構、觀察訊號與詳細分析；可撤回、補漏或修正本桌。',
        boundary='目前以路單結果作整理，沒有逐張牌面的剩餘牌堆資料。訊號分數不能直接當作下一局勝率。',
        steps=[('帶入目前路單','按「選擇路單圖片」上傳；桌機也能在百家頁貼上截圖。圖片要保留完整珠盤，避免遮住圓點。'),
               ('核對後確認','先比對紅、藍、和及順序；辨識不清楚時改用手動輸入。確認前，待核對內容不會直接取代本桌。'),
               ('每局接著記','開始後，每開一局按一次紅、藍或和。需要時按「看本輪分析」或「詳細分析」。'),
               ('按錯就修正','剛按錯用「撤回上一筆」；漏記或中段錯誤用「補漏／修正」。換新桌時重新帶入該桌路單。')],
        faqs=[('截圖看不清楚怎麼辦？','只截珠盤區，保留所有可見圓點；若仍辨識不清，可改用大按鈕手動匯入。手動開始需至少15局紅／藍紀錄。'),
              ('重新開啟網頁會接續舊桌嗎？','每次重新開啟百家操作頁，都從目前路單開始。請重新帶入現場紀錄，再核對確認。'),
              ('分數高就代表下一局一定會出嗎？','分數用來呈現規則訊號，並非經過機率校準的下一局勝率。要連同樣本、反向訊號與資料完整性一起看。')],
        related=['road-input','reading-signals','correcting-records']),
    '539': dict(title='539 好懂看盤', label='適用日期與開獎對照', color='amber',
        intro='先看本次推薦與適用開獎日，再查選號原因。開獎後回到紀錄，對照當時留下的內容。',
        image='539.jpg', image_alt='甦贏539頁面區分實際開獎與本次推薦的介面',
        inputs='系統取得的歷史開獎資料，以及畫面標示的適用開獎日。',
        outputs='推薦5碼、更多選號、選號原因與過去分析紀錄。',
        boundary='歷史頻率是過去樣本的統計。熱門、遺漏或分數排序，都不代表下期必然開出。',
        steps=[('先核對日期','看「本次推薦號碼」的適用開獎日與資料狀態。截止或休市時，畫面可能顯示下期。'),
               ('查看本次內容','按「查看推薦號碼」先看推薦5碼；想多了解，再展開「更多選號」與理由。'),
               ('開獎後做對照','按「看開獎對照」，核對同一期的實際結果。待開獎與未完成對照不等於未命中。'),
               ('查回原始紀錄','從過去分析表現查看當時保留的內容，別把後來更新的推薦拿去對照較早的結果。')],
        faqs=[('為什麼不是今天的日期？','請以畫面上的適用開獎日及狀態說明為準；分析截止或休市時，系統會切換下一個適用日期。'),
              ('收藏號碼會改變推薦嗎？','不會。關注號碼最多收藏10個，僅供自己追蹤，不會改變每日分析。'),
              ('歷史開獎與推薦要看哪一張？','實際開獎卡是已開出的結果；本次推薦卡是該適用日期的參考。核對前先確認日期相同。')],
        related=['539-dates','539-results','reading-history']),
    'bingo': dict(title='賓果看盤', label='更新時間與歷史樣本', color='violet',
        intro='先看推薦5碼與資料時間，再展開選號原因。新一期開出後更新，讓畫面和資料保持同步。',
        image='bingo.jpg', image_alt='甦贏賓果頁面的更新推薦與選號原因按鈕',
        inputs='系統取得的實際開獎紀錄與更新時間。',
        outputs='推薦5碼、選號原因與上期開獎資訊。',
        boundary='統計期數是回看多少筆歷史資料。資料超過15分鐘時，系統會暫停即時分析。',
        steps=[('取得目前內容','按「查看／更新推薦」，先閱讀推薦5碼。'),
               ('確認資料時間','核對開獎期別、資料時間及畫面狀態。資料尚未更新時，先等待新資料。'),
               ('展開選號原因','點「選號原因與上期開獎」，分開看分析依據和已開出的結果。'),
               ('新一期再更新','新一期開出後再次按更新；閱讀畫面上的新期別，避免沿用舊內容。')],
        faqs=[('近20／50／100期代表什麼？','代表向前統計多少筆歷史樣本，不是需要連續操作的期數，也不是未來保證有效的期間。'),
              ('為什麼暫停即時分析？','可能是開獎來源尚未更新或資料已過時。先看狀態與時間；資料恢復後再按更新。'),
              ('連續按更新，內容會一直變嗎？','同一期應以相同的資料時間與期別判讀。新資料尚未出現時，不需要反覆操作。')],
        related=['bingo-window','bingo-freshness','reading-signals']),
}

ARTICLES = {
 'road-input': dict(category='百家實戰', mode='baccarat', title='截圖怎麼傳，才比較容易核對？', summary='完整珠盤、圓點顏色與順序，是帶入路單時最重要的三件事。', minutes=2,
   sections=[('先保留完整珠盤','讓畫面中的紅、藍、和與排列順序清楚可見。裁切可以去掉無關按鈕，但不要切掉邊緣圓點；遮罩、反光與壓縮模糊都可能影響辨識。'),
             ('上傳後先看預覽','辨識完成後，把預覽與原圖逐段比對，尤其留意最後幾局、和局與較淡的圓點。確認後才開始，能減少把錯誤帶到後續分析。'),
             ('看不清楚就改用手動','上傳圖片上限4MB。可改用手動匯入或一次貼上紅、藍、和；手動開始需至少15局紅／藍。順序要與現場一致。')]),
 'reading-signals': dict(category='數據怎麼看', mode='baccarat', title='訊號分數、歷史比例與勝率，有什麼不同？', summary='把三種數字分清楚，才能知道畫面實際告訴你什麼。', minutes=3,
   sections=[('歷史比例：發生過多少次','假設某段20局紀錄有12局紅，這段樣本的紅色比例是60%。它描述這20局，不等於下一局紅色有60%的機率。'),
             ('訊號分數：規則呈現多強','系統把若干規則與路單特徵整理成分數，讓你比較訊號強弱。分數的刻度與機率不同，80分不能直接讀成80%勝率。'),
             ('讀數字也要讀條件','先看樣本範圍、資料時間、支持與反向訊號，再理解結論。資料不足或辨識不完整時，補好紀錄會比反覆刷新更有幫助。')]),
 'correcting-records': dict(category='百家實戰', mode='baccarat', title='按錯、漏記或換桌，分別怎麼處理？', summary='撤回上一筆、補漏修正、重新帶入，各有對應情境。', minutes=2,
   sections=[('剛剛按錯：撤回上一筆','先撤回最新一筆，再輸入正確結果，重新核對目前本桌的尾端紀錄。'),
             ('中段有錯：補漏／修正','使用補漏修正流程，依畫面要求填入位置與內容。先看待確認預覽，再確認更新；不確定位置時，重新上傳完整路單比較清楚。'),
             ('換新桌：帶入該桌紀錄','不同桌的紀錄要分開。進入新桌後重新帶入目前路單，核對後開始；不要把新桌結果接在上一桌後面。')]),
 '539-dates': dict(category='539', mode='539', title='先看適用日期，再看推薦號碼', summary='畫面上的日期決定這份內容對應哪一期。', minutes=2,
   sections=[('推薦日期與閱讀日期可能不同','畫面在分析截止或休市時可能顯示下期推薦。以「適用開獎日」和狀態說明為準，不要只用手機今天的日期判斷。'),
             ('歷史資料截至哪一天？','資料截至日期表示模型讀到的最新歷史範圍；適用開獎日則表示這份推薦對應的期別。這兩個日期有不同用途。'),
             ('對照前再核對一次','開獎後，使用相同適用日期的已留存分析與實際結果比較。較新推薦不能代替較早的原始紀錄。')]),
 '539-results': dict(category='539', mode='539', title='實際開獎與本次推薦，要分開閱讀', summary='一張是結果，一張是事前內容，先核對期別再比較。', minutes=2,
   sections=[('實際開獎：已發生的結果','實際開獎卡呈現已取得的號碼與日期。它是用來核對的結果，不是下一期的推薦。'),
             ('本次推薦：適用期別的參考','推薦卡先顯示核心5碼；其他搭配與選號原因可以再展開。不同範圍的選號，不能混用同一個命中口徑。'),
             ('待對照：結果尚未齊全','尚未開獎或結果未更新時，應保留待對照狀態。等資料齊全後再評估，避免把缺資料算成命中或未命中。')]),
 'reading-history': dict(category='數據怎麼看', mode='539', title='看分析紀錄，先確認這四件事', summary='時間、樣本、計算口徑與完整紀錄，比單一百分比更有用。', minutes=3,
   sections=[('一、內容是否在結果之前留下','先看產生時間與適用期別，確認對照的是當時已留下的分析內容。事後挑出的案例，無法代表事前表現。'),
             ('二、統計包含多少筆','同樣的百分比，在10筆與1000筆樣本中的解讀不同。統計需要同時呈現期間、已完成對照筆數及待對照筆數。'),
             ('三、什麼算命中','推薦5碼命中幾碼、兩碼搭配是否同時出現，是不同問題。比較前先確認使用相同的定義與選號範圍。'),
             ('四、是否保留完整結果','把命中、未命中與待對照一起看，才能理解波動。會員個別回饋可以補充使用體驗，不能代替完整統計。')]),
 'bingo-window': dict(category='賓果', mode='bingo', title='近20、50、100期，是歷史樣本數', summary='短樣本反映較近變化，長樣本提供較長背景。', minutes=2,
   sections=[('期數是回看的範圍','近20期就是往前取20筆已開獎紀錄。它描述統計的資料範圍，不代表未來20期的有效期限。'),
             ('不同範圍可能有不同排序','某號碼近期出現密集，拉長樣本後未必仍排在前面。這是觀察範圍不同，閱讀時要連同期數一起看。'),
             ('熱門與遺漏都需要背景','熱門描述近期出現較多，遺漏描述多久未出現；兩者都屬於歷史特徵，不能直接推成下一期必出。')]),
 'bingo-freshness': dict(category='賓果', mode='bingo', title='為什麼即時分析要先看資料時間？', summary='同一組號碼，對應的期別與更新時間也需要一致。', minutes=2,
   sections=[('先看期別，再看更新狀態','閱讀推薦前先確認畫面的資料時間與期別。新一期剛開出時，來源與分析畫面可能尚未同步。'),
             ('超過15分鐘會暫停','目前系統在資料超過15分鐘時暫停即時分析，避免把過時內容當成目前資料。暫停時先等待更新。'),
             ('資料恢復後重新取得','新一期開出後按「查看／更新推薦」，確認期別及資料時間已更新，再閱讀該份內容。')]),
 'membership': dict(category='開始使用', mode=None, title='綁定帳號、開通與 LINE 通知，一次看懂', summary='從LINE登入、確認帳號，到收到開通結果。', minutes=2,
   sections=[('從LINE取得登入連結','在甦贏LINE送出「開啟甦贏」，點回覆中的入口。登入連結有使用期限；失效時回LINE取得新的連結。'),
             ('輸入自己的帳號','到「個人中心」輸入4～20個英文字母、數字或底線，核對拼字再確認綁定。接著找小幫手驗證開通。'),
             ('開通後查看期限','管理員確認開通後，系統會嘗試發送LINE通知，內含帳號、到期時間及開始使用入口。個人中心也能查看目前資格與期限。'),
             ('續期與未收到通知','有效正式會員續期會從原到期日延長。未收到通知時先查看個人中心，或請小幫手查詢，不需因此重複開通。')]),
}

def install(app):
    common = dict(modes=MODES, articles=ARTICLES, updated=UPDATED)

    @app.get('/discover')
    def discover():
        return render_template('discover.html', **common)

    @app.get('/guide/<mode>')
    def guide(mode):
        if mode not in MODES:
            abort(404)
        return render_template('mode_guide.html', mode=mode, product=MODES[mode], **common)

    @app.get('/learn')
    def learn():
        category=request.args.get('category','全部')
        query=request.args.get('q','').strip()[:100]
        categories=['全部']+list(dict.fromkeys(x['category'] for x in ARTICLES.values()))
        if category not in categories:
            category='全部'
        selected=[(slug,x) for slug,x in ARTICLES.items()
                  if (category=='全部' or x['category']==category)
                  and (not query or query.casefold() in (x['title']+x['summary']+' '.join(a+b for a,b in x['sections'])).casefold())]
        return render_template('learn_index.html', selected=selected, categories=categories,
                               category=category, query=query, **common)

    @app.get('/learn/<slug>')
    def article(slug):
        if slug not in ARTICLES:
            abort(404)
        item=ARTICLES[slug]
        related=[(s,x) for s,x in ARTICLES.items() if s!=slug and x['category']==item['category']][:2]
        return render_template('learn_article.html', slug=slug, item=item, related=related, **common)

    @app.after_request
    def knowledge_headers(response):
        if request.path=='/discover' or request.path.startswith(('/guide/','/learn')):
            response.headers['X-Content-Type-Options']='nosniff'
            response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
            response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response
