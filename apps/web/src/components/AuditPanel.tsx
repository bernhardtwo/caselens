import type { AuditEntry } from "@/lib/api";

function isDenied(action: string): boolean {
  return action.includes("denied");
}

export function AuditPanel({ entries }: { entries: AuditEntry[] }) {
  return (
    <div className="p-4">
      <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        Auditoría
      </h2>
      {entries.length === 0 ? (
        <p className="text-sm text-slate-400">Sin entradas para este tenant.</p>
      ) : (
        <ol className="space-y-2">
          {entries.map((entry) => (
            <li key={entry.id} className="rounded-lg border border-slate-200 bg-white p-2.5 text-xs">
              <div className="flex items-center justify-between gap-2">
                <code
                  className={`rounded px-1.5 py-0.5 font-mono ${
                    isDenied(entry.action) ? "bg-red-100 text-red-700" : "bg-slate-100 text-slate-600"
                  }`}
                >
                  {entry.action}
                </code>
                <span className="shrink-0 text-slate-400">
                  {new Date(entry.created_at).toLocaleTimeString()}
                </span>
              </div>
              <p className="mt-1 text-slate-500">
                {entry.target_type}
                {entry.target_id ? ` #${entry.target_id}` : ""} · user {entry.actor_user_id}
              </p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
