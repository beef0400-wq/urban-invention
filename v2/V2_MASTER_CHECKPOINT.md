# AI理性陪跑 V2 MASTER CHECKPOINT

## CURRENT PHASE
V2.1 本機 Test Candidate；未部署，不是手機真人測試 READY。

## DONE
- 完整讀取三份 ZIP 的程式與 P0 變更，沿用百家 V15、539、Bingo 核心。
- 百家珠盤截圖辨識候選 → 預覽 → 確認開始；單格修正／刪除／追加／重新匯入。
- 批次紅藍和／BPT、快速連點後一次完成；每局單次輸入立即重算。
- 多訊號分析、支持／反向訊號、規則指數不宣稱勝率；對子牌值選填。
- 539 原演算法不變；今日母盤、核心5碼、Top3、逐號評分與2/3/4星輸出。
- 539 開獎前鎖定、hash、不可覆寫、同日期對帳；7/30/90期含0命中公開驗證；不回填事後預測。
- Bingo 20/50/100期盤、熱冷／升降溫／區段／大小單雙；模擬fallback完全停用。
- 無真實來源、過期最新資料、無 provenance 舊 DB 不用於新分析。
- 共用会员與三模式紀錄；修正試用誤判為正式會員與新百家帳號另開試用問題。
- 全域導航、每使用者單程序鎖、重送event去重、簽章與會員驗證。
- 新增 storage SQL migration、回滾文件、測試用排程workflow。
- 26項本機測試通過；百家100組牌路與539一般/回補核心回歸一致。
- 只讀確認既有 Render test / test DB users與analysis_logs schema；未寫入任何遠端DB。

## DOING
- 2026-10-07：改接 urban-invention 的隔離測試分支 v2-rational-companion-test-20261007。
- 已核對兩個正式倉庫 app.py 與原 ZIP 完全一致（除尾端空行）。
- 測試分支基底 commit：6dafef5ca66f4b33843c23a9c5279bb8b7806e68。
- 已重新安裝依賴；2026-10-07 重跑 26 passed in 0.42s、compile 通過。推送 v2/ 目錄，不修改原有根目錄程式。

## BLOCKED
- 已解除原有倉庫權限問題；使用者指示忽略空 ai-rational-companion-v 倉庫。
- Render 既有測試服務仍連接空倉庫；目前連接工具沒有修改 service repo/branch 的操作。若改用瀏覽器設定，需使用者同意此工具切換。
- 真實百家平台路單尚未提供；大路龍尾／和局覆蓋／多區歧義保守拒絕，不能宣稱完成跨平台辨識。

## NEXT
1. 完成隔離分支 v2/ 推送，保留正式根目錄與 main 不變。
2. 將既有 Render test 接到此分支，Build: pip install -r v2/requirements.txt；Start: cd v2 && gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120。
3. 備份測試DB，migration、Postgres會員／資料／rollback驗證。
4. Render部署、來源實抓、LINE圖像／reply／簽章、手機Smoke／Regression。
5. 設定排程所需測試URL與secret，確認18:00鎖盤與21:00對帳實際運行。
6. 用至少3～5張真實珠盤截圖校準。
7. 提供真正測試站READY報告；正式切換需本人確認且先做兩個production DB快照合併對帳。

## FILES CHANGED
app.py / membership.py / road_vision.py / legacy/baccarat.py / legacy/lotto539.py
store.py / verification.py / v2_flows.py / tests/test_v2.py / tests/reference/*
migrations/001_v2_up.sql / migrations/001_v2_down.sql / ROLLBACK.md
README.md / render.yaml / .github/workflows/tests.yml / .github/workflows/verification.yml

## TEST / DEPLOY STATUS
Local: 26 passed；compile通過。
Real screenshots: NOT TESTED。
Remote DB migration / rollback rehearsal: NOT RUN。
Real 539/Bingo fetch: NOT VERIFIED。
GitHub push: 本 checkpoint 隨 V2 測試候選版提交至隔離分支；commit 以 GitHub HEAD 為準。
Render V2 deploy: NOT RUN。
LINE OA / mobile smoke: NOT RUN。
Schedule activation: NOT RUN。
Existing test URL: https://ai-rational-companion-v1-test.onrender.com（尚未更新為本版）。
Production urban-invention、百家服務與兩個正式DB：未修改。
