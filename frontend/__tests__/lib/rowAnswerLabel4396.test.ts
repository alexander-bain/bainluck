/**
 * #4396 — the decision behind "which answer is this percentage for?".
 *
 * The render arm lives in `__tests__/components/compactRowNamesItsAnswer4396.test.tsx`;
 * this file is the pure decision and its edges. Every specimen below is a row
 * `GET /api/feed?limit=250` served on 2026-09-09 (edition `b433c96f31941ab7`),
 * banked at `__tests__/fixtures/compactRowAnswer4396.json`.
 */

import { rowAnswerLabel, captionNames } from "@/lib/discover/rowAnswerLabel";
import fixture from "../fixtures/compactRowAnswer4396.json";

interface CensusRow {
  question: string;
  hero_outcome: string | null;
  caption: string;
}

const CENSUS = fixture.compact_row_census as CensusRow[];

describe("#4396 — rowAnswerLabel names the answer only where the caption did not", () => {
  it("names the outcome when the caption is a movement line that never says it", () => {
    // The headline specimen: 93% is the probability of ZERO cuts.
    expect(rowAnswerLabel({ name: "0 (0 bps)", probability: 0.9275 }, "Well off its opening price")).toBe("0 (0 bps)");
  });

  it("names the outcome when there is no caption at all", () => {
    expect(rowAnswerLabel({ name: "3", probability: 0.25 }, "")).toBe("3");
    expect(rowAnswerLabel({ name: "Brazil", probability: 0.22 }, null)).toBe("Brazil");
  });

  it("stays silent when the caption already names the outcome", () => {
    expect(rowAnswerLabel({ name: "Hike 25bps", probability: 0.555 }, "Hike 25bps leads at 56%")).toBeNull();
    expect(rowAnswerLabel({ name: "Jon Ossoff", probability: 0.17 }, "New favorite: Jon Ossoff (17%)")).toBeNull();
    // Case and whitespace are not a difference the reader can see.
    expect(rowAnswerLabel({ name: "The  Odyssey", probability: 0.41 }, "the odyssey leads at 41%")).toBeNull();
  });

  it("stays silent on a bare affirmative, because the question already states it", () => {
    expect(rowAnswerLabel({ name: "Yes", probability: 0.12 }, "")).toBeNull();
    expect(rowAnswerLabel({ name: "yes", probability: 0.12 }, "Well off its opening price")).toBeNull();
  });

  it("DOES name a hero still reading 'No' — heroOutcome only leaves one there when the affirmative had no price", () => {
    expect(rowAnswerLabel({ name: "No", probability: 0.88 }, "")).toBe("No");
    // And a qualified yes is an answer, not the question restated.
    expect(rowAnswerLabel({ name: "Yes, before June", probability: 0.3 }, "")).toBe("Yes, before June");
  });

  it("has nothing to say without a hero or a name", () => {
    expect(rowAnswerLabel(null, "Well off its opening price")).toBeNull();
    expect(rowAnswerLabel({ name: "   ", probability: 0.4 }, "")).toBeNull();
  });

  describe("captionNames is boundary-checked, because quantity answers are one character", () => {
    it("does not read the answer '3' out of an unrelated number in the caption", () => {
      expect(captionNames("Well off its 3-month low", "3")).toBe(false);
      expect(captionNames("Up 13 points since Monday", "3")).toBe(false);
      // A price in the caption is not the caption naming the answer.
      expect(captionNames("Hike 25bps leads at 25%", "25")).toBe(false);
    });

    it("still finds a short answer the caption really does state", () => {
      expect(captionNames("3 leads at 25%", "3")).toBe(true);
      expect(captionNames("New favorite: 3 (25%)", "3")).toBe(true);
    });

    it("finds an answer whose own edges are punctuation", () => {
      expect(captionNames("0 (0 bps) leads at 93%", "0 (0 bps)")).toBe(true);
      expect(captionNames("December 31 leads at 41%", "December 31")).toBe(true);
    });
  });

  describe("the production census", () => {
    it("is the 22 rows page one served, not a hand-written sample", () => {
      // A fixture that shrank to the convenient rows would make every count
      // below true and meaningless.
      expect(CENSUS).toHaveLength(22);
      expect(fixture.edition).toBe("b433c96f31941ab7");
    });

    it("labels exactly the four rows whose answer was invisible, and no others", () => {
      const labelled = CENSUS.filter((r) => rowAnswerLabel({ name: r.hero_outcome }, r.caption) !== null).map(
        (r) => r.question,
      );

      expect(labelled.sort()).toEqual(
        [
          "FIFA Women's World Cup 2027 Winner",
          "How many Fed rate cuts in 2026?",
          "How many dissent at the October Fed meeting?",
          "Russia x Ukraine ceasefire agreement by...?",
        ].sort(),
      );
    });

    it("CONTROL — the 15 rows whose caption already names the answer gain nothing", () => {
      // Without this arm, "label everything" passes the arm above's spirit and
      // puts "The Odyssey" on its row twice.
      const alreadyNamed = CENSUS.filter((r) => r.hero_outcome && captionNames(r.caption, r.hero_outcome));

      expect(alreadyNamed).toHaveLength(15);
      for (const row of alreadyNamed) {
        expect(rowAnswerLabel({ name: row.hero_outcome }, row.caption)).toBeNull();
      }
    });

    it("CONTROL — the census really did contain orphans, so the arms above are not vacuous", () => {
      // If page one ever stops serving an unlabelled row this reds, and the
      // fixture is a dated capture that should then be re-cut — a suppression
      // rule proved on a population with nothing to suppress proves nothing.
      const orphans = CENSUS.filter((r) => r.hero_outcome && !captionNames(r.caption, r.hero_outcome));
      expect(orphans.length).toBe(7);
    });
  });
});
