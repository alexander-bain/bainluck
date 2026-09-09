/**
 * #4332 (notice 34, eighth instance; #4125 item 1) — A MATCH ROW MAY DESCRIBE
 * THE MATCH, NEVER OUR PIPELINE.
 *
 * ═══ THE DEFECT, MEASURED ON PRODUCTION ═══
 *
 * `/tournaments/us-open` → Doubles → Quarter-Finals, 390px, Wed 2026-09-09
 * ~06:40am PT. Verbatim from the live DOM:
 *
 *     3:00 PM · MEN'S DOUBLES
 *     No probability yet
 *     KP  Kevin Krawietz / Tim Puetz
 *     MP  Marcelo Arevalo / Mate Pavic
 *     This match is in the draw with no probability against it. That is not a
 *     statement about whether a venue listed one.
 *
 * The row answers in two words and then explains the answer in nineteen more,
 * about our coverage. Notice 34 closes with the instruction this inverts — *"if
 * a number cannot be shown honestly, leave the space empty; do not explain the
 * emptiness in a paragraph"* — and Alex's words that produced the notice were
 * about this page: *"all the grey text is madness"*.
 *
 * ═══ WHY THE GUARD HAS TWO ARMS ═══
 *
 * `matchDetailNote` is called by BOTH mirrored builders (UX-P135):
 * `matchListFromSlate` (line ~630) and `matchListFromBracket` (line ~794). The
 * two reach the unpriced branch by DIFFERENT routes, so one arm cannot stand in
 * for the other:
 *
 *   slate    `priced: match.priced !== false`        — a real unquoted fixture
 *   bracket  `joined ? joined.priced !== false : false` — an UNJOINED draw slot
 *
 * A guard that renders only the slate leaves the board printing the paragraph
 * with the whole suite green. This is the failure ux/1152 shipped into #4283's
 * first cut and caught by hand; here it is caught by a test.
 *
 * ═══ WHAT MUST STILL PRINT (the CONTROLS, and they can fail) ═══
 *
 * Two of the four branches state a fact about the MATCH and are correct to
 * keep — the upset and the opening. The opening is visible on the sibling card
 * in the very screenshot above (*"Marcel Granollers / Horacio Zeballos opened
 * at 68%."*). Without these, "delete `matchDetailNote`" passes every assertion
 * in this file, and the ship would be a regression wearing a fix's clothes.
 */

import fs from "node:fs";
import path from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentMatches from "@/components/tournament/TournamentMatches";
import type { BracketRound } from "@/lib/bracket";
import { buildMatchList, matchDetailNote, matchListFromBracket, matchListFromSlate } from "@/lib/matchList";
import type { SlateMatch } from "@/lib/slate";
import type { TournamentPayload } from "@/lib/tournament";

/** The two sentences that talked about us. Neither may reach a reader again. */
const BANNED = [
  "no probability against it",
  "not a statement about whether a venue listed one",
  "we are not showing a split",
  "do not agree yet",
];

const PAYLOAD_PATH = path.join(
  __dirname,
  "..",
  "..",
  "..",
  "docs",
  "mocks",
  "us-open",
  "payload-2026-08-27.json"
);
const payload: TournamentPayload = JSON.parse(fs.readFileSync(PAYLOAD_PATH, "utf8"));
const ALL_SLATE = (payload.slate?.matches ?? []) as SlateMatch[];
const UNPRICED = ALL_SLATE.filter((m) => m.priced === false);

/**
 * The production specimen, rebuilt from the committed corpus rather than typed
 * out: a real unpriced producer row wearing the live card's two names. Only the
 * display strings move, so every field that decides the branch is the
 * backend's (ux/1008's lesson — a hand-built row can invent its own population).
 */
const LIVE_DOUBLES_ROW = {
  ...UNPRICED[0],
  sides: [
    { ...(UNPRICED[0].sides?.[0] as object), display_name: "Kevin Krawietz / Tim Puetz" },
    { ...(UNPRICED[0].sides?.[1] as object), display_name: "Marcelo Arevalo / Mate Pavic" },
  ],
} as unknown as SlateMatch;

function notesIn(html: string): string[] {
  return [...html.matchAll(/data-testid="match-detail-note"[^>]*>([^<]*)</g)].map((m) =>
    m[1].replace(/\s+/g, " ").trim()
  );
}

function renderSlate(rows: SlateMatch[]): string {
  return renderToStaticMarkup(
    <TournamentMatches
      entries={buildMatchList({ slate: rows, rounds: [] })}
      initialExpanded
      notice={null}
    />
  );
}

/** An UNJOINED draw slot: the bracket arm's own route to `priced: false`. */
const UNJOINED_ROUND: BracketRound[] = [
  {
    round: "QF",
    label: "Quarter-Finals",
    matches: [
      {
        id: "qf-1",
        round: "QF",
        top: { entity_key: "krawietz-puetz", display_name: "Krawietz / Puetz", seed: 3, probability: null },
        bottom: { entity_key: "arevalo-pavic", display_name: "Arevalo / Pavic", seed: 1, probability: null },
        winnerKey: null,
        topFrom: null,
        bottomFrom: null,
      },
    ],
  },
];

// ---------------------------------------------------------------------------
// THE FIXTURE IS HONEST — the corpus really does hold the branch's population
// ---------------------------------------------------------------------------

describe("the corpus reaches the branch under test", () => {
  it("the committed payload carries real unpriced producer rows", () => {
    expect(UNPRICED.length).toBe(96);
    expect(UNPRICED[0].priced).toBe(false);
  });

  it("the rebuilt specimen changed ONLY the two display names", () => {
    const base = UNPRICED[0] as unknown as Record<string, unknown>;
    const live = LIVE_DOUBLES_ROW as unknown as Record<string, unknown>;
    const changed = [...new Set([...Object.keys(base), ...Object.keys(live)])].filter(
      (k) => k !== "sides" && base[k] !== live[k]
    );
    expect(changed).toEqual([]);
    expect(live.priced).toBe(false);
  });

  it("the UNJOINED bracket slot really does reach `priced: false`", () => {
    // Not an assumption: the bracket builder defaults an unjoined slot to
    // unpriced, which is the arm a slate-only guard cannot see.
    const entries = matchListFromBracket(UNJOINED_ROUND, {});
    expect(entries).toHaveLength(1);
    expect(entries[0].priced).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// THE SHIP — both arms, at the render
// ---------------------------------------------------------------------------

describe("an unpriced row stops explaining its own emptiness", () => {
  it("THE SPECIMEN: the live doubles card renders NO detail note", () => {
    const html = renderSlate([LIVE_DOUBLES_ROW]);
    expect(notesIn(html)).toEqual([]);
    // The names are really on the card — so the empty note is the note being
    // absent, not the row failing to render (a blank render passes any
    // `not.toContain`, which is how an empty-render guard lies).
    expect(html).toContain("Kevin Krawietz / Tim Puetz");
  });

  it("THE SPECIMEN: the honest empty answer is still there", () => {
    // Notice 34 says leave the space empty, not leave the reader guessing.
    // `slate.ts` already answers as `kind: "answer"`, and that must survive.
    expect(renderSlate([LIVE_DOUBLES_ROW])).toContain("No probability yet");
  });

  it("ARM 1 (slate): not one of the 96 unpriced rows prints a banned sentence", () => {
    const html = renderSlate(UNPRICED);
    for (const phrase of BANNED) expect(html).not.toContain(phrase);
    expect(notesIn(html)).toEqual([]);
  });

  it("ARM 2 (bracket): an unjoined draw slot prints no note either", () => {
    const entries = matchListFromBracket(UNJOINED_ROUND, {});
    expect(entries[0].detailNote).toBeNull();
    const html = renderToStaticMarkup(
      <TournamentMatches entries={entries} initialExpanded notice={null} />
    );
    for (const phrase of BANNED) expect(html).not.toContain(phrase);
    // Same anti-blank-render check as the specimen arm.
    expect(html).toContain("Krawietz / Puetz");
  });

  it("the `!coherent` branch is silent too, on every state it can be in", () => {
    // Zero live rows today (11 priced+coherent, 1 unpriced, 0 priced-incoherent
    // in `GET /api/tournaments/us-open` this morning) — but it is the same
    // defect in the same function and it had no test at all before this file.
    for (const priced of [true, undefined]) {
      for (const decided of [false, true]) {
        expect(
          matchDetailNote({
            coherent: false,
            decided,
            liveState: null,
            score: null,
            priced,
            sides: [{} as never, {} as never],
          })
        ).toBeNull();
      }
    }
  });
});

// ---------------------------------------------------------------------------
// CONTROLS — the survivors still print, or the ship is a deletion
// ---------------------------------------------------------------------------

describe("CONTROL: the row still says what it knows about the MATCH", () => {
  const withOpening = (m: SlateMatch): SlateMatch =>
    ({
      ...m,
      priced: true,
      coherent: true,
      sides: [
        { ...(m.sides?.[0] as object), probability: 0.72, opening_probability: 0.68 },
        { ...(m.sides?.[1] as object), probability: 0.28, opening_probability: 0.32 },
      ],
    }) as unknown as SlateMatch;

  it("the OPENING sentence survives — it was on the sibling card in the shot", () => {
    const notes = notesIn(renderSlate([withOpening(UNPRICED[0])]));
    expect(notes).toHaveLength(1);
    expect(notes[0]).toMatch(/opened at \d+%/);
  });

  it("the UPSET sentence survives", () => {
    const note = matchDetailNote({
      coherent: true,
      decided: true,
      liveState: null,
      score: "6-4, 6-4",
      priced: true,
      // The upset is the FAVOURITE losing, so the favoured side is the one
      // with `isWinner: false` — getting this backwards is how the first cut of
      // this control passed a null through as if the branch were gone.
      sides: [
        { displayName: "Favourite", matchProbability: 0.59, isWinner: false },
        { displayName: "Upsetter", matchProbability: 0.41, isWinner: true },
      ] as never,
    });
    expect(note).toBe("Favourite was favoured at 59%.");
  });

  it("a plain decided row still says nothing, as it always did", () => {
    expect(
      matchDetailNote({
        coherent: true,
        decided: true,
        liveState: null,
        score: "6-4, 6-4",
        priced: true,
        sides: [
          { displayName: "Fav", matchProbability: 0.7, isWinner: true },
          { displayName: "Dog", matchProbability: 0.3, isWinner: false },
        ] as never,
      })
    ).toBeNull();
  });

  it("the slate builder still produces rows at all", () => {
    // The cheapest way this ship could be a silent deletion is the builder
    // returning nothing; assert the denominator rather than trusting it.
    expect(matchListFromSlate(ALL_SLATE).length).toBe(ALL_SLATE.length);
  });
});
