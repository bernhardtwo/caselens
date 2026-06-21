import json
from dataclasses import dataclass
from typing import Any

import cohere
import psycopg

from caselens.clients import get_cohere_client
from caselens.config.settings import Settings, get_settings
from caselens.data.db import connect
from caselens.data.models import TenantContext
from caselens.rag.models import Citation, GroundedAnswer, RetrievedChunk
from caselens.security.audit import audit

from .tools import AgentTool, ToolOutcome, build_tools

_SYSTEM_PROMPT = (
    "You are CaseLens, an assistant for warranty and insurance claims. You operate strictly "
    "within one tenant's context, which is fixed by the system; you cannot choose or change it.\n"
    "- Use rag_search for policy, coverage, exclusion, or procedure questions, and ground your "
    "answer in its passages.\n"
    "- Use query_claims or get_claim to read claims; you only ever see the current tenant's data.\n"
    "- Use update_claim_status to change a status; it is permission- and transition-checked.\n"
    "- Never invent claim data or policy. If a tool returns nothing, say so plainly.\n"
    "- Answer in the user's language, concisely."
)


@dataclass(frozen=True)
class ToolCallRecord:
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any]


@dataclass(frozen=True)
class AgentResult:
    answer: str
    citations: list[Citation]
    sources: list[RetrievedChunk]
    tool_trace: list[ToolCallRecord]
    actions_taken: list[dict[str, Any]]


def _aggregate(grounded: list[GroundedAnswer]) -> tuple[list[RetrievedChunk], list[Citation]]:
    """Merge sources and citations across rag_search calls, re-basing citation source indices."""
    sources: list[RetrievedChunk] = []
    citations: list[Citation] = []
    for item in grounded:
        base = len(sources)
        sources.extend(item.sources)
        for citation in item.citations:
            remapped = []
            for sid in citation.sources:
                digits = "".join(ch for ch in sid if ch.isdigit())
                remapped.append(str(base + int(digits)) if digits else sid)
            citations.append(
                Citation(
                    start=citation.start,
                    end=citation.end,
                    text=citation.text,
                    sources=remapped,
                )
            )
    return sources, citations


def run_agent(
    ctx: TenantContext,
    message: str,
    *,
    co: cohere.ClientV2 | None = None,
    conn: psycopg.Connection | None = None,
    settings: Settings | None = None,
    tools: list[AgentTool] | None = None,
    max_iterations: int | None = None,
) -> AgentResult:
    settings = settings or get_settings()
    max_iterations = max_iterations or settings.agent_max_iterations
    co = co or get_cohere_client(settings)
    own_conn = conn is None
    conn = conn or connect(settings)
    try:
        tools = (
            tools if tools is not None else build_tools(ctx, conn=conn, co=co, settings=settings)
        )
        by_name = {tool.name: tool for tool in tools}
        schemas = [tool.schema() for tool in tools]
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ]
        trace: list[ToolCallRecord] = []
        actions: list[dict[str, Any]] = []
        grounded: list[GroundedAnswer] = []

        resp = co.chat(
            model=settings.chat_model,
            messages=messages,
            tools=schemas,
            temperature=settings.agent_temperature,
        )
        for _ in range(max_iterations):
            tool_calls = resp.message.tool_calls
            if not tool_calls:
                break
            messages.append(
                {"role": "assistant", "tool_calls": tool_calls, "tool_plan": resp.message.tool_plan}
            )
            for call in tool_calls:
                name = call.function.name
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool = by_name.get(name)
                if tool is None:
                    outcome = ToolOutcome(result={"error": f"unknown tool: {name}"})
                else:
                    try:
                        outcome = tool.run(**args)
                    except Exception as exc:  # report the failure to the model, keep the loop alive
                        outcome = ToolOutcome(result={"error": str(exc)})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(outcome.result, ensure_ascii=False),
                    }
                )
                trace.append(ToolCallRecord(name=name, arguments=args, result=outcome.result))
                if outcome.grounded is not None:
                    grounded.append(outcome.grounded)
                if outcome.action is not None:
                    actions.append(outcome.action)
                audit(
                    ctx,
                    "agent.tool_call",
                    "tool",
                    name,
                    {"ok": "error" not in outcome.result, "denied": outcome.denied},
                    conn=conn,
                )
            conn.commit()
            resp = co.chat(
                model=settings.chat_model,
                messages=messages,
                tools=schemas,
                temperature=settings.agent_temperature,
            )

        if resp.message.tool_calls:  # hit the iteration cap; force a final text answer
            resp = co.chat(
                model=settings.chat_model,
                messages=messages,
                temperature=settings.agent_temperature,
            )
        answer_text = resp.message.content[0].text if resp.message.content else ""
        sources, citations = _aggregate(grounded)
        return AgentResult(
            answer=answer_text,
            citations=citations,
            sources=sources,
            tool_trace=trace,
            actions_taken=actions,
        )
    finally:
        if own_conn:
            conn.close()
