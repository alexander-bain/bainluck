// #6563 — A LIVING SOURCE AUTHORISED A WITHDRAWN ONE'S PRICE.
//
// #5890 asks the bag "does ANYBODY still speak". That gate cannot see the case
// where somebody else does: one source is withdrawn, a second is not, the bag is
// therefore non-empty, and the hero's last-resort arm hands back a number that
// belongs to the source that was taken out.
//
// Measured on production 2026-09-16, /events/15307696 (Port FC v Kobe, AFC
// Champions League), 14:23–14:39Z:
//
//   events.win_probability_sources      polymarket only — kalshi WITHDRAWN 14:18:34Z
//   futures_outcomes.current_probability  all 18 kalshi legs NULL, held 5 passes
//   win_prob_snapshots                  kalshi 461 rows, last 0.0100 @ 14:17:57Z
//   GET /api/events/15307696            hero_probability 0.0005, source "blend"
//   the page at 390px                   hero "1 %", source mark "Kalshi"
//
// The payload carried no Kalshi and nothing reading 1%. The page printed both.
//
// WHY THE FIX CANNOT BE "ATTRIBUTE THE CHART POINT AND CHECK ITS SOURCE": with
// two or more rails the backend serves an `aggregate_line` blended from
// `win_prob_history` — withdrawn series included (`routes/events.py`, the
// `agg_sources` block) — and `computeLastChartPoint` reads that edge first. The
// number the hero was printing is a blend of a living source and a dead one, so
// no inspection of it can say whose it is. It has to be replaced, not cleared.
//
// The three fixtures below are that event's numbers.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import EventHeroProbabilityPair from "@/components/EventHeroProbabilityPair";
import {
  livingRailReading,
  railSourceStanding,
  resolveProbability,
} from "@/lib/eventKeyStats";
import type {
  ActiveChartPoint,
  EventDetailResponse,
  EventHistoryResponse,
} from "@/lib/types";

/** 15307696 as served: kalshi gone from the bag, polymarket still in it. */
function portFcEvent(over: Record<string, unknown> = {}): EventDetailResponse {
  return {
    id: 15307696,
    home_team: "Port FC",
    away_team: "Vissel Kobe",
    sport: "soccer_afc_champions_league",
    commence_time: "2026-09-16T15:15:00+00:00",
    status: "scheduled",
    completed_at: null,
    current_odds: null,
    win_probability_sources: {
      polymarket: {
        value: 0.0005,
        display_name: "Polymarket",
        type: "market",
        color: "#3b82f6",
      },
    },
    ...over,
  } as unknown as EventDetailResponse;
}

/**
 * The rail. Kalshi's series is still there — `win_prob_snapshots` is immutable —
 * and `aggregate_line` is still blending it, which is why its edge reads 0.01
 * while the bag's only member says 0.0005.
 */
const PORT_FC_RAIL: EventHistoryResponse = {
  aggregate_line: [{ timestamp: "2026-09-16T14:18:00+00:00", home_probability: 0.01 }],
  win_prob_sources: { kalshi: [], polymarket: [] },
  win_prob_history: {
    kalshi: [
      { timestamp: "2026-09-16T14:16:57+00:00", home_probability: 0.014 },
      { timestamp: "2026-09-16T14:17:57+00:00", home_probability: 0.01 },
    ],
    polymarket: [
      { timestamp: "2026-09-16T14:17:40+00:00", home_probability: 0.0007 },
      { timestamp: "2026-09-16T14:18:40+00:00", home_probability: 0.0005 },
    ],
  },
} as unknown as EventHistoryResponse;

/** What `computeLastChartPoint` returns off that rail: the blend's edge. */
const BLEND_EDGE: ActiveChartPoint = {
  homeProb: 0.01,
  awayProb: 0.99,
} as unknown as ActiveChartPoint;

/** The page's call for this row: not live, not finished, no reported result. */
function heroFor(
  event: EventDetailResponse,
  rail: EventHistoryResponse = PORT_FC_RAIL,
) {
  return resolveProbability(event, rail, BLEND_EDGE, false, false, true, false);
}

describe("🔴 the production specimen", () => {
  test("the hero no longer names the source the bag has withdrawn", () => {
    const resolved = heroFor(portFcEvent());
    expect(resolved.probSourceLabel).toBe("Polymarket");
    expect(resolved.probSourceLabel).not.toContain("Kalshi");
  });

  test("and no longer prints the withdrawn source's price", () => {
    const resolved = heroFor(portFcEvent());
    // Polymarket's own newest reading — which is `hero_probability` in the
    // payload the page was already being served, to the digit.
    expect(resolved.homeProb).toBeCloseTo(0.0005, 6);
    expect(resolved.homeProb).not.toBeCloseTo(0.01, 6);
  });

  test("the rendered hero shows neither the 1% nor the word Kalshi", () => {
    const resolved = heroFor(portFcEvent());
    const html = renderToStaticMarkup(
      <EventHeroProbabilityPair
        homeProb={resolved.homeProb}
        awayProb={resolved.awayProb}
        homePct={resolved.homePct}
        awayPct={resolved.awayPct}
        probSourceLabel={resolved.probSourceLabel}
        started
      />,
    );
    expect(html).not.toContain("Kalshi");
    expect(html).toContain("Polymarket");
  });

  test("the withdrawal is not a licence to invent a final score", () => {
    // The trap Alex named on the issue: the 1% is a real settlement of a contest
    // that really finished, so the repair must take the ATTRIBUTION off the page
    // without the page starting to assert a result. Nothing here reads a winner,
    // and the header's own "No result reported" state is untouched — this arm
    // only ever writes a probability pair and a caption.
    const resolved = heroFor(portFcEvent());
    expect(resolved).not.toHaveProperty("winner");
    expect(resolved.openingHomeProb).toBeNull();
    expect(resolved.openingAwayProb).toBeNull();
  });
});

describe("🟢 the cases this must not touch", () => {
  test("nothing withdrawn: the blend edge and its caption are unchanged", () => {
    // The overwhelming majority. Rail list and bag agree, so the edge is a blend
    // of living sources and #4015's dark-match fallback keeps exactly what it
    // has today — value off `lastChartPoint`, caption off the rail list.
    const resolved = heroFor(
      portFcEvent({
        win_probability_sources: {
          kalshi: { value: 0.01 },
          polymarket: { value: 0.0005 },
        },
      }),
    );
    expect(resolved.homeProb).toBe(0.01);
    expect(resolved.awayProb).toBe(0.99);
    expect(resolved.probSourceLabel).toBe("Kalshi, Polymarket");
  });

  test("#4015 preserved: newer SAME-SOURCE history still beats a stale bag value", () => {
    // Jodar v Bu (15300276): bag `kalshi 0.895` @ 00:00:54Z, rail `kalshi 0.01`
    // @ 21:03Z, 21 hours apart. The bag's number is the stale one and the ruling
    // is that the chart wins. Rail equals bag here, so this does not even reach
    // the new branch — asserted so a later widening of it cannot eat this case.
    const jodarRail = {
      aggregate_line: [],
      win_prob_sources: { kalshi: [] },
      win_prob_history: {
        kalshi: [{ timestamp: "2026-09-02T21:03:00+00:00", home_probability: 0.01 }],
      },
    } as unknown as EventHistoryResponse;
    const resolved = heroFor(
      portFcEvent({ win_probability_sources: { kalshi: { value: 0.895 } } }),
      jodarRail,
    );
    expect(resolved.homeProb).toBe(0.01);
    expect(resolved.probSourceLabel).toBe("Kalshi");
  });

  test("#5890 preserved: an entirely empty bag still says nothing at all", () => {
    const resolved = heroFor(portFcEvent({ win_probability_sources: {} }));
    expect(resolved.homeProb).toBeNull();
    expect(resolved.probSourceLabel ?? null).toBeNull();
  });

  test("every rail withdrawn: no living reading, so no number and no caption", () => {
    // The bag is non-empty — `betting` still speaks — but neither rail does, so
    // there is nothing on the chart anybody stands behind. #5890's answer, one
    // degree further along.
    const resolved = heroFor(
      portFcEvent({ win_probability_sources: { betting: { value: 0.33 } } }),
    );
    expect(resolved.homeProb).toBeNull();
    expect(resolved.probSourceLabel ?? null).toBeNull();
  });

  test("an odds-only event has no rail list, so it is never contaminated", () => {
    // `win_prob_sources` names only `win_prob_snapshots` series. An event drawn
    // from bookmaker history alone has an empty one, and an empty rail list can
    // hold no withdrawal — it must keep its hero rather than lose it to a gate
    // about a store it does not use.
    const oddsOnly = {
      aggregate_line: [{ timestamp: "2026-09-16T14:18:00+00:00", home_probability: 0.42 }],
      win_prob_sources: {},
    } as unknown as EventHistoryResponse;
    const resolved = heroFor(
      portFcEvent({ win_probability_sources: { betting: { value: 0.42 } } }),
      oddsOnly,
    );
    expect(resolved.homeProb).toBe(0.01); // the passed-in chart point, untouched
    expect(resolved.probSourceLabel ?? null).toBeNull();
  });
});

describe("the two helpers answer the question they are named for", () => {
  test("railSourceStanding splits the rail list against the live bag", () => {
    expect(
      railSourceStanding(PORT_FC_RAIL, { polymarket: { value: 0.0005 } }),
    ).toEqual({ living: ["polymarket"], withdrawn: ["kalshi"] });
  });

  test("a non-source rail key is not a withdrawal (#3914's miscount)", () => {
    // `betting_book_count` is served in the same decorated shape with a finite
    // value. If the rail side were unfiltered while the bag side is filtered,
    // any such key would read as permanently withdrawn and contaminate every
    // event carrying one.
    const rail = {
      ...PORT_FC_RAIL,
      win_prob_sources: { kalshi: [], betting_book_count: [] },
    } as unknown as EventHistoryResponse;
    expect(railSourceStanding(rail, { kalshi: { value: 0.01 } })).toEqual({
      living: ["kalshi"],
      withdrawn: [],
    });
  });

  test("livingRailReading takes the newest reading across the living rails", () => {
    expect(livingRailReading(PORT_FC_RAIL, ["kalshi", "polymarket"])).toEqual({
      homeProb: 0.0005,
      source: "polymarket",
      timestamp: "2026-09-16T14:18:40+00:00",
    });
  });

  test("it skips a null tail rather than reading it as a stop", () => {
    // A series can end on a row written before its price arrived. That is an
    // absence in one row, not the end of the series — walking past it is the
    // same judgement `resolveProbability`'s own history scan makes.
    const rail = {
      win_prob_history: {
        kalshi: [
          { timestamp: "2026-09-16T14:16:57+00:00", home_probability: 0.014 },
          { timestamp: "2026-09-16T14:17:57+00:00", home_probability: null },
        ],
      },
    } as unknown as EventHistoryResponse;
    expect(livingRailReading(rail, ["kalshi"])).toEqual({
      homeProb: 0.014,
      source: "kalshi",
      timestamp: "2026-09-16T14:16:57+00:00",
    });
  });

  test("no living rails, or no rail series at all, reads null", () => {
    expect(livingRailReading(PORT_FC_RAIL, [])).toBeNull();
    expect(
      livingRailReading(
        { win_prob_sources: { kalshi: [] } } as unknown as EventHistoryResponse,
        ["kalshi"],
      ),
    ).toBeNull();
  });
});
