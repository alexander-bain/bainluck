/**
 * A SETTLED FIELD CARD STOPS QUOTING A MARKET — UX-P211, CERT-516's BLOCK.
 *
 * CERT-516 blocked `58467180` on one finding, and it was right:
 *
 *   > the field list is gated only by `answer === null && rows.length > 0`, not
 *   > by `settled === null`. An adversarial render of a settled two-player field
 *   > failed 1/1: the same card contained `data-settled="true"`, headline result
 *   > `Player A`, `data-testid="prop-field"`, two liquidity marks, and
 *   > live-styled `70%` / `30%` rows. The section-level `anyThin` gate also scans
 *   > settled outcomes, so it prints the liquidity explainer for a market nobody
 *   > can trade.
 *
 * ═══ WHY UX-P207 MISSED IT, WHICH IS THE REUSABLE PART ═══
 *
 * UX-P207 built the settled treatment for the shape it had a specimen of — the
 * one-outcome answer card, `sinner-competes` — and every one of the ten tests in
 * `tournamentPropSettled.test.tsx` drives that shape. A prop card has TWO
 * renderings, and the settled path only ever met one of them. The headline slot,
 * the age chip and the card-level mark were all correctly gated on `settled`;
 * the ranked list two elements below was not, because on the specimen it never
 * rendered at all.
 *
 * That is the same class UX-P208, UX-P209 and UX-P210 each paid for on the
 * tennis hub, one element out each time: silencing the element the specimen
 * showed you is not silencing the claim. So the assertions here are scoped to
 * the SETTLED CARD'S OWN MARKUP rather than to the whole page — a card is a
 * claim about its question, and everything inside it inherits that claim.
 *
 * ═══ WHAT A SETTLED FIELD CARD DOES INSTEAD, AND WHY IT IS NOT A DELETION ═══
 *
 * The cert offers two fixes: suppress the rows, or "replace them with explicitly
 * historical result context". This takes the second, because the first
 * contradicts the treatment the answer card already ships — UX-P207's own note
 * on the muted line reads *"Deleting it would throw away a true fact — the
 * market really did close at 1% — and printing it in the headline would make a
 * finished question look open."* A field card's readings are the same true fact
 * several times over, and one card type keeping its history while the other
 * discards it would be two philosophies wearing one design.
 *
 * So the rows survive, demoted: no liquidity mark, no confident type, no "yet",
 * under a line that says they are the last readings before the question closed.
 *
 * ⚠️ EVERY ASSERTION IS AGAINST THE RENDER of the real default export
 * (`reference_plant_must_hit_the_render`), and the over-correction controls are
 * as load-bearing as the bans: a guard that only says "no live rows on a settled
 * card" is satisfied by deleting the section.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentProps from "@/components/tournament/TournamentProps";
import type { PropMarket, PropOutcome } from "@/lib/tournamentProps";

const render = (element: React.ReactElement) => renderToStaticMarkup(element);

/**
 * The markup of ONE card, by its register key.
 *
 * Scoped rather than page-wide on purpose. "No liquidity mark anywhere on the
 * page" is a different and wrong assertion — it would fail the mixed-section
 * control below, where an open card beside a settled one is fully entitled to
 * its mark. What is banned is the mark on the CLOSED question.
 */
function cardMarkup(html: string, key: string): string {
  const start = html.indexOf(`data-key="${key}"`);
  expect(start).toBeGreaterThan(-1);
  const open = html.lastIndexOf("<li", start);
  // The next card starts at the next `data-testid="prop-market"`, or the list ends.
  const next = html.indexOf('data-testid="prop-market"', start);
  const end = next === -1 ? html.indexOf("</ul>", start) : html.lastIndexOf("<li", next);
  expect(end).toBeGreaterThan(open);
  return html.slice(open, end);
}

/** The markup of one element by testid, from its tag to its closing tag. */
function elementMarkup(html: string, testid: string): string {
  const at = html.indexOf(`data-testid="${testid}"`);
  expect(at).toBeGreaterThan(-1);
  const open = html.lastIndexOf("<", at);
  const tag = /^<([a-z]+)/.exec(html.slice(open))?.[1];
  expect(tag).toBeTruthy();
  const close = html.indexOf(`</${tag}>`, at);
  expect(close).toBeGreaterThan(open);
  return html.slice(open, close);
}

function outcome(over: Partial<PropOutcome> & { entity_key: string }): PropOutcome {
  return {
    display_name: "Player",
    probability: 0.5,
    probability_is_live: true,
    observed_at: "2026-08-31T00:58:18+00:00",
    age_hours: 0.34,
    price_state: "live",
    is_answer: false,
    // A THIN BOOK ON EVERY ROW, because the mark is half of what the cert found
    // and a fixture without one cannot show it went away.
    liquidity: "thin",
    liquidity_reasons: ["no_trades_24h"],
    ...over,
  };
}

/**
 * The shape UX-P207 never met: a field card, two priced outcomes, no single
 * outcome answering the question. The cert's own adversarial render.
 */
function womensTitle(overrides: Partial<PropMarket> = {}): PropMarket {
  return {
    key: "womens-title",
    title: "Who takes the women's title?",
    hook: null,
    draw: "womens-singles",
    source: "kalshi",
    legs: 1,
    unpriced_legs: [],
    outcomes: [
      outcome({ entity_key: "sabalenka", display_name: "Aryna Sabalenka", probability: 0.7 }),
      outcome({ entity_key: "swiatek", display_name: "Iga Swiatek", probability: 0.3 }),
    ],
    // A FIELD CARD. `null` selects the ranked-list rendering — the one the
    // settled path did not know about.
    answer_entity_key: null,
    price_state: "live",
    observed_at: "2026-08-31T00:58:18+00:00",
    age_hours: 0.34,
    freshest_observed_at: "2026-08-31T00:58:18+00:00",
    freshest_age_hours: 0.34,
    stale_outcomes: [],
    mixed_freshness: false,
    liquidity: "thin",
    liquidity_reasons: ["no_trades_24h"],
    ...overrides,
  };
}

const SETTLED = {
  settled: true,
  settled_answer: "Aryna Sabalenka",
  settled_at: "2026-08-30T15:00:00+00:00",
};

const DRAW = "womens-singles";

describe("UX-P211 — a settled FIELD card stops presenting an open market", () => {
  it("REPRODUCES what CERT-516 rendered: the open card is the live treatment", () => {
    // Every ban below is a change to THIS render, so it is worth pinning what it
    // is a change FROM. The open card is entitled to all of it.
    const html = render(<TournamentProps markets={[womensTitle()]} draw={DRAW} />);
    const card = cardMarkup(html, "womens-title");
    expect(card).toContain('data-settled="false"');
    expect(card).toContain('data-testid="prop-field"');
    expect(card).toContain('data-testid="liquidity-mark"');
    expect(card).toContain("70%");
    expect(card).toContain("30%");
  });

  it("prints NO live field list once the register says the question closed", () => {
    const html = render(<TournamentProps markets={[womensTitle(SETTLED)]} draw={DRAW} />);
    const card = cardMarkup(html, "womens-title");
    expect(card).toContain('data-settled="true"');
    // The exact element the cert found under a settled headline.
    expect(card).not.toContain('data-testid="prop-field"');
    expect(card).not.toContain('data-testid="prop-field-row"');
  });

  it("carries no liquidity mark — advice about a trade nobody can make", () => {
    // The card-level mark was already gated by UX-P207; the PER-ROW marks inside
    // the ranked list were not, and there are two of them.
    const html = render(<TournamentProps markets={[womensTitle(SETTLED)]} draw={DRAW} />);
    expect(cardMarkup(html, "womens-title")).not.toContain('data-testid="liquidity-mark"');
  });

  it("KEEPS both readings, demoted and named as the last ones", () => {
    // Not a deletion — see the note at the top. The same true fact the answer
    // card keeps in its muted line, twice over.
    const html = render(<TournamentProps markets={[womensTitle(SETTLED)]} draw={DRAW} />);
    const card = cardMarkup(html, "womens-title");
    expect(card).toContain('data-testid="prop-settled-field"');
    expect(card).toContain("Aryna Sabalenka");
    expect(card).toContain("Iga Swiatek");
    expect(card).toContain("70%");
    expect(card).toContain("30%");
    // And the line above them says what they are, mirroring "· last reading 1%"
    // on the answer card rather than inventing a second vocabulary.
    expect(card).toContain('data-testid="prop-settled"');
    expect(card).toContain("last readings");
  });

  it("prints no number in the confident type inside a closed question", () => {
    // The live rows read `text-text-primary` when `probability_is_live`; both of
    // these are live-quoted and neither may look current.
    const html = render(<TournamentProps markets={[womensTitle(SETTLED)]} draw={DRAW} />);
    const list = elementMarkup(html, "prop-settled-field");
    expect(list).toContain("70%");
    expect(list).not.toContain("text-text-primary");
  });

  it("does not summon the section explainers for a market nobody can trade", () => {
    // `anyThin` scanned every card's outcomes regardless of settlement, so the
    // liquidity legend printed under a section whose only mark had been
    // suppressed. `anyQuiet` is the same bug in the other footnote: a settled
    // card is never `fresh`, so it summoned the definition of an age chip it had
    // already dropped. An explainer for a symbol that is not on screen is worse
    // than no explainer.
    const html = render(<TournamentProps markets={[womensTitle(SETTLED)]} draw={DRAW} />);
    expect(html).not.toContain('data-testid="props-liquidity-definition"');
    expect(html).not.toContain('data-testid="props-freshness-definition"');
    expect(html).not.toContain('data-testid="prop-age"');
  });

  it("stops saying a closed comparison is still waiting for a number", () => {
    // `incompleteComparisonNote` ends "…has not reached us YET, so this
    // comparison is not complete" — true of an open card and a claim about the
    // future on a closed one. The hole is still reported; only the tense moves.
    const settledComparison = womensTitle({
      ...SETTLED,
      legs: 2,
      outcomes: [
        outcome({ entity_key: "sabalenka", display_name: "Aryna Sabalenka", probability: 0.7 }),
        outcome({ entity_key: "swiatek", display_name: "Iga Swiatek", probability: null }),
      ],
    });
    const card = cardMarkup(
      render(<TournamentProps markets={[settledComparison]} draw={DRAW} />),
      "womens-title"
    );
    expect(card).toContain('data-testid="prop-incomplete"');
    expect(card).toContain("Iga Swiatek");
    expect(card).not.toMatch(/\byet\b/);
  });

  /* ═══ THE OVER-CORRECTION CONTROLS ═══
   *
   * "No live rows on a settled card" is trivially satisfied by rendering no
   * rows, no cards and no section. Every ban above is therefore paired with a
   * case that REQUIRES the thing to be there. UX-P210's mutant E — delete the
   * heading unconditionally — killed thirteen tests; these are the same idea
   * written down before the mutant rather than after it.
   */

  it("CONTROL: an OPEN field card keeps its rows, its marks and its explainers", () => {
    const html = render(<TournamentProps markets={[womensTitle()]} draw={DRAW} />);
    const card = cardMarkup(html, "womens-title");
    expect(card).toContain('data-testid="prop-field"');
    expect((card.match(/data-testid="liquidity-mark"/g) ?? []).length).toBeGreaterThanOrEqual(2);
    expect(card).toContain("text-text-primary");
    expect(html).toContain('data-testid="props-liquidity-definition"');
    // …and it must NOT have grown the settled rendering.
    expect(card).not.toContain('data-testid="prop-settled-field"');
    expect(card).not.toContain('data-testid="prop-settled"');
  });

  it("CONTROL: one settled card does not silence the open card beside it", () => {
    // The failure this pins is the plausible over-fix — gating the SECTION on
    // any card being settled instead of gating each card on its own state.
    const open = womensTitle({
      key: "mens-title",
      title: "Who takes the men's title?",
      draw: DRAW,
    });
    const html = render(
      <TournamentProps markets={[womensTitle(SETTLED), open]} draw={DRAW} />
    );
    const settledCard = cardMarkup(html, "womens-title");
    const openCard = cardMarkup(html, "mens-title");

    expect(settledCard).toContain('data-settled="true"');
    expect(settledCard).not.toContain('data-testid="prop-field"');
    expect(settledCard).not.toContain('data-testid="liquidity-mark"');

    expect(openCard).toContain('data-settled="false"');
    expect(openCard).toContain('data-testid="prop-field"');
    expect(openCard).toContain('data-testid="liquidity-mark"');
    // The open card's mark is on screen, so the legend is owed and printed.
    expect(html).toContain('data-testid="props-liquidity-definition"');
    // Exactly one of each rendering on the page.
    expect((html.match(/data-testid="prop-field"/g) ?? []).length).toBe(1);
    expect((html.match(/data-testid="prop-settled-field"/g) ?? []).length).toBe(1);
  });

  it("CONTROL: a settled card still renders — it is demoted, never hidden", () => {
    // Alex, 2026-08-28: illiquid props render with honest indication, never
    // hidden. Settlement is an honesty treatment too, not a new way to delete a
    // question the register curated.
    const html = render(<TournamentProps markets={[womensTitle(SETTLED)]} draw={DRAW} />);
    expect(html).toContain('data-testid="tournament-props"');
    expect(html).toContain('data-testid="prop-market"');
    expect(html).not.toContain('data-testid="props-empty"');
    expect(html).toContain("Who takes the women’s title?".replace("’", "&#x27;"));
  });

  it("FAIL-SAFE: a field payload with no settlement fields is untouched", () => {
    // The whole settled path stays behind an explicit `settled === true`, so a
    // register that has never heard of it renders as it did before UX-P207.
    for (const settled of [undefined, false, null]) {
      const card = cardMarkup(
        render(<TournamentProps markets={[womensTitle({ settled })]} draw={DRAW} />),
        "womens-title"
      );
      expect(card).toContain('data-settled="false"');
      expect(card).toContain('data-testid="prop-field"');
      expect(card).not.toContain('data-testid="prop-settled-field"');
      expect(card).not.toContain('data-testid="prop-settled"');
    }
  });
});

/**
 * A CLOSED CARD DOES NOT INVENT A HISTORY IT DOES NOT HAVE — UX-P212, CERT-537.
 *
 * CERT-537 graded UX-P211's repair and closed CERT-516's live-row leak, then
 * blocked it on what replaced those rows:
 *
 *   > the repair removes the live-market treatment but replaces it with two
 *   > unsupported historical claims. A closed comparison can now say it has last
 *   > readings when it has none, or say a number never reached us when its own
 *   > observation timestamp proves one did.
 *
 * Both are gotcha #53 in the same component — an ABSENCE read as a fact about
 * the past — and neither is a wording quibble, because the payload carries the
 * evidence that contradicts them:
 *
 *   • `· last readings` was gated on `rows.length > 0`. A comparison
 *     deliberately RETAINS its null-probability subjects (that is the whole of
 *     CERT-430's fix), so "there are rows" and "there are readings" are
 *     different questions and the label asked the wrong one. An entirely
 *     unpriced settled comparison printed `Settled · last readings` above two
 *     rows that each said `No number`.
 *
 *   • `No number ever reached us for X` is a claim about all of history, and
 *     `PropOutcome.observed_at` is the newest `captured_at` **where
 *     `probability IS NOT NULL`** (`backend/app/utils/latest_observation.py`) —
 *     so a populated timestamp on a null-probability row is positive proof that
 *     a number DID reach us. `tournaments.py` loads `current_probability` and
 *     that timestamp from two different statements, so the shape is ordinary
 *     wire data, not a contrived fixture. UX-P211's own partial fixture
 *     produced it.
 *
 * ═══ WHY THE OPEN SENTENCE MOVED TOO, WHICH THE CERT DID NOT ASK FOR ═══
 *
 * `No number has reached us for X yet` is the identical claim in the identical
 * shape — present perfect over all of history, disproven by the same field. The
 * cert only rendered the settled branch, but fixing the branch it happened to
 * render and leaving its twin is precisely the failure UX-P208→P211 each paid
 * for one element at a time, and UX-P211's own `anyQuiet` fix is the precedent:
 * when the cert names a mechanism, the mechanism is the finding.
 *
 * So both tenses now speak about what we HAVE, which is what the card can
 * actually see. The tense distinction UX-P211 introduced survives — an open
 * comparison may still be completed, a closed one may not — because that part
 * was right.
 *
 * ⚠️ THE RICHER FIX WAS AVAILABLE AND IS DELIBERATELY NOT TAKEN. `observed_at`
 * would let the card distinguish "never had a number" from "had one, lost it"
 * and say so. It is rejected here because `who` is a NAME LIST: one sentence
 * covering Alcaraz-never and Sinner-lapsed cannot carry two histories without
 * splitting, and a four-way copy matrix is a larger claim surface than the
 * defect. Present availability is true in every wire shape. If a grader wants
 * the historical split it is an additive change to one function.
 */
describe("UX-P212 — a settled card claims only what the payload supports", () => {
  /** Every declared subject unpriced: rows exist, readings do not. */
  const allUnpriced = (over: Partial<PropMarket> = {}) =>
    womensTitle({
      ...SETTLED,
      legs: 2,
      outcomes: [
        outcome({ entity_key: "sabalenka", display_name: "Aryna Sabalenka", probability: null }),
        outcome({ entity_key: "swiatek", display_name: "Iga Swiatek", probability: null }),
      ],
      ...over,
    });

  /** One priced, one not — and the unpriced row carries a real timestamp. */
  const partlyPriced = () =>
    womensTitle({
      ...SETTLED,
      legs: 2,
      outcomes: [
        outcome({ entity_key: "sabalenka", display_name: "Aryna Sabalenka", probability: 0.7 }),
        outcome({ entity_key: "swiatek", display_name: "Iga Swiatek", probability: null }),
      ],
    });

  it("REPRODUCES the cert: an all-unpriced settled comparison has rows but no readings", () => {
    // Pinning what the finding is a finding ABOUT, before banning it: two rows
    // render, both say they have no number, and neither carries one.
    const card = cardMarkup(render(<TournamentProps markets={[allUnpriced()]} draw={DRAW} />), "womens-title");
    expect(card).toContain('data-testid="prop-settled-field"');
    expect((card.match(/data-testid="prop-settled-field-row"/g) ?? []).length).toBe(2);
    expect((card.match(/data-testid="prop-settled-field-missing"/g) ?? []).length).toBe(2);
    expect(card).not.toMatch(/\d+%/);
  });

  it("does not say last readings when not one row has a reading", () => {
    const card = cardMarkup(render(<TournamentProps markets={[allUnpriced()]} draw={DRAW} />), "womens-title");
    // The card is still labelled closed — this bans the CLAIM, not the state.
    expect(card).toContain('data-testid="prop-settled"');
    expect(card).not.toContain('data-testid="prop-settled-lasts"');
    expect(card).not.toContain("last reading");
  });

  it("CONTROL: a settled field card WITH readings still says so, in the plural", () => {
    // The over-correction that kills the label outright. Two numbers, so two
    // readings, so the plural the answer card's singular is a sibling of.
    const card = cardMarkup(render(<TournamentProps markets={[womensTitle(SETTLED)]} draw={DRAW} />), "womens-title");
    expect(card).toContain('data-testid="prop-settled-lasts"');
    expect(card).toContain("last readings");
    expect(card).toContain("70%");
    expect(card).toContain("30%");
  });

  it("CONTROL: exactly one surviving reading is a reading, not readings", () => {
    // `rows.length > 0` and `somePriced` agree here and only the COUNT tells
    // them apart from a label that always pluralises — which is the same class
    // of overstatement one order of magnitude down.
    const card = cardMarkup(render(<TournamentProps markets={[partlyPriced()]} draw={DRAW} />), "womens-title");
    expect(card).toContain('data-testid="prop-settled-lasts"');
    expect(card).toContain("last reading");
    expect(card).not.toContain("last readings");
    expect(card).toContain("70%");
  });

  it("does not claim a number NEVER reached us when the payload timestamps one", () => {
    // Swiatek: `probability: null`, `observed_at` populated by the shared
    // fixture — the exact wire shape `load_latest_observed_at` produces, and
    // proof that a number did reach us.
    const html = render(<TournamentProps markets={[partlyPriced()]} draw={DRAW} />);
    const note = elementMarkup(html, "prop-incomplete");
    expect(note).not.toMatch(/\bever\b/i);
    expect(note).not.toMatch(/\bnever\b/i);
    expect(note).not.toMatch(/reached us/i);
  });

  it("does not make the same lifetime claim on an OPEN comparison", () => {
    // The sibling the cert did not render. Identical shape, identical evidence
    // against it: present perfect over all of history on a row whose timestamp
    // says otherwise.
    const open = womensTitle({
      legs: 2,
      outcomes: [
        outcome({ entity_key: "sabalenka", display_name: "Aryna Sabalenka", probability: 0.7 }),
        outcome({ entity_key: "swiatek", display_name: "Iga Swiatek", probability: null }),
      ],
    });
    const html = render(<TournamentProps markets={[open]} draw={DRAW} />);
    const note = elementMarkup(html, "prop-incomplete");
    expect(note).not.toMatch(/\bever\b/i);
    expect(note).not.toMatch(/\bnever\b/i);
    expect(note).not.toMatch(/reached us/i);
  });

  it("CONTROL: the hole is still reported, still named, and still tensed", () => {
    // The over-correction that deletes the sentence rather than repairing it.
    // CERT-430 exists because this card must ADMIT the missing subject; a fix
    // that buys truthfulness by going quiet fails the finding it answers.
    const settledNote = elementMarkup(
      render(<TournamentProps markets={[partlyPriced()]} draw={DRAW} />),
      "prop-incomplete"
    );
    expect(settledNote).toContain("Iga Swiatek");
    // Wording-neutral ON PURPOSE, so this control is green on the BROKEN bytes
    // too (UX-P211's rule). It asks whether the sentence still admits the hole,
    // not whether it admits it in the words this queue chose.
    expect(settledNote).toMatch(/\bcomplete\b/);
    // UX-P211's tense rule, unchanged: a closed question is not still waiting.
    expect(settledNote).not.toMatch(/\byet\b/);

    const open = womensTitle({
      legs: 2,
      outcomes: [
        outcome({ entity_key: "sabalenka", display_name: "Aryna Sabalenka", probability: 0.7 }),
        outcome({ entity_key: "swiatek", display_name: "Iga Swiatek", probability: null }),
      ],
    });
    const openNote = elementMarkup(
      render(<TournamentProps markets={[open]} draw={DRAW} />),
      "prop-incomplete"
    );
    expect(openNote).toContain("Iga Swiatek");
    expect(openNote).toMatch(/\bcomplete\b/);
    // …and an OPEN one still may be completed, so it keeps the future tense.
    expect(openNote).toMatch(/\byet\b/);
  });

  it("CONTROL: an all-unpriced comparison still renders every subject it declared", () => {
    // The over-correction that reads "nothing to show" and drops the card. Alex,
    // item 4: honest indication, never hidden.
    const card = cardMarkup(render(<TournamentProps markets={[allUnpriced()]} draw={DRAW} />), "womens-title");
    expect(card).toContain("Aryna Sabalenka");
    expect(card).toContain("Iga Swiatek");
    expect(card).toContain('data-testid="prop-incomplete"');
    expect(card).toContain('data-settled="true"');
  });
});
