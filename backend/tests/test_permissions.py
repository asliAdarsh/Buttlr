"""The permission engine is the security boundary — these tests are the contract.

Every property here is enforced server-side; none of it can be influenced by a request body.
"""

from __future__ import annotations

from app.runtime.permissions.engine import (
    AccessContext,
    PermissionEngine,
    granted_permission,
)
from app.schemas.buttlr import ApprovalPolicy, ApprovalRule, Buttlr, PermissionGrant
from app.schemas.enums import (
    ApprovalMode,
    Decision,
    GrantSubject,
    OrgRole,
    Permission,
    RiskLevel,
)
from app.schemas.organization import OrganizationSettings

engine = PermissionEngine()


def make_buttlr(**overrides) -> Buttlr:
    payload = {
        "id": "b1",
        "organization_id": "org1",
        "name": "PR Guardian",
        "permissions": [],
    }
    payload.update(overrides)
    return Buttlr.model_validate(payload)


def member(user_id: str = "u1", teams: tuple[str, ...] = ()) -> AccessContext:
    return AccessContext(user_id=user_id, org_role=OrgRole.MEMBER, team_ids=teams)


def owner(user_id: str = "owner") -> AccessContext:
    return AccessContext(user_id=user_id, org_role=OrgRole.OWNER)


def test_member_without_a_grant_is_denied() -> None:
    decision = engine.evaluate(
        buttlr=make_buttlr(),
        access=member(),
        tool_name="github.list_pull_requests",
        required_permission=Permission.EXECUTE,
        risk=RiskLevel.LOW,
    )
    assert decision.decision == Decision.DENY
    assert decision.granted_permission is None


def test_owner_has_admin_floor() -> None:
    decision = engine.evaluate(
        buttlr=make_buttlr(),
        access=owner(),
        tool_name="github.list_pull_requests",
        required_permission=Permission.EXECUTE,
        risk=RiskLevel.LOW,
    )
    assert decision.decision == Decision.ALLOW
    assert decision.granted_permission == Permission.ADMIN


def test_team_grant_is_honoured() -> None:
    buttlr = make_buttlr(
        permissions=[
            PermissionGrant(
                subject_type=GrantSubject.TEAM, subject="eng", permission=Permission.EXECUTE
            )
        ]
    )
    assert engine.can(buttlr=buttlr, access=member(teams=("eng",)), permission=Permission.EXECUTE)
    assert not engine.can(buttlr=buttlr, access=member(teams=("finance",)), permission=Permission.EXECUTE)


def test_ask_rule_requests_approval_without_allowing_execution() -> None:
    buttlr = make_buttlr(
        permissions=[
            PermissionGrant(
                subject_type=GrantSubject.EVERYONE, subject="*", permission=Permission.EXECUTE
            )
        ],
        approval_policy=ApprovalPolicy(
            rules=[ApprovalRule(tool="jira.create_issue", mode=ApprovalMode.ASK)]
        ),
    )
    decision = engine.evaluate(
        buttlr=buttlr,
        access=member(),
        tool_name="jira.create_issue",
        required_permission=Permission.EXECUTE,
        risk=RiskLevel.HIGH,
    )
    assert decision.decision == Decision.REQUEST_APPROVAL
    assert decision.requires_approval
    assert not decision.allowed


def test_deny_rule_wins_over_permission() -> None:
    buttlr = make_buttlr(
        permissions=[
            PermissionGrant(
                subject_type=GrantSubject.EVERYONE, subject="*", permission=Permission.ADMIN
            )
        ],
        approval_policy=ApprovalPolicy(
            rules=[ApprovalRule(tool="github.create_issue", mode=ApprovalMode.DENY)]
        ),
    )
    decision = engine.evaluate(
        buttlr=buttlr,
        access=member(),
        tool_name="github.create_issue",
        required_permission=Permission.EXECUTE,
        risk=RiskLevel.HIGH,
    )
    assert decision.decision == Decision.DENY


def test_high_risk_defaults_to_approval_even_with_a_permissive_policy() -> None:
    buttlr = make_buttlr(
        permissions=[
            PermissionGrant(
                subject_type=GrantSubject.EVERYONE, subject="*", permission=Permission.EXECUTE
            )
        ]
    )
    settings = OrganizationSettings(require_approval_for_high_risk=True)
    access = AccessContext(
        user_id="u1", org_role=OrgRole.MEMBER, team_ids=(), settings=settings
    )
    decision = engine.evaluate(
        buttlr=buttlr,
        access=access,
        tool_name="gmail.send_message",
        required_permission=Permission.EXECUTE,
        risk=RiskLevel.HIGH,
    )
    assert decision.decision == Decision.REQUEST_APPROVAL


def test_attenuation_caps_the_buttlr_at_its_creators_authority() -> None:
    """A run must never exceed the authority of the account that owns the Buttlr."""
    buttlr = make_buttlr(
        permissions=[
            PermissionGrant(
                subject_type=GrantSubject.USER, subject="buttlr-actor", permission=Permission.ADMIN
            )
        ]
    )
    # The actor holds admin on the Buttlr, but the account that owns it has no access at all,
    # so the delegated authority collapses to none.
    decision = engine.evaluate(
        buttlr=buttlr,
        access=AccessContext(user_id="buttlr-actor", org_role=OrgRole.MEMBER),
        tool_name="github.create_issue",
        required_permission=Permission.EXECUTE,
        risk=RiskLevel.MEDIUM,
        owner_access=AccessContext(user_id="creator", org_role=OrgRole.MEMBER),
    )
    assert decision.decision == Decision.DENY


def test_grant_hierarchy_is_ordered() -> None:
    buttlr = make_buttlr(
        permissions=[
            PermissionGrant(
                subject_type=GrantSubject.USER, subject="u1", permission=Permission.VIEW
            )
        ]
    )
    assert granted_permission(buttlr, member()) == Permission.VIEW
    assert engine.can(buttlr=buttlr, access=member(), permission=Permission.VIEW)
    assert not engine.can(buttlr=buttlr, access=member(), permission=Permission.ASK)
    assert not engine.can(buttlr=buttlr, access=member(), permission=Permission.CONFIGURE)


def test_require_raises_for_insufficient_permission() -> None:
    from app.core.errors import PermissionDeniedError

    buttlr = make_buttlr()
    try:
        engine.require(
            buttlr=buttlr, access=member(), permission=Permission.CONFIGURE, action="edit it"
        )
    except PermissionDeniedError as exc:
        assert exc.details["required_permission"] == "configure"
    else:  # pragma: no cover
        raise AssertionError("expected PermissionDeniedError")
