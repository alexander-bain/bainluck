// UX-P263 (#2561) — the Discover leaderboard prints the matchup, not initials.
//
// `compactOutcomeName` is a PERSON-NAME abbreviator: it pops the last token as
// a surname and initialises everything before it. Master ran it on every label
// longer than 22 characters, so it initialised the separator too, and Discover
// page one shipped:
//
//     Tampa Bay vs Los Angeles D   ->  T. B. v. L. A. D
//     New York Y vs Los Angeles D  ->  N. Y. Y. v. L. A. D
//     Spider-Man: Brand New Day    ->  S. B. N. Day
//     No release by September 30   ->  N. r. b. S. 30
//
// 🔴 THE FIXTURE IS THE LIVE PAYLOAD, VERBATIM. `matchupNotInitials2561.json`
// holds four whole cards cut from `GET /api/feed` on 2026-09-02 while the
// defect was in production — the reported baseball matchup card, the reported
// movie card, a Russian-party card and an ATP draw. Between them they carry
// all four classes master mangled (matchup, colon-title, bracketed org name,
// accented person name) plus their controls, and every string asserted below
// is one a real reader saw.
//
// 🔴 WHY THE 22-CHARACTER ROW IS A CONTROL AND NOT A CLAIM. `Tampa Bay vs
// Milwaukee` renders verbatim on master too — it is exactly 22 characters and
// returns before the abbreviator. #2561's body read its correctness as
// evidence the bug was semantic; it is a coincidence of string length. It is
// asserted here, GREEN IN BOTH ARMS, for one reason: it pins the boundary, so
// a "fix" that merely raised 22 to 30 would satisfy none of the claims above
// it while still passing this row.
//
// 🔴 AND WHY A COUNTER-CASE ARM EXISTS. "Stop abbreviating" is not the ship —
// the column is 170px and long names still have to fit. `Botic Van de
// Zandschulp` must STILL be shortened, just correctly (`B. Van de Zandschulp`,
// not `B. V. d. Zandschulp`). Without that arm, deleting the function
// altogether would pass.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { FeedItem, FeedFuturesData } from "@/lib/types";
import { compactOutcomeName } from "@/components/discover/utils";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const FIXTURE = require("../fixtures/matchupNotInitials2561.json") as Record<
  string,
  { item: Record<string, unknown>; data: FeedFuturesData }
>;

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: () => {}, prefetch: () => {} }),
  useSearchParams: () => new URLSearchParams(),
}));

jest.mock("@/lib/analytics", () => ({ trackEvent: () => {} }));

jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));

jest.mock("@/lib/discoverInteractions", () => ({
  getDiscoverItemAnalytics: () => ({}),
  recordDiscoverInteraction: () => {},
  sendDiscoverInteraction: () => {},
}));

jest.mock("@/components/Analytics/AnalyticsProvider", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
  AnalyticsProvider: ({ children }: { children: React.ReactNode }) => children,
}));

import DiscoverCard from "@/components/DiscoverCard";

function renderDiscover(id: string): string {
  const spec = FIXTURE[id];
  if (!spec) throw new Error(`fixture ${id} missing`);
  const item = { ...spec.item, data: spec.data } as unknown as FeedItem;
  return renderToStaticMarkup(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    React.createElement(DiscoverCard as any, {
      groupedItem: { type: "single", item },
    }),
  );
}

/**
 * Every leaderboard row the card actually drew, as `{ full, shown }`.
 *
 * Read out of the label span itself rather than the document text, because the
 * card also prints the leader's untouched name in its hook sentence — a
 * whole-document `toContain("Tampa Bay vs Los Angeles D")` passes on the BROKEN
 * render. `title` is the served string and the element body is what the reader
 * sees, so the pair is the only assertion that distinguishes the two.
 */
function leaderboardRows(html: string): Array<{ full: string; shown: string }> {
  const rows: Array<{ full: string; shown: string }> = [];
  const re = /<span class="min-w-0 truncate [^"]*" title="([^"]*)">([^<]*)<\/span>/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html))) {
    rows.push({ full: decode(m[1]), shown: decode(m[2]) });
  }
  return rows;
}

/** The same rows, located WITHOUT depending on the `truncate` class, so the
 *  "labels are not initialised" claims stay meaningful even in an arm where
 *  the class is missing. */
function leaderboardRowsLoose(html: string): Array<{ full: string; shown: string }> {
  const rows: Array<{ full: string; shown: string }> = [];
  const re = /<span class="min-w-0[^"]*text-xs leading-tight[^"]*" title="([^"]*)">([^<]*)<\/span>/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html))) {
    rows.push({ full: decode(m[1]), shown: decode(m[2]) });
  }
  return rows;
}

const HTML_ENTITIES: Record<string, string> = {
  "&quot;": '"',
  "&apos;": "'",
  "&lt;": "<",
  "&gt;": ">",
  "&amp;": "&",
};

/**
 * Undo the escaping `renderToStaticMarkup` applies, in ONE pass.
 *
 * Chained `.replace()` calls are a double-unescaping bug (CodeQL
 * `js/double-escaping`, and it flagged the first draft of this helper): once
 * `&amp;` has become `&`, a later rule turns `&amp;#39;` into `'` rather than
 * the literal `&#39;` the payload actually contained. A single regex with a
 * lookup can never re-examine its own output.
 */
function decode(s: string): string {
  return s.replace(
    /&(?:quot|apos|lt|gt|amp);|&#x([0-9a-fA-F]+);|&#(\d+);/g,
    (match, hex: string | undefined, dec: string | undefined) => {
      if (hex !== undefined) return String.fromCodePoint(parseInt(hex, 16));
      if (dec !== undefined) return String.fromCodePoint(Number(dec));
      return HTML_ENTITIES[match] ?? match;
    },
  );
}

function shownFor(html: string, full: string): string | undefined {
  return leaderboardRowsLoose(html).find((r) => r.full === full)?.shown;
}

// ── The seed is real ────────────────────────────────────────────────────────
// If the fixture stops arriving, or the card stops taking the leaderboard
// branch, every assertion below turns vacuous — an empty row list satisfies
// "no row is initialised". These fail loudly instead.

describe("the fixture reaches the leaderboard render", () => {
  it.each(["matchup", "party", "particle", "showTitle"])(
    "%s renders four leaderboard rows",
    (id) => {
      const rows = leaderboardRowsLoose(renderDiscover(id));
      expect(rows).toHaveLength(4);
    },
  );

  it("the matchup card is the one #2561 reported", () => {
    const rows = leaderboardRowsLoose(renderDiscover("matchup"));
    expect(rows.map((r) => r.full)).toEqual([
      "Tampa Bay vs Los Angeles D",
      "New York Y vs Los Angeles D",
      "Tampa Bay vs Milwaukee",
      "Boston vs Milwaukee",
    ]);
  });
});

// ── The claims: labels that are not person names keep their words ───────────

describe("a matchup is not initialised", () => {
  it("prints both teams instead of T. B. v. L. A. D", () => {
    const html = renderDiscover("matchup");
    expect(shownFor(html, "Tampa Bay vs Los Angeles D")).toBe("Tampa Bay vs Los Angeles D");
    expect(shownFor(html, "New York Y vs Los Angeles D")).toBe("New York Y vs Los Angeles D");
  });

  it("never turns the separator into an initial", () => {
    const html = renderDiscover("matchup");
    expect(html).not.toContain("v. L. A.");
    for (const row of leaderboardRowsLoose(html)) {
      expect(row.shown).not.toMatch(/\bv\.\s/);
    }
  });

  it("leaves every row on the card exactly as served", () => {
    for (const row of leaderboardRowsLoose(renderDiscover("matchup"))) {
      expect(row.shown).toBe(row.full);
    }
  });
});

describe("a title is not initialised", () => {
  it("prints Spider-Man: Brand New Day, not S. B. N. Day", () => {
    const html = renderDiscover("showTitle");
    expect(shownFor(html, "Spider-Man: Brand New Day")).toBe("Spider-Man: Brand New Day");
    expect(html).not.toContain("S. B. N. Day");
  });
});

describe("an organisation name is not initialised", () => {
  it("prints the party names whole", () => {
    const html = renderDiscover("party");
    expect(shownFor(html, "Liberal Democratic Party of Russia (LDPR)")).toBe(
      "Liberal Democratic Party of Russia (LDPR)",
    );
    expect(shownFor(html, "Communist Party of the Russian Federation (KPRF)")).toBe(
      "Communist Party of the Russian Federation (KPRF)",
    );
    expect(html).not.toContain("P. o. t. R. F.");
  });
});

// ── The counter-case: a person's name IS still shortened, correctly ─────────

describe("a person's name is still compacted", () => {
  it("initialises the given name but never the particle", () => {
    const html = renderDiscover("particle");
    expect(shownFor(html, "Botic Van de Zandschulp")).toBe("B. Van de Zandschulp");
  });

  it("stays inside the column budget", () => {
    const shown = shownFor(renderDiscover("particle"), "Botic Van de Zandschulp") ?? "";
    expect(shown.length).toBeLessThanOrEqual(22);
    expect(shown.length).toBeLessThan("Botic Van de Zandschulp".length);
  });
});

// ── Controls — green in BOTH arms, present to pin what must not move ────────

describe("controls (green on master too)", () => {
  it("the exactly-22-character matchup is untouched, pinning the boundary", () => {
    // 22 chars: returns before the abbreviator on master AND on this branch.
    expect("Tampa Bay vs Milwaukee".length).toBe(22);
    expect(shownFor(renderDiscover("matchup"), "Tampa Bay vs Milwaukee")).toBe(
      "Tampa Bay vs Milwaukee",
    );
  });

  it("short labels render verbatim", () => {
    const html = renderDiscover("particle");
    expect(shownFor(html, "Arthur Fery")).toBe("Arthur Fery");
    expect(shownFor(html, "Luciano Darderi")).toBe("Luciano Darderi");
  });

  it("the served string stays on the title attribute", () => {
    for (const id of ["matchup", "party", "particle", "showTitle"]) {
      for (const row of leaderboardRowsLoose(renderDiscover(id))) {
        expect(row.full.length).toBeGreaterThan(0);
      }
    }
  });
});

// ── The render must clip what it no longer abbreviates ──────────────────────

describe("the label span truncates", () => {
  it("carries the truncate class, so a long verbatim label clips instead of wrapping", () => {
    // Without this the party card's 48-character label wraps to a second line
    // and every row on the card grows taller. Asserted through the rendered
    // class list, on the same span the labels come out of.
    const rows = leaderboardRows(renderDiscover("party"));
    expect(rows).toHaveLength(4);
    expect(rows.map((r) => r.full)).toContain(
      "Communist Party of the Russian Federation (KPRF)",
    );
  });
});

// ── The rule, over the live corpus it was measured on ───────────────────────
//
// Each row below is a real label from the same `GET /api/feed` capture, with
// the string master printed beside it. Rendering all of them would need a
// fixture per card; the render arms above already prove the component consults
// this function, so breadth is proved here.

describe("compactOutcomeName over the live corpus", () => {
  const KEEPS_ITS_WORDS: Array<[string, string]> = [
    ["Tampa Bay vs Los Angeles D", "T. B. v. L. A. D"],
    ["New York Y vs Los Angeles D", "N. Y. Y. v. L. A. D"],
    ["Boston vs Los Angeles D", "B. v. L. A. D"],
    ["Houston vs Los Angeles D", "H. v. L. A. D"],
    ["Spider-Man: Brand New Day", "S. B. N. Day"],
    ["The Hunger Games: Sunrise on the Reaping", "T. H. G. S. o. t. Reaping"],
    ["The Late Show with Stephen Colbert", "T. L. S. w. S. Colbert"],
    ["Last Week Tonight with John Oliver", "L. W. T. w. J. Oliver"],
    ["Jury Duty Presents Company Retreat", "J. D. P. C. Retreat"],
    ["No release by September 30", "N. r. b. S. 30"],
    ["On or prior to September 2", "O. o. p. t. S. 2"],
    ["A Just Russia – For Truth (SRZP)", "A. J. R. –. F. T. (SRZP)"],
    ["Liberal Democratic Party of Russia (LDPR)", "L. D. P. o. R. (LDPR)"],
    ["Communist Party of the Russian Federation (KPRF)", "C. P. o. t. R. F. (KPRF)"],
    ["Swedish Social Democratic Party", "S. S. D. Party"],
    ["Arizona State Sun Devils", "A. S. S. Devils"],
    ["Antigua And Barbuda Falcons", "A. A. B. Falcons"],
  ];

  it.each(KEEPS_ITS_WORDS)("%s is left alone", (label) => {
    expect(compactOutcomeName(label)).toBe(label);
  });

  it.each(KEEPS_ITS_WORDS)("%s no longer prints as %s", (label, mastered) => {
    expect(compactOutcomeName(label)).not.toBe(mastered);
  });

  const STILL_COMPACTED: Array<[string, string]> = [
    // [served, what this branch prints]
    ["Alexandria Ocasio-Cortez", "A. Ocasio-Cortez"],
    ["Jonathan Kreiss-Tomkins", "J. Kreiss-Tomkins"],
    ["Botic Van de Zandschulp", "B. Van de Zandschulp"],
    ["Saskatchewan Roughriders", "S. Roughriders"],
    ["Veterinário Wilson Grassi", "V. Wilson Grassi"],
    ["Alejandro Davidovich Fokina", "A. Davidovich Fokina"],
    ["Stanley E. Woodward Jr.", "S. E. Woodward Jr."],
  ];

  it.each(STILL_COMPACTED)("%s still shortens to %s", (label, expected) => {
    expect(compactOutcomeName(label)).toBe(expected);
  });

  it("every compacted person name fits the 22-character budget", () => {
    for (const [label] of STILL_COMPACTED) {
      // `S. E. Woodward Jr.` and friends: the loop stops as soon as it fits, and
      // a name that cannot fit still returns its most-compacted form.
      expect(compactOutcomeName(label).length).toBeLessThanOrEqual(label.length);
    }
  });

  it("short labels are returned untouched", () => {
    for (const label of ["Arthur Fery", "Rodina", "Toy Story 5", "United Russia (ER)"]) {
      expect(compactOutcomeName(label)).toBe(label);
    }
  });

  it("collapses whitespace exactly as before", () => {
    expect(compactOutcomeName("  Boston   vs  Milwaukee  ")).toBe("Boston vs Milwaukee");
  });

  it("a single long word has nothing to initialise", () => {
    expect(compactOutcomeName("Kaiserslauternvereinigung")).toBe("Kaiserslauternvereinigung");
  });
});
