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
      <TournamentMatches entries={matchListFromSlate([incoherent])} initialOpenMatchId={incoherent.matchup_key} />
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
    const html = renderToStaticMarkup(
      <TournamentMatches entries={[entry]} initialOpenMatchId={entry.id} />
    );
    expect(html).not.toContain("has not moved");
  });

  it("a moved match's note adds ONLY the opening price", () => {
    const [entry] = matchListFromSlate([match()]);
    expect(entry.detailNote).toBe("Carlos Alcaraz opened at 74%.");
    // The two things already on the row are NOT repeated in it.
    expect(entry.detailNote).not.toContain("78%");
    expect(entry.detailNote).not.toContain("+4");
  });

  it("the row itself carries no restating sentence", () => {
    const html = renderToStaticMarkup(<TournamentMatches entries={matchListFromSlate([match()])} />);
    // Closed row: number, delta, no prose.
    expect(html).toContain('data-testid="match-move"');
    expect(html).not.toContain('data-testid="match-detail-note"');
    expect(html).not.toContain("opened at");
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

describe("ruling 7 — where to watch lives in the detail view", () => {
  const entries = matchListFromSlate([match()], { broadcasts: BROADCASTS });

  it("is NOT on the closed row", () => {
    const html = renderToStaticMarkup(<TournamentMatches entries={entries} />);
    expect(html).not.toContain("ESPN");
    expect(html).not.toContain('data-testid="match-detail-broadcast"');
  });

  it("appears when the row is opened", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches entries={entries} initialOpenMatchId={entries[0].id} />
    );
    expect(html).toContain('data-testid="match-detail-broadcast"');
    expect(html).toContain("ESPN, ESPN2");
  });

  it("is in exactly ONE place — a guard that only checked the detail would pass twice", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches entries={entries} initialOpenMatchId={entries[0].id} />
    );
    expect(count(html, "ESPN, ESPN2")).toBe(1);
  });

  it("tags the answer as region-wide, because that is all the register holds", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches entries={entries} initialOpenMatchId={entries[0].id} />
    );
    expect(html).toContain('data-scope="tournament"');
  });

  it("prefers a per-match channel the moment the register carries one", () => {
    const own = matchListFromSlate(
      [match({ broadcast: { region: "US", channels: ["Court 17 stream"], note: null } })],
      { broadcasts: BROADCASTS }
    );
    const html = renderToStaticMarkup(
      <TournamentMatches entries={own} initialOpenMatchId={own[0].id} />
    );
    expect(html).toContain('data-scope="match"');
    expect(html).toContain("Court 17 stream");
  });

  it("offers no tap at all on a row with nothing behind it", () => {
    const bare = matchListFromSlate([
      match({
        has_moved: false,
        sides: [
          side({ probability: 0.5, opening_probability: 0.5, move: 0 }),
          side({
            entity_key: "andrey-rublev",
            display_name: "Andrey Rublev",
            probability: 0.5,
            opening_probability: 0.5,
            move: 0,
          }),
        ],
      }),
    ]);
    const html = renderToStaticMarkup(<TournamentMatches entries={bare} />);
    expect(html).toContain("disabled");
    expect(html).not.toContain(">Details<");
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
        notice={{ tone: "stale", headline: "Prices paused", detail: "Last reading 9 hours ago." }}
      />
    );
    expect(html).toContain("Prices paused");
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
    expect(html).toContain("No matches scheduled");
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
  it("renders NO link when the register pins no event", () => {
    // The honest state today: checked 2026-08-26, none of the 66 registered US
    // Open matchups has an `events` row, because the qualifying draw was never
    // ingested as events. A dead affordance is worse than an absent one.
    const entries = matchListFromSlate([match()]);
    expect(entries[0].eventId).toBeNull();
    const html = renderToStaticMarkup(
      <TournamentMatches entries={entries} initialOpenMatchId={entries[0].id} />
    );
    expect(html).not.toContain('data-testid="match-event-link"');
  });

  it("renders the link to /events/{id} the moment the register pins one", () => {
    const entries = matchListFromSlate([match({ event_id: 15201771 })]);
    expect(entries[0].eventId).toBe(15201771);
    const html = renderToStaticMarkup(
      <TournamentMatches entries={entries} initialOpenMatchId={entries[0].id} />
    );
    expect(html).toContain('data-testid="match-event-link"');
    expect(html).toContain('href="/events/15201771"');
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

