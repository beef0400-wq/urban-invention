"""Isolated Render test gate. Runs before importing legacy database initializers."""
import os
import uuid
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
from psycopg2 import sql

TEST_HOST = 'dpg-damhkgou01pc73aadrr0-a'
TEST_DB = 'ai_rational_companion_v1_test_db'


def validate_database_url(url):
    parsed = urlparse(url)
    host = parsed.hostname or ''
    if not (host == TEST_HOST or host.startswith(TEST_HOST + '.')):
        raise RuntimeError('V2 test gate: database host is not the isolated test database')
    if parsed.path.lstrip('/') != TEST_DB:
        raise RuntimeError('V2 test gate: database name is not the isolated test database')
    return True


def migration_body(path):
    lines = path.read_text().splitlines()
    return '\n'.join(line for line in lines if line.strip().upper() not in {'BEGIN;', 'COMMIT;'})


def main():
    url = os.environ.get('DATABASE_URL', '')
    validate_database_url(url)
    conn = psycopg2.connect(url, sslmode='require')
    schema = 'v2_rehearsal_' + uuid.uuid4().hex
    root = Path(__file__).resolve().parent
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT current_database()')
            if cur.fetchone()[0] != TEST_DB:
                raise RuntimeError('V2 test gate: connected database mismatch')
            cur.execute('SELECT to_regclass(%s)', ('public.v2_state',))
            first_migration = cur.fetchone()[0] is None
            if first_migration:
                # The saved baseline is empty. Abort if someone added data since backup.
                for table in ('users', 'analysis_logs'):
                    cur.execute(sql.SQL('SELECT count(*) FROM public.{}').format(sql.Identifier(table)))
                    if cur.fetchone()[0] != 0:
                        raise RuntimeError('V2 test gate: baseline changed; take a fresh full backup')
            cur.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            cur.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(schema)))
            cur.execute(migration_body(root / 'deployment/restore_empty_test_baseline.sql'))
            for table in ('users', 'analysis_logs'):
                cur.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table)))
                if cur.fetchone()[0] != 0:
                    raise RuntimeError('Empty baseline restore rehearsal failed')
            cur.execute(migration_body(root / 'migrations/001_v2_up.sql'))
            cur.execute("INSERT INTO v2_state VALUES ('rehearsal', '{}')")
            cur.execute("SELECT count(*) FROM v2_state WHERE user_id='rehearsal'")
            if cur.fetchone()[0] != 1:
                raise RuntimeError('V2 migration rehearsal write failed')
            cur.execute(migration_body(root / 'migrations/001_v2_down.sql'))
            cur.execute('SELECT count(*) FROM information_schema.tables WHERE table_schema=%s', (schema,))
            if cur.fetchone()[0] != 2:
                raise RuntimeError('V2 rollback rehearsal failed')
        # No schema or rehearsal data is committed to the database.
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute('SELECT count(*) FROM pg_namespace WHERE nspname=%s', (schema,))
            if cur.fetchone()[0] != 0:
                raise RuntimeError('V2 rollback left a rehearsal schema')
        print('V2_TEST_PREFLIGHT PASS: isolated DB; empty baseline restore; migration up/down; transaction rollback', flush=True)
    finally:
        conn.rollback()
        conn.close()


if __name__ == '__main__':
    main()
    from ui_preflight import main as validate_ui
    validate_ui()
