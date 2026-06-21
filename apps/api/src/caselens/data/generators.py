"""Synthetic multi-tenant claims generator (spec-0002).

IP-clean: tenant, claimant, and product names are fabricated and mirror the demo
corpus theme (solar, batteries, EV chargers). Seedable for reproducible local data.

    uv run python -m caselens.data.generators --reset --tenants 3 --claims 12
"""

import argparse
import random
from dataclasses import dataclass

import psycopg

from .db import apply_schema, connect
from .models import ClaimStatus, Role

_TENANT_NAMES = [
    "Acme Insurance",
    "Globex Mutual",
    "Initech Warranty",
    "Umbra Energy Cover",
    "Stark Solar Care",
]
_FIRST_NAMES = ["Ana", "Luis", "Mara", "Noah", "Iris", "Theo", "Vera", "Omar", "Lena", "Hugo"]
_LAST_NAMES = ["Reyes", "Kane", "Soto", "Vance", "Park", "Adler", "Bauer", "Cruz", "Mora", "Nilo"]
_PRODUCTS = [
    "Solar Inverter X1",
    "Home Battery 10kWh",
    "EV Charger Pro",
    "Solar Inverter S2",
    "Home Battery 5kWh",
]
_ISSUES = [
    "{product} no enciende tras una caída de red.",
    "{product} reporta error de temperatura y se apaga.",
    "{product} pierde capacidad por debajo de lo garantizado.",
    "{product} no se comunica con la app móvil.",
    "{product} presenta ruido anómalo durante la carga.",
]
_SEVERITIES = ["low", "medium", "high", "critical"]
_STATUSES = [ClaimStatus.OPEN, ClaimStatus.OPEN, ClaimStatus.IN_REVIEW, ClaimStatus.APPROVED]


@dataclass(frozen=True)
class DraftUser:
    email: str
    role: Role


@dataclass(frozen=True)
class DraftClaim:
    claimant_name: str
    product: str
    description: str
    status: str
    severity: str
    cost_cents: int | None


@dataclass(frozen=True)
class DraftTenant:
    name: str
    users: list[DraftUser]
    claims: list[DraftClaim]


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")


def _role_for(index: int) -> Role:
    return {0: Role.ADMIN, 1: Role.REVIEWER}.get(index, Role.AGENT)


def _draft_claim(rng: random.Random) -> DraftClaim:
    product = rng.choice(_PRODUCTS)
    # cost stays an integer number of cents (ADR-0005); ~1 in 5 has no cost yet.
    cost = None if rng.random() < 0.2 else rng.randrange(5_000, 500_000)
    return DraftClaim(
        claimant_name=f"{rng.choice(_FIRST_NAMES)} {rng.choice(_LAST_NAMES)}",
        product=product,
        description=rng.choice(_ISSUES).format(product=product),
        status=rng.choice(_STATUSES).value,
        severity=rng.choice(_SEVERITIES),
        cost_cents=cost,
    )


def generate(
    n_tenants: int, users_per_tenant: int, claims_per_tenant: int, *, seed: int = 0
) -> list[DraftTenant]:
    rng = random.Random(seed)
    tenants: list[DraftTenant] = []
    for t in range(n_tenants):
        base = _TENANT_NAMES[t % len(_TENANT_NAMES)]
        name = base if t < len(_TENANT_NAMES) else f"{base} {t // len(_TENANT_NAMES) + 1}"
        users = [
            DraftUser(email=f"user{u}@{_slug(name)}.example", role=_role_for(u))
            for u in range(users_per_tenant)
        ]
        claims = [_draft_claim(rng) for _ in range(claims_per_tenant)]
        tenants.append(DraftTenant(name=name, users=users, claims=claims))
    return tenants


def seed(conn: psycopg.Connection, drafts: list[DraftTenant]) -> dict[str, int]:
    counts = {"tenants": 0, "users": 0, "claims": 0}
    with conn.cursor() as cur:
        for tenant in drafts:
            cur.execute("INSERT INTO tenants (name) VALUES (%s) RETURNING id", (tenant.name,))
            tenant_id = cur.fetchone()[0]
            counts["tenants"] += 1
            for user in tenant.users:
                cur.execute(
                    "INSERT INTO users (tenant_id, email, role) VALUES (%s, %s, %s)",
                    (tenant_id, user.email, user.role.value),
                )
                counts["users"] += 1
            for claim in tenant.claims:
                cur.execute(
                    "INSERT INTO claims (tenant_id, claimant_name, product, description, "
                    "status, severity, cost_cents) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        tenant_id,
                        claim.claimant_name,
                        claim.product,
                        claim.description,
                        claim.status,
                        claim.severity,
                        claim.cost_cents,
                    ),
                )
                counts["claims"] += 1
    conn.commit()
    return counts


def _truncate(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE audit_log, claims, users, tenants RESTART IDENTITY CASCADE")
    conn.commit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="caselens-seed", description="Siembra claims sintéticos multi-tenant (spec-0002)."
    )
    parser.add_argument("--tenants", type=int, default=3)
    parser.add_argument("--users", type=int, default=3)
    parser.add_argument("--claims", type=int, default=12)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--reset", action="store_true", help="Vacía las tablas del data layer antes de sembrar."
    )
    args = parser.parse_args(argv)
    drafts = generate(args.tenants, args.users, args.claims, seed=args.seed)
    with connect() as conn:
        apply_schema(conn)
        if args.reset:
            _truncate(conn)
        counts = seed(conn, drafts)
    print(
        f"Sembrados {counts['tenants']} tenants, "
        f"{counts['users']} users, {counts['claims']} claims."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
