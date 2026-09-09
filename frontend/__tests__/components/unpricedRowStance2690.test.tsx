/**
 * UX-1042 / #2690 — AN UNPRICED HUB ROW STATES ITS OWN IGNORANCE, NOT THE
 * WORLD'S.
 *
 * ⚠️ SUPERSEDED BY #4332 (notice 34): the sentence this file was written to
 * CORRECT has since been REMOVED. The assertions below are re-aimed rather than
 * deleted — the fixture work and the two specimens (a LIVE unpriced row, a
 * DECIDED one) are the hardest part of this file and #4332's own guard has
 * neither. Everything above the "THE SHIP" divider is the original record and
 * is still true; read it as history, and see `matchList.ts`'s tombstone for why
 * three rounds of making the sentence more accurate never saved it.
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
import { buildMatchList } from "@/lib/matchList";
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
 * The notes on a row, read off the render rather than the library.
 *
 * ANCHORED ON `data-testid="match-detail-note"`, which predates all of this, so
 * every arm can run on the parent too. An extractor keyed on the WORDING makes
 * every test that uses it arm-dependent — including the ones labelled CONTROL,
 * which then go red for a reason that has nothing to do with the claim they
 * make.
 *
 * Returns the LIST. The previous version threw unless it found exactly one
 * note, which was right while every row had one; under #4332 an unpriced row
 * has none, and "there is no note" is now the assertion rather than the error
 * case. Callers that expect exactly one still say so, explicitly.
 */
function notesFor(rows: SlateMatch[]): string[] {
  return [...renderRows(rows).matchAll(/data-testid="match-detail-note"[^>]*>([^<]*)</g)].map(
    (m) => m[1].replace(/\s+/g, " ").trim()
  );
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
// THE SHIP — SUPERSEDED BY #4332, AND THIS IS WHAT REPLACED IT
// ---------------------------------------------------------------------------

/**
 * #2690's ship was a sentence made ACCURATE. #4332's is the same sentence
 * REMOVED, under notice 34: a row may describe the match, never our pipeline.
 *
 * Both were right in their turn, and the pair is worth keeping as one record —
 * the paragraph was corrected twice (UX-P142 → #2690 → the venue-refusal
 * clause) and every correction left it a paragraph about our coverage on a
 * reader's screen. Accuracy was never the axis it failed on.
 *
 * The assertions below are re-aimed, not deleted, because this file owns two
 * specimens #4332's own guard does not have: a LIVE unpriced row (the authority
 * overlay) and a DECIDED one. Those were exactly the states #2690 proved the
 * sentence could not describe, so they are exactly the states most worth
 * checking now say nothing at all.
 */
describe("an unpriced row says nothing about our pipeline, in every state", () => {
  it("THE LIVE ROW — #2690's specimen — renders no note at all", () => {
    expect(notesFor([LIVE_UNPRICED_ROW])).toEqual([]);
  });

  it("THE DECIDED ROW renders no note either", () => {
    expect(notesFor([DECIDED_UNPRICED_ROW])).toEqual([]);
  });

  it("THE UPCOMING ROW — the population UX-P142 was RIGHT about — is silent too", () => {
    // The sentence was true of this row for its whole life. It still goes:
    // notice 34 bans the shape, not the inaccuracy.
    expect(notesFor([UNPRICED[0]])).toEqual([]);
  });

  it("no arm leaks any clause of the retired paragraph", () => {
    for (const rows of [[LIVE_UNPRICED_ROW], [DECIDED_UNPRICED_ROW], [UNPRICED[0]]]) {
      const html = renderRows(rows);
      for (const phrase of [
        "Nobody is quoting",
        "no probability against it",
        "not a statement about whether a venue listed one",
        "This match is under way",
        "This match is over",
      ]) {
        expect(html).not.toContain(phrase);
      }
    }
  });

  it("every state's row is still FULLY DRAWN, and still answers", () => {
    // Without this the whole block above passes on a component that renders
    // nothing — the empty-render trap that makes a `not.toContain` suite lie.
    for (const rows of [[LIVE_UNPRICED_ROW], [DECIDED_UNPRICED_ROW], [UNPRICED[0]]]) {
      const html = renderRows(rows);
      expect(html.length).toBeGreaterThan(500);
      expect(html).toContain("No probability yet");
    }
  });
});

// ---------------------------------------------------------------------------
// CONTROLS — every one verified green on the parent
// ---------------------------------------------------------------------------

describe("CONTROL: nothing else about the row moved", () => {
  it("CONTROL: priced rows are untouched — the fixture still renders 17 of them", () => {
    const html = renderRows(PRICED);
    expect(html).not.toContain("with no probability against it");
    expect(html).not.toContain("Nobody is quoting");
    expect(PRICED).toHaveLength(17);
  });

  it("CONTROL: a priced row that EARNS a sentence still prints one", () => {
    // The sweep removed two branches, not the feature. If `matchDetailNote`
    // had been gutted, every assertion above would still pass and this one
    // would not.
    const withOpening = {
      ...PRICED[0],
      sides: [
        { ...(PRICED[0].sides?.[0] as object), probability: 0.72, opening_probability: 0.68 },
        { ...(PRICED[0].sides?.[1] as object), probability: 0.28, opening_probability: 0.32 },
      ],
    } as unknown as SlateMatch;
    const notes = notesFor([withOpening]);
    expect(notes).toHaveLength(1);
    expect(notes[0]).toMatch(/opened at \d+%/);
  });

  it("COUNTER-CASE: #2690's own suggested copy would still have been rejected", () => {
    // The issue proposed "We can't show a price for this match yet" — a
    // ruling-138 violation. Kept because the ban rail is what stopped the
    // obvious fix, and it must keep working now the branch is gone.
    const hits = findBannedCopy("We can't show a price for this match yet");
    expect(hits.map((h) => h.ban.id)).toContain("price-family");
  });
});
