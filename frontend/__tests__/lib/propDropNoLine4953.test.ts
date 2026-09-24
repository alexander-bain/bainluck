/**
 * #4953 — the props rail told the reader "Also not shown: 13 unknown".
 *
 * The issue read this as a translation bug: one enum key that never got written
 * in English, to be fixed by picking a better phrase ("couldn't be classified").
 * It is not, and the fixture here is why.
 *
 * `eventPlayerProps.14782151.noLine.json` is a REAL production payload slice —
 * `GET /api/events/14782151/game-markets` (Steelers @ Patriots), captured live
 * at 17:0xZ on 2026-09-20, the 13 rows that page reported as `unknown` plus six
 * ordinary over/under rows from the same game. Every one of the 13 is a NAMED
 * Kalshi market with a NAMED outcome:
 *
 *   "Pittsburgh vs New England: Most Receiving Yards" / "DK Metcalf" / null
 *
 * They carry no threshold because they are **field markets** (Most Receiving
 * Yards 8, Most Rushing Yards 5 — winner-take-all, one leg per player) and, on
 * other games in the same slate, **yes/no markets** (Anytime Touchdown, Safety,
 * Overtime, D/ST Touchdown, First Team to Score a TD). Measured across all
 * eight live NFL games that afternoon: 5-19 such rows each, and ZERO rows with
 * no market name at all.
 *
 * So a better adjective would have printed a better-worded falsehood. Two
 * separate things were wrong:
 *
 *   1. the taxonomy — a market with no over/under line is a different SHAPE,
 *      not an unreadable row, and
 *   2. the sentence — those rows are not "not shown". They render on the same
 *      page under "All 468 props", so the reader was told 13 things were
 *      missing while looking at them.
 *
 * The admission channel this rail exists to keep open is unchanged:
 * `misclassified`, `wrong_game`, `ungraded` and a genuinely nameless row still
 * reach the screen.
 */

import {
  selectDivergenceRows,
  isBenignDrop,
  PROP_DROP_REASON_LABEL,
  type PropDropReason,
} from "@/lib/propDivergence";
import type { PlayerPropRow } from "@/lib/playerPropsGrouping";

import noLinePayload from "../fixtures/eventPlayerProps.14782151.noLine.json";

const ROWS = noLinePayload as unknown as PlayerPropRow[];

/** The rows the live page reported as `unknown`. */
const NO_LINE_ROWS = ROWS.filter(
  (r) => (r.market_name || "").trim() !== "" && !Number.isFinite(r.threshold as number),
);

describe("#4953 — the production specimen the old branch called unreadable", () => {
  it("is 13 named, thresholdless rows — the fixture is the defect, not a strawman", () => {
    expect(NO_LINE_ROWS).toHaveLength(13);
    // Not one of them is nameless: the old `!marketName || !isFiniteNumber()`
    // branch was reached entirely by its SECOND clause.
    expect(NO_LINE_ROWS.every((r) => (r.market_name || "").trim().length > 0)).toBe(true);
    expect(NO_LINE_ROWS.every((r) => (r.outcome_name || "").trim().length > 0)).toBe(true);
    // And they are the two field-market families, not noise.
    const families = new Set(
      NO_LINE_ROWS.map((r) => (r.market_name || "").split(":").pop()!.trim()),
    );
    expect(families).toEqual(new Set(["Most Receiving Yards", "Most Rushing Yards"]));
  });

  it("classifies them as no_line, never as unknown", () => {
    const res = selectDivergenceRows({ playerProps: ROWS, status: "live" });

    const noLine = res.dropped.find((d) => d.reason === "no_line");
    expect(noLine?.count).toBe(13);

    // The whole point: `unknown` must no longer be able to absorb them.
    expect(res.dropped.find((d) => d.reason === "unknown")).toBeUndefined();
  });

  it("stops announcing them to the reader, because they are on the page", () => {
    const res = selectDivergenceRows({ playerProps: ROWS, status: "live" });

    expect(isBenignDrop("no_line")).toBe(true);
    expect(res.dropped.filter((d) => !d.benign)).toHaveLength(0);
    // `nonBenignCount` is what puts the "Also not shown: ..." sentence on the
    // screen. On this specimen it is now zero, so the sentence does not render.
    expect(res.nonBenignCount).toBe(0);
  });

  it("still ranks the ordinary over/under rows from the same game", () => {
    // gotcha #43, both directions: the drop must not have taken the rail with
    // it. Six priced O/U rows ride in the same fixture.
    const res = selectDivergenceRows({ playerProps: ROWS, status: "live" });
    expect(res.rows.length).toBeGreaterThan(0);
  });
});

describe("#4953 — a nameless row keeps its channel to the screen", () => {
  it("is still unknown, still non-benign", () => {
    const nameless = {
      market_name: "",
      outcome_name: "",
      threshold: null,
      over_probability: 0.5,
      pregame_mark: 0.3,
    } as unknown as PlayerPropRow;

    const res = selectDivergenceRows({ playerProps: [nameless], status: "scheduled" });
    const drop = res.dropped.find((d) => d.reason === "unknown")!;

    expect(drop.count).toBe(1);
    expect(drop.benign).toBe(false);
    expect(res.nonBenignCount).toBe(1);
    expect(isBenignDrop("unknown")).toBe(false);
  });

  it("keeps the three genuinely-bad reasons non-benign", () => {
    expect(isBenignDrop("misclassified")).toBe(false);
    expect(isBenignDrop("wrong_game")).toBe(false);
    expect(isBenignDrop("ungraded")).toBe(false);
  });
});

describe("#4953 — the vocabulary", () => {
  const REASONS: PropDropReason[] = [
    "no_real_price",
    "outside_band",
    "misclassified",
    "wrong_game",
    "ungraded",
    "no_line",
    "conflicting_legs",
    "unknown",
  ];

  it("gives every reason a label, and none of them is its own enum key", () => {
    // The defect in one line: `unknown: "unknown"` put an enum name on a
    // reader's screen. No label may be its own key, ever again.
    for (const reason of REASONS) {
      const label = PROP_DROP_REASON_LABEL[reason];
      expect(typeof label).toBe("string");
      expect(label.length).toBeGreaterThan(0);
      expect(label).not.toBe(reason);
    }
  });

  it("writes every label in words a reader uses, never in snake_case", () => {
    for (const reason of REASONS) {
      expect(PROP_DROP_REASON_LABEL[reason]).not.toMatch(/_/);
    }
  });
});

describe("#4953 — one vocabulary, not two", () => {
  it("defines the drop-reason labels in exactly one place", () => {
    // The issue's second ask. `REASON_LABEL` was duplicated verbatim in
    // `PropDivergenceRail.tsx` and `PropDivergenceDetail.tsx` — a rail and the
    // detail view it expands into, each with its own copy of one vocabulary.
    // The day they drift is the day the two disagree about the same row.
    const fs = require("fs") as typeof import("fs");
    const path = require("path") as typeof import("path");
    const root = path.resolve(__dirname, "../..");

    // Keyed on THIS vocabulary's fingerprint, not on the identifier. A first
    // cut matched `\w*REASON_LABEL\w*` and flagged `app/admin/taxonomy/page.tsx`
    // — a genuinely unrelated map ("missing" / "invalid" / "authority_disagree")
    // that merely shares the name. A guard that fires on a different vocabulary
    // is a guard aimed at the word instead of the thing.
    const walk = (dir: string): string[] => {
      const abs = path.join(root, dir);
      if (!fs.existsSync(abs)) return [];
      if (fs.statSync(abs).isDirectory()) {
        return fs.readdirSync(abs).flatMap((e) => walk(path.join(dir, e)));
      }
      return /\.tsx?$/.test(dir) ? [dir] : [];
    };

    const defining = ["lib", "components", "app"]
      .flatMap((d) => walk(d))
      .filter((rel) => {
        const src = fs.readFileSync(path.join(root, rel), "utf8");
        // The prop-drop vocabulary is identifiable by its own keys, so this
        // cannot be satisfied by renaming the constant either.
        return /no_real_price\s*:/.test(src) && /outside_band\s*:/.test(src);
      });

    expect(defining).toEqual(["lib/propDivergence.ts"]);
  });
});
