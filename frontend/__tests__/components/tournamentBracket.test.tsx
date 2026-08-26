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
import {
  TITLE_COLUMN_LABEL,
  bracketProgress,
  buildBracket,
  prematchFromSlate,
  reachColumnLabel,
  roundIsUnreached,
  ROUND_NAMES,
} from "@/lib/bracket";
import { advanceMarketsForRound, advanceRound } from "@/lib/advanceToStage";
import type { TournamentBoardData } from "@/lib/tournament";
import {
  SYNTHETIC_MENS_DRAW,
  SYNTHETIC_WOMENS_DRAW,
  syntheticDrawWithHoles,
  syntheticFirstRoundResults,
  syntheticPartialResults,
  syntheticPrematch,
} from "../fixtures/syntheticDraw";

const count = (html: string, needle: string) =>
  (html.match(new RegExp(needle, "g")) ?? []).length;

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

describe("NOTHING advances without a declared result (UX-P136 regression)", () => {
  // The bug: a `null` opponent slot was read as a bye and advanced the other
  // side. It fired in two places, and BOTH printed a player into a round it
  // had not reached — the one thing the charter forbids, because a projection
  // rendered this way is indistinguishable from a result.

  it("does not advance a winner past an UNDECIDED sibling match", () => {
    // Two first-round matches feed R64-1. Decide only the first. The winner of
    // R128-1 belongs in R64 and NOWHERE further, because R128-2 is still on
    // court and R64-1 therefore has not been played.
    const rounds = buildBracket(SYNTHETIC_MENS_DRAW, syntheticPartialResults(SYNTHETIC_MENS_DRAW, 1));

    expect(rounds[1].matches[0].top?.entity_key).toBe("syn-m-1");
    expect(rounds[1].matches[0].bottom).toBeNull();
    // The bug walked syn-m-1 straight into R32 for beating an empty slot.
    expect(rounds[1].matches[0].winnerKey).toBeNull();
    expect(rounds[2].matches[0].top).toBeNull();
    expect(rounds[2].matches[0].bottom).toBeNull();
  });

  it("keeps a half-played first round out of every later round", () => {
    // THIRTY-THREE, not thirty-two, and the odd number is the whole point. An
    // even count fills R64 in complete pairs, so no match is ever left with
    // one side — the bug cannot fire and a green here would mean nothing. At
    // 33, R64's seventeenth match holds one name against an empty slot, which
    // is exactly the shape that used to promote him.
    const rounds = buildBracket(SYNTHETIC_MENS_DRAW, syntheticPartialResults(SYNTHETIC_MENS_DRAW, 33));
    const named = rounds[1].matches.flatMap((m) => [m.top, m.bottom]).filter(Boolean);
    expect(named).toHaveLength(33);
    expect(rounds[1].matches[16].top?.entity_key).toBe("syn-m-65");
    expect(rounds[1].matches[16].bottom).toBeNull();
    for (const later of rounds.slice(2)) {
      expect(later.matches.every((m) => m.top === null && m.bottom === null)).toBe(true);
    }
  });

  it("treats a register HOLE as undetermined, not as a bye", () => {
    // The backend's own contract: `None` is "a slot we hold no registered
    // player for … not a bye, and never a name we invented". The fold used to
    // disagree with the function feeding it, and promoted the opponent.
    const holed = syntheticDrawWithHoles(SYNTHETIC_MENS_DRAW, [1]);
    const rounds = buildBracket(holed);

    expect(rounds[0].matches[0].top?.entity_key).toBe("syn-m-1");
    expect(rounds[0].matches[0].bottom).toBeNull();
    expect(rounds[0].matches[0].winnerKey).toBeNull();
    // syn-m-1 did not win the Round of 128 by being the only one in it.
    expect(rounds[1].matches[0].top).toBeNull();
  });

  it("refuses a result naming somebody who is not in the match", () => {
    // A data fault, and the honest response is an empty slot rather than a
    // name teleported across the draw.
    const rounds = buildBracket(SYNTHETIC_MENS_DRAW, { "R128-1": "syn-m-99" });
    expect(rounds[0].matches[0].winnerKey).toBeNull();
    expect(rounds[1].matches[0].top).toBeNull();
  });
});

describe("roundIsUnreached", () => {
  it("is true for a round nobody has got to, false for one with names", () => {
    const rounds = buildBracket(SYNTHETIC_MENS_DRAW, syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW));
    expect(roundIsUnreached(rounds[0])).toBe(false);
    expect(roundIsUnreached(rounds[1])).toBe(false);
    expect(roundIsUnreached(rounds[2])).toBe(true);
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

  it("offers every round as a chip, and renders ONE of them", () => {
    // The 128-draw layout gate (UX-P136). Seven side-by-side columns is
    // ~1,360px wide and ~3,450px tall in its first column; at the 390px
    // viewport this page targets that is unreadable in two dimensions at once.
    const html = renderToStaticMarkup(
      <TournamentBracket rounds={buildBracket(SYNTHETIC_MENS_DRAW)} drawReleased />
    );
    expect(html.match(/data-testid="bracket-round-chip"/g)).toHaveLength(7);
    // ...but only one round's matches are in the document.
    expect(html.match(/data-testid="bracket-round"[^-]/g) ?? []).toHaveLength(1);
  });

  it("never renders more than one round's worth of match cards", () => {
    // The cost gate behind the layout change: the old render put all 127
    // matches on the page at once.
    const rounds = buildBracket(SYNTHETIC_MENS_DRAW, syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW));
    const html = renderToStaticMarkup(<TournamentBracket rounds={rounds} drawReleased />);
    const cards = (html.match(/data-testid="bracket-match"/g) ?? []).length;
    expect(cards).toBeLessThanOrEqual(64);
    expect(cards).toBeGreaterThan(0);
  });

  it("opens on the round the tournament is actually in", () => {
    // R128 fully played, so the tab should open on R64 — not on a round that
    // finished, and not on an empty Final.
    const rounds = buildBracket(SYNTHETIC_MENS_DRAW, syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW));
    const html = renderToStaticMarkup(<TournamentBracket rounds={rounds} drawReleased />);
    expect(html).toContain('data-testid="bracket-round-title" data-round="R64"');
  });

  it("collapses an unreached round to a sentence, not to empty cards", () => {
    const rounds = buildBracket(SYNTHETIC_MENS_DRAW, syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW));
    const html = renderToStaticMarkup(
      <TournamentBracket rounds={rounds} drawReleased initialRound="QF" />
    );
    expect(html).toContain('data-testid="bracket-round-unreached"');
    expect(html).toContain("Nobody has reached the quarter-finals yet");
    expect(html).not.toContain('data-testid="bracket-match"');
  });

  it("marks a decided match and its winner", () => {
    const rounds = buildBracket(
      SYNTHETIC_MENS_DRAW,
      syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW)
    );
    const html = renderToStaticMarkup(
      <TournamentBracket rounds={rounds} drawReleased initialRound="R128" />
    );
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

  it("renders the women's draw as readily as the men's", () => {
    const html = renderToStaticMarkup(
      <TournamentBracket
        rounds={buildBracket(SYNTHETIC_WOMENS_DRAW, syntheticFirstRoundResults(SYNTHETIC_WOMENS_DRAW))}
        drawReleased
        initialRound="R128"
      />
    );
    expect(html).toContain('data-entity="syn-w-1"');
    expect(html).toContain('data-won="true"');
  });

  it("prints no probability for a slot that has none, rather than a plausible one", () => {
    const html = renderToStaticMarkup(
      <TournamentBracket
        rounds={buildBracket(SYNTHETIC_MENS_DRAW)}
        drawReleased
        initialRound="R128"
        initialExpanded
      />
    );
    // Slot 101 is unpriced in the fixture, as most of a 128 field really is.
    const idx = html.indexOf('data-entity="syn-m-101"');
    expect(idx).toBeGreaterThan(-1);
    const cell = html.slice(idx, idx + 400);
    expect(cell).not.toMatch(/\d+\.\d%/);
  });

  it("reports progress on screen", () => {
    const html = renderToStaticMarkup(
      <TournamentBracket rounds={buildBracket(SYNTHETIC_MENS_DRAW)} drawReleased />
    );
    expect(html).toContain('data-testid="bracket-progress"');
    expect(html).toContain("0 of 127 matches decided");
  });
});

// ---------------------------------------------------------------------------
// UX-P137 — Alex's five bracket rulings, each with the failure it forbids
// ---------------------------------------------------------------------------

describe("ruling 1 — the pre-draw view is not empty", () => {
  const boardFor = (draw: string, name: string): TournamentBoardData => ({
    draw,
    label: draw === "mens-singles" ? "Men's Singles" : "Women's Singles",
    contenders: 2,
    unpriced: 0,
    price_state: "live",
    newest_observed_at: "2026-08-26T20:00:00+00:00",
    age_hours: 0.2,
    rows_not_live: 0,
    mixed_freshness_rows: 0,
    rows: [
      {
        entity_key: `${draw}-1`,
        display_name: name,
        seed: 1,
        country: null,
        rank: 1,
        state: "live",
        probability: 0.31,
        probability_is_live: true,
        observed_at: "2026-08-26T20:00:00+00:00",
        age_hours: 0.2,
        price_state: "live",
        source_count: 2,
        sources: [],
        stale_sources: [],
        mixed_freshness: false,
        freshest_observed_at: "2026-08-26T20:00:00+00:00",
        freshest_age_hours: 0.2,
        blend_rule: "equal_weight_midpoint",
        divergent: false,
        trend: [],
        trend_delta: null,
      },
    ],
  });

  const boards = [
    boardFor("mens-singles", "Ivan Petrenko"),
    boardFor("womens-singles", "Marta Kowalczyk"),
  ];

  it("shows BOTH winner boards before the draw exists", () => {
    // The ruling verbatim: "never an empty page when tradeable truth exists".
    // Both, not the one behind the gender pill — on the day before a ceremony
    // there is exactly one question and it has two answers.
    const html = renderToStaticMarkup(
      <TournamentBracket rounds={[]} drawReleased={false} preDrawBoards={boards} />
    );
    expect(html).toContain('data-testid="bracket-unreleased"');
    expect(count(html, 'data-testid="tournament-board"')).toBe(2);
    expect(html).toContain("Ivan Petrenko");
    expect(html).toContain("Marta Kowalczyk");
  });

  it("still says the draw is not out — the boards are an addition, not a cover", () => {
    const html = renderToStaticMarkup(
      <TournamentBracket rounds={[]} drawReleased={false} preDrawBoards={boards} />
    );
    expect(html).toContain("Draw not released");
  });

  it("degrades to the old honest sentence when there are no boards either", () => {
    // The other direction: a component that only worked with boards would
    // render a titled empty box on a tournament we hold no prices for.
    const html = renderToStaticMarkup(
      <TournamentBracket rounds={[]} drawReleased={false} />
    );
    expect(html).toContain("Draw not released");
    expect(html).not.toContain('data-testid="tournament-board"');
  });
});

describe("ruling 2 — the percentage column says what it means", () => {
  it("labels the column on every reachable round", () => {
    const rounds = buildBracket(SYNTHETIC_MENS_DRAW);
    const html = renderToStaticMarkup(
      <TournamentBracket rounds={rounds} drawReleased initialRound="R128" />
    );
    expect(html).toContain('data-testid="bracket-column-header"');
    expect(html).toContain(TITLE_COLUMN_LABEL);
  });

  it("the number IS the title probability, so the label may not say match", () => {
    // Traced end to end: `build_bracket` fills a slot from the register
    // player's `kind: "outright"` sources — the champion market. Beside an
    // opponent the player is about to play, it reads as a match number, which
    // is precisely why Alex could not tell.
    expect(TITLE_COLUMN_LABEL.toLowerCase()).toContain("title");
    expect(TITLE_COLUMN_LABEL.toLowerCase()).not.toContain("match");
  });

  it("a fully decided round says PRE-MATCH instead, because that is its number", () => {
    // A header describing a column that is not on screen is the same failure
    // in the other direction.
    const rounds = buildBracket(
      SYNTHETIC_MENS_DRAW,
      syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW)
    );
    const html = renderToStaticMarkup(
      <TournamentBracket rounds={rounds} drawReleased initialRound="R128" />
    );
    expect(html).toContain("Pre-match");
    expect(html).not.toContain(TITLE_COLUMN_LABEL);
  });

  it("the advance table carries its OWN sentence, not the title one", () => {
    expect(reachColumnLabel("QF")).toBe("To reach the quarter-finals");
    expect(reachColumnLabel("SF")).toBe("To reach the semi-finals");
  });
});

describe("ruling 3 — nothing renders blank", () => {
  const partly = buildBracket(
    SYNTHETIC_MENS_DRAW,
    syntheticPartialResults(SYNTHETIC_MENS_DRAW, 33)
  );

  it("names the feeder match instead of an em-dash", () => {
    // The mid-day state: R64 is half holes because half of R128 is still on
    // court. "— v —" is uninterpretable; "Winner of R128 #23" is checkable.
    const html = renderToStaticMarkup(
      <TournamentBracket rounds={partly} drawReleased initialRound="R64" initialExpanded />
    );
    expect(html).toContain("Winner of R128 #");
    expect(html).not.toMatch(/>—<\/span>/);
  });

  it("points at the CORRECT feeder — an off-by-one is a confident lie", () => {
    // R64 match 3 is fed by R128 matches 5 and 6. This is the assertion that
    // makes the sentence worth printing at all.
    const r64 = partly.find((r) => r.round === "R64")!;
    expect(r64.matches[2].topFrom).toBe("R128-5");
    expect(r64.matches[2].bottomFrom).toBe("R128-6");
    expect(r64.matches[0].topFrom).toBe("R128-1");
    const r128 = partly.find((r) => r.round === "R128")!;
    expect(r128.matches[0].topFrom).toBeNull();
    expect(r128.matches[0].bottomFrom).toBeNull();
  });

  it("a round-one hole is a REGISTER gap, and says so — not a feeder", () => {
    const holed = buildBracket(syntheticDrawWithHoles(SYNTHETIC_MENS_DRAW, [1, 3]));
    const html = renderToStaticMarkup(
      <TournamentBracket rounds={holed} drawReleased initialRound="R128" />
    );
    expect(html).toContain("No registered player");
    expect(html).not.toContain("Winner of");
  });

  it("a decided match prints an explicit outcome on BOTH sides", () => {
    // Bold-versus-muted is a font weight, not a result.
    const rounds = buildBracket(
      SYNTHETIC_MENS_DRAW,
      syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW)
    );
    const html = renderToStaticMarkup(
      <TournamentBracket rounds={rounds} drawReleased initialRound="R128" />
    );
    expect(html).toContain('data-outcome="won"');
    expect(html).toContain('data-outcome="out"');
    // Five cards collapsed, two sides each.
    expect(count(html, 'data-testid="bracket-outcome"')).toBe(10);
  });

  it("a decided match prints the PRE-MATCH probability beside the outcome", () => {
    const results = syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW);
    const rounds = buildBracket(SYNTHETIC_MENS_DRAW, results);
    const html = renderToStaticMarkup(
      <TournamentBracket
        rounds={rounds}
        drawReleased
        initialRound="R128"
        prematch={syntheticPrematch(results, SYNTHETIC_MENS_DRAW)}
      />
    );
    expect(html).toContain('data-testid="bracket-prematch"');
    // And NOT the title probability, which is a fact about nobody once the
    // match is over.
    expect(html).not.toContain('data-testid="bracket-title-probability"');
  });

  it("a decided match with no slate coverage still shows its outcome", () => {
    // The pre-match number is a bonus; the outcome is the ruling.
    const rounds = buildBracket(
      SYNTHETIC_MENS_DRAW,
      syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW)
    );
    const html = renderToStaticMarkup(
      <TournamentBracket rounds={rounds} drawReleased initialRound="R128" prematch={{}} />
    );
    expect(html).toContain('data-outcome="won"');
    expect(html).not.toContain('data-testid="bracket-prematch"');
  });

  it("joins the slate onto the draw by the pair of names, and never guesses", () => {
    const rounds = buildBracket(
      SYNTHETIC_MENS_DRAW,
      syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW)
    );
    const joined = prematchFromSlate(
      [
        {
          sides: [
            { entity_key: "syn-m-1", probability: 1, opening_probability: 0.64 },
            { entity_key: "syn-m-2", probability: 0, opening_probability: 0.36 },
          ],
        },
        // A pair that is not in this draw at all.
        {
          sides: [
            { entity_key: "nobody-a", probability: 0.5, opening_probability: 0.5 },
            { entity_key: "nobody-b", probability: 0.5, opening_probability: 0.5 },
          ],
        },
      ],
      rounds
    );
    expect(joined["R128-1"]).toEqual({ top: 0.64, bottom: 0.36 });
    expect(Object.keys(joined)).toHaveLength(1);
  });

  it("uses the OPENING price — the settled one is 1 or 0 and says nothing", () => {
    const rounds = buildBracket(SYNTHETIC_MENS_DRAW);
    const joined = prematchFromSlate(
      [
        {
          sides: [
            { entity_key: "syn-m-1", probability: 1, opening_probability: 0.58 },
            { entity_key: "syn-m-2", probability: 0, opening_probability: 0.42 },
          ],
        },
      ],
      rounds
    );
    expect(joined["R128-1"].top).toBe(0.58);
  });
});

describe("ruling 4 — an unreached round shows the markets on reaching it", () => {
  const advanceProp = (key: string, title: string, probability: number, draw: string) => ({
    key,
    title,
    hook: null,
    draw,
    source: "polymarket",
    outcomes: [
      {
        entity_key: `${key}:yes`,
        display_name: "Yes",
        probability,
        probability_is_live: false,
        observed_at: "2026-08-25T20:21:47+00:00",
        age_hours: 24.6,
        price_state: "stale" as const,
        is_answer: true,
      },
    ],
    answer_entity_key: `${key}:yes`,
    price_state: "stale" as const,
    observed_at: "2026-08-25T20:21:47+00:00",
    age_hours: 24.6,
    freshest_observed_at: "2026-08-25T20:21:47+00:00",
    freshest_age_hours: 24.6,
    stale_outcomes: [`${key}:yes`],
    mixed_freshness: false,
  });

  // The register's real eight, in the shape it really carries them.
  const markets = [
    advanceProp("alcaraz-semifinals", "Does Alcaraz reach the semifinals?", 0.575, "mens-singles"),
    advanceProp("zverev-semifinals", "Does Zverev reach the semifinals?", 0.47, "mens-singles"),
    advanceProp("djokovic-quarterfinals", "Does Djokovic reach the quarterfinals?", 0.58, "mens-singles"),
    advanceProp("shelton-quarterfinals", "Does Shelton reach the quarterfinals?", 0.505, "mens-singles"),
    advanceProp("osaka-round-of-16", "Does Osaka reach the second week?", 0.475, "womens-singles"),
    advanceProp("sinner-competes", "Will Sinner actually play?", 0.63, "mens-singles"),
  ];

  it("reads the round off the curated key, never off free text", () => {
    expect(advanceRound(markets[0])).toBe("SF");
    expect(advanceRound(markets[2])).toBe("QF");
    // Titled "the second week", keyed `round-of-16`. The key is the authority.
    expect(advanceRound(markets[4])).toBe("R16");
  });

  it("returns null for a prop that is not about reaching a round", () => {
    // A market filed under the wrong round is worse than one filed under none.
    expect(advanceRound(markets[5])).toBeNull();
  });

  it("selects by round AND draw, best first", () => {
    const sf = advanceMarketsForRound(markets, "SF", "mens-singles");
    expect(sf.map((e) => e.displayName)).toEqual(["Alcaraz", "Zverev"]);
    expect(sf[0].probability).toBe(0.575);
    // The women's R16 market must not appear on the men's side.
    expect(advanceMarketsForRound(markets, "R16", "mens-singles")).toEqual([]);
    expect(advanceMarketsForRound(markets, "R16", "womens-singles")).toHaveLength(1);
  });

  it("renders the table under an unreached round, with its own column label", () => {
    const rounds = buildBracket(
      SYNTHETIC_MENS_DRAW,
      syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW)
    );
    const html = renderToStaticMarkup(
      <TournamentBracket
        rounds={rounds}
        drawReleased
        initialRound="SF"
        propMarkets={markets}
        draw="mens-singles"
      />
    );
    expect(html).toContain('data-testid="bracket-round-unreached"');
    expect(html).toContain('data-testid="bracket-advance"');
    expect(html).toContain("To reach the semi-finals");
    expect(count(html, 'data-testid="bracket-advance-row"')).toBe(2);
  });

  it("keeps the honest sentence — the table is an addition, not a replacement", () => {
    const rounds = buildBracket(
      SYNTHETIC_MENS_DRAW,
      syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW)
    );
    const html = renderToStaticMarkup(
      <TournamentBracket
        rounds={rounds}
        drawReleased
        initialRound="SF"
        propMarkets={markets}
        draw="mens-singles"
      />
    );
    expect(html).toContain("Nobody has reached the semi-finals yet");
  });

  it("shows nothing extra when no market covers the round", () => {
    // The other direction: an empty bordered table under a round with no
    // markets is the emptiness this ruling exists to remove, re-added.
    const rounds = buildBracket(
      SYNTHETIC_MENS_DRAW,
      syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW)
    );
    const html = renderToStaticMarkup(
      <TournamentBracket
        rounds={rounds}
        drawReleased
        initialRound="F"
        propMarkets={markets}
        draw="mens-singles"
      />
    );
    expect(html).not.toContain('data-testid="bracket-advance"');
  });
});

describe("rulings 5 and 9 — the round list collapses", () => {
  it("shows five matches, not sixty-four", () => {
    const html = renderToStaticMarkup(
      <TournamentBracket
        rounds={buildBracket(SYNTHETIC_MENS_DRAW)}
        drawReleased
        initialRound="R128"
      />
    );
    expect(count(html, 'data-testid="bracket-match"')).toBe(5);
    expect(html).toContain("Show all 64");
  });

  it("expands to the whole round", () => {
    const html = renderToStaticMarkup(
      <TournamentBracket
        rounds={buildBracket(SYNTHETIC_MENS_DRAW)}
        drawReleased
        initialRound="R128"
        initialExpanded
      />
    );
    expect(count(html, 'data-testid="bracket-match"')).toBe(64);
  });

  it("a short round gets no expander", () => {
    // The Final is one match. "Show all 1" would be absurd, and a rule that
    // always rendered the control would print it.
    const html = renderToStaticMarkup(
      <TournamentBracket
        rounds={buildBracket(SYNTHETIC_MENS_DRAW, syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW))}
        drawReleased
        initialRound="R64"
      />
    );
    expect(html).toContain('data-testid="show-more"');
    const final = renderToStaticMarkup(
      <TournamentBracket
        rounds={buildBracket([SYNTHETIC_MENS_DRAW[0], SYNTHETIC_MENS_DRAW[1]])}
        drawReleased
      />
    );
    expect(final).not.toContain('data-testid="show-more"');
  });
});
