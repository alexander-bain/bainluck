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
  propTemplateFamily,
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

describe("ruling 8 — never a repeating template", () => {
  it("reads the family off the curated key, not off the wording", () => {
    expect(propTemplateFamily(prop("alcaraz-second-major"))).toBe("second-major");
    expect(propTemplateFamily(prop("sinner-second-major"))).toBe("second-major");
    expect(propTemplateFamily(prop("sinner-competes"))).toBe("competes");
  });

  it("keeps ONE card per family, and the more interesting one survives", () => {
    // Our actual register: Alcaraz at 25% and Sinner at 55.5% for the same
    // question with the name swapped. The coin flip is the question.
    const result = curatedProps(
      [
        prop("alcaraz-second-major", {
          outcomes: [outcome({ entity_key: "alcaraz-second-major:yes", probability: 0.25 })],
        }),
        prop("sinner-second-major", {
          outcomes: [outcome({ entity_key: "sinner-second-major:yes", probability: 0.555 })],
        }),
      ],
      "mens-singles"
    );
    expect(result.markets.map((m) => m.key)).toEqual(["sinner-second-major"]);
    expect(result.dropped.template).toBe(1);
  });

  it("does NOT merge two questions that merely share phrasing", () => {
    const a = prop("sinner-competes", { title: "Will Sinner actually play?" });
    const b = prop("sinner-retires", { title: "Will Sinner actually retire?" });
    expect(curatedProps([a, b], "mens-singles").markets).toHaveLength(2);
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
