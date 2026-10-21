# Electronic community zone — 2026-10-21

Scope: non-monetary game operating instructions and member experiences. No deposits, wagering, payouts, betting recommendations, or generated testimonials in this module.

Base: 9c75bf24b280da9644bf6a1b0d06336285fc75c2, branch v2-rational-companion-test-20261007.
Service: srv-dami3j740ujc73b1acfg, existing service only.
Previous live deploy: dep-dbbeib7avr4c73djllt0.

Entry: LINE main menu → 電子專區 → exactly 領取打法專區 / 反饋專區. Web /electronics has the same two entries. Existing web homepage and top navigation link to it.

Admin: sign in through existing LINE login, open /electronics#admin. Save draft, preview, publish/schedule or hide. Published versions cannot be overwritten directly; copy as a new draft (defaults to +14 days) or hide before editing. Taiwan timestamps. At request time each game exposes only its two most recent published, due versions. Future entries and drafts are not public. Old releases remain stored for rollback; absence of new content does not fabricate or expire an edition. Weekly collation is an editorial process, not automatic content generation.

Feedback: explicit publication consent required, images must be redacted by editor before upload. Server re-encodes uploads as JPEG to strip metadata and reject non-raster payloads. 3MB, 16MP, eight images per item. Assets persist in existing Postgres-backed state table, not ephemeral disk. Public feedback can be viewed without signing in; guide body and associated images require LINE login. Admin mutations require current administrator identity and CSRF.

The owner explicitly confirmed the 600+ membership/agent statement; displayed as supplied, not independently audited. No individual feedback or guide has been seeded.

Verification: 21 targeted tests pass; one existing 539 overview date test excluded after reproducing identical failure on clean baseline. New tests cover authentication/CSRF, draft privacy, scheduling, latest-two visibility, immutable published content, feedback consent, image validation/access, login target allowlist and two-entry LINE menu. JS syntax and git whitespace checks pass. Browser local download unavailable (corrupt/blocked download); post-deploy visual verification remains required.

Images downloaded from manufacturer sites, original artwork unmodified. Original rights remain with RSG and ATG; no endorsement claimed.
- https://www.rsg-games.com/en-US/games_detail_112.html
- https://www.rsg-games.com/assets/images/games/112/slot-PowerofThor-rsg-detail-banner-mobile-bg.webp
- https://www.rsg-games.com/assets/images/games/112/slot-PowerofThor-rsg-detail-banner-mobile-logo-en-US.webp
- https://www.atg-games.com/zh-tw/games/slot/storm-of-seth
- https://atg-games.com/storm-of-seth/character/banner_character.png

Optimized ATG WebP delivered by its own image endpoint: https://atg-games.com/_ipx/f_webp/storm-of-seth/character/banner_character.png

## Deployment verification
- Render deploy dep-dbc86ics728c73eaqea0 LIVE at 2026-10-21 09:19:01Z, code commit 84b196df88865b23cdaaff8edc56d083cfcab957.
- Cloud browser verified actual /electronics home, two entry links, 600+ statement, guides and feedback navigation. Both manufacturer images loaded successfully. Empty-state copy displayed; no placeholder testimonials published.
- Desktop visual inspection passed. Mobile responsive CSS implemented; real phone / LINE login acceptance remains with owner. Admin upload and publishing covered locally, no fake live content added.
