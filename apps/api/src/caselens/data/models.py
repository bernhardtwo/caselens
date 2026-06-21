from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class Role(StrEnum):
    AGENT = "agent"
    REVIEWER = "reviewer"
    ADMIN = "admin"


class ClaimStatus(StrEnum):
    OPEN = "open"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CLOSED = "closed"


@dataclass(frozen=True)
class TenantContext:
    """Identity and scope passed to every data call. Assumed authenticated upstream."""

    tenant_id: int
    user_id: int
    role: Role


@dataclass(frozen=True)
class Tenant:
    id: int
    name: str
    created_at: datetime


@dataclass(frozen=True)
class User:
    id: int
    tenant_id: int
    email: str
    role: Role
    created_at: datetime


@dataclass(frozen=True)
class Claim:
    id: int
    tenant_id: int
    claimant_name: str
    product: str
    description: str
    status: ClaimStatus
    severity: str
    cost_cents: int | None
    submitted_at: datetime


@dataclass(frozen=True)
class AuditEntry:
    id: int
    tenant_id: int
    actor_user_id: int
    action: str
    target_type: str
    target_id: str | None
    metadata: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class ClaimFilters:
    status: ClaimStatus | None = None
    product: str | None = None
    severity: str | None = None
