/**
 * #7729 — the accuracy page's data corrections log stops quoting our own
 * work-tracking id at a reader.
 *
 * THE SPECIMEN, photographed at 390px on production 2026-09-21:
 *
 *     2026-07-13
 *     Kalshi player-prop threshold exclusion — corrected discriminator (Queue #186)
 *
 * `Queue #186` is this repo's handoff numbering. It resolves to nothing a reader
 * can open, and it is the only one of the thirteen titles that carries one.
 *
 * ── WHAT THIS SUITE HAS TO PROVE, AND THE TWO WAYS IT COULD BE VACUOUS ──────
 *
 * The easy version of this test asserts `correctionTitle(SPECIMEN)` is the new
 * string and stops. That passes against a `correctionTitle` that is a lookup and
 * nothing else, and it is blind to both real failure modes:
 *
 *   1. THE MAP GOES STALE. The override is keyed on the producer's exact string.
 *      Reword the title upstream by one character and the key stops matching —
 *      silently, in a HEAVY task whose artifact is currently six days old, so the
 *      served payload cannot even show you. The closure test below therefore
 *      reads the titles out of `backend/app/tasks/precompute_calibration.py`
 *      itself and requires the page to have an answer for every one of them.
 *      Reading `api.bainluck.com/api/calibration` instead is what put the
 *      exclusions map one block short for five days (#7627) — `bainluck-heavy`
 *      runs behind master (notice 48) and the response is a lagging view of that
 *      file. Not soft-guarded: a missing backend file must turn this red and say
 *      which path it wanted, because a soft read produces a green closure test
 *      over an empty universe.
 *
 *   2. THE FLOOR EATS GOOD TITLES. `withheldInternalReference` cuts a trailing
 *      fragment, so its risk is the opposite of the map's: a title with a price,
 *      a year or a count in it must come through untouched. Twelve live controls
 *      below are asserted byte-identical, and four adversarial titles carrying
 *      reader numbers are asserted unchanged.
 *
 * Neither half is decorative. The map with no closure test is the hardcoded
 * literal this card has already been bitten by three times (#7353, #7363,
 * #7599); the floor with no identity controls is a normaliser nobody measured.
 */

import { readFileSync } from "fs";
import { join } from "path";

import {
  CORRECTION_TITLE_OVERRIDES,
  carriesInternalReference,
  correctionTitle,
  correctionsNeedingCopy,
  withheldInternalReference,
} from "@/lib/calibrationCorrections";

/** The producer's own source — the only honest answer to "which titles exist". */
const PAYLOAD_BUILDER = join(
  __dirname, "..", "..", "..", "backend", "app", "tasks", "precompute_calibration.py"
);

/**
 * Every `title` in the `CALIBRATION_CORRECTIONS` list literal.
 *
 * Sliced to that literal first rather than grepping the whole file: the module
 * is 7,000 lines and a `"title":` key elsewhere in it would quietly widen the
 * universe this test calls closed. The slice ends at the first column-0 `]`,
 * which is the literal's own terminator.
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
  return [...literal.matchAll(/^ {8}"title": "(.*?)",$/gm)].map(m =>
    // The producer writes these as plain Python strings with real em-dashes; the
    // only escape that appears is the quote. Unescaping nothing else on purpose —
    // an escape shape this does not know about should look wrong here rather than
    // be silently normalised into a key that then fails to match.
    m[1].replace(/\\"/g, '"')
  );
}

/**
 * One correction row.
 *
 * `description` is required by `CalibrationCorrection` and is deliberately
 * empty: this suite is about the title, and the page has not rendered the
 * description since #4067 / CERT-2295. Supplying it once here rather than at
 * seven call sites keeps the fixtures reading as the thing under test.
 */
function row(title: string, date = "2026-01-01") {
  return { date, title, rows: null, description: "" };
}

/** The one title the fix is about, transcribed from the producer. */
const SPECIMEN =
  "Kalshi player-prop threshold exclusion — corrected discriminator (Queue #186)";

/**
 * The other twelve, exactly as they render today.
 *
 * These are the change's blast radius. #7729 moves one string; if it moves a
 * thirteenth, that is a regression and it is invisible from the specimen
 * assertion alone.
 */
const UNTOUCHED_TITLES = [
  "Polymarket hockey sign-flip",
  "Premature golf resolutions",
  "DataGolf survivorship exclusion",
  "Polymarket no-bid placeholder exclusion",
  "Malformed-binary exclusion",
  "Golf FIELD one-sided-ask placeholder exclusion",
  "Multi-candidate probability normalization",
  "Soccer 2-way (draw-omission) historical exclusion",
  "Esports match-bundle exclusion",
  "Prices nobody could have traded at",
  "A price ladder is one forecast, not forty",
  "The one-question markets we were throwing away are now scored",
];

describe("the specimen: what a reader sees on 2026-07-13", () => {
  it("no longer carries our queue id", () => {
    const rendered = correctionTitle(SPECIMEN);
    expect(rendered).not.toMatch(/Queue/);
    expect(rendered).not.toMatch(/#\d/);
    expect(rendered).not.toMatch(/186/);
  });

  it("no longer says 'discriminator'", () => {
    // The second half of the defect. A fix that cut the parenthetical and left
    // the jargon would pass the test above and still be jargon in the one slot
    // the page controls (D102).
    expect(correctionTitle(SPECIMEN).toLowerCase()).not.toContain("discriminator");
  });

  it("still says what was corrected, in reader words", () => {
    // Pinned by VALUE, not by a shape test: "does not contain Queue" is also
    // satisfied by the empty string, by the date alone, and by dropping the row.
    expect(correctionTitle(SPECIMEN)).toBe(
      "Player-prop prices (Kalshi): corrected the test for which prices to drop"
    );
  });

  it("is the map's words and not the floor's", () => {
    // The distinction this suite exists to keep: running the floor on the
    // specimen yields "…— corrected discriminator", which is a leak stopped and
    // a reader still unserved. If the override is ever deleted, this fails and
    // the "no discriminator" test above fails with it.
    expect(withheldInternalReference(SPECIMEN)).toBe(
      "Kalshi player-prop threshold exclusion — corrected discriminator"
    );
    expect(correctionTitle(SPECIMEN)).not.toBe(withheldInternalReference(SPECIMEN));
  });
});

describe("the other twelve are byte-identical", () => {
  it.each(UNTOUCHED_TITLES)("passes through unchanged: %j", (title) => {
    expect(correctionTitle(title)).toBe(title);
  });

  it("and none of them is silently running on an override", () => {
    // An override for a title that needs none is a second place the page's copy
    // can drift from the producer's, with nothing pointing at it.
    for (const title of UNTOUCHED_TITLES) {
      expect(CORRECTION_TITLE_OVERRIDES[title]).toBeUndefined();
    }
  });
});

describe("closure against the producer's own source", () => {
  it("reads all thirteen titles out of precompute_calibration.py", () => {
    const titles = producerCorrectionTitles();
    // A count assertion would go stale the next time a correction is appended,
    // which is the wrong kind of red. What must hold is that the extraction
    // found the list and found the specimen in it — if the regex silently
    // matched nothing, every closure assertion below would pass vacuously.
    expect(titles.length).toBeGreaterThanOrEqual(13);
    expect(titles).toContain(SPECIMEN);
    expect(new Set(titles).size).toBe(titles.length);
  });

  it("every producer title the page cannot name is zero", () => {
    const rows = producerCorrectionTitles().map((title, i) =>
      row(title, `2026-01-${String((i % 28) + 1).padStart(2, "0")}`)
    );
    expect(correctionsNeedingCopy(rows)).toBe(0);
  });

  it("and no producer title renders a tracker id", () => {
    for (const title of producerCorrectionTitles()) {
      const rendered = correctionTitle(title);
      expect({ title, rendered, leaks: carriesInternalReference(rendered) }).toEqual({
        title,
        rendered,
        leaks: false,
      });
    }
  });

  it("the closure is not vacuous — a planted producer title would fail it", () => {
    // The control the three tests above need. They all run over whatever
    // `producerCorrectionTitles()` returns, so a broken extraction makes them
    // green. This asserts the detector fires on the shape they are looking for.
    const planted = [row("Something we fixed (CERT-9001)", "2026-10-01")];
    expect(correctionsNeedingCopy(planted)).toBe(1);
  });
});

describe("the floor, and what it must not eat", () => {
  it("withholds a trailing tracker parenthetical", () => {
    expect(correctionTitle("Some correction (Queue #999)")).toBe("Some correction");
    expect(correctionTitle("Some correction (CERT-2295)")).toBe("Some correction");
    expect(correctionTitle("Some correction (see #4067)")).toBe("Some correction");
  });

  it("withholds a trailing tracker clause after an em-dash", () => {
    expect(correctionTitle("Some correction — per L2-74")).toBe("Some correction");
  });

  it("withholds, it does not rewrite", () => {
    // The whole difference between this and a normaliser. What survives is a
    // prefix of the producer's own string, character for character.
    const rendered = correctionTitle("Some correction (Queue #999)");
    expect("Some correction (Queue #999)".startsWith(rendered)).toBe(true);
  });

  it("leaves a reader's numbers alone", () => {
    // The floor's own risk. Each of these carries a number that is content, not
    // a tracker, and a fix that ate one would be a worse defect than #7729.
    const readerNumbers = [
      "Two golfers both priced above 80% to win the same event",
      "Prices we captured in 2026 and never re-read",
      "A price ladder is one forecast, not forty",
      "Soccer 2-way (draw-omission) historical exclusion",
    ];
    for (const title of readerNumbers) {
      expect(correctionTitle(title)).toBe(title);
      expect(carriesInternalReference(title)).toBe(false);
    }
  });

  it("does not cut a tracker id out of the middle of a sentence", () => {
    // Cutting mid-sentence would change what the sentence says, so the floor
    // declines and the row is counted instead. The honest answer is "the page
    // needs words for this", not a mangled one.
    const midSentence = "Queue #500 changed how we price a draw";
    expect(correctionTitle(midSentence)).toBe(midSentence);
    expect(correctionsNeedingCopy([row(midSentence, "2026-10-02")])).toBe(1);
  });

  it("never returns empty, even for a title that is only a reference", () => {
    // A row with no title reads as a dateless, nameless entry in a log the page
    // calls dated and complete. Keeping the original is the lesser wrong, and it
    // is counted so it is not silent.
    const onlyRef = "(Queue #777)";
    expect(correctionTitle(onlyRef)).toBe(onlyRef);
    expect(correctionsNeedingCopy([row(onlyRef, "2026-10-03")])).toBe(1);
  });
});

describe("the counter the page publishes", () => {
  it("is zero on the live thirteen", () => {
    const live = [SPECIMEN, ...UNTOUCHED_TITLES].map((title, i) =>
      row(title, `2026-02-${String(i + 1).padStart(2, "0")}`)
    );
    expect(correctionsNeedingCopy(live)).toBe(0);
  });

  it("does not count a row the map has words for", () => {
    expect(correctionsNeedingCopy([row(SPECIMEN, "2026-07-13")])).toBe(0);
  });

  it("survives an absent, empty or title-less payload", () => {
    expect(correctionsNeedingCopy(null)).toBe(0);
    expect(correctionsNeedingCopy(undefined)).toBe(0);
    expect(correctionsNeedingCopy([])).toBe(0);
    expect(correctionsNeedingCopy([row("", "2026-10-04")])).toBe(0);
    expect(correctionTitle(null)).toBe("");
    expect(correctionTitle(undefined)).toBe("");
  });
});
