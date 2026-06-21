"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { AnswerWithCitations } from "@/components/AnswerWithCitations";
import { ConfirmationCard, type Proposal } from "@/components/ConfirmationCard";
import { IdentitySwitcher } from "@/components/IdentitySwitcher";
import { SourcesPanel } from "@/components/SourcesPanel";
import { ToolTrace, type TraceEntry } from "@/components/ToolTrace";
import { type AgentEvent, type Citation, type Source, streamAgent } from "@/lib/agentStream";
import { confirmAction, fetchIdentities, type Identity, type Tenant, toIdentity } from "@/lib/api";

interface Exchange {
  id: number;
  question: string;
  trace: TraceEntry[];
  answer: string | null;
  citations: Citation[];
  sources: Source[];
  proposals: Proposal[];
  status: "streaming" | "done" | "error";
  error?: string;
}

interface State {
  exchanges: Exchange[];
}

type Action =
  | { type: "submit"; id: number; question: string }
  | { type: "event"; event: AgentEvent }
  | { type: "done" }
  | { type: "error"; message: string }
  | {
      type: "proposal_update";
      exchangeId: number;
      proposalId: string;
      state: Proposal["state"];
      message?: string;
    };

function updateLast(state: State, fn: (exchange: Exchange) => Exchange): State {
  if (state.exchanges.length === 0) return state;
  const exchanges = state.exchanges.slice();
  exchanges[exchanges.length - 1] = fn(exchanges[exchanges.length - 1]);
  return { exchanges };
}

function updateById(state: State, id: number, fn: (exchange: Exchange) => Exchange): State {
  return { exchanges: state.exchanges.map((e) => (e.id === id ? fn(e) : e)) };
}

function closeRunning(trace: TraceEntry[], result: TraceEntry["result"]): TraceEntry[] {
  const next = trace.slice();
  for (let i = next.length - 1; i >= 0; i--) {
    if (next[i].status === "running") {
      next[i] = { ...next[i], status: "done", result };
      break;
    }
  }
  return next;
}

function applyEvent(state: State, event: AgentEvent): State {
  switch (event.type) {
    case "tool_call":
      return updateLast(state, (e) => ({
        ...e,
        trace: [...e.trace, { name: event.data.name, arguments: event.data.arguments, status: "running" }],
      }));
    case "tool_result":
      return updateLast(state, (e) => ({ ...e, trace: closeRunning(e.trace, event.data.result) }));
    case "answer":
      return updateLast(state, (e) => ({ ...e, answer: event.data.text }));
    case "citations":
      return updateLast(state, (e) => ({
        ...e,
        citations: event.data.citations,
        sources: event.data.sources,
      }));
    case "error":
      return updateLast(state, (e) => ({ ...e, status: "error", error: event.data.detail }));
    case "action_proposed":
      return updateLast(state, (e) => ({
        ...e,
        proposals: [
          ...e.proposals,
          {
            id: `${e.id}-${e.proposals.length}`,
            claimId: event.data.claim_id,
            fromStatus: event.data.from_status,
            toStatus: event.data.to_status,
            state: "pending",
          },
        ],
      }));
  }
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "submit":
      return {
        exchanges: [
          ...state.exchanges,
          {
            id: action.id,
            question: action.question,
            trace: [],
            answer: null,
            citations: [],
            sources: [],
            proposals: [],
            status: "streaming",
          },
        ],
      };
    case "event":
      return applyEvent(state, action.event);
    case "done":
      return updateLast(state, (e) => (e.status === "streaming" ? { ...e, status: "done" } : e));
    case "error":
      return updateLast(state, (e) => ({ ...e, status: "error", error: action.message }));
    case "proposal_update":
      return updateById(state, action.exchangeId, (e) => ({
        ...e,
        proposals: e.proposals.map((p) =>
          p.id === action.proposalId ? { ...p, state: action.state, message: action.message } : p,
        ),
      }));
  }
}

function Spinner() {
  return (
    <svg className="h-4 w-4 animate-spin text-indigo-500" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
      />
    </svg>
  );
}

export function Console() {
  const [state, dispatch] = useReducer(reducer, { exchanges: [] });
  const [input, setInput] = useState("");
  const [activeSources, setActiveSources] = useState<number[] | null>(null);
  const [identities, setIdentities] = useState<Tenant[]>([]);
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [identitiesError, setIdentitiesError] = useState<string | null>(null);
  const idRef = useRef(0);
  const bottomRef = useRef<HTMLDivElement>(null);

  const busy = state.exchanges.some((e) => e.status === "streaming");

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [state.exchanges]);

  useEffect(() => {
    fetchIdentities()
      .then((tenants) => {
        setIdentities(tenants);
        const first = tenants[0];
        if (first && first.users.length > 0) setIdentity(toIdentity(first, first.users[0]));
      })
      .catch((err) =>
        setIdentitiesError(err instanceof Error ? err.message : "No se pudieron cargar las identidades."),
      );
  }, []);

  const send = useCallback(async () => {
    const message = input.trim();
    if (!message || busy || !identity) return;
    const id = idRef.current + 1;
    idRef.current = id;
    dispatch({ type: "submit", id, question: message });
    setInput("");
    setActiveSources(null);
    try {
      await streamAgent(message, identity, (event) => dispatch({ type: "event", event }));
      dispatch({ type: "done" });
    } catch (err) {
      dispatch({ type: "error", message: err instanceof Error ? err.message : "Error de conexión." });
    }
  }, [input, busy, identity]);

  const confirm = useCallback(
    async (exchangeId: number, proposal: Proposal) => {
      if (!identity) return;
      dispatch({ type: "proposal_update", exchangeId, proposalId: proposal.id, state: "confirming" });
      const outcome = await confirmAction(identity, proposal.claimId, proposal.toStatus);
      if (outcome.ok) {
        dispatch({
          type: "proposal_update",
          exchangeId,
          proposalId: proposal.id,
          state: "committed",
        });
      } else {
        dispatch({
          type: "proposal_update",
          exchangeId,
          proposalId: proposal.id,
          state: outcome.status === 403 ? "denied" : "error",
          message: outcome.detail,
        });
      }
    },
    [identity],
  );

  const dismiss = useCallback((exchangeId: number, proposalId: string) => {
    dispatch({ type: "proposal_update", exchangeId, proposalId, state: "dismissed" });
  }, []);

  const focused = [...state.exchanges].reverse().find((e) => e.sources.length > 0) ?? null;

  return (
    <div className="flex h-screen flex-col bg-slate-50">
      <header className="flex items-center justify-between gap-3 border-b border-slate-200 bg-white px-6 py-3">
        <div className="flex items-center gap-3">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-indigo-600 text-sm font-bold text-white">
            C
          </span>
          <div>
            <h1 className="text-sm font-semibold leading-tight text-slate-800">CaseLens</h1>
            <p className="text-xs leading-tight text-slate-400">Consola del agente</p>
          </div>
        </div>
        {identitiesError ? (
          <span className="text-xs text-red-600">{identitiesError}</span>
        ) : (
          <IdentitySwitcher identities={identities} identity={identity} onChange={setIdentity} />
        )}
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-[1fr_340px]">
        <section className="flex min-h-0 flex-col">
          <div className="flex-1 overflow-y-auto px-6 py-6">
            <div className="mx-auto flex max-w-2xl flex-col gap-8">
              {state.exchanges.length === 0 && (
                <div className="mt-16 text-center text-slate-400">
                  <p className="text-base font-medium text-slate-500">Pregúntale al agente</p>
                  <p className="mt-1 text-sm">
                    Verás cómo razona con sus herramientas y cita sus fuentes en vivo.
                  </p>
                </div>
              )}

              {state.exchanges.map((exchange) => (
                <article key={exchange.id} className="flex flex-col gap-3">
                  <div className="self-end max-w-[80%] rounded-2xl rounded-br-sm bg-indigo-600 px-4 py-2 text-sm text-white">
                    {exchange.question}
                  </div>

                  {exchange.trace.length > 0 && <ToolTrace entries={exchange.trace} />}

                  {exchange.answer !== null && (
                    <AnswerWithCitations
                      text={exchange.answer}
                      citations={exchange.citations}
                      activeSources={exchange.id === focused?.id ? activeSources : null}
                      onHover={exchange.id === focused?.id ? setActiveSources : undefined}
                    />
                  )}

                  {exchange.proposals.map((proposal) => (
                    <ConfirmationCard
                      key={proposal.id}
                      proposal={proposal}
                      onConfirm={() => void confirm(exchange.id, proposal)}
                      onDismiss={() => dismiss(exchange.id, proposal.id)}
                    />
                  ))}

                  {exchange.status === "streaming" && exchange.answer === null && (
                    <div className="flex items-center gap-2 text-sm text-slate-400">
                      <Spinner />
                      El agente está trabajando…
                    </div>
                  )}

                  {exchange.status === "error" && (
                    <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                      {exchange.error}
                    </p>
                  )}
                </article>
              ))}
              <div ref={bottomRef} />
            </div>
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              void send();
            }}
            className="border-t border-slate-200 bg-white px-6 py-4"
          >
            <div className="mx-auto flex max-w-2xl items-center gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Escribe tu consulta…"
                disabled={busy || !identity}
                className="flex-1 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm text-slate-800 outline-none placeholder:text-slate-400 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50"
              />
              <button
                type="submit"
                disabled={busy || !identity || input.trim().length === 0}
                className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-600 text-white transition-colors hover:bg-indigo-700 disabled:bg-slate-200 disabled:text-slate-400"
                aria-label="Enviar"
              >
                {busy ? (
                  <Spinner />
                ) : (
                  <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </button>
            </div>
          </form>
        </section>

        <aside className="min-h-0 overflow-y-auto border-l border-slate-200 bg-white">
          <SourcesPanel
            sources={focused?.sources ?? []}
            activeSources={activeSources}
            onHover={setActiveSources}
          />
        </aside>
      </div>
    </div>
  );
}
