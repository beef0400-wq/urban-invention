# 甦贏首頁、模式介紹與參考資訊中心

## Scope
- Replaced the portal's home content with a responsive three-mode entry page, actual-interface screenshot, reference articles, and existing electronic-zone links.
- Added public server-rendered `/discover`, `/guide/baccarat`, `/guide/539`, `/guide/bingo`, `/learn` and nine `/learn/<slug>` articles.
- Search and category filtering use ordinary GET requests and work without JavaScript or membership. Unknown article/mode paths return 404. Templates escape query text; public pages have CSP and do not issue sessions.
- LINE official-site links now point to this service's `/discover`; member/login links still use the existing signed gateway.
- Preserved operation APIs, membership and admin logic, existing electronic-zone routes, and game calculations.
- Articles describe existing controls, dates, sample ranges, correction flow and membership. They do not claim unmeasured performance. The 600+ community statement is owner-confirmed.
- Images are captured from the actual portal with explicitly synthetic local state. No real accounts or credentials are included. 539 screenshot is labeled as interface/demo date rather than current analysis. Test transport is isolated to localhost.
- Browser QA uses Playwright. Optional external browser/font packages are test-environment dependencies only; none are needed by Render or public pages.

## Verification
- Public content routes, search/category/body matching, escaped input, invalid paths, shareability and mode boundaries: 4 tests passed.
- Existing portal authentication/login/trial/shared-data checks: 4 targeted tests passed.
- Existing official LINE/web navigation checks: 2 passed, run from `v2/` to avoid importing the root legacy `app.py`.
- Browser checks at 320, 390 and 1440 CSS pixels: home, overview, all three modes, article index and article; no horizontal overflow or broken images. Search, FAQ, entry button and navigation exercised.
- JS syntax and diff whitespace checks passed.

## Deployment target
Branch `v2-rational-companion-test-20261007`; Render `srv-dami3j740ujc73b1acfg` in owner-confirmed workspace `tea-d6fc0pfgi27c73crft20`. Existing Sites marketing artifact is not replaced or deleted.
