"""The permission engine.

Single decision point for "may this actor make this Buttlr do this thing?".

Two properties matter and are enforced here, not in the UI:

1. **Attenuation** — a Buttlr can never act with more authority than the person who owns it.
   A scheduled run is evaluated against the creator's authority, capped by the Buttler's own
   grants.
2. **Approval is orthogonal to permission** — having ``execute`` does not mean an action runs
   unreviewed. The approval policy decides that, and it is stored server-side.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch

from app.core.errors import PermissionDeniedError
from app.schemas.buttlr import ApprovalPolicy, Buttlr, PermissionGrant
from app.schemas.enums import (
    PERMISSION_ORDER,
    RISK_ORDER,
    ApprovalMode,
    Decision,
    GrantSubject,
    OrgRole,
    Permission,
    RiskLevel,
)
from app.schemas.organization import OrganizationSettings

ORG_ROLE_FLOOR: dict[OrgRole, Permission] = {
    OrgRole.OWNER: Permission.ADMIN,
    OrgRole.ADMIN: Permission.CONFIGURE,
}


@dataclass(frozen=True)
class AccessContext:
    """Who is acting, and what they are within the organization."""

    user_id: str
    org_role: OrgRole | None = None
    team_ids: tuple[str, ...] = ()
    settings: OrganizationSettings = field(default_factory=OrganizationSettings)

    @property
    def is_owner(self) -> bool:
        return self.org_role == OrgRole.OWNER


@dataclass(frozen=True)
class PermissionDecision:
    decision: Decision
    allowed: bool
    reason: str
    required_permission: Permission
    granted_permission: Permission | None
    risk: RiskLevel
    requires_approval: bool = False
    approver_permission: Permission = Permission.APPROVE
    approver_roles: tuple[str, ...] = ()
    tool: str = ""
    matched_rule: str | None = None

    @property
    def denied(self) -> bool:
        return self.decision == Decision.DENY

    def as_dict(self) -> dict[str, object]:
        return {
            "decision": self.decision.value,
            "reason": self.reason,
            "tool": self.tool,
            "risk": self.risk.value,
            "required_permission": self.required_permission.value,
            "granted_permission": self.granted_permission.value if self.granted_permission else None,
            "requires_approval": self.requires_approval,
        }


def strongest(first: Permission | None, second: Permission | None) -> Permission | None:
    if first is None:
        return second
    if second is None:
        return first
    return first if PERMISSION_ORDER[first] >= PERMISSION_ORDER[second] else second


def weakest(first: Permission | None, second: Permission | None) -> Permission | None:
    if first is None or second is None:
        return None
    return first if PERMISSION_ORDER[first] <= PERMISSION_ORDER[second] else second


def _grants_for(buttlr: Buttlr, access: AccessContext) -> list[PermissionGrant]:
    # One branch per grant subject on purpose: this is the security boundary, and the
    # readable form is worth more here than a combined boolean expression.
    matches: list[PermissionGrant] = []
    for grant in buttlr.permissions:
        if grant.subject_type == GrantSubject.EVERYONE:  # noqa: SIM114
            matches.append(grant)
        elif grant.subject_type == GrantSubject.USER and grant.subject == access.user_id:  # noqa: SIM114
            matches.append(grant)
        elif grant.subject_type == GrantSubject.TEAM and grant.subject in access.team_ids:  # noqa: SIM114
            matches.append(grant)
        elif (
            grant.subject_type == GrantSubject.ROLE
            and access.org_role is not None
            and grant.subject == access.org_role.value
        ):
            matches.append(grant)
    return matches


def granted_permission(buttlr: Buttlr, access: AccessContext) -> Permission | None:
    """Highest permission this actor holds on this Buttlr."""
    level: Permission | None = ORG_ROLE_FLOOR.get(access.org_role) if access.org_role else None
    if access.org_role == OrgRole.OWNER:
        return Permission.ADMIN
    for grant in _grants_for(buttlr, access):
        level = strongest(level, grant.permission)
    return level


def _matches_rule(rule_tool: str, tool_name: str) -> bool:
    if rule_tool == "*":
        return True
    if fnmatch(tool_name, rule_tool):
        return True
    # Allow "github.*" style prefixes to match any github tool.
    if rule_tool.endswith("*"):
        return tool_name.startswith(rule_tool[:-1])
    # Allow a bare provider name to match its whole family.
    return tool_name.split(".", 1)[0] == rule_tool


def resolve_approval(
    policy: ApprovalPolicy,
    tool_name: str,
    risk: RiskLevel,
    settings: OrganizationSettings,
) -> tuple[ApprovalMode, str | None, tuple[str, ...]]:
    """Return (mode, matched rule, approver roles) for a tool call."""
    for rule in policy.rules:
        if _matches_rule(rule.tool, tool_name):
            return rule.mode, rule.tool, tuple(rule.approver_roles)

    if settings.require_approval_for_high_risk and RISK_ORDER[risk] >= RISK_ORDER[RiskLevel.HIGH]:
        return ApprovalMode.ASK, "organization.high_risk", ()

    if RISK_ORDER[risk] >= RISK_ORDER[policy.require_for_risk]:
        return ApprovalMode.ASK, "policy.risk_threshold", ()

    return policy.default_mode, None, ()


class PermissionEngine:
    """Stateless evaluator. Construct once, call anywhere."""

    def evaluate(
        self,
        *,
        buttlr: Buttlr,
        access: AccessContext,
        tool_name: str,
        required_permission: Permission,
        risk: RiskLevel,
        owner_access: AccessContext | None = None,
    ) -> PermissionDecision:
        granted = granted_permission(buttlr, access)

        # Attenuation: a Buttlr cannot exceed the authority of the account that created it.
        if owner_access is not None and owner_access.user_id != access.user_id:
            owner_level = granted_permission(buttlr, owner_access)
            capped = weakest(owner_level, granted)
            if capped is None:
                return PermissionDecision(
                    decision=Decision.DENY,
                    allowed=False,
                    reason=(
                        "The account that owns this Buttlr no longer has access to it, "
                        "so its authority cannot be delegated."
                    ),
                    required_permission=required_permission,
                    granted_permission=None,
                    risk=risk,
                    tool=tool_name,
                )
            granted = capped

        if granted is None or PERMISSION_ORDER[granted] < PERMISSION_ORDER[required_permission]:
            return PermissionDecision(
                decision=Decision.DENY,
                allowed=False,
                reason=(
                    f"This action needs '{required_permission.value}' permission on {buttlr.name}; "
                    f"you have {'none' if granted is None else granted.value}."
                ),
                required_permission=required_permission,
                granted_permission=granted,
                risk=risk,
                tool=tool_name,
            )

        mode, matched, approver_roles = resolve_approval(
            buttlr.approval_policy, tool_name, risk, access.settings
        )

        if mode == ApprovalMode.DENY:
            return PermissionDecision(
                decision=Decision.DENY,
                allowed=False,
                reason=f"Policy for '{matched or tool_name}' forbids this action.",
                required_permission=required_permission,
                granted_permission=granted,
                risk=risk,
                tool=tool_name,
                matched_rule=matched,
            )

        if mode == ApprovalMode.ASK:
            return PermissionDecision(
                decision=Decision.REQUEST_APPROVAL,
                allowed=False,
                reason=f"'{tool_name}' requires human approval.",
                required_permission=required_permission,
                granted_permission=granted,
                risk=risk,
                requires_approval=True,
                approver_permission=buttlr.approval_policy.approver_permission,
                approver_roles=approver_roles,
                tool=tool_name,
                matched_rule=matched,
            )

        return PermissionDecision(
            decision=Decision.ALLOW,
            allowed=True,
            reason="Allowed by policy.",
            required_permission=required_permission,
            granted_permission=granted,
            risk=risk,
            tool=tool_name,
            matched_rule=matched,
        )

    # ---- coarse-grained checks used by the HTTP layer ----------------------

    def require(
        self,
        *,
        buttlr: Buttlr,
        access: AccessContext,
        permission: Permission,
        action: str,
    ) -> None:
        granted = granted_permission(buttlr, access)
        if granted is None or PERMISSION_ORDER[granted] < PERMISSION_ORDER[permission]:
            raise PermissionDeniedError(
                f"You need '{permission.value}' permission on {buttlr.name} to {action}.",
                details={
                    "required_permission": permission.value,
                    "granted_permission": granted.value if granted else None,
                },
            )

    def can(
        self, *, buttlr: Buttlr, access: AccessContext, permission: Permission
    ) -> bool:
        granted = granted_permission(buttlr, access)
        return granted is not None and PERMISSION_ORDER[granted] >= PERMISSION_ORDER[permission]


engine = PermissionEngine()
