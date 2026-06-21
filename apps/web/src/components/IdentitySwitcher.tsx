import { type Identity, type Tenant, toIdentity } from "@/lib/api";

const ROLE_STYLES: Record<string, string> = {
  admin: "bg-indigo-100 text-indigo-700",
  reviewer: "bg-emerald-100 text-emerald-700",
  agent: "bg-amber-100 text-amber-700",
};

export function roleBadge(role: string): string {
  return ROLE_STYLES[role] ?? "bg-slate-100 text-slate-600";
}

export function IdentitySwitcher({
  identities,
  identity,
  onChange,
}: {
  identities: Tenant[];
  identity: Identity | null;
  onChange: (identity: Identity) => void;
}) {
  if (identities.length === 0) {
    return <span className="text-xs text-slate-400">Cargando identidades…</span>;
  }
  const tenant = identities.find((t) => t.id === identity?.tenantId) ?? identities[0];

  const selectTenant = (tenantId: number) => {
    const next = identities.find((t) => t.id === tenantId);
    if (next && next.users.length > 0) onChange(toIdentity(next, next.users[0]));
  };
  const selectUser = (userId: number) => {
    const user = tenant.users.find((u) => u.id === userId);
    if (user) onChange(toIdentity(tenant, user));
  };

  return (
    <div className="flex items-center gap-2">
      <span className="hidden text-xs font-medium text-slate-400 sm:inline">Acting as</span>
      <select
        value={tenant.id}
        onChange={(e) => selectTenant(Number(e.target.value))}
        aria-label="Tenant"
        className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-700 outline-none focus:border-indigo-500"
      >
        {identities.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name}
          </option>
        ))}
      </select>
      <select
        value={identity?.userId ?? tenant.users[0]?.id}
        onChange={(e) => selectUser(Number(e.target.value))}
        aria-label="Usuario"
        className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-700 outline-none focus:border-indigo-500"
      >
        {tenant.users.map((u) => (
          <option key={u.id} value={u.id}>
            {u.email}
          </option>
        ))}
      </select>
      {identity && (
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-semibold capitalize ${roleBadge(identity.role)}`}
        >
          {identity.role}
        </span>
      )}
    </div>
  );
}
