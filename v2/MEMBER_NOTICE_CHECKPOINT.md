# Membership transaction notice — 2026-10-21

- LINE management and web account grants now push a member-facing confirmation to the resolved account owner's LINE ID, with bound username, Taiwan expiry, and Start / Member Center buttons.
- Active paid extensions use a renewal heading. Existing accounts are not backfilled.
- Grant state is saved before network notification. Notification failure does not undo access or retry the grant. Repeated LINE confirmation and identical web request IDs do not send again.
- Admin results distinguish LINE API acceptance from unconfirmed notification; acceptance does not guarantee receipt/read status.
- Tests use mocked transport only; no production member expiry or messages changed during verification.
- Targeted verification: 9 LINE/admin/transport tests and 5 web admin/binding tests passed; JS syntax and diff whitespace checks passed.
- Production target remains branch `v2-rational-companion-test-20261007`, Render service `srv-dami3j740ujc73b1acfg`. No env, plan, database schema, membership duration rules, or game logic changes.
- Human follow-up: on the next legitimate opening/renewal, check the member's LINE receives the card. Do not re-open an existing member just to test a notification.
