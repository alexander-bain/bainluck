"use client";

import { useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowUpRight, Check, ChevronDown, ChevronRight, Info, Maximize2 } from "lucide-react";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import EventHeroProbabilityPair from "@/components/EventHeroProbabilityPair";
import ProbabilityBar from "@/components/ProbabilityBar";
import { FuturesChart } from "@/components/FuturesChart";
import { SettledMark } from "@/components/SettledOutcomeMark";
import ChartRangeChips from "@/components/event/ChartRangeChips";
import ChartFullscreenDialog from "@/components/event/ChartFullscreenDialog";
import { availableRanges, windowOutcomeHistory, type ChartRangeKey } from "@/lib/chartWindow";
import { renderedDuelPercents, renderedPercent } from "@/lib/renderedPercent";
import type { FuturesOutcome } from "@/lib/types";
import { bodyKind, CASES, datePT, payloadVerdict, percentText, rankedOutcomes, type PrototypeData, type StudyState } from "./_model";
import styles from "./prototype.module.css";

function SourceMark() {
  // Reserved for #11920. A quiet mark, not a dead button or a fake sources sheet.
  return <span className="inline-flex shrink-0 align-middle text-text-muted" role="img" aria-label="Source information reserved" title="Source information · reserved for the upcoming sources sheet"><Info size={13} strokeWidth={1.5} /></span>;
}

function Value({ probability, verdict, rendered, large = false }: { probability: number | null; verdict?: "won" | "lost" | null; rendered?: number | null; large?: boolean }) {
  return <span className={`inline-flex items-center gap-1.5 whitespace-nowrap ${large ? "text-xl" : "text-sm"}`}>
    {verdict ? <SettledMark won={verdict === "won"} /> : <span className="font-mono font-bold tabular-nums">{percentText(probability, rendered)}</span>}
    <SourceMark />
  </span>;
}

function Attribution({ sources }: { sources: string[] }) {
  const labels: Record<string, string> = { kalshi: "Kalshi", polymarket: "Polymarket", odds_api: "Sportsbooks" };
  return <span className="text-[11px] text-text-secondary">{sources.map((source) => labels[source] ?? source).join(" · ")}</span>;
}

export default function Prototype({ data, initialStudy = "payload" }: { data: PrototypeData; initialStudy?: StudyState }) {
  usePageTracking({ pageType: "futures_detail", pageTitle: data.detail.name });
  useScrollDepth({ pageType: "futures_detail" });
  useEngagementTime({ pageType: "futures_detail" });
  const { detail, history, sources, related } = data;
  const shape = bodyKind(detail);
  const [study, setStudy] = useState<StudyState>(initialStudy);
  const [expanded, setExpanded] = useState(false);
  const [range, setRange] = useState<ChartRangeKey>(initialStudy === "settled" || (initialStudy === "payload" && detail.status === "resolved") ? "all" : "1W");
  const [fullscreen, setFullscreen] = useState(false);
  const ranked = useMemo(() => rankedOutcomes(detail), [detail]);
  const printedPair = useMemo(() => shape === "duel" && detail.mutually_exclusive && ranked.length === 2
    ? new Map(ranked.map((outcome, index) => [outcome.id, renderedDuelPercents(ranked[0].probability, ranked[1].probability)[index]]))
    : new Map<number, number | null>(), [shape, detail.mutually_exclusive, ranked]);
  const [selectedId, setSelectedId] = useState<number>(ranked[0].id);
  const selected = detail.outcomes.find((outcome) => outcome.id === selectedId) ?? ranked[0];
  const winner = detail.outcomes.find((outcome) => payloadVerdict(detail, outcome) === "won");
  const isStudy = study !== "payload";
  const resolved = study === "settled" || (study === "payload" && detail.status === "resolved");
  const liveLead = shape === "quantity" || shape === "unshaped" ? selected : ranked[0];
  const lead = resolved && !isStudy ? winner ?? liveLead : study === "settled" ? selected : liveLead;
  const hasResult = resolved && (study === "settled" || !!winner);
  const thresholdValue = (outcome: FuturesOutcome) => parseFloat(outcome.name.replace(/[^\d.]/g, ""));
  const verdictFor = (outcome: FuturesOutcome) => study === "open" ? null
    : study === "settled" ? (shape === "participation"
      ? (ranked.findIndex((row) => row.id === outcome.id) < 12 ? "won" : "lost")
      : shape === "quantity" ? (thresholdValue(outcome) <= thresholdValue(selected) ? "won" : "lost")
        : outcome.id === selectedId ? "won" : "lost")
      : payloadVerdict(detail, outcome);
  const category = CASES.find((item) => item.id === detail.id)!.category;
  const ranges = useMemo(() => availableRanges(history, false), [history]);
  const effectiveRange = ranges.some((item) => item.key === range) ? range : "all";
  const windowed = useMemo(() => windowOutcomeHistory(history, effectiveRange), [history, effectiveRange]);
  const chartSelection = useMemo(() => new Set(shape === "quantity" || shape === "unshaped"
    ? [selectedId] : [...ranked.slice(0, shape === "duel" ? 2 : 3).map((outcome) => outcome.id), selectedId]), [shape, selectedId, ranked]);
  const outcomeColors = useMemo(() => new Map(ranked.map((outcome, index) => [outcome.id,
    ["var(--accent-brand)", "var(--accent-futures)", "var(--accent-warning)", "var(--text-secondary)"][index % 4]])), [ranked]);
  const drawableHistory = windowed.some((outcome) => chartSelection.has(outcome.outcome_id)
    && new Set(outcome.history.filter((point) => point.probability != null && point.bookmaker !== "settlement").map((point) => point.timestamp)).size >= 2);
  const chart = drawableHistory ? <FuturesChart historyData={windowed} selectedOutcomes={chartSelection}
    fixedYAxis fieldCeiling={false} allowZoom={false} stepInterpolation={false}
    showCombinedProbability={false} height={fullscreen ? 480 : 260} showLegend={false} showAxes outcomeColors={outcomeColors}
    settled={resolved && !isStudy} marketName={detail.name} /> : <div className="flex h-[260px] flex-col items-center justify-center gap-2 px-5 text-center" role="status"><Info size={18} className="text-text-muted" /><p className="text-sm font-medium text-text-primary">Not enough recorded history</p><p className="max-w-[240px] text-xs leading-relaxed text-text-secondary">A path needs more than one reading. Current probabilities are shown above.</p></div>;
  const expandRef = useRef<HTMLButtonElement>(null);
  const probability = lead.probability;
  const title = detail.name.replace(/\?$/, "");
  const orderedThresholds = [...detail.outcomes].sort((a, b) => parseFloat(a.name.replace(/[^\d.]/g, "")) - parseFloat(b.name.replace(/[^\d.]/g, "")));
  const displayRows = expanded ? ranked : ranked.slice(0, shape === "participation" ? 6 : 3);

  const row = (outcome: FuturesOutcome, index: number) => <button key={outcome.id} type="button"
    onClick={() => setSelectedId(outcome.id)} aria-pressed={selectedId === outcome.id}
    className={`w-full rounded-lg px-3 py-3 text-left transition-colors focus-visible:outline-accent-brand ${selectedId === outcome.id ? "bg-accent-brand/5" : "hover:bg-surface-elevated"}`}>
    <span className="flex items-center gap-3">
      <span className="w-4 text-[11px] font-mono text-text-muted">{index + 1}</span>
      <span className="min-w-0 flex-1 text-sm font-medium text-text-primary">{outcome.name}</span>
      <span>{resolved && !verdictFor(outcome) && <span className="mr-2 text-[10px] text-text-secondary">Last recorded</span>}<Value probability={outcome.probability} verdict={verdictFor(outcome)} /></span>
    </span>
    {!verdictFor(outcome) && outcome.probability != null && <span className="ml-7 mt-2 block h-1 overflow-hidden rounded-full bg-surface-elevated">
      <span className={`block h-full rounded-full ${selectedId === outcome.id ? "bg-accent-brand" : "bg-accent-brand/35"}`} style={{ width: `${outcome.probability * 100}%` }} />
    </span>}
  </button>;

  return <div className={`${styles.prototype} mx-auto max-w-[1080px] pb-8`}>
    <aside aria-label="Prototype review controls" className="mb-5 rounded-card border border-surface-border bg-surface-card p-3">
      <details><summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-[10px] font-semibold uppercase tracking-wider text-text-secondary">Futures / design preview <span className="inline-flex items-center gap-1 text-text-muted">Six markets <ChevronDown size={13} /></span></summary>
      <p className="mb-3 mt-3 text-[10px] text-text-secondary">Production snapshot · {datePT(data.capturedAt, true)}</p>
      <nav aria-label="Prototype examples" className="flex flex-wrap gap-1.5">
        {CASES.map((item) => <Link key={item.id} href={`/kernels-preview/futures/${item.id}`}
          aria-current={item.id === detail.id ? "page" : undefined}
          className={`rounded-full px-2.5 py-1.5 text-xs ${item.id === detail.id ? "bg-text-primary text-surface-card" : "bg-surface-elevated text-text-secondary hover:text-text-primary"}`}>{item.label}</Link>)}
      </nav>
      <div className="mt-3 flex items-center gap-2 border-t border-surface-border/50 pt-3">
        <label htmlFor="study-state" className="text-[11px] text-text-secondary">Review state</label>
        <select id="study-state" value={study} onChange={(event) => { setStudy(event.target.value as StudyState); if (event.target.value === "settled") setRange("all"); }} className="max-w-full rounded-md border border-surface-border bg-surface-card px-2 py-1 text-xs text-text-primary">
          <option value="payload">As served</option><option value="open">Open layout study</option><option value="settled">Settled layout study</option>
        </select>
      </div>
      {isStudy && <p className="mt-2 text-xs leading-relaxed text-text-secondary" role="status">Layout study only. {study === "settled" ? shape === "participation" ? "The twelve leading teams are assumed to qualify. These are not production results." : shape === "quantity" ? `${selected.name} is assumed to be the last threshold cleared. This is not a production result.` : `${selected.name} is assumed to win for this study; this is not a production result.` : "Uses the last recorded probabilities; this does not change the production status."}</p>}
      </details>
      {isStudy && <p className="mt-2 text-xs text-text-secondary" role="status">{study === "settled" ? "Settled layout study · assumed result, not a production grade." : "Open layout study · last recorded numbers, not the production status."}</p>}
    </aside>

    <Link href="/discover" className="mb-4 inline-flex items-center gap-1 text-xs text-text-secondary hover:text-text-primary"><ArrowLeft size={13} /> Discover</Link>
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_296px] lg:gap-5">
      <div className="min-w-0 space-y-4">
        <section aria-label="Market overview" className="overflow-hidden rounded-card bg-surface-card shadow-card">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-surface-border/50 px-4 py-2.5 sm:px-5">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-text-secondary">{category}</span>
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${resolved ? "bg-surface-elevated text-text-secondary" : "bg-accent-brand/10 text-accent-brand"}`}>{resolved ? "Settled" : "Open"}</span>
          </div>
          <div className="px-4 pb-5 pt-4 sm:px-5 sm:pt-5">
            <h1 className="max-w-[600px] text-[23px] font-bold leading-tight tracking-tight text-text-primary sm:text-[28px]">{title}</h1>
            <p className="mt-2 text-[13px] leading-relaxed text-text-secondary">{shape === "quantity" ? "How much snow will December bring?" : shape === "participation" ? "Who makes the playoff field? Several teams can qualify." : shape === "field" ? "The state with the smallest margin of victory." : shape === "unshaped" ? "One market. One recorded outcome." : "One outcome, one probability across the market."}</p>

            <div className="my-6">
              {hasResult ? <div className="flex items-start gap-3">
                <span className="mt-1 rounded-full bg-accent-brand/10 p-2 text-accent-brand"><Check size={23} /></span>
                <div><div className="flex items-center gap-2"><p className="text-[27px] font-bold leading-tight text-text-primary sm:text-[32px]">{lead.name}</p><SourceMark /></div>
                  <div className="mt-2 flex items-center gap-2"><SettledMark won /><span className="text-xs text-text-secondary">{data.settledAt && !isStudy ? `Settled ${datePT(data.settledAt, true)}` : "Result layout study"}</span></div>
                </div>
              </div> : resolved ? <div><p className="text-2xl font-semibold text-text-primary">Result unavailable <SourceMark /></p><p className="mt-2 text-xs text-text-secondary">No confirmed grade is available for this outcome.</p></div>
                : <><div className="flex items-end gap-2">
                  <div className={styles.heroNumber}><EventHeroProbabilityPair homeProb={probability} awayProb={null} homePct={printedPair.get(lead.id) ?? renderedPercent(probability)} awayPct={null} awayWithheld /></div>
                  <span className="pb-2"><SourceMark /></span>
                </div><p className="mt-2 text-[15px] font-semibold text-text-primary">{lead.name}<span className="ml-2 text-xs font-normal text-text-secondary">{shape === "quantity" ? "of snow" : shape === "participation" ? "to qualify" : shape === "unshaped" ? "" : "leads"}</span></p></>}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-surface-border/60 pt-3">
              <Attribution sources={sources} />
              <span className="text-[11px] text-text-secondary">{resolved ? "Final state" : detail.resolution_date ? `Closes ${datePT(detail.resolution_date)}` : "Open market"}</span>
            </div>
          </div>

          <div className="border-t border-surface-border/60 px-3 pb-3 pt-4 sm:px-4">
            <div className="mb-2 flex items-center justify-between gap-2 px-1">
              <h2 className="text-sm font-semibold text-text-primary">{shape === "duel" ? "The race" : shape === "quantity" ? "Snowfall thresholds" : shape === "participation" ? "Chance to qualify" : shape === "unshaped" ? "The outcome" : "The field"}</h2>
              {shape !== "quantity" && <span className="text-[11px] text-text-secondary">{detail.outcomes.length} {detail.outcomes.length === 1 ? "outcome" : "outcomes"}</span>}
            </div>
            {shape === "duel" ? <div className="px-1">
              <div className="grid grid-cols-2 gap-3 py-2">{ranked.map((outcome) => <div key={outcome.id} className="min-w-0"><p className="mb-2 text-[13px] font-medium text-text-primary">{outcome.name}</p><Value probability={outcome.probability} rendered={printedPair.get(outcome.id)} verdict={verdictFor(outcome)} large /></div>)}</div>
              {!resolved && <ProbabilityBar homeProbability={printedPair.get(ranked[0].id) == null ? null : printedPair.get(ranked[0].id)! / 100} awayProbability={printedPair.get(ranked[1].id) == null ? null : printedPair.get(ranked[1].id)! / 100} homeColor="var(--accent-brand)" awayColor="var(--text-secondary)" height={6} animated={false} />}
            </div> : shape === "quantity" ? <><div className="grid grid-cols-3 gap-2 py-2">{orderedThresholds.map((outcome) => <button key={outcome.id} onClick={() => setSelectedId(outcome.id)} aria-pressed={selectedId === outcome.id} className={`rounded-lg border px-2 py-3 text-left ${selectedId === outcome.id ? "border-accent-brand/35 bg-accent-brand/5" : "border-surface-border bg-surface-card hover:bg-surface-elevated"}`}>
              <span className="block text-[11px] text-text-secondary">{outcome.name}</span><span className="mt-2 block"><Value probability={outcome.probability} verdict={verdictFor(outcome)} /></span>
            </button>)}</div><p className="px-1 pt-2 text-[11px] leading-relaxed text-text-secondary">Thresholds overlap. Clearing a higher rung also clears the lower rungs.</p></>
              : shape === "unshaped" ? <>{row(ranked[0], 0)}<p className="px-3 pb-1 pt-2 text-xs leading-relaxed text-text-secondary">Only this outcome is served. A second side is not supplied.</p></>
                : <>{shape === "participation" && <p className="px-1 pb-2 text-xs leading-relaxed text-text-secondary">Independent chances · these do not add to 100%.</p>}
                  <div className={shape === "participation" ? "border-l-2 border-accent-brand/30 pl-1" : ""}>{displayRows.map(row)}</div>
                  {ranked.length > (shape === "participation" ? 6 : 3) && <button onClick={() => setExpanded(!expanded)} aria-expanded={expanded} className="mt-2 flex min-h-10 w-full items-center justify-center gap-1.5 rounded-lg bg-surface-elevated text-xs font-medium text-text-secondary hover:text-text-primary">{expanded ? "Show fewer" : `${ranked.length - displayRows.length} more`}<ChevronDown className={expanded ? "rotate-180" : ""} size={14} /></button>}
                </>}
          </div>
        </section>

        <section aria-labelledby="journey-heading" className="min-w-0 rounded-card bg-surface-card px-3 py-4 shadow-card sm:px-5 sm:py-5">
          <div className="mb-3 flex items-center justify-between gap-2">
            <div><h2 id="journey-heading" className="text-sm font-semibold text-text-primary">{resolved && !isStudy ? "The completed journey" : "How it moved"}</h2><p className="mt-1 text-[11px] text-text-secondary">{shape === "quantity" || shape === "unshaped" ? selected.name : "Leading outcomes"} · probability over time</p></div>
            <button ref={expandRef} onClick={() => setFullscreen(true)} aria-label="Expand probability chart" className="rounded-md p-2 text-text-secondary hover:bg-surface-elevated"><Maximize2 size={15} /></button>
          </div>
          <ChartRangeChips ranges={ranges} selected={effectiveRange} onSelect={setRange} className="mb-4" />
          <div className={styles.chartFrame}>{chart}</div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2 border-t border-surface-border/50 pt-3">{ranked.filter((outcome) => chartSelection.has(outcome.id)).map((outcome) => <span key={outcome.id} className="inline-flex items-center gap-1.5 text-[11px] text-text-secondary"><span className="h-1.5 w-1.5 rounded-full" style={{background: outcomeColors.get(outcome.id)}} />{outcome.name}<SourceMark /></span>)}</div>
          <p className="mt-3 text-[11px] leading-relaxed text-text-secondary">{data.historyNote ?? "Recorded probabilities. Full scale, no smoothing; missing readings remain gaps."}</p>
          {isStudy && <p className="mt-2 text-[11px] text-text-secondary">Recorded production history. Assumed results are not added to the chart.</p>}
          {data.historyNote && <p className="mt-2 text-[10px] text-text-muted"><Attribution sources={[detail.source ?? ""]} /> · recorded history</p>}
        </section>
      </div>

      <aside className="min-w-0 space-y-4">
        <section aria-labelledby="related-heading" className="rounded-card bg-surface-card p-4 shadow-card">
          <div className="mb-1 flex items-center justify-between"><h2 id="related-heading" className="text-sm font-semibold text-text-primary">Related markets</h2><ArrowUpRight size={15} className="text-text-muted" /></div>
          <p className="mb-4 text-[11px] text-text-secondary">{category === "Politics" ? "The election picture" : shape === "participation" ? "The college football picture" : "More weather markets"}</p>
          <div className="divide-y divide-surface-border/60">{related.map((market) => {
            const relatedDetail = { status: market.status } as PrototypeData["detail"];
            const relatedWinner = market.outcomes?.find((outcome) => payloadVerdict(relatedDetail, outcome) === "won");
            return <Link key={market.id} href={CASES.some((item) => item.id === market.id) ? `/kernels-preview/futures/${market.id}` : `/futures/${market.id}`} className="group block py-3 first:pt-0 last:pb-0">
            <div className="flex items-start gap-2"><p className="flex-1 text-[13px] font-medium leading-snug text-text-primary">{market.name.replace(/\?$/, "")}</p><ChevronRight size={14} className="mt-0.5 shrink-0 text-text-muted group-hover:text-text-primary" /></div>
            <div className="mt-2 flex items-center justify-between gap-2"><span className="min-w-0 text-[11px] text-text-secondary">{relatedWinner?.name ?? market.lead}</span><Value probability={market.probability} verdict={relatedWinner ? "won" : market.verdict} /></div>
            <div className="mt-1"><Attribution sources={market.sources} /></div>
          </Link>; })}</div>
        </section>
        <section className="rounded-card border border-surface-border/70 p-4">
          <h2 className="text-xs font-semibold text-text-primary">What this market means</h2>
          <p className="mt-2 text-xs leading-relaxed text-text-secondary">{shape === "duel" ? "A race with one winner. The split shows each candidate’s chance." : shape === "field" ? "One state has the closest race. Each row keeps its own share of the full field, including outcomes below the fold." : shape === "quantity" ? "Each rung is a separate threshold for total December snowfall in Denver. Select a rung to read its history." : shape === "participation" ? "Teams qualify independently. A high chance for one team does not take a place away from another team’s probability." : "Yes is the only recorded outcome. Its probability stands on its own; no opposing outcome is fabricated."}</p>
          {detail.description && <details className="mt-3 border-t border-surface-border/60 pt-3"><summary className="cursor-pointer text-xs font-medium text-text-secondary">Market rules</summary><p className="mt-2 whitespace-pre-line text-[11px] leading-relaxed text-text-secondary">{detail.description}</p></details>}
        </section>
      </aside>
    </div>
    {fullscreen && <ChartFullscreenDialog title={`${title} · probability history`} openerRef={expandRef} onClose={() => setFullscreen(false)}><div className="mx-auto w-full max-w-[960px] px-3">{chart}</div></ChartFullscreenDialog>}
  </div>;
}
