"use client";

/**
 * QuantityGroup — the Quantity kernel: one question, many lines, heat-strip.
 *
 * Queue L2-118 Phase 1, from the Claude Design "Props Reorg / Futures Detail"
 * spec (§03 Grouped markets — "A threshold ladder … the Discover heat-strip,
 * expanded with per-rung history").
 *
 * A "≥ N" market is really ONE continuous question. The legacy behavior stacked
 * it as N separate yes/no cards (a grid) and hid the shape. The ladder restores
 * it: every rung is cumulative, the heat reads top-down, and an optional
 * distribution strip shows where the value actually lands. Each rung carries a
 * chevron — a lens, never a buy button; tapping it re-scopes the history chart
 * (wired in Phase 2 via `onRungSelect`).
 *
 * This is the SHARED Quantity component — the same primitive covers MLB hit
 * props, RT scores, CPI ladders, and temperature buckets, at both detail-page
 * zoom (default) and Discover glance zoom (`compact`). It renders on the shape
 * field (`market_type === "quantity"`); see `lib/marketShape.ts`.
 *
 * Heat: uses the tokenized `probabilityHeat()` scale L2-117 cleaned — accent
 * tokens only, no raw Tailwind palette (CLAUDE.md light-mode rule).
 */

import { probabilityHeat } from "@/lib/probabilityColors";
import { formatMovementPoints, isRenderedMove } from "@/lib/probabilityDisplay";

export interface QuantityRung {
  /** Stable key (outcome id or the threshold string). */
  key: string | number;
  /** Row label, e.g. "≥ 80" or "$90K+". Pre-formatted by the caller. */
  label: string;
  /** Cumulative probability for this rung (0–1), or null when unknown. */
  probability: number | null;
  /** The reference line (e.g. the Certified Fresh ≥ 80 rung) — tinted + accented. */
  highlighted?: boolean;
  /** Numeric value used for ascending sort when `sort` is on. */
  value?: number;
  /**
   * UX-1052 item 4 — 24h movement as a wire fraction, rendered as a small
   * ± points chip beside the label. Alex, on the date-bucket card: "the leader
   * marked and the mover marked". Absent or sub-rounding movement prints
   * nothing (`isRenderedMove`), so a 0.003-point drift never becomes a badge.
   */
  movement?: number | null;
  /**
   * #2437 — the grade this rung states, precomputed by the caller with
   * `outcomeRowVerdict` (the one settled-state decision). A rung that states a
   * verdict renders the site-wide settled dialect — `Won`/`Lost`, `100%`/`0%`,
   * `Settled` — matching `OutcomeRow`, never a second vocabulary. `null` or
   * absent renders exactly as today.
   */
  verdict?: "won" | "lost" | null;
}

/** A single bar in the "where it lands" distribution heat-strip. */
export interface QuantityDistributionBin {
  label: string;
  /** Probability mass in this bin (0–1). Bars are scaled to the max mass. */
  mass: number;
  /** Whether this is the modal / highlighted bin. */
  highlighted?: boolean;
}

interface QuantityGroupProps {
  /** Group title (e.g. the market stem). Omitted → no title row. */
  title?: string;
  /** The ladder rungs. */
  rungs: QuantityRung[];
  /** Header hint on the right (default depends on interactivity). */
  hint?: string;
  /** Footer legend describing the highlighted line, e.g. "≥ 80 is Certified Fresh". */
  lineLabel?: string;
  /** Optional distribution strip — "where it lands · probability mass". */
  distribution?: QuantityDistributionBin[];
  /** Phase-2 seam: tap a rung to re-scope history. Renders a chevron when set. */
  onRungSelect?: (rung: QuantityRung) => void;
  /** Sort rungs ascending by `value` (design shows ≥60 → ≥95 top-to-bottom). */
  sort?: boolean;
  /**
   * UX-1052 item 2 — what `sort` sorts BY.
   *
   * "value" (default) is the threshold ladder's reading: a cumulative question
   * read low-to-high. "probability" is the discrete distribution's reading —
   * an exact-score market has no ordinal axis to climb, and taking the first
   * four rungs in scoreline order gives "0–0, 0–1, 0–2, 0–3", which is an
   * alphabetisation rather than a story. Most likely first.
   */
  sortBy?: "value" | "probability";
  /**
   * A plain footer line, e.g. "12 more scorelines". Unlike `lineLabel` it
   * carries no swatch and makes no claim about a highlighted rung — it exists
   * so a capped ladder can say it is capped instead of silently ending.
   */
  footnote?: string;
  /** Glance zoom for Discover cards: fewer rungs, tighter spacing, no distribution. */
  compact?: boolean;
  /**
   * Embed mode: drop the outer card chrome (border/shadow/padding) so the ladder
   * can render INSIDE an existing card that already owns the question context
   * (e.g. the Discover FuturesCard's title). Queue L2-119.
   */
  bare?: boolean;
  /**
   * Cap the number of rungs shown. Defaults to 4 in `compact`, unbounded
   * otherwise. Date-bucket cards use a slightly higher cap to keep the full
   * timeline legible without wrapping columns.
   */
  maxRungs?: number;
  /**
   * Wide-label mode for date/time buckets ("2029 or later") that don't fit the
   * fixed numeric-threshold label column. The "by WHEN" variant of the kernel —
   * same ladder, roomier label track. Queue L2-119.
   */
  wideLabels?: boolean;
}

function pct(p: number | null): string {
  return p == null ? "—" : `${Math.round(p * 100)}%`;
}

export default function QuantityGroup({
  title,
  rungs,
  hint,
  lineLabel,
  distribution,
  onRungSelect,
  sort = true,
  sortBy = "value",
  footnote,
  compact = false,
  bare = false,
  maxRungs,
  wideLabels = false,
}: QuantityGroupProps) {
  if (!rungs || rungs.length === 0) return null;

  let ordered = rungs;
  if (sort) {
    ordered = [...rungs].sort((a, b) => {
      if (sortBy === "probability") {
        return (b.probability ?? -1) - (a.probability ?? -1);
      }
      const av = a.value ?? Number.NEGATIVE_INFINITY;
      const bv = b.value ?? Number.NEGATIVE_INFINITY;
      return av - bv;
    });
  }
  const cap = maxRungs ?? (compact ? 4 : undefined);
  if (cap != null) ordered = ordered.slice(0, cap);

  const interactive = typeof onRungSelect === "function";
  const headerHint = hint ?? (interactive ? "tap a rung for its history" : undefined);

  // #4404 — the numeric track is a fixed 2.75rem, which is exactly what "≥ 95",
  // "$90K+" and an exact-score "2–1" need, and 18px short of a unit-bearing label.
  // A soccer totals ladder therefore printed "≥ 0.5goals" as TWO lines with the
  // operator orphaned above the number it qualifies — 32 rungs across the live
  // /sports page at 390px, four per card. The track is now sized to the longest
  // label this ladder actually prints: still ONE width for every rung, so two
  // rungs at the same percentage still draw the same bar (#1574 acceptance c),
  // and never a wrap — past 45% of the card it ellipsises instead. A ladder whose
  // labels all fit keeps the `w-11` class byte-for-byte, so the numeric ladders
  // that were already right are provably untouched.
  const NUMERIC_TRACK_CH = 5; // what 2.75rem holds at 13px in the mono face
  const longestLabelChars = ordered.reduce((m, r) => Math.max(m, r.label.length), 0);
  const roomyNumericTrack = !wideLabels && longestLabelChars > NUMERIC_TRACK_CH;

  // #8562 — the wide slot gets the same "measure the ink" rule, capped where it
  // always was. It used to be a flat 45% whatever it held, so a stock ladder
  // reserved 114px for "$730" — and once #5659's badge took 67px for
  // "▲56.0 pts", production measured the bar track at 0px on all three rungs of
  // the 1280 Meta card (254px row: 114 label + 67 move + 40 pct + gaps). The
  // width is still ONE per ladder (#1574 c), and it can only ever be ≤ 45%, so
  // every bar is as long as it was or longer; a label past ~16 characters hits
  // the cap and renders exactly as #7427 left it. The label does NOT shrink below
  // this to rescue a track: on a long date ladder that re-clips the year #7427
  // restored, and a missing bar loses nothing the printed percent does not say.
  const wideLabelWidth = `clamp(2.75rem, calc(${longestLabelChars}ch + 0.75rem), 45%)`;

  // #4644 — the SAME property as the comment above, one column further right.
  // The movement badge was a `shrink-0` sibling rendered ONLY on rungs that
  // moved, so it took its width (and its flex gap) out of the `flex-1` track
  // beside it: a rung carrying "▲48.0" measured its bar against a materially
  // shorter track than a rung with no badge. On the production "Netflix App
  // Downloads in September" card at 390px that inverted the ladder — 94% drew
  // a SHORTER bar than 88%, and the two longest bars belonged to the two
  // smallest numbers. #1574 acceptance (c) is the invariant: one track width
  // per ladder, so equal percentages draw equal bars.
  //
  // The slot is therefore reserved on EVERY row of a ladder that has a mover,
  // sized once from the longest badge THIS ladder prints (the same "measure the
  // ink you actually render" approach as the label track), so the bar starts at
  // the same x whether or not the rung moved. A ladder where nothing moved
  // renders no slot at all and is byte-for-byte what it was.
  // #5659 — POINTS, and the badge now SAYS points. `formatMovementPoints`
  // returns percentage POINTS and deliberately emits no unit, leaving that to
  // the caller; every other caller in the family supplies one and this one did
  // not. So a rung printed a bare "▲45.0" in a column between its label and a
  // number that IS a percent ("89%"), and the reader had nothing to tell them
  // what 45.0 was — a 45-POINT move, further than the whole remaining distance
  // to certainty, sitting inches from a percentage that makes it read as one.
  //
  // The `aria-label` two hundred lines down has always read "45.0 points". As
  // in #4066, the label was the spec sitting next to the bug the whole time.
  //
  // ONE DECIMAL IS KEPT, deliberately. `isRenderedMove` decides whether a badge
  // prints at all by asking whether the movement survives `toFixed(1)`, so
  // rounding the display to whole points here — matching `MovementBadge`'s
  // "18 pts" exactly — would print "▲0 pts" for every move under half a point
  // that the gate admits.
  const movementBadgeText = (movement: number | null | undefined): string =>
    `${(movement ?? 0) > 0 ? "▲" : "▼"}${formatMovementPoints(movement)} pts`;
  // #2437 — a rung that STATES a verdict never advertises a live move (#6488's
  // rule: a settled market never reads like an ongoing question). The slot is
  // measured over ungraded rungs only, and the badge below is gated the same way.
  const rungPrintsMove = (r: QuantityRung): boolean =>
    r.verdict == null && isRenderedMove(r.movement);
  const movementSlotChars = ordered.reduce(
    (m, r) => (rungPrintsMove(r) ? Math.max(m, movementBadgeText(r.movement).length) : m),
    0,
  );
  // The arrow is the one glyph in the badge that may fall back out of the mono
  // face, so its advance can exceed 1ch; the half-rem of slack absorbs that
  // rather than clipping a badge, and is the same on every row either way.
  // #8562, second half — the date ladder. Sizing the wide slot from its ink
  // rescued "$320 ▼7.8 pts" (73px of track on the 1280 Google card), but a
  // prose label cannot shrink that far: "Trump publicly insults Warsh?" at
  // 1280 printed "December 31 · ▲22.0 pts · [11px] · 43%" — a 43% bar 5px
  // long, and the Astra card drew 9px. The row cannot hold label, badge and
  // a bar side by side, so on such a ladder the badge moves UNDER the label
  // and its column goes away. Decided once per ladder, never per rung, so
  // every rung still has one track width (#1574 c) and no rung pays a slot.
  //
  // The estimate is the production row it failed on: 254px (a 1280 grid
  // card), less the 40px percent and three 12px gaps, at the measured
  // advances of the two faces (12px sans label ≈ 8px/ch + the 0.75rem pad;
  // 11px mono badge ≈ 6.6px/ch + 0.5rem). It predicts the Google card's 73px
  // exactly. Below a 48px track the badge stacks.
  const NARROWEST_ROW_PX = 254;
  const MIN_INLINE_TRACK_PX = 48;
  const inlineTrackPx =
    NARROWEST_ROW_PX -
    (8 * longestLabelChars + 12) -
    (6.6 * movementSlotChars + 8) -
    40 -
    3 * 12;
  const stackMove =
    wideLabels && movementSlotChars > 0 && inlineTrackPx < MIN_INLINE_TRACK_PX;
  // Stacked, the label cell must also hold the badge line under the label.
  const stackedCellWidth = `clamp(2.75rem, max(calc(${longestLabelChars}ch + 0.75rem), calc(${movementSlotChars}ch + 0.5rem)), 45%)`;
  const movementSlotStyle =
    movementSlotChars > 0 && !stackMove
      ? { width: `calc(${movementSlotChars}ch + 0.5rem)` }
      : undefined;

  // #2437 — the verdict slot, reserved on EVERY row of a ladder that states any
  // verdict, for the same reason as the movement slot above (#1574 acceptance
  // c): one bar x per ladder. "Won"/"Lost" is a closed vocabulary, so the slot
  // is sized to the longer word and never measured per ladder.
  const ladderStatesVerdict = ordered.some((r) => r.verdict != null);
  const verdictSlotStyle = ladderStatesVerdict
    ? { width: `calc(4ch + 0.5rem)` }
    : undefined;

  const inner = (
    <>
      {(title || headerHint) && (
        <div className="flex items-center gap-2 pb-2.5 mb-1.5 border-b border-surface-elevated">
          {title && (
            <span className="text-xs font-semibold uppercase tracking-wide text-text-muted">
              {title}
            </span>
          )}
          {headerHint && (
            <span className="ml-auto text-[11px] text-text-muted">{headerHint}</span>
          )}
        </div>
      )}

      <div className="flex flex-col gap-0.5">
        {ordered.map((rung) => {
          const heat = probabilityHeat(rung.probability);
          // #4660. The 2% floor exists so a genuine long shot still draws a
          // sliver instead of nothing (#1574), and it must not be applied to a
          // rung that has no price: that turned an absent number into a VISIBLE
          // red claim of near-impossibility. An unpriced rung draws no fill —
          // the track below stays, so the ladder keeps its shape and the `—`
          // in the number cell is the only thing that speaks.
          // #8167 — and the same coercion fires on an exact ZERO. A settled
          // spread board prices every losing rung at `0`, which is `known`, so
          // the floor drew a solid red pill on a row whose own number cell says
          // `0%`. At a glance that reads as a small non-zero value — the #4660
          // defect with a different input: the floor turning "nothing" into a
          // visible red claim. Gated on the PROBABILITY, not the rounded
          // percent, so a genuine long shot that rounds to 0% (0.004) keeps its
          // sliver and only a true zero loses it.
          const width =
            heat.known && rung.probability! > 0
              ? Math.max(2, Math.round(rung.probability! * 100))
              : 0;
          const RowTag = interactive ? "button" : "div";
          // #2437 — the settled dialect, matching `OutcomeRow` word for word:
          // `Won`/`Lost`, `100%`/`0%`, `Settled`, and the row tint. The
          // aria-label keeps its `{label}: {pct}` prefix — hooks address rungs
          // by it — with the verdict appended.
          const rungVerdict = rung.verdict ?? null;
          // #8562 — a tinted rung (the leader, or a graded one) is inset with
          // `px-2 -mx-2`. At `w-full` that padding came out of its CONTENT box,
          // so the leader's label and track were 16px shorter than its
          // siblings': production drew the 93% rung's bar SHORTER than the 92%
          // rung's under it (13px vs 22px at 390). Adding the 1rem the negative
          // margins give back keeps one track width per ladder (#1574 c).
          const insetRow = rung.highlighted || rungVerdict != null;
          const labelSpan = (
            <span
              title={wideLabels || roomyNumericTrack ? rung.label : undefined}
              style={
                // stacked, the width belongs to the wrapper below: a 45% cap on
                // this span would resolve against an auto-width parent, and each
                // rung would size to its own text (measured 171/156/158px tracks)
                wideLabels && !stackMove
                  ? { width: wideLabelWidth }
                  : roomyNumericTrack
                    ? { width: `clamp(2.75rem, calc(${longestLabelChars}ch + 0.5rem), 45%)` }
                    : undefined
              }
              className={[
                // A FIXED label width, not `max-w-`. With a content-width label
                // the `flex-1` track below is a different length on every row,
                // so two rungs printing the same % render visibly different
                // bars (#1574 acceptance c).
                //
                // #7427 — THE WIDE LABEL WRAPS; IT DOES NOT ELLIPSISE. The line
                // that used to sit here said "Truncate rather than wrap so the
                // track always starts at the same x", and that reason does not
                // hold: the width is a fixed 45% whether the text wraps or not,
                // so wrapping moves the track's x by exactly zero. Truncating
                // bought nothing the fixed width had not already bought, and it
                // cost the TAIL — which on these labels is the load-bearing
                // token. Measured on production at 390px (the slot is 128–135px
                // of a 300px row): "Before January 20, 2029" printed as "Before
                // January 20, …" directly above "Before 2027", clipping away the
                // one word that tells two rungs four years apart apart; and a
                // coal ladder printed "Above 20 million short t…" on all six
                // rungs, so the ladder stopped naming its own unit. 8 of 91
                // rungs on that draw were over the slot, by 16–33px each.
                //
                // Two lines, not unbounded: at this width two lines hold about
                // 44 characters against the 27 the widest measured label needs,
                // so the clamp is headroom rather than a second clip, while a
                // pathological label still cannot grow the row without limit.
                // `break-words` covers the one case wrapping alone cannot, an
                // unbroken token wider than the slot.
                //
                // This is deliberately NOT the #4404 treatment one arm below.
                // There the label is mono and numeric ("≥ 0.5goals") and wrapping
                // orphaned an operator above the number it qualified, so widening
                // the slot was right and wrapping was wrong. Here the label is a
                // prose phrase that already reads across a line break, and the
                // slot cannot be widened far enough anyway — the widest label is
                // 54% of the row, and paying that out of the `flex-1` track would
                // shorten every bar on every ladder to fix eight rows.
                //
                // #8562 — the 45% is now the CAP of `wideLabelWidth` above,
                // not the width; everything said here about wrapping holds.
                wideLabels
                  ? "shrink-0 break-words line-clamp-2 text-[12px] font-semibold leading-tight"
                  : roomyNumericTrack
                    ? "shrink-0 truncate font-mono text-[13px] font-bold tabular-nums"
                    : "w-11 shrink-0 font-mono text-[13px] font-bold tabular-nums",
                rung.highlighted ? "text-accent-brand" : "text-text-primary",
              ].join(" ")}
            >
              {rung.label}
            </span>
          );
          const moveBadge = rungPrintsMove(rung) ? (
            <span
              className={
                (rung.movement ?? 0) > 0 ? "text-accent-brand" : "text-text-secondary"
              }
              aria-label={`${(rung.movement ?? 0) > 0 ? "up" : "down"} ${formatMovementPoints(rung.movement)} points`}
            >
              {movementBadgeText(rung.movement)}
            </span>
          ) : null;
          return (
            <RowTag
              key={rung.key}
              type={interactive ? "button" : undefined}
              onClick={interactive ? () => onRungSelect!(rung) : undefined}
              className={[
                `flex items-center gap-3 ${insetRow ? "w-[calc(100%+1rem)]" : "w-full"} text-left`,
                compact ? "py-1" : "py-1.5",
                rung.highlighted
                  ? "px-2 -mx-2 rounded-lg bg-accent-brand/[0.06]"
                  : "",
                rungVerdict === "won"
                  ? "px-2 -mx-2 rounded-lg bg-accent-brand/[0.06] border border-accent-brand/30"
                  : rungVerdict === "lost"
                    ? "px-2 -mx-2 rounded-lg bg-surface-elevated/50"
                    : "",
                interactive ? "transition-colors hover:bg-surface-elevated/60 rounded-lg" : "",
              ].join(" ")}
              aria-label={`${rung.label}: ${pct(rung.probability)}${rungVerdict === "won" ? ", Won" : rungVerdict === "lost" ? ", Lost" : ""}`}
            >
              {stackMove ? (
                <span style={{ width: stackedCellWidth }} className="shrink-0 flex flex-col gap-0.5">
                  {labelSpan}
                  {moveBadge && (
                    <span className="whitespace-nowrap font-mono text-[11px] font-bold tabular-nums leading-tight">
                      {moveBadge}
                    </span>
                  )}
                </span>
              ) : (
                labelSpan
              )}
              {/* #2437 — the verdict, in `OutcomeRow`'s own words (token colors —
                  this file is under the L2-117 raw-palette guard).
                  Reserved on every row (see `verdictSlotStyle`) so the bar's x
                  never depends on whether this rung stated a grade. */}
              {verdictSlotStyle && (
                <span
                  style={verdictSlotStyle}
                  aria-hidden={rungVerdict == null ? true : undefined}
                  className="shrink-0 whitespace-nowrap text-left text-xs font-medium"
                >
                  {rungVerdict === "won" && (
                    <span data-testid="rung-verdict" className="text-accent-brand">
                      Won
                    </span>
                  )}
                  {rungVerdict === "lost" && (
                    <span data-testid="rung-verdict" className="text-accent-danger/80">
                      Lost
                    </span>
                  )}
                </span>
              )}
              {/* UX-1052 item 4 — "the mover marked". The BADGE still prints
                  only when the movement actually PRINTS as a move, so a
                  rounding residue cannot become an arrow (UX-P275); the SLOT
                  holding it is reserved on every row so the bar beside it is
                  measured against the same track (#4644). #2437: never on a
                  rung that states a verdict. A ladder that cannot fit the
                  column prints the badge under its label instead (`stackMove`). */}
              {movementSlotStyle && (
                <span
                  style={movementSlotStyle}
                  aria-hidden={rungPrintsMove(rung) ? undefined : true}
                  className="shrink-0 whitespace-nowrap text-right font-mono text-[11px] font-bold tabular-nums"
                >
                  {moveBadge}
                </span>
              )}
              <span className="flex-1 h-[18px] rounded-md bg-surface-elevated overflow-hidden">
                <span
                  className={`block h-full rounded-md ${heat.bar}`}
                  style={{ width: `${width}%` }}
                />
              </span>
              {/* #2437 — a graded rung prints a RESULT, never a quote:
                  `100%`/`0%` + `Settled`, in the design-token equivalents of `OutcomeRow`'s colors. An ungraded
                  rung keeps today's number, verdict or no verdict around it. */}
              <span
                className={[
                  "w-10 shrink-0 text-right font-mono text-[13px] font-bold tabular-nums",
                  rungVerdict === "won"
                    ? "text-accent-brand"
                    : rungVerdict === "lost"
                      ? "text-text-muted font-semibold"
                      : rung.highlighted
                        ? "text-accent-brand"
                        : "text-text-primary",
                ].join(" ")}
              >
                {pct(rung.probability)}
                {rungVerdict != null && (
                  <span
                    className={`block text-[10px] font-medium ${
                      rungVerdict === "won" ? "text-accent-brand/80" : "text-text-muted"
                    }`}
                  >
                    Settled
                  </span>
                )}
              </span>
              {interactive && (
                <span className="shrink-0 text-text-muted text-[15px] leading-none">›</span>
              )}
            </RowTag>
          );
        })}
      </div>

      {lineLabel && (
        <div className="flex items-center gap-1.5 pt-2 mt-1.5 border-t border-surface-elevated">
          <span className="w-2 h-2 rounded-[2px] bg-accent-brand shrink-0" />
          <span className="text-[11px] text-text-muted">{lineLabel}</span>
        </div>
      )}

      {footnote && (
        <div className="pt-2 mt-1.5 border-t border-surface-elevated">
          <span className="text-[11px] text-text-muted">{footnote}</span>
        </div>
      )}

      {!compact && distribution && distribution.length > 0 && (
        <div className="mt-3 pt-3 border-t border-surface-elevated">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-text-muted mb-2.5">
            Where it lands · probability mass
          </div>
          <QuantityDistribution bins={distribution} />
        </div>
      )}
    </>
  );

  if (bare) return inner;

  return (
    <div className="bg-surface-card rounded-card shadow-card border border-surface-border p-4">
      {inner}
    </div>
  );
}

function QuantityDistribution({ bins }: { bins: QuantityDistributionBin[] }) {
  const maxMass = Math.max(...bins.map((b) => b.mass), 0.0001);
  return (
    <>
      <div className="flex gap-[3px] items-end h-16">
        {bins.map((b, i) => {
          const h = Math.max(4, Math.round((b.mass / maxMass) * 100));
          return (
            <div key={`${b.label}-${i}`} className="flex-1 flex items-end h-full">
              <div
                className={[
                  "w-full rounded-t",
                  b.highlighted ? "bg-accent-brand" : "bg-accent-brand/40",
                ].join(" ")}
                style={{ height: `${h}%` }}
              />
            </div>
          );
        })}
      </div>
      <div className="flex gap-[3px] mt-1.5 font-mono text-[9px] text-text-muted text-center">
        {bins.map((b, i) => (
          <span
            key={`lbl-${b.label}-${i}`}
            className={`flex-1 ${b.highlighted ? "text-accent-brand font-bold" : ""}`}
          >
            {b.label}
          </span>
        ))}
      </div>
    </>
  );
}

/**
 * Build ladder rungs from futures threshold-group outcomes (the futures-detail
 * `threshold_groups` payload shape). Formats "≥ N unit" labels, sorts ascending,
 * and marks the top rung by probability as the reference line when none is
 * explicitly flagged.
 *
 * UX-1052 item 2 — an outcome may carry an explicit `label`, which is used
 * verbatim (exact-score rows send the scoreline, "2–3"). Alex's rule for this
 * queue: **a rung that cannot be labelled is not rendered.** An outcome with
 * neither a label nor a real threshold is DROPPED rather than given a made-up
 * "≥ 0" — that invented rung is the defect being fixed, and re-deriving it here
 * from a zeroed `threshold_value` would put it straight back.
 */
export function buildThresholdRungs(
  outcomes: {
    outcome_id: number;
    name: string;
    probability: number | null;
    threshold_value: number;
    threshold_unit?: string;
    threshold_direction?: string;
    label?: string | null;
  }[],
): QuantityRung[] {
  const rungs: QuantityRung[] = [];
  outcomes.forEach((o) => {
    const explicit = (o.label ?? "").trim();
    if (explicit) {
      rungs.push({
        key: o.outcome_id,
        label: explicit,
        probability: o.probability,
        value: o.threshold_value,
      });
      return;
    }
    if (o.threshold_direction === "exact") return; // labelled or nothing
    rungs.push({
      key: o.outcome_id,
      label: formatThresholdLabel(o.threshold_value, o.threshold_unit, o.threshold_direction),
      probability: o.probability,
      value: o.threshold_value,
    });
  });
  return rungs;
}

function formatThresholdLabel(
  value: number,
  unit?: string,
  direction?: string,
): string {
  const u = unit ?? "";
  const arrow = direction === "under" || direction === "below" ? "≤" : "≥";
  let num: string;
  if (u.includes("$")) {
    if (value >= 1_000_000) num = `$${(value / 1_000_000).toFixed(1)}M`;
    else if (value >= 1_000) num = `$${(value / 1_000).toFixed(0)}K`;
    else num = `$${value}`;
  } else {
    // #4404 — a WORD unit is a separate word: "0.5 goals", not "0.5goals". The
    // old join glued them into one token on every soccer totals rung on /sports.
    // A symbol unit ("%", "+", "°") stays welded to its number, which is why the
    // separator is decided by the unit's first character rather than by a flag.
    const suffix = u && !u.includes("$") ? (/^[A-Za-z]/.test(u) ? ` ${u}` : u) : "";
    num = `${value}${suffix}`;
  }
  return `${arrow} ${num}`;
}
