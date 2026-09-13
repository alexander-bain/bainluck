// #5890 — A WITHDRAWN PRICE CAME STRAIGHT BACK OUT OF THE SNAPSHOT RAIL.
//
// `win_probability_sources` is the live claim; `win_prob_snapshots` (behind the
// chart) is immutable history. Every backend withdrawal works by emptying the
// bag — #5820 pulls a speaker whose market we have already settled,
// `_retire_unpriced_legs` pulls a leg that stopped trading — and the API then
// serves the event with no `hero_probability` at all. The hero's last-resort arm
// read the rail, found the withdrawn number still sitting on it, and printed it.
//
// Measured on production 2026-09-13 10:1x–14:0xZ, /events/15310861 (Liu v
// Blinkova, `suspended`, no result):
//
//   events.win_probability_sources      {}            (the withdrawal worked)
//   GET /api/events/15310861            no `hero_probability` key, no bag key
//   GET .../history?hours=48            aggregate_line last = 0.9945
//   the page at 390px                   99% – 1%, captioned "Kalshi, Polymarket"
//
// 0.99 was a SETTLED Kalshi market's price. The caption is the tell: a row
// carrying no sources cannot name two of them — it was labelling from
// `historyData.win_prob_sources`, which is the rail's own list.
//
// The fixtures below are the shapes of those two payloads, and the numbers are
// that event's numbers. Driving the real `resolveProbability` over a 40-event
// production sample the same morning: 20 events reached this arm, all 20 with an
// empty bag; the 20 with a live source were untouched. The before/after run and
// its banked payloads are quoted in the PR (ux/1237).

import React from "react";
import fs from "fs";
import path from "path";
import { renderToStaticMarkup } from "react-dom/server";

import EventHeroProbabilityPair from "@/components/EventHeroProbabilityPair";
import { resolveProbability } from "@/lib/eventKeyStats";
import { hasProbabilitySourceReading } from "@/lib/probabilityEvidence";
import type {
  ActiveChartPoint,
  EventDetailResponse,
  EventHistoryResponse,
} from "@/lib/types";

/** The withdrawn event: suspended, no result, no current odds, empty bag. */
function withdrawnEvent(over: Record<string, unknown> = {}): EventDetailResponse {
  return {
    id: 15310861,
    home_team: "Liu",
    away_team: "Blinkova",
    sport: "tennis_wta",
    commence_time: "2026-09-13T00:30:00+00:00",
    status: "suspended",
    completed_at: null,
    // Both keys are ABSENT on the wire when the bag empties — the serializer
    // drops them — so the fixture omits them rather than sending null.
    current_odds: null,
    ...over,
  } as unknown as EventDetailResponse;
}

/** The rail: the withdrawn price is still the last point, and still labelled. */
const RAIL: EventHistoryResponse = {
  aggregate_line: [{ timestamp: "2026-09-13T03:55:00+00:00", home_probability: 0.9945 }],
  win_prob_sources: { kalshi: [], polymarket: [] },
} as unknown as EventHistoryResponse;

const RAIL_TAIL: ActiveChartPoint = {
  homeProb: 0.9945,
  awayProb: 0.0055,
} as unknown as ActiveChartPoint;

/** The page's call, for a dark match: not live, not finished, no reported result. */
function heroFor(event: EventDetailResponse) {
  return resolveProbability(event, RAIL, RAIL_TAIL, false, false, true, false);
}

/** A decorated bag entry, the shape `/api/events/*` serves. */
function decorated(value: number) {
  return { value, display_name: "Kalshi", type: "prediction_market", color: "#000" };
}

describe("🔴 an emptied bag is a WITHDRAWAL, and the hero may not undo it", () => {
  test("the production specimen prints no number and names no source", () => {
    const resolved = heroFor(withdrawnEvent());

    expect(resolved.homeProb).toBeNull();
    expect(resolved.awayProb).toBeNull();
    expect(resolved.homePct).toBeNull();
    expect(resolved.awayPct).toBeNull();
    // The caption is half the defect: it named two sources the row did not have.
    expect(resolved.probSourceLabel ?? null).toBeNull();
  });

  test("the rendered hero says so in words rather than printing 99", () => {
    const resolved = heroFor(withdrawnEvent());
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
    expect(html).not.toContain("99");
    expect(html).not.toContain("Kalshi");
    expect(html).toContain("No price");
  });

  test("a live match is no more allowed to say it than a dark one", () => {
    // 15311329 (Brady v Sahtali, `live`, tennis, kicked off 12:10Z) printed
    // "Live · Kalshi 99%" off the same rail with an empty bag — same withdrawal,
    // louder caption.
    //
    // Its `aggregate_line` is EMPTY, and the fixture copies that rather than
    // reusing `RAIL`: with a blend line present the live branch returns
    // `latestBlendPoint` and never reaches this arm at all, so a test written
    // the lazy way would assert the wrong path and pass for the wrong reason.
    // Both live bag-empty events in the 48-hour window measured empty here
    // (14:0xZ), so the blend arm's version of this defect has no specimen today;
    // it is named in the PR as a residual rather than fixed blind.
    const liveRail = { ...RAIL, aggregate_line: [] } as unknown as EventHistoryResponse;
    const resolved = resolveProbability(
      withdrawnEvent({ status: "live" }),
      liveRail,
      RAIL_TAIL,
      true,
      false,
      false,
      false,
    );
    expect(resolved.homePct).toBeNull();
    expect(resolved.probSourceLabel ?? null).toBeNull();
  });
});

describe("🟢 an event that still HAS a source keeps the fallback (#4015)", () => {
  test("a stale bag entry still hands the hero to the chart's last point", () => {
    // The #4015 ruling: a dark match whose `current_odds` stopped being written
    // reads the chart rather than contradicting it. That population has a source
    // — Jodar v Bu carried `kalshi 0.895` — so this fix must not touch it.
    const resolved = heroFor(
      withdrawnEvent({ win_probability_sources: { kalshi: decorated(0.895) } }),
    );
    expect(resolved.homePct).toBe(99);
    expect(resolved.probSourceLabel).toBe("Kalshi, Polymarket");
  });

  test("the bare-number wire shape counts as a source too", () => {
    // `/api/feed` serves `{"kalshi": 0.9}` while `/api/events/*` serves the
    // decorated shape. A gate that read only the decorated one would blank every
    // hero on the other surface — the both-shapes failure `readSourceValue`
    // exists for.
    const resolved = heroFor(
      withdrawnEvent({ win_probability_sources: { kalshi: 0.9 } }),
    );
    expect(resolved.homePct).toBe(99);
  });

  test("a bag entry with no value yet is not a source", () => {
    const resolved = heroFor(
      withdrawnEvent({ win_probability_sources: { kalshi: { value: null } } }),
    );
    expect(resolved.homePct).toBeNull();
  });

  test("`betting_book_count` alone is not an opinion (#3914's miscount)", () => {
    // It is served in the same decorated shape and its value is a finite number,
    // so a bare value read counts it as a source and the withdrawn price comes
    // back. 15298125's bag is exactly this: `{betting_book_count: 2}` and nothing
    // else.
    const bag = { betting_book_count: { value: 2 } };
    expect(hasProbabilitySourceReading(bag)).toBe(false);
    expect(heroFor(withdrawnEvent({ win_probability_sources: bag })).homePct).toBeNull();
  });
});

describe("the no-reading copy is in the right tense", () => {
  const noReading = (started: boolean) =>
    renderToStaticMarkup(
      <EventHeroProbabilityPair
        homeProb={null}
        awayProb={null}
        homePct={null}
        awayPct={null}
        started={started}
      />,
    );

  test("a match that has kicked off is not waiting for a price", () => {
    expect(noReading(true)).toContain("No price");
    expect(noReading(true)).not.toContain("No price yet");
  });

  test("a pre-game event keeps the string it has always had", () => {
    expect(noReading(false)).toContain("No price yet");
  });
});

describe("the page hands the hero its state", () => {
  // No render harness exists for `app/events/[id]/page.tsx` (client page behind
  // SWR and an SSE stream), so this is a source scan — comments stripped first,
  // because this file and the page both name `started` in prose.
  const PAGE = path.resolve(__dirname, "../../app/events/[id]/page.tsx");
  const executable = () =>
    fs
      .readFileSync(PAGE, "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, " ")
      .split("\n")
      .map((line) => line.replace(/(^|\s)\/\/.*$/, "$1"))
      .join("\n");

  test("`started` is wired from the page's own three answers", () => {
    expect(executable()).toMatch(
      /started=\{isLive \|\| isFinished \|\| isSuspended\}/,
    );
  });
});
