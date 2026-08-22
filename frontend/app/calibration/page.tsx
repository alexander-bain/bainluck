"use client";

import { useState, useMemo } from "react";
import ErrorBoundary from "@/components/ErrorBoundary";
import Link from "next/link";
import useSWR from "swr";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { fetchCalibration, fetchCalibrationExamples, ApiError, CalibrationBucket, CalibrationExample } from "@/lib/api";
import ErrorState from "@/components/ErrorState";
import LoadingState from "@/components/LoadingState";
import CalibrationChart from "@/components/CalibrationChart";
import {
  buildSourcePanels,
  compareMatchedBuckets,
  describeActivityComparison,
  ece,
  mce,
  monthYear,
  MatchedBucketRow,
} from "@/lib/calibrationMath";
import { describeCohort, partitionByActivity } from "@/lib/calibrationCohort";
import {
  describeCategoryPopulation,
  describeCategoryTablePopulation,
} from "@/lib/calibrationPopulation";
import {
  anyNotProvable,
  provabilityPresentation,
  type ProvabilityCell,
} from "@/lib/calibrationProvability";
import {
  groupSourcesByProvider,
  shapeBreakdownIsSymmetric,
  SHAPE_BREAKDOWN_MIN_N,
} from "@/lib/calibrationProviders";
// UX-P078 (Alex ruling 2026-08-14(b) item 3): By Source is a panel per PROVIDER
// too, with the shape breakdown moved inside the provider it describes. The
// module header records the overturned CAL-P050 decision and the ruling-003
// reasoning behind the panel's ECE.
import {
  buildProviderPanels,
  providerKpiDetail,
  shapeBreakdownNote,
} from "@/lib/calibrationProviderPanels";
// CAL-P043 (#1643): the page's bucket math and its parity record live in one
// module so a gate can call the code the page actually renders from. They used
// to be private functions in this file, which is why the cross-surface gate had
// nothing to compare against but a constant.
import {
  aggregateBuckets,
  brierScore,
  buildCalibrationParity,
  cohortFilterFor,
  parityValue,
} from "@/lib/calibrationParity";
import {
  decideCalibrationContract,
  CONTRACT_REFUSAL_MESSAGE,
} from "@/lib/calibrationContract";
import {
  decideCalibrationStaleness,
  stalenessDriftClause,
  stalenessHeadline,
} from "@/lib/calibrationStaleness";
import { SOURCE_COLORS as SOURCE_COLOR_REGISTRY, canonicalSourceKey } from "@/lib/sourceColors";
// UX-P075 item (e): the category vocabulary moved to its own module so the
// raw-key guard can be TESTED — this page is a "use client" component behind
// SWR, and a guard that cannot call the function asserts against a copy of it.
import {
  DISPLAY_NAMES,
  categoryLabel,
  nicheCatLabel,
  normalizeCat,
} from "@/lib/calibrationCategories";

// L2-127 (Alex's Option 4): the 1,000-outcome floor USED to HIDE buckets from the
// By Source / By Category charts, which made a longshot category (golf, tennis)
// read like a broken page — a few dots in the corner. Alex's ruling: undo the
// hiding. This is now the THIN threshold, not a hide floor: buckets below it still
// render, as faded hollow dots with wide 95% CI bars (the existing n<30 visual
// convention, extended), so a casual reader sees "80% means 80%" with every bucket
// visible in its honest treatment — big solid dots = proven, ghost dots = small
// sample. Nothing is silently dropped.
const MIN_CHART_BUCKET_N = 1000;

// UX-P080 item 1 (Alex round 2). ONE sentence, in the card's own small grey
// detail slot. Alex's bar, quoted because it generalises past this card: "if it
// can't earn its sentence, it doesn't earn its card."
//
// A constant rather than a literal in the JSX so the FAQ entry further down the
// page and this card cannot drift into two different explanations of one
// number — the page already carries a longer FAQ answer, and two prose
// definitions of the same metric is how a reader learns to trust neither.
//
// NOT exported: a Next.js page module may only export `default`, `metadata` and
// the other framework names, and adding one more turns the generated route type
// in `.next/types/app/calibration/page.ts` red. Caught by `npm run typecheck`,
// which is why that gate runs AFTER the build (gotcha #10) — `next build` would
// have shipped this.
const BRIER_ONE_LINER =
  "how far our probabilities were from what happened, squared — " +
  "0 is perfect, coin-flipping scores 0.25";

// UX-P080 item 4 (Alex round 2): "Label every section with the cohort it draws
// from (traded / all) explicitly — Alex had to ask whether the category section
// is traded-only, and a reader shouldn't have to."
//
// The label is DERIVED from the live cohort object, never written beside it, so
// flipping the toggle relabels every section at once and no section can claim a
// cohort it is not drawing from. `calibrationAuditHooks.test.tsx` asserts the
// other half structurally: every cohort-drawing <h2> carries one of these, and
// a new section is untagged-by-default RED unless it is declared cohort-free.
function CohortTag({ cohort, scope }: {
  cohort: { key: string; shortLabel: string };
  scope?: "comparison";
}) {
  // The traded-vs-untraded section draws from BOTH sides — that comparison is
  // its entire subject — so labelling it with the active cohort would be a lie
  // in the one place the distinction is being explained.
  const text = scope === "comparison" ? "Traded vs untraded" : cohort.shortLabel;
  return (
    <span
      className="ml-2 align-middle text-[10px] uppercase tracking-wide text-text-muted border border-surface-border rounded px-1.5 py-0.5"
      data-testid="calibration-cohort-tag"
      data-cohort-key={scope === "comparison" ? "comparison" : cohort.key}
    >
      {text}
    </span>
  );
}

const COLORS = [
  "#2563eb", "#16a34a", "#dc2626", "#ea580c", "#7c3aed",
  "#db2777", "#0d9488", "#d97706", "#4f46e5", "#65a30d",
  "#0891b2", "#be185d", "#059669", "#9333ea", "#c2410c",
];

const SOURCE_DISPLAY_NAMES: Record<string, string> = {
  kalshi: "Kalshi",
  polymarket: "Polymarket",
  odds_api: "Odds API",
  odds_api_spreads: "Spreads (Odds API)",
  odds_api_totals: "Totals (Odds API)",
  odds_api_bookmaker: "Per-Bookmaker (Odds API)",
};

function sourceLabel(src: string): string {
  return SOURCE_DISPLAY_NAMES[src] || src;
}

interface DrillInState {
  source: string;
  bucketLabel: string;
  bucketIdx: number;
  loading: boolean;
  error: boolean;
  examples: CalibrationExample[];
  note?: string | null;
}

/** Queue 297: how old a served last-good snapshot is, in plain words. */
function formatAge(seconds: number): string {
  if (seconds < 90) return "moments";
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) return `${minutes} min`;
  const hours = Math.round(seconds / 3600);
  if (hours < 48) return `${hours} hr`;
  return `${Math.round(seconds / 86400)} days`;
}

export default function CalibrationPage() {
  usePageTracking({ pageType: "calibration", pageTitle: "Calibration" });
  useScrollDepth({ pageType: "calibration" });
  useEngagementTime({ pageType: "calibration" });

  const { data, error } = useSWR("calibration-data", fetchCalibration, {
    refreshInterval: 300000,
  });

  // UX-P078: this selects a PROVIDER now, not a source key. The shapes inside a
  // multi-shape provider are reached through that provider's disclosure, so the
  // tab strip and the panel grid stay the same three things.
  const [activeProvider, setActiveProvider] = useState<string | null>(null);
  const [activeCat, setActiveCat] = useState<string | null>(null);
  const priceCohort: "all" | "closing" | "opening" = "all";
  // L2-74 §C (#940) as re-named by L2-236: the page defaults to EXCLUDING the
  // outcomes whose price never moved off its opening line, and a visible toggle
  // layers them back in. The toggle never hides — counts are shown in both
  // states. (It used to be called the "thin/untraded" toggle, which described
  // neither side: those rows traded, they just never moved, and zero-bid
  // outcomes are already excluded upstream. See lib/calibrationCohort.ts.)
  const [includeNeverMoved, setIncludeNeverMoved] = useState(false);

  // L2-103 Item 2: per-bucket drill-in — click a point on the By Source chart to
  // sample the real outcomes inside it (reader-trust: verify any bucket yourself).
  const [drillIn, setDrillIn] = useState<DrillInState | null>(null);
  const openDrillIn = async (source: string, bucketLabel: string, bucketIdx: number) => {
    setDrillIn({ source, bucketLabel, bucketIdx, loading: true, error: false, examples: [] });
    try {
      // The API's `well_traded` flag is a wire contract with the backend and is
      // not renamed here; what it selects is the same `price_moved !== false`
      // cohort this page shows.
      const res = await fetchCalibrationExamples(source, bucketIdx, !includeNeverMoved);
      setDrillIn({
        source, bucketLabel, bucketIdx,
        loading: false, error: false,
        examples: res.examples, note: res.note ?? null,
      });
    } catch {
      setDrillIn({ source, bucketLabel, bucketIdx, loading: false, error: true, examples: [] });
    }
  };

  const normalized = useMemo(() => {
    if (!data) return null;
    return data.buckets.map(b => ({ ...b, category: normalizeCat(b.category) }));
  }, [data]);

  const overallBrier = useMemo(() => normalized ? brierScore(normalized) : 0, [normalized]);

  const movedBuckets = useMemo(() =>
    normalized ? aggregateBuckets(normalized, b => b.price_moved === true) : [], [normalized]);
  const unchangedBuckets = useMemo(() =>
    normalized ? aggregateBuckets(normalized, b => b.price_moved === false) : [], [normalized]);
  const movedN = useMemo(() => movedBuckets.reduce((s, b) => s + b.n, 0), [movedBuckets]);
  const unchangedN = useMemo(() => unchangedBuckets.reduce((s, b) => s + b.n, 0), [unchangedBuckets]);
  const movedECE = useMemo(() => ece(movedBuckets), [movedBuckets]);
  const unchangedECE = useMemo(() => ece(unchangedBuckets), [unchangedBuckets]);
  // L2-230 / C111 [P1]: one place decides what the split says, from the same
  // rounded values the stat cards print. See lib/calibrationMath.ts.
  const activity = useMemo(
    () => describeActivityComparison(
      { ece: movedECE, n: movedN },
      { ece: unchangedECE, n: unchangedN },
    ),
    [movedECE, movedN, unchangedECE, unchangedN]
  );

  // CAL-P025 / exit-exam item 2: the comparison the section now LEADS with.
  // The two cohorts differ in predicted-probability mix, so the gap between
  // their headline ECEs is part composition — `describeActivityComparison`'s
  // own comment says so and then correctly declines to claim more. Compared
  // bucket for bucket the mix is held fixed, and the picture is both narrower
  // and more specific. Computed off the RAW payload buckets, not `normalized`,
  // because the category rewrite above is irrelevant here and reading the
  // payload directly keeps this on exactly the rows the server published.
  const matched = useMemo(
    () => compareMatchedBuckets(data?.buckets ?? null),
    [data]
  );

  // L2-74 §C: the main chart/table exclude never-moved outcomes
  // (price_moved===false) by default; they keep real trades (true) AND sportsbook
  // consensus (null, always a live line, where "did trading move the price" is
  // not a question the source can answer). The toggle layers the excluded side
  // back in. The predicate is unchanged by L2-236 — only what we CALL it is.
  // CAL-P043: the predicate is `cohortFilterFor`'s, shared with the parity
  // record and mirrored by native, so the population this page renders and the
  // population it publishes cannot be two different things.
  const cohortFilter = useMemo(() => cohortFilterFor(includeNeverMoved), [includeNeverMoved]);
  const fullN = useMemo(() =>
    normalized ? normalized.reduce((s, b) => s + b.n, 0) : 0, [normalized]);
  const cohortBuckets = useMemo(() =>
    normalized ? aggregateBuckets(normalized, cohortFilter) : [], [normalized, cohortFilter]);
  const cohortMCE = useMemo(() => mce(cohortBuckets), [cohortBuckets]);
  const cohortECE = useMemo(() => ece(cohortBuckets), [cohortBuckets]);
  const cohortBrier = useMemo(() =>
    normalized ? brierScore(normalized, cohortFilter) : 0, [normalized, cohortFilter]);
  const cohortN = useMemo(() =>
    normalized ? normalized.filter(b => !cohortFilter || cohortFilter(b)).reduce((s, b) => s + b.n, 0) : 0,
    [normalized, cohortFilter]);

  // L2-236: `price_moved` is a TRI-state and this page modelled it as a boolean.
  // The default cohort is `true` PLUS `null` — 349,310 + 40,075 on the 2026-08-02
  // payload — and every rendered string called all 389,385 of them "well-traded
  // markets, where real trading moved the price". That was false for the 40,075
  // sportsbook rows, which were named nowhere: the activity section's two cards
  // summed to 612,332 against a stated population of 652,407.
  //
  // One pure module now derives every cohort-facing string from the partition,
  // so a label cannot drift from the predicate it describes. Same grammar native
  // shipped in L2-231; `lib/calibrationCohort.ts` carries the reasoning.
  const partition = useMemo(() =>
    partitionByActivity(normalized ?? []), [normalized]);
  const cohort = useMemo(() =>
    describeCohort(partition, fullN, includeNeverMoved),
    [partition, fullN, includeNeverMoved]);

  const sources = useMemo(() => {
    if (!normalized) return [];
    return [...new Set(normalized.map(b => b.source))].sort(
      (a, b) => normalized.filter(x => x.source === b).reduce((s, x) => s + x.n, 0)
        - normalized.filter(x => x.source === a).reduce((s, x) => s + x.n, 0)
    );
  }, [normalized]);

  // #997: minimum-sample bar comes from the API (Redis-tunable) so web + native
  // gate on the same threshold. Fall back to 1000 if an older cached payload or
  // the in-request fallback omits it — never regress to the noisy 100 floor.
  const minCategoryOutcomes = data?.min_category_outcomes ?? 1000;

  const categories = useMemo(() => {
    if (!normalized) return [];
    const catMap: Record<string, number> = {};
    for (const b of normalized) {
      catMap[b.category] = (catMap[b.category] || 0) + b.n;
    }
    return Object.entries(catMap)
      .filter(([, n]) => n >= minCategoryOutcomes)
      .sort(([, a], [, b]) => b - a)
      .map(([cat]) => cat)
      .slice(0, 15);
  }, [normalized, minCategoryOutcomes]);

  // Per-source metrics for the comparison section
  const sourceMetrics = useMemo(() => {
    if (!normalized) return [];
    return sources.map(src => {
      const srcBuckets = aggregateBuckets(normalized, b => b.source === src && (!cohortFilter || cohortFilter(b)));
      const srcN = normalized.filter(b => b.source === src && (!cohortFilter || cohortFilter(b))).reduce((s, b) => s + b.n, 0);
      const srcMCE = mce(srcBuckets);
      const srcECE = ece(srcBuckets);
      const srcBrier = brierScore(normalized, b => b.source === src && (!cohortFilter || cohortFilter(b)));
      const bucketsInBand = srcBuckets.filter(b => Math.abs(b.error) <= 5).length;
      return { source: src, n: srcN, mce: srcMCE, ece: srcECE, brier: srcBrier, bucketsInBand, totalBuckets: srcBuckets.length };
    });
  }, [normalized, sources, cohortFilter]);

  // Per-category metrics for the breakdown table
  // CAL-P067 item 4: the selection-bias verdict is computed BACKEND-side (it
  // needs the ungraded denominator, which never reaches the browser) and rides
  // on `by_category`. These rows are computed here from buckets, so the verdict
  // has to be joined on by category key. A category the backend did not annotate
  // simply carries no verdict, and `provabilityPresentation` renders that as the
  // pre-rule row — which is right: the backend states an absent census once, in
  // `provability_census`, rather than badging every row.
  const provabilityByCategory = useMemo(() => {
    const map = new Map<string, ProvabilityCell>();
    for (const cell of data?.by_category ?? []) {
      if (!cell?.category) continue;
      map.set(normalizeCat(cell.category), {
        provability: cell.provability,
        graded_share: cell.graded_share,
        provability_reason: cell.provability_reason,
      });
    }
    return map;
  }, [data]);

  // UX-P118 item 5: which PAYLOAD categories each displayed row is measured
  // over. Computed from `data.buckets` — the RAW keys — because `normalized`
  // has already applied `normalizeCat` and the pre-image is exactly what has
  // been lost by the time the table renders. On the 2026-08-21 payload this is
  // 2 rows of 128 (football, hockey), and hockey is the specimen the two-ECEs
  // disclosure was filed on.
  const pooledByCategory = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const b of data?.buckets ?? []) {
      const key = normalizeCat(b.category);
      const seen = map.get(key);
      if (seen) {
        if (!seen.includes(b.category)) seen.push(b.category);
      } else {
        map.set(key, [b.category]);
      }
    }
    return map;
  }, [data]);

  const categoryMetrics = useMemo(() => {
    if (!normalized) return [];
    return categories.map(cat => {
      const catBuckets = aggregateBuckets(normalized, b => b.category === cat && (!cohortFilter || cohortFilter(b)));
      const catN = normalized.filter(b => b.category === cat && (!cohortFilter || cohortFilter(b))).reduce((s, b) => s + b.n, 0);
      const catMCE = mce(catBuckets);
      const catECE = ece(catBuckets);
      const catBrier = brierScore(normalized, b => b.category === cat && (!cohortFilter || cohortFilter(b)));
      return {
        category: cat,
        n: catN,
        mce: catMCE,
        ece: catECE,
        brier: catBrier,
        ...(provabilityByCategory.get(cat) ?? {}),
      };
    });
  }, [normalized, categories, cohortFilter, provabilityByCategory]);

  // Queue 316 item 2: one row per PROVIDER, not per source key. Three of the
  // five live keys are the Odds API answering three question shapes, and the
  // table showed them as three unrelated "sportsbook" lines.
  //
  // The parent is computed the SAME way every other row on this page is —
  // pool the buckets, run the page's own metric over them — so it is a
  // measurement of the provider's own outcomes, never an average of the three
  // child summaries. That distinction is the whole reason this is safe: the
  // forbidden blend is fusing two same-shape sources' published figures, and
  // pooling buckets does not do that.
  const providerMetrics = useMemo(() => {
    if (!normalized) return [];
    return groupSourcesByProvider(sources).map(group => {
      const inGroup = (b: { source: string }) => group.sources.includes(b.source);
      const match = (b: { source: string }) =>
        inGroup(b) && (!cohortFilter || cohortFilter(b as CalibrationBucket));
      const groupBuckets = aggregateBuckets(normalized, match);
      const groupN = normalized
        .filter(match)
        .reduce((s, b) => s + b.n, 0);
      return {
        provider: group.provider,
        label: group.label,
        sources: group.sources,
        n: groupN,
        mce: mce(groupBuckets),
        ece: ece(groupBuckets),
        brier: brierScore(normalized, match),
      };
    });
  }, [normalized, sources, cohortFilter]);

  // Whether the shape breakdown may appear INLINE (Fable's symmetry addendum).
  // Measured from the live payload rather than asserted: on today's data Kalshi
  // and Polymarket publish one shape each, so it is false and the breakdown
  // lives in the per-source panels annex instead.
  const shapeInline = useMemo(
    () =>
      shapeBreakdownIsSymmetric(
        groupSourcesByProvider(sources),
        Object.fromEntries(sourceMetrics.map(sm => [sm.source, sm.n]))
      ),
    [sources, sourceMetrics]
  );

  // L2-232: may this build's labels go on this payload's numbers? Decided in one
  // pure place (`lib/calibrationContract.ts`) so the precedence between refusal
  // and the dated-degraded banner is a tested table rather than the order two
  // JSX conditionals happen to sit in. Last hook before the conditional returns.
  const contract = useMemo(() => decideCalibrationContract(data), [data]);

  // #2007 item 1b (CAL-P077). What must the reader be TOLD about this payload?
  // A different question from the contract's "may we label it at all", with a
  // different state set, so it is decided in its own pure module — and the
  // ordering between them stays in the JSX below, where a refusal returns
  // before this is ever rendered.
  //
  // Hook, and here, because every hook has to sit above the conditional returns.
  const staleness = useMemo(() => decideCalibrationStaleness(data), [data]);

  // CAL-P043 (#1643): the complete cross-surface parity record, built by the
  // same module the figures above come from and published below as `data-parity`
  // in native's grammar. Before this, web published these facts as a dozen
  // separate attributes and native published a single structured string, so the
  // two surfaces could not be compared without a translation table — and the
  // gate that claimed to compare them read neither (codex C236).
  //
  // Kept beside `contract` because it consumes the contract decision and both
  // must sit above the conditional returns.
  const parity = useMemo(
    () => (data ? buildCalibrationParity(data, includeNeverMoved, contract.state) : null),
    [data, includeNeverMoved, contract.state],
  );

  if (error) {
    // Queue 297 Item 1: the backend now answers a genuine outage with a TYPED
    // unavailable body instead of an opaque failure, so say what is actually
    // happening — the curve is rebuilt hourly and a retry is worth making.
    // Anything else still falls through to the generic error state.
    const detail = (error as ApiError).detail as
      | { status?: string; message?: string; reason?: string }
      | undefined;
    const unavailable = detail?.status === "unavailable";
    // A transport/backend failure outranks every payload-level check below: we
    // have no payload to judge. (Poison ordering, rung 1.)
    return (
      <CalibrationUnavailable
        stateName={unavailable ? (detail?.reason || "unavailable") : "load-failed"}
        contractState="no-payload"
        message={
          unavailable
            ? detail?.message ||
              "Calibration data is temporarily unavailable. It is rebuilt hourly — please retry shortly."
            : "Failed to load calibration data"
        }
        onRetry={() => window.location.reload()}
      />
    );
  }

  if (!data || !normalized) {
    return (
      <div className="max-w-6xl mx-auto" data-testid="calibration-loading">
        <LoadingState message="Loading calibration data..." />
      </div>
    );
  }

  // L2-232 Item 1. The payload arrived and parsed — and names a population this
  // build cannot label. Everything below this line renders numbers under THIS
  // build's descriptions, so this is where the page has to stop.
  //
  // Poison ordering, rung 2: this sits AFTER the transport error and the loading
  // state (no payload can be judged) and BEFORE the stale banner. A payload that
  // is both dated and incompatible must refuse, not render a mild "here's an
  // older snapshot" caveat wrapped around numbers we will not stand behind.
  if (!contract.render) {
    return (
      <CalibrationUnavailable
        stateName="population-contract-refused"
        contractState={contract.state}
        servedVersion={contract.servedVersion}
        message={CONTRACT_REFUSAL_MESSAGE}
      />
    );
  }

  // Built once, after the refusal gate, because it is only ever rendered inside
  // the banner. `null` when there is nothing honest to say about drift — which
  // is not the same as "no drift", and is why this returns null rather than "0".
  const driftClause = staleness ? stalenessDriftClause(staleness) : null;

  const topCats = categories.slice(0, 3).map(c =>
    `${categoryLabel(c)} (${normalized.filter(b => b.category === c).reduce((s, b) => s + b.n, 0).toLocaleString()})`
  ).join(", ");

  // L2-127 (Alex's Option 4): show EVERY populated bucket — no floor filter. A
  // small-sample bucket renders as a faded hollow dot with a wide 95% CI bar (the
  // thin convention, threshold = MIN_CHART_BUCKET_N), never silently hidden. The
  // label count is the full source/category total, as before.
  // UX-P078: the full-width view is a PROVIDER's pooled curve. Pooling here is
  // the same `aggregateBuckets` call the per-source view used, given the whole
  // provider's keys instead of one — not an average of three curves.
  const activeProviderGroup = activeProvider
    ? groupSourcesByProvider(sources).find(g => g.provider === activeProvider) ?? null
    : null;
  const providerChartData = activeProviderGroup
    ? [{
        data: aggregateBuckets(
          normalized,
          b => activeProviderGroup.sources.includes(b.source) && (!cohortFilter || cohortFilter(b)),
        ),
        color:
          SOURCE_COLOR_REGISTRY[canonicalSourceKey(activeProviderGroup.sources[0])]?.hex ||
          COLORS[0],
        label: `${activeProviderGroup.label} (${normalized
          .filter(b => activeProviderGroup.sources.includes(b.source) && (!cohortFilter || cohortFilter(b)))
          .reduce((s, b) => s + b.n, 0)
          .toLocaleString()})`,
      }]
    : [];

  // CAL-P025 / exit-exam item 4: the same per-source data, as small multiples.
  //
  // Overlaid, the five sources span 28x in n and 3.3x in ECE, so the two large
  // ones own every pixel and kalshi-vs-polymarket — the comparison a reader
  // most wants — is the hardest to see. Panels fix that, and `CalibrationChart`
  // fixes both axes at 0-100% structurally, so the axis is shared for free.
  //
  // What panels DON'T give for free is the size difference: equal-area frames
  // make a 12K curve look as authoritative as a 420K one. `buildSourcePanels`
  // is what puts n, share and ECE back on each frame.
  // Ruling 003: the panel's ECE is the SERVER's `by_source` number, rendered.
  // A client that recomputed it here would be the ruling's own named failure —
  // the same calibration number derived twice, guaranteed to drift.
  const publishedSourceEce = new Map(
    (data.by_source ?? []).map(m => [m.source, m.ece])
  );
  const sourcePanelBuckets = sources.map(src => ({
    source: src,
    buckets: aggregateBuckets(normalized, b => b.source === src && (!cohortFilter || cohortFilter(b))),
    publishedEce: publishedSourceEce.get(src) ?? null,
  }));
  const sourcePanels = buildSourcePanels(sourcePanelBuckets);
  const sourcePanelData = sourcePanels.map(p => ({
    ...p,
    data: sourcePanelBuckets.find(s => s.source === p.source)?.buckets ?? [],
    color: SOURCE_COLOR_REGISTRY[canonicalSourceKey(p.source)]?.hex || COLORS[0],
  }));

  // ── UX-P078 (Alex ruling 2026-08-14(b) item 3) ────────────────────────────
  // By Source is a panel per PROVIDER. The per-source panels above are not
  // discarded — they become the contents of the Sportsbooks disclosure, which
  // is how the annex's stated purpose survives inside the provider frame.
  //
  // The provider's ECE is read from `providerMetrics`, the SAME memo Source
  // Comparison renders, so the page derives it exactly once. See the module
  // header in `lib/calibrationProviderPanels.ts` for why that satisfies ruling
  // 003 rather than dodging it — and `calibrationProviderPanels.test.ts` for
  // the pairing assertion that makes the two renders unable to disagree.
  const providerGroups = groupSourcesByProvider(sources);
  const providerBucketsFor = (group: { sources: string[] }) =>
    aggregateBuckets(
      normalized,
      b => group.sources.includes(b.source) && (!cohortFilter || cohortFilter(b)),
    );
  const providerPanels = buildProviderPanels(
    providerGroups.map(group => ({
      provider: group.provider,
      label: group.label,
      sources: group.sources,
      buckets: providerBucketsFor(group),
      // Single-shape provider: provider IS the source key, so the server's own
      // published number is the panel's number, exactly as ruling 003 requires.
      publishedEce:
        group.sources.length === 1 ? publishedSourceEce.get(group.sources[0]) ?? null : null,
      // Multi-shape provider: the number already on the page, not a new one.
      pooledEce:
        group.sources.length > 1
          ? providerMetrics.find(pm => pm.provider === group.provider)?.ece ?? null
          : null,
    })),
  );
  const providerPanelData = providerPanels.map(p => ({
    ...p,
    data: providerBucketsFor({ sources: p.sources }),
    color: SOURCE_COLOR_REGISTRY[canonicalSourceKey(p.sources[0])]?.hex || COLORS[0],
    // The shape panels for this provider, in the order `buildSourcePanels`
    // already put them (largest first). Empty for a single-shape provider.
    shapes: p.hasShapeBreakdown
      ? sourcePanelData.filter(sp => p.sources.includes(sp.source))
      : [],
  }));
  const providerShapeNote = shapeBreakdownNote(providerPanels);

  const catChartData = (activeCat ? [activeCat] : categories.slice(0, 5)).map((cat, i) => ({
    data: aggregateBuckets(normalized, b => b.category === cat && (!cohortFilter || cohortFilter(b))),
    color: COLORS[i % COLORS.length],
    label: `${categoryLabel(cat)} (${normalized.filter(b => b.category === cat && (!cohortFilter || cohortFilter(b))).reduce((s, b) => s + b.n, 0).toLocaleString()})`,
  }));

  return (
    <ErrorBoundary fallback={<div className="p-8 text-center"><h2>Something went wrong</h2><button onClick={() => window.location.reload()} className="mt-2 text-sm text-accent-brand hover:underline">Reload page</button></div>}>
    {/* L2-231 Item 1: the page root carries the declared population contract as
        DATA, not prose. `data-population-version` is what lets the rail — and a
        native-parity check — prove web and iOS rendered the SAME payload
        contract, rather than two clients each rendering something plausible. */}
    <div
      className="max-w-6xl mx-auto space-y-8 pb-12"
      data-testid="calibration-page"
      data-population-version={data.population_version ?? ""}
      data-cache-status={data.cache?.status ?? "fresh"}
      /* L2-232: WHY the page considered itself allowed to render. "match" means
         the served version is one this build's labels describe; "unverified"
         means the payload named no population at all and is rendered without
         that claim. A refusal never reaches this element. */
      data-contract-state={contract.state}
      /* CAL-P043 (#1643): the COMPLETE parity record, in the same `key=value`
         grammar native publishes as the surface's accessibilityValue. Raw
         values only — a formatted figure ("1.5pp", "652,407") is a presentation
         decision, and a cross-surface check that compared those would fail on a
         thousands separator and pass on a wrong number. */
      data-parity={parity ? parityValue(parity) : ""}
    >
      {/* Queue 297 Item 1: when we are serving a last-good snapshot rather than a
          current one, say so and date it. A stale curve is fine; a stale curve
          presented as live is not.

          L2-232: gated on the contract decision, not on `cache.status` read
          again here — one place decides, so "degraded" can never outrank a
          refusal by virtue of being checked first. */}
      {staleness && (
        <div
          role="status"
          data-testid="calibration-stale-banner"
          data-staleness-kind={staleness.kind}
          data-cache-reason={data.cache?.reason ?? ""}
          data-generated-at={data.cache?.generated_at ?? ""}
          /* An undated last-good still banners — dropping it would lose the
             honesty signal entirely — but it cannot say WHEN, and the rail
             should be able to tell those two apart. */
          data-degraded-dated={contract.degradedDated ? "true" : "false"}
          /* #2007 item 1b: the input as-of and the drift, as DATA. A rail that
             had to parse the sentence to check them would break on a comma. */
          data-staged-at={staleness.stagedAt ?? ""}
          data-units-drifted={
            staleness.unitsDrifted === null ? "" : String(staleness.unitsDrifted)
          }
          data-units-banked={
            staleness.unitsBanked === null ? "" : String(staleness.unitsBanked)
          }
          data-availability={data.availability ?? ""}
          className="rounded-lg border border-surface-border bg-surface-card px-4 py-3 text-sm text-text-secondary"
        >
          <strong className="text-text-primary">{stalenessHeadline(staleness)}</strong>{" "}
          {staleness.kind === "last-good" && (
            <>
              These numbers were built{" "}
              {staleness.generatedAt
                ? new Date(staleness.generatedAt).toLocaleString("en-US", {
                    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
                  })
                : "earlier"}
              {staleness.ageS !== null && ` (${formatAge(staleness.ageS)} ago)`}
              {" "}and are not being refreshed right now. The curve rebuilds hourly.
            </>
          )}
          {/* #2007 item 1b, Fable ruling (c). The old sentence — "not being
              refreshed right now" — is FALSE here and pointed a reader at a
              problem that would appear to fix itself on the next beat. The
              curve is rebuilt every hour, on time. What is dated is the market
              census underneath it. */}
          {staleness.kind === "frozen-inputs" && (
            <>
              The curve was rebuilt on schedule, but the market data behind it was last
              staged{" "}
              {staleness.stagedAt
                ? new Date(staleness.stagedAt).toLocaleString("en-US", {
                    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
                  })
                : "earlier"}
              {staleness.stagedAgeS !== null && ` (${formatAge(staleness.stagedAgeS)} ago)`}
              {driftClause ? `, and ${driftClause}` : ""}. It catches up as the backlog
              re-stages.
            </>
          )}
          {staleness.kind === "undisclosed" && (
            <>
              The curve rebuilds hourly, but we couldn&rsquo;t read when the market data
              behind it was last staged. We&rsquo;d rather say so than call these numbers
              current.
            </>
          )}
        </div>
      )}

      {/* Hero */}
      <div className="text-center space-y-3 pb-6 border-b border-surface-border">
        <h1 className="text-title-1 text-text-primary">Do Prediction Markets Predict Anything?</h1>
        <p className="text-text-secondary max-w-2xl mx-auto">
          We analyzed {cohort.heroClause} across
          Kalshi, Polymarket, and sportsbook odds (moneylines, spreads, and totals). The answer: when markets say
          something has a 30% chance of happening, it happens about 30% of the time.
        </p>
        {/* Queue 316 item 3. The greeting is a sentence a person can check; the
            precision sits one click away rather than in front of it. The value
            is read from the payload, never transcribed, so it stays true when
            the hourly rebuild moves it. */}
        <p className="text-text-primary max-w-2xl mx-auto" data-testid="calibration-plain-headline"
          data-plain-ece={cohortECE}>
          Across every market we track, prices land{" "}
          <strong>within about {cohortECE.toFixed(1)} percentage points</strong> of what actually
          happened.
        </p>
        <details className="max-w-2xl mx-auto text-left" data-testid="calibration-show-the-math">
          <summary className="cursor-pointer text-xs text-accent-brand hover:underline text-center list-none">
            Show the math
          </summary>
          <div className="mt-3 space-y-2 text-xs text-text-muted bg-surface-card rounded-lg p-4 border border-surface-border">
            <p>
              That figure is <strong className="text-text-secondary">ECE</strong> (expected
              calibration error), n-weighted: every resolved outcome counts once, so the number
              reflects what readers actually saw rather than treating a 12-outcome bucket as the
              equal of a 40,000-outcome one.{" "}
              {priceCohort === "all" && (
                <>95% confidence interval on the worst-bucket figure:{" "}
                <span className="tabular-nums text-text-secondary">
                  {data.mce_ci_lower.toFixed(1)}&ndash;{data.mce_ci_upper.toFixed(1)}pp
                </span>.{" "}</>
              )}
              Worst-bucket error (MCE, equal-weighted){" "}
              <span className="tabular-nums text-text-secondary">{cohortMCE.toFixed(1)}pp</span>;
              Brier <span className="tabular-nums text-text-secondary">{cohortBrier.toFixed(4)}</span>.
            </p>
            <p>
              Population: <span className="tabular-nums text-text-secondary">{cohortN.toLocaleString()}</span>{" "}
              resolved outcomes{cohortN !== fullN && <> of <span className="tabular-nums text-text-secondary">{fullN.toLocaleString()}</span> total</>}
              {" "}&middot; {sources.length} sources &middot; {categories.length} categories.{" "}
              <a href="#methodology" className="text-accent-brand hover:underline">
                How we measure this
              </a>{" "}
              covers which price we use, who we count as the winner, and every exclusion.
            </p>
          </div>
        </details>
        <p className="text-xs text-text-muted" data-testid="calibration-generated-at"
          data-generated-at={data.generated_at ?? ""}>
          {data.date_range?.start && data.date_range?.end
            ? `Data ${monthYear(data.date_range.start)}–${monthYear(data.date_range.end)}`
            : `${data.total_outcomes.toLocaleString()} resolved outcomes`}
          {" · Updated "}
          {data.generated_at
            ? new Date(data.generated_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })
            : "hourly"}
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {/* The population count the page LEADS with is the cohort count, not
            total_outcomes — the two differ whenever the thin toggle is off, and
            a native surface reading the other one diverges silently. Both are
            published here as data so the parity check reads numbers, not text. */}
        <div data-testid="calibration-population-count" data-cohort-n={cohortN} data-full-n={fullN}>
          <StatCard label="Resolved Outcomes" value={cohortN.toLocaleString()}
            testId="calibration-stat-outcomes"
            detail={cohort.statDetail} />
        </div>
        {/* CAL-P043 (#1643): MCE used to exist on this surface ONLY inside the
            detail PROSE — "worst-bucket (MCE) 1.5pp" — while native published
            ECE and MCE as two raw numbers. Same figure, two incomparable
            protocols behind matching hook names, which is codex C236's second
            P1. Both are published as raw data here. */}
        <div data-testid="calibration-stat-ece-figures"
          data-ece={cohortECE} data-mce={cohortMCE}>
          {/* Queue 316 item 3: the card leads with what the number MEANS. The
              metric's name, its sibling figures and the CI have not been
              removed — they moved into the disclosure under the hero, because
              "Calibration Error (ECE) 1.2pp" is a label only a reader who
              already knows the answer can parse. */}
          <StatCard label="How far off, on average"
            testId="calibration-stat-ece"
            value={`${cohortECE.toFixed(1)}pp`}
            detail={`percentage points · ${cohortECE < 3 ? "close" : "wide"} · see “show the math”`}
            valueClass={cohortECE < 3 ? "text-green-600" : cohortECE < 5 ? "text-blue-600" : "text-orange-600"} />
        </div>
        {/* UX-P080 item 1 (Alex round 2): "explain it in ONE sentence of small
            grey text, or exclude it from the headline row. If it can't earn its
            sentence, it doesn't earn its card." It earns it — the sentence is
            below, in the card's own 11px muted detail slot. What it replaces,
            "0 = oracle, lower = better", is not an explanation: it tells a
            reader which direction is good without ever saying what the number
            measures, which is the shape of every metric label this page has
            been walking back (ruling 044 — rendered-green is not
            communicates-green; banked against this page by name). */}
        <StatCard label="Brier Score" value={cohortBrier.toFixed(4)}
          testId="calibration-stat-brier"
          detail={BRIER_ONE_LINER} />
        {/* UX-P080 item 2: counts PROVIDERS, from the same `providerGroups` the
            two tables below are built from — so the card cannot say 5 while
            they say 3. The shapes are named in the subtext rather than dropped. */}
        <StatCard label="Sources" value={String(providerGroups.length)}
          testId="calibration-stat-sources"
          detail={providerKpiDetail(providerGroups, sourceLabel)} />
        <StatCard label="Categories" value={String(categories.length)}
          testId="calibration-stat-categories"
          detail={topCats} />
      </div>

      {/* Cohort toggle (L2-74 §C, #940; renamed L2-236) — governs every table +
          curve below. Both the headline and the sentence under it come from
          `describeCohort`, so the words are derived from the cohort's predicate
          rather than written beside it. The partition is published as data too:
          a rail can then check the arithmetic without parsing prose. */}
      <div
        className="flex flex-wrap items-center gap-3 bg-surface-card rounded-xl px-4 py-3 border border-surface-border"
        data-testid="calibration-cohort-toggle"
        data-cohort-key={cohort.key}
        data-moved-n={partition.movedN}
        data-unchanged-n={partition.unchangedN}
        data-not-applicable-n={partition.notApplicableN}
        data-partition-reconciles={cohort.reconciles ? "true" : "false"}
      >
        <div className="text-sm text-text-secondary">
          <strong className="text-text-primary">{cohort.headline}</strong>{" "}
          {cohort.detail}
        </div>
        <button
          onClick={() => setIncludeNeverMoved(v => !v)}
          className="ml-auto text-xs font-medium px-3 py-1.5 rounded-full border border-surface-border text-text-secondary hover:text-text-primary hover:border-text-muted transition-colors whitespace-nowrap"
        >
          {cohort.toggleLabel}
        </button>
        {/* UX-P075 item (a), and it is the half of that item that does the
            work. Alex ruled the cohort renamed to "traded"/"untraded" AND the
            proxy footnote kept — the short word is for the reader, this is what
            stops it becoming a claim we cannot support. It sits inside the same
            banner as the word, full-width beneath it, because a caveat a scroll
            away from its term is a caveat that is not read.
            `lib/calibrationCohort.ts` carries the reversal of L2-236's
            contrary decision, in the open, per ruling 055. */}
        {cohort.proxyFootnote && (
          <p
            className="basis-full text-xs text-text-muted"
            data-testid="calibration-proxy-footnote"
          >
            {cohort.proxyFootnote}
          </p>
        )}
      </div>

      {/* Source Comparison */}
      <section className="bg-surface-card rounded-xl p-5 border border-surface-border">
        <h2 className="text-title-3 text-text-primary mb-1">Source Comparison<CohortTag cohort={cohort} /></h2>
        <p className="text-xs text-text-muted mb-4">
          How each data source performs independently, sorted by ECE.{" "}
          <strong className="text-text-secondary">ECE</strong> (n-weighted error) is the headline
          metric &mdash; it reflects the outcomes users actually see. MCE (equal-weighted) is a
          secondary &ldquo;worst-bucket sensitivity&rdquo; stat where a tiny bucket counts as much
          as a huge one. Lower is better.
        </p>
        {/* Queue 316 item 2. One row per provider, and the row says which source
            keys it pooled — so the collapse is legible instead of being a
            relabelling the reader has to take on trust. */}
        <p className="text-xs text-text-muted mb-4" data-testid="calibration-provider-note">
          Each row is one <strong className="text-text-secondary">data provider</strong>, measured
          by pooling its outcomes and running the same calculation used for every other row.
          {shapeInline ? null : (
            <>
              {" "}Sportsbook odds arrive in three shapes (moneylines, spreads, totals); the
              prediction markets publish a single shape each, so a per-shape column here would
              exist for one provider and be blank for the others. The shape-by-shape breakdown is
              in <a href="#by-source" className="text-accent-brand hover:underline">By Source</a>{" "}
              below &mdash; open &ldquo;Break out the shapes&rdquo; inside the Sportsbooks panel to
              see all {sources.length} keys separately.
            </>
          )}
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-text-muted uppercase tracking-wide">
                <th className="pb-2 pr-4">Source</th>
                <th className="pb-2 pr-4 text-right">Outcomes</th>
                <th className="pb-2 pr-4 text-right">ECE</th>
                <th className="pb-2 pr-4 text-right" title="Max/worst-bucket sensitivity (equal-weighted): a small bucket counts as much as a large one, so it over-reacts to thin samples.">
                  MCE&nbsp;<span className="text-text-muted/60">&#9432;</span>
                </th>
                <th className="pb-2 text-right">Brier</th>
              </tr>
            </thead>
            <tbody>
              {[...providerMetrics].sort((a, b) => a.ece - b.ece).map(pm => (
                <tr
                  key={pm.provider}
                  className="border-t border-surface-border"
                  data-testid="calibration-provider-row"
                  data-provider={pm.provider}
                  data-provider-n={pm.n}
                  data-provider-sources={pm.sources.join(",")}
                >
                  <td className="py-2.5 pr-4 font-medium text-text-primary">
                    {pm.label}
                    {pm.sources.length > 1 && (
                      <span className="block text-xs font-normal text-text-muted">
                        {pm.sources.map(sourceLabel).join(" · ")}
                      </span>
                    )}
                  </td>
                  <td className="py-2.5 pr-4 text-right tabular-nums">{pm.n.toLocaleString()}</td>
                  <td className={`py-2.5 pr-4 text-right tabular-nums font-semibold ${
                    pm.ece < 3 ? "text-green-600" : pm.ece < 5 ? "text-blue-600" : "text-orange-600"
                  }`}>
                    {pm.ece.toFixed(1)}pp
                  </td>
                  <td className="py-2.5 pr-4 text-right tabular-nums text-text-muted">
                    {pm.mce.toFixed(1)}pp
                  </td>
                  <td className="py-2.5 text-right tabular-nums">{pm.brier.toFixed(4)}</td>
                </tr>
              ))}
              <tr className="border-t-2 border-surface-border font-semibold">
                <td className="py-2.5 pr-4 text-text-primary">Combined</td>
                <td className="py-2.5 pr-4 text-right tabular-nums">{cohortN.toLocaleString()}</td>
                <td className={`py-2.5 pr-4 text-right tabular-nums ${
                  cohortECE < 3 ? "text-green-600" : cohortECE < 5 ? "text-blue-600" : "text-orange-600"
                }`}>
                  {cohortECE.toFixed(1)}pp
                </td>
                <td className="py-2.5 pr-4 text-right tabular-nums text-text-muted">
                  {cohortMCE.toFixed(1)}pp
                </td>
                <td className="py-2.5 text-right tabular-nums">{cohortBrier.toFixed(4)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* How We Compare */}
      <section className="bg-surface-card rounded-xl p-5 border border-surface-border">
        <h2 className="text-title-3 text-text-primary mb-1">How We Compare</h2>
        <p className="text-xs text-text-muted mb-4">
          Our aggregate MCE compared to published calibration benchmarks from academic research and forecasting platforms.
        </p>
        <div className="space-y-3">
          {[
            { label: priceCohort === "closing" ? "Bain Luck (closing line)" : priceCohort === "opening" ? "Bain Luck (opening price)" : "Bain Luck (all sources)", mce: cohortMCE, n: cohortN, highlight: true, ci: priceCohort === "all" ? `${data.mce_ci_lower.toFixed(1)}-${data.mce_ci_upper.toFixed(1)}pp` : undefined },
            { label: "Metaculus (self-reported)", mce: 2.5, n: null, highlight: false },
            { label: "Iowa Electronic Markets (Berg et al. 2008)", mce: 1.5, n: null, highlight: false },
            { label: "Academic consensus range (Arrow et al. 2008)", mce: 3.5, n: null, highlight: false, range: "2-5pp" },
          ].map(row => {
            const barWidth = Math.min(100, (row.mce / 10) * 100);
            return (
              <div key={row.label}>
                <div className="flex justify-between items-baseline text-sm mb-1">
                  <span className={row.highlight ? "font-semibold text-text-primary" : "text-text-secondary"}>
                    {row.label}
                  </span>
                  <span className={`tabular-nums text-xs ${
                    row.mce < 4 ? "text-green-600" : row.mce < 6 ? "text-blue-600" : "text-orange-600"
                  } font-semibold`}>
                    {row.range || `${row.mce.toFixed(1)}pp`}
                    {"ci" in row && row.ci ? ` (95% CI: ${row.ci})` : ""}
                    {row.n ? ` | ${row.n.toLocaleString()} outcomes` : ""}
                  </span>
                </div>
                <div className="h-2 bg-surface-secondary rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${row.highlight ? "bg-blue-500" : "bg-text-muted"}`}
                    style={{ width: `${barWidth}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
        <p className="text-xs text-text-muted mt-4">
          Lower is better. Most prediction markets achieve 2-5pp MCE. Values below 4pp are considered excellent calibration.
        </p>
      </section>

      {/* Calibration curve + trading-activity story (L2-80 Item 2: merged into ONE
          section. The standalone default-cohort curve was redundant — the
          page-level toggle banner above already carries the default cohort, and
          the split curve's green "price moved" series is most of it. Falls back to
          a single cohort curve when the moved/unchanged split isn't available, so
          the page always shows a headline curve.) */}
      {movedN > 0 && unchangedN > 0 ? (
        <section
          className="bg-surface-card rounded-xl p-5 border border-surface-border"
          data-testid="calibration-activity-section"
          data-activity-direction={activity.direction}
        >
          {/* Queue 316 item 4. The heading asked about TRADING; the data is
              whether a PRICE MOVED. Those are not the same claim, and the gap
              between them is the whole reason this section needed rewording:
              we do not receive trade counts, we observe the price. Naming the
              stand-in as a stand-in is the honest version, and it also keeps
              the third state speakable — sportsbook lines carry no flag at
              all, which a "traded / didn't trade" framing cannot express. */}
          <h2 className="text-title-3 text-text-primary mb-1">
            Does a price that moves predict better?
            <CohortTag cohort={cohort} scope="comparison" />
          </h2>
          <p className="text-xs text-text-muted mb-4">
            We don&rsquo;t receive trading volume for most of these markets, so we use{" "}
            <strong>whether the price changed at all</strong> as the stand-in for whether anyone was
            actively trading. It is a proxy, not a measurement of activity. Compared{" "}
            <strong>bucket for bucket</strong>, so both groups are judged on outcomes we priced the
            same. That matters: the two groups have different predicted-probability mixes, so any
            gap between their overall figures is partly a difference in what they contain rather
            than in how they behaved.
          </p>

          {/* CAL-P025 / exit-exam item 2. The section used to lead with two
              cross-cohort ECE tiles, and the prose beneath them had to spend a
              sentence warning the reader not to read them as an effect. This
              table is that warning, discharged: same-bucket rows, so the
              composition difference is held fixed and only the residual is
              left. The tiles are kept below as supporting detail — demoted,
              not deleted; they are still the honest aggregate. */}
          {matched.widest ? (
            <div className="mb-5" data-testid="calibration-matched-buckets">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-text-muted border-b border-surface-border">
                      <th className="py-2 pr-4 font-medium">Predicted</th>
                      {/* UX-P075 item (c): one vocabulary. These columns said
                          "Price moved"/"Price unchanged" while the toggle above
                          them said something else again — same two cohorts,
                          three namings on one page. */}
                      <th className="py-2 pr-4 font-medium text-right">Traded</th>
                      <th className="py-2 pr-4 font-medium text-right">Untraded</th>
                      <th className="py-2 font-medium text-right">Difference</th>
                    </tr>
                  </thead>
                  <tbody>
                    {matched.rows.map(row => (
                      <MatchedBucketTableRow
                        key={row.bucketIdx}
                        row={row}
                        widest={row.bucketIdx === matched.widest?.bucketIdx}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
              <p
                className="text-sm text-text-secondary mt-3"
                data-testid="calibration-matched-sentence"
                data-widest-bucket={matched.widest.bucketIdx}
                data-widest-gap-pp={matched.widest.gapPp ?? ""}
                data-compared-n={matched.comparedN}
                data-close-count={matched.closeCount}
              >
                {matched.sentence}
              </p>
              <p className="text-xs text-text-muted mt-2">
                Error is actual minus predicted, in percentage points: negative = the outcome
                happened <em>less</em> often than the price implied. Rows where either side is
                below {MIN_CHART_BUCKET_N.toLocaleString()} outcomes are shown but greyed &mdash;
                too thin to carry a comparison. A dash means only one cohort reaches that bucket,
                so there is no matched pair to compare.
              </p>
            </div>
          ) : (
            <p className="text-xs text-text-muted mb-5" data-testid="calibration-matched-unavailable">
              No bucket has enough outcomes on both sides of the split to compare like with like,
              so only the overall figures are shown below.
            </p>
          )}

          {/* UX-P075 item (b) — Alex, 2026-08-13: the section keeps ONLY the
              bucket-matched table; the redundant cohort chart is "cut, or
              collapsed to a toggle".

              COLLAPSED, and the choice is deliberate rather than lazy. Cutting
              the chart alone would leave the two aggregate cards orphaned above
              nothing; cutting the whole block would delete L2-236's population
              reconciliation, the fix for a real 40,075-row shortfall. So the
              redundant block goes behind one disclosure, closed by default —
              default view is the matched table and nothing else, which is what
              the instruction asked for, and the honest aggregate is one click
              away rather than gone. The partition note is deliberately left
              OUTSIDE the fold; see below. */}
          <details className="mt-2 group" data-testid="calibration-overall-split">
            <summary className="cursor-pointer text-sm font-semibold text-text-primary hover:text-accent-brand list-none flex items-center gap-2">
              <span className="text-text-muted text-xs group-open:rotate-90 transition-transform">&#9654;</span>
              The overall split, as two whole cohorts
            </summary>
            <p className="text-xs text-text-muted mt-2 mb-4">
              The same data without the bucket matching, which is how this section used to lead.
              Points on the diagonal = perfect calibration; above = outcomes happened <em>more</em>{" "}
              than predicted, below = <em>less</em>. Shaded band = &plusmn;5pp and point size
              reflects sample count. Because the two cohorts differ in source, category and
              market-shape mix, whichever side lands lower here is an observed ordering &mdash; not
              evidence that trading caused it. <strong className="text-text-secondary">The table
              above is the version that controls for that</strong>, which is why this one is folded
              away rather than shown beside it.
            </p>
            <CalibrationChart
              series={[
                { data: movedBuckets, color: "#16a34a", label: `Traded (${movedN.toLocaleString()})` },
                { data: unchangedBuckets, color: "#dc2626", label: `Untraded (${unchangedN.toLocaleString()})` },
              ]}
              width={700}
              height={400}
              thinFloor={MIN_CHART_BUCKET_N}
            />
          {/* L2-230: the value colour is part of the claim. Hard-coding moved
              green and unchanged orange asserted "moved is better" in pixels
              even on the day moved measured 1.7pp against unchanged's 1.0pp,
              so it follows the same direction the sentence below does. */}
          <div className="grid grid-cols-2 gap-3 mt-4">
            {/* UX-P075 item (c): "Active Trading" / "Opening Price Only" were a
                fourth and fifth name for the same two cohorts. */}
            <StatCard label="Traded"
              testId="calibration-activity-moved"
              value={`${movedECE.toFixed(1)}pp`}
              detail={`${movedN.toLocaleString()} outcomes`}
              valueClass={
                activity.direction === "moved_higher" ? "text-orange-600"
                  : activity.direction === "unchanged_higher" ? "text-green-600"
                    : "text-text-primary"
              } />
            <StatCard label="Untraded"
              testId="calibration-activity-unchanged"
              value={`${unchangedECE.toFixed(1)}pp`}
              detail={`${unchangedN.toLocaleString()} outcomes`}
              valueClass={
                activity.direction === "unchanged_higher" ? "text-orange-600"
                  : activity.direction === "moved_higher" ? "text-green-600"
                    : "text-text-primary"
              } />
          </div>
          {activity.sentence && (
            <p
              className="text-sm text-text-secondary mt-3 text-center"
              data-testid="calibration-activity-sentence"
            >
              {activity.sentence}
            </p>
          )}
          {/* L2-236: the two cards above are `price_moved === true` and
              `=== false`. The `null` rows — sportsbook lines, where the test
              does not apply — were named nowhere, so the two counts silently
              fell 40,075 short of the population this page claims. */}
          </details>

          {/* DELIBERATELY OUTSIDE the disclosure above, and this is the one
              judgment call in item (b). Alex asked for the redundant COHORT
              CHART to be folded away; this note is not that chart, it is the
              page's population arithmetic — the only place a reader can check
              that the parts add up (L2-236's fix for a real 40,075-row
              shortfall). Folding it would also have hidden it from the browser
              rail, whose strongest claim on this page reads it: `innerText`
              does not return a closed `<details>`, so the fold would have
              turned a rendered proof into a silent one. */}
          {cohort.partitionNote && (
            <p
              className="text-xs text-text-muted mt-3 text-center"
              data-testid="calibration-activity-partition"
            >
              {cohort.partitionNote}
            </p>
          )}
        </section>
      ) : (
        <section className="bg-surface-card rounded-xl p-5 border border-surface-border">
          <h2 className="text-title-3 text-text-primary mb-1">Calibration Curve<CohortTag cohort={cohort} /></h2>
          <p className="text-xs text-text-muted mb-4">
            {cohort.shortLabel} ({cohortN.toLocaleString()} outcomes). Points on the diagonal =
            perfect calibration. Above = outcomes happened <em>more</em> than
            predicted. Below = <em>less</em>. Shaded band = &plusmn;5pp. Point size reflects sample count.
          </p>
          <CalibrationChart
            series={[{
              data: cohortBuckets,
              color: includeNeverMoved ? "#2563eb" : "#16a34a",
              label: `${cohort.shortLabel} (${cohortN.toLocaleString()})`,
            }]}
            width={700}
            height={400}
            thinFloor={MIN_CHART_BUCKET_N}
          />
        </section>
      )}

      {/* Table */}
      <section className="bg-surface-card rounded-xl p-5 border border-surface-border">
        <h2 className="text-title-3 text-text-primary mb-3">Calibration Table<CohortTag cohort={cohort} /></h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-text-muted uppercase tracking-wide">
                <th className="pb-2 pr-4">Bucket</th>
                <th className="pb-2 pr-4 text-right">N</th>
                <th className="pb-2 pr-4 text-right">Avg Predicted</th>
                <th className="pb-2 pr-4 text-right">Actual Rate</th>
                <th className="pb-2 pr-4 text-right">95% CI</th>
                <th className="pb-2 text-right">Error</th>
              </tr>
            </thead>
            <tbody>
              {cohortBuckets.map(b => (
                <tr key={b.bucket} className="border-t border-surface-border">
                  <td className="py-2 pr-4">{b.bucket}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{b.n.toLocaleString()}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{b.avgProb}%</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{b.actual}%</td>
                  <td className="py-2 pr-4 text-right tabular-nums text-text-muted">
                    {b.ciLower.toFixed(1)}-{b.ciUpper.toFixed(1)}%
                  </td>
                  <td className={`py-2 text-right tabular-nums ${
                    Math.abs(b.error) < 3 ? "text-text-muted" : b.error > 0 ? "text-green-600" : "text-red-600"
                  }`}>
                    {b.error > 0 ? "+" : ""}{b.error}pp
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* By Source — one panel per PROVIDER, matching Source Comparison above.
          UX-P078, Alex ruling 2026-08-14(b) item 3. CAL-P050 deliberately kept
          this section per-source-key and named it the annex; Alex overturned
          that for the presentation, and the annex MOVED rather than being cut —
          it is now the disclosure inside the Sportsbooks panel. The overturned
          reasoning is quoted in `lib/calibrationProviderPanels.ts` (ruling 055:
          a resolution that changes a decision is a decision, and it is recorded
          where the next reader will look, not deleted). */}
      <section id="by-source" className="bg-surface-card rounded-xl p-5 border border-surface-border scroll-mt-4">
        <h2 className="text-title-3 text-text-primary mb-1">By Source<CohortTag cohort={cohort} /></h2>
        <p className="text-xs text-text-muted mb-4">
          One panel per data provider &mdash; the same three rows as Source Comparison above &mdash;
          all on the same 0&ndash;100% axis so the curves are directly comparable, and each panel
          states its own sample size, because the providers differ by more than 28x in how much of
          the curve they carry. Error bars are the 95% CI (wider = less certain). Every bucket is
          shown &mdash; well-sampled buckets are solid dots, small-sample ones
          (&lt;{MIN_CHART_BUCKET_N.toLocaleString()} outcomes) are faded hollow dots with wide error
          bars, so you can see exactly how much data stands behind each point rather than having any
          hidden. Click any point for example outcomes, or select a provider tab for the full-width
          view.
        </p>
        {/* Derived from the built panels, never from a condition that implies
            them — UX-P075's PROXY_FOOTNOTE lesson. If no provider has more than
            one shape, there is no disclosure and this says nothing.

            ⚠️ Deliberately OUTSIDE the disclosure it describes: `innerText` does
            not return a closed `<details>`, so a sentence folded into the thing
            it announces is invisible to the browser rail and to a reader who
            never opens it. UX-P075 nearly hid this page's population arithmetic
            the same way. */}
        {providerShapeNote && (
          <p className="text-xs text-text-muted mb-4" data-testid="calibration-shape-annex-note">
            {providerShapeNote}
          </p>
        )}
        <div className="flex flex-wrap gap-2 mb-4">
          <TabButton label="All" active={!activeProvider} onClick={() => { setActiveProvider(null); setDrillIn(null); }} />
          {providerPanelData.map(p => (
            <TabButton
              key={p.provider}
              label={p.label}
              active={activeProvider === p.provider}
              onClick={() => { setActiveProvider(p.provider); setDrillIn(null); }}
            />
          ))}
        </div>
        {/* CAL-P025 / exit-exam item 4: on the "All" tab this used to be five
            curves on one axis. Measured on the published payload the sources
            span 28x in n and 3.3x in ECE, so the two large ones dominated and
            the three sportsbook curves were unreadable — including the one
            comparison that matters most, kalshi vs polymarket. Small multiples
            on the shared 0-100% axis `CalibrationChart` fixes structurally.
            Selecting a tab still gives the full-width chart, because that is the
            view the per-bucket drill-in belongs to.

            UX-P078: the tab is a provider, and the full-width curve is that
            provider's outcomes POOLED. The per-bucket drill-in is not offered on
            a pooled curve — `/calibration/examples` answers per source key, so a
            pooled point has no single key to ask about, and inventing one would
            hand the reader examples from a shape they did not click. The
            drill-in lives on the shape panels inside the disclosure, which is
            the other half of why the annex had to move rather than be cut. */}
        {activeProvider ? (
          <CalibrationChart
            series={providerChartData}
            width={700}
            height={340}
            thinFloor={MIN_CHART_BUCKET_N}
            showAllN
            onPointClick={
              activeProviderGroup && activeProviderGroup.sources.length === 1
                ? (_, pt) =>
                    openDrillIn(activeProviderGroup.sources[0], pt.bucket, Math.floor(pt.midpoint / 10))
                : undefined
            }
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4" data-testid="calibration-source-panels">
            {providerPanelData.map(p => (
              <div
                key={p.provider}
                className="border border-surface-border rounded-lg p-3"
                data-testid="calibration-provider-panel"
                data-provider={p.provider}
                data-provider-sources={p.sources.join(",")}
                data-panel-n={p.n}
                data-panel-ece={p.ece}
                /* Published beside the number so the rail can tell a server
                   figure from a pooled one without reading our prose. */
                data-ece-basis={p.eceBasis}
              >
                {/* Equal-area frames erase the size difference the overlay
                    carried by accident, so every panel states its own weight. */}
                <div className="flex items-baseline justify-between mb-1">
                  <span className="text-sm font-semibold text-text-primary">{p.label}</span>
                  {/* Absent when there is honestly no number for this panel.
                      Nothing is better than a number we made up to fill it. */}
                  {p.ece !== null && (
                    <span className="text-xs text-text-muted tabular-nums">
                      {p.ece.toFixed(1)}pp ECE
                    </span>
                  )}
                </div>
                <div className="text-xs text-text-muted mb-2 tabular-nums">
                  {p.n.toLocaleString()} outcomes &middot; {(p.share * 100).toFixed(1)}% of the curve
                </div>
                <CalibrationChart
                  series={[{ data: p.data, color: p.color, label: p.label }]}
                  width={330}
                  height={260}
                  thinFloor={MIN_CHART_BUCKET_N}
                  showLegend={false}
                  onPointClick={
                    p.hasShapeBreakdown
                      ? undefined
                      : (_, pt) => openDrillIn(p.sources[0], pt.bucket, Math.floor(pt.midpoint / 10))
                  }
                />
                {/* THE ANNEX, MOVED (Alex ruling 2026-08-14(b) item 3). Not a
                    second thing built beside the provider table — the same
                    per-shape panels CAL-P050 pointed at, relocated inside the
                    provider they describe, keeping their own published ECE,
                    their own n and their own drill-in. */}
                {p.hasShapeBreakdown && (
                  <details className="mt-3" data-testid="calibration-shape-breakdown">
                    <summary className="text-xs text-accent-brand cursor-pointer select-none">
                      Break out the shapes ({p.sources.length})
                    </summary>
                    <p className="text-xs text-text-muted mt-2">
                      Each shape is a different question, so these curves are not comparable to each
                      other &mdash; only to the same shape elsewhere. The panel above is all of them
                      pooled and measured together, which is the number the table reports.
                    </p>
                    <div className="grid grid-cols-1 gap-3 mt-3">
                      {p.shapes.map(sp => (
                        <div
                          key={sp.source}
                          className="border border-surface-border rounded-lg p-3"
                          data-testid="calibration-source-panel"
                          data-source={sp.source}
                          data-panel-n={sp.n}
                          data-panel-ece={sp.ece}
                        >
                          <div className="flex items-baseline justify-between mb-1">
                            <span className="text-sm font-semibold text-text-primary">
                              {sourceLabel(sp.source)}
                            </span>
                            {sp.ece !== null && (
                              <span className="text-xs text-text-muted tabular-nums">
                                {sp.ece.toFixed(1)}pp ECE
                              </span>
                            )}
                          </div>
                          <div className="text-xs text-text-muted mb-2 tabular-nums">
                            {sp.n.toLocaleString()} outcomes
                          </div>
                          <CalibrationChart
                            series={[{ data: sp.data, color: sp.color, label: sourceLabel(sp.source) }]}
                            width={300}
                            height={230}
                            thinFloor={MIN_CHART_BUCKET_N}
                            showLegend={false}
                            onPointClick={(_, pt) =>
                              openDrillIn(sp.source, pt.bucket, Math.floor(pt.midpoint / 10))
                            }
                          />
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            ))}
          </div>
        )}
        <BucketExamples
          state={drillIn}
          onClose={() => setDrillIn(null)}
          sourceLabel={sourceLabel}
        />
      </section>

      {/* By Category */}
      <section className="bg-surface-card rounded-xl p-5 border border-surface-border">
        <h2 className="text-title-3 text-text-primary mb-1">By Category<CohortTag cohort={cohort} /></h2>
        <p className="text-xs text-text-muted mb-4">
          Same treatment as By Source: 95% CI error bars, and every bucket shown &mdash;
          small-sample ones (&lt;{MIN_CHART_BUCKET_N.toLocaleString()} outcomes) as faded
          hollow dots with wide error bars, never hidden. Select a category tab to see
          per-bucket sample counts.
        </p>
        <div className="flex flex-wrap gap-2 mb-4">
          <TabButton label="Top 5" active={!activeCat} onClick={() => setActiveCat(null)} />
          {categories.map(c => (
            <TabButton key={c} label={categoryLabel(c)} active={activeCat === c} onClick={() => setActiveCat(c)} />
          ))}
        </div>
        <CalibrationChart series={catChartData} width={700} height={340} thinFloor={MIN_CHART_BUCKET_N} showAllN />
      </section>

      {/* L2-80 Item 1: the standalone per-category chart grid was removed — the
          tabbed "By Category" explorer above owns per-category curves, and the
          Category Breakdown table below is the scannable summary. One section per job. */}

      {/* Category Breakdown Table */}
      <section
        className="bg-surface-card rounded-xl p-5 border border-surface-border"
        data-testid="calibration-category-breakdown"
        data-published-categories={categoryMetrics.length}
      >
        <h2 className="text-title-3 text-text-primary mb-1">Category Breakdown<CohortTag cohort={cohort} /></h2>
        <p className="text-xs text-text-muted mb-4">
          Calibration metrics by market category. Categories with fewer than {minCategoryOutcomes.toLocaleString()} resolved outcomes are excluded &mdash; a sub-category chart below that sample size is statistical noise, not a calibration signal.
        </p>
        {/* UX-P118 item 5: WHICH POPULATION. The API publishes a per-category
            ECE over the whole population; this table renders one over the active
            cohort, and two of its rows additionally pool several published
            categories. Both numbers are correct about their own population —
            unlabelled, the pair reads as a contradiction to anyone who curls the
            API (hockey: 0.95pp published, 2.25pp here on 2026-08-21). The
            sentence is DERIVED from the same inputs the numbers are, so it
            cannot drift from the predicate it describes. */}
        <p
          className="text-xs text-text-muted mb-4"
          data-testid="calibration-category-population-note"
          data-pooled-rows={[...pooledByCategory.values()].filter(v => v.length > 1).length}
        >
          {describeCategoryTablePopulation(
            cohort.key,
            [...pooledByCategory.values()].filter(v => v.length > 1).length,
            categoryMetrics.length
          )}
        </p>
        {/* CAL-P067 item 4 (Fable ruling): the selection-bias disclosure. This
            is deliberately NOT phrased as a sample-size caveat — the two look
            alike and have opposite remedies. More data fixes a small sample; it
            does not fix a sample chosen by the thing you are measuring. */}
        {anyNotProvable(categoryMetrics) && (
          <p
            className="text-xs text-orange-800 bg-orange-50 border border-orange-200 rounded-lg p-3 mb-4"
            data-testid="calibration-selection-bias-note"
          >
            <strong>Some rows are marked &ldquo;not provable&rdquo;.</strong> A calibration
            number answers &ldquo;when we said 30%, how often did it happen?&rdquo; &mdash; which
            needs a graded result. So a category&rsquo;s curve is built only from its
            <em> graded</em> outcomes. Where fewer than half are graded, the curve describes
            that graded minority rather than the category, and the ungraded rest is not a
            random rest: it is concentrated in whole market types our graders have not yet
            covered. We show those numbers struck through with the graded share, because a
            wider error bar would be the wrong fix for the wrong problem. They become
            provable as grading coverage passes 50%, not as more data arrives.
          </p>
        )}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-text-muted uppercase tracking-wide">
                <th className="pb-2 pr-4">Category</th>
                <th className="pb-2 pr-4 text-right">Outcomes</th>
                <th className="pb-2 pr-4 text-right">ECE</th>
                <th className="pb-2 pr-4 text-right" title="Worst-bucket sensitivity (equal-weighted).">MCE&nbsp;<span className="text-text-muted/60">&#9432;</span></th>
                <th className="pb-2 text-right">Brier</th>
              </tr>
            </thead>
            <tbody>
              {[...categoryMetrics].sort((a, b) => a.ece - b.ece).map(cm => {
                // CAL-P067 (Fable ruling): a cell graded under 50% is measured
                // on a sample selected on the property being measured, so the
                // pp figures below are not a measurement of the category. We
                // keep the numbers visible — a biased estimate is still the
                // estimate — but strike the confident formatting and say why.
                // Decision logic lives in lib/calibrationProvability so it is
                // testable without mounting the page.
                const prov = provabilityPresentation(cm);
                const notProvable = prov.showNotProvableBadge;
                const shareUnknown = prov.showUnknownBadge;
                // UX-P118 item 5: this row's own population, naming BOTH axes.
                const pop = describeCategoryPopulation(
                  cm.category,
                  pooledByCategory.get(cm.category) ?? [cm.category],
                  data?.by_category ?? [],
                  cohort.key
                );
                return (
                <tr key={cm.category} className="border-t border-surface-border"
                  data-testid="calibration-category-row" data-category={cm.category} data-n={cm.n}
                  data-provability={cm.provability ?? "unset"}
                  data-pools={pop.pools ? "true" : "false"}
                  data-pooled-from={pop.pooledFrom.join(",")}
                  data-published-ece={pop.publishedEce ?? ""}
                  data-graded-share={cm.graded_share ?? ""}>
                  <td className="py-2 pr-4 font-medium text-text-primary">
                    {categoryLabel(cm.category)}
                    {notProvable && (
                      <span
                        data-testid="calibration-not-provable-badge"
                        title={prov.title}
                        className="ml-2 align-middle inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide border border-orange-300 text-orange-700 bg-orange-50"
                      >
                        {prov.badgeLabel}
                      </span>
                    )}
                    {shareUnknown && (
                      <span
                        data-testid="calibration-provability-unknown-badge"
                        title={prov.title}
                        className="ml-2 align-middle inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide border border-surface-border text-text-muted"
                      >
                        {prov.badgeLabel}
                      </span>
                    )}
                    {/* A pooled row's label is not the payload key it looks
                        like. Marked visibly rather than only in a tooltip,
                        because the reader who needs it is the one comparing
                        against the API and he is not hovering. */}
                    {pop.pools && (
                      <span
                        data-testid="calibration-pooled-categories-badge"
                        title={pop.title}
                        className="ml-2 align-middle inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide border border-surface-border text-text-muted"
                      >
                        {pop.pooledFrom.length} categories
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-4 text-right tabular-nums">{cm.n.toLocaleString()}</td>
                  <td title={pop.title} className={`py-2 pr-4 text-right tabular-nums ${
                    notProvable
                      ? "font-normal text-text-muted line-through decoration-orange-400/60"
                      : `font-semibold ${cm.ece < 3 ? "text-green-600" : cm.ece < 5 ? "text-blue-600" : "text-orange-600"}`
                  }`}>
                    {cm.ece.toFixed(1)}pp
                  </td>
                  <td className={`py-2 pr-4 text-right tabular-nums text-text-muted ${
                    notProvable ? "line-through decoration-orange-400/60" : ""
                  }`}>
                    {cm.mce.toFixed(1)}pp
                  </td>
                  <td className={`py-2 text-right tabular-nums ${
                    notProvable ? "text-text-muted line-through decoration-orange-400/60" : ""
                  }`}>{cm.brier.toFixed(4)}</td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* CAL-P067 item 5 — the quarantine disclosure (Alex ruling).
          Rows held OUT of the published curves pending review. The point of
          publishing this is that a quarantine and a silent drop are
          indistinguishable from the outside: both just make the denominator
          smaller. Stating the count, the reason and the status is what makes it
          an exclusion rather than a disappearance, and what makes it
          reversible. Triage owns the flag write; this surface owns saying so. */}
      {data.quarantine && data.quarantine.length > 0 && (() => {
        const held = data.quarantine!;
        const total = held.reduce((s, q) => s + (q.outcomes || 0), 0);
        return (
          <section
            className="bg-surface-card rounded-xl p-5 border border-surface-border"
            data-testid="calibration-quarantine"
            data-quarantine-total={total}
          >
            <h2 className="text-title-3 text-text-primary mb-1">
              Held out, under review<CohortTag cohort={cohort} />
            </h2>
            <p className="text-xs text-text-muted mb-4">
              {total.toLocaleString()} resolved {total === 1 ? "outcome is" : "outcomes are"}{" "}
              excluded from every curve on this page while we check them. They are not
              graded, not counted, and not deleted &mdash; a held-out row is a stated
              exclusion we can reverse, which is the difference between a quarantine and a
              quietly shorter denominator.
            </p>
            <ul className="space-y-2">
              {held.map((q, i) => (
                <li
                  key={`${q.reason}-${i}`}
                  className="flex items-start justify-between gap-4 border-t border-surface-border pt-2 text-sm"
                  data-testid="calibration-quarantine-row"
                  data-reason={q.reason}
                  data-outcomes={q.outcomes}
                >
                  <div>
                    <span className="font-medium text-text-primary">{q.reason}</span>
                    {q.note && (
                      <span className="block text-xs text-text-muted mt-0.5">{q.note}</span>
                    )}
                  </div>
                  <div className="text-right shrink-0">
                    <div className="tabular-nums font-semibold text-text-primary">
                      {q.outcomes.toLocaleString()}
                    </div>
                    <div className="text-[10px] uppercase tracking-wide text-orange-700">
                      under review
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        );
      })()}

      {/* Too-thin-to-grade honest note (L2-80 Item 4) — answers the friends-and-family
          skeptic ("what about the weird / novelty / long-shot markets?") without faking
          a curve. Fully payload-driven from small_sample_categories (real counts), so
          the native app inherits the same honest note with no extra logic. */}
      {data.small_sample_categories && data.small_sample_categories.length > 0 && (() => {
        const thin = [...data.small_sample_categories].sort((a, b) => b.outcomes - a.outcomes);
        const thinTotal = thin.reduce((s, c) => s + c.outcomes, 0);
        const examples = thin.slice(0, 8);
        const catLabel = nicheCatLabel;
        // Queue 299 made the held-out disposition machine-readable
        // (`parked_below_publish_bar` + the bar + the cohort's own ECE). It is
        // published here as data so the rail — and the native surface — can
        // prove a parked category is accounted for rather than silently gone.
        // The visible copy is unchanged.
        return (
          <section className="bg-surface-card rounded-xl p-5 border border-surface-border"
            data-testid="calibration-niche-section" data-parked-count={thin.length}>
            <h2 className="text-title-3 text-text-primary mb-1">What About Niche &amp; Long-Shot Markets?<CohortTag cohort={cohort} /></h2>
            <p className="text-sm text-text-secondary mb-3">
              Fair question &mdash; what about the offbeat ones (one-off culture bets, novelty props,
              minor leagues)? A calibration curve is only honest with enough resolved outcomes behind it, so
              we don&rsquo;t publish one for any category below{" "}
              {minCategoryOutcomes.toLocaleString()} resolved outcomes &mdash; under that bar it&rsquo;s
              statistical noise, not a signal. Right now{" "}
              <strong className="text-text-primary">{thin.length}</strong>{" "}
              {thin.length === 1 ? "category is" : "categories are"} still accumulating
              ({thinTotal.toLocaleString()} outcomes and counting). The moment one crosses the bar it
              appears above automatically &mdash; no fake curve until we can stand behind it.
            </p>
            <p className="text-xs text-text-muted mb-2 uppercase tracking-wide">Closest to the bar</p>
            <div className="flex flex-wrap gap-2 mb-3">
              {examples.map(c => (
                <span
                  key={c.category}
                  data-testid="calibration-parked-category"
                  data-category={c.category}
                  data-disposition={c.disposition ?? ""}
                  data-outcomes={c.outcomes}
                  className="text-xs px-2.5 py-1 rounded-full bg-surface-deep text-text-secondary border border-surface-border capitalize"
                >
                  {catLabel(c.category)}{" "}
                  <span className="tabular-nums text-text-muted normal-case">{c.outcomes.toLocaleString()}</span>
                </span>
              ))}
              {thin.length > examples.length && (
                <span className="text-xs px-2.5 py-1 text-text-muted">
                  +{(thin.length - examples.length).toLocaleString()} more
                </span>
              )}
            </div>
            <p className="text-xs text-text-muted">
              How we&rsquo;ll know it&rsquo;s ready: see{" "}
              <a href="#methodology" className="text-accent-brand hover:underline">How We Measure This</a>{" "}
              for the sample-size bar and full methodology.
            </p>
          </section>
        );
      })()}

      {/* Data corrections log (L2-74 §E — trust panel; L2-80 Item 3: collapsed into a
          <details> closed by default and clearly labeled technical — too detailed to
          show expanded in every view. Content unchanged.) */}
      {data.corrections && data.corrections.length > 0 && (
        <section className="bg-surface-card rounded-xl border border-surface-border">
          <details className="group">
            <summary className="cursor-pointer list-none p-5 flex items-center justify-between gap-3 select-none">
              <span className="flex items-baseline gap-2">
                <span className="text-title-3 text-text-primary">Technical: data corrections log</span>
                <span className="text-xs text-text-muted tabular-nums">({data.corrections.length})</span>
              </span>
              <span className="text-text-muted text-sm transition-transform group-open:rotate-180" aria-hidden="true">&#9662;</span>
            </summary>
            <div className="px-5 pb-5">
              <p className="text-xs text-text-muted mb-4">
                A calibration page is only trustworthy if it fixes its own mistakes. Every data-quality
                correction we&rsquo;ve made &mdash; with dates and rows affected &mdash; is on the record here.
                See <a href="#methodology" className="text-accent-brand hover:underline">How We Measure This</a> for the full methodology.
              </p>
              <ul className="space-y-0">
                {data.corrections.map((c, i) => (
                  <li
                    key={`${c.date}-${i}`}
                    className="flex flex-col sm:flex-row sm:items-baseline gap-0.5 sm:gap-3 border-t border-surface-border py-3 first:border-0 first:pt-0"
                  >
                    <span className="text-xs font-mono text-text-muted whitespace-nowrap w-24 shrink-0">{c.date}</span>
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-text-primary">
                        {c.title}
                        {c.rows != null && (
                          <span className="ml-2 text-xs font-normal text-text-muted tabular-nums">
                            {c.rows.toLocaleString()} rows
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-text-secondary">{c.description}</div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </details>
        </section>
      )}

      {/* Further Reading */}
      <section className="bg-surface-card rounded-xl p-5 border border-surface-border">
        <h2 className="text-title-3 text-text-primary mb-3">Further Reading</h2>
        <p className="text-sm text-text-secondary mb-3">
          Our findings are consistent with decades of academic research on prediction market accuracy:
        </p>
        <ul className="space-y-3 text-sm text-text-secondary">
          <li><strong className="text-text-primary">Arrow et al., &ldquo;The Promise of Prediction Markets&rdquo;</strong> (2008, <em>Science</em>) &mdash; 22 leading economists argued that prediction markets are &ldquo;among the most accurate forecasting mechanisms known.&rdquo; <a href="https://www.science.org/doi/10.1126/science.1157679" target="_blank" rel="noopener noreferrer" className="text-accent-brand hover:underline">Read &rarr;</a></li>
          <li><strong className="text-text-primary">Berg, Nelson &amp; Rietz, &ldquo;Prediction Market Accuracy in the Long Run&rdquo;</strong> (2008) &mdash; The Iowa Electronic Markets predicted presidential outcomes within 1.5pp, outperforming 74% of polls. <a href="https://doi.org/10.1016/j.ijforecast.2008.03.007" target="_blank" rel="noopener noreferrer" className="text-accent-brand hover:underline">Read &rarr;</a></li>
          <li><strong className="text-text-primary">Tetlock &amp; Gardner, <em>Superforecasting</em></strong> (2015) &mdash; The foundational work on calibration. Well-calibrated forecasters can be identified by exactly the kind of curve shown above. <a href="https://en.wikipedia.org/wiki/Superforecasting" target="_blank" rel="noopener noreferrer" className="text-accent-brand hover:underline">Learn more &rarr;</a></li>
          <li><strong className="text-text-primary">Wolfers &amp; Zitzewitz, &ldquo;Prediction Markets&rdquo;</strong> (2004, <em>J. Econ. Perspectives</em>) &mdash; Comprehensive survey showing prediction markets produce well-calibrated estimates across domains. <a href="https://doi.org/10.1257/0895330041371321" target="_blank" rel="noopener noreferrer" className="text-accent-brand hover:underline">Read &rarr;</a></li>
          <li><strong className="text-text-primary">Metaculus Track Record</strong> &mdash; The forecasting platform publishes its calibration curve publicly, achieving ~2-3pp mean calibration error. <a href="https://www.metaculus.com/questions/track-record/" target="_blank" rel="noopener noreferrer" className="text-accent-brand hover:underline">See their data &rarr;</a></li>
        </ul>
      </section>

      {/* Methodology */}
      <section id="methodology" className="bg-surface-card rounded-xl p-5 border border-surface-border scroll-mt-4">
        <h2 className="text-title-3 text-text-primary mb-3">How We Measure This</h2>
        <ul className="space-y-3 text-sm text-text-secondary">
          <li><strong className="text-text-primary">What&rsquo;s a calibration curve?</strong> We group every resolved prediction by its opening probability (0-10%, 10-20%, etc.) and check what percentage actually came true. If markets are well-calibrated, the points follow the diagonal line &mdash; a 30% prediction happens 30% of the time.</li>
          <li><strong className="text-text-primary">How do we know who won?</strong> For sports, we use final scores &mdash; no ambiguity. For prediction markets (Kalshi, Polymarket), a market&rsquo;s final price settles at $1.00 (happened) or $0.00 (didn&rsquo;t happen) when it resolves.</li>
          <li><strong className="text-text-primary">Which probability do we use?</strong> For events with a known start time (sports games, tournaments), we use <strong>closing line prices</strong> &mdash; the last traded price before the event begins. This is the <a href="https://doi.org/10.1016/j.ijforecast.2008.03.007" target="_blank" rel="noopener noreferrer" className="text-accent-brand hover:underline">academic gold standard</a> for calibration because it captures all available information at the moment of truth. For sports, we use vig-removed consensus closing odds across 20+ bookmakers. For prediction markets linked to events (Kalshi, Polymarket game markets), we use the last traded price before the event starts. For markets without a fixed event start time (elections, economics, entertainment), we use the <strong>opening price after initial trading settles</strong> &mdash; the most conservative and honest measure. A year-long market&rsquo;s accuracy depends on when you measure, so a single closing line would be misleading.</li>
          {/* Queue 316 item 1. This was a column in Source Comparison, where it
              competed with ECE for the reader's attention while being a
              guardrail rather than a headline: it answers "is the error spread
              across the curve or concentrated in one bucket", which matters
              when you already distrust the number and not before. */}
          <li data-testid="calibration-buckets-in-band-note">
            <strong className="text-text-primary">&ldquo;Buckets within 5pp&rdquo; &mdash; the
            guardrail behind the headline.</strong> We split the curve into probability buckets and
            check how many land within 5 percentage points of perfect. Across the whole page that is{" "}
            <strong className="text-text-primary">
              {cohortBuckets.filter(b => Math.abs(b.error) <= 5).length} of {cohortBuckets.length}
            </strong>{" "}
            buckets. A good ECE with few buckets in the band would mean the average is being carried
            by the big buckets while the thin ones swing wildly &mdash; so this is the check that
            says whether the headline is trustworthy, not the headline itself.
          </li>
          {/* Queue 316 item 2b (premise P8). The events/Odds-API path selects
              COALESCE(closing, opening), so "closing line" was not uniformly
              true across the table and the fallback was silent. Wording only —
              nothing about what is computed changes here. */}
          {data.closing_line_coverage && data.closing_line_coverage.total > 0 && (
            <li data-testid="calibration-price-basis-note"
              data-has-closing={data.closing_line_coverage.has_closing}
              data-needs-closing={data.closing_line_coverage.needs_closing}>
              <strong className="text-text-primary">Not every row is a closing price, and we say
              which.</strong> Kalshi and Polymarket are measured on their closing line. Sportsbook
              rows use the closing line <em>where one exists</em> and fall back to the opening price
              where it does not &mdash;{" "}
              <span className="text-text-primary">
                {data.closing_line_coverage.has_closing.toLocaleString()} of{" "}
                {data.closing_line_coverage.total.toLocaleString()}
              </span>{" "}
              sportsbook rows have a close ({data.closing_line_coverage.needs_closing.toLocaleString()}{" "}
              do not). The two bases do not measure the same, and we publish both figures rather than
              one blended number: {data.mce_closing_line?.toFixed(1)}pp on closing-line rows against{" "}
              {data.mce_opening_price?.toFixed(1)}pp on opening-price rows. A closing line is the
              stronger test, so the gap is the cost of the fallback, not a finding about the books.
            </li>
          )}
          <li><strong className="text-text-primary">What&rsquo;s a Brier score?</strong> It measures the average squared error of every prediction. If you predicted 70% and it happened, your error for that prediction is (0.70 - 1.0)&sup2; = 0.09. Average that across all predictions: 0 is perfect, 0.25 is random guessing. Ours is {overallBrier.toFixed(2)}.</li>
          <li><strong className="text-text-primary">What&rsquo;s included?</strong> {data.total_outcomes.toLocaleString()} resolved outcomes{data.date_range?.start && data.date_range?.end ? ` from ${monthYear(data.date_range.start)}–${monthYear(data.date_range.end)}` : ""} across Kalshi, Polymarket, and sportsbook odds (via The Odds API). That published total is lower than the raw resolved-outcome count because we exclude markets that can&rsquo;t form an honest prediction &mdash; see the exclusions below. We only include markets where real trading occurred &mdash; outcomes with zero bids or no trading volume are excluded, because a price without participants isn&rsquo;t a prediction. Data refreshes hourly.</li>
          {data.liquidity_filter && (data.liquidity_filter.kalshi_included + data.liquidity_filter.kalshi_excluded > 0) && (
            <li>
              <strong className="text-text-primary">Liquidity filter (Kalshi).</strong>{" "}
              {data.liquidity_filter.rule}{" "}
              <span className="text-text-primary">
                {data.liquidity_filter.kalshi_included.toLocaleString()} included
              </span>{" "}
              &middot;{" "}
              <span className="text-text-muted">
                {data.liquidity_filter.kalshi_excluded.toLocaleString()} excluded
              </span>{" "}
              ({(100 * data.liquidity_filter.kalshi_excluded / (data.liquidity_filter.kalshi_included + data.liquidity_filter.kalshi_excluded)).toFixed(0)}% of the Kalshi set). A skeptical auditor can re-include them &mdash; we publish both counts so the filter is never silent.
            </li>
          )}
          {/* L2-103 Item 4: the other read-side exclusions that pull the raw count
              down to the published total — surfaced so the drop is never silent. */}
          {data.esports_multi_bundle_filter && data.esports_multi_bundle_filter.excluded > 0 && (
            <li>
              <strong className="text-text-primary">Esports match-bundle filter.</strong>{" "}
              {data.esports_multi_bundle_filter.rule}{" "}
              <span className="text-text-muted">{data.esports_multi_bundle_filter.excluded.toLocaleString()} excluded.</span>
            </li>
          )}
          {data.soccer_2way_filter && data.soccer_2way_filter.excluded > 0 && (
            <li>
              <strong className="text-text-primary">Soccer 2-way (draw-omission) filter.</strong>{" "}
              {data.soccer_2way_filter.rule}{" "}
              <span className="text-text-muted">{data.soccer_2way_filter.excluded.toLocaleString()} excluded.</span>
            </li>
          )}
          {data.void_filter && data.void_filter.excluded > 0 && (
            <li>
              <strong className="text-text-primary">Void filter (did-not-play / withdrew).</strong>{" "}
              {data.void_filter.rule}{" "}
              <span className="text-text-muted">{data.void_filter.excluded.toLocaleString()} excluded.</span>
            </li>
          )}
          {data.exclusion_symmetry && (
            <li>
              <strong className="text-text-primary">Never-traded exclusions differ by source (and we say so).</strong>{" "}
              Kalshi excludes <em>every</em> never-traded outcome (any price); Polymarket only excludes never-traded
              outcomes near 0.50 (the Gamma synthetic-placeholder band). So a Polymarket outcome that never traded but
              sits outside that band is still counted.{" "}
              <span className="text-text-muted">
                {data.exclusion_symmetry.poly_never_traded_excluded_by_band.toLocaleString()} poly never-traded already
                excluded by the placeholder band; {data.exclusion_symmetry.poly_never_traded_in_curve.toLocaleString()} still
                counted (the residual asymmetry). We publish the count so it&rsquo;s never silent.
              </span>
            </li>
          )}
          <li><strong className="text-text-primary">When did we start publishing this?</strong> We began publicly publishing and documenting these calibration metrics in July 2026. The underlying work &mdash; closing-line capture, resolution, devigging, and the exclusion rules above &mdash; long predates that date. July 2026 is when we started showing our work, not when the measurement began.</li>
        </ul>
      </section>

      {/* Footer */}
      <footer className="text-center text-xs text-text-muted pt-4 border-t border-surface-border">
        <p>
          {cohortN.toLocaleString()} resolved outcomes &middot; {sources.length} sources &middot; {categories.length} categories
          {priceCohort !== "all" && ` (${priceCohort === "closing" ? "closing line" : "opening price"} cohort)`}
        </p>
        <p className="mt-1">
          <Link href="/about" className="text-accent-brand hover:underline">About Bain Luck</Link>
        </p>
      </footer>
    </div>
    </ErrorBoundary>
  );
}

// L2-231 Item 1 / L2-232: the ONE element the page renders when it will not show
// numbers, whichever reason it has.
//
// Two properties are load-bearing:
//
//   1. `calibration-error` is declared exactly ONCE in this file. The rail
//      selects it with `.first()`, so a second declaration would make the choice
//      markup order rather than intent — and `calibrationAuditHooks.test.tsx`
//      fails CI on a duplicate. Both the transport failure and the contract
//      refusal therefore route through here rather than each rendering their own.
//
//   2. It NAMES itself as data. "the loaded-page hook is missing" is not a
//      diagnosis: a rebuild window, a hard fetch failure, a refused population
//      contract and a rendering regression all look identical from outside.
//      `data-error-state-name` distinguishes them, and `data-contract-state`
//      says whether a payload was even available to judge.
//
// `onRetry` is deliberately optional. The transport failures pass one — a reload
// genuinely can fix those. The contract refusal does NOT: retrying the same
// build against the same payload reproduces the same refusal, so offering the
// button would be an invitation to a loop that cannot terminate. Recovery there
// is a republish or a redeploy, and SWR's 5-minute poll picks up either without
// the reader doing anything, which is what the copy promises.
function CalibrationUnavailable({
  stateName, contractState, message, onRetry, servedVersion,
}: {
  stateName: string;
  contractState: string;
  message: string;
  onRetry?: () => void;
  servedVersion?: string;
}) {
  return (
    <div
      className="max-w-6xl mx-auto"
      data-testid="calibration-error"
      data-error-state-name={stateName}
      data-contract-state={contractState}
      /* The version is EVIDENCE, not copy: published where the rail can grade
         the exact mismatch, and kept out of the reader's sentence, where a bare
         "q267" is unexplained jargon. */
      data-served-population-version={servedVersion ?? ""}
    >
      <ErrorState message={message} onRetry={onRetry} />
    </div>
  );
}

// L2-231 Item 1: `testId` is the browser rail's anchor. The audit used to find a
// card by its LABEL TEXT and then read child `> div` index 1 positionally, so an
// editorial reword ("Resolved Outcomes" -> "Graded Outcomes") broke the evidence
// and a markup reshuffle silently moved the read onto a different number. The
// hook names the card; `-value` names the number inside it. Neither is prose.
/**
 * CAL-P025 — one matched bucket.
 *
 * The rule this component exists to hold: an ABSENT side renders as an em dash,
 * never as 0.0pp. `compareMatchedBuckets` already returns `null` for it and
 * `null` for the gap, so the only way to reintroduce the bug is here, by
 * defaulting. Nothing below defaults.
 */
function MatchedBucketTableRow({ row, widest }: {
  row: MatchedBucketRow;
  widest: boolean;
}) {
  const fmt = (pp: number) => `${pp > 0 ? "+" : pp < 0 ? "−" : ""}${Math.abs(pp).toFixed(1)}pp`;
  const thin = !row.comparable;
  return (
    <tr
      className={`border-b border-surface-border last:border-0 ${thin ? "text-text-muted" : "text-text-primary"} ${widest ? "bg-amber-50" : ""}`}
      data-testid="calibration-matched-row"
      data-bucket={row.bucketIdx}
      data-comparable={row.comparable}
      data-gap-pp={row.gapPp ?? ""}
    >
      <td className="py-2 pr-4 font-medium">{row.label}</td>
      <td className="py-2 pr-4 text-right tabular-nums">
        {row.moved
          ? <>{fmt(row.moved.errorPp)}<span className="block text-xs text-text-muted">{row.moved.n.toLocaleString()}</span></>
          : <span aria-label="no outcomes in this bucket">&mdash;</span>}
      </td>
      <td className="py-2 pr-4 text-right tabular-nums">
        {row.unchanged
          ? <>{fmt(row.unchanged.errorPp)}<span className="block text-xs text-text-muted">{row.unchanged.n.toLocaleString()}</span></>
          : <span aria-label="no outcomes in this bucket">&mdash;</span>}
      </td>
      <td className={`py-2 text-right tabular-nums ${widest ? "font-semibold" : ""}`}>
        {row.gapPp === null
          ? <span aria-label="no matched pair to compare">&mdash;</span>
          : fmt(row.gapPp)}
      </td>
    </tr>
  );
}

function StatCard({ label, value, detail, valueClass, testId }: {
  label: string; value: string; detail: string; valueClass?: string; testId?: string;
}) {
  return (
    <div className="bg-surface-card rounded-xl p-3 border border-surface-border" data-testid={testId}>
      <div className="text-[10px] text-text-muted uppercase tracking-wide">{label}</div>
      <div
        className={`text-xl font-bold ${valueClass || "text-text-primary"}`}
        data-testid={testId ? `${testId}-value` : undefined}
      >
        {value}
      </div>
      <div className="text-[11px] text-text-muted mt-0.5 leading-tight">{detail}</div>
    </div>
  );
}

// L2-103 Item 2: unobtrusive per-bucket drill-in panel — shows 3-5 real sample
// outcomes so a skeptic can verify what any bucket is made of.
function BucketExamples({ state, onClose, sourceLabel }: {
  state: DrillInState | null;
  onClose: () => void;
  sourceLabel: (s: string) => string;
}) {
  if (!state) return null;
  const fmtDate = (d: string | null) => {
    if (!d) return "—";
    const dt = new Date(d);
    return isNaN(dt.getTime()) ? "—" : dt.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  };
  return (
    <div className="mt-4 rounded-lg border border-surface-border bg-surface-deep p-4">
      <div className="flex items-baseline justify-between gap-3 mb-2">
        <div className="text-sm font-medium text-text-primary">
          Sample outcomes &mdash; {sourceLabel(state.source)}, {state.bucketLabel} bucket
        </div>
        <button
          onClick={onClose}
          className="text-xs text-text-muted hover:text-text-primary shrink-0"
          aria-label="Close examples"
        >
          Close &times;
        </button>
      </div>
      {state.loading ? (
        <div className="text-xs text-text-muted py-2">Loading examples&hellip;</div>
      ) : state.error ? (
        <div className="text-xs text-accent-danger py-2">Couldn&rsquo;t load examples. Try again.</div>
      ) : state.examples.length === 0 ? (
        <div className="text-xs text-text-muted py-2">
          {state.note || "No individual examples available for this source/bucket."}
        </div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-text-muted uppercase tracking-wide">
                  <th className="pb-1.5 pr-3">Market</th>
                  <th className="pb-1.5 pr-3">Outcome</th>
                  <th className="pb-1.5 pr-3 text-right">Predicted</th>
                  <th className="pb-1.5 pr-3 text-right">Result</th>
                  <th className="pb-1.5 text-right">Settled</th>
                </tr>
              </thead>
              <tbody>
                {state.examples.map((ex, i) => (
                  <tr key={i} className="border-t border-surface-border align-top">
                    <td className="py-1.5 pr-3 text-text-secondary max-w-[260px] truncate" title={ex.market_name}>{ex.market_name}</td>
                    <td className="py-1.5 pr-3 text-text-secondary max-w-[160px] truncate" title={ex.outcome_name}>{ex.outcome_name}</td>
                    <td className="py-1.5 pr-3 text-right tabular-nums text-text-primary">{(ex.price * 100).toFixed(1)}%</td>
                    <td className={`py-1.5 pr-3 text-right font-medium ${
                      /^(yes|won|true)$/i.test(ex.result) ? "text-green-600" : "text-red-600"
                    }`}>{ex.result}</td>
                    <td className="py-1.5 text-right tabular-nums text-text-muted whitespace-nowrap">{fmtDate(ex.settle_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-text-muted mt-2">A representative sample &mdash; not the full bucket.</p>
        </>
      )}
    </div>
  );
}

function TabButton({ label, active, onClick }: {
  label: string; active: boolean; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
        active
          ? "bg-text-primary text-surface-deep"
          : "bg-surface-deep text-text-secondary hover:text-text-primary"
      }`}
    >
      {label}
    </button>
  );
}
