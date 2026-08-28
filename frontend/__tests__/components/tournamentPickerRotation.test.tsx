/**
 * UX-P138, Alex's rulings 5 and 8 — the chart's picker, and prop rotation.
 *
 * Both rulings are about a control or a section that LOOKED finished and was
 * not, so both suites are written to fail on the "looks fine" version:
 *
 * RULING 5 ("is it as good as DataGolf's picker? If not, close the gap"). The
 * old picker rendered, opened, added a line, and had no way to find a player
 * in a field of 44 and no way back to the default. Every one of those is
 * invisible to a test that only asks whether the picker renders.
 *
 * RULING 8 ("when a prop resolves or goes stale, it rotates out, curated by
 * interestingness, never a repeating template"). Rotation DROPS things, and a
 * section that drops things silently is indistinguishable from a section
 * nobody is filling. So the counters are asserted as hard as the drops.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ContenderChart from "@/components/tournament/ContenderChart";
import TournamentProps from "@/components/tournament/TournamentProps";
import {
  MAX_SERIES_COUNT,
  defaultSelection,
  filterCandidates,
  selectionIsDefault,
} from "@/lib/contenderChart";
import {
  PROP_DARK_AFTER_HOURS,
  curatedProps,
  curatedPropsEmptyReason,
  propInterestScore,
  propIsDark,
  propIsResolved,
  propSubject,
  propTemplateFamily,
  propTopic,
  type PropMarket,
  type PropOutcome,
} from "@/lib/tournamentProps";
import type { TournamentRow } from "@/lib/tournament";

const count = (html: string, needle: string) =>
  (html.match(new RegExp(needle, "g")) ?? []).length;

function row(overrides: Partial<TournamentRow> = {}): TournamentRow {
  return {
    entity_key: "a",
    display_name: "Carlos Alcaraz",
    seed: 1,
    country: null,
    rank: 1,
    state: "live",
    probability: 0.3,
    probability_is_live: true,
    observed_at: "2026-08-26T20:00:00+00:00",
    age_hours: 0.2,
    price_state: "live",
    freshest_observed_at: "2026-08-26T20:00:00+00:00",
    freshest_age_hours: 0.2,
    stale_sources: [],
    mixed_freshness: false,
    source_count: 2,
    sources: [],
    blend_rule: "equal_weight_midpoint",
    divergent: false,
    trend: [
      { date: "2026-08-20", probability: 0.28 },
      { date: "2026-08-21", probability: 0.3 },
    ],
    trend_delta: 0.02,
    ...overrides,
  };
}

/** A field with the accented and Nordic names the real draw is full of. */
const FIELD: TournamentRow[] = [
  row({ entity_key: "a", display_name: "Carlos Alcaraz", rank: 1, probability: 0.3 }),
  row({ entity_key: "b", display_name: "Jannik Sinner", rank: 2, probability: 0.26 }),
  row({ entity_key: "c", display_name: "Novak Djokovic", rank: 3, probability: 0.14 }),
  row({ entity_key: "d", display_name: "Tomas Sørensen", rank: 4, probability: 0.08 }),
  row({ entity_key: "e", display_name: "Nikola Dvořák", rank: 5, probability: 0.06 }),
  row({ entity_key: "f", display_name: "Ugo Beaumont", rank: 6, probability: 0.05 }),
  row({ entity_key: "g", display_name: "Emil Hedström", rank: 7, probability: 0.04 }),
  row({ entity_key: "h", display_name: "Pavel Zaytsev", rank: 8, probability: 0.03 }),
  row({ entity_key: "i", display_name: "Wei Xu", rank: 9, probability: 0.02 }),
];

const chart = (extra: Record<string, unknown> = {}, selection = defaultSelection(FIELD)) =>
  renderToStaticMarkup(
    <ContenderChart
      rows={FIELD}
      draw="mens-singles"
      selection={selection}
      onToggle={() => {}}
      onReset={() => {}}
      {...extra}
    />
  );

// ---------------------------------------------------------------------------
// Ruling 5 — the picker
// ---------------------------------------------------------------------------

describe("ruling 5 — filtering the field", () => {
  it("matches anywhere in the name, not only at the start", () => {
    // A reader who knows a surname should not have to remember the first name
    // it is filed under.
    expect(filterCandidates(FIELD, "djok").map((r) => r.entity_key)).toEqual(["c"]);
    expect(filterCandidates(FIELD, "sinner").map((r) => r.entity_key)).toEqual(["b"]);
  });

  it("is case-insensitive", () => {
    expect(filterCandidates(FIELD, "ALCARAZ")).toHaveLength(1);
  });

  it("folds combining accents — nobody types Dvořák", () => {
    expect(filterCandidates(FIELD, "dvorak").map((r) => r.entity_key)).toEqual(["e"]);
    expect(filterCandidates(FIELD, "hedstrom").map((r) => r.entity_key)).toEqual(["g"]);
  });

  it("folds the letters NFD does not decompose — ø, and its friends", () => {
    // The partial-fold trap: NFD + combining-mark strip handles Dvořák and
    // silently fails on Sørensen, which teaches the reader that search is
    // unreliable rather than strict.
    expect(filterCandidates(FIELD, "sorensen").map((r) => r.entity_key)).toEqual(["d"]);
    expect(filterCandidates(FIELD, "Sørensen").map((r) => r.entity_key)).toEqual(["d"]);
  });

  it("an empty query is not a filter", () => {
    expect(filterCandidates(FIELD, "")).toHaveLength(FIELD.length);
    expect(filterCandidates(FIELD, "   ")).toHaveLength(FIELD.length);
  });

  it("returns nothing rather than everything when nothing matches", () => {
    expect(filterCandidates(FIELD, "zzzz")).toHaveLength(0);
  });

  it("renders the filter box inside the open picker", () => {
    const html = chart({ initialPickerOpen: true });
    expect(html).toContain('data-testid="chart-picker-filter"');
  });

  it("does not render the filter box on a closed picker", () => {
    const html = chart();
    expect(html).toContain('data-testid="chart-picker-toggle"');
    expect(html).not.toContain('data-testid="chart-picker-filter"');
  });

  it("narrows the OPTION LIST, not just the input's value", () => {
    // The gap this closes is scanning 41 names. A filter that renders and
    // filters nothing would satisfy every assertion above.
    const all = chart({ initialPickerOpen: true });
    const filtered = chart({ initialPickerOpen: true, initialFilter: "dvorak" });
    expect(count(all, 'data-testid="chart-picker-option"')).toBeGreaterThan(1);
    expect(count(filtered, 'data-testid="chart-picker-option"')).toBe(1);
    expect(filtered).toContain('data-entity="e"');
  });

  it("says so when the filter matches nobody", () => {
    const html = chart({ initialPickerOpen: true, initialFilter: "zzzz" });
    expect(html).toContain('data-testid="chart-picker-no-match"');
    expect(html).not.toContain('data-testid="chart-picker-option"');
  });

  it("counts the FILTERED list in the expander, not the whole field", () => {
    // "Show all 41" under six filtered results is a lie about the list.
    const html = chart({ initialPickerOpen: true, initialFilter: "a" });
    const matches = filterCandidates(
      FIELD.filter((r) => !defaultSelection(FIELD).includes(r.entity_key)),
      "a"
    );
    if (matches.length > 5) expect(html).toContain(`Show all ${matches.length}`);
    expect(html).not.toContain("Show all 6");
  });
});

describe("ruling 5 — the way back", () => {
  it("offers no reset when the selection IS the default", () => {
    expect(selectionIsDefault(FIELD, defaultSelection(FIELD))).toBe(true);
    expect(chart()).not.toContain('data-testid="chart-reset"');
  });

  it("offers a reset once the selection has moved", () => {
    const moved = [...defaultSelection(FIELD), "f"];
    expect(selectionIsDefault(FIELD, moved)).toBe(false);
    expect(chart({}, moved)).toContain('data-testid="chart-reset"');
  });

  it("treats a re-ordered default as the default — an inert control is worse than none", () => {
    const reordered = [...defaultSelection(FIELD)].reverse();
    expect(selectionIsDefault(FIELD, reordered)).toBe(true);
    expect(chart({}, reordered)).not.toContain('data-testid="chart-reset"');
  });

  it("offers no reset when the page did not supply one", () => {
    const html = renderToStaticMarkup(
      <ContenderChart
        rows={FIELD}
        draw="mens-singles"
        selection={[...defaultSelection(FIELD), "f"]}
        onToggle={() => {}}
      />
    );
    expect(html).not.toContain('data-testid="chart-reset"');
  });

  it("still refuses to draw more lines than it can read", () => {
    const full = FIELD.slice(0, MAX_SERIES_COUNT).map((r) => r.entity_key);
    const html = chart({ initialPickerOpen: true }, full);
    expect(count(html, 'data-testid="chart-legend-item"')).toBe(MAX_SERIES_COUNT);
    expect(html).toContain("disabled");
  });
});

// ---------------------------------------------------------------------------
// Ruling 8 — rotation
// ---------------------------------------------------------------------------

function outcome(overrides: Partial<PropOutcome> = {}): PropOutcome {
  return {
    entity_key: "x:yes",
    display_name: "Yes",
    probability: 0.63,
    probability_is_live: true,
    observed_at: "2026-08-26T20:00:00+00:00",
    age_hours: 1,
    price_state: "live",
    is_answer: true,
    ...overrides,
  };
}

function prop(key: string, overrides: Partial<PropMarket> = {}): PropMarket {
  return {
    key,
    title: key,
    hook: null,
    draw: "mens-singles",
    source: "kalshi",
    answer_entity_key: `${key}:yes`,
    price_state: "live",
    observed_at: "2026-08-26T20:00:00+00:00",
    age_hours: 1,
    freshest_observed_at: "2026-08-26T20:00:00+00:00",
    freshest_age_hours: 1,
    stale_outcomes: [],
    mixed_freshness: false,
    outcomes: [outcome({ entity_key: `${key}:yes` })],
    ...overrides,
  };
}

const dark = (key: string, ageHours = 188) =>
  prop(key, {
    price_state: "dark",
    age_hours: ageHours,
    outcomes: [
      outcome({
        entity_key: `${key}:yes`,
        probability_is_live: false,
        price_state: "dark",
        age_hours: ageHours,
      }),
    ],
  });

describe("ruling 8 — an advance-to-round question is not a prop", () => {
  it("routes every reach market to the grid instead of the section", () => {
    const result = curatedProps(
      [
        prop("alcaraz-semifinals"),
        prop("djokovic-quarterfinals"),
        prop("osaka-round-of-16"),
        prop("sinner-competes"),
      ],
      "mens-singles"
    );
    expect(result.markets.map((m) => m.key)).toEqual(["sinner-competes"]);
    expect(result.dropped.advance).toBe(3);
  });

  it("says where they went, rather than quietly having three fewer cards", () => {
    const html = renderToStaticMarkup(
      <TournamentProps
        markets={[prop("alcaraz-semifinals"), prop("sinner-competes")]}
        draw="mens-singles"
      />
    );
    expect(html).toContain('data-testid="props-moved-to-grid"');
    expect(html).toContain("on the Bracket tab");
  });
});

describe("ruling 8 — resolved and dark questions rotate out", () => {
  it("drops a question the market has answered", () => {
    const settled = prop("done", {
      outcomes: [outcome({ entity_key: "done:yes", probability: 1 })],
    });
    expect(propIsResolved(settled)).toBe(true);
    expect(curatedProps([settled], "mens-singles").dropped.resolved).toBe(1);
  });

  it("keeps a near-certainty, because 98% is still a question", () => {
    const nearly = prop("nearly", {
      outcomes: [outcome({ entity_key: "nearly:yes", probability: 0.98 })],
    });
    expect(propIsResolved(nearly)).toBe(false);
    expect(curatedProps([nearly], "mens-singles").markets).toHaveLength(1);
  });

  it("drops a reading we no longer call a price", () => {
    expect(propIsDark(dark("old"))).toBe(true);
    expect(curatedProps([dark("old")], "mens-singles").dropped.dark).toBe(1);
  });

  it("KEEPS a merely stale one, which wears the honesty treatment instead", () => {
    // One vocabulary across the page: live is confident, stale is muted and
    // says its age, dark is gone. A section-specific threshold would be a
    // fourth opinion about what old means.
    const stale = dark("stale-only", PROP_DARK_AFTER_HOURS - 1);
    expect(propIsDark(stale)).toBe(false);
    expect(curatedProps([stale], "mens-singles").markets).toHaveLength(1);
  });

  it("treats a never-priced question as dark rather than as fresh", () => {
    const never = prop("never", {
      outcomes: [outcome({ entity_key: "never:yes", probability: null, age_hours: null })],
    });
    expect(propIsDark(never)).toBe(true);
  });
});

/* ═══ UX-P147, ALEX'S ITEM 6: THE FAMILY MAY NOT CROSS PLAYERS ═══
 *
 * Verbatim: "alcaraz-second-major and sinner-second-major are DIFFERENT
 * PLAYERS and must both render. Key the near-duplicate rule so it never
 * collapses across players." And: "I'd love to" see both.
 *
 * The two tests this replaces asserted the opposite and were correct under the
 * reading of UX-P138 ruling 8 that shipped — "a repeating template" was taken
 * to mean *the same question with a different name in it*. Alex overruled that
 * reading, and he is right about why: two rivals' odds of the same feat is the
 * comparison, and it is the single most interesting thing a two-horse men's
 * draw has. One of them alone is trivia.
 *
 * The cap is not weaker. It is keyed on the WHOLE register key now, so it still
 * collapses the same question about the same subject, and it still cannot be
 * defeated by rewording — nothing is read off the title.
 *
 * ═══ UX-P151: THE CASE IS GONE, THE RULE IS NOT ═══
 *
 * Alex ruled on 2026-08-28 that the two questions become ONE COMBINED CARD, so
 * the register no longer carries `alcaraz-second-major` or `sinner-second-
 * major` at all. These tests are KEPT, and the keys in them are now synthetic
 * rather than shipped, because the clause survives deleting its case
 * (`docs/doctrine.md`): a near-duplicate rule may never collapse across
 * subjects. If it were deleted along with its case, the next two same-topic
 * cards to be curated would silently lose one — which is exactly how the first
 * one was lost, and the reason there were three queues about it.
 *
 * The combined card is a REGISTER-level composition, decided once against the
 * evidence with both markets named. That is a different act from a render-time
 * cap deciding which of two curated cards the reader gets, and the test below
 * pins that the cap leaves it alone.
 */
describe("ruling 8 as amended — a family is a subject AND a topic", () => {
  it("keys the family on the whole curated key, so two players never merge", () => {
    expect(propTemplateFamily(prop("alcaraz-second-major"))).toBe("alcaraz-second-major");
    expect(propTemplateFamily(prop("sinner-second-major"))).toBe("sinner-second-major");
    expect(propTemplateFamily(prop("alcaraz-second-major"))).not.toBe(
      propTemplateFamily(prop("sinner-second-major"))
    );
    // The split is still real and still nameable — the report and the guards
    // both need to say "same topic, different subject" out loud.
    expect(propSubject(prop("alcaraz-second-major"))).toBe("alcaraz");
    expect(propTopic(prop("alcaraz-second-major"))).toBe("second-major");
    expect(propTopic(prop("sinner-second-major"))).toBe("second-major");
    expect(propSubject(prop("sinner-competes"))).toBe("sinner");
  });

  it("RENDERS both second-major cards — Alex's item 6, at the render", () => {
    // Measured on Kalshi 2026-08-28T00:5xZ: Alcaraz's `2+` is 27c on 42,723
    // open interest and Sinner's is 1c, because his "to play" market is 1c
    // too. Side by side that is the men's draw in two numbers.
    const markets = [
      prop("alcaraz-second-major", {
        title: "Can Alcaraz win a second major this year?",
        outcomes: [outcome({ entity_key: "alcaraz-second-major:yes", probability: 0.27 })],
      }),
      prop("sinner-second-major", {
        title: "Can Sinner win a second major this year?",
        outcomes: [outcome({ entity_key: "sinner-second-major:yes", probability: 0.555 })],
      }),
    ];
    const result = curatedProps(markets, "mens-singles");
    expect(result.markets.map((m) => m.key).sort()).toEqual([
      "alcaraz-second-major",
      "sinner-second-major",
    ]);
    expect(result.dropped.template).toBe(0);

    // And at the RENDER, not only in the pure layer — a library assertion stays
    // green the day the component stops printing the card.
    const html = renderToStaticMarkup(
      <TournamentProps markets={markets} draw="mens-singles" />
    );
    expect(html).toContain("Can Alcaraz win a second major this year?");
    expect(html).toContain("Can Sinner win a second major this year?");
  });

  it("still collapses the SAME question about the same subject", () => {
    // The cap has not been weakened, only keyed correctly.
    const result = curatedProps(
      [
        prop("sinner-second-major", {
          outcomes: [outcome({ entity_key: "a", probability: 0.9 })],
        }),
        prop("sinner-second-major", {
          outcomes: [outcome({ entity_key: "b", probability: 0.555 })],
        }),
      ],
      "mens-singles"
    );
    expect(result.markets).toHaveLength(1);
    expect(result.dropped.template).toBe(1);
  });

  it("does NOT merge two questions that merely share phrasing", () => {
    const a = prop("sinner-competes", { title: "Will Sinner actually play?" });
    const b = prop("sinner-retires", { title: "Will Sinner actually retire?" });
    expect(curatedProps([a, b], "mens-singles").markets).toHaveLength(2);
  });

  it("UX-P151: the combined card survives rotation and prints BOTH rows", () => {
    // The shape Alex ruled: one card, two legs, no headline. It has to clear
    // all four rotation rules — it is not an advance question, not resolved,
    // not dark, and cannot collide with itself on the template cap — and then
    // it has to actually render two names and two numbers.
    const combined = prop("second-major", {
      title: "Who wins a second major this year?",
      hook: "Both already have one in 2026.",
      // A comparison has no single answering outcome. `null` selects the
      // ranked rendering; anything else would promote one man's number into
      // the headline slot under a question about both of them.
      answer_entity_key: null,
      outcomes: [
        outcome({
          entity_key: "second-major:alcaraz",
          display_name: "Alcaraz",
          probability: 0.25,
          is_answer: false,
        }),
        outcome({
          entity_key: "second-major:sinner",
          display_name: "Sinner",
          probability: 0.555,
          is_answer: false,
        }),
      ],
    });

    const result = curatedProps([combined], "mens-singles");
    expect(result.markets.map((m) => m.key)).toEqual(["second-major"]);
    expect(result.dropped).toEqual({ advance: 0, resolved: 0, dark: 0, template: 0 });

    const html = renderToStaticMarkup(
      <TournamentProps markets={[combined]} draw="mens-singles" />
    );
    expect(html).toContain('data-shape="field"');
    expect(count(html, 'data-testid="prop-field-row"')).toBe(2);
    expect(html).toContain("Alcaraz");
    expect(html).toContain("Sinner");
    expect(html).toContain("25%");
    expect(html).toContain("56%");
    // No headline number: there is no single answer, and inventing one is the
    // defect `answerOutcome` was written to stop.
    expect(html).not.toContain('data-testid="prop-probability"');
  });

  it("a two-market card is dark when EITHER leg is, not only the leader", () => {
    // CERT-411's rule, on the shape that makes it matter most. A comparison
    // whose fresh side is confident and whose old side is silent is a card
    // arguing that one man's number is more real than the other's.
    const mixed = prop("second-major", {
      answer_entity_key: null,
      outcomes: [
        outcome({
          entity_key: "second-major:alcaraz",
          display_name: "Alcaraz",
          probability: 0.25,
          is_answer: false,
          probability_is_live: false,
          price_state: "dark",
          age_hours: 856,
        }),
        outcome({
          entity_key: "second-major:sinner",
          display_name: "Sinner",
          probability: 0.555,
          is_answer: false,
        }),
      ],
    });
    // The card's governing age is its OLDEST printed leg, so it rotates out.
    expect(propIsDark(mixed)).toBe(true);
    expect(curatedProps([mixed], "mens-singles").dropped.dark).toBe(1);
  });
});

describe("ruling 8 — curated by interestingness", () => {
  it("ranks the coin flip above the near-certainty", () => {
    const flip = prop("flip", {
      outcomes: [outcome({ entity_key: "flip:yes", probability: 0.52 })],
    });
    const sure = prop("sure", {
      outcomes: [outcome({ entity_key: "sure:yes", probability: 0.95 })],
    });
    expect(propInterestScore(flip)).toBeLessThan(propInterestScore(sure));
    expect(curatedProps([sure, flip], "mens-singles").markets.map((m) => m.key)).toEqual([
      "flip",
      "sure",
    ]);
  });

  it("ranks a live reading above an equally-poised stale one", () => {
    const staleFlip = prop("stale-flip", {
      outcomes: [
        outcome({
          entity_key: "stale-flip:yes",
          probability: 0.52,
          probability_is_live: false,
          price_state: "stale",
          age_hours: 30,
        }),
      ],
    });
    const liveFlip = prop("live-flip", {
      outcomes: [outcome({ entity_key: "live-flip:yes", probability: 0.52 })],
    });
    expect(propInterestScore(liveFlip)).toBeLessThan(propInterestScore(staleFlip));
  });

  it("never DROPS a curated question for being uninteresting", () => {
    // The curation bar lives in the register. A sort function that also
    // deleted content would move it here, silently.
    const boring = prop("boring", {
      outcomes: [outcome({ entity_key: "boring:yes", probability: 0.9 })],
    });
    expect(curatedProps([boring], "mens-singles").markets).toHaveLength(1);
  });
});

describe("ruling 8 — an empty section says WHY, with a number", () => {
  it("names the count and the reason, not the generic 'nothing yet'", () => {
    // UX-P145 rewrote the sentence into the reader's vocabulary — Alex quoted
    // the old one as forbidden language. What ruling 8 requires is unchanged
    // and is what this asserts: the empty section must give the NUMBER and the
    // REASON, and must not fall back to the generic branch. The exact wording
    // is pinned in `tournamentPlainLanguage.test.tsx`.
    const result = curatedProps([dark("a"), dark("b"), dark("c")], "mens-singles");
    expect(result.markets).toHaveLength(0);
    const reason = curatedPropsEmptyReason(result);
    expect(reason).toContain("3 questions");
    expect(reason).toContain("have not seen a new number");
    const html = renderToStaticMarkup(
      <TournamentProps markets={[dark("a"), dark("b"), dark("c")]} draw="mens-singles" />
    );
    expect(html).toContain('data-testid="props-empty-reason"');
    expect(html).toContain("have not seen a new number on 3 questions");
    expect(html).not.toContain("Nothing to ask yet");
  });

  it("says so when every question for a draw is a reach market", () => {
    const result = curatedProps(
      [prop("gauff-semifinals", { draw: "womens-singles" })],
      "womens-singles"
    );
    expect(curatedPropsEmptyReason(result)).toContain("Bracket tab");
  });

  /* ═══ UX-P147, ALEX'S ITEM 7: THE WOMEN'S SECTION, READY AND BLOCKED ═══
   *
   * He ruled YES on a women's props section with real questions. The register
   * carries none, and the reason is measured rather than asserted — see
   * `WOMENS_NON_ADVANCE_CENSUS` in `scripts/populate_tournament_props.py`. In
   * one line: every non-advance women's US Open market that exists anywhere is
   * one we do not ingest (six Kalshi `*NATSTAGE*` tickers, 0 rows in our DB),
   * and every one of those is 0 trades / 0 open interest / a .02–.90 spread
   * upstream, so it has no number to print either.
   *
   * "The section is ready" is the load-bearing claim in that report, and a
   * claim in a report is worth nothing. This proves it: a women's question with
   * a live number renders, in full, through the shipped component, with no code
   * change of any kind. The day a NATSTAGE market lands and trades, it is one
   * entry in `CURATION`.
   */
  it("renders a WOMEN'S question the moment one exists — no code change owed", () => {
    const womens = [
      // ⚠️ NOT `americans-quarterfinals`. `advanceRound` claims any key ending
      // in a round suffix and routes it to the playoff grid, which is right for
      // "Does Gauff reach the semifinals?" and wrong for "how many Americans
      // do" — the grid has one row per player and no row for a count. The
      // curation naming rule this implies is written down beside the census in
      // `scripts/populate_tournament_props.py`.
      prop("americans-in-the-quarters", {
        draw: "womens-singles",
        title: "Do two Americans reach the women's quarter-finals?",
        outcomes: [
          outcome({ entity_key: "americans-in-the-quarters:yes", probability: 0.41 }),
        ],
      }),
      prop("sabalenka-back-to-back", {
        draw: "womens-singles",
        title: "Can Sabalenka win back-to-back US Opens?",
        outcomes: [
          outcome({ entity_key: "sabalenka-back-to-back:yes", probability: 0.33 }),
        ],
      }),
    ];
    const result = curatedProps(womens, "womens-singles");
    // BOTH survive — different subjects, so item 6's rekeying holds here too.
    expect(result.markets.map((m) => m.key).sort()).toEqual([
      "americans-in-the-quarters",
      "sabalenka-back-to-back",
    ]);
    expect(result.dropped).toEqual({ advance: 0, resolved: 0, dark: 0, template: 0 });

    const html = renderToStaticMarkup(
      <TournamentProps markets={womens} draw="womens-singles" />
    );
    expect(html).toContain('data-key="americans-in-the-quarters"');
    expect(html).toContain('data-key="sabalenka-back-to-back"');
    expect(html).toContain("Do two Americans reach the women");
    expect(html).toContain("Can Sabalenka win back-to-back US Opens?");
    expect(html).toContain("41%");
    expect(html).toContain("33%");
    // Both live, both with the confident treatment — the honesty layer is not
    // muting a women's card for being a women's card.
    expect(count(html, 'data-live="true"')).toBe(2);
    // And it does not leak into the men's tab, which is the other half of
    // "the section takes a draw and does not care which".
    expect(
      renderToStaticMarkup(<TournamentProps markets={womens} draw="mens-singles" />)
    ).toContain("Nothing to ask yet");
  });

  it("keeps the genuinely-empty sentence when there is truly nothing on file", () => {
    const result = curatedProps([], "mens-singles");
    expect(curatedPropsEmptyReason(result)).toBeNull();
    const html = renderToStaticMarkup(<TournamentProps markets={[]} draw="mens-singles" />);
    // UX-P145: "Nothing curated yet" → "Nothing to ask yet". Same branch, same
    // job — distinguishing "we have nothing" from "we had some and they aged".
    expect(html).toContain("Nothing to ask yet");
  });

  it("counts what it considered, so the drop is auditable from the markup", () => {
    const html = renderToStaticMarkup(
      <TournamentProps
        markets={[dark("a"), prop("alcaraz-semifinals"), prop("live-one")]}
        draw="mens-singles"
      />
    );
    expect(html).toContain('data-considered="3"');
    expect(html).toContain('data-testid="props-rotated-out"');
    expect(html).toContain('data-testid="props-moved-to-grid"');
  });

  it("does not count a moved reach market as 'rotated out' — it moved", () => {
    const html = renderToStaticMarkup(
      <TournamentProps
        markets={[prop("alcaraz-semifinals"), prop("live-one")]}
        draw="mens-singles"
      />
    );
    expect(html).not.toContain('data-testid="props-rotated-out"');
    expect(html).toContain('data-testid="props-moved-to-grid"');
  });
});
