# AI理性陪跑 V2｜MASTER CHECKPOINT

## CURRENT
甦贏 mobile portal deployed on existing isolated service; owner-authorized research OA remains connected. Browser homepage/539 navigation checked. New portal phone acceptance and owner admin role confirmation pending.
Date: 2026-10-09 Asia/Taipei.
Repository: beef0400-wq/urban-invention.
Branch: v2-rational-companion-test-20261007.
Runtime commit: 4dd9a85beb207ced38ed3ed92dc6e99865fb09b4 (SUYING-V2.7-ACCOUNT-TEST).
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
- Deployment dep-db47jpbl550s73arigo0 LIVE at 2026-10-09 05:23:28Z (Taipei 13:23:28). Startup LINE 13-format validation PASS at 05:22:34Z and fresh-table Postgres portal smoke PASS at 05:23:17Z; no messages sent. Deployed browser homepage and public 539 compact icon cards verified; homepage contains no resume/progress panel. Owner phone/authenticated visual acceptance remains pending. Previous runtime rollback 43159aa35526225ad964be5f9f0ce07a0516f3e7; preserve all DB data.

## V2.6 orange and explicit 539 labels
- Fire red/orange theme across web and LINE; live red/blue/tie semantics retained.
- Optional panel prose collapsed under 看說明. Deeper report groups collapsed.
- 539 overview separates previous actual draw, current target-date forecast, and current actual if available. Date identifies the draw; no fabricated official issue ID. Forecast only disclosed to an authenticated active member from immutable lock, never rebuilt on GET. Cache-Control private/no-store. Missing/unlocked status explicit.
- LINE daily analysis also labels previous actual and current prediction dates; no algorithm changes.
- 57 tests PASS including previous/current draw separation and member-only forecast disclosure. V2.6 deployed LIVE dep-db47qe942hec73adkf2g at 2026-10-09 05:37:00Z; real previous draw 2026-10-08 [03,07,15,17,30], public forecast protected, orange homepage and 539 browser checked.

## V2.7 standalone application accounts (owner accepted)
- Independent stable SY identifiers automatically created on signed-in portal entry. No external registration/account binding/deposit qualifications.
- Personal center shows own identifier/status/expiry; copy and optional activation explanation. External casino registration and binding removed from web template, portal response, command allowlist and campaign destinations.
- Admin account activation uses SY identity only, 3/7/30 days and confirmation. Web role/CSRF required, per-target lock and request dedup with parameter mismatch rejection. Native LINE management also resolves SY accounts. No guessed admin role granted.
- Existing membership durations and personal history retained; expired trial identified as expired in personal center.
- 59 local tests PASS. Startup V27 synthetic Postgres smoke checks independent account creation/cleanup. Deployment dep-db484l7lot8c73859s30 LIVE at 2026-10-09 05:59:21Z. Postgres V27 smoke PASS at 05:59:14Z and 13 official LINE format validations PASS at 05:58:31Z. Browser confirms external registration removed and 個人中心 header shown. Owner phone/account/admin acceptance remains pending; no real account grants performed.


## 2026-10-09 Owner admin access V2.7.1
- Owner provided LINE /myid screenshot; add verified identity through private Render OWNER_ADMIN_USER_ID (do not commit identity).
- Main app and both legacy modules merge OWNER_ADMIN_USER_ID with existing ADMIN_USER_IDS, preserving previous administrators.
- LINE and web admin checks use the merged allowlist; unrelated users remain denied.
- Local regression: 74 passed including 15 admin configuration cases.
- Deployment and owner real-device verification pending at commit time.

- Owner explicitly confirmed exact LINE identity and admin grant on 2026-10-09. Render OWNER_ADMIN_USER_ID merged successfully.
- Deployment dep-db4aljd9fdbs73bc6rs0 LIVE at 2026-10-09T08:51:33Z; runtime commit 45118e0d7b8668ce80a3be4aed30eb02262e1aa9. Database and 13 LINE Flex preflights PASS; owner real-device admin command verification remains pending.


## V2.7.2 Admin account list fix
- Owner verified LINE admin command reaches management screen; list was empty because only inactive accounts were shown and message entry did not create application identities.
- Create application account on LINE event entry; admin list includes recent trial, paid, and inactive accounts with clear status. No membership granted by viewing list.
- Added regression coverage for first-message account creation and selecting trial/paid/free accounts. Deployment pending.


## V2.8 username binding / one-hour trial (2026-10-09)
- Users bind a 4–20 character ASCII username from LINE or authenticated personal center; confirmation, cancellation, case-insensitive unique index, immutable binding. Binding never grants membership. Success asks users to return to helper for verification. Helper URL not supplied; no invented link.
- Admin list shows bound usernames and accepts username or existing internal SY code. Internal IDs and membership data preserved.
- New trials last one hour, once per LINE identity, all three modes. Bound users cannot start trials; binding preserves an already-running expiry. Existing trial expiries preserved. UI hides unavailable trial buttons; server rejects replay.
- Browser open-page expiry reminder polls locally every 15 seconds and refreshes server status; LINE reminds on next operation. No unsolicited scheduled LINE push configured.
- Verification: 80 pytest tests pass; node --check passes. Includes auth/CSRF, cross-user collision, manual grant, one-hour expiry and mode guards.
- Runtime commit 65a8918c85880a226349e35a739604e8b997dbed; deploy dep-db4b6k59fdbs73bdncc0 LIVE 2026-10-09T09:27:52Z. Database preflight and 13 LINE message validations PASS.


## V2.9 compact cards and tutorials (2026-10-09)
- Screenshot requests: one mega-size LINE home bubble, wrapped clickable text tiles instead of truncated button labels; no duplicated quick-reply home menu. Red/blue/draw round buttons stay native buttons.
- 539 default card keeps previous actual draw, current forecast motherboard/core and 2/3/4 combinations. Model description/structure, per-number diagnostics and recent records moved to separate actions. Same locked model data; detail reads do not record new forecasts or regenerate numbers.
- Recent public records default to 5 periods with separate forecast/actual labels. Full 5-period audit via separate button. Personal history limited to 5 calendar days and 5 entries, Taiwan time. Older stored data preserved.
- Tutorial hub covers baccarat/539/Bingo, with dedicated instructions and interpretation guides; corresponding browser help updated.
- 85 pytest tests PASS and node --check PASS.
- Runtime commit 3c4ed9dfaa92c99a1bffa838744e2fff8473a6ea; deploy dep-db4beu67bikc73e70eg0 LIVE 2026-10-09T09:45:33Z. Remote health 200 V2.9, updated browser copy verified, DB preflight PASS and 17 LINE Flex types validated PASS. Native device visual acceptance remains owner review.
