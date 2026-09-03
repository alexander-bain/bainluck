/**
 * THE MATCH LIST — UX-P138, Alex's rulings 1, 2, 4, 6 and 7.
 *
 * This suite replaces the component half of `tournamentSlate.test.tsx` and the
 * match-card half of `tournamentBracket.test.tsx`, because ruling 4 merged
 * those two lists into one. The pure-`lib/slate` assertions stay where they
 * are; what is here is the join, the two-number treatment, and the detail view.
 *
 * The failures this suite exists to catch, each of them a thing the page did
 * or nearly did:
 *
 * 1. **One match rendered twice.** Before ruling 4 the slate and the bracket
 *    both listed a main-draw fixture, on two tabs, with nothing saying they
 *    were the same match. The dedup test is the first one below.
 * 2. **A bare percentage.** UX-P137's ruling 2 came from Alex being unable to
 *    tell what a number on this page meant. Ruling 1 puts a SECOND number on
 *    every row. If the chip ever loses the word "title", the confusion is back
 *    in a smaller font.
 * 3. **The sentence coming back.** Ruling 6 deleted a generator, not a call
 *    site, and the tests assert the row prints no restatement — both that the
 *    flat row is silent and that the moved row's addition is only the OPENING
 *    price.
 * 4. **Where-to-watch leaking back onto the row.** Ruling 7 moved it behind a
 *    tap; a guard that only checked "the detail contains it" would pass with
 *    it in both places.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import TournamentMatches from "@/components/tournament/TournamentMatches";
import {
  buildMatchList,
  defaultMatchRound,
  matchDetailNote,
  matchListFromBracket,
  matchListFromSlate,
  matchRoundPills,
  slateRoundKey,
  titleChipLabel,
} from "@/lib/matchList";
import { buildBracket } from "@/lib/bracket";
import type { Broadcast, SlateMatch, SlateSide } from "@/lib/slate";
import {
  SYNTHETIC_MENS_DRAW,
  syntheticFirstRoundResults,
  syntheticPartialResults,
  syntheticPrematch,
} from "../fixtures/syntheticDraw";

const count = (html: string, needle: string) =>
  (html.match(new RegExp(needle, "g")) ?? []).length;

function side(overrides: Partial<SlateSide> = {}): SlateSide {
  return {
    entity_key: "carlos-alcaraz",
    display_name: "Carlos Alcaraz",
    seed: 1,
    country: null,
    role: "participant",
    probability: 0.78,
    opening_probability: 0.74,
    move: 0.04,
    raw_probability: 0.78,
    raw_opening_probability: 0.74,
    age_hours: 0.2,
    price_state: "live",
    ...overrides,
  };
}

function match(overrides: Partial<SlateMatch> = {}): SlateMatch {
  return {
    matchup_key: "mens-singles:alcaraz-vs-rublev:2026-08-31",
    draw: "mens-singles",
    draw_label: "Men's Singles",
    round: "R64",
    scheduled_date: "2026-08-31T15:00:00+00:00",
    sides: [
      side(),
      side({
        entity_key: "andrey-rublev",
        display_name: "Andrey Rublev",
        seed: 9,
        probability: 0.22,
        opening_probability: 0.26,
        move: -0.04,
      }),
    ],
    coherent: true,
    raw_sum: 1,
    opening_raw_sum: 1,
    probability_is_live: true,
    price_state: "live",
    observed_at: "2026-08-31T14:50:00+00:00",
    age_hours: 0.2,
    freshest_observed_at: "2026-08-31T14:50:00+00:00",
    freshest_age_hours: 0.2,
    stale_sides: [],
    mixed_freshness: false,
    favourite: "carlos-alcaraz",
    has_moved: true,
    source_count: 1,
    ...overrides,
  };
}

const BROADCASTS: Broadcast[] = [
  { region: "US", channels: ["ESPN", "ESPN2"], note: null },
  { region: "UK", channels: ["Sky Sports Tennis"], note: null },
];

// ---------------------------------------------------------------------------
// Ruling 4 — ONE list. The dedup is the point.
// ---------------------------------------------------------------------------

describe("ruling 4 — the slate and the draw are one match list", () => {
  const draw = [
    { entity_key: "carlos-alcaraz", display_name: "Carlos Alcaraz", seed: 1, probability: 0.31 },
    { entity_key: "andrey-rublev", display_name: "Andrey Rublev", seed: 9, probability: 0.09 },
  ];

  it("renders a positioned match ONCE, not once per pipeline", () => {
    const rounds = buildBracket(draw);
    const entries = buildMatchList({ slate: [match()], rounds });
    expect(entries).toHaveLength(1);
    expect(entries[0].source).toBe("bracket");
  });

  it("the surviving entry keeps the draw POSITION and gains the slate's PRICE", () => {
    const rounds = buildBracket(draw);
    const [entry] = buildMatchList({ slate: [match()], rounds });
    expect(entry.round).toBe("F");
    const alcaraz = entry.sides.find((s) => s.entityKey === "carlos-alcaraz");
    expect(alcaraz?.matchProbability).toBe(0.78);
  });

  it("keeps a slate match the draw does not contain — qualifying is still a round", () => {
    const rounds = buildBracket(draw);
    const qualifier = match({
      matchup_key: "q1",
      round: "qualifying",
      sides: [
        side({ entity_key: "a", display_name: "A" }),
        side({ entity_key: "b", display_name: "B", probability: 0.22 }),
      ],
    });
    const entries = buildMatchList({ slate: [match(), qualifier], rounds });
    expect(entries.map((e) => e.round).sort()).toEqual(["F", "qualifying"]);
  });

  it("offers a pill only for rounds that HAVE matches", () => {
    const rounds = buildBracket(SYNTHETIC_MENS_DRAW, syntheticPartialResults(SYNTHETIC_MENS_DRAW, 3));
    const pills = matchRoundPills(buildMatchList({ rounds }));
    // R128 has names; R64 has three real names against feeders; R32 onward is
    // 62 cards of "Winner of ..." and gets no pill at all.
    expect(pills.map((p) => p.round)).toEqual(["R128", "R64"]);
  });

  it("a round nobody has reached contributes nothing at all", () => {
    const rounds = buildBracket(SYNTHETIC_MENS_DRAW);
    const entries = buildMatchList({ rounds });
    expect(entries.every((e) => e.round === "R128")).toBe(true);
    expect(entries).toHaveLength(64);
  });

  it("opens on the earliest round still being played", () => {
    const rounds = buildBracket(SYNTHETIC_MENS_DRAW, syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW));
    // R128 is finished, R64 is not — the tab must not open on last week.
    expect(defaultMatchRound(buildMatchList({ rounds }))).toBe("R64");
  });

  it("normalises whatever the register calls a round, and never drops a match", () => {
    expect(slateRoundKey("qualifying")).toBe("qualifying");
    expect(slateRoundKey("Quarter-finals")).toBe("QF");
    expect(slateRoundKey("round of 32")).toBe("R32");
    expect(slateRoundKey("")).toBe("qualifying");
    // The unrecognised case files LEFT rather than losing the row.
    expect(slateRoundKey("mixed doubles playoff")).toBe("qualifying");
    expect(matchListFromSlate([match({ round: "who knows" })])).toHaveLength(1);
  });

  it("renders round pills and only the active round's matches", () => {
    const rounds = buildBracket(SYNTHETIC_MENS_DRAW, syntheticPartialResults(SYNTHETIC_MENS_DRAW, 3));
    const html = renderToStaticMarkup(
      <TournamentMatches entries={buildMatchList({ rounds })} initialRound="R64" />
    );
    expect(html).toContain('data-testid="match-round-strip"');
    expect(count(html, 'data-testid="match-round-pill"')).toBe(2);
    expect(html).toContain('data-round="R64"');
    expect(count(html, 'data-testid="match-row"')).toBe(5);
  });

  it("shows NO pill strip when there is only one round — a strip of one is a label", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches entries={matchListFromSlate([match()])} />
    );
    expect(html).not.toContain('data-testid="match-round-strip"');
    expect(html).toContain('data-testid="match-round-heading"');
  });
});

// ---------------------------------------------------------------------------
// Ruling 1 — match odds primary, title chance as a labelled secondary chip
// ---------------------------------------------------------------------------

describe("ruling 1 — match odds everywhere a match shows", () => {
  const titleChances = { "carlos-alcaraz": 0.31, "andrey-rublev": 0.09 };

  it("prints the MATCH number as the big one", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches entries={matchListFromSlate([match()], { titleChances })} />
    );
    expect(html).toContain("78%");
    expect(html).toContain("22%");
    expect(count(html, 'data-testid="match-probability"')).toBe(2);
  });

  it("carries the title chance as a chip, on the SAME row", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches entries={matchListFromSlate([match()], { titleChances })} />
    );
    expect(count(html, 'data-testid="match-title-chip"')).toBe(2);
    expect(html).toContain("31% title");
    expect(html).toContain("9% title");
  });

  it("the chip SAYS what it is — a bare percentage is the defect ruling 2 named", () => {
    expect(titleChipLabel(0.31)).toBe("31% title");
    expect(titleChipLabel(0.31)).toContain("title");
    // And the full sentence reaches a screen reader.
    const html = renderToStaticMarkup(
      <TournamentMatches entries={matchListFromSlate([match()], { titleChances })} />
    );
    expect(html).toContain("chance of winning the tournament");
  });

  it("omits the chip entirely rather than printing an empty one", () => {
    // Density is the binding constraint here (Alex: "without it being too
    // busy"). An absent chip is quieter than a chip apologising for being
    // empty, and most of a 128 field genuinely has no title price.
    expect(titleChipLabel(null)).toBeNull();
    const html = renderToStaticMarkup(
      <TournamentMatches entries={matchListFromSlate([match()])} />
    );
    expect(html).not.toContain('data-testid="match-title-chip"');
    expect(html).not.toContain("—%");
  });

  it("the column header names the big number's question", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches entries={matchListFromSlate([match()], { titleChances })} />
    );
    expect(html).toContain('data-testid="match-column-label"');
    expect(html).toContain("To win this match");
  });

  it("the two numbers come from DIFFERENT markets and neither is derived", () => {
    // The one thing that must never happen: the title chip computed off the
    // match price, or vice versa. 0.78 and 0.31 have no arithmetic relation
    // and the row prints both unchanged.
    const [entry] = matchListFromSlate([match()], { titleChances });
    const alcaraz = entry.sides.find((s) => s.entityKey === "carlos-alcaraz");
    expect(alcaraz?.matchProbability).toBe(0.78);
    expect(alcaraz?.titleChance).toBe(0.31);
  });

  it("prefers the BOARD's title number over the draw slot's copy", () => {
    // Two surfaces printing different values for one question is the
    // divergence bug, not a feature.
    const rounds = buildBracket([
      { entity_key: "carlos-alcaraz", display_name: "Carlos Alcaraz", seed: 1, probability: 0.55 },
      { entity_key: "andrey-rublev", display_name: "Andrey Rublev", seed: 9, probability: 0.09 },
    ]);
    const [entry] = matchListFromBracket(rounds, { titleChances });
    expect(entry.sides.find((s) => s.entityKey === "carlos-alcaraz")?.titleChance).toBe(0.31);
  });

  it("puts BOTH numbers on the nothing-played view, which is what the ruling asked for", () => {
    const rounds = buildBracket(SYNTHETIC_MENS_DRAW);
    const chances = Object.fromEntries(
      SYNTHETIC_MENS_DRAW.slice(0, 4).map((s) => [s.entity_key, s.probability])
    );
    const slate = [
      match({
        matchup_key: "m1",
        round: "R128",
        sides: [
          side({ entity_key: SYNTHETIC_MENS_DRAW[0].entity_key, display_name: "A" }),
          side({
            entity_key: SYNTHETIC_MENS_DRAW[1].entity_key,
            display_name: "B",
            probability: 0.22,
          }),
        ],
      }),
    ];
    const html = renderToStaticMarkup(
      <TournamentMatches
        entries={buildMatchList({ rounds, slate, titleChances: chances })}
        initialRound="R128"
      />
    );
    expect(html).toContain("78%");
    expect(html).toContain('data-testid="match-title-chip"');
  });
});

// ---------------------------------------------------------------------------
// Ruling 2 — a decided match shows the score with the outcome
// ---------------------------------------------------------------------------

describe("ruling 2 — decided matches print the score with the outcome", () => {
  const decided = match({
    winner_entity_key: "carlos-alcaraz",
    score: "6-1, 6-4",
    probability_is_live: false,
  });

  it("renders the score", () => {
    const html = renderToStaticMarkup(<TournamentMatches entries={matchListFromSlate([decided])} />);
    expect(html).toContain('data-testid="match-score"');
    expect(html).toContain("6-1, 6-4");
  });

  it("renders the outcome on BOTH sides — a font weight is not a result", () => {
    const html = renderToStaticMarkup(<TournamentMatches entries={matchListFromSlate([decided])} />);
    expect(html).toContain('data-outcome="won"');
    expect(html).toContain('data-outcome="out"');
  });

  it("keeps the score ON THE CARD, not behind the tap — a result is not a detail", () => {
    const html = renderToStaticMarkup(<TournamentMatches entries={matchListFromSlate([decided])} />);
    const beforeDetail = html.split('data-testid="match-detail"')[0];
    expect(beforeDetail).toContain("6-1, 6-4");
  });

  it("still shows the outcome when there is no score — which is every match today", () => {
    // The honest state of our pipeline: nothing anywhere holds a tennis result
    // or its score. The seam renders when filled and prints nothing when not.
    const html = renderToStaticMarkup(
      <TournamentMatches
        entries={matchListFromSlate([match({ winner_entity_key: "carlos-alcaraz" })])}
      />
    );
    expect(html).toContain('data-outcome="won"');
    expect(html).not.toContain('data-testid="match-score"');
  });

  it("prints the PRE-MATCH number on a decided bracket row, not the settled one", () => {
    // Once a match is over the live price has collapsed to 1 or 0; printing it
    // beside the result is a tautology dressed as a forecast.
    const results = syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW);
    const rounds = buildBracket(SYNTHETIC_MENS_DRAW, results);
    const prematch = syntheticPrematch(results, SYNTHETIC_MENS_DRAW);
    const entries = matchListFromBracket(rounds, { prematch });
    const first = entries[0];
    expect(first.decided).toBe(true);
    expect(first.sides[0].matchProbability).toBe(prematch["R128-1"].top);
  });

  it("suppresses the movement chip on a decided row — there is nothing left to move", () => {
    const html = renderToStaticMarkup(<TournamentMatches entries={matchListFromSlate([decided])} />);
    expect(html).not.toContain('data-testid="match-move"');
  });
});

// ---------------------------------------------------------------------------
// Ruling 3 (UX-P137) — nothing renders blank
// ---------------------------------------------------------------------------

describe("nothing renders blank", () => {
  it("names the feeder match instead of an em-dash", () => {
    const rounds = buildBracket(SYNTHETIC_MENS_DRAW, syntheticPartialResults(SYNTHETIC_MENS_DRAW, 3));
    const html = renderToStaticMarkup(
      <TournamentMatches entries={buildMatchList({ rounds })} initialRound="R64" />
    );
    expect(html).toContain('data-placeholder="awaiting-feeder"');
    expect(html).toContain("Winner of R128 #");
  });

  it("a round-one hole is a REGISTER gap and says so", () => {
    const holed = buildBracket(
      SYNTHETIC_MENS_DRAW.map((slot, i) => (i === 1 ? null : slot))
    );
    const html = renderToStaticMarkup(
      <TournamentMatches entries={buildMatchList({ rounds: holed })} initialRound="R128" />
    );
    // UX-P145: OUR name for the gap stays on the data attribute, where our
    // names belong; the reader gets a sentence about their draw instead of
    // about our JSON file ("No registered player" → "Player to be confirmed").
    expect(html).toContain('data-placeholder="register-hole"');
    expect(html).toContain("Player to be confirmed");
  });

  it("an incoherent pair shows both names and no split", () => {
    const incoherent = match({
      coherent: false,
      probability_is_live: false,
      sides: [
        side({ probability: null, opening_probability: null, move: null }),
        side({
          entity_key: "andrey-rublev",
          display_name: "Andrey Rublev",
          probability: null,
          opening_probability: null,
          move: null,
        }),
      ],
    });
    const html = renderToStaticMarkup(
      <TournamentMatches entries={matchListFromSlate([incoherent])} />
    );
    expect(html).toContain("Carlos Alcaraz vs Andrey Rublev");
    expect(html).toContain("do not agree");
    expect(html).not.toMatch(/\d+%/);
  });
});

// ---------------------------------------------------------------------------
// Ruling 6 — one primary treatment. The sentence is gone unless it adds.
// ---------------------------------------------------------------------------

describe("ruling 6 — the redundancy is dead", () => {
  it("a flat match gets NO sentence at all", () => {
    const flat = match({
      has_moved: false,
      sides: [
        side({ probability: 0.65, opening_probability: 0.65, move: 0 }),
        side({
          entity_key: "andrey-rublev",
          display_name: "Andrey Rublev",
          probability: 0.35,
          opening_probability: 0.35,
          move: 0,
        }),
      ],
    });
    const [entry] = matchListFromSlate([flat]);
    expect(entry.detailNote).toBeNull();
    const html = renderToStaticMarkup(<TournamentMatches entries={[entry]} />);
    expect(html).not.toContain("has not moved");
  });

  it("a moved match's note adds ONLY the opening price", () => {
    const [entry] = matchListFromSlate([match()]);
    expect(entry.detailNote).toBe("Carlos Alcaraz opened at 74%.");
    // The two things already on the row are NOT repeated in it.
    expect(entry.detailNote).not.toContain("78%");
    expect(entry.detailNote).not.toContain("+4");
  });

  it("the row carries the one sentence and nothing else (UX-P154)", () => {
    /* The sentence moved ONTO the card when UX-P154 deleted the drawer it used
     * to sit in — Alex's item 2: the whole card is the link, so there is no
     * accordion left to hide anything behind.
     *
     * Ruling 6 is unchanged and still enforced: a sentence appears only when it
     * adds something the numbers cannot say. `matchDetailNote` decides that and
     * returns `null` for most rows; the tests above and below pin both sides. */
    const html = renderToStaticMarkup(<TournamentMatches entries={matchListFromSlate([match()])} />);
    expect(html).toContain('data-testid="match-move"');
    expect(html).toContain('data-testid="match-detail-note"');
    expect(html).toContain("opened at");
  });

  it("a flat row still prints no sentence at all — ruling 6 is intact", () => {
    const flat = match({
      has_moved: false,
      sides: [
        side({ probability: 0.65, opening_probability: 0.65, move: 0 }),
        side({
          entity_key: "andrey-rublev",
          display_name: "Andrey Rublev",
          probability: 0.35,
          opening_probability: 0.35,
          move: 0,
        }),
      ],
    });
    const html = renderToStaticMarkup(
      <TournamentMatches entries={matchListFromSlate([flat])} />
    );
    expect(html).not.toContain('data-testid="match-detail-note"');
  });

  it("names the upset, because THAT comparison is not on the row", () => {
    const upset = match({
      winner_entity_key: "andrey-rublev",
      probability_is_live: false,
    });
    const [entry] = matchListFromSlate([upset]);
    expect(entry.detailNote).toBe("Carlos Alcaraz was favoured at 78%.");
  });

  it("says nothing about a decided match that went to form", () => {
    const [entry] = matchListFromSlate([
      match({ winner_entity_key: "carlos-alcaraz", probability_is_live: false }),
    ]);
    expect(entry.detailNote).toBeNull();
  });

  it("an incoherent pair keeps its sentence, because the row has no numbers", () => {
    expect(
      matchDetailNote({
        coherent: false,
        decided: false,
        // #2690 made this required. It is irrelevant to THIS arm — the row is
        // priced, so it never reaches the unpriced branch — and passing it
        // explicitly is the point: no call site may omit the row's state.
        liveState: null,
        score: null,
        sides: [] as never,
      })
    ).toContain("do not agree");
  });

  it("the deleted generator is really gone, not merely unused", () => {
    // Ruling 6 is about the layer that MANUFACTURES the redundancy. A
    // sentence generator left exported and tested is a sentence generator the
    // next component reaches for.
    const slate = jest.requireActual("@/lib/slate");
    expect(slate.matchNarrative).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Ruling 7 — where to watch is behind the tap, and ONLY behind the tap
// ---------------------------------------------------------------------------

/* ═══ RULING 7 KEPT ITS FORCE AND CHANGED ITS VENUE (UX-P154) ═══
 *
 * Alex's ruling 7: *"where-to-watch moves to the DETAIL view"* — not onto every
 * row, because a single line at the top of a long list is wrong and a line per
 * row is noise. UX-P138 implemented "the detail view" as an accordion inside
 * the row.
 *
 * Alex's item 2, 2026-08-28: the whole match card is clickable, exactly like
 * every other card in the product; no link row. So the accordion is gone, and
 * the detail view is the EVENT PAGE. The channel renders in
 * `TournamentExtensions` — guarded in `tournamentExtensions.test.tsx` — and the
 * property this block still owns is the negative one: **it did not come back
 * onto the row.** That is the half a moved feature usually loses.
 */
describe("ruling 7 — where to watch is NOT on the match row", () => {
  const entries = matchListFromSlate([match()], { broadcasts: BROADCASTS });

  it("is not on the row, in any state — there are no states left", () => {
    const html = renderToStaticMarkup(<TournamentMatches entries={entries} />);
    expect(html).not.toContain("ESPN");
    expect(html).not.toContain('data-testid="match-detail-broadcast"');
  });

  it("is not on the row even when the register carries a per-match channel", () => {
    // The case most likely to tempt a future change back onto the row: a real
    // per-match answer, which is exactly the thing ruling 7 said belongs in the
    // detail view rather than in the list.
    const own = matchListFromSlate(
      [match({ broadcast: { region: "US", channels: ["Court 17 stream"], note: null } })],
      { broadcasts: BROADCASTS }
    );
    const html = renderToStaticMarkup(<TournamentMatches entries={own} />);
    expect(html).not.toContain("Court 17 stream");
  });

  it("the accordion is gone — no toggle, no expanded state, no link row", () => {
    const html = renderToStaticMarkup(<TournamentMatches entries={entries} />);
    expect(html).not.toContain('data-testid="match-row-toggle"');
    expect(html).not.toContain('data-testid="match-detail"');
    expect(html).not.toContain('data-testid="match-page-link"');
    expect(html).not.toContain("See more on this match");
    expect(html).not.toContain("aria-expanded");
  });
});

// ---------------------------------------------------------------------------
// Honesty and collapse — carried over from the slate, because they still apply
// ---------------------------------------------------------------------------

describe("honesty treatment", () => {
  it("never upgrades a row the server did not call live", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches
        entries={matchListFromSlate([match({ probability_is_live: false, price_state: "stale", age_hours: 30 })])}
      />
    );
    expect(html).toContain('data-live="false"');
    expect(html).toContain('data-testid="match-age"');
  });

  it("does not label a live row at all — a healthy row that apologises teaches nothing", () => {
    const html = renderToStaticMarkup(<TournamentMatches entries={matchListFromSlate([match()])} />);
    expect(html).toContain('data-live="true"');
    expect(html).not.toContain('data-testid="match-age"');
  });

  it("carries the feed-wide banner, which the per-row ages do not add up to", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches
        entries={matchListFromSlate([match()])}
        notice={{ tone: "stale", headline: "Updates paused", detail: "Last reading 9 hours ago." }}
      />
    );
    expect(html).toContain("Updates paused");
    expect(html).toContain('data-testid="matches-notice"');
  });

  it("never renders a bare Yes or No as a side", () => {
    const html = renderToStaticMarkup(<TournamentMatches entries={matchListFromSlate([match()])} />);
    expect(html).not.toMatch(/>\s*Yes\s*</);
    expect(html).not.toMatch(/>\s*No\s*</);
  });

  it("says its own emptiness rather than rendering nothing", () => {
    const html = renderToStaticMarkup(<TournamentMatches entries={[]} />);
    expect(html).toContain('data-testid="matches-empty"');
    // #2707: this used to assert "No matches scheduled". That string was the
    // defect — the card printed it over five live US Open matches on
    // 2026-09-03 — so the assertion is now the shape of the admission rather
    // than the sentence that made it. The wording rules have their own suite in
    // `tournamentEmptySlate2707.test.tsx`.
    expect(html).toContain('data-empty-cause=');
    expect(html).not.toContain("No matches scheduled");
  });
});

describe("collapse — five, then an expander that says how many", () => {
  const rounds = buildBracket(SYNTHETIC_MENS_DRAW);

  it("shows five of sixty-four", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches entries={buildMatchList({ rounds })} initialRound="R128" />
    );
    expect(count(html, 'data-testid="match-row"')).toBe(5);
    expect(html).toContain("Show all 64");
  });

  it("expands to the whole round", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches entries={buildMatchList({ rounds })} initialRound="R128" initialExpanded />
    );
    expect(count(html, 'data-testid="match-row"')).toBe(64);
  });

  it("a short round gets no expander", () => {
    const html = renderToStaticMarkup(<TournamentMatches entries={matchListFromSlate([match()])} />);
    expect(html).not.toContain('data-testid="show-more"');
  });
});

// ---------------------------------------------------------------------------
// ITEM 7 (UX-P139) — the click-through to the standard event page
// ---------------------------------------------------------------------------

describe("item 7 — matches click through to the event page", () => {
  /**
   * UX-P152 merged the two links these tests were written against into one.
   *
   * There were two: item 7's `match-event-link` to `/events/{id}`, which
   * rendered on nothing because no fixture carried an event id, and UX-P149's
   * `match-page-link` to a tournament-private match URL, built BECAUSE the
   * first had nowhere to go. Both premises expired on 2026-08-27, when the Odds
   * API ingested the main draw and 94 standard `events` rows appeared for the
   * 96 registered R128 fixtures. The parallel page is deleted; one link remains
   * and it addresses `/events/{id}`.
   *
   * UX-P154 then deleted the link ROW as well. Alex: *"no 'See more on this
   * match' link row — the whole match card is clickable, exactly like every
   * other card in the product."* So there is no `match-page-link` any more;
   * the card itself is the anchor, and it marks itself `event-card` — the same
   * hook ruling 047's acceptance is written against for the league page.
   *
   * The behaviour these tests pin — a link exactly when there is an event to
   * link to — is unchanged.
   */
  it("renders NO link when the register pins no event", () => {
    // Still the honest state for the 28 registered QUALIFYING matchups: their
    // markets carry no `event_id` because the qualifying draw was never
    // ingested as events. A dead affordance is worse than an absent one — so
    // the card renders inert, with no anchor and no pointer treatment.
    const entries = matchListFromSlate([match()]);
    expect(entries[0].eventId).toBeNull();
    const html = renderToStaticMarkup(<TournamentMatches entries={entries} />);
    expect(html).not.toContain('href="/events/');
    expect(html).toContain('data-linked="false"');
    // Still drawn by the shared card — the marker is a claim about which
    // component rendered, which is true whether or not it links anywhere.
    expect(html).toContain('data-testid="event-card"');
  });

  it("THE WHOLE CARD is the link the moment the register pins an event", () => {
    const entries = matchListFromSlate([match({ event_id: 15201771 })]);
    expect(entries[0].eventId).toBe(15201771);
    const html = renderToStaticMarkup(<TournamentMatches entries={entries} />);
    expect(html).toContain('href="/events/15201771"');
    expect(html).toContain('data-linked="true"');
    // And it is the CARD that carries it, not a row inside the card.
    expect(html).not.toContain('data-testid="match-page-link"');
    expect(html).not.toContain("See more on this match");
    expect(count(html, 'href="/events/15201771"')).toBe(1);
  });

  it("the tournament list renders THE SHARED event card, not a copy of one", () => {
    /* Alex: *"it kinda feels like we're reinventing the event card inside the
     * tournament product"*, and: the tournament list uses THE standard
     * event-card component.
     *
     * `data-testid="event-card"` lives on `EventCardShell` and nowhere else, so
     * this assertion is answerable from the DOM: it is true only if the shared
     * component drew the row. A tournament-local card that copied the styling
     * could not produce it without importing the shell, which is the point.
     */
    const entries = matchListFromSlate([match({ event_id: 15201771 })]);
    const html = renderToStaticMarkup(<TournamentMatches entries={entries} />);
    expect(count(html, 'data-testid="event-card"')).toBe(1);
    // The shell is a real import, not a copied attribute.
    const shell = fs.readFileSync(
      path.join(__dirname, "..", "..", "components", "EventCardShell.tsx"),
      "utf8"
    );
    expect(shell).toContain('export const EVENT_CARD_TESTID = "event-card"');
    const list = fs.readFileSync(
      path.join(__dirname, "..", "..", "components", "tournament", "TournamentMatches.tsx"),
      "utf8"
    );
    expect(list).toContain('from "@/components/EventCardShell"');
    // The marker is EMITTED in exactly one component. Two emitters would be two
    // cards claiming to be the shared one, which is the state this whole item
    // exists to end. (`EventCardShell` names it; every other reference in the
    // tree is a comment or a test.)
    const emitters = fs
      .readdirSync(path.join(__dirname, "..", "..", "components"), { recursive: true })
      .filter((f) => typeof f === "string" && f.endsWith(".tsx"))
      .filter((f) => {
        const src = fs.readFileSync(
          path.join(__dirname, "..", "..", "components", f as string),
          "utf8"
        );
        return src.includes("data-testid={EVENT_CARD_TESTID}");
      });
    expect(emitters).toEqual(["EventCardShell.tsx"]);
  });

  it("carries the link through the bracket join, from the slate row it absorbed", () => {
    // A positioned draw slot has no event of its own; the link travels with the
    // price, from the slate row the position absorbed.
    const slate = match({ event_id: 42 });
    const entries = buildMatchList({
      rounds: buildBracket(SYNTHETIC_MENS_DRAW.slice(0, 2)),
      slate: [
        {
          ...slate,
          sides: [
            { ...slate.sides[0], entity_key: SYNTHETIC_MENS_DRAW[0]!.entity_key,
              display_name: SYNTHETIC_MENS_DRAW[0]!.display_name },
            { ...slate.sides[1], entity_key: SYNTHETIC_MENS_DRAW[1]!.entity_key,
              display_name: SYNTHETIC_MENS_DRAW[1]!.display_name },
          ],
        },
      ],
    });
    expect(entries).toHaveLength(1);
    expect(entries[0].source).toBe("bracket");
    expect(entries[0].eventId).toBe(42);
  });
});


// ---------------------------------------------------------------------------
// Q463 — THE DAY'S CARD, and the placeholder it must not print as a start
//
// Alex on opening day: "It's weird that there's no matches scheduled. that's
// obviously not true." It was not true; the server was dropping the whole draw
// because the register's midnight-local placeholder read as a start. The server
// fix puts those rows back, and these guard the two things that then reach the
// reader: the TBD rows must not claim a time, and the real ones must keep one.
// ---------------------------------------------------------------------------

describe("Q463 — a fixture with no published order of play says TBD", () => {
  const tbd = match({
    matchup_key: "mens-singles:mannarino-vs-tirante:2026-08-30",
    // Midnight in Flushing Meadows — ESPN's "some time that day".
    scheduled_date: "2026-08-31T04:00:00+00:00",
    start_is_tbd: true,
    live_state: "upcoming",
    status_detail: null,
  });

  it("carries the flag from the payload onto the entry", () => {
    const [entry] = matchListFromSlate([tbd]);
    expect(entry.startIsTbd).toBe(true);
    expect(entry.liveState).toBe("upcoming");
  });

  it("prints TBD and no clock time on the row", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches entries={matchListFromSlate([tbd])} />
    );
    expect(html).toContain("TBD");
    // The whole point: no confident hour for a match nobody has scheduled.
    expect(html).not.toMatch(/\d{1,2}:\d{2}\s?(AM|PM)/i);
  });

  it("a fixture WITH a real start still prints its time", () => {
    const scheduled = match({ start_is_tbd: false, live_state: "upcoming" });
    const html = renderToStaticMarkup(
      <TournamentMatches entries={matchListFromSlate([scheduled])} />
    );
    expect(html).toMatch(/\d{1,2}:\d{2}\s?(AM|PM)/i);
    expect(html).not.toContain("TBD");
  });

  it("a payload with neither field reads as a real start — nothing regresses", () => {
    const [entry] = matchListFromSlate([match()]);
    expect(entry.startIsTbd).toBe(false);
    expect(entry.liveState).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// #2550 — A MATCH THAT IS BEING PLAYED SAYS SO
//
// Shopper pass, 2026-09-01, 8:44 PM in Flushing Meadows: the hub printed
// "4:05 PM · Men's Singles" over Monfils v Vallejo. The server had already
// said `live_state: "in_progress"`, `status_detail: "3rd Set"` on that exact
// row, and the DB had the event at `status='live'`. Nothing was missing from
// the payload — `MatchRow` simply never read the field, so a match four hours
// into its third set advertised a start time that had come and gone.
//
// The clock is the defect, not just the absent badge. "4:05 PM" on a match
// being played now is not incomplete information, it is wrong information:
// a reader who checks back at 4:05 has already missed two sets.
//
// The label is ESPN's words when ESPN has live words, and the flat "LIVE"
// otherwise — the same `detail || "LIVE"` idiom `FeedCard` uses for a period
// and a game clock. `status_detail` is NOT trusted blindly: on an `upcoming`
// row that same field carries "Tue, September 1st at 9:00 PM EDT", and an
// ESPN row that flips to `in` a beat before its detail catches up would put
// a full scheduled datetime inside a red LIVE pill. A detail that still reads
// like a schedule is refused and the row falls back to the word.
// ---------------------------------------------------------------------------

describe("#2550 — an in-progress match prints LIVE, not a start time", () => {
  const inProgress = match({
    matchup_key: "mens-singles:adolfo-daniel-vallejo-vs-gael-monfils:2026-08-30",
    scheduled_date: "2026-09-01T23:05:00+00:00",
    start_is_tbd: false,
    live_state: "in_progress",
    status_detail: "3rd Set",
  });

  it("carries the detail from the payload onto the entry", () => {
    const [entry] = matchListFromSlate([inProgress]);
    expect(entry.liveState).toBe("in_progress");
    expect(entry.statusDetail).toBe("3rd Set");
  });

  it("prints ESPN's live words and NO scheduled clock", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches entries={matchListFromSlate([inProgress])} />
    );
    expect(html).toContain('data-testid="match-live"');
    expect(html).toContain("3rd Set");
    // The whole finding: the row must stop advertising a start that passed.
    expect(html).not.toMatch(/\d{1,2}:\d{2}\s?(AM|PM)/i);
  });

  it("falls back to the word when ESPN carries no live detail", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches
        entries={matchListFromSlate([match({ ...inProgress, status_detail: null })])}
      />
    );
    expect(html).toContain('data-testid="match-live"');
    expect(html).toContain("LIVE");
    expect(html).not.toMatch(/\d{1,2}:\d{2}\s?(AM|PM)/i);
  });

  it("refuses a detail that is still a schedule, rather than printing it as live", () => {
    // LAZY import: a missing export must fail THIS test, not collapse the
    // whole file into a module-resolution error that proves nothing about
    // what the row renders.
    const { liveMatchLabel } = require("@/lib/matchList");
    const [entry] = matchListFromSlate([
      match({ ...inProgress, status_detail: "Tue, September 1st at 9:00 PM EDT" }),
    ]);
    expect(liveMatchLabel(entry)).toBe("LIVE");
  });

  // CONTROL. An upcoming row is untouched by all of the above — it keeps its
  // clock and grows no badge. Without this the fix could simply delete times.
  it("leaves an upcoming row with its time and no badge", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches
        entries={matchListFromSlate([match({ live_state: "upcoming", status_detail: null })])}
      />
    );
    expect(html).toMatch(/\d{1,2}:\d{2}\s?(AM|PM)/i);
    expect(html).not.toContain('data-testid="match-live"');
  });

  it("leaves a row the scoreboard never listed with its time and no badge", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches entries={matchListFromSlate([match()])} />
    );
    expect(html).toMatch(/\d{1,2}:\d{2}\s?(AM|PM)/i);
    expect(html).not.toContain('data-testid="match-live"');
  });
});
