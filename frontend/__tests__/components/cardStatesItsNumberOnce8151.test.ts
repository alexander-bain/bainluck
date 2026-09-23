import {
  feedContextSnippet,
  stripCardTitleHead,
  stripHeroProbabilityRestatement,
} from "../../components/discover/utils";

/**
 * #8151 — a Discover card stops printing its own number twice.
 *
 * Production 2026-09-23 01:5xZ, 390px, backend `a14f981c`. Whole-card renders in
 * `artifacts-discover/d426/hero-03.png` and `hero-06.png`:
 *
 *     HEALTH · Resolves Dec 31, 2026
 *     68%                                      <- hero, 48pt
 *     Will there be at least 5000 measles cases in the U.S. in 2026?
 *     68% chance, up 53 points since Apr 29    <- caption
 *
 *     ECONOMICS · Closes Sep 25
 *     18%   ↓ 52.0 pts / 24H
 *     Will Netflix, Inc. (NFLX) hit (HIGH) $75 Week of September 21 2026?
 *     Down 52 points today — now 18% chance
 *
 * `binary_card_copy` builds `answer = f"{pct}% chance"` and glues it onto four of
 * its five rungs. #4056 deleted the fifth — where `answer` was the whole caption
 * — recording that "a bare '42% chance' above a 42% hero IS the empty case,
 * wearing text". This is the clause form it left standing: 28 of 89 served
 * futures captions, 5 of the 7 hero cards on page one.
 *
 * ** EVERY SPECIMEN BELOW IS A SERVED PAYLOAD **, replayed through the REAL
 * chain with the REAL hero string, because the thing under test is a
 * three-subtraction composition and a direct call to the helper would not
 * exercise it. `artifacts-discover/d426/feed-200.json` is the capture.
 */

type Payload = {
  headline?: string | null;
  reason?: string | null;
  context_summary?: string | null;
  name?: string;
  hook?: string | null;
};

const card = ({
  headline = null,
  reason = null,
  context_summary = null,
  name = "Will there be at least 5000 measles cases in the U.S. in 2026?",
  hook = null,
}: Payload = {}) =>
  ({
    type: "futures" as const,
    headline,
    reason,
    context_summary,
    data: { name, hook_description: hook },
  }) as any;

/** The eyebrow and hero these cards actually render, verbatim. */
const EYEBROW = "Resolves Dec 31, 2026";

describe("#8151 the caption stops restating the hero the card prints above it", () => {
  test("leading shape: the production measles card", () => {
    const item = card({
      context_summary: "68% chance, up 53 points since Apr 29",
      reason:
        "Will there be at least 5000 measles cases in the U.S....: 68% chance, up 53 points since Apr 29",
    });
    expect(feedContextSnippet(item, EYEBROW, "68%")).toBe(
      "Up 53 points since Apr 29",
    );
  });

  test("trailing shape: the production NFLX card", () => {
    const item = card({
      name: "Will Netflix, Inc. (NFLX) hit (HIGH) $75 Week of September 21 2026?",
      context_summary: "Down 52 points today — now 18% chance",
      reason:
        "Will Netflix, Inc. (NFLX) hit (HIGH) $75 Week of...: Down 52 points today — now 18% chance",
    });
    expect(feedContextSnippet(item, "Closes Sep 25", "18%")).toBe(
      "Down 52 points today",
    );
  });

  test("ANTI-VACUITY: the same two payloads are UNCHANGED without the hero argument", () => {
    // If the strip fired on the payload rather than on the caller's gate, these
    // two would already read "Up 53 points…" and the assertions above would
    // pass against a component that never passed anything. They are also the
    // literal BEFORE — what the two non-hero roots keep.
    const measles = card({
      context_summary: "68% chance, up 53 points since Apr 29",
    });
    const nflx = card({
      name: "Will Netflix, Inc. (NFLX) hit (HIGH) $75 Week of September 21 2026?",
      context_summary: "Down 52 points today — now 18% chance",
    });
    expect(feedContextSnippet(measles, EYEBROW)).toBe(
      "68% chance, up 53 points since Apr 29",
    );
    expect(feedContextSnippet(nflx, "Closes Sep 25")).toBe(
      "Down 52 points today — now 18% chance",
    );
  });
});

describe("#8151 the controls — what must NOT move", () => {
  test("🔴 a caption that NAMES ITS SUBJECT keeps its percent (the #8127 trap)", () => {
    // Production page one, same read: a `66%` hero over "Which party will win
    // the Senate in 2026?". The hero is a bare number with no subject, so
    // "Democratic Party" is the only thing saying WHICH side owns the 66.
    // Stripping "at 66%" here leaves "Democratic Party leads" — precisely the
    // defect #8127 shipped to remove. This is the whole reason the expressions
    // are anchored on the literal clause `"{hero} chance"` and not on a percent.
    const item = card({
      name: "Which party will win the Senate in 2026?",
      context_summary: "Democratic Party leads at 66%",
    });
    expect(feedContextSnippet(item, "Resolves Jan 4, 2027", "66%")).toBe(
      "Democratic Party leads at 66%",
    );
  });

  test("a caption stating a DIFFERENT percent than the hero is left alone", () => {
    // Two numbers on one card is a defect to report, never one to hide by
    // deleting the evidence. Also the `<1%` / `>99%` hero case by construction:
    // `_display_pct` returns an int, so the caption says "0% chance" under a
    // "<1%" hero and the strings do not match.
    const item = card({ context_summary: "41% chance, up 6 points since May 24" });
    expect(feedContextSnippet(item, EYEBROW, "68%")).toBe(
      "41% chance, up 6 points since May 24",
    );
    expect(stripHeroProbabilityRestatement("0% chance", "<1%")).toBe("0% chance");
  });

  test("#6470's deadline level clause is out of scope, not half-eaten", () => {
    // "60% chance by December 31, 2026" — the remainder would be a bare
    // "By December 31, 2026", and that date is the eyebrow's field (#7872), not
    // this one. 0 of 89 carried the shape on the capture; it is excluded on
    // purpose, so a later reader does not "finish" it by widening the regex.
    const item = card({ context_summary: "60% chance by December 31, 2026" });
    expect(feedContextSnippet(item, EYEBROW, "60%")).toBe(
      "60% chance by December 31, 2026",
    );
  });

  test("a caller that renders no hero keeps every word", () => {
    // The heatmap and leaderboard roots, and `FuturesCompactRow`: for them the
    // caption is the reader's ONLY statement of the number.
    const item = card({ context_summary: "Down 52 points today — now 18% chance" });
    expect(feedContextSnippet(item, EYEBROW, null)).toBe(
      "Down 52 points today — now 18% chance",
    );
    expect(feedContextSnippet(item, EYEBROW, "")).toBe(
      "Down 52 points today — now 18% chance",
    );
  });
});

describe("#8151 when the restatement is the whole caption", () => {
  test("the chain falls through to its next door rather than printing blank", () => {
    const item = card({
      name: "Will Tatyana Ali be eliminated in week 2 of Dancing With The Stars: Season 35?",
      context_summary: "38% chance",
      reason:
        "Will Tatyana Ali be eliminated in week 2 of Dancing...: 38% chance",
      hook: "Week 2 eliminations are decided on Tuesday's live vote.",
    });
    expect(feedContextSnippet(item, EYEBROW, "38%")).toBe(
      "Week 2 eliminations are decided on Tuesday's live vote.",
    );
  });

  test("and when there is no next door it is empty — #4056's own ruling", () => {
    // The production specimen: `Will Tatyana Ali be eliminated in week 2 of
    // Dancing With The Stars: Season 35?`, whose entire served copy is the
    // restatement, under a 38% hero and an eyebrow already saying when it
    // closes. It is the ONE card of 89 this change silences, and silence is the
    // state #4056 ruled for it, not a new one.
    const item = card({
      name: "Will Tatyana Ali be eliminated in week 2 of Dancing With The Stars: Season 35?",
      context_summary: "38% chance, resolving within a day",
      reason:
        "Will Tatyana Ali be eliminated in week 2 of Dancing...: 38% chance, resolving within a day",
    });
    expect(feedContextSnippet(item, "Closes in 4h", "38%")).toBe("");
  });
});

describe("#8151 the head-strip repair this ship depends on", () => {
  // `stripCardTitleHead`'s truncated-head branch (#6903) required whitespace
  // after the `...` mark. `generate_futures_reason` composes `f"{title}:
  // {context}"`, so on a truncated title the mark is ALWAYS followed by a colon.
  // Measured over the same capture: the old lookahead cut 0 of the 23 reasons
  // carrying a truncation mark; the new one cuts 23 of 23. Without this the hero
  // strip above makes a card WORSE — the caption falls through from "38% chance"
  // to the whole reason, title and all.
  const OLD_LOOKAHEAD = /^(.{12,}?)\.\.\.(?=\s|$)/;

  test("the backend's own reason shape is cut", () => {
    expect(
      stripCardTitleHead(
        "Will there be at least 5000 measles cases in the U.S....: 68% chance, up 53 points since Apr 29",
        "Will there be at least 5000 measles cases in the U.S. in 2026?",
      ),
    ).toBe("68% chance, up 53 points since Apr 29");
  });

  test("STRAWMAN: that exact string is one the old expression could not match", () => {
    // Pins WHY the assertion above is a repair and not a restatement of
    // behaviour that already worked. If someone reverts the lookahead, this
    // fails alongside it instead of leaving a green test lying about a fix.
    expect(
      "Will there be at least 5000 measles cases in the U.S....: 68% chance".match(
        OLD_LOOKAHEAD,
      ),
    ).toBeNull();
  });

  test("a head that is NOT this card's name is still never cut", () => {
    // #6903's own guard: only a head that is genuinely a prefix of the heading.
    expect(
      stripCardTitleHead(
        "Some other market entirely...: 68% chance",
        "Will there be at least 5000 measles cases in the U.S. in 2026?",
      ),
    ).toBe("Some other market entirely...: 68% chance");
  });
});
