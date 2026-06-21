from caselens.data.models import Role, TenantContext

# Action labels double as audit action strings.
READ = "claim.read"
UPDATE_STATUS = "claim.update_status"

PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.AGENT: frozenset({READ}),
    Role.REVIEWER: frozenset({READ, UPDATE_STATUS}),
    Role.ADMIN: frozenset({READ, UPDATE_STATUS}),
}


class PermissionDeniedError(RuntimeError):
    """Raised when a role lacks permission for an action."""


def can(ctx: TenantContext, action: str) -> bool:
    return action in PERMISSIONS.get(ctx.role, frozenset())


def require_role(ctx: TenantContext, action: str) -> None:
    if not can(ctx, action):
        raise PermissionDeniedError(f"El rol {ctx.role.value} no puede ejecutar {action}.")
