# V2.17 point engine access restoration

The old point calculation and four modes (保守/標準/積極/極限) remained in legacy/baccarat.py but were absent from V2 menus and the web allowlist. Mode-dependent legacy routing could send configuration commands to 539.

Added explicit gateway handler and independent per-user draft state: point range -> mode -> target ratio. Commit all three profile fields only at final selection. Cancel/home/navigation preserve saved settings; updates preserve active road, import/edit preview, undo, predictions and streaks. Existing point-range/mode plain text selections remain supported within a draft. Target percentage is described as an existing calculation parameter, not a promised return. Existing get_base_points, calculate_points, and analyze_v15 ASTs are unchanged.

LINE live/menu and detail point-section footers now expose points/modes. Web has matching buttons and exact command allowlist. Normal red/blue/tie messages do not incur a new points-state lookup. Binding can be interrupted by these explicit commands. Starting a new web desk discards unfinished point drafts.

Tianmen: a clearly labelled entry is present but NOT activated. Original complete rule sequence, transitions, ties and stop conditions were not found in current source, original reference source or retrieved prior conversation. Do not substitute the rejected six-stage scheme. Owner input is required before implementing this part.

Checks: 15 new integration cases passed (four modes, atomic save/cancel, cross-mode routing, expired access, preserved table/edit state, old aliases, binding interruption, unchanged loss pause, detail Flex actions, authenticated web flow). Ten relevant existing import/round/undo/correction/analysis tests passed. Python and JavaScript syntax passed. No database migration or membership change.

After deploy: verify /health version SUYING-V2.17-POINT-ENGINE. Owner LINE round-trip check: 百家實戰 -> 點數／打法 -> 設定點數 -> range -> mode -> target, then return to current table. Tianmen remains blocked pending authentic rules.
