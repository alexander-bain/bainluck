"use client";

import React, { useEffect, useId, useRef, useState } from "react";
import {
  chanceLabel, compactChange, comparisonPoints, complementQuestion, exactChanceLabel,
  finiteChance, matrixForStat, quotedChance, resolveQuestion, resolveSource, selectQuestion, sourceKey,
  type DuringPlayerProps, type DuringPropsRow, type QuestionSelection, type SourceSelection,
} from "../lib/duringPlayerPropsMatrixSelection";

export interface DuringPlayerPropsMatrixProps {
  /** Already accepted embedded-market projection. No independent fetch/stream. */
  data: DuringPlayerProps | null;
  initialStatKey?: string;
  initialSelection?: QuestionSelection;
  /** Host freshness policy, using observation time only. Stale quotes stay visible. */
  observationLabel?: (observedAt: string | null) => string;
}

export default function DuringPlayerPropsMatrix({ data, initialStatKey, initialSelection, observationLabel }: DuringPlayerPropsMatrixProps) {
  const [statKey, setStatKey] = useState(initialSelection?.statKey ?? initialStatKey ?? data?.stats[0]?.stat_key ?? "");
  const [selection, setSelection] = useState<QuestionSelection | null>(initialSelection ?? null);
  const [source, setSource] = useState<SourceSelection | null>(null);
  const sectionId = useId();
  const dialogId = useId();
  const scroller = useRef<HTMLDivElement>(null);
  const section = useRef<HTMLElement>(null);
  const dialog = useRef<HTMLDivElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const origin = useRef<HTMLButtonElement | null>(null);
  const returnPosition = useRef({ x: 0, y: 0, left: 0, top: 0 });
  const sourceChoices = useRef(new Map<string, SourceSelection | null>());
  const stat = data?.stats.find(item => item.stat_key === statKey);
  const matrix = matrixForStat(data, statKey);
  const row = selection ? resolveQuestion(data, selection) : null;
  const contributor = source ? resolveSource(row, source) : null;
  const opposite = row && data ? complementQuestion(data, row) : null;
  const chance = row ? source ? row.current.state === "quoted" && contributor && finiteChance(contributor.probability) ? contributor.probability : null : quotedChance(row) : null;
  const points = row && !source ? comparisonPoints(row) : null;

  function showQuestion(rowToOpen: DuringPropsRow) {
    const next = selectQuestion(rowToOpen);
    setSelection(next);
    setSource(sourceChoices.current.get(JSON.stringify(next)) ?? null);
  }
  function open(rowToOpen: DuringPropsRow, button: HTMLButtonElement) {
    origin.current = button;
    returnPosition.current = { x: window.scrollX, y: window.scrollY, left: scroller.current?.scrollLeft ?? 0, top: scroller.current?.scrollTop ?? 0 };
    showQuestion(rowToOpen);
  }
  function close() {
    setSelection(null);
    requestAnimationFrame(() => {
      if (scroller.current) {
        scroller.current.scrollLeft = returnPosition.current.left;
        scroller.current.scrollTop = returnPosition.current.top;
      }
      window.scrollTo(returnPosition.current.x, returnPosition.current.y);
      const focusTarget = origin.current?.isConnected ? origin.current : scroller.current ?? section.current;
      focusTarget?.focus({ preventScroll: true });
    });
  }
  const isOpen = selection !== null;
  useEffect(() => {
    if (!statKey && data?.stats[0]) setStatKey(data.stats[0].stat_key);
  }, [data, statKey]);
  useEffect(() => {
    if (selection) sourceChoices.current.set(JSON.stringify(selection), source);
  }, [selection, source]);
  useEffect(() => {
    if (!isOpen) return;
    closeButton.current?.focus({ preventScroll: true });
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previousOverflow; };
  }, [isOpen]);
  useEffect(() => {
    // Removing a focused exact source/question must not strand keyboard focus
    // behind the modal while its unavailable state remains open.
    if (isOpen && dialog.current && !dialog.current.contains(document.activeElement)) closeButton.current?.focus({ preventScroll: true });
  }, [isOpen, row, contributor]);

  function clock(value: string | null) {
    if (observationLabel) return observationLabel(value);
    return value && Number.isFinite(Date.parse(value)) ? `Observed ${value}` : "Observation time unknown";
  }

  // Null/unsupported/no-row fallback is the existing page holder's dashboard.
  // Keep an open withdrawn question visible instead of silently switching it.
  if ((!data || data.contract !== "10236.v1" || !data.rows.length) && !selection) return null;

  return (
    <section ref={section} tabIndex={-1} aria-labelledby={sectionId} className="overflow-hidden rounded-2xl border border-surface-border bg-surface-card">
      <div className="space-y-3 p-4">
        <div className="flex items-baseline justify-between gap-3">
          <h2 id={sectionId} className="text-lg font-semibold text-text-primary">Player props</h2>
          <span className="text-xs text-text-muted">During · Game</span>
        </div>
        <div aria-label="Statistic" className="flex flex-wrap gap-2">
          {data?.stats.map(item => <button key={item.stat_key} type="button" aria-pressed={statKey === item.stat_key}
            className={`min-h-[44px] rounded-full border px-4 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand ${statKey === item.stat_key ? "border-accent-brand bg-accent-brand text-text-inverse" : "border-surface-border bg-surface-card text-text-secondary"}`}
            onClick={() => { setStatKey(item.stat_key); if (scroller.current) scroller.current.scrollLeft = 0; }}>{item.label}</button>)}
        </div>
        <p className="text-xs leading-relaxed text-text-muted">{matrix.players.length} {matrix.players.length === 1 ? "player" : "players"} · {matrix.questions} {matrix.questions === 1 ? "question" : "questions"} loaded{matrix.withoutQuote > 0 ? ` · ${matrix.withoutQuote} without a current quote` : ""}. Swipe across thresholds.</p>
      </div>
      {matrix.players.length > 0 ? <div ref={scroller} className="overflow-x-auto overscroll-x-contain snap-x snap-mandatory" style={{ scrollPaddingLeft: 136 }} tabIndex={0} role="region" aria-label={`${stat?.label ?? "Selected statistic"} thresholds`}>
        <table className="w-full table-fixed border-collapse text-left" style={{ minWidth: 136 + matrix.columns.length * 88 }}>
          <caption className="sr-only">Players&apos; chances for {stat?.label ?? "the selected statistic"}. Changes are percentage points since the pregame observation.</caption>
          <colgroup><col style={{ width: 136 }} />{matrix.columns.map(column => <col key={column.key} style={{ width: 88 }} />)}</colgroup>
          <thead><tr><th scope="col" className="sticky left-0 z-10 border-y border-surface-border bg-surface-elevated px-4 py-3 text-xs font-medium text-text-muted">Player</th>
            {matrix.columns.map(column => <th key={column.key} scope="col" className="border-y border-surface-border bg-surface-elevated px-2 py-3 text-center text-sm font-semibold text-text-secondary">{column.label}{column.underOnly && <span className="block text-xs font-normal">Under only</span>}</th>)}</tr></thead>
          <tbody>{matrix.players.map(player => <tr key={player.key}>
            <th scope="row" className="sticky left-0 z-10 border-b border-surface-border bg-surface-card px-4 py-4 text-sm font-semibold leading-snug text-text-primary break-words">{player.label}</th>
            {player.cells.map((cell, index) => {
              const probability = cell && !matrix.columns[index].underOnly ? quotedChance(cell) : null;
              const change = cell && probability !== null ? compactChange(cell) : null;
              const accessible = `${player.label}, ${stat?.label ?? statKey}, ${matrix.columns[index].label}, ${probability === null ? "current chance unavailable" : `${chanceLabel(probability)} chance`}${change ? `, ${change.replace(/%/g, " percentage points")} since pregame` : ""}${matrix.columns[index].underOnly ? ", exact under question available" : ""}`;
              return <td key={matrix.columns[index].key} className="snap-start border-b border-surface-border p-0 text-center align-middle">
                {cell ? <button type="button" aria-label={accessible} aria-haspopup="dialog" onClick={event => open(cell, event.currentTarget)}
                  className="flex min-h-[72px] w-full flex-col items-center justify-center gap-1 px-2 py-3 text-text-primary hover:bg-surface-elevated focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand">
                  <span className="font-mono text-[22px] font-semibold tabular-nums">{probability === null ? "—" : chanceLabel(probability)}</span>
                  {change ? <span className="font-mono text-xs tabular-nums text-text-secondary">{change}</span> : probability === null ? <span className="text-[10px] text-text-muted">{matrix.columns[index].underOnly ? "See under" : "No quote"}</span> : null}
                </button> : <span aria-label={accessible} className="flex min-h-[72px] items-center justify-center text-xl text-text-muted">—</span>}
              </td>;
            })}</tr>)}</tbody>
        </table>
      </div> : <p role="status" className="px-4 pb-4 text-sm text-text-secondary">No questions for this statistic are currently available.</p>}
      <p className="px-4 py-3 text-xs leading-relaxed text-text-muted">Signed changes are percentage points since pregame. Missing quotes are shown as —.</p>

      {selection && <div className="fixed inset-0 z-50 flex items-end justify-center bg-surface-deep/60 p-3 sm:items-center" onClick={event => { if (event.target === event.currentTarget) close(); }}>
        <div ref={dialog} role="dialog" aria-modal="true" aria-labelledby={dialogId} className="max-h-[85dvh] w-full max-w-md overflow-y-auto rounded-2xl border border-surface-border bg-surface-card p-5 shadow-lg"
          onKeyDown={event => {
            if (event.key === "Escape") { event.preventDefault(); close(); }
            if (event.key !== "Tab") return;
            const buttons = dialog.current?.querySelectorAll<HTMLButtonElement>('button:not([disabled])');
            if (!buttons?.length) return;
            const first = buttons[0], last = buttons[buttons.length - 1];
            if (!dialog.current?.contains(document.activeElement)) { event.preventDefault(); first.focus(); }
            else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
          }}>
          <div className="flex items-start justify-between gap-3"><h3 id={dialogId} className="text-lg font-semibold text-text-primary">{row ? `${row.subject.label} · ${data?.stats.find(item => item.stat_key === row.stat_key)?.label ?? row.stat_key} · ${row.predicate.label}` : "Question unavailable"}</h3>
            <button ref={closeButton} type="button" onClick={close} className="min-h-[44px] px-2 text-sm font-medium text-accent-brand">Close</button></div>
          {!row ? <p role="status" className="mt-4 text-sm text-text-secondary">This exact question is no longer in the accepted projection. Your selection has been kept.</p> : <>
            <p className="mt-1 text-sm text-text-muted">{row.period_key === "full_game" ? "Full game" : row.period_key} · {row.predicate.side === "under" ? "Under" : "Over"}</p>
            <div className="my-5"><p className="font-mono text-3xl font-semibold tabular-nums text-text-primary">{chance === null ? "Unavailable" : exactChanceLabel(chance)}</p>
              <p className="mt-1 text-sm text-text-secondary">{source ? `${source.source} · ${source.side}` : row.current.basis === "blend_mean" ? "Blended chance" : "Current chance"}</p>
              <p className="mt-2 break-words text-xs text-text-muted">{clock(source ? contributor?.observed_at ?? null : row.current.observed_at)}</p>
              {source && !contributor && <p role="status" className="mt-2 text-sm text-text-secondary">This exact source/outcome is no longer available. Select another source explicitly.</p>}
              {row.current.state === "actual_only" && !source && <p className="mt-2 text-sm text-text-secondary">An actual result is available, but there is no current quote.</p>}
            </div>
            {points !== null ? <p className="text-sm text-text-secondary">{points > 0 ? "+" : ""}{Number(points.toPrecision(12))} percentage points since pregame ({exactChanceLabel(row.comparison.baseline!.probability)}).<span className="mt-1 block break-words text-xs text-text-muted">Pregame observed {row.comparison.baseline!.observed_at}</span></p> : <p className="text-sm text-text-muted">Pregame comparison unavailable{source ? " for this exact source." : "."}</p>}
            <div aria-label="Quote source" className="mt-5 flex flex-wrap gap-2">
              <button type="button" aria-pressed={!source} onClick={() => setSource(null)} className={`min-h-[44px] rounded-lg border px-3 text-sm text-text-primary ${!source ? "border-accent-brand bg-surface-elevated" : "border-surface-border"}`}>{row.current.basis === "blend_mean" ? "Blend" : "Published chance"}</button>
              {row.contributors.map(item => <button key={sourceKey(item)} type="button" aria-pressed={!!source && sourceKey(source) === sourceKey(item)} onClick={() => setSource(item)} className={`min-h-[44px] rounded-lg border px-3 text-sm text-text-primary ${source && sourceKey(source) === sourceKey(item) ? "border-accent-brand bg-surface-elevated" : "border-surface-border"}`}>{item.source} · {item.outcome_name ?? `Outcome ${item.outcome_id ?? "unknown"}`} · {item.side}</button>)}
            </div>
            {contributor && <p className="mt-3 break-words text-xs text-text-muted">Market {contributor.market_id ?? "unknown"} · Outcome {contributor.outcome_id ?? "unknown"} · Full game</p>}
            {opposite && <button type="button" className="mt-4 min-h-[44px] text-sm font-medium text-accent-brand" onClick={() => showQuestion(opposite)}>View {opposite.predicate.side} · {opposite.predicate.label}</button>}
          </>}
        </div>
      </div>}
    </section>
  );
}
