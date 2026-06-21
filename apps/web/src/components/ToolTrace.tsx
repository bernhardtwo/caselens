import type { ToolResult } from "@/lib/agentStream";

export interface TraceEntry {
  name: string;
  arguments: Record<string, unknown>;
  status: "running" | "done";
  result?: ToolResult;
}

function formatArgs(args: Record<string, unknown>): string {
  return Object.values(args)
    .map((value) => {
      if (typeof value === "string") {
        return value.length > 36 ? `"${value.slice(0, 36)}…"` : `"${value}"`;
      }
      return String(value);
    })
    .join(", ");
}

function summarize(entry: TraceEntry): string {
  if (entry.status === "running") return "…";
  const result = entry.result ?? {};
  if (Array.isArray(result.passages)) return `${result.passages.length} pasajes`;
  if (typeof result.count === "number") {
    return `${result.count} ${entry.name === "rag_search" ? "pasajes" : "resultados"}`;
  }
  if ("claim" in result) return result.claim ? "1 reclamo" : "sin resultados";
  if (result.proposed) return "cambio propuesto";
  if (typeof result.ok === "boolean") {
    return result.ok ? "ok" : typeof result.reason === "string" ? result.reason : "rechazado";
  }
  return "listo";
}

function Dot({ running }: { running: boolean }) {
  if (running) {
    return (
      <span className="relative mt-1.5 flex h-2.5 w-2.5">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-75" />
        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-indigo-500" />
      </span>
    );
  }
  return <span className="mt-1.5 flex h-2.5 w-2.5 rounded-full bg-emerald-500" />;
}

export function ToolTrace({ entries }: { entries: TraceEntry[] }) {
  if (entries.length === 0) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white/70 p-3">
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        Traza de herramientas
      </p>
      <ol className="space-y-2">
        {entries.map((entry, index) => (
          <li key={`${entry.name}-${index}`} className="flex items-start gap-3">
            <Dot running={entry.status === "running"} />
            <p className="text-sm leading-5">
              <code className="font-mono font-medium text-indigo-700">
                {entry.name}
                <span className="text-slate-400">({formatArgs(entry.arguments)})</span>
              </code>
              <span className="mx-1.5 text-slate-300">→</span>
              <span className={entry.status === "running" ? "text-slate-400" : "text-slate-600"}>
                {summarize(entry)}
              </span>
            </p>
          </li>
        ))}
      </ol>
    </div>
  );
}
