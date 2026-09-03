/**
 * UX-1042 / #2690 — AN UNPRICED HUB ROW STATES ITS OWN IGNORANCE, NOT THE
 * WORLD'S.
 *
 * ═══ THE DEFECT ═══
 *
 * `/tournaments/us-open` printed *"Nobody is quoting this match yet. It is in
 * the draw with no probability against it."* under a live Men's Singles third
 * set. In the same minute `/sports` priced that match 51/49 and
 * `/events/15300190` drew it a chart with five lead changes — so the hub, the
 * flagship surface during the tournament, made a confident claim about every
 * venue in the world that our own site refuted two clicks away. Both clauses
 * were false at once: the match was being quoted, and it was not "in the draw",
 * it was being played.
 *
 * ═══ WHY THE COMMITTED CORPUS CANNOT SEE IT (measured, and asserted below) ═══
 *
 * Every tournament fixture in this repo is ceremony day or later-but-dark:
 *
 *   payload-2026-08-27.json                    113 rows,  96 unpriced,  0 live
 *   payload-2026-08-28.json                     96 rows,  96 unpriced,  0 live
 *   payload-2026-08-31.json                      0 rows
 *   tournamentHubUsOpen.20260901.json            0 rows
 *   tournamentHubUsOpen.20260903.json            0 rows
 *   tournamentHubBooksRung.20260903T0310Z.json   0 rows
 *
 * **Zero live unpriced rows across all six.** That is why UX-P142's sentence
 * shipped and stayed green for a week: the population that falsifies it did not
 * exist when it was written (the AUTHORITY builder, which reuses `priced:
 * false` for ESPN-paired rows, landed after), and no fixture has carried one
 * since. `LIVE_UNPRICED_ROW` below is therefore CONSTRUCTED — and constructed
 * in the one way that cannot invent a population (ux/1008's lesson #2): it
 * takes a real unpriced row out of the committed producer output and overlays
 * ONLY the three fields the authority builder adds, at the values #2690
 * captured from production. The overlay's key set is asserted, so a reader can
 * check that every other field came from the backend rather than from me.
 *
 * ═══ WHAT IS ASSERTED, AND WHERE ═══
 *
 * At the RENDER, through the shipped `TournamentMatches`, because the sentence
 * is assembled per row and a library-level assertion cannot see a component
 * that stops printing it. The three arms differ only in the row's state, so
 * each one's expected clause is a discriminator rather than a restatement.
 */

import fs from "node:fs";
import path from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentMatches from "@/components/tournament/TournamentMatches";
import { findBannedCopy } from "@/lib/copyBans";
import { buildMatchList, matchDetailNote } from "@/lib/matchList";
import type { SlateMatch } from "@/lib/slate";
import type { TournamentPayload } from "@/lib/tournament";

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
const PRICED = ALL_SLATE.filter((m) => m.priced !== false);

/** The three fields the authority builder adds, at #2690's captured values. */
const AUTHORITY_OVERLAY = {
  live_state: "in_progress",
  status_detail: "3rd Set",
  pairing_source: "authority",
} as const;

const LIVE_UNPRICED_ROW = { ...UNPRICED[0], ...AUTHORITY_OVERLAY } as SlateMatch;
const DECIDED_UNPRICED_ROW = {
  ...UNPRICED[1],
  winner_entity_key: (UNPRICED[1].sides?.[0] as { entity_key?: string })?.entity_key,
} as SlateMatch;

function renderRows(rows: SlateMatch[]): string {
  return renderToStaticMarkup(
    <TournamentMatches
      entries={buildMatchList({ slate: rows, rounds: [] })}
      initialExpanded
      notice={null}
    />
  );
}

/**
 * The one sentence on a row, read off the render rather than the library.
 *
 * ANCHORED ON `data-testid="match-detail-note"`, which predates this diff, so
 * every arm below can run on the parent too. An extractor keyed on the NEW
 * wording makes every test that uses it arm-dependent — including the ones
 * labelled CONTROL, which then go red for a reason that has nothing to do with
 * the claim they make. The red arm caught exactly that and this is the repair.
 *
 * It also reports its own yield: one row in, one note out, or it throws with
 * the counts rather than silently returning the wrong row's sentence.
 */
function noteFor(rows: SlateMatch[]): string {
  const html = renderRows(rows);
  const notes = [
    ...html.matchAll(/data-testid="match-detail-note"[^>]*>([^<]*)</g),
  ].map((m) => m[1]);
  if (notes.length !== 1) {
    throw new Error(
      `expected exactly 1 detail note for ${rows.length} row(s), found ` +
        `${notes.length} in ${html.length} bytes: ${JSON.stringify(notes)}`
    );
  }
  return notes[0].replace(/\s+/g, " ").trim();
}

// ---------------------------------------------------------------------------
// THE FIXTURE IS HONEST
// ---------------------------------------------------------------------------

describe("the corpus, and how the live row was built", () => {
  it("the committed payload is ceremony day: many unpriced rows, NONE of them live", () => {
    expect(UNPRICED.length).toBe(96);
    expect(PRICED.length).toBe(17);
    // The measurement that explains the whole bug's lifetime.
    expect(UNPRICED.filter((m) => m.live_state === "in_progress")).toHaveLength(0);
    expect(UNPRICED.filter((m) => m.winner_entity_key)).toHaveLength(0);
  });

  it("the live row differs from real producer output in EXACTLY three keys", () => {
    const base = UNPRICED[0] as unknown as Record<string, unknown>;
    const live = LIVE_UNPRICED_ROW as unknown as Record<string, unknown>;
    const changed = [...new Set([...Object.keys(base), ...Object.keys(live)])].filter(
      (k) => base[k] !== live[k]
    );
    expect(changed.sort()).toEqual(["live_state", "pairing_source", "status_detail"]);
    // ...and it is still an unpriced row on every field that decides the branch.
    expect(live.priced).toBe(false);
    expect(live.price_state).toBe("unpriced");
    expect(live.event_id).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// THE SHIP
// ---------------------------------------------------------------------------

describe("an unpriced row no longer speaks for every venue in the world", () => {
  it("THE DEFECT: a LIVE unpriced row does not claim nobody is quoting it", () => {
    const note = noteFor([LIVE_UNPRICED_ROW]);
    expect(note).not.toContain("Nobody is quoting");
    expect(note).toContain("not a statement about whether a venue listed one");
  });

  it("THE DEFECT'S SECOND HALF: a match being played is not 'in the draw'", () => {
    const note = noteFor([LIVE_UNPRICED_ROW]);
    expect(note).toContain("This match is under way");
    expect(note).not.toContain("in the draw");
  });

  it("an unpriced row that is OVER says so", () => {
    expect(noteFor([DECIDED_UNPRICED_ROW])).toContain("This match is over");
  });

  it("the row still says the fact UX-P142 shipped it for: there is no number", () => {
    for (const rows of [[LIVE_UNPRICED_ROW], [UNPRICED[0]], [DECIDED_UNPRICED_ROW]]) {
      expect(noteFor(rows)).toContain("with no probability against it");
    }
  });

  it("every sentence the branch can produce passes the ruling-138/141/142 bans", () => {
    for (const state of [null, "upcoming", "in_progress"] as const) {
      for (const decided of [false, true]) {
        const note = matchDetailNote({
          coherent: false,
          decided,
          liveState: state,
          score: null,
          priced: false,
          sides: [{} as never, {} as never],
        })!;
        expect(findBannedCopy(note)).toEqual([]);
      }
    }
  });

  it("COUNTER-CASE: #2690's own suggested copy would have been rejected here", () => {
    // The issue proposes "We can't show a price for this match yet". It is a
    // ruling-138 violation, so the fix a reader writes straight from the issue
    // goes red — which is the reason this assertion exists rather than a note.
    const hits = findBannedCopy("We can't show a price for this match yet");
    expect(hits.map((h) => h.ban.id)).toContain("price-family");
  });
});

// ---------------------------------------------------------------------------
// CONTROLS — every one verified green on the parent
// ---------------------------------------------------------------------------

describe("CONTROL: nothing else about the row moved", () => {
  it("CONTROL: an UPCOMING unpriced row still reads 'in the draw'", () => {
    // The population UX-P142 was written for, and the one it was right about.
    // Verified green on the parent, which is why it is anchored on the bare
    // "in the draw" both arms print rather than on this diff's full clause.
    const note = noteFor([UNPRICED[0]]);
    expect(note).toContain("in the draw");
    expect(note).not.toContain("under way");
    expect(note).not.toContain("This match is over");
  });

  it("CONTROL: the row still refuses the incoherent branch's sentence", () => {
    expect(noteFor([LIVE_UNPRICED_ROW])).not.toContain("do not agree");
  });

  it("CONTROL: an incoherent PRICED row keeps its own sentence", () => {
    expect(
      matchDetailNote({
        coherent: false,
        decided: false,
        liveState: "in_progress",
        score: null,
        sides: [{} as never, {} as never],
      })
    ).toContain("do not agree");
  });

  it("CONTROL: priced rows are untouched — the fixture still renders 17 of them", () => {
    const html = renderRows(PRICED);
    expect(html).not.toContain("with no probability against it");
    expect(html).not.toContain("Nobody is quoting");
  });
});
