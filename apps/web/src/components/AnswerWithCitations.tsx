import type { Citation } from "@/lib/agentStream";

interface Segment {
  text: string;
  sources: number[] | null;
}

// citation start/end are character offsets into `text` and already align (ADR-0007).
function segmentize(text: string, citations: Citation[]): Segment[] {
  const ordered = citations
    .filter((c) => c.start >= 0 && c.end <= text.length && c.end > c.start)
    .sort((a, b) => a.start - b.start);

  const segments: Segment[] = [];
  let cursor = 0;
  for (const citation of ordered) {
    if (citation.start < cursor) continue; // skip overlapping spans
    if (citation.start > cursor) segments.push({ text: text.slice(cursor, citation.start), sources: null });
    segments.push({
      text: text.slice(citation.start, citation.end),
      sources: citation.sources.map(Number).filter(Number.isFinite),
    });
    cursor = citation.end;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor), sources: null });
  return segments;
}

export function AnswerWithCitations({
  text,
  citations,
  activeSources,
  onHover,
}: {
  text: string;
  citations: Citation[];
  activeSources: number[] | null;
  onHover?: (sources: number[] | null) => void;
}) {
  const segments = segmentize(text, citations);
  return (
    <p className="text-[15px] leading-7 text-slate-800">
      {segments.map((segment, index) => {
        if (segment.sources === null) {
          return <span key={index}>{segment.text}</span>;
        }
        const sources = segment.sources;
        const active = activeSources !== null && sources.some((s) => activeSources.includes(s));
        return (
          <mark
            key={index}
            onMouseEnter={() => onHover?.(sources)}
            onMouseLeave={() => onHover?.(null)}
            className={`cursor-default rounded px-0.5 transition-colors ${
              active
                ? "bg-indigo-200 text-indigo-950"
                : "bg-indigo-50 text-slate-800 hover:bg-indigo-100"
            }`}
          >
            {segment.text}
            <sup className="ml-0.5 text-[10px] font-semibold text-indigo-600">
              {sources.map((s) => s + 1).join(",")}
            </sup>
          </mark>
        );
      })}
    </p>
  );
}
