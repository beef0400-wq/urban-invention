-- Before applying: stop V2 workers and export V2 tables using pg_dump.
-- This reverse migration applies ONLY if all five tables were absent in the pre-up baseline.
-- Never run against a shared production DB, and never remove pre-existing tables.
BEGIN;
DROP TABLE v2_bingo_provenance;
DROP TABLE v2_events;
DROP TABLE v2_public_539;
DROP TABLE v2_records;
DROP TABLE v2_state;
COMMIT;
