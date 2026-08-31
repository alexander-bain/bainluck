"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { BarChart3 } from "lucide-react";
import { buildDiscoverShareUrl, formatShareProbability } from "@/lib/share";
import { marketEventKey, eventPath } from "@/lib/eventKey";
import { leaderFirstSlice } from "@/lib/discover/leaderOrder";
import { heroOutcome } from "@/lib/discover/heroOutcome";
import { formatProbabilityPercent, formatMovementPoints, movementPoints } from "@/lib/probabilityDisplay";
import { renderedLeaderPercent } from "@/lib/renderedPercent";
import type { FeedItem, FeedFuturesData } from "@/lib/types";
import { CATEGORY_GRADIENTS, getCat } from "./constants";
import { feedContextSnippet, feedExpandedContext, resolvesLabel } from "./utils";
import { AnimatedProbability, DismissBtn, TrendBadge, TemporalBadge, ActionBar, MovementBadge, ExpandableContextText, SignalBars } from "./shared";
import QuantityGroup from "../QuantityGroup";
import type { ActionBarProps, CardActionCallbacks } from "./types";
import { shapeForbidsKernel, storedShape, SHAPE_QUANTITY, SHAPE_FIELD } from "@/lib/marketShape";
import { HERO_PROBABILITY_HINT } from "@/lib/discoverFirstRun";
import { probabilityAuthorityClass } from "@/lib/confidence";

// Deterministic exposure hash — the same char-fold the card has always used,
// factored out so the SSR/first-render seed and the post-mount session
// assignment share one implementation (L2-199).
function computeVariantB(id: number, session: string): boolean {
  const seed = `${session}_${id}`;
  const hash = Array.from(seed).reduce((h, c) => ((h << 5) - h + c.charCodeAt(0)) | 0, 0);
  return Math.abs(hash) % 2 === 0;
}

// Read the persisted Discover session id WITHOUT creating one — preserving the
// existing A/B allocation intent (anon users hash under "anon", exactly as the
// old render-time `localStorage.getItem` did). Guarded so blocked storage
// returns the stable fallback instead of throwing (L2-199).
function readSessionSeed(): string {
  if (typeof window === "undefined") return "anon";
  try {
    return localStorage.getItem("bainluck_session_id") || "anon";
  } catch {
    return "anon";
  }
}

/**
 * How big a 24h move must be, IN POINTS, before the hero slot shows it.
 *
 * UX-P048 (#1695): this is the pre-existing bar, unchanged in value — it was
 * spelled `>= 0.1` against a wire fraction, which is 10 points. It is named and
 * expressed in points here because the surrounding `toFixed(1)` made it read as
 * a tenth of a point, and that ambiguity is what let the scale bug live.
 *
 * Deliberately NOT reconciled with `MovementBadge`'s 2-point floor
 * (`shared.tsx`). Two surfaces may honestly want different bars, and the
 * measurement that would settle it is on #1695: at 10 points, 20 of 21 cards
 * carrying a real move show nothing. That is a design call, not this fix.
 */
const HERO_MIN_MOVEMENT_POINTS = 10;

// One row of `discover_card.distribution_outcomes` as the card renders it.
type DistributionRow = {
  label: string;
  probability: number | null;
  movement?: number | null;
};

interface FuturesCardProps extends CardActionCallbacks {
  item: FeedItem;
  data: FeedFuturesData;
  liked: boolean;
  setLiked: (v: boolean) => void;
  onDismiss?: () => void;
  trending: boolean;
  /**
   * Queue 309 Item 2 — label the hero percentage for a first-run reader who has
   * never been told what these numbers are. The page owns the cohort decision;
   * the card stays presentational and just renders what it is handed.
   */
  showProbabilityHint?: boolean;
  /**
   * UX-P234 (board item 16) — Alex: *"on the web Discover feed there is no
   * indication a card can be pinned at all."* It could not be: this card had no
   * pin of any kind, while the SAME market was pinnable from search, my-stuff and
   * preferences.
   *
   * 🔴 A PROP, NOT A HOOK, AND THE FIRST DRAFT GOT THIS WRONG. Calling
   * `usePinnedFutures()` in here reaches `useAuthContext`, which THROWS outside an
   * `AuthProvider` — it took down TEN existing suites that render this card in
   * isolation. It also contradicts the convention `DiscoverCard` states in its own
   * docblock: *"Cards stay presentational … never behind a storage read in here."*
   * The page owns the store and hands the binding down, exactly as
   * `components/FuturesCard.tsx` has always done with `isPinned` / `onPinToggle`.
   *
   * Optional: a caller that passes nothing renders no pin and is byte-identical.
   */
  pin?: ActionBarProps["pin"];
}

export function FuturesCard({ item, data, liked, setLiked, onDismiss, trending, showProbabilityHint, onDetailClick, onShare, onContextExpand, onContextCollapse, pin }: FuturesCardProps) {
  const [showContext, setShowContext] = useState(false);
  const [showHeatmapContext, setShowHeatmapContext] = useState(false);
  // A/B variant: exposure-level assignment — hash(session + market) so each
  // market serves both variants across sessions and each session sees both.
  //
  // Hydration-safe (L2-199): the session id lives in localStorage, which is
  // undefined during SSR and can THROW when browser storage is blocked. The old
  // code read it during render, so (a) the server hashed "ssr_<id>" while the
  // client hashed the real session — server and first-hydration markup could
  // pick structurally DIFFERENT card variants, causing a React hydration
  // mismatch / subtree replacement / flicker — and (b) a storage-access throw
  // took down the whole card subtree. We now seed a hydration-stable default
  // ("anon") for SSR AND the first client render (the useState initializer runs
  // identically on both), then resolve the real session-scoped assignment in a
  // post-mount effect. The SSR body stays non-personalized (edge-cache safe),
  // and the assignment is stable after mount and across rerenders. `data-card-
  // variant` records the assigned variant for exposure analytics. Anon users
  // (no session id) hash under "anon" both before and after mount → no flip,
  // preserving the existing allocation intent exactly.
  const [variantB, setVariantB] = useState(() => computeVariantB(data.id, "anon"));
  useEffect(() => {
    setVariantB(computeVariantB(data.id, readSessionSeed()));
  }, [data.id]);
  const catStyle = getCat(data.llm_sport_category);
  const category = data.sport_name || data.llm_sport_category || "Markets";
  // UX-P238 — the hero speaks for the question, not for whichever side is
  // winning. `top_outcomes[0]` is the No side on a market whose answer is
  // "probably not", and this hero prints a bare number with no outcome label
  // under the title, so `Will "Onslaught" score at least 80?` headlined 88%
  // when the answer was 12%. `heroOutcome` returns the served headline
  // unchanged for every card that is not an explicit negation pair.
  const leader = heroOutcome(data.top_outcomes);
  const prob = leader?.probability ?? null;
  const contextSnippet = feedContextSnippet(item);
  const expandedContext = feedExpandedContext(item);
  const resolveText = resolvesLabel(data.resolution_date);
  const hasImage = !!data.image_url;
  const outcomesAreDate = data.top_outcomes?.some((o) => /^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2}/i.test(o.name));
  // L2-65: a winner-field market that IS an event concept (e.g. a tennis
  // tournament winner) links into the richer /event/[key] surface; everything
  // else stays on the futures market page.
  const conceptKey = marketEventKey(data);
  const detailHref = conceptKey ? eventPath(conceptKey) : `/futures/${data.id}`;
  const shareUrl = buildDiscoverShareUrl(detailHref, "futures", data.id);
  const leaderProbability = prob != null ? formatShareProbability(prob) : null;
  const shareText = leader && leaderProbability
    ? `${leader.name} is at ${leaderProbability} in ${data.name} on Bain Luck.`
    : `Track ${data.name} on Bain Luck.`;
  const heatmapRows = buildHeatmapRows(data);
  // Queue 309 Item 4 — no dollar volume on a feed card. Standing rule,
  // docs/design-system.md: "Dollar volume as social proof is banned too"
  // (ruling 2026-07-30). Volume still does its job in ranking and gating; it
  // stops being printed as money. `SignalBars` remains the confidence signal.

  // Typed locally: `data.discover_card` is still untyped debt (see the frontend
  // tsc baseline), so without this annotation these rows arrive as `any` and
  // leaderFirstSlice's generic widens them to its own constraint.
  const distributionRows: DistributionRow[] = data.discover_card?.distribution_outcomes ?? [];

  // UX-P237 — the card obeys the shape field.
  //
  // `suggested_format` is a text-regex guess; `market_type` is the classifier's
  // stored answer. Where they disagree the stored field wins (`shapeForbidsKernel`,
  // lib/marketShape.ts, which documents why only these two pairs are vetoed).
  const forbidsLadder = shapeForbidsKernel(data.market_type, "ladder-strip");
  const forbidsLeaderboard = shapeForbidsKernel(data.market_type, "top-3");
  const isQuantity = storedShape(data.market_type) === SHAPE_QUANTITY;
  const isField = storedShape(data.market_type) === SHAPE_FIELD;

  // The rungs the Quantity kernel draws, in preference order:
  //
  //  1. `threshold_points` — the archetype's PARSED numeric ladder. Each rung
  //     carries a real `value`, so the ladder can be ordered by it. This is the
  //     path 11 of the 13 live quantity cards already take, and it is unchanged.
  //  2. `distribution_outcomes` — used only when the stored shape says
  //     `quantity` and the parser found NO thresholds. That combination is how
  //     a date ladder arrives ("Before Sep 1, 2026" is not a numeric threshold),
  //     and it is the case the leaderboard was mis-drawing.
  //
  // Source 2 renders with `sort={false}`: these rows carry no numeric `value`,
  // so there is nothing to order them BY. They arrive probability-descending,
  // which is a real reading order for a cumulative ladder and makes no ordinal
  // claim for a disjoint one — unlike the leaderboard, which numbered them
  // "Rank N by probability". Disjoint bins ("40-50mm", "<30mm") parse as
  // thresholds and so never reach here; they keep their value-ordered ladder.
  const ladderFromDistribution = isQuantity && heatmapRows.length < 2;
  const ladderCells = ladderFromDistribution
    ? distributionRows.slice(0, 8).map((row, index) => ({
        key: `${row.label}-${index}`,
        label: row.label,
        probability: row.probability,
        value: undefined as number | undefined,
      }))
    : heatmapRows.slice(0, 8).map((row) => ({
        key: row.key,
        label: row.label,
        probability: row.probability,
        value: row.sortValue as number | undefined,
      }));

  const drawsLadder =
    !forbidsLadder &&
    ladderCells.length >= 2 &&
    (ladderFromDistribution || data.discover_card?.suggested_format === "threshold_heatmap");

  if (drawsLadder) {
    const shownCells = ladderCells;
    // "Above 50% through X" names the last rung of an ASCENDING numeric ladder
    // still at or above even money. It is only meaningful when the rungs are
    // ordered by a parsed threshold `value`. The distribution-fed rungs have no
    // such value (that is why they arrive here at all), so the phrase would be
    // pointing at whatever the probability sort happened to put last. Suppress
    // it there rather than print a sentence the ordering cannot support.
    const above50 = ladderFromDistribution
      ? []
      : shownCells.filter((r) => (r.probability ?? 0) >= 0.5);
    const lastAbove50Label = above50.length > 0 ? above50[above50.length - 1].label : null;

    return (
      <article className="relative overflow-hidden rounded-[10px] border border-surface-border bg-surface-card shadow-md hover:shadow-lg transition-shadow" aria-label={data.name} data-card-format="heatmap">
        <DismissBtn onDismiss={onDismiss} />
        {trending && <TrendBadge />}

        <div className="p-4">
          <div className="flex items-center gap-1.5 mb-1">
            <span className="text-[10px] font-semibold uppercase tracking-[0.04em] text-text-muted">{catStyle.emoji} {category}</span>
            <span className="ml-auto text-[11px] text-text-muted">{resolveText}</span>
          </div>
          <Link href={detailHref} onClick={onDetailClick} className="block group">
            <h3 className="text-[15px] font-semibold leading-snug text-text-primary group-hover:text-accent-brand transition-colors mb-4">{data.name}</h3>
          </Link>

          {/* #1102/L2-119: the "by WHEN" Quantity kernel. The old horizontal
              cell grid used equal flex-1 columns, so long date labels ("2029 or
              later") wrapped and broke alignment against the fixed-height cells.
              The vertical ladder (QuantityGroup, wide-label variant) never wraps
              its columns — one component covers "how MANY" and "by WHEN".
              L2-120: maxRungs is pinned to the sliced set so the `compact`
              default (4) doesn't silently crop the timeline. Date buckets tell
              their story in the TAIL (the modal/latest bucket is usually the
              highest-probability rung); with every bucket often below 50% there
              is no footer summary to carry a cropped rung, so a 5-bucket card
              must show all 5 — not just the first 4. */}
          <QuantityGroup
            bare
            compact
            wideLabels
            sort={false}
            maxRungs={shownCells.length}
            rungs={shownCells.map((row) => ({
              key: row.key,
              label: row.label,
              probability: row.probability,
              value: row.value,
            }))}
          />

          {/* Summary footer — orphan-free: "All below 50%" is dropped (it read as
              a context-less phrase). L2-183: the confidence glyph joins the right
              cluster so this multi-candidate kernel matches its ComparisonCard
              sibling. Queue 309: the volume figure that used to sit beside the
              glyph is gone, so the row renders only when something is left in it. */}
          {(lastAbove50Label || data.confidence_tier) && (
            <div className="flex items-center gap-1.5 mt-3.5 pt-3 border-t border-surface-border">
              {lastAbove50Label && (
                <>
                  <span className="text-[12px] text-text-secondary">Above 50% through</span>
                  <span className="font-mono font-bold text-[13px] text-accent-brand">{lastAbove50Label}</span>
                </>
              )}
              <span className="ml-auto flex items-center gap-1.5 text-[11px] text-text-muted">
                <SignalBars tier={data.confidence_tier} />
              </span>
            </div>
          )}

          <ActionBar liked={liked} setLiked={setLiked} shareUrl={shareUrl} shareTitle={data.name} shareText={shareText} contentType="futures" itemId={data.id} onShare={onShare} pin={pin} />
        </div>
      </article>
    );
  }

  // The leaderboard draws on the format hint as before, and ALSO when the stored
  // shape says `field` — otherwise vetoing a field's ladder above would drop the
  // card to the generic single-number hero and lose every entrant, which is a
  // worse read than the wrong ladder it replaced. A veto has to leave the card
  // somewhere better, not just somewhere else.
  if (
    (data.discover_card?.suggested_format === "outcome_distribution" || isField) &&
    distributionRows.length >= 4 &&
    !forbidsLeaderboard
  ) {
    // #1526: sort BEFORE slicing. `slice(0, 4)` on an array that is not
    // leader-first drops the leader — the Fed September card showed four
    // also-rans totalling 47% while the 56% "No change" row never rendered.
    // The rank column below is `index + 1` and titled "Rank N by probability",
    // so an unsorted slice mislabels the rows as well as losing the answer.
    const shownRows = leaderFirstSlice(distributionRows, 4);
    const remainingCount = data.discover_card.remaining_outcome_count + Math.max(0, distributionRows.length - shownRows.length);

    return (
      <article className="relative overflow-hidden rounded-[10px] border border-surface-border bg-surface-card shadow-md hover:shadow-lg transition-shadow" aria-label={`${data.name}`}>
        <DismissBtn onDismiss={onDismiss} />
        {trending && <TrendBadge />}

        <div className="p-3 pb-2">
          {/* L2-160 — muted category header (no internal-taxonomy "Distribution"
              pill; ruling: no internal taxonomy pills). Matches the handoff's
              leaderboard header + the sibling ComparisonCard treatment. */}
          <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
            <span className="text-[10px] font-semibold uppercase tracking-[0.04em] text-text-muted">{catStyle.emoji} {category}</span>
            <TemporalBadge badge={data.temporal_badge} />
            <span className="ml-auto flex items-center gap-1.5 text-[11px] text-text-muted">
              {resolveText && <span>{resolveText}</span>}
              {data.confidence_tier && resolveText && <span>·</span>}
              <SignalBars tier={data.confidence_tier} />
            </span>
          </div>
          <h3 className="text-base font-bold leading-tight text-text-primary line-clamp-2">{data.name}</h3>

          {contextSnippet && (
            <ExpandableContextText
              text={contextSnippet}
              expandedText={expandedContext}
              className="mt-2 text-xs leading-relaxed text-text-secondary"
              onExpand={onContextExpand}
              onCollapse={onContextCollapse}
            />
          )}
        </div>

        <div className="px-3 pb-3">
          <div className="space-y-1.5 border-y border-surface-border py-2">
              {shownRows.map((row, index) => {
                const probability = row.probability ?? 0;
                // UX-P046: a nonzero probability must never print as "0%".
                const pct = formatProbabilityPercent(probability);
                // #1574 acceptance (c): the fill IS the printed number. This was
                // previously divided by the leader's probability, which renders
                // the top bar full regardless of its actual value — a 12% leader
                // looked like a certainty, and two rows printing the same
                // percentage drew different bars.
                const width = Math.max(2, Math.round(probability * 100));
                const displayName = compactOutcomeName(row.label);
                return (
                  <div
                    key={`${row.label}-${index}`}
                    className="grid min-h-8 grid-cols-[1.25rem_minmax(0,1fr)_2.75rem] items-center gap-2 rounded-md px-1.5 py-1"
                  >
                    <span className="font-mono text-xs font-semibold tabular-nums text-text-muted" title={`Rank ${index + 1} by probability`} aria-label={`Rank ${index + 1}`}>{index + 1}</span>
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className={`min-w-0 text-xs leading-tight text-text-primary ${index === 0 ? "font-bold" : "font-semibold"}`} title={row.label}>{displayName}</span>
                        <MovementBadge m={row.movement} prob={row.probability} />
                      </div>
                      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-border">
                        <div
                          className={`h-full rounded-full transition-all duration-500 ${index === 0 ? "bg-accent-brand" : "bg-text-muted/35"}`}
                          style={{ width: `${width}%` }}
                        />
                      </div>
                    </div>
                    <span className="text-right font-mono text-xs font-bold tabular-nums text-text-primary">{probability > 0 ? pct : "—"}</span>
                  </div>
                );
              })}
              {remainingCount > 0 && (
                <div
                  className="grid min-h-7 grid-cols-[1.25rem_minmax(0,1fr)_2.75rem] items-center gap-2 rounded-md px-1.5 py-1 text-text-muted"
                >
                  <span className="font-mono text-xs font-semibold tabular-nums">{shownRows.length + 1}</span>
                  <span className="truncate text-xs font-medium">Field and remaining outcomes</span>
                  <span className="text-right text-xs font-semibold">+{remainingCount}</span>
                </div>
              )}
          </div>

          <ActionBar
            pin={pin}
            liked={liked}
            setLiked={setLiked}
            shareUrl={shareUrl}
            shareTitle={data.name}
            shareText={shareText}
            contentType="futures"
            itemId={data.id}
            onShare={onShare}
          />
        </div>
      </article>
    );
  }

  // UX-P162 — "one number per question", across surfaces and not just within a card.
  //
  // This hero rounded the leader's raw probability while `FeedCard` — the SAME
  // market, drawn by `/categories/*`, `/sports` and `/my-stuff` off the SAME
  // `GET /api/feed` payload — takes the card rule. The rule normalizes a
  // complement pair by its true total before rounding, so a pair summing to
  // 1.005 moves the leader by a point: the identical market reads 57% here and
  // 56% one tab over, which is the "blend is the product" thesis broken across
  // surfaces rather than within a card.
  //
  // LATENT TODAY, and deliberately reported as such: measured on the deployed
  // feed 2026-08-29 across all five feed surfaces, 114 unique futures cards, 7
  // two-outcome, and 0 currently disagree. The fix is here because the disagreement
  // is structural and silent — nothing would have told us the day a pair landed
  // off 1.00.
  //
  // `renderedLeaderPercent` is the shared decision (served-percent-wins,
  // leader-first anchoring, identity lookup) rather than a fourth hand-copy of
  // the three-line dance; `FeedCard` calls the same function, which is what makes
  // "they agree" a property of the code instead of a promise.
  const heroPercent = renderedLeaderPercent(data.top_outcomes, leader);
  // UX-P046's floor still runs on the PROBABILITY, not on the override, so a
  // served 0 over a live 0.003 prints `<1%` and not `0%`. That composition lives
  // in `formatProbabilityPercent`; passing `{ rendered }` does not opt out of it.
  const pctDisplay = prob != null ? formatProbabilityPercent(prob, { rendered: heroPercent }) : null;
  // UX-P052 (#1690) — the verbatim census finding names THIS number: rendered
  // "at full visual authority regardless of provenance", so a single 48h-old
  // print and a 3-source consensus look identical at the same 62%. Both hero
  // variants below take the coupling; the ladder rows do not, because the
  // finding (and the tier) is about the card's headline probability.
  const authorityClass = probabilityAuthorityClass(data.confidence_tier);
  const movementVal = leader?.movement;
  const movementUp = movementVal != null && movementVal > 0;
  // L2-160 — respect the 5% placeholder floor: suppress the hero movement delta
  // when the leader probability is a placeholder (illiquid ~5% floor), where the
  // "movement" is noise rather than a real 24h shift.
  const probIsPlaceholder = prob != null && prob <= 0.05;
  // UX-P048 (#1695) — `movement` is a WIRE FRACTION; the conversion to points
  // happens in exactly one place now (`formatMovementPoints`). This slot used to
  // print the raw fraction under a label reading "points", so a 64.0-point swing
  // to a new favourite rendered as `↑ 0.6` with a tooltip asserting "Up 0.6
  // points in the last 24h".
  //
  // The THRESHOLD is deliberately unchanged in value — only in unit. `>= 0.1` on
  // a fraction was always "≥ 10 points"; it is written that way now so the next
  // reader cannot mistake it for a tenth of a point, which is what the sibling
  // `toFixed(1)` made it look like. Whether 10 is the right bar is a live design
  // question with its measurement recorded on #1695 (it silences 20 of 21 cards
  // that carry a real move, including 7.0- and 5.0-point ones) — but changing it
  // here would have moved nine more cards in the same commit that fixed the
  // scale, and made this fix impossible to measure.
  const movementPts = movementPoints(movementVal);
  const movementDisplay = formatMovementPoints(movementVal);
  const movementStr = movementPts != null && Math.abs(movementPts) >= HERO_MIN_MOVEMENT_POINTS && !probIsPlaceholder
    ? `${movementUp ? "↑" : "↓"} ${movementDisplay}`
    : null;
  // L2-156 Item 3 — explain the arrow: it's a 24h probability move, not a rank change.
  const movementTitle = movementDisplay != null
    ? `${movementUp ? "Up" : "Down"} ${movementDisplay} points in the last 24h`
    : undefined;
  if (variantB) {
    // ── Variant B: data-pure (no image) ──
    return (
      <article className="relative overflow-hidden rounded-[10px] border border-surface-border bg-surface-card shadow-md hover:shadow-lg transition-shadow" aria-label={data.name} data-card-variant="B">
        <DismissBtn onDismiss={onDismiss} />
        {trending && <TrendBadge />}

        <div className="p-4">
          <div className="flex items-center gap-2.5 mb-3.5">
            <div className="w-[38px] h-[38px] rounded-lg bg-surface-elevated flex items-center justify-center text-lg shrink-0">
              {catStyle.emoji}
            </div>
            <div className="leading-tight min-w-0">
              <div className="text-[10px] font-semibold uppercase tracking-[0.04em] text-text-muted">{category}</div>
              {resolveText && <div className="text-[11px] text-text-muted mt-0.5">{resolveText}</div>}
            </div>
          </div>

          {pctDisplay && (
            <div className="flex items-end gap-3 mb-3">
              <span
                className={`font-mono font-bold text-4xl tracking-tight leading-none text-text-primary tabular-nums ${authorityClass}`.trim()}
                data-testid="futures-hero-probability"
                data-authority-tier={data.confidence_tier ?? undefined}
              >{pctDisplay}</span>
              {showProbabilityHint && (
                <span className="pb-1 text-[11px] leading-none text-text-muted" data-testid="hero-probability-hint">
                  {HERO_PROBABILITY_HINT}
                </span>
              )}
              {movementStr && (
                <div className="pb-1">
                  <div className={`font-mono font-bold text-[15px] whitespace-nowrap ${movementUp ? "text-accent-live" : "text-accent-danger"}`} title={movementTitle}>{movementStr}</div>
                  <div className="text-[10px] font-semibold uppercase tracking-[0.04em] text-text-muted mt-0.5">24h</div>
                </div>
              )}
            </div>
          )}

          {prob != null && (
            <div className="flex h-[7px] gap-0.5 mb-3.5">
              <div className="rounded-full bg-accent-brand shadow-inner" style={{ width: `${Math.round(prob * 100)}%` }} />
              <div className="rounded-full bg-text-muted/30 flex-1" />
            </div>
          )}

          <Link href={detailHref} onClick={onDetailClick} className="block group">
            <h3 className="text-[15px] font-semibold leading-snug text-text-primary group-hover:text-accent-brand transition-colors mb-1.5">{data.name}</h3>
          </Link>

          {contextSnippet && (
            <ExpandableContextText
              text={contextSnippet}
              expandedText={expandedContext}
              className="text-[13px] leading-relaxed text-text-secondary mb-2.5"
              onExpand={onContextExpand}
              onCollapse={onContextCollapse}
            />
          )}

          {/* Meta footer — L2-184: confidence glyph joins the same semantic
              footer as Variant A. SignalBars renders nothing when the tier is
              absent.
              Queue 309 Item 4: the dollar volume is gone. `resolveText` went
              with it here, and ONLY here, because this variant already prints
              it in its own header block above — it was rendered twice on every
              volume-bearing Variant B card, and dropping the volume would have
              made that duplication unconditional. Variant A, whose header does
              NOT carry it, keeps its footer copy. */}
          {data.confidence_tier && (
            <div className="flex items-center gap-1.5 text-[11px] text-text-muted">
              <SignalBars tier={data.confidence_tier} />
            </div>
          )}

          <ActionBar liked={liked} setLiked={setLiked} shareUrl={shareUrl} shareTitle={data.name} shareText={shareText} contentType="futures" itemId={data.id} onShare={onShare} pin={pin} />
        </div>
      </article>
    );
  }

  // ── Variant A: image-led (refined current treatment) ──
  return (
    <article className="relative overflow-hidden rounded-[10px] border border-surface-border bg-surface-card shadow-md hover:shadow-lg transition-shadow" aria-label={data.name} data-card-variant="A">
      <DismissBtn onDismiss={onDismiss} />
      {trending && <TrendBadge />}

      <div className={`relative ${hasImage ? "aspect-[16/10]" : "h-32"} flex flex-col justify-end overflow-hidden`} style={{
        background: hasImage
          ? `url(${data.image_url}) center/cover`
          : CATEGORY_GRADIENTS[data.llm_sport_category?.toLowerCase() ?? ""] || "linear-gradient(135deg, #0f172a, #1e293b)",
      }}>
        {/* Scrim gradient */}
        <div className="absolute inset-0" style={{ background: "linear-gradient(to top, rgba(0,0,0,0.6), rgba(0,0,0,0.04) 55%, rgba(0,0,0,0.22))" }} />

        {/* Category pill */}
        <div className="absolute top-2.5 left-2.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.04em] text-white bg-white/[0.18] backdrop-blur-sm px-2.5 py-1 rounded-full">
          {catStyle.emoji} {category}
        </div>

        {!hasImage && <span className="absolute inset-0 flex items-center justify-center text-[80px] opacity-[0.08] select-none pointer-events-none">{catStyle.emoji}</span>}

        {/* Probability hero bottom-left */}
        {leader && (
          <div className="relative z-10 px-3.5 pb-2.5">
            <div className="flex items-end gap-2">
              <span
                className={`font-mono font-bold text-[38px] tracking-tight leading-none text-white tabular-nums ${authorityClass}`.trim()}
                data-testid="futures-hero-probability"
                data-authority-tier={data.confidence_tier ?? undefined}
              >{pctDisplay}</span>
              {movementStr && (
                <span className={`font-mono font-bold text-[13px] pb-1 whitespace-nowrap ${movementUp ? "text-emerald-400" : "text-red-400"}`} title={movementTitle} aria-label={movementTitle}>{movementStr}</span>
              )}
            </div>
            <div className="text-[12px] font-medium text-white/85 mt-0.5 line-clamp-1">{leader.name}</div>
            {/* Queue 309 Item 2 — this hero sits on a photo scrim, so it uses the
                same white/opacity treatment as the leader name above rather than
                a surface token. */}
            {showProbabilityHint && (
              <div className="text-[11px] text-white/70 mt-0.5" data-testid="hero-probability-hint">
                {HERO_PROBABILITY_HINT}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="px-3.5 py-3">
        <Link href={detailHref} onClick={onDetailClick} className="block group">
          <h3 className="text-[15px] font-semibold leading-snug text-text-primary group-hover:text-accent-brand transition-colors mb-1.5">{data.name}</h3>
        </Link>

        {contextSnippet && (
          <ExpandableContextText
            text={contextSnippet}
            expandedText={expandedContext}
            className="text-[13px] leading-relaxed text-text-secondary mb-3"
            onExpand={onContextExpand}
            onCollapse={onContextCollapse}
          />
        )}

        {/* Queue 309 Item 4: volume removed; `resolveText` survives as the row's
            only text, so the separator now hangs off it alone. */}
        {(resolveText || data.confidence_tier) && (
          <div className="flex items-center gap-2 text-[11px] text-text-muted">
            {resolveText && <span className="whitespace-nowrap">{resolveText}</span>}
            {data.confidence_tier && resolveText && <span>·</span>}
            <SignalBars tier={data.confidence_tier} />
          </div>
        )}

        <ActionBar liked={liked} setLiked={setLiked} shareUrl={shareUrl} shareTitle={data.name} shareText={shareText} contentType="futures" itemId={data.id} onShare={onShare} pin={pin} />
      </div>
    </article>
  );
}

type HeatmapRow = {
  key: string;
  label: string;
  probability: number | null;
  movement: number | null;
  sortValue: number;
};

function buildHeatmapRows(data: FeedFuturesData): HeatmapRow[] {
  const byLabel = new Map<string, HeatmapRow>();
  const outcomesByName = new Map(
    data.top_outcomes.map((outcome) => [outcome.name.toLowerCase(), outcome])
  );

  for (const point of data.discover_card?.threshold_points ?? []) {
    const label = point.label.trim();
    if (!label) continue;
    const key = label.toLowerCase();
    const matchedOutcome = outcomesByName.get(key);
    const existing = byLabel.get(key);
    const probability = point.probability ?? matchedOutcome?.probability ?? null;
    const movement = matchedOutcome?.movement ?? null;
    const sortValue = existing
      ? Math.min(existing.sortValue, point.value)
      : point.value;

    byLabel.set(key, {
      key,
      label,
      probability: existing?.probability ?? probability,
      movement: existing?.movement ?? movement,
      sortValue,
    });
  }

  return Array.from(byLabel.values()).sort((a, b) => a.sortValue - b.sortValue);
}

function formatComparisonTheme(theme: string | null | undefined): string {
  switch (theme) {
    case "ipo_valuation":
      return "Valuation";
    case "commodity_ranges":
      return "Commodity";
    case "rotten_tomatoes_scores":
      return "Score";
    case "macro_ranges":
      return "Macro";
    case "weather_distributions":
      return "Weather";
    case "sports_paths":
      return "Path";
    default:
      return "";
  }
}

function compactOutcomeName(name: string): string {
  const trimmed = name.trim().replace(/\s+/g, " ");
  if (trimmed.length <= 22) return trimmed;

  const parts = trimmed.split(" ");
  if (parts.length < 2) return trimmed;

  const suffixes = new Set(["Jr.", "Jr", "Sr.", "Sr", "II", "III", "IV"]);
  const suffix = suffixes.has(parts[parts.length - 1]) ? ` ${parts.pop()}` : "";
  const last = parts.pop() || "";
  const initials = parts
    .filter(Boolean)
    .map((part) => `${part[0]}.`)
    .join(" ");

  return `${initials} ${last}${suffix}`.trim();
}

// ── Compact row used by GroupCard ──

export function FuturesCompactRow({ item, data }: { item: FeedItem; data: FeedFuturesData }) {
  // UX-P238 — same headline decision as the full card. This row prints the
  // percent beside `data.name` with no outcome label at all, so an inverted
  // hero is even less recoverable here than on the card it expands into.
  const leader = heroOutcome(data.top_outcomes);
  // UX-P162 — the same market's headline, so a group row and the full card it
  // expands into cannot print two different numbers for one question. `GroupCard`
  // and `ThemeBundleCard` render this row for markets that ALSO appear as their
  // own `FuturesCard`, so leaving it on raw rounding would have moved the
  // disagreement one component sideways instead of removing it.
  const compactPercent = renderedLeaderPercent(data.top_outcomes, leader);
  const context = feedContextSnippet(item);
  const conceptKey = marketEventKey(data);
  const detailHref = conceptKey ? eventPath(conceptKey) : `/futures/${data.id}`;
  return (
    <Link href={detailHref} className="flex items-center gap-3 group">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold line-clamp-2 group-hover:text-accent-brand transition-colors">{data.name}</div>
        {context && <div className="text-xs text-text-muted mt-0.5 line-clamp-2">{context}</div>}
      </div>
      {leader && (
        <div className="flex items-center gap-2 shrink-0">
          <MovementBadge m={leader.movement} prob={leader.probability} />
          <span className="font-mono tabular-nums text-sm font-bold">{leader.probability != null && leader.probability > 0 ? formatProbabilityPercent(leader.probability, { rendered: compactPercent }) : "—"}</span>
        </div>
      )}
    </Link>
  );
}
