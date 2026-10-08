import pytest
from deployment_preflight import validate_database_url, TEST_HOST, TEST_DB


@pytest.mark.parametrize('host', [TEST_HOST, TEST_HOST + '.oregon-postgres.render.com'])
def test_isolated_database_accepted(host):
    assert validate_database_url(f'postgresql://user:password@{host}/{TEST_DB}')


@pytest.mark.parametrize('url', [
    '',
    'postgresql://u:p@production/db',
    f'postgresql://u:p@{TEST_HOST}/wrong_database',
    f'postgresql://u:p@{TEST_HOST}-wrong/{TEST_DB}',
])
def test_other_databases_rejected(url):
    with pytest.raises(RuntimeError):
        validate_database_url(url)
