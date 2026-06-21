import { API_BASE, authHeaders, type Identity } from "@/lib/api";

export interface Passage {
  id: number | string;
  source: string;
  title: string;
  section: string;
  text: string;
}

export interface ToolResult {
  passages?: Passage[];
  count?: number;
  [key: string]: unknown;
}

export interface Citation {
  start: number;
  end: number;
  text: string;
  sources: string[];
}

export interface Source {
  source: string;
  title: string;
  section: string;
  rerank_score: number | null;
}

export type AgentEvent =
  | { type: "tool_call"; data: { name: string; arguments: Record<string, unknown> } }
  | {
      type: "tool_result";
      data: { name: string; arguments: Record<string, unknown>; result: ToolResult };
    }
  | { type: "answer"; data: { text: string } }
  | { type: "citations"; data: { citations: Citation[]; sources: Source[] } }
  | { type: "action_proposed"; data: { claim_id: number; from_status: string; to_status: string } }
  | { type: "error"; data: { detail: string } };

function parseBlock(block: string): AgentEvent | null {
  let name = "";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trim());
  }
  if (!name || data.length === 0) return null;
  try {
    return { type: name, data: JSON.parse(data.join("\n")) } as AgentEvent;
  } catch {
    return null;
  }
}

// POST /agent/stream returns Server-Sent Events. EventSource only does GET, so we read
// the ReadableStream ourselves and split on the SSE record separator (a blank line).
export async function streamAgent(
  message: string,
  identity: Identity,
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE}/agent/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(identity) },
    body: JSON.stringify({ message }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`El agente respondió ${response.status}.`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const event = parseBlock(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      if (event) onEvent(event);
      boundary = buffer.indexOf("\n\n");
    }
  }
}
