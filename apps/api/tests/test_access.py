"""RBAC matrix: every (role, action) pair, plus the no-grant-denies rule."""

from __future__ import annotations

import pytest
from app.access import Action, Role, can

MATRIX: dict[tuple[Role, Action], bool] = {
    (Role.ADMIN, Action.VIEW): True,
    (Role.ADMIN, Action.UPLOAD): True,
    (Role.ADMIN, Action.PROCESS): True,
    (Role.ADMIN, Action.RETRY): True,
    (Role.ADMIN, Action.PUBLISH): True,
    (Role.ADMIN, Action.MANAGE_ACCESS): True,
    (Role.OPERATOR, Action.VIEW): True,
    (Role.OPERATOR, Action.UPLOAD): True,
    (Role.OPERATOR, Action.PROCESS): True,
    (Role.OPERATOR, Action.RETRY): True,
    (Role.OPERATOR, Action.PUBLISH): True,
    (Role.OPERATOR, Action.MANAGE_ACCESS): False,
    (Role.VIEWER, Action.VIEW): True,
    (Role.VIEWER, Action.UPLOAD): False,
    (Role.VIEWER, Action.PROCESS): False,
    (Role.VIEWER, Action.RETRY): False,
    (Role.VIEWER, Action.PUBLISH): False,
    (Role.VIEWER, Action.MANAGE_ACCESS): False,
}


@pytest.mark.parametrize(("role", "action"), list(MATRIX))
def test_rbac_matrix(role: Role, action: Action) -> None:
    assert can(role, action) is MATRIX[(role, action)]


@pytest.mark.parametrize("action", list(Action))
def test_no_grant_denies_every_action(action: Action) -> None:
    assert can(None, action) is False


def test_every_role_and_action_pair_is_covered() -> None:
    all_pairs = {(role, action) for role in Role for action in Action}
    assert all_pairs == set(MATRIX)
