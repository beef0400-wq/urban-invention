# AI理性陪跑 V2.1 Test Candidate

沿用三份來源核心，沒有部署或覆蓋正式服務。

## 隔離測試分支（2026-10-07）
來源：beef0400-wq/urban-invention，分支 v2-rational-companion-test-20261007。
V2 放在 v2/，原有根目錄程式與正式 main 保持不變。
Render Build: pip install -r v2/requirements.txt
Render Start: cd v2 && python deployment_preflight.py && gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120
既有測試服務需改接此倉庫／分支；部署前必須備份測試 DB，依 ROLLBACK.md 演練 migration。
v2/.github/workflows/ 僅為排程與測試範本，不會被 GitHub 自動執行；正式啟用前需另行設定根目錄 workflow 與測試專用 secret，不能宣稱排程已運行。

## 使用
單一 LINE /webhook。主選單：百家 AI、539 AI、Bingo AI、我的紀錄、使用教學、會員中心。
百家：傳清楚的完整珠盤路截圖，核對後按確認開始。或直接貼紅藍序列／BPT，支援修正 3 藍、刪除 3、追加 紅藍和；手動可連點後完成匯入。進入分析後每局一次紅／藍／和。可隨時切換主選單或模式。
截圖僅 synthetic 珠盤測試通過；大路長龍／和局覆蓋／多區歧義會拒絕自動辨識，真實平台截圖尚待校準。
539：沿用既有演算法，增加逐號依據；每日20:00前鎖定，星期日不產生新鎖盤；開獎後只對同日期，未事前鎖定不回填。公開驗證／驗證7／驗證30／驗證90可查看含失敗結果的紀錄。
Bingo：即時盤顯示20/50/100期。僅來源已驗證且最新期時間在15分鐘內才分析；舊無來源 DB 資料排除，資料异常不產號。

## Runtime
Python 3.12; pip install -r requirements.txt
gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120
同一使用者單程序序列處理；目前只允許1個worker／1個instance。重送event ID去重。故障發生在資料寫入後、event完成記錄前的極窄區間仍需進一步交易化；不能宣稱跨程序 exactly-once。

必要環境：DATABASE_URL（測試 Postgres）、CHANNEL_ACCESS_TOKEN、CHANNEL_SECRET、CRON_SECRET、ADMIN_SECRET（不可用預設密碼）、ADMIN_USER_IDS。
沒有 DATABASE_URL 時 SQLite 僅作本機測試；Render 必須配置 Postgres，避免磁碟重啟遺失。

## Automation
.github/workflows/verification.yml 每日台灣18:00鎖定／21:00對帳；需 repository variable TEST_BASE_URL 與 secret V2_TEST_CRON_SECRET，必須只指測試站。部署與secret設定後才算自動驗證已啟用。
本測試版 /cron/daily-push 僅鎖定，不對舊 production 會員發推播。正式推播接軌需 production 切換時處理。

## Tests
python -m pytest -q
真實 LINE image download/reply、Render/Postgres migration、來源解析、mobile smoke 尚未驗收。
