import { sportVocab } from "@/lib/marketMapUtils";

/**
 * #6144 — WHAT THE SCORE DIFFERENTIAL CARD IS ALLOWED TO CALL ITSELF.
 *
 * ── WHAT THE READER SAW ────────────────────────────────────────────────────
 *
 * `/events/15311956`, Hanshin Tigers v Chunichi Dragons (NPB), read live ~2h45m
 * in and again at 12:30Z once it had been suspended
 * (`artifacts/ux-1259/before-slice-02.png`). The page says LIVE. There is **no
 * score and no inning anywhere on it**. Under the win-probability curve it
 * draws a card headed **"Score Differential"**, in the largest type on the
 * card, whose single line falls from +1 to −5.5 on a TIGERS/DRAGONS axis
 * labelled `+7 / +4 / +1 / −2 / −5 / −8`.
 *
 * A casual fan — the target user — reads that as *"Dragons lead by 5 runs."*
 * There is no score. The line is the sportsbooks' projected margin, and the
 * only thing on the card that says so is the small grey legend "Projected
 * margin" beneath it. The heading is what a reader prices, and the heading
 * asserts a score we do not hold.
 *
 * ── THE POPULATION, AND WHY IT DOES NOT DRAIN ──────────────────────────────
 *
 * Measured by live/226 at 11:50Z and again here at 12:28Z: every one of the
 * 36 rows at `status='live'` carried NULL `home_score`, `away_score`, `period`,
 * `game_clock` and `espn_id` — 18 ATP/WTA/other tennis, 1 esports, 1 soccer,
 * plus the NPB games earlier in the day. This is not a race and not a
 * live-writer fault: `statpal_livescores` is healthy, and its ingestion door
 * only ever reaches NFL/MLB/NBA/NHL — dark for soccer by decision, unparseable
 * for tennis. For these sports in-game NEVER brings an actual score, so the
 * card is permanently the masquerade, not briefly.
 *
 * ── WHY THE HEADING AND NOT THE GATE ───────────────────────────────────────
 *
 * The page's own gate comment (L2-157 Item 4) names this exact render — "a
 * projected-spread line masquerading as innings" — and suppresses the card
 * PREGAME, where it is empty chrome: one static pre-game quote under a bare
 * header, nothing to read. It opens the card again in-game on the assumption
 * that in-game implies actual scores, which for these sports it does not.
 *
 * Extending that suppression is the wrong half to move, for two reasons:
 *
 *   * IN-GAME THE PROJECTION IS CONTENT. It moved five and a half runs over
 *     two and three-quarter hours on this very specimen. For a sport whose
 *     score we cannot read it is the only "how is this game actually going"
 *     signal the page has, and deleting it leaves the reader with less.
 *   * ux/1034 B5 ALREADY RULED THE OPPOSITE WAY ON THE SAME CARD. For tennis —
 *     18 of today's live rows — it deliberately keeps the projection and drops
 *     only the wrong-unit actual line: *"the widget keeps its projection, and
 *     STOPS DRAWING A LINE IN THE WRONG UNIT."* A suppression here would
 *     silently reverse that ship.
 *
 * So the card is honest about what it holds instead of being taken away. Once
 * the heading says "Projected Run Margin", the legend ("Projected margin"), the
 * axis and the sibling card below it ("Run margin map — Expected run-margin
 * distribution") all say the same thing, and nothing on the card is claiming a
 * number the page does not have. There is then no absence to explain either,
 * which is why this ships no new grey sentence about our coverage (D102).
 *
 * ── THE UNIT COMES FROM THE SAME PLACE THE CARD BELOW IT GETS ITS OWN ──────
 *
 * `sportVocab` already titles this exact quantity for the market maps — "Run
 * margin map", "Goal margin map", "Game margin map", and a unit-free "Margin
 * map" for a sport nobody has declared. The heading is built from that vocab
 * rather than from a second table, so the two cards on one page cannot come to
 * call the same number two different things, and an undeclared sport prints no
 * unit this file invented.
 */

/** Title Case for a one-word unit ("run" → "Run"). */
function capitalize(word: string): string {
  return word ? word[0].toUpperCase() + word.slice(1) : word;
}

/**
 * Does this card draw a line of the score that was ACTUALLY played?
 *
 * This is the predicate `ScoreDifferentialChart` has gated its orange actual
 * series on since ux/1034 B5, lifted here so the heading and the series cannot
 * disagree: a card that says "Score Differential" while drawing no score is
 * exactly #6144, and two spellings of one question is how that comes back.
 *
 * The `scoreboardCountsTheUnit` half is ux/1034 B5's and is load-bearing well
 * beyond the sports with no feed at all: a tennis page HOLDS `score_history`,
 * but those points are SETS under a games axis, so the chart refuses to plot
 * them — and a heading keyed on "is there score history" rather than on "is a
 * score drawn" would call that card Score Differential with no score on it.
 */
export function actualScoreSeriesDrawn(opts: {
  sportKey?: string;
  scoreHistory?: { home_score?: number | null; away_score?: number | null }[] | null;
  espnHistory?: { home_score?: number | null; away_score?: number | null }[] | null;
}): boolean {
  if (!sportVocab(opts.sportKey).scoreboardCountsTheUnit) return false;
  if ((opts.scoreHistory?.length ?? 0) > 0) return true;
  return (opts.espnHistory ?? []).some(
    (p) => p.home_score != null && p.away_score != null
  );
}

/**
 * The card's heading: the name of what is drawn inside it.
 *
 * `"Score Differential"` is reserved for a card that draws the played score —
 * it has been this card's name for as long as it has had one, and where an
 * actual line exists it is the right name and does not move. Everywhere else
 * the card holds one thing, the market's projected margin, and says so.
 *
 * Computed from the page's UNFILTERED history on purpose. The heading is a
 * claim about what this card is *about* — whether we hold the played score for
 * this game — and the All / Since Start pills are a zoom within it, not a
 * change of subject.
 */
export function scoreDifferentialHeading(opts: {
  sportKey?: string;
  actualSeriesDrawn: boolean;
}): string {
  if (opts.actualSeriesDrawn) return "Score Differential";
  const unit = capitalize(sportVocab(opts.sportKey).unitSingular);
  return unit ? `Projected ${unit} Margin` : "Projected Margin";
}
