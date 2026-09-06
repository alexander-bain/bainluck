/**
 * #3459 — a live match with NO probability data must not invent "50% — 50%",
 * and must not draw a hero of two 48px em-dashes each trailed by a naked `%`.
 *
 * THE PRODUCTION CASE THIS IS BUILT FROM. Event 15305801, Ram/Salisbury v
 * Arribage/Olivetti, US Open doubles, status `live`, read at 390px on
 * 2026-09-06. `futures_markets WHERE event_id = 15305801` → 0 rows.
 * `odds_snapshots WHERE event_id = 15305801` → 0 rows. There was no number
 * anywhere. The page nonetheless printed, on one screen:
 *
 *   hero    "—%–—%"                                   (data-probability="")
 *   chart   "Tracking will begin when odds are available"
 *   card    "Ram/Salisbury 50% — Arribage/Olivetti 50%"
 *
 * WHY IT HAPPENED, WHICH IS THE PART WORTH GUARDING. `computeLastChartPoint`
 * ended its source cascade with `?? 0.5`, so ABSENCE and a genuine pick-'em
 * market were the same value. Every consumer then had to re-derive the
 * distinction for itself: `resolveProbability` sniffed for the literal
 * `homeProb !== 0.5` and so suppressed the hero, `GamePlayCard` never learned
 * the trick and printed the placeholder as a reading. A test that only pinned
 * the card's output would leave the shared cause in place for the next
 * consumer, so the first two arms below pin the SIGNAL and the last three pin
 * the two screens that read it.
 *
 * Arm 3 is the one that is not a bug report: the `!== 0.5` sniff also threw
 * away every market that is honestly dead even, so a real 50/50 lost its hero
 * for looking like an absence. That arm FAILS on the parent for the opposite
 * reason to the others, which is how we know the fix replaced the judgment
 * rather than moving it.
 */

import { renderToStaticMarkup } from "react-dom/server";
import { computeLastChartPoint, resolveProbability } from "../../lib/eventKeyStats";
import GamePlayCard from "../../components/GamePlayCard";
import EventHeroProbabilityPair from "../../components/EventHeroProbabilityPair";
import type {
  ActiveChartPoint,
  EventDetailResponse,
  EventHistoryResponse,
  WinProbSourceMeta,
} from "../../lib/types";

function hist(partial: Partial<EventHistoryResponse>): EventHistoryResponse {
  return { event_id: 15305801, history: [], ...partial } as unknown as EventHistoryResponse;
}

function evt(partial: Partial<EventDetailResponse> = {}): EventDetailResponse {
  return {
    id: 15305801,
    home_team: "Ram/Salisbury",
    away_team: "Arribage/Olivetti",
    status: "live",
    commence_time: "2026-09-06T04:10:12Z",
    ...partial,
  } as unknown as EventDetailResponse;
}

/** One win-prob history point, complete — the away side is required. */
function wp(home: number, timestamp = "2026-09-06T05:00:00Z") {
  return [{ home_probability: home, away_probability: 1 - home, timestamp }];
}

/** A fully-shaped source-meta entry, so `win_prob_sources` is non-empty. */
const ESPN_META: WinProbSourceMeta = {
  display_name: "ESPN",
  type: "model",
  color: "#CC0000",
  snapshot_count: 12,
};

/**
 * The production point: live, no probability from any source, no score.
 * `aggregate_line` is OMITTED rather than nulled — absent is what the wire
 * actually sends for an event with no blend, and it is the case that matters.
 */
const NOTHING_KNOWN = hist({ win_prob_history: {}, history: [] });

describe("#3459 — the signal that separates 'no reading' from 'dead even'", () => {
  test("ARM 1: no source has a probability → the point declares probKnown false", () => {
    const pt = computeLastChartPoint(NOTHING_KNOWN, null, null);
    expect(pt).not.toBeNull();
    expect(pt!.probKnown).toBe(false);
  });

  test("ARM 2: a real reading of exactly 0.5 is KNOWN, not an absence", () => {
    // The distinguishing case. Same number, opposite meaning.
    const pt = computeLastChartPoint(
      hist({ win_prob_history: { espn: wp(0.5) } }),
      null,
      null,
    );
    expect(pt!.homeProb).toBeCloseTo(0.5);
    expect(pt!.probKnown).toBe(true);
  });
});

describe("#3459 — what the two screens do with it", () => {
  test("ARM 3: a genuine 50/50 chart point now REACHES the hero", () => {
    // Regression the old `homeProb !== 0.5` sniff caused: an honestly even
    // market was discarded for resembling the placeholder.
    const evenPoint: ActiveChartPoint = {
      timestamp: "2026-09-06T05:00:00Z",
      homeProb: 0.5,
      awayProb: 0.5,
      probKnown: true,
    };
    const resolved = resolveProbability(
      evt(),
      hist({ win_prob_sources: { espn: ESPN_META } }),
      evenPoint,
      true,
      false,
    );
    expect(resolved.homeProb).toBeCloseTo(0.5);
  });

  test("ARM 4: the card says 'No price yet' rather than printing 50% — 50%", () => {
    const pt = computeLastChartPoint(NOTHING_KNOWN, null, null)!;
    const html = renderToStaticMarkup(
      <GamePlayCard
        activePoint={null}
        homeTeam="Ram/Salisbury"
        awayTeam="Arribage/Olivetti"
        lastPoint={pt}
      />,
    );
    expect(html).toContain("No price yet");
    // The exact string a reader saw on production, from either side.
    expect(html).not.toContain("50%");
  });

  test("ARM 5: the hero says it in words instead of drawing two em-dash bars", () => {
    const html = renderToStaticMarkup(
      <EventHeroProbabilityPair
        homeProb={null}
        awayProb={null}
        homePct={null}
        awayPct={null}
      />,
    );
    // `—%` is the defect verbatim: a 48px em-dash reads as a redaction bar and
    // the `%` after it has nothing to qualify.
    expect(html).not.toContain("—%");
    expect(html).toContain("No price yet");
    // The rail's contract selector must survive the empty state (UX-P003).
    expect(html).toContain('data-testid="event-hero-probability"');
  });

  /**
   * A REAL control: it asserts only things that are true on BOTH sides of the
   * fix, so it passes against the parent too. Its job is to catch a change that
   * silences the empty state by breaking the populated one — deliberately no
   * `probKnown` assertion here, because that would make it a second fix-detector
   * dressed as a control and it would fail on the parent for the same reason
   * every real arm does, telling us nothing.
   */
  test("CONTROL: a normal priced pair is untouched on both surfaces", () => {
    const pt = computeLastChartPoint(
      hist({ win_prob_history: { espn: wp(0.62) } }),
      null,
      null,
    )!;

    const card = renderToStaticMarkup(
      <GamePlayCard activePoint={null} homeTeam="Ram/Salisbury" awayTeam="Arribage/Olivetti" lastPoint={pt} />,
    );
    expect(card).toContain("62%");
    expect(card).not.toContain("No price yet");

    const hero = renderToStaticMarkup(
      <EventHeroProbabilityPair homeProb={0.62} awayProb={0.38} homePct={62} awayPct={38} />,
    );
    expect(hero).toContain("62");
    expect(hero).toContain("38");
    expect(hero).not.toContain("No price yet");
  });
});
