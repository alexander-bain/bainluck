"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { BarChart3 } from "lucide-react";
import { buildDiscoverShareUrl, buildLadderShareText, formatShareProbability } from "@/lib/share";
import type { LadderKind } from "@/lib/share";
import { marketEventKey, eventPath } from "@/lib/eventKey";
import { leaderFirstSlice } from "@/lib/discover/leaderOrder";
import { heroOutcome } from "@/lib/discover/heroOutcome";
import { buildHeroSrcSet, HERO_IMAGE_SIZES } from "@/lib/discover/heroSrcSet";
import { formatProbabilityPercent, formatMovementPoints, movementPoints } from "@/lib/probabilityDisplay";
import { renderedLeaderPercent } from "@/lib/renderedPercent";
import type { FeedItem, FeedFuturesData } from "@/lib/types";
import { CATEGORY_GRADIENTS, getCat } from "./constants";
import { compactOutcomeName, feedContextSnippet, feedExpandedContext, resolvesLabel } from "./utils";
import { AnimatedProbability, DismissBtn, TrendBadge, TemporalBadge, ActionBar, MovementBadge, ExpandableContextText, SignalBars, ForYouChip } from "./shared";
import { forYouCue } from "@/lib/discover/forYouCue";
import QuantityGroup from "../QuantityGroup";
import type { ActionBarProps, CardActionCallbacks } from "./types";
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
  // LAT-P191 (#1636, ruling on latency-022 = option b). Pure function of the
  // url and the measured raster width, so SSR and hydration agree; `null` means
  // "no safe ladder", and the hero then renders exactly as it did before.
  //
  // LAT-P195 (#2614): `image_width` is the photo's TRUE width when the backfill
  // has reached it and null until then. Passing it through is the whole ship —
  // with it the ladder is derived from the pixels the photo has, without it
  // from the conservative bound the url can prove, which is today's behaviour.
  const heroSrcSet = data.image_url
    ? buildHeroSrcSet(data.image_url, data.image_width)
    : null;
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
  // UX-P248 / CERT-678 repair — computed ONCE, above the variant fork, because
  // the fork is the defect. The first version of this ship read `forYouCue(item)`
  // inline at the single place it remembered to render, and this component has
  // FOUR `<article>` roots: threshold heatmap, outcome-distribution leaderboard,
  // Variant B and Variant A. Three of them returned before the call site was
  // reached, so the same reader saw the cue or did not depending on which shape
  // the feed picked for the market. Hoisting it does not by itself fix that —
  // `forYouCueRenderPaths.test.tsx` does, by asserting every article root prints
  // it — but it removes the reason the omission was easy to make.
  const cue = forYouCue(item);
  // Queue 309 Item 4 — no dollar volume on a feed card. Standing rule,
  // docs/design-system.md: "Dollar volume as social proof is banned too"
  // (ruling 2026-07-30). Volume still does its job in ranking and gating; it
  // stops being printed as money. `SignalBars` remains the confidence signal.

  if (data.discover_card?.suggested_format === "threshold_heatmap" && heatmapRows.length >= 2) {
    const shownCells = heatmapRows.slice(0, 8);
    const above50 = shownCells.filter((r) => (r.probability ?? 0) >= 0.5);
    const lastAbove50Label = above50.length > 0 ? above50[above50.length - 1].label : null;
    // UX-1052 item 4 — the leader is the highest-probability rung, marked in
    // place. On a date ladder the rows are chronological, so "the answer" is
    // not the top row and had nothing pointing at it.
    const leaderCell = shownCells.reduce<HeatmapRow | null>(
      (best, r) =>
        r.probability == null ? best
        : best == null || r.probability > (best.probability ?? -1) ? r
        : best,
      null,
    );
    const leaderCellKey = leaderCell?.key ?? null;
    // UX-1052 item 4 — the share text gets the same treatment as the card.
    // Alex on the old one: "Before 2027 is at 15% in When will Apple…" — it
    // reads backwards, and it hands the reader the single number the card was
    // criticised for. One sentence, question first, and it says the ladder has
    // more than one rung.
    // CERT-867 — the rung noun follows the ladder's own axis. `shownCells` is
    // both the count and the kind, so the sentence can never describe rungs the
    // card did not draw.
    const ladderShareText =
      leaderCell && leaderCell.probability != null
        ? buildLadderShareText(
            data.name,
            leaderCell.label,
            leaderCell.probability,
            shownCells.length,
            ladderKind(shownCells),
          )
        : shareText;

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
            <h3 className={`text-[15px] font-semibold leading-snug text-text-primary group-hover:text-accent-brand transition-colors ${cue ? "mb-1.5" : "mb-4"}`}>{data.name}</h3>
          </Link>

          {/* UX-P248 / Alex D-D — why this card is in front of THIS reader.
              CERT-678: this branch is a separate `<article>` from Variant A and
              returned before Variant A's chip was ever reached. The heading owns
              the gap when there is no cue, the chip's wrapper when there is, so
              the cue never changes the card's rhythm by appearing. */}
          {cue && <div className="mb-4"><ForYouChip cue={cue} /></div>}

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
          {/* UX-1052 item 4 — "outcomes as ordered bars … with the leader
              marked and the mover marked" (Alex, on the iPhone-18 date-bucket
              card). Chronological order is `sort={false}` over the backend's
              already-ordered rungs; the leader is the highlighted rung; the
              mover prints its own chip. Nothing here re-derives a number — both
              marks read what the payload sent. */}
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
              value: row.sortValue,
              movement: row.movement,
              highlighted: leaderCellKey != null && row.key === leaderCellKey,
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

          <ActionBar liked={liked} setLiked={setLiked} shareUrl={shareUrl} shareTitle={data.name} shareText={ladderShareText} contentType="futures" itemId={data.id} onShare={onShare} pin={pin} />
        </div>
      </article>
    );
  }

  // Typed locally: `data.discover_card` is still untyped debt (see the frontend
  // tsc baseline), so without this annotation these rows arrive as `any` and
  // leaderFirstSlice's generic widens them to its own constraint.
  const distributionRows: DistributionRow[] = data.discover_card?.distribution_outcomes ?? [];
  if (data.discover_card?.suggested_format === "outcome_distribution" && distributionRows.length >= 4) {
    // #1526: sort BEFORE slicing. `slice(0, 4)` on an array that is not
    // leader-first drops the leader — the Fed September card showed four
    // also-rans totalling 47% while the 56% "No change" row never rendered.
    // The rank column below is `index + 1` and titled "Rank N by probability",
    // so an unsorted slice mislabels the rows as well as losing the answer.
    const shownRows = leaderFirstSlice(distributionRows, 4);
    const remainingCount = data.discover_card.remaining_outcome_count + Math.max(0, distributionRows.length - shownRows.length);

    // `data-card-format` added by the CERT-678 repair: this was the only one of
    // the four `<article>` roots with no marker, so a render-path test could not
    // prove it had reached the leaderboard rather than falling through to
    // Variant A — the exact way a guard passes while the path it claims to
    // cover stays dark.
    return (
      <article className="relative overflow-hidden rounded-[10px] border border-surface-border bg-surface-card shadow-md hover:shadow-lg transition-shadow" aria-label={`${data.name}`} data-card-format="leaderboard">
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

          {/* UX-P248 / Alex D-D — why this card is in front of THIS reader.
              CERT-678: the leaderboard is its own `<article>` and was one of the
              four paths that stayed silent. No margin juggling here — this
              header block already spaces its children with `mt-*` on whatever
              follows the heading. */}
          {cue && <div className="mt-1.5"><ForYouChip cue={cue} /></div>}

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
                        {/* UX-P263 (#2561): `truncate` is what lets
                            compactOutcomeName leave a non-person label alone.
                            The column measures 170px and nothing here wrapped
                            before, so this clips only the labels that used to
                            be initialised into nonsense — and it clips them at
                            the real pixel boundary, which a character count
                            cannot do across fonts, accents and the 390px
                            viewport. The full string stays on `title`. */}
                        <span className={`min-w-0 truncate text-xs leading-tight text-text-primary ${index === 0 ? "font-bold" : "font-semibold"}`} title={row.label}>{displayName}</span>
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

          {/* UX-P248 / Alex D-D — why this card is in front of THIS reader.
              CERT-678: Variant B is the no-image half of the A/B split, so which
              of the two a reader got was a coin flip on a hash of their session
              id and the market id — and only one of them said anything. */}
          <ForYouChip cue={cue} />

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

      {/* LAT-P179: the hero used to be a CSS `background: url(...)`, which the
          browser can neither lazy-load nor skip — every one of the ~20 cards a
          cold Discover load mounts fetched its photo immediately, at low
          priority, even the ~18 below the fold. That is what pushed the cold
          load's last-byte `finish` out past 10 s while `load` fired at 983 ms.
          A real <img> gives the browser back `loading="lazy"`, so an off-screen
          hero is not fetched at all until the card approaches the viewport.
          The gradient moves onto the container so it now serves as the
          placeholder behind a not-yet-loaded photo instead of a blank box. */}
      <div className={`relative ${hasImage ? "aspect-[16/10]" : "h-32"} flex flex-col justify-end overflow-hidden`} style={{
        background: CATEGORY_GRADIENTS[data.llm_sport_category?.toLowerCase() ?? ""] || "linear-gradient(135deg, #0f172a, #1e293b)",
      }}>
        {/* Decorative — the card's accessible name is on the <article>, and the
            CSS background this replaces carried no accessible name either. */}
        {/* LAT-P191 (#1636) — `srcset`/`sizes`, capped at the raster we already
            serve (Alex ruling on `alex-inbox/latency-022`, option (b)). Every
            rung is a SHRINK of `src`, and the top rung IS `src`, so the four-
            column desktop slot (300 CSS px) stops downloading a 525–940 px
            photo while no device gets a byte heavier than today. Sharpness on
            a retina phone would need rungs ABOVE 940 px and costs mobile bytes
            — deliberately not taken; the reasoning is in `heroSrcSet.ts`. */}
        {data.image_url && (
          <img
            src={data.image_url}
            {...(heroSrcSet ? { srcSet: heroSrcSet, sizes: HERO_IMAGE_SIZES } : {})}
            alt=""
            aria-hidden="true"
            loading="lazy"
            decoding="async"
            className="absolute inset-0 h-full w-full object-cover object-center"
            data-testid="futures-hero-image"
          />
        )}

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

        {/* UX-P248 / Alex D-D — why this card is in front of THIS reader. Below
            the question, not over the hero photo: the hero already carries the
            category pill, the probability and the movement delta. */}
        <ForYouChip cue={cue} />

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
  /**
   * The rung's provenance, straight off the wire (`"date_bucket"`, `"outcome"`,
   * `"market_name"`). Carried rather than dropped because it is the only thing
   * that says whether this ladder's axis is time or magnitude, and the share
   * sentence has to know — CERT-867. The row builder used to discard it, which
   * is why "N windows" reached a share-price ladder.
   */
  source: string | null;
};

/**
 * Which axis this ladder runs on — CERT-867.
 *
 * `every`, not `some`: the backend returns date rungs whole and first
 * (`_date_bucket_points`), so a genuine date ladder is entirely date rungs. Any
 * mixture is therefore not a date ladder we recognise, and the neutral noun is
 * the safe answer. An empty list is not a date ladder either — the caller has
 * already gated on `length >= 2`, so this only defends the helper in isolation.
 */
function ladderKind(rows: HeatmapRow[]): LadderKind {
  return rows.length > 0 && rows.every((row) => row.source === "date_bucket")
    ? "date"
    : "threshold";
}

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
    // UX-1052 item 4: `top_outcomes` is the top THREE, so a ladder rung outside
    // it had no movement to show. Date-bucket rungs now carry their own.
    const movement = matchedOutcome?.movement ?? point.movement ?? null;
    const sortValue = existing
      ? Math.min(existing.sortValue, point.value)
      : point.value;

    byLabel.set(key, {
      key,
      label,
      probability: existing?.probability ?? probability,
      movement: existing?.movement ?? movement,
      sortValue,
      // First writer wins, matching every other field's merge above, so a
      // duplicate label cannot quietly change the ladder's kind.
      source: existing?.source ?? point.source ?? null,
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
  const rowCue = forYouCue(item);
  const conceptKey = marketEventKey(data);
  const detailHref = conceptKey ? eventPath(conceptKey) : `/futures/${data.id}`;
  return (
    <Link href={detailHref} className="flex items-center gap-3 group">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold line-clamp-2 group-hover:text-accent-brand transition-colors">{data.name}</div>
        {/* UX-P248 / CERT-678 repair — a path the BLOCK did not name and this
            queue found anyway. `_public_member_item` (backend/app/utils/
            discover_bundles.py) strips only underscore-prefixed keys, so a
            bundle member keeps `personalized`, `multiplier` and
            `personalization_reasons` all the way to here. `ThemeBundleCard`
            renders its members as full `FuturesCard`s, which now carry the cue
            on all four variants; leaving this row silent would have put the
            same boosted market's explanation on or off depending on whether
            the feed grouped it as a theme bundle or a plain group. */}
        {context && <div className="text-xs text-text-muted mt-0.5 line-clamp-2">{context}</div>}
        {rowCue && <div className="mt-1"><ForYouChip cue={rowCue} /></div>}
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
