// #8906: a search answer row about a game is dated by the game, not by when the
// venue settles it. Production 2026-09-26, `/search?q=chiefs` at 390px: the
// ANSWERS card printed `KC Chiefs vs MIA Dolphins: Spread … 71% · Sep 29` two
// cards below the GAMES row for the same game reading `Tomorrow 10:00 AM`
// (Sep 27). Specimen 61806201 is linked to event 14781701: commence
// 2026-09-27T17:00Z, resolution_date 2026-09-29T17:00Z (Kalshi settlement).

import * as fs from "fs";
import * as path from "path";
import { answerDateLabel, resolutionLabel } from "../../components/searchFamilyDisplay";

const DAY = 86_400_000;
// Offsets from now, never fixed dates, so the 30-day window never branches on
// the clock (gotcha #44). One day vs three days always lands on different dates.
const at = (days: number) => new Date(Date.now() + days * DAY).toISOString();

describe("#8906 answerDateLabel", () => {
  test("a linked game prop prints its kickoff, not its settlement date", () => {
    const kickoff = at(1);
    const settles = at(3);
    const label = answerDateLabel({ event_commence_time: kickoff, resolution_date: settles });
    expect(label).toBe(resolutionLabel(kickoff));
    // Strawman: the pre-fix row printed the settlement label, which differs.
    expect(label).not.toBe(resolutionLabel(settles));
    expect(label).not.toBeNull();
  });

  test("an unlinked market (key absent) keeps its settlement label", () => {
    const settles = at(10);
    expect(answerDateLabel({ resolution_date: settles })).toBe(resolutionLabel(settles));
    expect(answerDateLabel({ resolution_date: settles, event_commence_time: null })).toBe(
      resolutionLabel(settles),
    );
    expect(answerDateLabel({ resolution_date: null })).toBeNull();
  });

  test("a game already under way prints no date, never the settlement one", () => {
    const label = answerDateLabel({ event_commence_time: at(-0.1), resolution_date: at(2) });
    expect(label).toBeNull();
  });

  test("the answer row reads its date through answerDateLabel", () => {
    const src = fs.readFileSync(
      path.join(__dirname, "../../components/SearchFamilyCard.tsx"),
      "utf8",
    );
    expect(src).toMatch(/answerDateLabel\(market\)/);
    expect(src).not.toMatch(/resolutionLabel\(/);
  });
});
