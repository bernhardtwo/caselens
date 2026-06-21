// Same-origin: every call goes to the Next proxy at /api/*, which forwards to the API.
export const API_BASE = "/api";

export interface IdentityUser {
  id: number;
  email: string;
  role: string;
}

export interface Tenant {
  id: number;
  name: string;
  users: IdentityUser[];
}

// The acting identity. The console sends it as headers on every API call; it is never
// part of a request body, so the model and the browser cannot smuggle a different tenant.
export interface Identity {
  tenantId: number;
  tenantName: string;
  userId: number;
  email: string;
  role: string;
}

export function toIdentity(tenant: Tenant, user: IdentityUser): Identity {
  return {
    tenantId: tenant.id,
    tenantName: tenant.name,
    userId: user.id,
    email: user.email,
    role: user.role,
  };
}

export function authHeaders(identity: Identity | null): Record<string, string> {
  if (!identity) return {};
  return {
    "X-Tenant-Id": String(identity.tenantId),
    "X-User-Id": String(identity.userId),
    "X-Role": identity.role,
  };
}

export async function fetchIdentities(): Promise<Tenant[]> {
  const response = await fetch(`${API_BASE}/dev/identities`);
  if (!response.ok) throw new Error(`/dev/identities respondió ${response.status}.`);
  const data = (await response.json()) as { tenants: Tenant[] };
  return data.tenants;
}

export interface ConfirmResult {
  ok: true;
  claim_id: number;
  from: string;
  to: string;
}

export type ConfirmOutcome =
  | { ok: true; result: ConfirmResult }
  | { ok: false; status: number; detail: string };

export async function confirmAction(
  identity: Identity,
  claimId: number,
  toStatus: string,
): Promise<ConfirmOutcome> {
  const response = await fetch(`${API_BASE}/actions/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(identity) },
    body: JSON.stringify({ claim_id: claimId, to_status: toStatus }),
  });
  if (response.ok) {
    return { ok: true, result: (await response.json()) as ConfirmResult };
  }
  let detail = `Error ${response.status}.`;
  try {
    const data = (await response.json()) as { detail?: string };
    if (data.detail) detail = data.detail;
  } catch {
    // keep the generic message
  }
  return { ok: false, status: response.status, detail };
}

export interface ClaimRow {
  id: number;
  claimant_name: string;
  product: string;
  description: string;
  status: string;
  severity: string;
  cost_cents: number | null;
  submitted_at: string;
}

export interface AuditEntry {
  id: number;
  actor_user_id: number;
  action: string;
  target_type: string;
  target_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export async function fetchClaims(identity: Identity): Promise<ClaimRow[]> {
  const response = await fetch(`${API_BASE}/claims`, { headers: authHeaders(identity) });
  if (!response.ok) throw new Error(`/claims respondió ${response.status}.`);
  return ((await response.json()) as { claims: ClaimRow[] }).claims;
}

export async function fetchAudit(identity: Identity): Promise<AuditEntry[]> {
  const response = await fetch(`${API_BASE}/audit`, { headers: authHeaders(identity) });
  if (!response.ok) throw new Error(`/audit respondió ${response.status}.`);
  return ((await response.json()) as { audit: AuditEntry[] }).audit;
}
