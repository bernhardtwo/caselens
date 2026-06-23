import json
from collections.abc import Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import cohere
import psycopg

from caselens.clients import get_cohere_client
from caselens.config.settings import Settings, get_settings
from caselens.data.models import TenantContext
from caselens.data.pool import db_connection
from caselens.rag.answer import citations as parse_citations
from caselens.rag.answer import document as to_document
from caselens.rag.models import Citation, RetrievedChunk
from caselens.security.audit import audit_isolated

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


class EventType(StrEnum):
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ANSWER = "answer"
    CITATIONS = "citations"
    ACTION_PROPOSED = "action_proposed"


@dataclass(frozen=True)
class AgentEvent:
    type: EventType
    data: dict[str, Any]


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


def run_agent_events(
    ctx: TenantContext,
    message: str,
    *,
    interactive: bool = False,
    co: cohere.ClientV2 | None = None,
    conn: psycopg.Connection | None = None,
    settings: Settings | None = None,
    tools: list[AgentTool] | None = None,
    max_iterations: int | None = None,
) -> Iterator[AgentEvent]:
    """The agent loop as a stream of typed events. interactive=True makes mutations
    propose (action_proposed) instead of committing; autonomous runs execute directly."""
    settings = settings or get_settings()
    max_iterations = max_iterations or settings.agent_max_iterations
    co = co or get_cohere_client(settings)
    own_conn = conn is None
    stack = ExitStack()
    if own_conn:
        conn = stack.enter_context(db_connection())
    try:
        tools = (
            tools
            if tools is not None
            else build_tools(ctx, conn=conn, co=co, settings=settings, interactive=interactive)
        )
        by_name = {tool.name: tool for tool in tools}
        schemas = [tool.schema() for tool in tools]
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ]
        retrieved: list[RetrievedChunk] = []

        resp = co.chat(
            model=settings.chat_model,
            messages=messages,
            tools=schemas,
            citation_options={"mode": "fast"},
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
                yield AgentEvent(EventType.TOOL_CALL, {"name": name, "arguments": args})
                tool = by_name.get(name)
                if tool is None:
                    outcome = ToolOutcome(result={"error": f"unknown tool: {name}"})
                else:
                    try:
                        outcome = tool.run(**args)
                    except Exception as exc:  # report the failure to the model, keep the loop alive
                        # Contain it: roll back the failed op's aborted transaction so the shared
                        # connection stays usable for the rest of the loop and the iteration commit.
                        conn.rollback()
                        outcome = ToolOutcome(result={"error": str(exc)})
                # rag_search passages are returned as tool-result documents with explicit
                # ids, the idiomatic Cohere tool-use grounding pattern, so the final answer
                # carries citations referencing those ids (ADR-0007).
                if outcome.passages:
                    base = len(retrieved)
                    content: str | list[dict[str, Any]] = [
                        {"type": "document", "document": to_document(base + offset, chunk)}
                        for offset, chunk in enumerate(outcome.passages)
                    ]
                    retrieved.extend(outcome.passages)
                else:
                    content = json.dumps(outcome.result, ensure_ascii=False)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
                # Audit on a dedicated connection so the record is written even if the tool
                # failed and poisoned `conn`; it never depends on the tool's transaction state.
                audit_isolated(
                    ctx,
                    "agent.tool_call",
                    "tool",
                    name,
                    {"ok": "error" not in outcome.result, "denied": outcome.denied},
                )
                yield AgentEvent(
                    EventType.TOOL_RESULT,
                    {"name": name, "arguments": args, "result": outcome.result},
                )
                if outcome.proposed is not None:
                    yield AgentEvent(EventType.ACTION_PROPOSED, outcome.proposed)
            conn.commit()
            resp = co.chat(
                model=settings.chat_model,
                messages=messages,
                tools=schemas,
                citation_options={"mode": "fast"},
                temperature=settings.agent_temperature,
            )

        if resp.message.tool_calls:  # hit the iteration cap; force a final grounded answer
            resp = co.chat(
                model=settings.chat_model,
                messages=messages,
                citation_options={"mode": "fast"},
                temperature=settings.agent_temperature,
            )
        answer_text = resp.message.content[0].text if resp.message.content else ""
        yield AgentEvent(EventType.ANSWER, {"text": answer_text})
        if retrieved:
            # Native citations from the final turn: offsets map to answer_text (ADR-0007).
            citations = parse_citations(resp.message.citations)
            yield AgentEvent(EventType.CITATIONS, {"citations": citations, "sources": retrieved})
    finally:
        stack.close()


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
    """Non-streaming agent run: collects the autonomous event stream into an AgentResult."""
    answer_text = ""
    citations: list[Citation] = []
    sources: list[RetrievedChunk] = []
    trace: list[ToolCallRecord] = []
    actions: list[dict[str, Any]] = []
    for event in run_agent_events(
        ctx,
        message,
        interactive=False,
        co=co,
        conn=conn,
        settings=settings,
        tools=tools,
        max_iterations=max_iterations,
    ):
        if event.type == EventType.TOOL_RESULT:
            result = event.data["result"]
            trace.append(
                ToolCallRecord(
                    name=event.data["name"], arguments=event.data["arguments"], result=result
                )
            )
            if result.get("action") == "update_claim_status" and result.get("ok"):
                actions.append(
                    {
                        "action": "update_claim_status",
                        "claim_id": result["claim_id"],
                        "from": result["from"],
                        "to": result["to"],
                    }
                )
        elif event.type == EventType.ANSWER:
            answer_text = event.data["text"]
        elif event.type == EventType.CITATIONS:
            citations = event.data["citations"]
            sources = event.data["sources"]
    return AgentResult(
        answer=answer_text,
        citations=citations,
        sources=sources,
        tool_trace=trace,
        actions_taken=actions,
    )
