/**
 * #6082 — a leg the venue has already settled prints its RESULT, even while the
 * market around it is legitimately still open.
 *
 * ## The defect, as a reader met it
 *
 * `/futures/261` ("Boston pro baseball wins this season?"), production
 * 2026-09-14 06:00Z at 390px. Kalshi had settled two rungs YES
 * (`is_winner true`, `resolution_source 'api_settlement'`) while the market
 * itself was correctly `status='open'` — the parent question runs to Nov 8 and
 * `90+ wins` genuinely traded at 19%. The `All Outcomes` table printed:
 *
 *     1  80+ wins   OPEN 72%   LATEST 99%
 *     2  75+ wins   OPEN 83%   LATEST 98%
 *
 * Both numbers are pre-settlement relics rather than live prices, so they are
 * also mutually impossible: P(≥75) cannot sit below P(≥80). A reader does not
 * need to know what a threshold ladder is to see that one.
 *
 * Cause: `outcomeRowVerdict` gated a LEG-level question on a MARKET-level flag
 * (`market.status === "resolved"`). `can_write_winner` (#845) — the rule the
 * backend's `_outcome_is_settled` already renders on — says a winner stands on a
 * settled market OR on any market when an AUTHORITATIVE (tier-3) venue
 * settlement says so.
 *
 * Population measured on production the same day: **2,428 legs on 797 markets
 * still `open`** carry `is_winner IS TRUE` + `api_settlement`; **1,738** of them
 * store a probability under 99.5% and so rendered as a live-looking percentage.
 *
 * ## What is under guard here, in both directions (gotcha #43)
 *
 * The widening is one arm on one branch, and every refusal around it is
 * load-bearing. Each of these is a real row on the specimen market:
 *
 *   - `80+ wins` / `75+ wins` — tier-3 settled YES on an OPEN market ⇒ `Won`
 *   - `85+ wins` — `ungradeable_result` (a RETRACTION) ⇒ keeps its 96%
 *   - `90+ wins` — ungraded, still trading ⇒ keeps its 19%
 *   - a tier-3 `is_winner false` on an OPEN market ⇒ keeps its price, because
 *     that is #4597's arm and it waits on the CAL-P1004 drain
 *
 * The last one is the test that stops this ship from quietly becoming a
 * different, unlicensed one.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import OutcomeRow, {
  outcomeRowPrintsMove,
  outcomeRowVerdict,
  RETRACTED_RESOLUTION_SOURCE,
} from "@/components/futures/OutcomeRow";
import { AUTHORITATIVE_RESOLUTION_SOURCES } from "@/lib/resolutionAuthority";
import type { FuturesOutcome } from "@/lib/types";

/**
 * The seven rungs of `/futures/261` exactly as `/api/futures/261` served them at
 * 06:50Z on 2026-09-14. Named and complete, so nobody can "fix" a failure by
 * trimming the fixture down to the two rows that move.
 */
const RUNGS: FuturesOutcome[] = [
  { id: 2193, name: "80+ wins", probability: 0.99, opening_probability: 0.72, is_winner: true, resolution_source: "api_settlement" },
  { id: 2194, name: "75+ wins", probability: 0.98, opening_probability: 0.83, is_winner: true, resolution_source: "api_settlement" },
  { id: 2192, name: "85+ wins", probability: 0.955, opening_probability: 0.58, is_winner: false, resolution_source: RETRACTED_RESOLUTION_SOURCE },
  { id: 2191, name: "90+ wins", probability: 0.185, opening_probability: 0.46, is_winner: null, resolution_source: null },
  { id: 2190, name: "95+ wins", probability: 0.01, opening_probability: 0.27, is_winner: null, resolution_source: null },
  { id: 2196, name: "100+ wins", probability: 0.0, opening_probability: 0.15, is_winner: false, resolution_source: "api_settlement" },
  { id: 2195, name: "105+ wins", probability: 0.0, opening_probability: 0.07, is_winner: false, resolution_source: "api_settlement" },
].map((o) => ({
  probability_change_24h: null,
  rank_change_24h: 0,
  last_updated: "2026-09-11T20:50:52.804630+00:00",
  ...o,
})) as FuturesOutcome[];

const byName = (name: string): FuturesOutcome => {
  const found = RUNGS.find((o) => o.name === name);
  if (!found) throw new Error(`no such rung in the specimen: ${name}`);
  return found;
};

/** The market is OPEN — that is the whole point of the specimen. */
const OPEN = false;
const RESOLVED = true;

function render(o: FuturesOutcome, isResolved: boolean): string {
  return renderToStaticMarkup(
    <OutcomeRow
      outcome={o}
      rank={1}
      isLeader={false}
      isSelected={false}
      onToggleSelect={() => {}}
      hasHistory={false}
      marketCategory="baseball"
      marketName="Boston pro baseball wins this season?"
      isResolved={isResolved}
      rendered={null}
      renderedOpening={null}
      showLastMove
      showEntityImage={false}
    />,
  );
}

describe("#6082 outcomeRowVerdict — a tier-3 settlement stands on an OPEN market", () => {
  it("THE DEFECT: the two rungs Kalshi settled YES now read `won`, not a price", () => {
    expect(outcomeRowVerdict(byName("80+ wins"), OPEN)).toBe("won");
    expect(outcomeRowVerdict(byName("75+ wins"), OPEN)).toBe("won");
  });

  it("every tier-3 source carries a winner across the status line, not just Kalshi's", () => {
    for (const source of AUTHORITATIVE_RESOLUTION_SOURCES) {
      expect(
        outcomeRowVerdict(
          { ...byName("80+ wins"), resolution_source: source },
          OPEN,
        ),
      ).toBe("won");
    }
  });

  it("a settled market is untouched — both arms answer exactly as before", () => {
    expect(outcomeRowVerdict(byName("80+ wins"), RESOLVED)).toBe("won");
    expect(
      outcomeRowVerdict(
        { ...byName("80+ wins"), is_winner: false },
        RESOLVED,
      ),
    ).toBe("lost");
  });
});

describe("#6082 the refusals that must survive the widening", () => {
  it("THE RETRACTION IS STILL FIRST: `85+ wins` states no verdict and keeps its price", () => {
    expect(outcomeRowVerdict(byName("85+ wins"), OPEN)).toBeNull();
    // …and it is refused on a resolved market too, unconditionally as before.
    expect(outcomeRowVerdict(byName("85+ wins"), RESOLVED)).toBeNull();
    // Even when something crowns it — a row both retracted and crowned is a
    // contradiction, and the honest render for a contradiction is the live one.
    expect(
      outcomeRowVerdict(
        { ...byName("85+ wins"), is_winner: true },
        OPEN,
      ),
    ).toBeNull();
  });

  it("#4597's ARM IS NOT SHIPPED: a tier-3 `is_winner false` on an OPEN market keeps its price", () => {
    // `is_winner` is `boolean NULL DEFAULT false`, so on a market nobody has
    // finished grading a defaulted FALSE cannot be told from a called loss. This
    // waits on the CAL-P1004 drain (#4597); widening it here would be #4788's lie
    // on a market that is still trading.
    expect(outcomeRowVerdict(byName("100+ wins"), OPEN)).toBeNull();
    expect(outcomeRowVerdict(byName("105+ wins"), OPEN)).toBeNull();
  });

  it("an ungraded, still-trading rung is untouched", () => {
    expect(outcomeRowVerdict(byName("90+ wins"), OPEN)).toBeNull();
    expect(outcomeRowVerdict(byName("95+ wins"), OPEN)).toBeNull();
  });

  it("a NON-authoritative source may not crown a leg on an open market", () => {
    // Tier 0 (the guess family, #754) and tier 2 are exactly what the backend
    // CLEARS off open markets — `_clear_premature_open_winners`.
    for (const source of ["pass2_guess", "multi_max_prob", "box_score", "clean_resolution"]) {
      expect(
        outcomeRowVerdict(
          { ...byName("80+ wins"), resolution_source: source },
          OPEN,
        ),
      ).toBeNull();
    }
    // …and an unknown source is refused rather than trusted (fail-safe).
    expect(
      outcomeRowVerdict(
        { ...byName("80+ wins"), resolution_source: "some_future_grader" },
        OPEN,
      ),
    ).toBeNull();
  });

  it("a SERVED null still says nothing, and an ABSENT field still falls open", () => {
    expect(
      outcomeRowVerdict(
        { ...byName("80+ wins"), resolution_source: null },
        OPEN,
      ),
    ).toBeNull();
    // Vercel deploys ahead of Heroku: for the length of every deploy this
    // component runs against a payload with no `resolution_source` key at all.
    // Absent means "this payload cannot say" ⇒ today's behaviour on an open
    // market, which is silence, and the unchanged answer on a resolved one.
    const absent = { ...byName("80+ wins") } as Partial<FuturesOutcome>;
    delete absent.resolution_source;
    expect(outcomeRowVerdict(absent as FuturesOutcome, OPEN)).toBeNull();
    expect(outcomeRowVerdict(absent as FuturesOutcome, RESOLVED)).toBe("won");
  });

  it("`is_winner` null states nothing whatever the source says", () => {
    expect(
      outcomeRowVerdict(
        { ...byName("80+ wins"), is_winner: null },
        OPEN,
      ),
    ).toBeNull();
  });
});

describe("#6082 what the reader actually sees on /futures/261", () => {
  it("the settled rung prints `Won` and `Settled`, not `LATEST 99%`", () => {
    const html = render(byName("80+ wins"), OPEN);
    expect(html).toContain(">Won<");
    expect(html).toContain(">Settled<");
    // The price that made the pair impossible is gone from the row.
    expect(html).not.toContain("99%");
    // And the price column's own header goes with it — "Latest" above a
    // `100% / Settled` cell would be a fresh contradiction.
    expect(html).not.toContain(">Latest<");
  });

  it("THE IMPOSSIBLE PAIR IS GONE: neither settled rung prints a percentage below the other", () => {
    const eighty = render(byName("80+ wins"), OPEN);
    const seventyFive = render(byName("75+ wins"), OPEN);
    for (const html of [eighty, seventyFive]) {
      expect(html).toContain(">Won<");
    }
    expect(eighty).not.toContain("99%");
    expect(seventyFive).not.toContain("98%");
  });

  it("the retracted rung on that same market still shows its 96% and no verdict", () => {
    const html = render(byName("85+ wins"), OPEN);
    expect(html).toContain("96%");
    expect(html).not.toContain(">Won<");
    expect(html).not.toContain(">Lost<");
    expect(html).toContain(">Latest<");
  });

  it("the still-trading rung on that same market still shows its 19%", () => {
    const html = render(byName("90+ wins"), OPEN);
    expect(html).toContain("19%");
    expect(html).not.toContain(">Won<");
    expect(html).not.toContain(">Lost<");
  });

  it("a settled rung trades its movement cell for its result", () => {
    // `outcomeRowPrintsMove` keys off the verdict, so this follows the widening
    // rather than restating it — the defect that extraction exists to end.
    expect(
      outcomeRowPrintsMove(
        { ...byName("80+ wins"), probability_change_24h: 0.05 },
        OPEN,
      ),
    ).toBe(false);
    expect(
      outcomeRowPrintsMove(
        { ...byName("90+ wins"), probability_change_24h: 0.05 },
        OPEN,
      ),
    ).toBe(true);
  });
});
