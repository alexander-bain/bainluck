import { readFileSync } from "fs";
import { join } from "path";

import {
  providerOf,
  providerLabel,
  prettifySourceKey,
  sourceLabel,
  makeSourceLabeller,
  groupSourcesByProvider,
  shapeBreakdownIsSymmetric,
  SHAPE_BREAKDOWN_MIN_N,
} from "@/lib/calibrationProviders";

// The five source keys the live 2026-08-13 payload publishes, with their real
// outcome counts. Pinned so a change to the grouping rule has to argue with
// production numbers rather than with a convenient example.
const LIVE_SOURCES = [
  "kalshi",
  "polymarket",
  "odds_api",
  "odds_api_totals",
  "odds_api_spreads",
];
const LIVE_N: Record<string, number> = {
  kalshi: 424127,
  polymarket: 241372,
  odds_api: 15674,
  odds_api_totals: 12704,
  odds_api_spreads: 12409,
};

describe("providerOf", () => {
  it("maps every Odds API shape onto one provider", () => {
    expect(providerOf("odds_api")).toBe("odds_api_family");
    expect(providerOf("odds_api_spreads")).toBe("odds_api_family");
    expect(providerOf("odds_api_totals")).toBe("odds_api_family");
    // Not in today's payload, but the producer still knows how to emit it.
    expect(providerOf("odds_api_bookmaker")).toBe("odds_api_family");
  });

  it("leaves single-shape providers as themselves — they are not special cases", () => {
    expect(providerOf("kalshi")).toBe("kalshi");
    expect(providerOf("polymarket")).toBe("polymarket");
  });

  it("is total: an unknown key becomes its own provider rather than vanishing", () => {
    // A source key we have never seen must still get a row. Dropping it would
    // silently shrink the table's population below the page's own headline.
    expect(providerOf("some_future_source")).toBe("some_future_source");
  });
});

describe("providerLabel", () => {
  it("names the Odds API family for a reader, not for a schema", () => {
    expect(providerLabel("odds_api_family")).toBe("Sportsbooks (Odds API)");
  });

  // CAL-P1024 (#1865): this assertion used to read
  // `expect(providerLabel("some_future_source")).toBe("some_future_source")`,
  // and it was PASSING — the raw-key fallback was pinned here as the contract,
  // under a name ("rather than rendering undefined") that argues only against
  // the worse of two bad options. That is how `datagolf` printed at readers for
  // three weeks with a green suite over it: the guard agreed with the bug.
  //
  // The requirement it was reaching for is real and is kept — an unnamed source
  // must still get a row, never `undefined` and never a dropped source. It is
  // just no longer satisfied by handing over the database key.
  it("still names an unknown provider — but never with its raw key", () => {
    expect(providerLabel("some_future_source")).toBe("Some Future Source");
    expect(providerLabel("some_future_source")).not.toContain("undefined");
  });
});

describe("groupSourcesByProvider", () => {
  it("collapses the live five source keys into three provider rows", () => {
    const groups = groupSourcesByProvider(LIVE_SOURCES);
    expect(groups.map(g => g.provider)).toEqual([
      "kalshi",
      "polymarket",
      "odds_api_family",
    ]);
    expect(groups[2].sources).toEqual([
      "odds_api",
      "odds_api_totals",
      "odds_api_spreads",
    ]);
  });

  it("preserves every source key — the parent rows partition the input", () => {
    const groups = groupSourcesByProvider(LIVE_SOURCES);
    const regrouped = groups.flatMap(g => g.sources).sort();
    expect(regrouped).toEqual([...LIVE_SOURCES].sort());
  });

  it("preserves first-seen order instead of imposing its own", () => {
    const groups = groupSourcesByProvider(["odds_api_totals", "kalshi", "odds_api"]);
    expect(groups.map(g => g.provider)).toEqual(["odds_api_family", "kalshi"]);
  });

  it("does not double-count a duplicated source key into the parent", () => {
    const groups = groupSourcesByProvider(["odds_api", "odds_api", "odds_api_spreads"]);
    expect(groups).toHaveLength(1);
    expect(groups[0].sources).toEqual(["odds_api", "odds_api_spreads"]);
  });

  it("returns nothing for an empty payload rather than a phantom row", () => {
    expect(groupSourcesByProvider([])).toEqual([]);
  });
});

describe("shapeBreakdownIsSymmetric", () => {
  it("is FALSE on the live payload — Kalshi and Polymarket have one shape each", () => {
    // This is the measurement that sends the shape breakdown to the annex.
    // If it ever flips to true, the breakdown belongs inline and this test is
    // the thing that should fail and say so.
    const groups = groupSourcesByProvider(LIVE_SOURCES);
    expect(shapeBreakdownIsSymmetric(groups, LIVE_N)).toBe(false);
  });

  it("is TRUE only when EVERY provider clears the floor on 2+ shapes", () => {
    const groups = groupSourcesByProvider([
      "kalshi", "kalshi_spreads", "odds_api", "odds_api_totals",
    ]);
    const n = {
      kalshi: 5000, kalshi_spreads: 5000, odds_api: 5000, odds_api_totals: 5000,
    };
    // `kalshi_spreads` groups under kalshi only if providerOf says so; it does
    // not, so this asserts the honest thing: two single-shape providers stay
    // asymmetric no matter how large they are.
    expect(shapeBreakdownIsSymmetric(groups, n)).toBe(false);
  });

  it("holds one provider back when its second shape is below the floor", () => {
    const groups = groupSourcesByProvider(["odds_api", "odds_api_totals"]);
    const justUnder = {
      odds_api: 50000,
      odds_api_totals: SHAPE_BREAKDOWN_MIN_N - 1,
    };
    expect(shapeBreakdownIsSymmetric(groups, justUnder)).toBe(false);

    const justOver = {
      odds_api: 50000,
      odds_api_totals: SHAPE_BREAKDOWN_MIN_N,
    };
    expect(shapeBreakdownIsSymmetric(groups, justOver)).toBe(true);
  });

  it("treats a missing count as zero rather than throwing the table away", () => {
    const groups = groupSourcesByProvider(["odds_api", "odds_api_totals"]);
    expect(shapeBreakdownIsSymmetric(groups, { odds_api: 50000 })).toBe(false);
  });

  it("is FALSE on an empty payload — nothing symmetric about nothing", () => {
    expect(shapeBreakdownIsSymmetric([], {})).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// CAL-P1024 (#1865) — naming a source, and never printing its database key
//
// The defect, photographed on production 2026-09-05 before the fix: the last
// Source Comparison row read `datagolf` where every sibling read a proper name,
// and the By Source sentence opened on it — "datagolf has no outcomes in this
// cohort, so its panel is not drawn here...".
//
// `LIVE_SOURCES` above is the 2026-08-13 vocabulary and has FIVE keys. The
// vocabulary measured off `/api/calibration` on 2026-09-05 has SEVEN. That
// growth, with no backend constant to hold the maps against, is the mechanism —
// so the class guard below is written over ARBITRARY keys, not over either
// list. A list-shaped guard would be dead for exactly the key that broke.
// ---------------------------------------------------------------------------

/** Measured off production `/api/calibration` `by_source`, 2026-09-05 4:57pm PT. */
const LIVE_SOURCES_20260905 = [
  "kalshi",
  "polymarket",
  "odds_api_bookmaker",
  "odds_api",
  "odds_api_totals",
  "odds_api_spreads",
  "datagolf",
];

describe("source and provider naming", () => {
  it("names DataGolf in the Source Comparison row — the string production printed raw", () => {
    // The exact path the table takes: a key -> its provider -> that row's label.
    expect(providerOf("datagolf")).toBe("datagolf");
    expect(providerLabel(providerOf("datagolf"))).toBe("DataGolf");
    expect(groupSourcesByProvider(["datagolf"])[0].label).toBe("DataGolf");
  });

  it("names DataGolf wherever the page names a SOURCE, not just a provider", () => {
    // The tab strip, panel headers, chart legends and the drill-in title all go
    // through `sourceLabel`, and they are what the withheld sentence invites the
    // reader to go and look at.
    expect(sourceLabel("datagolf")).toBe("DataGolf");
  });

  it("is the curated brand, never the generated one", () => {
    // The whole reason the map entry exists alongside the fallback: the
    // prettifier cannot know where the capital G goes, and a fabricated brand is
    // the quiet version of this bug rather than a fix for it.
    expect(prettifySourceKey("datagolf")).toBe("Datagolf");
    expect(sourceLabel("datagolf")).not.toBe(prettifySourceKey("datagolf"));
  });

  it("names every source key production publishes today", () => {
    for (const src of LIVE_SOURCES_20260905) {
      expect(sourceLabel(src)).not.toBe(src);
      expect(providerLabel(providerOf(src))).not.toBe(providerOf(src));
    }
  });

  // -- the class, not the instance -----------------------------------------
  // #1865's bar, generalised from categories to sources: no label can ever be a
  // raw payload key, FOR ANY KEY, not just this one. These run over keys that
  // are in no map by construction, so they cannot be satisfied by remembering
  // to add an entry.
  const UNMAPPED = [
    "datagolf",            // today's, so the fallback is proven on the real shape
    "sportradar",
    "espn_bpi",
    "some_new_provider",
    "betfair_exchange",
    "nba_stats_api",
    "x",
  ];

  it.each(UNMAPPED)("never hands the reader the raw key %s", (key) => {
    for (const label of [prettifySourceKey(key), sourceLabel(key), providerLabel(key)]) {
      expect(label).not.toContain("_");
      expect(label.charAt(0)).toBe(label.charAt(0).toUpperCase());
      expect(label).not.toBe(key);
    }
  });

  it("shouts the acronyms a source key is made of rather than spelling them", () => {
    expect(prettifySourceKey("espn_bpi")).toBe("ESPN Bpi");
    expect(prettifySourceKey("nba_stats_api")).toBe("NBA Stats API");
  });

  it("does not fabricate a name for nothing", () => {
    // An empty or separator-only key has no tokens to title-case. Returning the
    // input unchanged is honest; inventing a word for it would not be. Nothing
    // reaches a reader here either way — `by_source` is keyed by a real column.
    expect(prettifySourceKey("")).toBe("");
    expect(prettifySourceKey("___")).toBe("___");
  });
});

// ---------------------------------------------------------------------------
// CAL-P1025 (#3357) — the server publishes the name, the map becomes an override
// ---------------------------------------------------------------------------

describe("makeSourceLabeller — the payload's names, with house style on top", () => {
  it("uses the server's name for a source this page has no opinion about", () => {
    // The exact case that made #3357: a key nobody here has heard of. Without
    // the payload it would be tidied into a guess; with it, it is named.
    const label = makeSourceLabeller({ espn_bpi: { label: "ESPN BPI" } });
    expect(label("espn_bpi")).toBe("ESPN BPI");
    expect(sourceLabel("espn_bpi")).toBe("ESPN Bpi"); // what the guess would be
  });

  it("keeps house style when this page and the server deliberately disagree", () => {
    // `odds_api` names one SOURCE row inside a FAMILY row reading "Sportsbooks
    // (Odds API)", and a server label must never silently overwrite a
    // deliberate local choice, or the two rows collapse into the same words.
    //
    // 🔴 CERT-2290 — THIS PRECEDENCE IS ALSO HOW #4067 SHIPPED A BANNED WORD.
    // The backend corrected `odds_api_bookmaker` to "Per-sportsbook (Odds API)"
    // and the page never saw it, because the local map wins here BY DESIGN.
    // The mechanism is right and stays; the consequence is that a vocabulary
    // sweep is not done when the server is fixed. It is done when every local
    // override is fixed too — which is what
    // `__tests__/lib/supplierWordsAreGuardedEverywhere4067.test.ts` now holds.
    const label = makeSourceLabeller({
      odds_api: { label: "Sportsbooks" },
      odds_api_bookmaker: { label: "Something the server made up" },
    });
    expect(label("odds_api")).toBe("Moneylines (Odds API)");
    expect(label("odds_api_bookmaker")).toBe("Per-sportsbook (Odds API)");
  });

  // -------------------------------------------------------------------------
  // #7213 — THE COST OF WINNING, PINNED.
  //
  // The test above is the mechanism working: house style beats the payload.
  // Its consequence is that for a key BOTH maps hold an opinion about, the
  // server's name is dead text on this page — so the two must be renamed in the
  // same commit or the rename is inert. That is exactly how #4067 shipped a
  // banned word and how #7213's "Odds API" survived #4214's fix.
  //
  // Read from the Python module rather than restated here, for the reason
  // `sportDirectoryNamesEverySport7015.test.ts` gives for the same rail: a
  // restatement is a third map, and three maps drift faster than two. Every
  // failure mode THROWS — a parse that returned `{}` would make this vacuously
  // green, which is the shape of bug it exists to catch.
  // -------------------------------------------------------------------------
  describe("the server vocabulary this page shadows", () => {
    const VOCABULARY_PATH = join(
      __dirname,
      "..",
      "..",
      "..",
      "backend",
      "app",
      "utils",
      "calibration_source_labels.py",
    );

    function readServerLabels(): Record<string, string> {
      const src = readFileSync(VOCABULARY_PATH, "utf8");
      const marker = "CALIBRATION_SOURCE_LABELS: dict[str, str] = {";
      const start = src.indexOf(marker);
      if (start === -1) {
        throw new Error(
          `Could not find "${marker}" in ${VOCABULARY_PATH}. The vocabulary ` +
            `moved or was renamed — fix this reader, do not delete the assertion.`,
        );
      }
      const body = src.slice(start + marker.length);
      const end = body.search(/^\}/m);
      if (end === -1) {
        throw new Error(
          `CALIBRATION_SOURCE_LABELS in ${VOCABULARY_PATH} has no closing brace ` +
            `at column 0.`,
        );
      }
      const out: Record<string, string> = {};
      for (const m of body.slice(0, end).matchAll(/^ {4}"([a-z_]+)": "([^"]+)",$/gm)) {
        out[m[1]] = m[2];
      }
      if (Object.keys(out).length === 0) {
        throw new Error(
          `Parsed zero entries out of CALIBRATION_SOURCE_LABELS — the literal's ` +
            `shape changed. Fix this reader, do not let it pass empty.`,
        );
      }
      return out;
    }

    /**
     * Keys the two maps are DELIBERATELY allowed to differ on.
     *
     * Empty today, and that is the point: rule 1 above says this page MAY
     * disagree with the server, and nothing was checking whether it actually
     * did. It does not. So a future disagreement is a decision somebody writes
     * down here with a reason, not a rename that quietly half-landed.
     */
    const DELIBERATE_DISAGREEMENTS: readonly string[] = [];

    it("is parsed, not assumed — the keys this page names really are in it", () => {
      const server = readServerLabels();
      expect(Object.keys(server).length).toBeGreaterThanOrEqual(7);
      for (const key of ["kalshi", "odds_api", "odds_api_bookmaker", "datagolf"]) {
        expect(server[key]).toBeTruthy();
      }
    });

    it("says the same words as this page's map, for every key it names", () => {
      const server = readServerLabels();
      for (const [key, serverName] of Object.entries(server)) {
        if (DELIBERATE_DISAGREEMENTS.includes(key)) continue;
        // Keyed pairs, not bare strings, so a failure names the source rather
        // than printing two labels and leaving you to guess which key they are.
        expect([key, sourceLabel(key)]).toEqual([key, serverName]);
      }
    });
  });

  it("falls back to the CAL-P1024 prettifier on a payload banked before `label`", () => {
    // The dated fallback tiers can serve an artifact older than the field, so
    // the floor has to survive its absence — never the raw key, either way.
    const absent: (Record<string, { label?: string | null }> | null | undefined)[] = [
      undefined,
      null,
      {},
      { sportradar: {} },
    ];
    for (const vocab of absent) {
      expect(makeSourceLabeller(vocab)("sportradar")).toBe("Sportradar");
    }
  });

  it("treats a blank server label as absent, not as a name", () => {
    // An empty string is how a source ends up rendering as nothing at all.
    const label = makeSourceLabeller({ sportradar: { label: "   " } });
    expect(label("sportradar")).toBe("Sportradar");
  });

  it("never returns a raw payload key, whatever the payload says", () => {
    for (const bad of [null, undefined, ""]) {
      const label = makeSourceLabeller({ some_new_source: { label: bad } });
      expect(label("some_new_source")).not.toBe("some_new_source");
      expect(label("some_new_source")).not.toContain("_");
    }
  });

  it("names a source the payload never mentioned", () => {
    // `sourceLabel`'s contract, unchanged: total over source keys, so a key the
    // vocabulary omits is still named rather than left raw.
    const label = makeSourceLabeller({ kalshi: { label: "Kalshi" } });
    expect(label("polymarket")).toBe("Polymarket");
    expect(label("betfair_exchange")).toBe("Betfair Exchange");
  });
});
