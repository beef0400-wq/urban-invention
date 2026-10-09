# AI理性陪跑 V2｜MASTER CHECKPOINT

## CURRENT
甦贏 mobile portal deployed on existing isolated service; owner-authorized research OA remains connected. Browser homepage/539 navigation checked. New portal phone acceptance and owner admin role confirmation pending.
Date: 2026-10-09 Asia/Taipei.
Repository: beef0400-wq/urban-invention.
Branch: v2-rational-companion-test-20261007.
Runtime commit: 43159aa35526225ad964be5f9f0ce07a0516f3e7.
Service: srv-dami3j740ujc73b1acfg.
Test DB: dpg-damhkgou01pc73aadrr0-a.
URL: https://ai-rational-companion-v1-test.onrender.com

## DONE
- Existing core retained: V15 baccarat and original 539 selection models.
- Unified member permissions, mode navigation and records.
- Batch road import / preview / correction / confirmation, one-click next-round update.
- Conservative screenshot recognition; no guessed long-dragon or overlaid tie reconstruction.
- 539 immutable pre-draw lock, same-date reconciliation, 7/30/90 reports including failures.
- Bingo fabricated fallback disabled; validated source provenance and freshness gate.
- Fixed current HTML tags; real source pagination loads 240 historical 539 draws.
- Isolated test source/branch configured on Render, autoDeploy off; production untouched.
- Schema baseline confirmed empty before migration. Preflight fixed DB guard, schema restore, up/down migration and transaction rollback PASS.
- Fixed new Postgres baccarat user NULL trial date conversion crash.
- 36 local tests PASS, including V15 100-road equivalence, 539 normal/recovery equivalence, source parsing, nullable trial dates and scheduler timing.
- Remote signed webhook, unsigned rejection, shared member, batch confirmation/correction, one-click round, duplicate event, three-mode router and records PASS.
- Remote real history: 539 240 draws (2026-01-05 through 2026-10-07); Bingo 109 verified source draws at latest smoke.
- 2026-10-08 forecast locked at 16:06:42+08, SHA256 07dcccee4cf107738ecd672bbe451d0d2ce68c6b3cc3d3e1b4b3df405e7dee8e. Actual=NULL pending tonight's draw.
- Free runtime scheduler: attempts pre-draw locking from 18:00 until 20:00; reconciles from 21:00, every 5 minutes while instance is alive. Awakening catches up results; never backfills late predictions.
- LINE credentials valid (bot/info 200). OA: AI理性陪跑研究室 @957ridwt. Owner explicitly approved dedicated new-program use; webhook now matches V2, active=true. LINE webhook/test success=true and HTTP 200 at 09:35:10Z. Previous endpoint stored in v2_state key __v2_line_connection__ for rollback; do not print it.

## DOING
- DONE: Final clean-start deploy dep-db3l08navr4c73a7vg6g LIVE at 2026-10-08 08:12:12Z; no repeated startup smoke. /health 200 with verification_scheduler=true; cron calls without secrets 403.
- Connection deployment dep-db3m78c9v7es73dknej0 LIVE. Normal start restored (no configure_line.py); clean deployment dep-db3m8449v7es73dkqvr0 LIVE at 09:37:15Z.

## BLOCKED / LIMITS
- Owner confirmation complete; no further OA authorization needed.
- Real LINE receive/reply/image-download and phone acceptance NOT TESTED.
- Need 3–5 real bead-plate road screenshots for platform calibration; synthetic images are not evidence of cross-platform accuracy.
- Tonight's actual draw reconciliation cannot be verified before the draw.
- Free Render idle sleeping means runtime scheduler is not an always-on SLA. For guaranteed production times, activate an external scheduler separately. GitHub workflows under v2/.github remain templates, not active schedules.
- One worker / one instance only. Crash between application write and event completion remains a narrow duplicate-processing risk; do not claim exactly-once.

## NEXT
1. Confirm clean-start deployment live and /health scheduler=true.
2. Persist report / screenshot; push checkpoint / README / rollback updates.
3. Obtain real screenshots for platform calibration.
4. OA routing and LINE verify complete; owner sends 主選單 for real phone acceptance.
5. Observe real post-draw reconciliation; check locked hash and same-date result preservation.
6. Production migration/switch requires separate snapshots, member merge and owner approval.

## ROLLBACK
Previous verified V2 deploy: dep-db3kv28m7kps73f3v6e0, runtime f81914c.
Earlier verified V2 deploy: dep-db3ktd7avr4c73a7ksd0, runtime 6ab7574.
Prefer application rollback preserving added tables. Do not drop member/history data.
Original cross-repository source: ai-rational-companion-v1 / main, live dep-dami3jf40ujc73b1ada0. Returning to that source needs restoring repo/branch/build/start settings; do not assume cross-repository one-click rollback.
See ROLLBACK.md and deployment/test_db_baseline.json.

## Phone acceptance 2026-10-08 17:48+08
- Owner screenshot confirms actual LINE 主選單 receive/reply and 確認開始 analysis with next-round quick replies.
- Found zero signal index still displaying direction; presentation now shows 觀望 when index=0. Public decision card uses 紅/藍 throughout and labels correlated rules 訊號彙整. Core scores/directions unchanged.
- 37 local tests pass, including zero-index presentation regression and existing core equivalence.
- Real image calibration and remaining modes/phone steps still pending.

## Native LINE presentation V2.2 (2026-10-08)
- All gateway replies use shared Flex: home, modes, live/detail analysis, membership, trial, records, instructions, confirmation/errors and verification. Text content and commands preserved; public display translates red/blue names.
- Navy header, white sections, color-coded modes, number chips, complete content paginated into swipeable panels; native footer exposes all actions, result buttons stay on one row. No maxLines clipping. Oversized replies retain previous text fallback.
- Core models, permissions, DB schema and LINE webhook unchanged. 回主選單 alias added.
- 40 local tests PASS, including actions, number preservation, long-report pagination and payload byte limits. Deployment startup validates 8 representative message types with official LINE validate/reply; no messages sent.
- Await real phone screenshots for font/width visual acceptance after deployment.

- V2.2 deployment dep-db3q4cqj9qps738l9ut0 LIVE at 2026-10-08 14:03:03Z. Official LINE validated all 8 cases (V2_FLEX_PREFLIGHT PASS); /health 200 reports INTEGRATED-V2.2-FLEX-TEST with verification_scheduler=true. No real messages sent by verification.

## Experience V2.3 (2026-10-08 owner approved continuation)
- Home reports membership/expiry, live baccarat road and pending preview, today's actual 539 lock/reconciliation status and last Bingo read status (explicitly not live background refresh).
- Resume table across modes. One-step undo restores full previous analysis state, including counters, and consumes the snapshot once. Ending/new table clears undo.
- Live append/correct/delete stages a preview; confirm required, original road preserved until confirmation. New image/text offers update current table vs new table. Full-prefix or unique overlap >=12 only; ambiguous alignment never auto-merges. Preview checks base road before apply.
- Human explanation added to baccarat and 539; Bingo describes its rise/fall window and historical-statistic limits. Algorithms unchanged.
- 539 today tracking shows original locked hash/date, exact-date actual, hits and reconciliation time.
- Bingo 20/50/100 now filters actual window; default overview shows all three. Existing source/freshness checks preserved.
- Admin member-button flow: recent inactive bound accounts, 3/7/30 days, explicit final confirmation; admin auth checked each step and account identity rechecked. Existing /vip remains supported.
- 47 local tests pass including undo state restoration, cancel, stale preview, ambiguous alignment, cross-mode resume, Bingo windows and admin confirmation/access revocation.
- LINE startup validates 12 representative UI cases without sending messages. Mobile visual acceptance remains needed.

- Remote isolated Postgres experience smoke PASS at 2026-10-08 16:08:45Z (undo/correction/resume/home/tracking). LINE validated 12 representative UI cases and 3 actual router replies. Synthetic identity was cleaned; verification marker prevents repeated experience smoke on restart.

- Final deployment dep-db3s0iegekts73fv9m80 LIVE at 2026-10-08 16:10:58Z. /health 200, version INTEGRATED-V2.3-EXPERIENCE-TEST and verification_scheduler=true. 47 tests PASS. Normal restart skips previously verified experience smoke.


## 甦贏 V2.4 mobile portal (2026-10-09 Asia/Taipei)
Owner approved new brand 甦贏 and LINE -> full mobile website, simple first layer with deeper analysis.
- Additive Flask portal at existing service root. LINE command 開啟甦贏 issues one-use 10-minute login link; 8-hour HttpOnly Secure SameSite cookie, CSRF on mutations. Never accepts a browser-supplied LINE user ID.
- Shared gateway reply capture uses ContextVar (no global monkeypatch); shared member/model/table storage. Web request dedup cache is per authenticated session and request ID. Same single-worker limits apply.
- Homepage registration/member, large baccarat/539, smaller Bingo, monthly/weekly campaigns, resume active table. Existing registration address retained from legacy source: https://AI001.aaawin88.com.
- Baccarat upload + conservative recognition preview, manual/batch input, live buttons, undo, correction, table choices. Full analysis expandable. Core algorithm unchanged.
- 539 large actions, mother number chips, expandable full model/combination reasons, original reconciliation reports, private favorite numbers (<=10, not prediction inputs).
- Bingo original source/freshness/window checks and full text retained in expandable sections.
- Admin-only campaign manager: image uploads reencoded JPEG, date scheduling in Taipei, preview then publish, separate draft/live records, expiry/hide, builtin destinations. Homepage Bingo size toggle. Empty activity state until owner supplies images.
- 55 local tests PASS including identity expiry, CSRF, shared trial/table/undo, dedup, cross-user isolation, drafts/private images, publish/expiry, favorite limits and admin revocation.
- Startup validates 13 LINE message formats including URI portal entry; isolated portal Postgres smoke sends no LINE messages and cleans its synthetic identity.
- First portal deployment dep-db3tk4g473hc73btqmm0 LIVE at 2026-10-08 18:01:30Z. Postgres portal smoke PASS at 18:01:11Z, 13 official LINE format checks PASS. Browser homepage and public 539 controls render correctly; local cloud-browser connection unavailable, so QA used deployed service. Owner phone acceptance pending. OA display name/rich menu artwork have not been changed.

- Final UI refinement runtime 43159aa35526225ad964be5f9f0ce07a0516f3e7: direct registration link at homepage top; seasonal Bingo toggle applies to public visitors too. Deployment dep-db3tm8u7bikc73ac96f0 LIVE at 2026-10-08 18:05:34Z (Taipei 02:05:34 Oct9). /health HTTP200 SUYING-V2.4-WEB-TEST; public activities200, unauthenticated portal401.
- Rollback: restore b19e6dcc1c2456c6bb6e3d1a5660aa76b887924f preserving all DB data. New web auth/draft/campaign/favorite state is additive v2_state, no schema removal.
- NEXT for new portal: owner sends 開啟甦贏 in research OA; phone login/road image/control acceptance; verify owner sees 活動管理; supply monthly/weekly images. OA account display name and native rich-menu artwork are still owner-managed and have not been renamed by this change.


## 甦贏 V2.5 compact cards (2026-10-09 owner requested)
- Removed homepage progress/resume on both web and LINE; no old table promoted as a next-session entry. Web portal no longer returns aggregate progress.
- Baccarat starts fresh on first entry in each document session (including reload/new tab): authenticated 開始新桌 clears current road/pending/undo/counters; membership, favorites and historical records retained. Continuous rounds and navigation within the current open page remain usable.
- All web surfaces share compact icon cards; primary home cards shortened and Bingo remains subordinate. Reports split losslessly into small cards with exact number chips; first three cards visible, remaining cards individually expandable. No invented chart data or fake scores.
- LINE Flex uses smaller kilo bubbles, two sections per card, full actions on first card and lightweight home action on subsequent cards. All report text and original commands retained.
- 56 local tests PASS; JS syntax and report preservation/escaping/number-chip smoke PASS. Startup validates 13 official LINE formats and fresh-table Postgres smoke under V25 marker; no messages sent.
- Deployment and browser visual verification pending. Previous runtime rollback 43159aa35526225ad964be5f9f0ce07a0516f3e7; preserve all DB data.
