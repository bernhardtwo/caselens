"""Agent eval (spec-0003): tool selection, scoping, RBAC, and citations.

Run from the repo root with CO_API_KEY set, the corpus ingested, and the data layer seeded:

    uv run --project apps/api caselens-rag ingest
    uv run --project apps/api caselens-seed --reset
    uv run --project apps/api python eval/run_agent_eval.py [--sleep 6.5]

Not wired into CI (ADR-0006): it needs a live key, an ingested corpus, and seeded claims.
"""

import argparse
import json
import time
from pathlib import Path
from typing import Any

from caselens.agent.loop import AgentResult, run_agent
from caselens.data.db import connect
from caselens.data.models import Role, TenantContext

_GOLDEN = Path(__file__).parent / "golden" / "agent.jsonl"


def _load_cases() -> list[dict[str, Any]]:
    with _GOLDEN.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _resolve_fixtures(conn) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM tenants ORDER BY id LIMIT 2")
        tenants = [row[0] for row in cur.fetchall()]
        if len(tenants) < 2:
            raise SystemExit("Faltan tenants. Corre caselens-seed --reset primero.")
        tenant_a, tenant_b = tenants[0], tenants[1]
        cur.execute("SELECT id FROM users WHERE tenant_id = %s ORDER BY id LIMIT 1", (tenant_a,))
        user_a = cur.fetchone()[0]
        cur.execute(
            "SELECT id FROM claims WHERE tenant_id = %s AND status = 'open' ORDER BY id LIMIT 1",
            (tenant_a,),
        )
        open_claim = cur.fetchone()
        cur.execute("SELECT id FROM claims WHERE tenant_id = %s ORDER BY id LIMIT 1", (tenant_b,))
        other_claim = cur.fetchone()
        cur.execute("SELECT id FROM claims WHERE tenant_id = %s", (tenant_a,))
        own_claim_ids = {row[0] for row in cur.fetchall()}
    if open_claim is None or other_claim is None:
        raise SystemExit("Faltan claims OPEN del tenant A o claims del tenant B. Re-siembra.")
    return {
        "tenant_a": tenant_a,
        "user_a": user_a,
        "own_claim": open_claim[0],
        "other_claim": other_claim[0],
        "own_claim_ids": own_claim_ids,
    }


def _check(case: dict[str, Any], result: AgentResult, fixtures: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    names = [record.name for record in result.tool_trace]
    if case.get("expect_tool") and case["expect_tool"] not in names:
        failures.append(f"expected tool {case['expect_tool']!r}, saw {names}")
    if case.get("expect_citation") and not result.citations:
        failures.append("expected at least one citation")
    if case.get("expect_action") and not result.actions_taken:
        failures.append("expected a mutation in actions_taken")
    if case.get("expect_denied"):
        denied = any(
            r.name == "update_claim_status" and r.result.get("denied") for r in result.tool_trace
        )
        if not denied:
            failures.append("expected an RBAC-denied update")
    if case.get("expect_scoped"):
        returned = {
            claim["id"]
            for record in result.tool_trace
            if record.name == "query_claims"
            for claim in record.result.get("claims", [])
        }
        if not returned or not returned <= fixtures["own_claim_ids"]:
            failures.append(f"claims not scoped to tenant: {returned}")
    if case.get("expect_empty"):
        leaked = any(
            r.name == "get_claim" and r.result.get("claim") is not None for r in result.tool_trace
        )
        if leaked:
            failures.append("cross-tenant claim was returned")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-eval")
    parser.add_argument(
        "--sleep",
        type=float,
        default=6.5,
        help="Seconds between scenarios to respect Cohere's trial limit (10/min per endpoint).",
    )
    args = parser.parse_args(argv)

    cases = _load_cases()
    passed = 0
    with connect() as conn:
        fixtures = _resolve_fixtures(conn)
        for index, case in enumerate(cases):
            if index:
                time.sleep(args.sleep)
            message = case["message"].format(
                own_claim=fixtures["own_claim"], other_claim=fixtures["other_claim"]
            )
            ctx = TenantContext(fixtures["tenant_a"], fixtures["user_a"], Role(case["role"]))
            result = run_agent(ctx, message, conn=conn)
            failures = _check(case, result, fixtures)
            status = "PASS" if not failures else "FAIL"
            passed += not failures
            print(f"[{status}] {case['id']}: tools={[r.name for r in result.tool_trace]}")
            for failure in failures:
                print(f"        - {failure}")

    total = len(cases)
    print(f"\n{passed}/{total} escenarios en verde.")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
