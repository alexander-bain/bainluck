/**
 * #4788 / #4783 / #1638 — A RED `Lost` THAT NOBODY WROTE
 *
 * ## What a reader sees
 *
 * `/futures/59700266` — *New England vs Seattle: Receptions*, an NFL game that
 * finished 2026-09-09. Under a heading that says **Final Results**, in red:
 *
 *   | row | we print | Kalshi's own result |
 *   |---|---|---|
 *   | Jaxon Smith-Njigba: 7+ | **Lost** · 0% · *Settled* | **`yes`** (`finalized`) |
 *   | Jaxon Smith-Njigba: 8+ | **Lost** · 0% · *Settled* | **`yes`** (`finalized`) |
 *
 * He caught **8**. Both props hit. This is not a blank and not a stale price —
 * it is a confident, wrong verdict presented as settled truth, which is the
 * direct negation of the *settled means settled* ruling.
 *
 * ## The mechanism
 *
 * `futures_outcomes.is_winner` is `boolean NULL DEFAULT false` (`models.py:942`,
 * `default=False` *and* `server_default=text("false")`). An INSERT that merely
 * OMITS the column stores an affirmative graded **LOSS** (CAL-P1004R). Three of
 * the four `pg_insert(FuturesOutcome)` sites in `tasks/polymarket.py` omit it.
 * So the value on the wire is routinely a database default wearing a verdict's
 * clothes, and the client had no way to tell — it read `is_winner` directly at
 * four separate sites.
 *
 * `resolution_source` is the field that says a grader actually ran.
 *
 * ## The measurement that makes this the right discriminant
 *
 * Production, `POST /api/admin/db-query`, 2026-09-10 (fingerprints
 * `555db36b5be77725`, `464869ddd75a7c26`):
 *
 *   | | carries a source | carries none |
 *   |---|---|---|
 *   | `is_winner IS TRUE`  | 1,277,870 | **1** |
 *   | `is_winner IS FALSE` | 2,236,925 | **682,853** |
 *
 * A *won* verdict essentially always has a grader behind it — one exception in
 * 1.28 million. A *lost* verdict has none 682,853 times. That one-directional
 * asymmetry is not a coincidence: a defaulted value can only ever be `false`,
 * so the fabrication can only ever be a loss. Withholding on a null source
 * therefore costs one genuine `Won` site-wide and removes 682,853 unwritten
 * losses.
 *
 * The specimen market, measured directly (fingerprint `210f4d4b8ced5146`):
 * 75 legs, **51 `(is_winner NULL, source NULL)` and 24 `(false, NULL)`** —
 * not one leg on the whole market carries a `resolution_source`, so all 24 red
 * `Lost` marks are unwritten.
 *
 * ## Why `undefined` is NOT folded in with `null` — the fence, not an oversight
 *
 * Only `/api/futures/{id}` serialises `resolution_source`; the feed and group
 * payloads do not, and Vercel ships the frontend independently of, and ahead
 * of, Heroku. A `== null` test would blank all 1.28M genuine `Won` marks for
 * the length of a deploy skew and permanently on any surface whose serialiser
 * lacks the field. "Absent" means *this payload cannot say*, and the honest
 * answer to that is today's behaviour — not a withheld verdict. Three of the
 * controls below exist to keep that branch alive.
 *
 * This is formatting, never adjudication (ruling 003): it only ever withholds a
 * claim the backend did not earn, and never manufactures one.
 *
 * ## Red-first, MEASURED against the parent (`6436a02b`), not reasoned
 *
 * **7 fail, 6 pass.** Every test in the first `describe` calls `outcomeRowVerdict`,
 * which does not exist on the parent, so those throw rather than assert — they
 * are diff tests, not controls, however control-shaped their expectation is.
 *
 * The seven that fail are the diff:
 *   1. a defaulted loss is not a verdict
 *   2. an unsourced WIN is withheld too (both directions — gotcha #43)
 *   3. an unresolved row never carries a verdict
 *   4. the specimen's 24 rows print no `Lost`
 *   5. …and print no `0%` / `Settled` either
 *   6. an ungraded settled row keeps its movement cell
 *   7. the row still renders its name and price while withholding
 *
 * The six that pass are the real CONTROLS — green on the parent and green here.
 * They fence the cheap over-correction (deleting the verdict outright, or
 * withholding whenever `is_winner` is false):
 *   - a sourced win still prints `Won` / `100%` / `Settled`
 *   - a sourced loss still prints `Lost` / `0%` / `Settled`
 *   - an absent field keeps today's behaviour, in both directions
 *   - a graded row still trades its movement cell for its result
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import OutcomeRow, {
  outcomeRowPrintsMove,
  outcomeRowVerdict,
} from "@/components/futures/OutcomeRow";
import type { FuturesOutcome } from "@/lib/types";

/**
 * The two legs Kalshi declared `yes` and we printed `Lost` on. Named, because a
 * fixture of anonymous rows would let someone "fix" this by deleting the verdict
 * and never notice that the specimen is two real props on a real NFL game.
 */
const CONTRADICTED = ["Jaxon Smith-Njigba: 7+", "Jaxon Smith-Njigba: 8+"];

function outcome(overrides: Partial<FuturesOutcome> = {}): FuturesOutcome {
  return {
    id: 1,
    name: "Jaxon Smith-Njigba: 7+",
    probability: 0.99,
    opening_probability: 0.59,
    probability_change_24h: 0.005,
    rank: 17,
    rank_change_24h: 3,
    is_winner: false,
    resolution_source: null,
    last_updated: "2026-09-10T12:15:43+00:00",
    ...overrides,
  } as FuturesOutcome;
}

function render(o: FuturesOutcome, isResolved = true): string {
  return renderToStaticMarkup(
    <OutcomeRow
      outcome={o}
      rank={1}
      isLeader={false}
      isSelected={false}
      onToggleSelect={() => {}}
      hasHistory={false}
      marketCategory="americanfootball_nfl"
      marketName="New England vs Seattle: Receptions"
      isResolved={isResolved}
      rendered={null}
      renderedOpening={null}
      showLastMove
      showEntityImage={false}
    />,
  );
}

describe("#4788 outcomeRowVerdict — only a sourced grade is a verdict", () => {
  it("THE DEFECT: `is_winner=false` with no resolution_source is not a verdict", () => {
    expect(outcomeRowVerdict(outcome(), true)).toBeNull();
  });

  it("withholds an UNSOURCED WIN too — the rule is about provenance, not sign", () => {
    // Both directions (gotcha #43). Production holds exactly one such row, so
    // this arm is nearly unreachable — and that is precisely why it is pinned:
    // a fix that only suppressed `false` would look identical on every page we
    // can screenshot, and would still be reading a column default as a verdict.
    expect(
      outcomeRowVerdict(outcome({ is_winner: true, resolution_source: null }), true),
    ).toBeNull();
  });

  it("an honest NULL is still ungraded", () => {
    expect(
      outcomeRowVerdict(outcome({ is_winner: null, resolution_source: null }), true),
    ).toBeNull();
  });

  it("an unresolved row never carries a verdict, however it is graded", () => {
    expect(
      outcomeRowVerdict(
        outcome({ is_winner: true, resolution_source: "api_settlement" }),
        false,
      ),
    ).toBeNull();
  });

  // ── CONTROLS: a real grade still reads as one ───────────────────────────────

  it("CONTROL: a sourced win is a win", () => {
    for (const src of ["api_settlement", "clean_resolution", "box_score"]) {
      expect(
        outcomeRowVerdict(outcome({ is_winner: true, resolution_source: src }), true),
      ).toBe("won");
    }
  });

  it("CONTROL: a sourced loss is a loss", () => {
    expect(
      outcomeRowVerdict(
        outcome({ is_winner: false, resolution_source: "api_settlement" }),
        true,
      ),
    ).toBe("lost");
  });

  it("CONTROL: an ABSENT field keeps today's behaviour, in both directions", () => {
    // The deploy-skew / other-serialiser fence. `undefined` is not `null`:
    // absent means "this payload cannot say", and folding the two together
    // would blank 1.28M genuine `Won` marks the moment Vercel shipped ahead of
    // Heroku. Built by deletion rather than by assigning `undefined`, so the
    // key is genuinely missing the way `JSON.parse` leaves it.
    const absent = outcome();
    delete (absent as { resolution_source?: string | null }).resolution_source;
    expect(outcomeRowVerdict({ ...absent, is_winner: true }, true)).toBe("won");
    expect(outcomeRowVerdict({ ...absent, is_winner: false }, true)).toBe("lost");
  });
});

describe("#4788 the rendered row", () => {
  it("THE DEFECT: neither contradicted leg prints `Lost`", () => {
    for (const name of CONTRADICTED) {
      const html = render(outcome({ name }));
      expect(html).toContain(name);
      expect(html).not.toContain("Lost");
    }
  });

  it("prints no `0%` and no `Settled` on an ungraded leg either", () => {
    // The verdict is stated twice on this row — once in words, once in numbers.
    // Removing only the word would leave `0% · Settled`, which says the same
    // thing to the same reader.
    const html = render(outcome());
    expect(html).not.toContain("Settled");
    expect(html).not.toContain(">0%<");
  });

  it("still renders the row — name and last recorded price — while withholding", () => {
    // The over-correction fence in the other direction: withholding a verdict
    // must not blank the row. Its `is_winner IS NULL` siblings on this very
    // market already print exactly this, which is the point — the two shapes
    // are indistinguishable in the data, so they must be on the screen.
    const html = render(outcome());
    expect(html).toContain("Jaxon Smith-Njigba: 7+");
    expect(html).toContain("99%");
  });

  it("an ungraded settled row keeps its movement cell", () => {
    // `outcomeRowPrintsMove` traded the move away for "the row prints its
    // result". A row with no result has nothing to trade it for.
    expect(outcomeRowPrintsMove(outcome(), true)).toBe(true);
  });

  // ── CONTROLS ────────────────────────────────────────────────────────────────

  it("CONTROL: a sourced win still prints `Won`, `100%` and `Settled`", () => {
    const html = render(
      outcome({ is_winner: true, resolution_source: "api_settlement" }),
    );
    expect(html).toContain("Won");
    expect(html).toContain("100%");
    expect(html).toContain("Settled");
  });

  it("CONTROL: a sourced loss still prints `Lost`", () => {
    const html = render(
      outcome({ is_winner: false, resolution_source: "api_settlement" }),
    );
    expect(html).toContain("Lost");
    expect(html).toContain("Settled");
  });

  it("CONTROL: a graded row still trades its movement cell for its result", () => {
    expect(
      outcomeRowPrintsMove(
        outcome({ is_winner: false, resolution_source: "api_settlement" }),
        true,
      ),
    ).toBe(false);
  });
});

describe("#4788 the specimen market, whole", () => {
  /**
   * `/futures/59700266` as production returns it: 75 legs, 51 ungraded-NULL and
   * 24 defaulted-false, not one carrying a `resolution_source`. Asserted over
   * the WHOLE set rather than a row, because the defect is a count a reader
   * sees at once — two dozen red marks down a column headed *Final Results*.
   */
  const SPECIMEN: FuturesOutcome[] = [
    ...Array.from({ length: 24 }, (_, i) =>
      outcome({
        id: 100 + i,
        name: i < 2 ? CONTRADICTED[i] : `Mack Hollins: ${i}+`,
        is_winner: false,
        resolution_source: null,
      }),
    ),
    ...Array.from({ length: 51 }, (_, i) =>
      outcome({
        id: 200 + i,
        name: `Cooper Kupp: ${i}+`,
        is_winner: null,
        resolution_source: null,
      }),
    ),
  ];

  it("THE DEFECT: the whole market prints zero `Lost` marks", () => {
    const html = SPECIMEN.map((o) => render(o)).join("");
    expect(SPECIMEN).toHaveLength(75);
    expect(html.match(/Lost/g)).toBeNull();
  });

  it("CONTROL: the same 75 rows still print all 75 names", () => {
    const html = SPECIMEN.map((o) => render(o)).join("");
    for (const o of SPECIMEN) expect(html).toContain(o.name);
  });
});

/**
 * CERT-2517's required repair: `4788-DETAIL-RETRACTION-IS-NOT-A-VERDICT`.
 *
 * The first cut of `outcomeRowVerdict` withheld on a NULL source and then trusted
 * every non-null one. That is the reading CERT-2222 had already blocked on the
 * sibling surface (`_outcome_is_settled`, `routes/league_futures.py`): a non-empty
 * `resolution_source` is not a grade, because exactly one value is a RETRACTION.
 *
 * `ungradeable_result` (CAL-P056, #1852) is the state of a leg whose stored loss
 * the venue never declared. It asserts NO winner, and it is written — leaving
 * `is_winner=false` in place — by the attended repair in
 * `app/tasks/repair_kalshi_fabricated_loss.py`. So the rows this ship is meant to
 * rescue are precisely the rows the repair stamps, and trusting the source would
 * have printed a confident red `Lost` on every one of them: the same lie the ship
 * removes, re-entering through the fix itself.
 *
 * Asserted through the REAL `OutcomeRow`, not the predicate alone, because the
 * predicate drives four separate branches and the reader only ever sees the
 * rendered ones.
 */
describe("#4788 a retraction is not a verdict (CERT-2517 repair)", () => {
  const retracted = (over: Partial<FuturesOutcome> = {}) =>
    outcome({ resolution_source: "ungradeable_result", ...over });

  it("THE DEFECT: a retracted leg with `is_winner=false` prints no verdict", () => {
    expect(outcomeRowVerdict(retracted({ is_winner: false }), true)).toBeNull();
    const html = render(retracted({ is_winner: false }));
    expect(html).not.toContain("Lost");
    expect(html).not.toContain("Settled");
  });

  it("refuses it in the OTHER direction too — retracted AND crowned is a contradiction", () => {
    // A row that is both "we cannot know" and "this one won" cannot be rendered
    // as a result in either direction; the honest render is the live one.
    expect(outcomeRowVerdict(retracted({ is_winner: true }), true)).toBeNull();
    const html = render(retracted({ is_winner: true }));
    expect(html).not.toContain("Won");
    expect(html).not.toContain("100%");
  });

  it("PRESERVES THE PRICE: the retracted row still shows its last recorded number", () => {
    const html = render(retracted({ is_winner: false, probability: 0.99 }));
    expect(html).toContain("99%");
    expect(html.toUpperCase()).toContain("LATEST");
  });

  it("CONTROL: a REAL source is still a grade, in both directions", () => {
    // The repair must not blanket-refuse every source — that would blank the
    // site's genuine verdicts, which is the opposite failure.
    expect(
      outcomeRowVerdict(
        outcome({ is_winner: false, resolution_source: "api_settlement" }),
        true,
      ),
    ).toBe("lost");
    expect(
      outcomeRowVerdict(
        outcome({ is_winner: true, resolution_source: "api_settlement" }),
        true,
      ),
    ).toBe("won");
    expect(render(outcome({ is_winner: true, resolution_source: "api_settlement" })))
      .toContain("Won");
  });

  it("CONTROL: the ABSENT-field deploy-skew fence still holds", () => {
    const absent = outcome({ is_winner: false });
    delete (absent as { resolution_source?: string | null }).resolution_source;
    expect(outcomeRowVerdict(absent, true)).toBe("lost");
  });

  it("a retracted leg on an OPEN market is unaffected — it was never a verdict", () => {
    expect(outcomeRowVerdict(retracted({ is_winner: false }), false)).toBeNull();
  });
});
