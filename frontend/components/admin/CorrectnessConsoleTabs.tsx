// #847 — the Correctness Console's Matching and Source Intelligence panels.
// Pure: each panel draws the sections `lib/correctnessConsoleTabs.ts` parsed,
// through the SAME presentation the standalone `/admin/matching` and
// `/admin/source-intelligence` pages use (`app/admin/_views/`). No fetch, no
// analytics hook — the console page owns its reads and its three GA hooks.
//
// What differs from the standalone pages is only what saved evidence obliges:
// every data section states which saved record answered and how old it is;
// a section with no trustworthy number says why instead of drawing zeros; and
// because no saved payload has a reviewed freshness horizon, the page-level
// verdict is shown as history ("was OK"), never as a current call.

import type { ReactNode } from "react";

import {
  MaturedLinkageCard,
  PredictionMarketDiagnosticSection,
  SourceContributionSection,
  SportCoverageSections,
  UnlinkedHeldCard,
  tier1Summary,
  type LinkRateData,
  type MaturedLinkageData,
  type MatchingStatus,
} from "@/app/admin/_views/MatchingView";
import SourceIntelligenceView, { siPageStatus } from "@/app/admin/_views/SourceIntelligenceView";
import { StateBadge } from "@/components/admin/CorrectnessConsole";
import type { SourceIntelligenceData } from "@/lib/api";
import { CORRECTNESS_ENDPOINTS, type CorrectnessState } from "@/lib/correctnessConsole";
import {
  TAB_READ_ENDPOINTS,
  sectionNoNumberText,
  sectionProvenance,
  sectionState,
  type SavedSection,
  type SportCardsSnapshot,
} from "@/lib/correctnessConsoleTabs";

const VERDICT: Record<MatchingStatus, CorrectnessState> = { good: "green", warning: "amber", critical: "red" };

/** The panel's state from its sections: a hit is never current. */
function panelState(sections: SavedSection<unknown>[]): CorrectnessState {
  const states = sections.map(sectionState);
  if (states.some((s) => s === "loading")) return "loading";
  if (states.every((s) => s === "unauthorized")) return "unauthorized";
  const hits = sections.filter((s) => s.kind === "hit").length;
  if (hits === 0) return "unavailable";
  if (hits < sections.length) return "partial";
  return states.includes("stale") ? "stale" : "freshness_unknown";
}

function TabHeader({
  question,
  subtitle,
  state,
  summary,
  verdictNote,
  ideal,
}: {
  question: string;
  subtitle: string;
  state: CorrectnessState;
  summary: string;
  verdictNote?: ReactNode;
  ideal: string;
}) {
  return (
    <div className="mb-2 text-left" data-tab-header="" data-state={state}>
      <h2 className="text-lg font-bold text-text-primary">{question}</h2>
      <p className="text-xs text-text-muted mt-0.5">{subtitle}</p>
      <div className="flex flex-wrap items-center gap-2 mt-2">
        <StateBadge state={state} />
        <span className="text-sm text-text-secondary break-words">{summary}</span>
      </div>
      {verdictNote && <p className="text-xs text-text-secondary mt-1">{verdictNote}</p>}
      <p className="text-xs text-text-muted mt-1.5">Target: {ideal}</p>
    </div>
  );
}

/** A section with no numbers: why, in words, with its state badge. */
export function SavedNotice({ section, what }: { section: SavedSection<unknown>; what: string }) {
  return (
    <div
      className="rounded-lg border border-surface-border bg-surface-elevated p-3 text-xs text-text-secondary break-words"
      data-notice={what}
      data-section-state={section.kind}
      role={section.kind === "loading" ? "status" : undefined}
    >
      <span className="mr-2 align-middle">
        <StateBadge state={sectionState(section)} />
      </span>
      {sectionNoNumberText(section)}
    </div>
  );
}

/** Which saved record answered, its age on this page's clock, and why it is not current. */
export function SavedProvenance({
  section,
  nowMs,
  endpoint,
  what,
  extra,
}: {
  section: Extract<SavedSection<unknown>, { kind: "hit" }>;
  nowMs: number;
  endpoint: string;
  what: string;
  extra?: string;
}) {
  const p = sectionProvenance(section, nowMs);
  return (
    <p
      className="text-[11px] text-text-muted break-words"
      data-provenance={what}
      data-served-from={section.servedFrom ?? ""}
      data-generated-at={section.generatedAt}
      data-freshness={section.freshness}
    >
      <span className="mr-1.5 align-middle">
        <StateBadge state={sectionState(section)} />
      </span>
      {what}: {p.record}, {p.built} · {p.freshness}
      {extra ? ` · ${extra}` : ""} · read in {section.ms} ms · {endpoint}
    </p>
  );
}

function windowText(s: SportCardsSnapshot): string {
  const start = new Date(s.windowStart).toISOString().replace(".000Z", "Z");
  return `events with commence_time ≥ ${start} (14 days before the snapshot), no upper bound — future games count`;
}

export function MatchingTabPanel({
  matured,
  sportCards,
  linkRate,
  nowMs,
  authNotice,
}: {
  matured: SavedSection<MaturedLinkageData>;
  sportCards: SavedSection<SportCardsSnapshot>;
  linkRate: SavedSection<LinkRateData>;
  nowMs: number;
  authNotice?: ReactNode;
}) {
  const sections = [matured, sportCards, linkRate] as SavedSection<unknown>[];
  const state = panelState(sections);
  const accuracy = sportCards.kind === "hit" ? sportCards.data.accuracy : null;
  const t1 = tier1Summary(accuracy);
  const summary =
    sportCards.kind === "hit"
      ? `${t1.linked}/${t1.total} Tier 1 events have Odds API data (${t1.pct}%)`
      : sectionNoNumberText(sportCards);
  return (
    <div className="max-w-4xl space-y-6" data-matching-panel="">
      <TabHeader
        question="Are events properly linked across data sources?"
        subtitle="Source linkage determines whether event pages show sportsbook odds, charts, and cross-source comparison."
        state={state}
        summary={summary}
        verdictNote={
          sportCards.kind === "hit" ? (
            <>
              The saved sport cards read <StateBadge state={VERDICT[t1.status]} muted /> — not a current verdict.
            </>
          ) : undefined
        }
        ideal="Every Tier 1 event should have Odds API, ESPN, and StatPal data."
      />
      {sections.some((s) => s.kind === "unauthorized") && authNotice}

      {matured.kind === "hit" ? (
        <>
          <MaturedLinkageCard
            data={matured.data}
            footer={
              <div className="mt-3">
                <SavedProvenance section={matured} nowMs={nowMs} endpoint={TAB_READ_ENDPOINTS.maturedLinkage} what="Matured linkage" />
              </div>
            }
          />
          {matured.data.unlinked_held && <UnlinkedHeldCard held={matured.data.unlinked_held} />}
        </>
      ) : (
        <div className="rounded-lg border border-surface-border bg-surface-card p-4" data-section="matured-linkage">
          <h2 className="text-sm font-semibold text-text-primary mb-2">
            Matured linkage <span className="text-text-muted font-normal">(headline)</span> and unlinked but held
          </h2>
          <SavedNotice section={matured} what="matured-linkage" />
        </div>
      )}

      <div className="space-y-2">
        {sportCards.kind === "hit" && (
          <SavedProvenance
            section={sportCards}
            nowMs={nowMs}
            endpoint={TAB_READ_ENDPOINTS.sportCards}
            what="Sport cards"
            extra={windowText(sportCards.data)}
          />
        )}
        <SportCoverageSections
          accuracy={accuracy}
          loading={sportCards.kind === "loading"}
          notice={sportCards.kind === "hit" ? undefined : <SavedNotice section={sportCards} what="sport-cards" />}
          verdictMuted
        />
      </div>

      <div className="space-y-2">
        {linkRate.kind === "hit" && (
          <SavedProvenance section={linkRate} nowMs={nowMs} endpoint={CORRECTNESS_ENDPOINTS.linkRate} what="Game-market link rate" />
        )}
        <PredictionMarketDiagnosticSection
          linkRate={linkRate.kind === "hit" ? linkRate.data : null}
          loading={linkRate.kind === "loading"}
          notice={linkRate.kind === "hit" ? undefined : <SavedNotice section={linkRate} what="link-rate" />}
          verdictMuted
        />
      </div>

      <SourceContributionSection verdictMuted />
    </div>
  );
}

export function SourceIntelligenceTabPanel({
  si,
  nowMs,
  authNotice,
}: {
  si: SavedSection<SourceIntelligenceData>;
  nowMs: number;
  authNotice?: ReactNode;
}) {
  const state = panelState([si]);
  const question = "Which probability source is most accurate?";
  const subtitle = "When sources disagree, who is right?";
  const ideal = "All sources measured. Best source identified per sport.";
  if (si.kind !== "hit") {
    return (
      <div className="max-w-3xl mx-auto space-y-4 pt-4" data-si-panel="">
        <TabHeader question={question} subtitle={subtitle} state={state} summary="Brier scores and calibration curves across all sources" ideal={ideal} />
        {si.kind === "unauthorized" && authNotice}
        <SavedNotice section={si} what="source-intelligence" />
      </div>
    );
  }
  const verdict = VERDICT[siPageStatus(si.data)];
  return (
    <div data-si-panel="">
      <SourceIntelligenceView
        data={si.data}
        header={
          <TabHeader
            question={question}
            subtitle={subtitle}
            state={state}
            summary="Brier scores and calibration curves across all sources"
            verdictNote={
              <>
                The saved snapshot read <StateBadge state={verdict} muted /> — not a current verdict.
              </>
            }
            ideal={ideal}
          />
        }
        updated={
          <div className="mt-2 text-left">
            <SavedProvenance section={si} nowMs={nowMs} endpoint={TAB_READ_ENDPOINTS.sourceIntelligence} what="Source Intelligence" />
          </div>
        }
      />
    </div>
  );
}
