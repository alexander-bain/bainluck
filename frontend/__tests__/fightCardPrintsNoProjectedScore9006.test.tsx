/**
 * #9006 — a UFC fight card stops printing "Proj 6--2".
 *
 * WHAT A READER SAW. `https://bainluck.com/search?q=ufc`, 390px, 2026-09-27
 * 01:42Z: the Raul Rosas Jr v Raoni Barcelos card (event 15314292) printed
 * `Proj 6--2` under the fighters. A projected score means nothing for a fight,
 * and this one is negative.
 *
 * THE MECHANISM. `current_odds.projected_*_score` is solved from a sportsbook's
 * spread point and total. On a fight the total is a ROUNDS line and the spread
 * is no margin of anything, so the served pair was 5.8 / −1.8 and the card
 * rounded it verbatim. The card now asks `sportsbookProjectionDrawable` — the
 * question the Sportsbooks table and the Score Differential gate already ask
 * (#8617) — and `mma` / `boxing` declare the answer no. Separately, a negative
 * half is withheld in every sport.
 *
 * Fixture: `GET /api/events/search?q=ufc` row 15314292 and
 * `GET /api/events/search?q=chiefs` row 14781701 (Chiefs @ Dolphins, the
 * control: a football spread IS a margin), production 2026-09-27 02:07Z,
 * verbatim. ⚠️ Both rows' `commence_time` is moved into the future here: the
 * footer is hidden for a `scheduled` row past its own start
 * (`hasNoReportedResult`), and the fight started at 02:15Z — a clock-bound
 * fixture would make every "no Proj" arm pass for the wrong reason.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});
jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));
jest.mock("@/hooks", () => ({
  useAnalytics: () => ({ trackEventCardClick: () => {}, track: () => {} }),
}));

import EventCard from "@/components/EventCard";
import type { Event } from "@/lib/types";
import { sportVocab, UNSCORED_IN_POINTS } from "@/lib/marketMapUtils";
import FIXTURE from "./fixtures/fightCardPrintsNoProjectedScore9006.json";

const rows = FIXTURE as unknown as Record<string, Event>;
const IN_THE_FUTURE = new Date(Date.now() + 26 * 3600_000).toISOString();

function row(id: string, patch: Partial<Event> = {}, odds: Record<string, unknown> = {}): Event {
  const base = rows[id];
  return {
    ...base,
    commence_time: IN_THE_FUTURE,
    ...patch,
    current_odds: { ...base.current_odds, ...odds } as Event["current_odds"],
  };
}

function card(event: Event): string {
  return renderToStaticMarkup(<EventCard event={event} />);
}

const PROJ = /Proj <span/;

describe("#9006 — the specimen is what the issue says it is", () => {
  it("the fight serves a projected pair with a negative half", () => {
    const fight = rows["15314292"];
    expect(fight.sport).toBe("mma_mixed_martial_arts");
    expect(fight.status).toBe("scheduled");
    expect(fight.current_odds?.projected_home_score).toBe(5.8);
    expect(fight.current_odds?.projected_away_score).toBe(-1.8);
  });

  it("strawman: the same row with no sport and a non-negative pair prints Proj", () => {
    expect(card(row("15314292", { sport: null }, { projected_away_score: 1.8 }))).toMatch(PROJ);
  });
});

describe("#9006 — a fight card prints no projected score", () => {
  it("the served fight prints no Proj", () => {
    expect(card(row("15314292"))).not.toMatch(PROJ);
    expect(card(row("15314292"))).not.toContain("6--2");
  });

  it("the sport gate bites on its own: a non-negative pair on a fight still prints none", () => {
    expect(card(row("15314292", {}, { projected_away_score: 1.8 }))).not.toMatch(PROJ);
  });

  it("boxing answers the same way", () => {
    expect(card(row("15314292", { sport: "boxing_boxing" }, { projected_away_score: 1.8 }))).not.toMatch(PROJ);
  });
});

describe("#9006 — a negative projected half is withheld in every sport", () => {
  it("a football row with a negative away half prints no Proj", () => {
    expect(card(row("14781701", {}, { projected_away_score: -1.8 }))).not.toMatch(PROJ);
  });

  it("control: the served football row keeps its projection", () => {
    const html = card(row("14781701"));
    expect(html).toMatch(PROJ);
    expect(html).toContain("18-29");
  });
});

describe("#9006 — the combat row changes one fact and no other", () => {
  it.each(["mma_mixed_martial_arts", "mma_ufc", "mma_other", "boxing_boxing"])(
    "%s: the sportsbooks' spread is not a margin; every other field is the undeclared default",
    (key) => {
      const vocab = sportVocab(key);
      expect(vocab.sportsbookSpreadIsAMargin).toBe(false);
      expect({ ...vocab, sportsbookSpreadIsAMargin: true }).toEqual(UNSCORED_IN_POINTS);
    }
  );
});
