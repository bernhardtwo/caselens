import type { Source } from "@/lib/agentStream";

export function SourcesPanel({
  sources,
  activeSources,
  onHover,
}: {
  sources: Source[];
  activeSources: number[] | null;
  onHover: (sources: number[] | null) => void;
}) {
  return (
    <div className="p-4">
      <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        Fuentes
      </h2>
      {sources.length === 0 ? (
        <p className="text-sm text-slate-400">Las fuentes citadas aparecerán aquí.</p>
      ) : (
        <ol className="space-y-2">
          {sources.map((source, index) => {
            const active = activeSources !== null && activeSources.includes(index);
            return (
              <li
                key={index}
                onMouseEnter={() => onHover([index])}
                onMouseLeave={() => onHover(null)}
                className={`flex gap-3 rounded-lg border p-3 transition-colors ${
                  active ? "border-indigo-300 bg-indigo-50" : "border-slate-200 bg-white"
                }`}
              >
                <span
                  className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${
                    active ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-500"
                  }`}
                >
                  {index + 1}
                </span>
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-slate-800">{source.title}</p>
                  <p className="truncate text-xs text-slate-500">{source.section}</p>
                  <p className="mt-1 font-mono text-[11px] text-slate-400">
                    {source.source}
                    {source.rerank_score != null && ` · rerank ${source.rerank_score.toFixed(3)}`}
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
