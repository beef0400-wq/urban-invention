# V2 Test rollback

正式 urban-invention 未變更，目前不需要正式回滾。

測試服務部署前：
1. 固定 GitHub HEAD、Render 最新 live deploy ID；保留上一版部署。
2. 確認 DATABASE_URL 是 ai-rational-companion-v1-test-db，絕不能使用 production DB。
3. 使用 pg_dump -Fc 備份完整測試 DB；儲存 table/column baseline（目前 users/analysis_logs）。
4. 紀錄快照路徑與 SHA256。備份成功才能測試 migration。

2026-10-07 實測：既有 test DB 僅 users、analysis_logs，兩表均 0 筆。由只讀 connector 取得完整欄位／default／NOT NULL／PRIMARY KEY／索引／sequence 定義，保存 deployment/test_db_baseline.json 與 restore_empty_test_baseline.sql 至隔離 GitHub 分支。這是空資料庫 schema 快照，不是 pg_dump，不能用於有資料的正式庫。
deployment_preflight.py 在任何 legacy initializer 匯入前檢查固定測試 DB host/name；首輪如既有表已新增資料會直接拒絕部署。於臨時 schema 演練 001 up → 寫入 sentinel → down → 整體 transaction rollback，不刪除任何既有 public 表。
回到旧版部署時先恢復舊 source/branch/build/start，或保留同一測試分支改為前一 commit。因首次部署跨倉庫，不能只假設一鍵 deploy rollback 可跨 source 工作。舊 source: beef0400-wq/ai-rational-companion-v1 / main；舊 live deploy: dep-dami3jf40ujc73b1ada0。保留 V2 新表為首選，不為回滾清資料。

新增資料表為 v2_state、v2_records、v2_public_539、v2_events、v2_bingo_provenance；既有 users 與 analysis_logs 資料不得删除。平台會員資料表與 539/Bingo 既有兼容表由沿用 init_db 建立。初始化前完整快照涵蓋這些表與欄位的還原。

回滾優先：先停止測試寫入、將測試服務回到前一個 live deploy，保留新增資料表（向後相容）。如果確實需要撤銷 DB migration，先再次導出所有 V2 資料，再在新建的隔離 DB 還原「部署前」完整 pg_dump；將測試服務 DATABASE_URL 指向已核對的還原 DB。不要直接清除舊會員或歷史紀錄。

001_v2_down.sql 只供確認五個 V2 表都是新建、且資料已導出時使用；不能當作完整 DB 還原。既有資料庫含同名 V2 表時不適用。

正式切換前須另做兩個 production DB 的只讀快照合併與逐表對帳，不能把測試 DB 當正式來源。目前尚未執行合併或切換。
