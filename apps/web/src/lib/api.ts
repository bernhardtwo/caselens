export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
