# V2 Test rollback

正式 urban-invention 未變更，目前不需要正式回滾。

測試服務部署前：
1. 固定 GitHub HEAD、Render 最新 live deploy ID；保留上一版部署。
2. 確認 DATABASE_URL 是 ai-rational-companion-v1-test-db，絕不能使用 production DB。
3. 使用 pg_dump -Fc 備份完整測試 DB；儲存 table/column baseline（目前 users/analysis_logs）。
4. 紀錄快照路徑與 SHA256。備份成功才能測試 migration。

新增資料表為 v2_state、v2_records、v2_public_539、v2_events、v2_bingo_provenance；既有 users 與 analysis_logs 資料不得删除。平台會員資料表與 539/Bingo 既有兼容表由沿用 init_db 建立。初始化前完整快照涵蓋這些表與欄位的還原。

回滾優先：先停止測試寫入、將測試服務回到前一個 live deploy，保留新增資料表（向後相容）。如果確實需要撤銷 DB migration，先再次導出所有 V2 資料，再在新建的隔離 DB 還原「部署前」完整 pg_dump；將測試服務 DATABASE_URL 指向已核對的還原 DB。不要直接清除舊會員或歷史紀錄。

001_v2_down.sql 只供確認五個 V2 表都是新建、且資料已導出時使用；不能當作完整 DB 還原。既有資料庫含同名 V2 表時不適用。

正式切換前須另做兩個 production DB 的只讀快照合併與逐表對帳，不能把測試 DB 當正式來源。目前尚未執行合併或切換。
