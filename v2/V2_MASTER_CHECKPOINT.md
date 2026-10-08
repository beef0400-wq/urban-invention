# AI理性陪跑 V2｜MASTER CHECKPOINT

## CURRENT
Backend test deployment verified; LINE mobile acceptance BLOCKED by unconfirmed OA routing.
Date: 2026-10-08 Asia/Taipei.
Repository: beef0400-wq/urban-invention.
Branch: v2-rational-companion-test-20261007.
Runtime commit: f81914ce6cc4117716526729ec89604faa7bb56c.
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
- LINE credentials valid (bot/info 200). OA: AI理性陪跑研究室 @957ridwt. Webhook active but does not match test URL; unchanged.

## DOING
- DONE: Final clean-start deploy dep-db3l08navr4c73a7vg6g LIVE at 2026-10-08 08:12:12Z; no repeated startup smoke. /health 200 with verification_scheduler=true; cron calls without secrets 403.
- Save final report and evidence after health/live confirmation.

## BLOCKED / LIMITS
- Need owner confirmation that @957ridwt is a dedicated test OA allowed to change webhook, or supply a separate test OA. Do not redirect existing production traffic without confirmation.
- Real LINE receive/reply/image-download and phone acceptance NOT TESTED.
- Need 3–5 real bead-plate road screenshots for platform calibration; synthetic images are not evidence of cross-platform accuracy.
- Tonight's actual draw reconciliation cannot be verified before the draw.
- Free Render idle sleeping means runtime scheduler is not an always-on SLA. For guaranteed production times, activate an external scheduler separately. GitHub workflows under v2/.github remain templates, not active schedules.
- One worker / one instance only. Crash between application write and event completion remains a narrow duplicate-processing risk; do not claim exactly-once.

## NEXT
1. Confirm clean-start deployment live and /health scheduler=true.
2. Persist report / screenshot; push checkpoint / README / rollback updates.
3. Ask only for concrete OA routing confirmation and real screenshots.
4. After OA confirmation: route authorized test channel, run LINE verify and owner phone script.
5. Observe real post-draw reconciliation; check locked hash and same-date result preservation.
6. Production migration/switch requires separate snapshots, member merge and owner approval.

## ROLLBACK
Previous verified V2 deploy: dep-db3kv28m7kps73f3v6e0, runtime f81914c.
Earlier verified V2 deploy: dep-db3ktd7avr4c73a7ksd0, runtime 6ab7574.
Prefer application rollback preserving added tables. Do not drop member/history data.
Original cross-repository source: ai-rational-companion-v1 / main, live dep-dami3jf40ujc73b1ada0. Returning to that source needs restoring repo/branch/build/start settings; do not assume cross-repository one-click rollback.
See ROLLBACK.md and deployment/test_db_baseline.json.
