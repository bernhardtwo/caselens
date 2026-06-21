import type { ClaimRow } from "@/lib/api";

const STATUS_STYLES: Record<string, string> = {
  open: "bg-slate-100 text-slate-700",
  in_review: "bg-amber-100 text-amber-700",
  approved: "bg-emerald-100 text-emerald-700",
  rejected: "bg-red-100 text-red-700",
  closed: "bg-slate-200 text-slate-600",
};

export function ClaimsPanel({ claims }: { claims: ClaimRow[] }) {
  return (
    <div className="p-4">
      <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        Reclamos
      </h2>
      {claims.length === 0 ? (
        <p className="text-sm text-slate-400">Sin reclamos para este tenant.</p>
      ) : (
        <ol className="space-y-2">
          {claims.map((claim) => (
            <li key={claim.id} className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-medium text-slate-800">
                  #{claim.id} · {claim.product}
                </span>
                <span
                  className={`shrink-0 rounded px-1.5 py-0.5 font-mono text-xs ${
                    STATUS_STYLES[claim.status] ?? "bg-slate-100 text-slate-700"
                  }`}
                >
                  {claim.status}
                </span>
              </div>
              <p className="mt-1 text-xs text-slate-500">
                {claim.claimant_name} · {claim.severity}
              </p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
