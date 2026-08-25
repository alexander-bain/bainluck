/**
 * The bracket, built against the SYNTHETIC 128-slot draw (UX-P131).
 *
 * Charter amendment 2026-08-25: the bracket does not wait for Thursday's draw
 * ceremony. This suite is what makes that real — the component and its fold
 * logic are gated now, against a fixture, so 08-28 swaps the data source and
 * nothing else.
 *
 * The assertion that matters most is the one about projection: an unplayed
 * match must render two names and no winner. A bracket that greys in a
 * projected winner looks identical to one showing a result, and the charter's
 * reliability doctrine is that every element does what it looks like it does.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentBracket from "@/components/tournament/TournamentBracket";
import { bracketProgress, buildBracket, ROUND_NAMES } from "@/lib/bracket";
import {
  SYNTHETIC_MENS_DRAW,
  SYNTHETIC_WOMENS_DRAW,
  syntheticFirstRoundResults,
} from "../fixtures/syntheticDraw";

describe("the synthetic fixture is a usable stand-in for a real draw", () => {
  it("carries a full 128-slot draw for both sides", () => {
    expect(SYNTHETIC_MENS_DRAW).toHaveLength(128);
    expect(SYNTHETIC_WOMENS_DRAW).toHaveLength(128);
  });

  it("has unique entity keys — a duplicate would fake a bracket collision", () => {
    const keys = new Set(SYNTHETIC_MENS_DRAW.map((s) => s.entity_key));
    expect(keys.size).toBe(128);
  });

  it("is deterministic across builds", () => {
    expect(SYNTHETIC_MENS_DRAW[0].entity_key).toBe("syn-m-1");
    expect(SYNTHETIC_MENS_DRAW[127].entity_key).toBe("syn-m-128");
    expect(SYNTHETIC_MENS_DRAW[0].display_name).toBe(SYNTHETIC_MENS_DRAW[0].display_name);
  });

  it("leaves most of the field without a title probability, as a real draw does", () => {
    const priced = SYNTHETIC_MENS_DRAW.filter((s) => s.probability !== null);
    expect(priced).toHaveLength(16);
    expect(SYNTHETIC_MENS_DRAW[100].probability).toBeNull();
  });

  it("mixes seeded and unseeded entrants", () => {
    const seeded = SYNTHETIC_MENS_DRAW.filter((s) => s.seed !== null);
    expect(seeded.length).toBeGreaterThan(0);
    expect(seeded.length).toBeLessThan(128);
  });
});

describe("buildBracket folds a draw into rounds", () => {
  const rounds = buildBracket(SYNTHETIC_MENS_DRAW);

  it("produces seven rounds from a 128 draw, ending at the final", () => {
    expect(rounds.map((r) => r.round)).toEqual([...ROUND_NAMES]);
    expect(rounds[rounds.length - 1].round).toBe("F");
  });

  it("halves the match count each round", () => {
    expect(rounds.map((r) => r.matches.length)).toEqual([64, 32, 16, 8, 4, 2, 1]);
  });

  it("pairs adjacent slots in the first round", () => {
    const first = rounds[0].matches[0];
    expect(first.top?.entity_key).toBe("syn-m-1");
    expect(first.bottom?.entity_key).toBe("syn-m-2");
  });

  it("starts a 32-slot draw at R32, not at R128", () => {
    const small = buildBracket(SYNTHETIC_MENS_DRAW.slice(0, 32));
    expect(small[0].round).toBe("R32");
    expect(small[small.length - 1].round).toBe("F");
  });

  it("refuses a draw that is not a power of two rather than truncating it", () => {
    expect(buildBracket(SYNTHETIC_MENS_DRAW.slice(0, 100))).toEqual([]);
    expect(buildBracket([])).toEqual([]);
  });
});

describe("an unplayed bracket projects nothing", () => {
  const rounds = buildBracket(SYNTHETIC_MENS_DRAW);

  it("declares no winners", () => {
    expect(rounds.every((r) => r.matches.every((m) => m.winnerKey === null))).toBe(true);
  });

  it("leaves every later round empty rather than guessing at it", () => {
    const secondRound = rounds[1];
    expect(secondRound.matches.every((m) => m.top === null && m.bottom === null)).toBe(true);
  });

  it("reports honest progress", () => {
    expect(bracketProgress(rounds)).toEqual({ played: 0, total: 127 });
  });
});

describe("results advance winners and only winners", () => {
  const results = syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW);
  const rounds = buildBracket(SYNTHETIC_MENS_DRAW, results);

  it("carries first-round winners into the second round", () => {
    expect(rounds[0].matches[0].winnerKey).toBe("syn-m-1");
    expect(rounds[1].matches[0].top?.entity_key).toBe("syn-m-1");
    expect(rounds[1].matches[0].bottom?.entity_key).toBe("syn-m-3");
  });

  it("does not advance past the results it was given", () => {
    expect(rounds[1].matches.every((m) => m.winnerKey === null)).toBe(true);
    expect(rounds[2].matches.every((m) => m.top === null && m.bottom === null)).toBe(true);
  });

  it("counts only decided matches", () => {
    expect(bracketProgress(rounds)).toEqual({ played: 64, total: 127 });
  });
});

describe("TournamentBracket rendering", () => {
  it("renders the not-yet state before the draw is released", () => {
    const html = renderToStaticMarkup(
      <TournamentBracket rounds={[]} drawReleased={false} />
    );
    expect(html).toContain('data-testid="bracket-unreleased"');
    expect(html).toContain("Draw not released");
    // And it says the boards are safe — the charter's own guarantee, on screen.
    expect(html).toContain("title boards do not move");
  });

  it("shows the not-yet state even if rounds arrive before the draw is official", () => {
    const html = renderToStaticMarkup(
      <TournamentBracket rounds={buildBracket(SYNTHETIC_MENS_DRAW)} drawReleased={false} />
    );
    expect(html).toContain('data-testid="bracket-unreleased"');
  });

  it("renders one column per round once released", () => {
    const html = renderToStaticMarkup(
      <TournamentBracket rounds={buildBracket(SYNTHETIC_MENS_DRAW)} drawReleased />
    );
    expect(html.match(/data-testid="bracket-round"/g)).toHaveLength(7);
    expect(html).toContain('data-round="R128"');
    expect(html).toContain('data-round="F"');
  });

  it("marks a decided match and its winner", () => {
    const rounds = buildBracket(
      SYNTHETIC_MENS_DRAW,
      syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW)
    );
    const html = renderToStaticMarkup(<TournamentBracket rounds={rounds} drawReleased />);
    expect(html).toContain('data-decided="true"');
    expect(html).toContain('data-won="true"');
  });

  it("marks an undecided match as undecided, with neither side won", () => {
    const html = renderToStaticMarkup(
      <TournamentBracket rounds={buildBracket(SYNTHETIC_MENS_DRAW)} drawReleased />
    );
    expect(html).toContain('data-decided="false"');
    expect(html).not.toContain('data-won="true"');
  });

  it("reports progress on screen", () => {
    const html = renderToStaticMarkup(
      <TournamentBracket rounds={buildBracket(SYNTHETIC_MENS_DRAW)} drawReleased />
    );
    expect(html).toContain('data-testid="bracket-progress"');
    expect(html).toContain("0 of 127 matches decided");
  });
});
