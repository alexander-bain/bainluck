/**
 * Period boundary derivation for chart annotations.
 * Extracts period transition timestamps from ESPN history, win prob history,
 * or scoring plays data — whichever is available.
 */

import type { ESPNHistoryPoint, WinProbHistoryPoint, ScoringPlay } from "./types";

/**
 * One entry of the served `period_markers` array (`routes/events.py`,
 * `app/utils/period_markers.py`). Everything past `period` is additive and
 * optional on the wire, so an older cached payload still decodes.
 */
export interface ServedPeriodMarker {
  timestamp: string;
  period: string;
  source?: string;
  precision?: string;
  not_before?: string | null;
}

export interface PeriodBoundary {
  /** ISO timestamp of the period transition */
  timestamp: string;
  /** Short display label (e.g., "Q2", "P2", "5", "2H") */
  label: string;
  /**
   * #3348 — WHO SAW THIS BOUNDARY. The server's `period_markers` carry a
   * `source` (`statpal` | `espn_box` | `win_prob` | `espn_state` are
   * instruments; `estimated` is arithmetic on `commence_time`) and, on the
   * observed-transition tier, a `precision` and a `not_before` lower bound.
   * `derivePeriodBoundaries` used to map every marker to `{timestamp, label}`,
   * so a tier-4 guess and an observed transition were byte-identical by the
   * time they reached a chart. Measured by ux/1319 on production 2026-09-17:
   * 46 of 60 completed soccer charts drew confident `1H`/`2H` rules nobody
   * observed, and `/events/15307941` (CFL) ruled `Q1 Q2 Q3 Q4` over
   * `espn_history: []`, `scoring_plays: []`, `win_prob_history: {}`.
   *
   * All three are OPTIONAL and ADDITIVE: a boundary the client derives from an
   * occurrence log (`espn_history`, `win_prob_history`, `scoring_plays`) names
   * that log as its source; a fixture written as `{timestamp, label}` is still
   * a valid boundary and reads as "provenance unknown", never as "estimated".
   */
  source?: string;
  /**
   * How much `timestamp` can be trusted AS A PERIOD START: `boundary_observed`
   * (bracketed inside one poll), `first_seen` (an instrument saw the period in
   * progress; it began at or before this) or `first_score` (the period's first
   * score, not its start). A first observed state is not an exact period start
   * — every client-derived boundary is `first_seen`.
   */
  precision?: string;
  /**
   * The period began AFTER this instant (the last observation that showed an
   * earlier state), or `null` when nothing bounds it from below.
   */
  notBefore?: string | null;
}

/** The server's word for "nobody observed this; it was placed by arithmetic". */
export const PERIOD_SOURCE_ESTIMATED = "estimated";

/** A boundary an instrument observed — anything provenance-less counts as observed
 * only in the sense that it was never MARKED an estimate; see `PeriodBoundary`. */
export function isEstimatedBoundary(b: { source?: string | null }): boolean {
  return b.source === PERIOD_SOURCE_ESTIMATED;
}

/**
 * The text a chart prints on a boundary's chip. An estimate is CLEARLY an
 * estimate (`~Q2`); an observed boundary prints exactly what it printed before
 * this field existed, so every pinned label in the test corpus is unchanged.
 * The `~` is the same mark `GamePlayCard` puts on a carried-forward clock
 * (#925): one glyph, one meaning — "not observed at this instant".
 */
export function periodBoundaryChipLabel(b: PeriodBoundary): string {
  return isEstimatedBoundary(b) ? `~${b.label}` : b.label;
}

/**
 * HALF the painted width of one period label, as a fraction of the chart's
 * visible time span. The number a reader actually feels is
 * `PERIOD_LABEL_INK_FRACTION` below; this is the historical base it is derived
 * from, kept because #6882's derivation is written in terms of it.
 *
 * UX-P022 derived this on the win-probability chart: label collision is a
 * function of PIXELS, so the rule has to be purely proportional. The earlier
 * hybrid — `max(duration * N%, some minutes)` — mixes a pixel budget with a time
 * budget, and the two only agree at one chart length: on a three-hour game the
 * minutes floor is far too tight, on a twenty-minute live game it is far too
 * wide.
 *
 * 🪤 IT IS NO LONGER A COLLAPSE THRESHOLD, AND #7876 IS WHY. Read as "markers
 * closer than 7% of the span are collapsed into one", this number silently
 * deleted a real boundary as soon as a game ran long — see `placePeriodLabels`.
 * Nothing compares a gap against it any more; it survives only as the term
 * `PERIOD_LABEL_INK_FRACTION` is written in.
 */
export const PERIOD_LABEL_MIN_SPACING_FRACTION = 0.07;

/**
 * How much wider than `PERIOD_LABEL_MIN_SPACING_FRACTION` a gap must be before
 * two labels read cleanly on the SAME row. Below it, the later label drops a
 * row.
 *
 * #6882 — NFL HALFTIME IS THE PAIR THIS EXISTS FOR, AND IT IS STRUCTURAL.
 * Measured on `/events/14638444` (Bills–Lions) at 390px with
 * `tools/period-label-gap-6882.mjs`, which reads the painted `getBoundingClientRect()`
 * of every marker label rather than its timestamp:
 *
 *   pair     clear gap (win prob / score diff)
 *   Q2 → HT      60.4px / 64.3px
 *   HT → Q3       3.4px /  5.5px   ← reads as one token, `HT Q3`
 *   Q3 → Q4      22.6px / 25.4px
 *
 * `HT → Q3` is 15.0 min on a 191.6 min span = 7.83%, so it clears
 * `PERIOD_LABEL_MIN_SPACING_FRACTION` by 1.6 minutes and both labels survive —
 * and then sit 3.4px apart. NFL halftime is structurally ~15 min and an NFL
 * broadcast structurally ~3.2 h, so this is a property of the sport: it happens
 * on every NFL game, on the one boundary a reader most needs distinguished.
 *
 * 🪤 RAISING `PERIOD_LABEL_MIN_SPACING_FRACTION` IS THE WRONG FIX, TWICE.
 * Collapsing this pair DELETES `HT` from every NFL chart — the collapse it used
 * to feed kept the LATER marker — which is strictly worse than the crowding. And
 * the constant is shared by both charts across every sport by deliberate design
 * (#888 / latency/467), so any move is also a claim about innings, halves and
 * hockey periods. The labels must both survive; only their layout changes.
 *
 * #7876 proved the second clause from the other direction: nobody raised the
 * constant, and `HT` was deleted anyway, because OVERTIME RAISED THE SPAN — which
 * against a purely proportional threshold is arithmetically the same thing. That
 * is why the threshold no longer decides what survives; see `placePeriodLabels`.
 *
 * WHY 1.8. At 390px the plot is 252px wide (measured, above). Reading the 3.4px
 * gap back through the 5px label offset puts a 2-character label at 11px bold at
 * ~16.3px wide, so a 3-character one (`OT2`, `/Q1`) is ~24px. Clean separation
 * needs the label's own width plus ~8px of air = ~32px of marker-to-marker
 * distance, and 32/252 = 12.7% of the plot — 1.81× the 7% collapse threshold.
 * Rounded to 1.8, the band is 7%–12.6%: `HT → Q3` (7.83%) staggers, `Q3 → Q4`
 * (15.66%) does not, and neither sits near an edge.
 *
 * IT IS A MULTIPLE OF THE COLLAPSE THRESHOLD, NOT A SECOND INDEPENDENT NUMBER,
 * so the two rules cannot drift apart: the band is by construction "survived the
 * collapse, but only just", which is the defect stated exactly.
 *
 * Staying proportional rather than pixel-measured is forced, not preferred: both
 * charts size themselves through `ResponsiveContainer width="100%"` and never
 * learn their own pixel width, and the server render every guard test uses has
 * no viewport at all. A pixel rule would be untestable and would behave
 * differently in the rig than in the browser. Over-firing is the safe direction
 * anyway — a staggered label is still wholly present and readable, where an
 * over-collapsed one is gone.
 */
export const PERIOD_LABEL_STAGGER_SPACING_MULTIPLE = 1.8;

/**
 * Vertical drop, in px, of a label pushed to the second row. One line at the
 * 10–11px the two charts label at; the drop is shared so they stagger alike.
 */
export const PERIOD_LABEL_ROW_HEIGHT_PX = 13;

/**
 * How close two period markers have to be before they are read as ONE moment
 * named twice, rather than as two boundaries.
 *
 * ⚠️ THE ONE RULE IN THIS MODULE MEASURED IN TIME, AND THE REASON IS THE WHOLE
 * POINT OF #7876. UX-P022 removed a `max(duration × N%, M minutes)` hybrid and
 * was right to: that rule's job was stopping two labels PAINTING ON TOP OF EACH
 * OTHER, which is a question about pixels, and a minutes floor answers it
 * differently at every chart length. This rule's job is different — "do these
 * two markers name the same transition?" — and that is a question about the
 * game, not about the picture. `"End of 2nd Quarter"` and `"Halftime"` are the
 * same moment whether the chart is twenty minutes wide or six hours. Answering
 * it proportionally is what broke: at 7% of the span it meant 84 seconds on a
 * live chart and 15 minutes on an overtime one, so it deleted halftime.
 *
 * MEASURED, on every derived boundary of four real payloads — two NFL
 * (14638444 regulation, 14780544 overtime) and two MLB (15313139, 15314713),
 * 53 adjacent pairs. The gap distribution is not a gradient; it is two clusters
 * with nothing between them:
 *
 *   60s ×6, 120s ×6   │   240s, 300s ×4, 420s ×2, 442s, 480s ×4, …
 *   ONE MOMENT, TWICE │   DISTINCT BOUNDARIES
 *
 * The low cluster is exactly the shape this exists for: `"end of the 2nd"`
 * arriving a minute before `"Top 3rd"`, and `"End of 2nd Quarter"` arriving
 * seconds before `"Halftime"`. The high cluster starts at 240s — `T9 → B9`, a
 * three-up-three-down half-inning, the tightest genuinely distinct pair any of
 * the four games contains.
 *
 * 150s sits in the empty space between them: 1.6× clear of the tightest real
 * boundary and 1.25× past the widest duplicate. The margins are deliberately
 * lopsided toward the real boundary, because the two errors are not equal —
 * keeping a redundant label is untidy, and deleting a real one is #7876.
 */
export const DUPLICATE_TRANSITION_WINDOW_MS = 150_000;

/**
 * Collapse markers that name the same transition twice, keeping the LATER —
 * `"End of 2nd Quarter"` then `"Halftime"` becomes `HT`, and `"end of the 2nd"`
 * then `"Top 3rd"` becomes `T3`. The later label names the moment better in
 * every pair the measurement above found.
 *
 * Input must be timestamp-ascending. This is the SEMANTIC pass and it knows
 * nothing about the chart: it removes markers that carry no information, so
 * that the layout pass below is only ever asked to place boundaries a reader
 * would actually want distinguished. Keeping the two apart is what stopped a
 * crowded chart and a repetitive one being answered with one number (#7876).
 */
export function collapseDuplicateTransitions<T extends { timestamp: string }>(
  ascending: T[],
): T[] {
  const out: T[] = [];
  for (const b of ascending) {
    const t = new Date(b.timestamp).getTime();
    if (out.length > 0) {
      const prevT = new Date(out[out.length - 1].timestamp).getTime();
      if (t - prevT < DUPLICATE_TRANSITION_WINDOW_MS) {
        out[out.length - 1] = b;
        continue;
      }
    }
    out.push(b);
  }
  return out;
}

/**
 * Painted width of one period label plus the air a reader needs after it, as a
 * fraction of the chart's visible span.
 *
 * NOT A NEW NUMBER. It is `PERIOD_LABEL_MIN_SPACING_FRACTION ×
 * PERIOD_LABEL_STAGGER_SPACING_MULTIPLE` — 12.6% — and that product is exactly
 * what #6882 derived it from: a 3-character label at 11px bold is ~24px, plus
 * ~8px of air, on the 252px plot a 390px screen draws, = 32px = 12.7%.
 *
 * This is the ONLY distance in this module a reader can feel. Two labels closer
 * than this on the SAME row touch; on different rows they never do, whatever
 * the gap. Every rule below spends this one budget against a different
 * obstacle — the next label (`placePeriodLabels`), or the plot's right rule
 * (`anchorPeriodLabels`) — which is what stops them drifting into several
 * numbers that mean one thing.
 */
export const PERIOD_LABEL_INK_FRACTION =
  PERIOD_LABEL_MIN_SPACING_FRACTION * PERIOD_LABEL_STAGGER_SPACING_MULTIPLE;

/**
 * How many rows of period labels the chart will paint before it gives up and
 * starts dropping markers.
 *
 * TWO, and the cost of a third is the reason. The chip band the chart reserves
 * above the plot grows a whole `PERIOD_LABEL_ROW_HEIGHT_PX` line per row
 * (`OddsChart`'s `band` calculation), and that height comes off a 390px phone
 * chart's drawing area. Two rows buy 2 × (1 / 12.6%) ≈ 15 labels across the
 * span, which is more than any sport's real boundary count except a deep
 * baseball game — so the third row would be bought for innings alone, and
 * innings are the labels a reader needs least.
 *
 * It is a BUDGET, not an assumption. `placePeriodLabels` drops a marker only
 * when this budget is exhausted, and the charts COUNT the rows they actually
 * got rather than trusting the number (`periodChipRowCount`), so raising it is
 * a one-line change that nothing downstream has to be told about.
 */
export const PERIOD_LABEL_MAX_ROWS = 2;

/**
 * The chart's own x categories as epoch ms, ascending, or `null` when the caller
 * did not supply an axis.
 *
 * 🔴 WHY THIS EXISTS AT ALL — THE BUDGET IS SPENT IN PIXELS, NOT IN MINUTES.
 * Every rule in this module is a proportion of the chart's width, and the whole
 * module used to convert that proportion into a number of MILLISECONDS. That is
 * only the same thing when the x axis is linear in time, and this one is not: it
 * is CATEGORICAL (`dataKey="time"`), so a marker is painted at its category's
 * INDEX and every category is the same width regardless of how much time it
 * covers. A page whose history starts hours before kickoff has sparse pre-game
 * categories an hour wide sitting beside in-game categories a minute wide.
 *
 * Measured, 2026-09-21, on `/events/15313139` at 390px with the fix in place and
 * spacing still computed in time: `T8` and `T9` were a full ink-width apart by
 * the clock and painted 7px apart, boxes OVERLAPPING BY 8px — the `TB2`/`T5T6`
 * smear #6658 exists to prevent, arriving from the one direction its guard could
 * not see, because the guard also measured in time. The jest arms were green.
 *
 * So positions are category indices whenever the caller knows its axis, and the
 * millisecond form survives only as a fallback for callers that do not.
 */
function categoryAxis(categoryTimestamps?: string[]): number[] | null {
  if (!categoryTimestamps || categoryTimestamps.length < 2) return null;
  return categoryTimestamps.map((t) => new Date(t).getTime());
}

/**
 * Index of the category a marker is painted on: the last one at or before it,
 * clamped into the axis. Binary search — this runs per marker per render.
 */
function categoryIndex(axis: number[], t: number): number {
  if (t <= axis[0]) return 0;
  if (t >= axis[axis.length - 1]) return axis.length - 1;
  let lo = 0;
  let hi = axis.length - 1;
  while (lo < hi - 1) {
    const mid = (lo + hi) >> 1;
    if (axis[mid] <= t) lo = mid;
    else hi = mid;
  }
  return lo;
}

/**
 * Decide which period labels are drawn and on which row, in one pass.
 *
 * Returns the survivors, timestamp-ascending, each carrying `labelRow` — 0 for
 * the top row, 1 for one line down. Input must be timestamp-ascending; each
 * chart bounds and filters the list its own way first, because they disagree on
 * what "on the chart" means: the win-probability chart measures its drawn extent
 * (CERT-1984), the score differential chart requires a drawn score line
 * (CERT-1989). Only this rule is shared, and it is shared because it is the same
 * pixel problem on the same page at the same width (#888 / latency/467 — the
 * score differential chart once carried a private pre-UX-P022 copy and smeared
 * `TB2`, `TB3`, `T5T6` at 390px while the chart directly above it did not).
 *
 * ── #7876: WHY THIS IS ONE PASS AND NOT TWO ──────────────────────────────────
 *
 * It used to be two: `dedupePeriodLabels` deleted a marker whose gap to its
 * predecessor was under 7% of the span, then `assignPeriodLabelRows` dropped a
 * row for anything still under 12.6%. On the completed Chiefs 33–30 Colts page
 * the win-probability chart read `Q2 Q3 Q4 OT`. There was no `HT`.
 *
 * The game's `HT → Q3` gap is 15.01 min — NFL halftime is structurally ~15 min —
 * and overtime stretched the span to 215.0 min, so the threshold was
 * 0.07 × 215.0 = 15.05 min. Halftime lost by 2.4 SECONDS, and because the
 * collapse kept the LATER of a too-close pair, the label the reader lost was the
 * one it most wanted. On a regulation broadcast (191.6 min) the identical pair
 * clears the identical threshold and both labels are drawn, staggered. So the
 * marker APPEARED IN REGULATION AND VANISHED WHEN THE GAME WENT TO OVERTIME —
 * visible to a reader who never reloaded.
 *
 * 🪤 THE FIRST PASS WAS ANSWERING A QUESTION THE SECOND PASS ALREADY OWNED.
 * A pairwise gap threshold cannot tell "one crowded pair on an otherwise empty
 * chart" from "a chart too dense to lay out" — and only the second is a reason
 * to delete anything. Five markers over 215 minutes need 5 × 12.6% = 63% of one
 * row's ink; KC–IND had room to spare and still lost a boundary.
 *
 * 🪤 AND LOWERING THE 7% WOULD HAVE BEEN A DEFERRAL, NOT A FIX. Halftime
 * survives while `15 min > threshold × span`, so every constant just names the
 * span at which the bug comes back: 7% fails past 214 min, 6.3% past 238 min.
 * Double overtime finds the next one. The defect is the SHAPE of the rule.
 *
 * ── WHAT DECIDES IT NOW ──────────────────────────────────────────────────────
 *
 * A marker is drawn if there is a row with room for it, and dropped only when
 * there is not. "Room" is `PERIOD_LABEL_INK_FRACTION` clear of whatever that row
 * last drew — the actual painted width of a label, which is the actual reason
 * two labels cannot share a spot. Consecutive markers need NO horizontal gap at
 * all when they land on different rows, because labels one line apart cannot
 * touch however close their rules are.
 *
 * This is strictly more permissive than the pair of rules it replaces — the old
 * collapse fired at 7% where collision starts at 12.6%, so it was deleting
 * markers the layout could always have drawn — and it is the same anti-smear
 * guarantee stated honestly for the first time. The old invariant, "no two
 * survivors closer than 7%", never implied legibility: 7% is INSIDE one label's
 * ink, which is exactly why #6882 had to add staggering behind it. The invariant
 * now is the one a reader can check: NO TWO LABELS ON THE SAME ROW ARE CLOSER
 * THAN ONE LABEL'S INK.
 *
 * ── THE TWO ORDERING RULES, BOTH LOAD-BEARING ────────────────────────────────
 *
 * LOWEST ROW WINS, so the FIRST of a crowded pair keeps the top row and the
 * later one drops. Not arbitrary: on the pair this was built for, the survivor
 * of the old collapse was `Q3`, so keeping the earlier label prominent is what
 * puts `HT` back where a reader looks for it.
 *
 * ON OVERFLOW THE LATER MARKER WINS, replacing the last one placed, in its row.
 * That is the old collapse's rule kept deliberately: on a ladder too dense to
 * draw whole, the newer boundary is the one a reader following the game wants.
 *
 * Input should already have run through `collapseDuplicateTransitions`, which
 * removes the markers that name a moment twice. This pass cannot tell a
 * redundant marker from a real one and must not try — that is the separation
 * #7876 turns on.
 *
 * `categoryTimestamps` is the chart's own x categories, in order. PASS IT: it is
 * what makes the spacing a statement about painted distance rather than about
 * elapsed time, and those differ by enough to smear labels on any page with
 * pre-game history (see `categoryAxis`). `chartDurationMs` is then only the
 * fallback for a caller with no axis to hand.
 */
export function placePeriodLabels<T extends { timestamp: string }>(
  ascending: T[],
  chartDurationMs: number,
  categoryTimestamps?: string[],
): Array<T & { labelRow: number }> {
  const axis = categoryAxis(categoryTimestamps);
  const span = axis ? axis.length - 1 : chartDurationMs;
  const ink = span * PERIOD_LABEL_INK_FRACTION;
  const at = (iso: string) =>
    axis ? categoryIndex(axis, new Date(iso).getTime()) : new Date(iso).getTime();

  const out: Array<T & { labelRow: number }> = [];
  // Where each row last drew a label. `-Infinity` reads as "this row is empty",
  // so an empty row always has room and needs no separate case.
  const rowLastMs: number[] = new Array(PERIOD_LABEL_MAX_ROWS).fill(-Infinity);

  for (const b of ascending) {
    const t = at(b.timestamp);

    const row = rowLastMs.findIndex((lastMs) => t - lastMs >= ink);

    if (row === -1) {
      // Every row is still inside one label's ink: this marker cannot be drawn
      // anywhere. Hand its position to the last marker placed — the later label
      // wins — rather than dropping it and leaving the earlier one to stand for
      // a moment that has moved on.
      //
      // No emptiness guard, and it is not an omission: every row starts at
      // `-Infinity`, so the FIRST marker always finds room while
      // `PERIOD_LABEL_MAX_ROWS >= 1`. Reaching here therefore means something
      // was already placed. A `if (prev)` beside it would be a condition that
      // cannot be false, which reads as a handled case and is not one.
      const prev = out[out.length - 1];
      rowLastMs[prev.labelRow] = t;
      out[out.length - 1] = { ...b, labelRow: prev.labelRow };
      continue;
    }

    rowLastMs[row] = t;
    out.push({ ...b, labelRow: row });
  }

  return out;
}

/** Where a period label is anchored, in the `ReferenceLine` label's own words. */
export type PeriodLabelPosition = "insideTopLeft" | "insideTopRight";

/**
 * Choose which side each period label grows out of, and drop a row where that
 * choice creates a collision the row rule above could not have seen.
 *
 * #7371 — A LIVE GAME'S NEWEST MARKER PRINTED A SINGLE ORPHAN GLYPH. On
 * `/events/15314713` (Angels–Twins, hero `Top 10th`) the right-hand period rule
 * was captioned **`T`**. There is no code path that emits a bare `T`: it is
 * `T10` with its last two glyphs cut off. `insideTopLeft` anchors the text
 * `start` at the rule, so a marker sitting ON the chart's last category grows
 * its label out of the svg, which ends 10px later at every width. Measured in
 * the rig at 390px before the fix: `x=385 anchor=start` against a plot rule at
 * 380 — 5px of room for a 24px word. It is the same structural clip as #3541's
 * bare `F` and #3525's stray `5`, on the one marker a live reader most wants.
 *
 * A live game reaches this shape every few minutes: the half-inning that just
 * started IS the newest data, so its boundary is at or within a pixel of the
 * right rule, and `Q`/`P`/`H` markers share the anchor in every other sport.
 *
 * WHY FLIP RATHER THAN DELETE THE CAPTION. #3541 answered the same clip by
 * dropping the `Final` marker's label, and that was right there: the hero
 * already carries a FINAL chip, so the word was redundant and its anchor could
 * not be changed without colliding with a period label it is not spaced
 * against. Neither holds here. `T10` is not printed anywhere else on the chart,
 * and a period label collides only with other period labels — which this
 * module already spaces, so the flip can be spaced by the same rule instead of
 * being a special case pleading its own exception.
 *
 * THE FLIPPED LABEL NEEDS TWICE THE BUDGET. A left-anchored label and a
 * right-anchored one on either side of a gap grow TOWARD each other, so the gap
 * has to hold both inks — that is UX-P022's finding, and it is why alternating
 * anchors was removed. It is not an argument against flipping the LAST label,
 * which has no neighbour to its right; it is the reason the flipped label's
 * clearance from its predecessor is `2 × PERIOD_LABEL_INK_FRACTION` rather than
 * the one-way stagger band. Under that, it drops a row — the same remedy #6882
 * chose for `HT → Q3`, for the same reason: both markers keep their caption.
 *
 * Over-firing is the safe direction (a staggered label is wholly readable, a
 * collapsed one is gone), and both charts size themselves through
 * `ResponsiveContainer width="100%"` and never learn their pixel width, so the
 * rule stays proportional like every other rule here.
 *
 * Input must be timestamp-ascending and ALREADY PLACED by `placePeriodLabels`:
 * this is the second layout pass and it only ever raises a row, never lowers
 * one.
 *
 * ── #7876: THE CLEARANCE CHECK WAS ASKING THE WRONG NEIGHBOUR ────────────────
 *
 * A flipped label grows LEFTWARD out of its rule, so the marker it can collide
 * with is the one BEHIND it — and only the one behind it ON ITS OWN ROW, since
 * labels a row apart cannot touch. This used to compare against
 * `out[out.length - 1]`, the previous marker in the ARRAY, which with two rows
 * in play is usually on the other row; the check then read `prev.labelRow === 0`
 * as false and silently passed.
 *
 * Measured on `/events/15313139` at 390px, both charts: `T9` is last, so it
 * flips; its predecessor in the array is `End 8th` on row 1, so no drop fired;
 * and its actual row-0 neighbour `T8` sat 31px away — inside the 64px a flipped
 * label needs — so `T9`'s caption painted backwards across `T8`, OVERLAPPING IT
 * BY 8px. That is the `TB2`/`T5T6` smear #6658 exists to prevent, on the pair
 * neither the spacing rule nor the row rule could see, because both had already
 * done their jobs correctly.
 *
 * A FLIPPED LABEL WITH ROOM ON NEITHER ROW IS NOT DRAWN. It needs twice the
 * budget (UX-P022: two labels either side of a gap grow toward each other), and
 * when neither row can give it that, the choice is a smear or a missing caption.
 * #3541 made the same trade for the `Final` marker and it is the right one: an
 * unreadable label is worse than an absent one, and this only ever reaches the
 * newest marker at the right edge.
 *
 * ── #8831: THE OTHER ROW CANNOT OVERLAP IT, BUT IT CAN OUT-ORDER IT ─────────
 *
 * #7876 was right that a label a row apart cannot TOUCH a flipped one. It can
 * still start to its right. On `/events/15318645` (Astros @ Athletics, final,
 * 390px) the right edge read `… T8 … T9 B8`: `T9` was last, so it flipped onto
 * row 1 and grew leftward, while `B8`, ten minutes earlier on row 0, grew
 * rightward from its own rule. One ink is wider than ten minutes there, so
 * `T9`'s caption began left of `B8`'s. A reader pairs captions with rules left
 * to right, so they read "B8" as the last line of the game.
 *
 * On a three-hour MLB span one ink is about 23 minutes and a half-inning about
 * ten, so this is the ordinary shape of every live MLB page, not an edge case.
 * The remedy follows from that:
 *   - FLIP THE PREDECESSOR when its own row has the same two inks of room
 *     behind it that a flipped label always needs. Both captions then grow
 *     leftward and end at their rules, so they read in order and both are kept.
 *   - Otherwise DROP THE PREDECESSOR, never the flipped marker. The flipped
 *     marker is the newest one, the one a live reader is following, and
 *     `placePeriodLabels` already settles overflow the same way: the later
 *     marker wins.
 * The predecessor never ends up out of order with anything behind it: the
 * flipped marker's own row is two inks clear, so anything else is at least one
 * ink behind the predecessor's new left edge.
 */
export function anchorPeriodLabels<T extends { timestamp: string; labelRow: number }>(
  ascending: T[],
  chartDurationMs: number,
  chartEndMs: number,
): Array<T & { labelPosition: PeriodLabelPosition }> {
  const ink = chartDurationMs * PERIOD_LABEL_INK_FRACTION;
  const out: Array<T & { labelPosition: PeriodLabelPosition }> = [];

  /** How far this marker sits from the last label drawn on `row` before `out[before]`. */
  const clearanceOn = (row: number, t: number, before = out.length) => {
    for (let i = before - 1; i >= 0; i--) {
      if (out[i].labelRow === row) return t - new Date(out[i].timestamp).getTime();
    }
    return Infinity; // nothing on that row yet
  };

  for (const b of ascending) {
    const t = new Date(b.timestamp).getTime();
    // Room to the right of this marker, measured against the plot's right rule.
    const flip = chartEndMs - t < ink;

    if (!flip) {
      out.push({ ...b, labelPosition: "insideTopLeft" });
      continue;
    }

    // Flipped: it grows backwards, so it needs two inks of clear room behind it
    // on whichever row it lands on. Its own row first — this pass raises a row,
    // never lowers one, so row 1 stays on row 1.
    const rows = b.labelRow === 0 ? [0, 1] : [1];
    const row = rows.find((r) => clearanceOn(r, t) >= 2 * ink);
    if (row === undefined) continue; // no room on any row: draw no marker here

    // #8831: the caption must not START left of a caption on the other row that
    // belongs to an earlier marker, or the two read in the wrong order. See the
    // docblock. Walk back over markers inside one ink of this rule; anything
    // older starts behind this caption's left edge.
    for (let k = out.length - 1; k >= 0; k--) {
      const prev = out[k];
      const tp = new Date(prev.timestamp).getTime();
      if (tp <= t - ink) break;
      // A flipped caption also starts behind this one. No same-row test: this
      // row is two inks clear (above), so nothing inside the window is on it.
      if (prev.labelPosition === "insideTopRight") continue;
      if (clearanceOn(prev.labelRow, tp, k) >= 2 * ink) {
        out[k] = { ...prev, labelPosition: "insideTopRight" };
      } else {
        out.splice(k, 1);
      }
    }

    out.push({ ...b, labelRow: row, labelPosition: "insideTopRight" });
  }
  return out;
}

/** Which horizontal band the period-label strip is painted in. */
export type PeriodStripBand = "top" | "bottom";

/**
 * How much clearer the far band must be, as a fraction of the y domain, before
 * the strip moves to it.
 *
 * It is a DEADBAND, and its job is to make "top" the answer to every question
 * that is close. `"top"` is what both charts drew before #7940, so a chart whose
 * series runs down the middle keeps the exact strip it has always had, and the
 * only charts that move are the ones where the far band is decisively emptier.
 *
 * 0.2 — a fifth of the plot. Measured on the four convicting games in #7940's
 * costing (ux/1431), the winning side's clear-air difference is 0.25–0.55, and
 * on the two home-LOSS controls it is negative, so the deadband sits well clear
 * of both populations rather than splitting either. A tighter number would start
 * flipping even games on noise; a wider one would leave the Chiefs OT chart —
 * the narrowest convicting case at 0.25 — struck through.
 *
 * 🪤 WHY THIS IS NOT DERIVED FROM `PERIOD_CHIP_BAND_PX`, WHICH IS THE OBVIOUS
 * MOVE. The strip's depth is 15px plus a row, and the honest question sounds
 * like "does the series come within that many px of the frame?". It cannot be
 * asked here: both charts size through `ResponsiveContainer height="100%"`
 * inside a `flex-1` parent, so neither the component nor the test rig knows the
 * plot's pixel height, and converting 15px into a fraction of the domain needs a
 * height nobody has. #7940's own instrument opens by saying exactly this, and it
 * is why `placePeriodLabels` is proportional too. So this rule asks a question
 * that has an answer in data space — WHICH END has more room — and never how
 * much room in pixels.
 */
export const PERIOD_STRIP_FLIP_MARGIN = 0.2;

/**
 * Put the period-label strip in whichever band the plotted series is NOT in.
 *
 * ═══ THE DEFECT ═══
 *
 * #7940: period labels are pinned to the plot top, and the chart plots the HOME
 * team's probability, so the two coincide exactly when the home team is winning
 * — the green line is drawn straight through the `Q4` glyphs. ux/1431 measured
 * the predicate across 6 games / 12 charts: **every home win collides, neither
 * home loss does**. That is about half of all completed games, not an edge case.
 *
 * The two bands hold complementary states — a series cannot be pinned against
 * both frames at once — so whenever one is full the other is empty. `bottomBandFree`
 * was true for every colliding label on all four convicting games. That is
 * structural, which is what makes this repair a comparison rather than a search.
 *
 * ═══ WHAT IT COMPARES ═══
 *
 * The CLEAR AIR at each end: the mean gap between the frame and the nearest ink
 * to it, normalised into the y domain. Per x sample the topmost plotted value
 * and the bottommost are taken — the collision is with whichever line is nearest
 * the frame, not with the average of all of them, and on a six-source chart
 * those are very different numbers. The strip goes to the end with more air, and
 * only if it wins by `flipMargin`.
 *
 * ═══ 🔴 THE WINDOW IS THE LABELS' OWN X SPAN, AND THIS IS MEASURED ═══
 *
 * The air is averaged from the FIRST period label to the end of the chart, never
 * over the whole series. A chart's left-hand side is pre-game — hours of it on
 * the "All" range — where the line sits mid-plot because nothing has happened
 * yet, and no label is drawn there to collide with anything.
 *
 * Built first without the window, measured on production data, and it left one
 * of the four convicting games completely unfixed: `15315580` (White Sox 8–1)
 * draws `T1 B3 T5 T9` at x = 248…329 of a plot spanning 100…352 — every label in
 * the right 40% — and its 4-of-4 collisions survived, because the flat pre-game
 * two thirds balanced the air and dragged the mean back inside the deadband. The
 * other three games flipped and looked like a fix. With the window it flips too.
 *
 * So the pre-game stretch is not merely noise, it is a MAJORITY of the samples on
 * a late-starting game, and averaging over it answers a question about a part of
 * the plot the strip is never drawn in.
 *
 * ═══ THE LIVE-GAME QUESTION, ANSWERED ═══
 *
 * #7940's costing left one thing open: on a live game the answer can change
 * mid-game, and a strip that jumps under a reader watching a comeback is its own
 * defect (#7876 is the precedent for a marker moving on a held page). Two choices
 * settle it, and neither is "read the tail":
 *
 *   - The window is anchored at the FIRST label and runs to the chart's end, so
 *     it only ever grows, and it grows by whole periods. It is not a trailing
 *     window and it cannot chase the last few minutes of a close game — which is
 *     the distinction that matters, because the fix above narrows the scope and
 *     narrowing scope is usually how a stable rule becomes a jittery one.
 *   - The deadband means a flip needs the far band to be a fifth of the plot
 *     clearer. A game that genuinely turns over will flip the strip ONCE, at the
 *     point the game has actually turned; a game that wobbles around even will
 *     not flip at all.
 *
 * A single flip on a genuine reversal is the honest outcome: at that moment the
 * top band really has been taken over by the series, and the alternative is
 * leaving the labels struck through for the rest of the game.
 *
 * ═══ CALLERS ═══
 *
 * Shared by `OddsChart` and `ScoreDifferentialChart` so the two strips cannot
 * drift apart, the same way `placePeriodLabels` and `anchorPeriodLabels` are.
 * The score chart is two-sided (its domain straddles 0), which is precisely the
 * case the issue flagged as "the bottom band need not be free" — this asks, so a
 * chart whose series hugs the floor keeps its strip at the top.
 *
 * @param rows   One entry per x sample, in x order; each holds that sample's
 *               plotted values. Nulls and gaps are skipped, so a caller may pass
 *               its raw rows.
 * @param yDomain `[min, max]` — the axis the values are read against, NOT the
 *               data's own range. A chart whose axis is zoomed (`computeWinProbYAxis`)
 *               puts the frame somewhere the raw values cannot tell you about.
 * @param window Optional; supplies the label span described above. Given the
 *               chart's own category timestamps and its drawn boundaries, the
 *               samples before the first boundary are dropped. Omit it (or pass
 *               a chart with no boundaries) and the whole series is read — which
 *               is the right answer when there are no labels to place.
 */
export function choosePeriodStripBand(
  rows: ReadonlyArray<ReadonlyArray<number | null | undefined>>,
  yDomain: readonly [number, number],
  window?: {
    categoryTimestamps?: ReadonlyArray<string>;
    boundaries?: ReadonlyArray<{ timestamp: string }>;
  },
  flipMargin: number = PERIOD_STRIP_FLIP_MARGIN,
): PeriodStripBand {
  const [lo, hi] = yDomain;
  // A degenerate or unreadable axis has no top and no bottom. Answering "top"
  // returns the chart to exactly its pre-#7940 rendering, which is the only
  // answer here that cannot make a chart worse than it already was.
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || hi <= lo) return "top";

  // The window's left edge, as an index into `rows`. The two inputs come from
  // the same memo on both charts, so they are the same list the labels are drawn
  // from — a window computed off anything else could exclude a label's own x.
  let from = 0;
  const stamps = window?.categoryTimestamps;
  const bounds = window?.boundaries;
  if (stamps && stamps.length === rows.length && bounds && bounds.length > 0) {
    let firstLabelMs = Infinity;
    for (const b of bounds) {
      const t = new Date(b.timestamp).getTime();
      if (Number.isFinite(t) && t < firstLabelMs) firstLabelMs = t;
    }
    if (Number.isFinite(firstLabelMs)) {
      const i = stamps.findIndex((s) => new Date(s).getTime() >= firstLabelMs);
      // `-1` means every category predates the first label, which cannot happen
      // on a chart that drew one — treat it as "no window" rather than as an
      // empty window, so a bad input falls back to the old, wider reading
      // instead of to no reading at all.
      if (i > 0) from = i;
    }
  }

  let topAirSum = 0;
  let bottomAirSum = 0;
  let samples = 0;

  for (let r = from; r < rows.length; r++) {
    const row = rows[r];
    let highest = -Infinity;
    let lowest = Infinity;
    for (const v of row) {
      if (typeof v !== "number" || !Number.isFinite(v)) continue;
      const raw = (v - lo) / (hi - lo);
      // Clamped because a series may legitimately sit outside a zoomed axis;
      // ink outside the frame is not drawn, so it cannot collide, and letting it
      // run negative would pay the far band air it has not earned.
      const norm = raw < 0 ? 0 : raw > 1 ? 1 : raw;
      if (norm > highest) highest = norm;
      if (norm < lowest) lowest = norm;
    }
    if (highest === -Infinity) continue; // an all-null sample says nothing
    topAirSum += 1 - highest;
    bottomAirSum += lowest;
    samples++;
  }

  // No plotted values at all: no series, so nothing to collide with.
  if (samples === 0) return "top";

  const topAir = topAirSum / samples;
  const bottomAir = bottomAirSum / samples;

  // Ties, near-ties and NaN margins all fall through to "top" — see the deadband
  // note above. Written as the positive test for that reason.
  return bottomAir - topAir >= flipMargin ? "bottom" : "top";
}

/** Everywhere a period label can be anchored, in recharts' own words. */
export type PeriodLabelAnchor =
  | "insideTopLeft"
  | "insideTopRight"
  | "insideBottomLeft"
  | "insideBottomRight";

/**
 * Turn one placed marker plus the chart's chosen band into the two props the
 * `<ReferenceLine>` label actually takes.
 *
 * Shared by both charts for the same reason `placePeriodLabels` is: the score
 * chart carried a private copy of the spacing rule once and smeared its inning
 * labels for it (latency/467). Two copies of "which way do rows stack" would
 * fail the same way and only on the chart nobody screenshotted.
 *
 * 🪤 THE ROW DIRECTION FLIPS WITH THE BAND, AND THAT IS THE WHOLE TRICK.
 * `dy` shifts the text block DOWN from whatever `position` computed (#6882).
 * Anchored at the top, row 1 must move down and away from the frame; anchored at
 * the bottom, the frame is underneath, so row 1 must move UP — the same stagger
 * reflected. Keeping `dy` positive in the bottom band would push row 1 through
 * the x axis and out of the plot, which reads on a screenshot as "the stagger
 * stopped working" rather than as a sign error.
 *
 * `top` returns byte-identical props to what both charts passed before #7940, so
 * every chart that does not flip renders exactly as it did.
 */
export function periodLabelPlacement(
  marker: { labelPosition?: string; labelRow?: number },
  band: PeriodStripBand,
): { position: PeriodLabelAnchor; dy: number } {
  const flipped = marker.labelPosition === "insideTopRight";
  const row = marker.labelRow || 0;

  if (band === "bottom") {
    return {
      position: flipped ? "insideBottomRight" : "insideBottomLeft",
      // `row === 0 ? 0` rather than `-row * …`, which yields NEGATIVE ZERO for
      // row 0 and reaches the markup as `dy="-0"`. Harmless to paint and
      // genuinely confusing to read on a diff of two rendered charts, which is
      // how this band gets checked.
      dy: row === 0 ? 0 : -row * PERIOD_LABEL_ROW_HEIGHT_PX,
    };
  }
  return {
    position: flipped ? "insideTopRight" : "insideTopLeft",
    dy: row * PERIOD_LABEL_ROW_HEIGHT_PX,
  };
}

/**
 * Largest plausible gap WITHIN a single game's period/inning markers. No sport
 * that renders period gridlines (NBA/NFL/MLB/NHL/soccer) has a 6-hour mid-game
 * pause, so a gap this large means the marker stream jumped to a DIFFERENT
 * game's data merged onto the same event (gotcha #32 territory — e.g. the
 * live-MLB exhibit whose period_markers still carried the prior day's innings).
 */
const SESSION_GAP_MS = 6 * 60 * 60 * 1000;

/**
 * Keep only the LAST contiguous session of a timestamp-ascending marker list.
 *
 * When markers from an earlier game are wrongly merged onto an event, their
 * inning/period labels ("Top 5th" from yesterday) get anchored to yesterday's
 * timestamp by the first-seen collapse below, then either vanish from the
 * visible domain or — in a wide "All" window — collide on the 12-hour "h:mm a"
 * categorical axis and render an inning to the LEFT of an earlier one (the
 * "T9 left of T1" bug, L2-163 Item 2c). Cutting to the latest contiguous run
 * discards the stale segment so the current game's innings stay monotonic. A
 * clean single-game stream (no large gaps) passes through unchanged.
 */
function keepLatestSession<T extends { timestamp: string }>(sorted: T[]): T[] {
  if (sorted.length < 2) return sorted;
  let cut = 0;
  for (let i = 1; i < sorted.length; i++) {
    const gap =
      new Date(sorted[i].timestamp).getTime() -
      new Date(sorted[i - 1].timestamp).getTime();
    if (gap > SESSION_GAP_MS) cut = i;
  }
  return cut > 0 ? sorted.slice(cut) : sorted;
}

/**
 * #4888 — WHAT A BARE PERIOD NUMBER MEANS, BY SPORT.
 *
 * ESPN's box-score fallback stores the period as a bare digit: the NFL season
 * opener (event 14780138) serves `period_markers` of exactly `"2"`, `"3"`, `"4"`,
 * source `espn_box`. Every branch of `normalizePeriodLabel` misses a bare digit
 * except the "already short" test, whose alternation ends in `\d+` and returns it
 * unchanged — so the chart drew dashed rules labelled `3` and `4` and a reader had
 * no way to learn they meant quarters. (Alex, 2026-09-09 iPad pass, item 6.)
 *
 * `"3"` alone is genuinely ambiguous — Q3 in football/basketball, P3 in hockey,
 * the 3rd inning in baseball — so the unit cannot be guessed inside a helper that
 * only sees the string. The caller knows the sport; this table is what it buys.
 *
 * WHY THIS LIVES HERE rather than reusing `lib/sportCategories.ts`: that module
 * answers "which tab does this league belong under", and its categories split pro
 * from college (`nfl`, `ncaaf`) in a way that has nothing to do with periods.
 * What a period number means is period knowledge, and it is four rows.
 *
 * BASEBALL IS DELIBERATELY ABSENT. A bare inning number cannot be completed
 * honestly — `T3` and `B3` are different moments and the digit does not say which
 * — so baseball keeps today's bare digit rather than gaining a fabricated half.
 *
 * #4955 — `regulation` IS NOT DECORATION; IT IS WHAT STOPS THE TABLE LYING.
 * A sport's period numbering runs past regulation into overtime, and completing
 * those with the regulation unit invents a period that does not exist: there is
 * no `Q5` in football, no `P4` in hockey, no `3H` in soccer. Past regulation we
 * return null and the caller's `?? s` leaves the bare digit — vague but true,
 * which is the same trade the baseball carve-out above makes. Unbounded, this
 * table turned an ambiguous label into a false one, the opposite direction from
 * the rest of #4888.
 *
 * ORDER-SENSITIVE, and the first matching row WINS OUTRIGHT — a row that matches
 * but is out of range returns null rather than falling through to a later row.
 * `basketball_ncaab` (men's college, two 20-minute halves) is therefore tested
 * before the `basketball_` row that gives everyone else quarters, and an NCAAB
 * `3` reads bare rather than picking up `Q3` from the row below it.
 *
 * The patterns are ANCHORED PREFIXES, not substrings, and that is load-bearing
 * here: `/^basketball_ncaab/` does not match `basketball_wncaab`, which plays
 * quarters and must keep them. (`sport_keys.py` carries both keys.)
 *
 * Table and bound mirror the Swift twin, `ios/…/Utilities/PeriodLabel.swift`
 * `barePeriodUnit` / `barePeriod` (#4888, PR #4925), so the two platforms read a
 * bare digit the same way. One known divergence past regulation, flagged by
 * native/107 and tracked under #1834, not introduced here: iOS falls through to
 * its ordinal (`5` → `5th`) where web leaves the bare digit (`5`). Web cannot
 * follow without contradicting its own plain-ordinal branch below, which
 * normalizes `"3rd"` → `"3"`.
 */
const BARE_PERIOD_UNIT: Array<{
  prefix: RegExp;
  regulation: number;
  format: (n: string) => string;
}> = [
  { prefix: /^americanfootball_/i, regulation: 4, format: (n) => `Q${n}` },
  { prefix: /^icehockey_/i, regulation: 3, format: (n) => `P${n}` },
  { prefix: /^soccer_/i, regulation: 2, format: (n) => `${n}H` },
  { prefix: /^basketball_ncaab/i, regulation: 2, format: (n) => `${n}H` },
  { prefix: /^basketball_/i, regulation: 4, format: (n) => `Q${n}` },
];

/** The sport-aware completion of a bare period number, or null to leave it be. */
function labelBarePeriod(n: string, sport?: string | null): string | null {
  if (!sport) return null;
  // `n` reaches here only from a `^\d+$` match, so this cannot be NaN — but it
  // CAN be 0, and `Q0` is as fabricated a period as `Q5`.
  const num = Number(n);
  if (!(num > 0)) return null;
  for (const { prefix, regulation, format } of BARE_PERIOD_UNIT) {
    if (!prefix.test(sport)) continue;
    return num <= regulation ? format(n) : null;
  }
  return null;
}

/**
 * Normalize ESPN's verbose period strings into short chart labels.
 *
 * Basketball/Football: "1st Quarter" -> "Q1", "Halftime" -> "HT"
 * Hockey: "1st Period" -> "P1"
 * Baseball: "Top 3rd" / "Bottom 3rd" -> "3"
 * Soccer: "1st Half" -> "1H", "2nd Half" -> "2H"
 * Generic: "Overtime" -> "OT"
 *
 * @param sport — the event's sport key (`americanfootball_nfl`, …). Optional and
 *   BACKWARD-COMPATIBLE: without it a bare period number renders exactly as it
 *   does today, so no existing caller changes behaviour by not passing it.
 */
export function normalizePeriodLabel(raw: string, sport?: string | null): string {
  if (!raw) return "";
  let s = raw.trim();

  // Reject pre-game date strings like "Wed, March 25th at 10:00 PM EDT"
  // These leak from ESPN status_detail during game transitions
  if (/\b(January|February|March|April|May|June|July|August|September|October|November|December)\b/i.test(s)) return "";
  if (/\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b.*\bat\b/i.test(s)) return "";

  // Strip clock prefix: "11:05 - 1st Quarter" → "1st Quarter"
  // ESPN status_detail includes game clock before the period name
  s = s.replace(/^[\d.:]+\s*-\s*/, "");

  // Detect "End of" / "Start of" prefix before stripping
  const isEnd = /^end\s+(?:of\s+)?/i.test(s);
  s = s.replace(/^(?:end|start)\s+(?:of\s+)?/i, "");

  // Halftime
  if (/^half\s*time$/i.test(s) || s === "HT") return "HT";

  // Overtime variants: "Overtime" → "OT", "End of OT" → "/OT", "2nd Overtime" → "OT2"
  //
  // 🪤 #7992 — THIS WAS THE ONE PERIOD FAMILY THAT DROPPED `isEnd` ON THE FLOOR.
  // `qMatch`, `pMatch` and `hMatch` below all honour it, so every other period
  // type distinguishes its two edges with the `/` prefix; overtime returned the
  // bare start label for both. `"End of OT"` and `"Overtime"` therefore
  // normalized to the SAME string, and `derivePeriodBoundaries` dedups by exact
  // label keeping the FIRST — so on a game carrying both, the end marker was
  // absorbed silently and nothing was visible.
  //
  // `/events/15312790` is the case where that silence breaks: the NHL game has
  // NO start-of-overtime marker at all — its only OT-ish row in any of the four
  // channels is `End of OT` — so the absorbed duplicate was the ONLY `OT` on the
  // chart, standing at 01:57:49Z, the moment overtime FINISHED, and reading like
  // every other marker on the strip: the period began here.
  //
  // The dedup argument that made this look harmless is an argument about
  // COLLISIONS, and it is silent on the singleton case — which is exactly where
  // the wrong survivor wins by default.
  if (/^(overtime|ot)$/i.test(s)) return isEnd ? "/OT" : "OT";

  // Numbered overtimes, both spellings: "2nd Overtime" and the already-short
  // "OT2". They are folded into ONE branch so the two cannot disagree about
  // `isEnd` the way `"End 8"` and `"End of 8th Inning"` did in #7982 — the reach
  // of a FORM is not the reach of the RULE, and that ship's own `"End 8"` arm
  // (zero corpus occurrences, fixed anyway) is the precedent this follows.
  //
  // MEASURED: zero occurrences of either numbered end-form in ux/1433's
  // 70-event / 7-sport corpus, so this arm changes no chart today. The 6 real
  // `End of OT` rows — 3 NFL, 3 NHL — are all handled by the branch above.
  //
  // `OT\d?` is deliberately gone from the "already short" test near the end of
  // this function: with `ot\d*` consumed here it would be unreachable there, and
  // a live-looking branch that can never run is what misled two readers in
  // #7982. The uppercase is preserved for the lowercase `"ot3"` input that test
  // used to catch.
  const otMatch = s.match(/^(?:(\d+)\w*\s+overtime|ot\s*(\d+))$/i);
  if (otMatch) return `${isEnd ? "/" : ""}OT${otMatch[1] ?? otMatch[2]}`;

  // Quarter (basketball, football): "1st Quarter" → "Q1", "End of 1st Quarter" → "/Q1"
  const qMatch = s.match(/^(\d+)\w*\s+quarter$/i);
  if (qMatch) return isEnd ? `/Q${qMatch[1]}` : `Q${qMatch[1]}`;

  // Period (hockey): "1st Period" → "P1", "End of 1st Period" → "/P1"
  const pMatch = s.match(/^(\d+)\w*\s+period$/i);
  if (pMatch) return isEnd ? `/P${pMatch[1]}` : `P${pMatch[1]}`;

  // Half (soccer): "1st Half" → "1H", "End of 1st Half" → "/1H"
  const hMatch = s.match(/^(\d+)\w*\s+half$/i);
  if (hMatch) return isEnd ? `/${hMatch[1]}H` : `${hMatch[1]}H`;

  // Baseball innings: "Top 3rd" → "T3", "Bottom 5th" → "B5"
  // Skip "Middle" to avoid chart clutter — only show half-inning starts.
  //
  // 🪤 "End" IS NOT IN THIS ALTERNATION, AND ITS ABSENCE IS THE FIX FOR #7982.
  // It used to be, and the branch was unreachable for every input: the `isEnd`
  // strip ~27 lines above consumes the word, so `"End 8th"` arrives here as
  // `"8th"` and `"End of 8th Inning"` as `"8th Inning"` — neither matches a
  // pattern anchored on `^(top|bottom|…)`. Both fell through to the ordinal
  // branch below and painted a BARE DIGIT on the chart (`T7  8  T9`), which is
  // the one label on the strip that does not name its half-inning and is not a
  // half-inning at all. `Middle` never had the problem because nothing strips
  // it. Two halves of one comment, two different behaviours.
  //
  // The drop now happens where the stripped string actually lands — at
  // `ordMatch` below, keyed on `isEnd` — so it cannot be un-reached again by a
  // change to the prefix strip. Listing `end` here as well would restore a
  // second, dead spelling of the same rule, which is what misled two readers.
  const iMatch = s.match(/^(top|bottom|mid(?:dle)?)\s+(\d+)/i);
  if (iMatch) {
    const half = iMatch[1].toLowerCase();
    if (half === "mid" || half === "middle") return "";
    const prefix = iMatch[1][0].toUpperCase();
    return `${prefix}${iMatch[2]}`;
  }

  // Plain ordinal inning: "3rd" -> "3" (sometimes ESPN just sends this), and
  // #7960 — the same fact with the unit spelled out: "8th Inning" -> "8".
  //
  // 🪤 IT IS THE LAST LINE OF THIS FUNCTION THAT MAKES A MISSING BRANCH VISIBLE
  // ON THE PAGE. `return s` is the right default for a label we do not
  // recognise, so every unhandled shape reaches the chart VERBATIM rather than
  // being dropped — which is why this one was not caught by anything counting
  // markers. On `/events/15316384` the strip read `T5 B5 T6 T7 8th Inning`, and
  // the odd one out was 57px wide on a 252px plot (23% of the chart) against
  // 7–15px for every sibling, overlapping the column `T9` is drawn in. The
  // defect is a WIDTH, so no guard that asks "is the label present and
  // correctly spelled" can see it.
  //
  // IT RETURNS THE BARE NUMBER, NOT `T8`. The verbose form does not say which
  // half-inning it is, and "8th Inning" is the whole inning. Inferring `Top`
  // to make the label match its neighbours would be #7901 in miniature —
  // asserting on the page a fact nobody observed, for tidiness. The bare number
  // is also exactly what the plain-ordinal form above already yields, so the
  // `1`, `4` and `8` already on that same chart are its precedent, not an
  // inconsistency introduced here.
  //
  // The alternation is what keeps a BARE "8" out of this branch — it must carry
  // an ordinal suffix or the unit or both. A bare number belongs to #4888's
  // `labelBarePeriod` below, which completes it from the sport, and quietly
  // swallowing it here would silently revert that. Anchored, so "8th Inning
  // Stretch" stays unknown and falls through to `return s` as it should.
  //
  // #7982 — AN "End of" ORDINAL IS DROPPED, NOT NUMBERED. Everything above about
  // the bare number is about the START of an inning, which is a thing that
  // happened at a time. `"End of 8th Inning"` is the other edge of the same
  // inning and the baseball branch has always meant to skip it; this is the line
  // that now does it, because the alternation up there never could.
  //
  // UNCONDITIONAL ON SPORT, MEASURED RATHER THAN ASSUMED. The worry is that this
  // branch is shared, so dropping here might silently delete a marker some other
  // sport needs. It does not: across ux/1433's 70-event / 7-sport corpus every
  // end-prefixed string in football, basketball and hockey carries its unit word
  // (`End of 3rd Quarter`, `End of 1st Period`) and is consumed by `qMatch` /
  // `pMatch` into `/Q3`, `/P1` long before it gets here — 267 of them, none a
  // bare digit — while soccer and MMA emit none at all. The 242 that DID reach
  // this line were baseball, every one. (`artifacts/ux-1434/reach-7982-*.json`.)
  //
  // So the sport gate would have been dead weight, and leaving it off is also the
  // safe direction for a shape nobody has seen yet: an unrecognised `End of Nth`
  // becomes a hole rather than a confident `N` asserting that period N STARTED
  // here when what was observed is that it ended.
  const ordMatch = s.match(/^(\d+)(?:(?:st|nd|rd|th)(?:\s+inning)?|\s+inning)$/i);
  if (ordMatch) return isEnd ? "" : ordMatch[1];

  // #4888: a BARE number is the one member of the "already short" set below that
  // does not name its own unit — `Q1`, `P2`, `1H`, `OT`, `HT` all do. Complete it
  // from the sport when we know it; fall through to the old behaviour when we
  // don't, or when the sport has no honest completion (baseball).
  //
  // #7982, the same rule one spelling over. `"End 8"` reaches HERE, not the
  // ordinal branch, because it carries neither an ordinal suffix nor the unit —
  // so a drop keyed only on `ordMatch` would leave the two spellings of one
  // marker behaving differently, which is the exact defect this ship is closing.
  // It is also the worse half: `labelBarePeriod` COMPLETES a bare number from
  // the sport, so `"End of 3"` on a football feed becomes `Q3` — not a terse
  // label but a false one, a quarter asserted to START where it was seen to end.
  //
  // Zero occurrences in the 70-event corpus, so this changes no chart today and
  // is a consistency arm rather than a reader-visible fix. It is here because
  // the reach of the form is not the reach of the rule, and #7960's control
  // pinned `"End 8" -> "8"` as an open question rather than a settled answer.
  const bare = s.match(/^(\d+)$/);
  if (bare) return isEnd ? "" : labelBarePeriod(bare[1], sport) ?? s;

  // Already short like "Q1", "P2", "1H", "HT". Every overtime spelling — bare
  // `OT` and numbered `OT2` alike — is consumed by the overtime branches above
  // (#7992), so this alternation no longer names one.
  if (/^(Q\d|P\d|\d+H|HT|\d+)$/i.test(s)) return s.toUpperCase();

  // Golf round labels: "R1", "R2", "R3", "R4", "PO" (playoff)
  if (/^R\d$/i.test(s)) return s.toUpperCase();
  if (/^round\s+(\d+)$/i.test(s)) {
    const rMatch = s.match(/^round\s+(\d+)$/i);
    return rMatch ? `R${rMatch[1]}` : s;
  }
  if (/^playoff$/i.test(s)) return "PO";

  return s;
}

/**
 * A period's IDENTITY, with the end-marker prefix removed (#7917).
 *
 * `normalizePeriodLabel` emits `/Q1` for "End of 1st Quarter" and `Q1` for its
 * start, and they are deliberately distinct LABELS. They are not distinct
 * PERIODS: both are statements about Q1. The fill below needs the period, not
 * the marker, or it treats a chart that already says `Q2` as one that is
 * missing the end of Q1 and draws both — two rules one minute apart naming the
 * same instant. Measured on the corpus: a fill keyed on the raw label imported
 * `/Q1`, `/Q3` and `/Q4` and took `14780544` from 5 markers to 9.
 */
function periodIdentity(label: string): string {
  return label.replace(/^\//, "");
}

/**
 * The label shapes `normalizePeriodLabel` deliberately PRODUCES, and the only
 * ones the fill below will import (#7917).
 *
 * 🪤 THIS EXISTS BECAUSE THE MORE PRINCIPLED-SOUNDING VERSION OF THE FIX WAS
 * REFUTED BY MEASUREMENT. Folding all four sources together — the general form
 * of "the cascade reads 'has ≥1 entry' as 'is complete'" — adds a rule labelled
 * **`Final`** to 50 of 70 corpus events, in every sport, because ESPN's
 * `period` field carries the game state at the end and `normalizePeriodLabel`'s
 * last line is `return s` (#7960). The priority cascade was load-bearing in a
 * way its comments never said: `period_markers` is a curated vocabulary and the
 * raw sources are not.
 *
 * So the allowlist is the protection that lets the fill be narrow, and it FAILS
 * SAFE BY CONSTRUCTION: an unrecognised shape is not filled, which is exactly
 * today's behaviour. Missing a legitimate shape costs a hole we could have
 * filled; admitting a junk one prints it on the chart.
 */
const FILLABLE_PERIOD_LABEL = /^\/?(?:Q\d+|P\d+|T\d+|B\d+|R\d+|\d+H|OT\d*|HT|PO|\d+)$/i;

/**
 * Fill the periods `primary` does not account for from `fallback` (#7917).
 *
 * `primary` stays authoritative for every period it names: nothing it supplies
 * is moved, relabelled or dropped, so a chart whose markers are already
 * complete is byte-identical after this. Only a period NO marker in `primary`
 * mentions can be added, and it enters at its own evidenced timestamp.
 */
function fillMissingPeriods(
  primary: PeriodBoundary[],
  fallback: PeriodBoundary[],
): PeriodBoundary[] {
  const claimed = new Set(primary.map((b) => periodIdentity(b.label)));
  // #3348 — an ESTIMATE does not get to silence an observation of the same
  // period. A tier-4 marker is `commence_time + offset`; if an occurrence log
  // actually saw that period, the observed time replaces the guess (and the
  // chip loses its `~`). Only estimates are superseded: an observed primary
  // marker keeps the #7917 guarantee that nothing it supplies is moved.
  const estimated = new Map<string, number>();
  primary.forEach((b, i) => {
    if (isEstimatedBoundary(b)) estimated.set(periodIdentity(b.label), i);
  });
  const kept = [...primary];
  const filled: PeriodBoundary[] = [];

  for (const b of fallback) {
    const id = periodIdentity(b.label);
    if (!FILLABLE_PERIOD_LABEL.test(b.label)) continue;
    if (claimed.has(id)) {
      const at = estimated.get(id);
      if (at === undefined || isEstimatedBoundary(b)) continue;
      kept[at] = b;
      estimated.delete(id);
      continue;
    }
    // Claim it here, not after the loop: the fallback holds `Q1` AND `/Q1`, and
    // without this the end marker is admitted by the same hole the start just
    // filled.
    claimed.add(id);
    filled.push(b);
  }

  // Nothing filled and nothing superseded: the same array, not a copy.
  if (filled.length === 0 && kept.every((b, i) => b === primary[i])) return primary;

  return [...kept, ...filled].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  );
}

/**
 * Derive period boundary timestamps from available history data.
 * Tries sources in priority order:
 *   1. espnHistory (has explicit period field)
 *   2. winProbHistory game_state.period
 *   3. scoringPlays period field
 *
 * E.g., for a basketball game: returns boundaries for Q1, Q2, Q3, Q4 starts.
 *
 * EVERY BOUNDARY MEANS THE SAME THING: THE FIRST MOMENT WE OBSERVED THAT PERIOD
 * (#7901). It used to mean that for all of them EXCEPT the first, which was
 * rewritten to the SCHEDULED start by `applyCommenceTime` — "the first period
 * boundary uses this instead of the first data point, which may arrive late".
 *
 * 🪤 That justification names the one circumstance in which the scheduled time
 * is least defensible. "Our data arrived late" and "the game started late" are
 * indistinguishable from inside this function, and the rule resolved the tie by
 * asserting, as a fact on the page, the time nobody observed.
 *
 * MEASURED on 60 completed events (2026-09-21, `artifacts/ux-1430/sizing-7901.json`):
 * the rewrite moved the first marker EARLIER by 9.6–47.6 minutes on real games —
 * MLB 15316297 by 47.6, WNBA by 13.8–16.7, NHL by 9.6–13.6 — never later, and
 * never toward evidence. The NHL rows are the proof that this is the game
 * starting late rather than us watching late: their period labels carry the game
 * clock ("19:57 - 1st Period" is three seconds in), so the period demonstrably
 * had only just begun, ten minutes after the scheduled face-off.
 *
 * On 15316297 the page therefore said the top of the 1st began at 3:35 PM and
 * that nothing happened for the next 47 minutes. Both game-state channels
 * (`mlb`, `espn`) have no point at all before 23:21Z; the only series running
 * across that window were Kalshi and Polymarket, which are market quotes and
 * carry no `game_state` on any of their 2,324 points. There was no evidence of
 * play, and the chart drew the claim anyway.
 *
 * Alex, 2026-09-14: scheduled kickoff/capture timestamps are not automatically
 * actual start/finish; align state markers to evidenced times.
 *
 * The second arm of the same rule was worse and unremarked: the regex also
 * matched `B1`, so a game we first saw in the BOTTOM of the 1st had that marker
 * moved to first pitch — a half-inning that by definition does not start there.
 *
 * ── #7917: PRECEDENCE IS PER-PERIOD, NOT PER-SOURCE ──────────────────────────
 *
 * `period_markers` is a TRANSITIONS log and the three fallbacks are PERIOD
 * OCCURRENCE logs. The first period is structurally unreachable in a
 * transitions log — there is no observed transition *into* Q1 — and that is
 * deliberate on the producer side (#5140, "absent, never kickoff"). So while
 * this cascade early-returned on the first non-empty source, it was reading
 * "this source has at least one entry" as "this source is complete", and the
 * moment the backend recorded its first transition the chart threw away every
 * marker the occurrence logs had supplied.
 *
 * A reader watching Giants @ Rams saw that happen under them on a page they
 * never reloaded: `Q1` at 00:40Z, gone by 01:01Z (#7917's table).
 *
 * `period_markers` still wins every period it names — this is a fill, not a
 * merge, and a chart whose markers are already complete does not move. MEASURED
 * on 70 completed events across 7 sports (`artifacts/ux-1433/reach.json`):
 * 20 change, ALL of them football (NFL 10/10, NCAAF 10/10), 19 gaining exactly
 * `Q1` and one — `15311740`, drawing only `Q2 Q4` — gaining `Q1` and `Q3`,
 * which is the general sparse-log case rather than the Q1 instance. MLB, NHL,
 * WNBA, soccer and MMA are unchanged: their `period_markers` already names
 * every period. Zero non-monotone sequences, zero label-packer evictions.
 *
 * Why this is now honest and was not when #7917 was filed: the issue's own
 * §Why says the occurrence logs have their first boundary pinned to kickoff by
 * `applyCommenceTime`. #7901 deleted that. A filled `Q1` therefore stands at
 * the first moment Q1 was OBSERVED — 1–18 minutes after the nominal start on
 * the corpus — which is the same kind of fact as every marker beside it, not a
 * scheduled time asserted as an observed one.
 */
export function derivePeriodBoundaries(
  espnHistory?: ESPNHistoryPoint[],
  winProbHistory?: Record<string, WinProbHistoryPoint[]>,
  scoringPlays?: ScoringPlay[],
  periodMarkers?: ServedPeriodMarker[],
  /** #4888: event sport key, so a bare period number can name its own unit. */
  sport?: string | null,
): PeriodBoundary[] {
  // Top priority: backend-computed period markers from scoring_plays table.
  // These come from StatPal play-by-play and have period info on every play,
  // covering games where ESPN and win_prob_history have no period data.
  let primary: PeriodBoundary[] = [];
  if (periodMarkers && periodMarkers.length > 0) {
    // Dedup by exact label (start "Q1" and end "/Q1" are distinct)
    const sorted = keepLatestSession(
      [...periodMarkers].sort(
        (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
      )
    );
    const firstSeen = new Map<string, PeriodBoundary>();
    for (const m of sorted) {
      const label = normalizePeriodLabel(m.period, sport);
      if (label && !firstSeen.has(label)) {
        // #3348 — the marker's provenance rides with it. `source` is carried
        // verbatim (an unknown vocabulary word is still not "estimated");
        // `precision` and `not_before` only when the server sent them.
        const b: PeriodBoundary = { timestamp: m.timestamp, label };
        if (typeof m.source === "string" && m.source) b.source = m.source;
        if (typeof m.precision === "string" && m.precision) b.precision = m.precision;
        if (m.not_before !== undefined) b.notBefore = m.not_before;
        firstSeen.set(label, b);
      }
    }
    primary = Array.from(firstSeen.values()).sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
    );
  }

  // The occurrence-log cascade, unchanged. It is still first-non-empty-wins
  // among its three members: folding THOSE together as well is the variant the
  // `FILLABLE_PERIOD_LABEL` docstring records as measured and rejected.
  const fallback = deriveFallbackBoundaries(espnHistory, winProbHistory, scoringPlays, sport);

  // #7917: `period_markers` cannot report the first period, so it does not get
  // to silence a source that can. It keeps every period it names; the rest are
  // filled at their own evidenced times.
  if (primary.length > 0) return fillMissingPeriods(primary, fallback);

  return fallback;
}

function deriveFallbackBoundaries(
  espnHistory?: ESPNHistoryPoint[],
  winProbHistory?: Record<string, WinProbHistoryPoint[]>,
  scoringPlays?: ScoringPlay[],
  sport?: string | null,
): PeriodBoundary[] {
  // Prefer win prob history — its timestamps are always present in chartData
  // (added via ensurePoint), so ReferenceLine x values will match chart categories.
  // ESPN history timestamps come from a separate table (ESPNSnapshot) and may not
  // have matching entries in the chart data when win_prob_snapshots deduped them.
  if (winProbHistory) {
    const boundaries = deriveBoundariesFromWinProb(winProbHistory, sport);
    if (boundaries.length > 0) return boundaries;
  }

  // Fallback to ESPN history (explicit period field, different table)
  if (espnHistory && espnHistory.length > 1) {
    const boundaries = deriveBoundariesFromEspn(espnHistory, sport);
    if (boundaries.length > 0) return boundaries;
  }

  // Try scoring plays
  if (scoringPlays && scoringPlays.length > 1) {
    const boundaries = deriveBoundariesFromScoringPlays(scoringPlays, sport);
    if (boundaries.length > 0) return boundaries;
  }

  return [];
}

/**
 * #3348 — the three occurrence logs the client can derive a boundary from,
 * named so a boundary can say which log saw it. These are the CLIENT's names for
 * the payload keys; the server's tier names (`espn_state`, `win_prob`, …) live on
 * markers the server built. Neither vocabulary contains `estimated`.
 */
export const CLIENT_SOURCE_ESPN_HISTORY = "espn_history";
export const CLIENT_SOURCE_WIN_PROB_HISTORY = "win_prob_history";
export const CLIENT_SOURCE_SCORING_PLAYS = "scoring_plays";

/** What every client-derived boundary can honestly claim about its timestamp. */
export const CLIENT_PRECISION_FIRST_SEEN = "first_seen";

/**
 * One boundary per distinct period label, at the first observation carrying it.
 *
 * `session` is timestamp-ascending and already session-trimmed. Each boundary
 * is `first_seen`: the log saw the period IN PROGRESS at `timestamp`, so the
 * period began at or before it — never "exactly here". `notBefore` is the
 * observation immediately before it in the same log (which showed a different
 * period), or `null` for the first label the log ever carried. That is the same
 * bracket shape the server's observed-transition tier serves (`not_before` /
 * `timestamp`), so a consumer can read either without caring who built it.
 */
function firstSeenBoundaries(
  session: Array<{ timestamp: string; period: string }>,
  sport: string | null | undefined,
  source: string,
): PeriodBoundary[] {
  const firstSeen = new Map<string, PeriodBoundary>();
  let previous: string | null = null;

  for (const point of session) {
    const label = normalizePeriodLabel(point.period, sport);
    if (!label) continue;
    if (!firstSeen.has(label)) {
      firstSeen.set(label, {
        timestamp: point.timestamp,
        label,
        source,
        precision: CLIENT_PRECISION_FIRST_SEEN,
        notBefore: previous,
      });
    }
    previous = point.timestamp;
  }

  return Array.from(firstSeen.values()).sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  );
}

function deriveBoundariesFromEspn(history: ESPNHistoryPoint[], sport?: string | null): PeriodBoundary[] {
  // Sort by timestamp, then drop any stale earlier-game segment (L2-163).
  const sorted = keepLatestSession(
    [...history].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    )
  );

  // Every unique period we observed gets a boundary at its first occurrence.
  // This handles missed transitions (e.g., ESPN sync started in Q2 — we still
  // mark Q2 even though we never saw Q1→Q2).
  return firstSeenBoundaries(
    sorted.flatMap((p) => (p.period ? [{ timestamp: p.timestamp, period: p.period }] : [])),
    sport,
    CLIENT_SOURCE_ESPN_HISTORY,
  );
}

function deriveBoundariesFromWinProb(
  winProbHistory: Record<string, WinProbHistoryPoint[]>,
  sport?: string | null,
): PeriodBoundary[] {
  // Merge all sources, extract period from game_state
  const allPoints: { timestamp: string; period: string }[] = [];

  for (const points of Object.values(winProbHistory)) {
    for (const point of points) {
      const gs = point.game_state as Record<string, unknown> | undefined;
      if (!gs) continue;

      // Standard period field (ESPN, stat_model)
      const period = gs.period;
      if (typeof period === "string" && period) {
        allPoints.push({ timestamp: point.timestamp, period });
        continue;
      }

      // MLB format: inning + inning_half (e.g., {inning: 3, inning_half: "top"})
      const inning = gs.inning;
      if (typeof inning === "number" && inning > 0) {
        const half = typeof gs.inning_half === "string" ? gs.inning_half : "top";
        // Construct a period string that normalizePeriodLabel can parse
        // e.g., "Top 3rd" → normalized to "3"
        const ordinal = inning === 1 ? "1st" : inning === 2 ? "2nd" : inning === 3 ? "3rd" : `${inning}th`;
        allPoints.push({
          timestamp: point.timestamp,
          period: `${half.charAt(0).toUpperCase() + half.slice(1)} ${ordinal}`,
        });
      }
    }
  }

  if (allPoints.length === 0) return [];

  // Sort by timestamp, then drop any stale earlier-game segment (L2-163).
  allPoints.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
  const session = keepLatestSession(allPoints);

  // Collect the first timestamp we see for each unique period label.
  // This handles missed transitions (e.g., ESPN sync started in Q2).
  return firstSeenBoundaries(session, sport, CLIENT_SOURCE_WIN_PROB_HISTORY);
}

function deriveBoundariesFromScoringPlays(plays: ScoringPlay[], sport?: string | null): PeriodBoundary[] {
  // Group scoring plays by period, use earliest timestamp per unique period.
  // Drop any stale earlier-game segment first (L2-163).
  const sorted = keepLatestSession(
    [...plays]
      .filter((p) => p.period && p.timestamp)
      .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
  );

  if (sorted.length === 0) return [];

  return firstSeenBoundaries(
    sorted.map((p) => ({ timestamp: p.timestamp, period: p.period as string })),
    sport,
    CLIENT_SOURCE_SCORING_PLAYS,
  );
}
