// #847 — the Correctness Console's rendering. Pure: it draws the tiles
// `lib/correctnessConsole.ts` evaluated and owns no data, so the whole page can
// be rendered from fixtures with `renderToStaticMarkup`.
//
// Every state carries a WORD as well as a colour, so a tile is readable without
// colour vision and in a grayscale screenshot.

import type { ReactNode } from "react";

import PageHeader from "@/components/admin/PageHeader";
import {
  ageSeconds,
  formatAge,
  summarize,
  type CorrectnessRow,
  type CorrectnessState,
  type CorrectnessTile,
} from "@/lib/correctnessConsole";

const STATE_STYLE: Record<CorrectnessState, { label: string; badge: string; border: string }> = {
  green: { label: "OK", badge: "bg-accent-live/10 text-accent-live", border: "border-accent-live/30" },
  amber: { label: "Watch", badge: "bg-accent-warning/10 text-accent-warning", border: "border-accent-warning/30" },
  red: { label: "Act now", badge: "bg-accent-danger/10 text-accent-danger", border: "border-accent-danger/30" },
  stale: { label: "Stale", badge: "bg-surface-elevated text-text-secondary", border: "border-surface-border" },
  partial: { label: "Partly verified", badge: "bg-surface-elevated text-text-secondary", border: "border-surface-border" },
  unavailable: { label: "Unverified", badge: "bg-surface-elevated text-text-secondary", border: "border-surface-border" },
  unauthorized: { label: "Not authorized", badge: "bg-surface-elevated text-text-muted", border: "border-surface-border" },
  loading: { label: "Loading", badge: "bg-surface-elevated text-text-muted", border: "border-surface-border" },
  no_threshold: { label: "No threshold", badge: "bg-surface-elevated text-text-muted", border: "border-surface-border" },
};

/** Rows shown before the rest fold under "Show all". */
export const ROWS_VISIBLE = 8;

/**
 * `muted`: the row sits in a stale tile, so its verdict is history, not a
 * current call — it reads "was …" in neutral colour, never a live red/green.
 */
export function StateBadge({ state, muted = false }: { state: CorrectnessState; muted?: boolean }) {
  const s = STATE_STYLE[state];
  const badge = muted ? "bg-surface-elevated text-text-muted" : s.badge;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold whitespace-nowrap ${badge}`}>
      {muted ? `was ${s.label}` : s.label}
    </span>
  );
}

function RowList({ rows, stale = false }: { rows: CorrectnessRow[]; stale?: boolean }) {
  const item = (r: CorrectnessRow, i: number) => (
    <li key={`${r.label}-${i}`} className="py-1.5 border-t border-surface-border first:border-t-0" data-row-state={r.state}>
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs text-text-primary min-w-0 break-words">{r.label}</span>
        <span className="flex items-center gap-1.5 shrink-0">
          <span className="text-xs font-semibold text-text-primary tabular-nums">{r.value}</span>
          <StateBadge state={r.state} muted={stale} />
        </span>
      </div>
      {r.note && <p className="text-[11px] text-text-muted mt-0.5 break-words">{r.note}</p>}
    </li>
  );
  const head = rows.slice(0, ROWS_VISIBLE);
  const rest = rows.slice(ROWS_VISIBLE);
  return (
    <>
      <ul>{head.map(item)}</ul>
      {rest.length > 0 && (
        <details className="mt-1">
          <summary className="text-xs text-text-secondary cursor-pointer py-1">Show all {rows.length}</summary>
          <ul>{rest.map((r, i) => item(r, i + ROWS_VISIBLE))}</ul>
        </details>
      )}
    </>
  );
}

export function CorrectnessTileCard({ tile, nowMs }: { tile: CorrectnessTile; nowMs: number }) {
  const style = STATE_STYLE[tile.state];
  const headingId = `correctness-${tile.key}`;
  const age = ageSeconds(tile.asOf, nowMs);
  return (
    <section
      aria-labelledby={headingId}
      className={`rounded-xl border bg-surface-card p-4 min-w-0 ${style.border}`}
      data-tile={tile.key}
      data-state={tile.state}
      data-last-verdict={tile.lastVerdict ?? ""}
      data-read-ms={tile.readMs ?? ""}
      data-as-of={tile.asOf ?? ""}
    >
      <div className="flex items-start justify-between gap-2">
        <h2 id={headingId} className="text-sm font-semibold text-text-primary">
          {tile.title}
        </h2>
        <StateBadge state={tile.state} />
      </div>
      <p className="text-sm text-text-primary mt-2 break-words">{tile.headline}</p>
      {tile.state === "stale" && tile.lastVerdict && (
        <p className="text-xs text-text-secondary mt-1">
          The stale data read <StateBadge state={tile.lastVerdict} muted /> — not a current verdict.
        </p>
      )}
      {tile.rows.length > 0 && (
        <div className="mt-3">
          <RowList rows={tile.rows} stale={tile.state === "stale"} />
        </div>
      )}
      {tile.related && tile.related.length > 0 && (
        <div className="mt-3">
          <p className="text-[11px] font-semibold text-text-secondary uppercase tracking-wide">Related, not this metric</p>
          <RowList rows={tile.related} />
        </div>
      )}
      <p className="text-[11px] text-text-muted mt-3 break-words">{tile.method}</p>
      <p className="text-[11px] text-text-muted mt-1 break-all">
        {tile.source}
        {tile.asOf ? ` · built ${formatAge(age)}` : tile.state !== "loading" && tile.key !== "guess_family" ? " · build time unknown" : ""}
        {typeof tile.readMs === "number" ? ` · read in ${tile.readMs} ms` : ""}
      </p>
    </section>
  );
}

export interface CorrectnessConsoleViewProps {
  tiles: CorrectnessTile[];
  nowMs: number;
  /** ms from the first request to the last read settling; null while pending. */
  settledMs: number | null;
  /** Drawn under the header when a read was refused (`AdminAuthNotice`). */
  authNotice?: ReactNode;
  onReload?: () => void;
}

export default function CorrectnessConsoleView({ tiles, nowMs, settledMs, authNotice, onReload }: CorrectnessConsoleViewProps) {
  const { status, summary } = summarize(tiles);
  const anyUnauthorized = tiles.some((t) => t.state === "unauthorized");
  return (
    <div data-console-status={status} data-settled-ms={settledMs ?? ""}>
      <PageHeader
        question="Can we trust our numbers today?"
        status={status}
        summary={summary}
        ideal="every tile OK, each against its documented threshold; anything unread or stale is unverified, never OK"
        subtitle="Correctness Console — winner coverage, guesses, calibration, sources, links and grids, from existing endpoints"
      />
      {anyUnauthorized && authNotice && <div className="mb-4">{authNotice}</div>}
      <div className="flex flex-wrap items-center gap-3 mb-4 text-xs text-text-muted">
        <span>{settledMs === null ? "Reads in progress…" : `All reads settled in ${settledMs} ms`}</span>
        <span data-judged-at={new Date(nowMs).toISOString()}>
          Judged against the clock at{" "}
          {new Date(nowMs).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit", timeZoneName: "short" })}
        </span>
        {onReload && (
          <button
            type="button"
            onClick={onReload}
            disabled={settledMs === null}
            className="px-3 py-1.5 rounded-lg border border-surface-border bg-surface-card text-text-secondary hover:text-text-primary disabled:opacity-50"
          >
            Reload
          </button>
        )}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-4">
        {tiles.map((t) => (
          <CorrectnessTileCard key={t.key} tile={t} nowMs={nowMs} />
        ))}
      </div>
    </div>
  );
}
