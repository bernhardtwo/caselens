import { type NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Same-origin proxy to the API. The browser only ever calls /api/* on the web origin,
// so there is no CORS and no API URL baked into the build. The upstream host is a
// server-side runtime env (API_INTERNAL_URL): localhost:8000 in dev, the api service in prod.
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

async function proxy(request: NextRequest, segments: string[]): Promise<Response> {
  const target = `${API_INTERNAL_URL}/${segments.join("/")}${request.nextUrl.search}`;

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("content-length");
  headers.delete("accept-encoding"); // keep the upstream response identity-encoded for streaming

  const init: RequestInit = { method: request.method, headers, redirect: "manual" };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.text();
  }

  const upstream = await fetch(target, init);

  // Stream the upstream body straight through; this preserves the SSE stream of /agent/stream.
  const responseHeaders = new Headers();
  const contentType = upstream.headers.get("content-type");
  if (contentType) responseHeaders.set("content-type", contentType);
  responseHeaders.set("cache-control", "no-cache, no-transform");
  responseHeaders.set("x-accel-buffering", "no");

  return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
}

type RouteContext = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxy(request, (await context.params).path);
}

export async function POST(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxy(request, (await context.params).path);
}
