export interface Proposal {
  id: string;
  claimId: number;
  fromStatus: string;
  toStatus: string;
  state: "pending" | "confirming" | "committed" | "denied" | "error" | "dismissed";
  message?: string;
}

const STATUS_STYLES: Record<string, string> = {
  open: "bg-slate-100 text-slate-700",
  in_review: "bg-amber-100 text-amber-700",
  approved: "bg-emerald-100 text-emerald-700",
  rejected: "bg-red-100 text-red-700",
  closed: "bg-slate-200 text-slate-600",
};

function StatusChip({ status }: { status: string }) {
  return (
    <span
      className={`rounded px-1.5 py-0.5 font-mono text-xs ${STATUS_STYLES[status] ?? "bg-slate-100 text-slate-700"}`}
    >
      {status}
    </span>
  );
}

function Change({ proposal }: { proposal: Proposal }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="font-medium">Claim #{proposal.claimId}</span>
      <StatusChip status={proposal.fromStatus} />
      <span className="text-slate-400">→</span>
      <StatusChip status={proposal.toStatus} />
    </span>
  );
}

export function ConfirmationCard({
  proposal,
  onConfirm,
  onDismiss,
}: {
  proposal: Proposal;
  onConfirm: () => void;
  onDismiss: () => void;
}) {
  if (proposal.state === "committed") {
    return (
      <div className="rounded-lg border border-emerald-300 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
        <p className="font-semibold">Cambio aplicado y auditado</p>
        <p className="mt-1">
          <Change proposal={proposal} />
        </p>
      </div>
    );
  }
  if (proposal.state === "denied") {
    return (
      <div className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
        <p className="font-semibold">Acción rechazada (RBAC)</p>
        <p className="mt-1">
          {proposal.message ?? "Tu rol no puede confirmar esta acción."} El intento quedó
          registrado en el audit.
        </p>
        <p className="mt-1 text-red-700">
          <Change proposal={proposal} />
        </p>
      </div>
    );
  }
  if (proposal.state === "error") {
    return (
      <div className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
        <p className="font-semibold">No se pudo confirmar</p>
        <p className="mt-1">{proposal.message}</p>
      </div>
    );
  }
  if (proposal.state === "dismissed") {
    return (
      <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-2 text-sm text-slate-400">
        Propuesta descartada. <Change proposal={proposal} />
      </div>
    );
  }

  const confirming = proposal.state === "confirming";
  return (
    <div className="rounded-xl border-2 border-amber-400 bg-amber-50 px-4 py-3 shadow-sm">
      <div className="flex items-center gap-2 text-amber-900">
        <svg className="h-5 w-5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path
            d="M12 9v4m0 4h.01M10.3 3.86l-8.5 14.7A1.5 1.5 0 003.1 21h17.8a1.5 1.5 0 001.3-2.44l-8.5-14.7a1.5 1.5 0 00-2.6 0z"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <p className="text-sm font-semibold">El agente propone un cambio. Requiere tu confirmación.</p>
      </div>
      <p className="mt-2 text-sm text-amber-950">
        <Change proposal={proposal} />
      </p>
      <div className="mt-3 flex gap-2">
        <button
          onClick={onConfirm}
          disabled={confirming}
          className="rounded-lg bg-amber-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-amber-700 disabled:bg-amber-300"
        >
          {confirming ? "Confirmando…" : "Confirmar y aplicar"}
        </button>
        <button
          onClick={onDismiss}
          disabled={confirming}
          className="rounded-lg px-3 py-1.5 text-sm font-medium text-amber-800 transition-colors hover:bg-amber-100 disabled:opacity-50"
        >
          Descartar
        </button>
      </div>
    </div>
  );
}
