import { CHIP_COPY, SOURCES_COPY } from "@/lib/evals/copy";
import type { EvalsSource } from "@/lib/evals/sources";
import { pacificDayLabel } from "@/lib/evals/truth";

/** "Where every number comes from": one link per source, with the sections that read it. */
export default function SourceList({
  sources,
  sectionTitles,
}: {
  sources: readonly EvalsSource[];
  sectionTitles: Readonly<Record<string, string>>;
}) {
  return (
    <ul className="space-y-2" data-testid="evals-source-list">
      {sources.map((source) => (
        <li key={source.id} data-source-id={source.id} className="text-caption">
          <a
            href={source.href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent-brand hover:underline"
          >
            {source.label}
          </a>
          <span className="text-text-secondary">
            {" · "}
            <time dateTime={source.date}>{pacificDayLabel(source.date) ?? CHIP_COPY.dateUnreadable}</time>
            {" · "}
            {SOURCES_COPY.usedByPrefix}{" "}
            {source.usedBy.map((id) => `“${sectionTitles[id] ?? id}”`).join(", ")}
          </span>
        </li>
      ))}
    </ul>
  );
}
