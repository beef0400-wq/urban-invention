# AI理性陪跑 V2｜MASTER CHECKPOINT

## CURRENT
Backend deployed; owner-authorized research OA connected and LINE official verification PASS (HTTP 200). Phone acceptance pending.
Date: 2026-10-08 Asia/Taipei.
Repository: beef0400-wq/urban-invention.
Branch: v2-rational-companion-test-20261007.
Runtime commit: 71f31783204ca08ddb004f5aaf368cf98bdd4292.
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
