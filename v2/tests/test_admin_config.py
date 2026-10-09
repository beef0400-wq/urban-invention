import ast
import os
from pathlib import Path

import pytest


@pytest.mark.parametrize('path', ['app.py', 'legacy/baccarat.py', 'legacy/lotto539.py'])
@pytest.mark.parametrize('existing,owner,expected', [
    ('Uexisting', 'Uowner', {'Uexisting', 'Uowner'}),
    (' Uexisting, ,Uanother ', ' Uowner ', {'Uexisting', 'Uanother', 'Uowner'}),
    ('Uexisting', '', {'Uexisting'}),
    ('', 'Uowner', {'Uowner'}),
    ('', '', set()),
])
def test_admin_config_preserves_existing_and_limits_owner(monkeypatch, path, existing, owner, expected):
    monkeypatch.setenv('ADMIN_USER_IDS', existing)
    monkeypatch.setenv('OWNER_ADMIN_USER_ID', owner)
    tree = ast.parse((Path(__file__).parents[1] / path).read_text())
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'ADMIN_USER_IDS' for t in node.targets))
    scope = {'os': os}
    exec(compile(ast.Module(body=[assignment], type_ignores=[]), path, 'exec'), scope)
    assert set(scope['ADMIN_USER_IDS']) == expected
    assert 'Uunrelated' not in scope['ADMIN_USER_IDS']
