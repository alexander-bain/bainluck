"use client";
import { useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { ChevronLeft, ChevronDown, Info, Maximize2 } from "lucide-react";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import EventHeroProbabilityPair from "@/components/EventHeroProbabilityPair";
import SettledOutcomeHero from "@/components/event/SettledOutcomeHero";
import EventLeaderboard from "@/components/event/EventLeaderboard";
import MatchupsRail from "@/components/event/MatchupsRail";
import ChartRangeChips from "@/components/event/ChartRangeChips";
import ChartFullscreenDialog from "@/components/event/ChartFullscreenDialog";
import { SettledMark } from "@/components/SettledOutcomeMark";
import {
  availableRanges,
  windowOutcomeHistory,
  type ChartRangeKey,
} from "@/lib/chartWindow";
import { renderedDuelPercents, renderedPercent } from "@/lib/renderedPercent";
import type { SettledOutcome } from "@/lib/eventOutcome";
import type { EventConceptChild, FuturesOutcome } from "@/lib/types";
import {
  bodyKind,
  CASES,
  datePT,
  payloadVerdict,
  percentText,
  rankedOutcomes,
  type PrototypeData,
  type StudyState,
} from "./_model";
import styles from "./prototype.module.css";

// The shared mark's exact stamp uses the reader's timezone. Keep that text
// out of server HTML, as with the shared history kernel below.
const PriceAgeMark = dynamic(
  () => import("@/components/event/PriceAgeMark").then((m) => m.PriceAgeMark),
  { ssr: false },
);

// Event composition's fixed-domain winner/settled journey kernel. OddsChart's
// automatic Y scale conflicts with this prototype's explicit 0–100 requirement.
const FuturesChart = dynamic(
  () => import("@/components/FuturesChart").then((m) => m.FuturesChart),
  {
    ssr: false,
    loading: () => (
      <div
        className="h-[380px] animate-pulse bg-surface-elevated"
        aria-label="Loading probability history"
      />
    ),
  },
);
function SourceMark() {
  return (
    <span
      role="img"
      aria-label="Source information reserved"
      className="inline-flex shrink-0 text-text-muted"
      title="Source information"
    >
      <Info size={11} strokeWidth={1.5} />
    </span>
  );
}
function Value({
  outcome,
  verdict,
  historical = false,
}: {
  outcome: FuturesOutcome;
  verdict: "won" | "lost" | null;
  historical?: boolean;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      {historical && (
        <span className="text-[10px] text-text-muted">Last recorded</span>
      )}
      {verdict ? (
        <SettledMark won={verdict === "won"} />
      ) : (
        <span className="font-mono text-sm font-semibold tabular-nums">
          {percentText(outcome.probability)}
        </span>
      )}
      <SourceMark />
    </span>
  );
}
function Identity({
  name,
  verdict,
}: {
  name: string;
  verdict?: "won" | "lost" | null;
}) {
  const initials = name
    .replace(/[^\p{L}\p{N}\s]/gu, "")
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w[0])
    .slice(0, 3)
    .join("");
  return (
    <div className="flex min-w-0 flex-1 flex-col items-center text-center">
      <div
        className="mb-1.5 flex h-14 w-14 items-center justify-center overflow-hidden rounded-2xl bg-surface-elevated text-sm font-extrabold text-text-secondary"
        aria-hidden
      >
        {initials}
      </div>
      <span className="max-w-[110px] text-xs font-semibold leading-snug text-text-primary">
        {name}
      </span>
      {verdict && (
        <span className="mt-2">
          <SettledMark won={verdict === "won"} />
        </span>
      )}
    </div>
  );
}
function Attribution({ sources }: { sources: string[] }) {
  const names: Record<string, string> = {
    kalshi: "Kalshi",
    polymarket: "Polymarket",
    odds_api: "Sportsbooks",
  };
  return (
    <span className="text-[10px] text-text-muted">
      {sources.map((s) => names[s] ?? s).join(" · ")}
    </span>
  );
}
export default function Prototype({
  data,
  initialStudy = "payload",
}: {
  data: PrototypeData;
  initialStudy?: StudyState;
}) {
  usePageTracking({ pageType: "futures_detail", pageTitle: data.detail.name });
  useScrollDepth({ pageType: "futures_detail" });
  useEngagementTime({ pageType: "futures_detail" });
  const { detail, history, sources } = data;
  const shape = bodyKind(detail);
  const ranked = useMemo(() => rankedOutcomes(detail), [detail]);
  const thresholds = useMemo(
    () =>
      [...detail.outcomes].sort(
        (a, b) =>
          parseFloat(a.name.replace(/[^\d.]/g, "")) -
          parseFloat(b.name.replace(/[^\d.]/g, "")),
      ),
    [detail.outcomes],
  );
  const [selectedId, setSelectedId] = useState(ranked[0].id);
  const [expanded, setExpanded] = useState(false);
  const [study, setStudy] = useState<StudyState>(initialStudy);
  const [range, setRange] = useState<ChartRangeKey>(
    initialStudy === "settled" ||
      (initialStudy === "payload" && detail.status === "resolved")
      ? "all"
      : "1W",
  );
  const [fullscreen, setFullscreen] = useState(false);
  const openerRef = useRef<HTMLButtonElement>(null);
  const selected =
    detail.outcomes.find((o) => o.id === selectedId) ?? ranked[0];
  const actualWinner = detail.outcomes.find(
    (o) => payloadVerdict(detail, o) === "won",
  );
  const isStudy = study !== "payload";
  const resolved =
    study === "settled" ||
    (study === "payload" && detail.status === "resolved");
  const lead = resolved && !isStudy ? (actualWinner ?? selected) : selected;
  const hasResult = resolved && (study === "settled" || !!actualWinner);
  const verdictFor = (o: FuturesOutcome): "won" | "lost" | null => {
    if (study === "open") return null;
    if (study === "settled") {
      if (shape === "participation")
        return ranked.indexOf(o) < 12 ? "won" : "lost";
      if (shape === "quantity")
        return thresholds.indexOf(o) <= thresholds.indexOf(selected)
          ? "won"
          : "lost";
      return o.id === selectedId ? "won" : "lost";
    }
    return payloadVerdict(detail, o);
  };
  const pair = renderedDuelPercents(
    ranked[0]?.probability,
    ranked[1]?.probability,
  );
  const category = CASES.find((c) => c.id === detail.id)!.category;
  const ranges = useMemo(() => availableRanges(history, false), [history]);
  const effectiveRange = ranges.some((r) => r.key === range) ? range : "all";
  const windowed = useMemo(
    () => windowOutcomeHistory(history, effectiveRange),
    [history, effectiveRange],
  );
  const focusedId =
    resolved && actualWinner && !isStudy ? actualWinner.id : selectedId;
  const chartSelection = useMemo(() => new Set([focusedId]), [focusedId]);
  const hasPath = windowed.some(
    (s) =>
      s.outcome_id === focusedId &&
      new Set(
        s.history
          .filter((p) => p.probability != null && p.bookmaker !== "settlement")
          .map((p) => p.timestamp),
      ).size >= 2,
  );
  const unknown = resolved && !hasResult;
  const shownRows = expanded
    ? ranked
    : ranked.slice(0, shape === "participation" ? 6 : 3);
  const heroOutcome: SettledOutcome | null = hasResult
    ? {
        winnerName: lead.name,
        winnerSide: null,
        resultLine: null,
        resultExplanation: null,
        resultKind: null,
        // Preview-only bridge: runtime provenance stays "market". The shared hero's
        // legacy type only lists score/tournament; no API or production type changes.
        authority: "market" as SettledOutcome["authority"],
      }
    : null;
  const chart = hasPath ? (
    <FuturesChart
      historyData={windowed}
      selectedOutcomes={chartSelection}
      fixedYAxis
      fieldCeiling={false}
      allowZoom={false}
      stepInterpolation={false}
      showCombinedProbability={false}
      height={fullscreen ? 520 : 380}
      fitToContainer
      greenTheme
      showLegend={false}
      showAxes
      settled={resolved && !isStudy}
      marketName={detail.name}
    />
  ) : (
    <div
      className="flex h-[380px] flex-col items-center justify-center gap-2 text-center"
      role="status"
    >
      <Info size={18} className="text-text-muted" />
      <p className="text-sm text-text-secondary">Not enough recorded history</p>
      <p className="max-w-[250px] text-xs leading-relaxed text-text-muted">
        A path needs more than one reading. Current threshold probabilities are
        shown above.
      </p>
    </div>
  );
  const railItems: EventConceptChild[] = data.related.map((m) => ({
    market_id: m.id,
    market_name: m.name,
    settled:
      m.status === "resolved" &&
      !!m.outcomes?.some((o) =>
        payloadVerdict({ status: "resolved" } as PrototypeData["detail"], o),
      ),
    graded_winner: m.outcomes?.find(
      (o) =>
        payloadVerdict({ status: m.status } as PrototypeData["detail"], o) ===
        "won",
    )?.name,
    outcomes: [{ name: m.lead, probability: m.probability }],
  }));
  return (
    <div
      className={`${styles.prototype} space-y-3`}
      data-testid="futures-event-grammar"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link
          href="/discover"
          className="inline-flex items-center gap-1 text-sm text-text-secondary hover:text-text-primary"
        >
          <ChevronLeft size={14} />
          Back to Discover
        </Link>
        <span className="text-[10px] text-text-muted">
          Snapshot · {datePT(data.capturedAt, true)}
          {isStudy ? ` · ${study} layout study` : ""}
        </span>
      </div>
      <section
        aria-label="Market overview"
        className="overflow-hidden rounded-card bg-surface-card shadow-card"
        data-testid="event-style-market-hero"
      >
        <div className="flex items-center justify-between gap-3 border-b border-surface-border/30 px-4 py-2 sm:px-5">
          <span
            className={`inline-flex items-center gap-1.5 text-[10px] font-semibold ${resolved ? "text-text-muted" : "text-accent-brand"}`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${resolved ? "bg-text-muted/50" : "bg-accent-brand"}`}
            />
            {resolved ? "Final" : "Open"}
            <span className="font-normal text-text-muted">· {category}</span>
          </span>
          <span className="text-[10px] text-text-muted">
            {resolved
              ? data.settledAt && !isStudy
                ? datePT(data.settledAt, true)
                : "Final state"
              : detail.resolution_date
                ? `Closes ${datePT(detail.resolution_date)}`
                : ""}
          </span>
        </div>
        <div className="px-5 py-4 sm:px-6 sm:py-5">
          <h1 className="mb-4 text-center text-[13px] font-semibold leading-snug text-text-primary">
            {detail.name.replace(/\?$/, "")}
          </h1>
          <div className="flex items-stretch justify-between">
            <Identity
              name={
                shape === "duel"
                  ? ranked[0].name
                  : shape === "quantity"
                    ? "Denver"
                    : lead.name
              }
              verdict={
                resolved && shape === "duel" ? verdictFor(ranked[0]) : null
              }
            />
            <div
              className={`${styles.pairedValues} flex min-w-0 shrink-0 flex-col items-center justify-center px-2 sm:px-4`}
            >
              {resolved ? (
                <div className="flex items-start gap-1.5">
                  <div>
                    <SettledOutcomeHero
                      outcome={heroOutcome}
                      hasNumericScore={false}
                      winnerPregameProb={null}
                    />
                    {unknown && (
                      <p className="mt-1 max-w-[170px] text-center text-sm font-semibold text-text-primary">
                        Result unavailable
                      </p>
                    )}
                  </div>
                  <SourceMark />
                </div>
              ) : (
                <EventHeroProbabilityPair
                  homeProb={lead.probability}
                  awayProb={shape === "duel" ? ranked[1].probability : null}
                  homePct={
                    shape === "duel"
                      ? pair[0]
                      : renderedPercent(lead.probability)
                  }
                  awayPct={shape === "duel" ? pair[1] : null}
                  awayWithheld={shape !== "duel"}
                  animate={false}
                />
              )}
              {!resolved && shape !== "duel" && (
                <span className="mt-1 text-[11px] text-text-secondary">
                  {shape === "participation"
                    ? "to qualify"
                    : shape === "quantity"
                      ? selected.name
                      : shape === "field"
                        ? "leads the field"
                        : "Yes"}
                </span>
              )}
              <div className="mt-2">
                <Attribution sources={sources} />
              </div>
            </div>
            {shape === "duel" ? (
              <Identity
                name={ranked[1].name}
                verdict={resolved ? verdictFor(ranked[1]) : null}
              />
            ) : (
              <div className="flex min-w-0 flex-1 flex-col items-center justify-center text-center">
                <span className="inline-flex items-center gap-1.5 text-2xl font-bold tabular-nums text-text-primary">
                  {shape === "quantity" ? "Dec" : detail.outcomes.length}
                  {shape !== "quantity" && <SourceMark />}
                </span>
                <span className="mt-1 text-[10px] text-text-muted">
                  {shape === "quantity"
                    ? "2026"
                    : shape === "participation"
                      ? "teams"
                      : shape === "field"
                        ? "states"
                        : "outcome"}
                </span>
              </div>
            )}
          </div>
        </div>
      </section>
      {(shape === "field" || shape === "participation") && (
        <section
          aria-label={
            shape === "field"
              ? "Full-field probabilities"
              : "Independent qualification band"
          }
          className="overflow-hidden rounded-card bg-surface-card shadow-card"
        >
          {shape === "participation" && (
            <p className="px-4 pt-4 text-xs text-text-secondary sm:px-6">
              Independent chances · these do not add to 100%. Several teams can
              qualify.
            </p>
          )}
          {resolved ? (
            <div className="px-4 py-3 sm:px-6">
              <h2 className="mb-3 text-[13px] font-semibold text-text-primary">
                Final outcomes
              </h2>
              {shownRows.map((o) => (
                <div
                  key={o.id}
                  className="flex items-center justify-between border-b border-surface-border/40 py-2.5"
                >
                  <span className="text-sm">{o.name}</span>
                  <Value outcome={o} verdict={verdictFor(o)} />
                </div>
              ))}
            </div>
          ) : (
            <div className={styles.nativeLeaderboard}>
              <EventLeaderboard
                key={`${detail.id}-${expanded}`}
                label={shape === "field" ? "The field" : "Chance to qualify"}
                competitors={shownRows.map((o) => ({
                  name: o.name,
                  probability: o.probability,
                }))}
                initialView="full"
                showSparkline={false}
                live={false}
              />
            </div>
          )}
          {(ranked.length > shownRows.length || expanded) && (
            <button
              type="button"
              onClick={() => setExpanded(!expanded)}
              aria-expanded={expanded}
              className="flex w-full items-center justify-center gap-1.5 border-t border-surface-border/40 py-3 text-xs font-medium text-text-secondary hover:bg-surface-elevated"
            >
              {expanded
                ? "Show fewer"
                : `${ranked.length - shownRows.length} more`}
              <ChevronDown size={12} className={expanded ? "rotate-180" : ""} />
            </button>
          )}
        </section>
      )}
      {shape === "quantity" && (
        <section
          className="overflow-hidden rounded-card bg-surface-card shadow-card"
          aria-label="Snowfall ladder"
        >
          <div className="px-4 py-3 sm:px-5">
            <h2 className="text-[13px] font-semibold text-text-primary">
              Snowfall thresholds
            </h2>
          </div>
          <div className="overflow-x-auto px-4 pb-4 sm:px-5">
            <div className="grid min-w-[570px] grid-cols-6 divide-x divide-surface-border/50">
              {thresholds.map((o) => (
                <button
                  key={o.id}
                  type="button"
                  onClick={() => setSelectedId(o.id)}
                  aria-pressed={selectedId === o.id}
                  className={`px-3 py-3 text-center ${selectedId === o.id ? "rounded-md bg-surface-elevated" : "hover:bg-surface-elevated/50"}`}
                >
                  <span className="mb-2 block text-[10px] text-text-muted">
                    {o.name}
                  </span>
                  <Value outcome={o} verdict={verdictFor(o)} />
                </button>
              ))}
            </div>
          </div>
          <p className="border-t border-surface-border/30 px-4 py-2.5 text-[11px] text-text-muted sm:px-5">
            Thresholds overlap; they are not shares of one total.
          </p>
        </section>
      )}
      {shape === "unshaped" && (
        <section
          className="overflow-hidden rounded-card bg-surface-card shadow-card"
          aria-label="One recorded outcome"
        >
          <div className="flex items-center justify-between px-4 py-3 sm:px-5">
            <h2 className="text-[13px] font-semibold text-text-primary">
              The outcome
            </h2>
            <span className="text-[10px] text-text-muted">1 outcome</span>
          </div>
          <div className="flex items-center justify-between border-t border-surface-border/30 px-4 py-3 sm:px-5">
            <span className="text-sm text-text-primary">Yes</span>
            <Value
              outcome={ranked[0]}
              verdict={verdictFor(ranked[0])}
              historical={unknown}
            />
          </div>
          <p className="px-4 pb-3 text-[11px] text-text-muted sm:px-5">
            One recorded outcome.
          </p>
        </section>
      )}
      <section
        className="overflow-hidden rounded-card bg-surface-card shadow-card"
        data-testid="win-probability-card"
        aria-labelledby="journey-heading"
      >
        <div className="relative flex items-center justify-between px-4 py-3 sm:px-5">
          <div className="flex min-w-0 items-center gap-3">
            <h2
              id="journey-heading"
              className="shrink-0 text-[13px] font-semibold text-text-primary"
            >
              {shape === "duel"
                ? "Win Probability"
                : shape === "participation"
                  ? "Qualification Probability"
                  : "Probability"}
            </h2>
            {!resolved && (
              <PriceAgeMark
                observedAt={lead.last_updated ?? detail.updated_at}
                cadence="futures"
                scope="card"
              />
            )}
          </div>
          <button
            type="button"
            ref={openerRef}
            onClick={() => setFullscreen(true)}
            className="rounded-md p-1.5 text-text-muted transition-colors hover:bg-surface-elevated hover:text-text-primary"
            aria-label="Open fullscreen chart"
            title="Open fullscreen chart"
          >
            <Maximize2 size={16} strokeWidth={1.5} />
          </button>
        </div>
        <div className="px-4 pb-1 pt-1 sm:px-5">
          <div className={styles.rangeChips}>
            <ChartRangeChips
              ranges={ranges}
              selected={effectiveRange}
              onSelect={setRange}
            />
          </div>
          <div className="mt-3" data-testid="event-composition-chart">
            {chart}
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-surface-border/30 px-4 py-2.5 sm:px-5">
          <span className="inline-flex items-center gap-1.5 text-[10px] text-text-muted">
            <span className="h-0.5 w-4 rounded bg-accent-brand" />
            {lead.name}
            <SourceMark />
          </span>
          <span className="inline-flex items-center gap-2">
            <Attribution sources={[detail.source ?? ""]} />
            <span className="text-[10px] text-text-muted">
              · recorded history
            </span>
          </span>
        </div>
        {data.historyNote && (
          <p className="border-t border-surface-border/20 px-4 py-2.5 text-[10px] leading-relaxed text-text-muted sm:px-5">
            {data.historyNote}
          </p>
        )}
        {isStudy && (
          <p className="px-4 pb-2.5 text-[10px] text-text-muted sm:px-5">
            {study === "settled"
              ? "Layout study only. Assumed results are not added to recorded history."
              : "Open layout study using the last recorded values. The market is resolved."}
          </p>
        )}
      </section>
      <div className={styles.relatedRail}>
        <MatchupsRail
          items={railItems}
          title="Bigger Picture"
          marketHref={(id) =>
            CASES.some((c) => c.id === id)
              ? `/kernels-preview/futures/${id}`
              : `/futures/${id}`
          }
        />
      </div>
      <details
        className="rounded-card border border-surface-border p-3 text-xs text-text-secondary"
        aria-label="Prototype review controls"
      >
        <summary className="cursor-pointer text-[11px] text-text-muted">
          Design preview · examples and state studies
        </summary>
        <nav
          aria-label="Prototype examples"
          className="mt-3 flex flex-wrap gap-1.5"
        >
          {CASES.map((c) => (
            <Link
              key={c.id}
              href={`/kernels-preview/futures/${c.id}`}
              className={`rounded-full px-2.5 py-1.5 ${c.id === detail.id ? "bg-text-primary text-surface-card" : "bg-surface-elevated"}`}
            >
              {c.label}
            </Link>
          ))}
        </nav>
        <div className="mt-3 flex items-center gap-2">
          <label htmlFor="study-state">Review state</label>
          <select
            id="study-state"
            value={study}
            onChange={(e) => {
              setStudy(e.target.value as StudyState);
              if (e.target.value === "settled") setRange("all");
            }}
            className="rounded-md border border-surface-border bg-surface-card px-2 py-1"
          >
            <option value="payload">As served</option>
            <option value="open">Open layout study</option>
            <option value="settled">Settled layout study</option>
          </select>
        </div>
        {isStudy && (
          <p className="mt-2 text-[11px] leading-relaxed">
            Layout study only.{" "}
            {study === "settled"
              ? shape === "participation"
                ? "The twelve leading teams are assumed to qualify; these are not production grades."
                : shape === "quantity"
                  ? "The selected threshold is assumed to be the last cleared; this is not a production grade."
                  : "The selected outcome is assumed to win; this is not a production grade."
              : "Uses last recorded numbers, not the production status."}
          </p>
        )}
      </details>
      {fullscreen && (
        <ChartFullscreenDialog
          title={shape === "duel" ? "Win Probability" : "Probability"}
          openerRef={openerRef}
          onClose={() => setFullscreen(false)}
        >
          <div className="mx-auto w-full max-w-[1200px] px-3">{chart}</div>
        </ChartFullscreenDialog>
      )}
    </div>
  );
}
