/**
 * #7734 — every entry in the accuracy page's corrections log is written for a
 * reader, and the page can prove it for entries that do not exist yet.
 *
 * THE SPECIMENS, photographed at 390px on production 2026-09-21 (#7734):
 *
 *     2026-07-09  Polymarket hockey sign-flip
 *     2026-07-09  DataGolf survivorship exclusion
 *     2026-07-09  Polymarket no-bid placeholder exclusion
 *     2026-07-09  Malformed-binary exclusion
 *     2026-07-09  Golf FIELD one-sided-ask placeholder exclusion
 *     2026-07-10  Multi-candidate probability normalization
 *     2026-07-11  Soccer 2-way (draw-omission) historical exclusion
 *     2026-07-12  Esports match-bundle exclusion
 *
 * The card's first sentence stakes the page's trustworthiness on the reader being
 * able to read the record; the title is the only thing it gives them (`description`
 * has not rendered since #4067 / CERT-2295). Eight of thirteen titles were our
 * changelog shorthand.
 *
 * ── WHY A CLOSURE TEST AND NOT EIGHT VALUE ASSERTIONS ───────────────────────
 *
 * Eight value assertions fix eight rows and nothing after them. This card has
 * been bitten three times by exactly that (#7353, #7363, #7599): the ninth row,
 * appended next month by the hand that appended these, renders as whatever it
 * was typed as.
 *
 * So the universe here is not a list in this file — it is
 * `precompute_calibration.py`'s own `CALIBRATION_CORRECTIONS`, read from source.
 * Every title in it must be one of two things and there is no third:
 *
 *   MAPPED — `CORRECTION_TITLE_OVERRIDES` has words for it, or
 *   READER-READY — it is on the short list below, each entry carrying the reason
 *   it needs none.
 *
 * A title that is neither reddens CI. That is the whole guard: the judgment
 * ("this one reads fine as written") stays a human's, but it has to be written
 * down before the row can ship.
 *
 * Read from the FILE, never from `/api/calibration`: `bainluck-heavy` runs behind
 * master (notice 48) and its artifact has been stamped 2026-09-15T11:16:10Z for
 * six days (#6868), so the served payload is a lagging view of the thing under
 * test. Reading the response instead is what left the exclusions map one block
 * short for five days (#7627).
 *
 * ── THE THREE WAYS THIS COULD BE VACUOUS, AND WHAT ANSWERS EACH ─────────────
 *
 *   1. THE EXTRACTION FINDS NOTHING. Every assertion here runs over whatever
 *      `producerCorrectionTitles()` returns, so an empty list is thirteen green
 *      tests over no rows. Answered by the arity + membership checks in the first
 *      block, and by the planted-title control at the bottom.
 *   2. THE ALLOWLIST SWALLOWS THE DEFECT. A future reader of this file can make
 *      any red go away by pasting the offending title into READER_READY_TITLES.
 *      Nothing can stop that, and nothing should — it is a reviewable line in a
 *      diff. What is checked is that the list stays HONEST: every entry on it
 *      must actually be in the producer (no dead entries accumulating cover), and
 *      no entry may be mapped as well, so the two sets cannot both claim a row.
 *   3. THE COPY IS JARGON TOO. A map entry proves someone typed a replacement,
 *      not that the replacement reads. The shorthand this issue is about is
 *      enumerated and banned from rendered output, so a "fix" that moved
 *      `Malformed-binary exclusion` into the map unchanged fails here.
 */

import { readFileSync } from "fs";
import { join } from "path";

import {
  CORRECTION_TITLE_OVERRIDES,
  carriesInternalReference,
  correctionTitle,
} from "@/lib/calibrationCorrections";

/** The producer's own source — the only honest answer to "which titles exist". */
const PAYLOAD_BUILDER = join(
  __dirname, "..", "..", "..", "backend", "app", "tasks", "precompute_calibration.py"
);

/**
 * Every `title` in the `CALIBRATION_CORRECTIONS` list literal.
 *
 * Deliberately the same extraction as #7729's suite rather than a shared helper:
 * these two suites are each other's control. If one day they disagree about what
 * the producer publishes, that disagreement should surface as a red test, not be
 * normalised away by a helper both of them trust.
 */
function producerCorrectionTitles(): string[] {
  const src = readFileSync(PAYLOAD_BUILDER, "utf8");
  const start = src.indexOf("CALIBRATION_CORRECTIONS = [");
  if (start === -1) {
    throw new Error(
      `CALIBRATION_CORRECTIONS list not found in ${PAYLOAD_BUILDER} — the producer was ` +
        "renamed or restructured, and this suite's universe is no longer derived from it."
    );
  }
  const end = src.indexOf("\n]", start);
  const literal = src.slice(start, end === -1 ? undefined : end);
  return [...literal.matchAll(/^ {8}"title": "(.*?)",$/gm)].map(m => m[1].replace(/\\"/g, '"'));
}

/**
 * Producer titles that already read as a reader's sentence, with the reason.
 *
 * This list is a judgment, recorded. It is short on purpose: the September
 * entries were written after this page became public and show the target voice,
 * and "Premature golf resolutions" is the one July title that names a thing in
 * words rather than a filter in ours.
 */
const READER_READY_TITLES: ReadonlyArray<readonly [string, string]> = [
  [
    "Premature golf resolutions",
    "Plain subject + plain verb; 'resolution' is the page's own word for a settled result.",
  ],
  [
    "Prices nobody could have traded at",
    "Written for a reader when the writer bar shipped (2026-09-12).",
  ],
  [
    "A price ladder is one forecast, not forty",
    "Written for a reader when the ladder collapse shipped (2026-09-12).",
  ],
  [
    "The one-question markets we were throwing away are now scored",
    "Written for a reader, and deliberately a whole sentence (D112 — the title is the whole disclosure on web).",
  ],
];

const READER_READY = new Set(READER_READY_TITLES.map(([title]) => title));

/**
 * The shorthand this issue is about, as the producer wrote it.
 *
 * Each fragment is lifted from a specimen title above, so this is not a general
 * "does it sound technical" oracle — it is the set of phrases a reader was
 * actually handed on 2026-09-21. A rendered title containing one of them has not
 * been fixed, whatever else changed around it.
 */
const SHORTHAND = [
  "sign-flip",
  "survivorship",
  "no-bid",
  "malformed",
  "one-sided",
  "normalization",
  "draw-omission",
  "match-bundle",
  "discriminator",
  "placeholder",
  "exclusion",
  "mutually-exclusive",
  "midpoint",
];

describe("the producer's list is what this suite is closed over", () => {
  it("extracts the thirteen titles, including the eight specimens", () => {
    const titles = producerCorrectionTitles();
    // No exact count: the next correction appended is a legitimate change and
    // must not redden this. What must hold is that the extraction found the list
    // and found the rows this issue is about in it.
    expect(titles.length).toBeGreaterThanOrEqual(13);
    expect(new Set(titles).size).toBe(titles.length);
    for (const specimen of [
      "Polymarket hockey sign-flip",
      "DataGolf survivorship exclusion",
      "Polymarket no-bid placeholder exclusion",
      "Malformed-binary exclusion",
      "Golf FIELD one-sided-ask placeholder exclusion",
      "Multi-candidate probability normalization",
      "Soccer 2-way (draw-omission) historical exclusion",
      "Esports match-bundle exclusion",
    ]) {
      expect(titles).toContain(specimen);
    }
  });
});

describe("every producer title is either mapped or declared reader-ready", () => {
  it("has no third case", () => {
    const unaccounted = producerCorrectionTitles().filter(
      title => CORRECTION_TITLE_OVERRIDES[title] === undefined && !READER_READY.has(title)
    );
    // Reported as the list, not as a count: a red here should name the row to
    // write words for without anyone re-running the test to find out which.
    expect(unaccounted).toEqual([]);
  });

  it("and the two sets never both claim a row", () => {
    for (const [title] of READER_READY_TITLES) {
      expect(CORRECTION_TITLE_OVERRIDES[title]).toBeUndefined();
    }
  });

  it("the reader-ready list carries no dead entries", () => {
    // Without this, a title reworded upstream leaves its allowlist line behind as
    // standing cover for a string that no longer exists — the same staleness the
    // map's closure test exists to catch, one list over.
    const titles = new Set(producerCorrectionTitles());
    for (const [title] of READER_READY_TITLES) {
      expect({ title, inProducer: titles.has(title) }).toEqual({ title, inProducer: true });
    }
  });

  it("every map key is a title the producer actually publishes", () => {
    // The same staleness in the other direction: an override keyed on a string
    // nobody sends is words the page will never print, and it reads in a diff as
    // a row that has been handled.
    const titles = new Set(producerCorrectionTitles());
    for (const key of Object.keys(CORRECTION_TITLE_OVERRIDES)) {
      expect({ key, inProducer: titles.has(key) }).toEqual({ key, inProducer: true });
    }
  });
});

describe("what the eight specimens now say", () => {
  // Pinned by value. "Is not the old string" is also satisfied by the empty
  // string, by a truncation, and by a second piece of shorthand.
  const EXPECTED: ReadonlyArray<readonly [string, string]> = [
    [
      "Polymarket hockey sign-flip",
      "Hockey player props (Polymarket): over and under prices were the wrong way round, now re-scored",
    ],
    [
      "DataGolf survivorship exclusion",
      "Golf: players who withdrew or never teed off are no longer scored",
    ],
    [
      "Polymarket no-bid placeholder exclusion",
      "Polymarket prices with no offer behind them, parked near 50%, are no longer scored",
    ],
    [
      "Malformed-binary exclusion",
      "Yes-or-no markets that settled with no winner, or with two, are no longer scored",
    ],
    [
      "Golf FIELD one-sided-ask placeholder exclusion",
      "Golf: prices that put two players in one event both above 80% to win are no longer scored",
    ],
    [
      "Multi-candidate probability normalization",
      "Markets with several candidates now add up to 100%, instead of well over it",
    ],
    [
      "Soccer 2-way (draw-omission) historical exclusion",
      "Soccer: older win-or-lose prices left the draw out, so they are no longer scored",
    ],
    [
      "Esports match-bundle exclusion",
      "Esports markets that pack a whole match into one question are no longer scored",
    ],
  ];

  it.each(EXPECTED)("renders the page's words for %j", (producer, rendered) => {
    expect(correctionTitle(producer)).toBe(rendered);
    // The positive half of notice 50's split: the row MOVED. A map entry that
    // accidentally repeated the producer's string would satisfy the line above
    // only if the copy were identical, and this says so out loud.
    expect(correctionTitle(producer)).not.toBe(producer);
  });
});

describe("the copy is not shorthand wearing a map entry", () => {
  it("no rendered producer title carries any of the specimens' shorthand", () => {
    for (const title of producerCorrectionTitles()) {
      const rendered = correctionTitle(title).toLowerCase();
      const found = SHORTHAND.filter(fragment => rendered.includes(fragment));
      expect({ title, found }).toEqual({ title, found: [] });
    }
  });

  it("nor a tracker id, which is #7729's floor holding under the wider map", () => {
    for (const title of producerCorrectionTitles()) {
      expect(carriesInternalReference(correctionTitle(title))).toBe(false);
    }
  });

  it("and no rendered title is empty or a bare fragment", () => {
    // The failure mode a ban list invites: satisfying it by deleting words.
    for (const title of producerCorrectionTitles()) {
      const rendered = correctionTitle(title);
      expect(rendered.length).toBeGreaterThan(20);
      expect(rendered.trim()).toBe(rendered);
    }
  });
});

describe("the closure is not vacuous", () => {
  it("a producer title in neither set would be reported", () => {
    // The control for the whole file. Every test above runs over the producer's
    // real list, which is currently clean — so each of them passes both when the
    // guard works and when it has silently stopped looking. This exercises the
    // membership rule directly on a title that is in neither set.
    const planted = "Kalshi bucket-boundary re-key (Queue #901)";
    expect(CORRECTION_TITLE_OVERRIDES[planted]).toBeUndefined();
    expect(READER_READY.has(planted)).toBe(false);
    const unaccounted = [...producerCorrectionTitles(), planted].filter(
      title => CORRECTION_TITLE_OVERRIDES[title] === undefined && !READER_READY.has(title)
    );
    expect(unaccounted).toEqual([planted]);
  });

  it("and the shorthand detector fires on the strings it was built from", () => {
    // The other half: SHORTHAND is only worth anything if it matches the titles
    // this issue photographed. Asserted against the producer's raw strings, which
    // are what a reader saw before this fix.
    const raw = "Malformed-binary exclusion";
    expect(SHORTHAND.some(f => raw.toLowerCase().includes(f))).toBe(true);
    expect(SHORTHAND.some(f => "Polymarket hockey sign-flip".toLowerCase().includes(f))).toBe(true);
  });
});
