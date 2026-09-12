/**
 * #5540 — a live tennis page serves four priced markets and renders no
 * Additional Markets section at all.
 *
 * THE DEFECT WAS ONE NUMBER COUNTING TWO DIFFERENT POPULATIONS. The event page
 * mounts this section on `(gameMarkets.other?.length ?? 0) >= 3` — the WIRE —
 * and `buildMarketSection` then returned nothing on `kept.length < 3` — the
 * SURVIVORS of `findWinProbMarkets` + `isRedundantWithMarketMaps`. Four wire
 * rows, two survivors, section mounted, null rendered, reader told nothing.
 *
 * MEASURED REACH (this module replayed over the real `other[]` wire of 22
 * events, production, 2026-09-12 07:5x–08:0xZ): of the SEVEN live events whose
 * payload passes the page's `>= 3` gate, SIX rendered nothing. Five were this
 * floor. All ten completed events in the same sample keep 3+ rows, so no
 * finished page changes.
 *
 * WHY A BINARY MARKET IS THE WHOLE PROBLEM: it is two rows on the wire and one
 * row on the page, because `scopedWinnerLabel` drops the `No` complement — one
 * question, one number. Any floor above zero is therefore counting wire rows to
 * decide whether the reader has enough to look at, and those are not the same
 * quantity.
 *
 * Fixtures are VERBATIM production wire, not invented shapes. The tennis rows
 * are `GET /api/events/15310723/game-markets` as quoted in #5540 (07:08Z); the
 * same event re-read at 07:15:08Z carried 0.50/0.50 on the Set 1 pair, and the
 * 51/49 read is used here precisely because an even pair could not tell a
 * rendered `Yes` from a rendered `No`.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import SpecialEventMarkets from "../../components/SpecialEventMarkets";
import { buildMarketSection } from "../../lib/otherMarketGroups";
import type { OtherMarketRow } from "../../lib/otherMarketGroups";
import type { GameMarketsResponse } from "../../lib/api";

const PM = "polymarket";
const KALSHI = "kalshi";
const AT = "2026-09-12T07:08:00.000000+00:00";

/** `/api/events/15310723/game-markets`, live, Claire Liu v Anna Blinkova. */
const TENNIS_WIRE: OtherMarketRow[] = [
  { market_name: "Barranquilla: Claire Liu vs Anna Blinkova", outcome_name: "Yes", probability: 0.52, source: PM, observed_at: AT },
  { market_name: "Barranquilla: Claire Liu vs Anna Blinkova", outcome_name: "No", probability: 0.48, source: PM, observed_at: AT },
  { market_name: "Set 1 Winner: Liu vs Blinkova", outcome_name: "Yes", probability: 0.51, source: PM, observed_at: AT },
  { market_name: "Set 1 Winner: Liu vs Blinkova", outcome_name: "No", probability: 0.49, source: PM, observed_at: AT },
];

/** `/api/events/15310234/game-markets`, live NPB — ONE survivor, not two. */
const NPB_WIRE: OtherMarketRow[] = [
  { market_name: "Hanshin Tigers vs Yomiuri Giants: First Inning Run", outcome_name: "Yes", probability: 0.01, source: KALSHI, observed_at: AT },
  { market_name: "Hanshin Tigers vs Yomiuri Giants", outcome_name: "Yomiuri Giants", probability: 0.82, source: KALSHI, observed_at: AT },
  { market_name: "Hanshin Tigers vs Yomiuri Giants", outcome_name: "Hanshin Tigers", probability: 0.16, source: KALSHI, observed_at: AT },
];

/**
 * `/api/events/15310602/game-markets`, live esports — SIX wire rows and ZERO
 * survivors, because `Liquid vs. NRG: Map 1` is a two-sided pair summing to 1.0
 * that `periodWinnerParts` does not recognise as period-scoped, so the map
 * winners are eaten as the hero's own question. That is a DIFFERENT defect and
 * is filed separately; it is here as the both-direction guard, because no floor
 * can rescue an empty kept set and this ship must not pretend to.
 */
const ESPORTS_WIRE: OtherMarketRow[] = [
  { market_name: "Liquid vs. NRG", outcome_name: "NRG", probability: 0.99, source: KALSHI, observed_at: AT },
  { market_name: "Liquid vs. NRG", outcome_name: "Liquid", probability: 0.01, source: KALSHI, observed_at: AT },
  { market_name: "Liquid vs. NRG: Map 1", outcome_name: "NRG", probability: 0.99, source: KALSHI, observed_at: AT },
  { market_name: "Liquid vs. NRG: Map 1", outcome_name: "Liquid", probability: 0.01, source: KALSHI, observed_at: AT },
  { market_name: "Liquid vs. NRG: Map 2", outcome_name: "NRG", probability: 0.99, source: KALSHI, observed_at: AT },
  { market_name: "Liquid vs. NRG: Map 2", outcome_name: "Liquid", probability: 0.01, source: KALSHI, observed_at: AT },
];

function labelsOf(rows: OtherMarketRow[], opts = {}) {
  return buildMarketSection(rows, opts).categories.flatMap((c) =>
    c.cards.flatMap((k) => k.outcomes.map((o) => o.label)),
  );
}

describe("#5540 — the survivors decide, not the wire count", () => {
  test("the live Set 1 Winner market reaches the page", () => {
    const section = buildMarketSection(TENNIS_WIRE, { completedSets: 0 });
    expect(section.categories).not.toHaveLength(0);
    expect(labelsOf(TENNIS_WIRE, { completedSets: 0 })).toEqual(["Liu wins Set 1"]);
  });

  test("and it carries the YES side's number, not the complement's", () => {
    // The assertion the 50/50 re-read could not make. 0.51 is `Yes`; a render
    // that picked `No` would read 0.49 and this passes only on the former.
    const probs = buildMarketSection(TENNIS_WIRE, { completedSets: 0 }).categories
      .flatMap((c) => c.cards.flatMap((k) => k.outcomes.map((o) => o.prob)));
    expect(probs).toEqual([0.51]);
  });

  test("the hero's own question is still filtered out", () => {
    // The cheap wrong fix is to stop filtering `findWinProbMarkets`, which would
    // also clear the floor — and reprint the hero's 52% in the rail (#3575).
    const labels = labelsOf(TENNIS_WIRE, { completedSets: 0 });
    expect(labels).not.toContain("Yes");
    expect(labels).not.toContain("No");
    expect(labels.join(" ")).not.toContain("Barranquilla");
  });

  test("ONE survivor is enough — the mutation guard for a floor of 2", () => {
    // TENNIS_WIRE keeps two rows, so a floor of `< 2` would still pass every
    // assertion above. This payload keeps exactly one.
    const section = buildMarketSection(NPB_WIRE);
    expect(section.categories).not.toHaveLength(0);
    expect(section.renderedOutcomes).toBe(1);
    expect(labelsOf(NPB_WIRE).join(" ")).toContain("Yes");
  });

  test("BOTH DIRECTIONS: no survivors still renders nothing", () => {
    expect(buildMarketSection(ESPORTS_WIRE).categories).toEqual([]);
    expect(buildMarketSection(ESPORTS_WIRE).renderedOutcomes).toBe(0);
  });
});

describe("#5540 — through the component the reader actually gets", () => {
  const payload = (other: OtherMarketRow[], extra: Record<string, unknown> = {}) =>
    ({
      other,
      player_props: [],
      matchups: [],
      home_team: "Claire Liu",
      away_team: "Anna Blinkova",
      ...extra,
    }) as unknown as GameMarketsResponse;

  test("the section renders, headed and named, on the live tennis wire", () => {
    const html = renderToStaticMarkup(
      <SpecialEventMarkets data={payload(TENNIS_WIRE)} eventStatus="live" completedSets={0} />,
    );
    // SURVIVAL FIRST (#4286's lesson): an empty render passes every `not`
    // assertion below for the wrong reason.
    expect(html).toContain("Additional Markets");
    expect(html).toContain("Liu wins Set 1");
    expect(html).toContain("51");
  });

  test("and renders nothing at all when nothing survives", () => {
    const html = renderToStaticMarkup(
      <SpecialEventMarkets data={payload(ESPORTS_WIRE)} eventStatus="live" completedSets={0} />,
    );
    expect(html).toBe("");
  });
});
