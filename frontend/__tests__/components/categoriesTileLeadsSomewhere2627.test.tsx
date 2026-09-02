// #2627 — EVERY TILE IN THE BROWSE GRID LEADS SOMEWHERE.
//
// ═══ WHAT WAS ON SCREEN ═══
//
// `/categories` draws 29 tiles. Two of them were doors onto nothing, and they
// were dead for two entirely different reasons:
//
//   Motorsport  "No items"  →  /categories/motorsport   served 0 items
//   Poker       "No items"  →  /categories/poker        served 0 items
//
// Measured against production 2026-09-02 ~02:30 PT, one request each:
//
//     GET /api/feed?limit=50&category=motorsport    items=0
//     GET /api/feed?limit=50&category=motorsports   items=22   ← the same tile,
//                                                                one letter over
//
// ═══ WHY MOTORSPORT WAS DEAD ═══
//
// A category key is not a label. It is used three ways, and all three read a
// store that spells this category in the PLURAL:
//
//   1. `getCategoryForFutures` matches it against `llm_sport_category`.
//   2. `/categories` looks it up in `/api/feed/tag-counts`.
//   3. `/categories/<key>` sends it to the feed as `category=<key>`.
//
// The tile's key was the singular `motorsport`. It was the only singular in the
// tree — `app/preferences`, `app/discover`, `lib/play/kidSafe`,
// `EXCLUDED_SUBCATEGORY_TAGS`, iOS's `DiscoverCategory.swift` and the backend's
// own `_normalize_open_ended_category` (which maps "motorsport" → "motorsports")
// all say plural — so all three readers missed, and 142 open markets sat
// invisible under a key no tile asked for.
//
// ═══ WHY POKER WAS DEAD, WHICH IS NOT THE SAME BUG ═══
//
// `poker` is the correct key. There are 20 poker markets and every one is
// resolved, so there is genuinely nothing to show. That is not a lookup bug, it
// is a tile with no destination — and the destination is empty BY CONSTRUCTION,
// because `/categories/<key>` renders whatever `category=<key>` returns. A grid
// should not offer a door it knows is locked.
//
// ═══ THE FIXTURE ═══
//
// `uxp266_tag_counts.20260902.json` is an unedited `GET /api/feed/tag-counts`
// body, 48 categories. It is what makes the two claims above measurable rather
// than asserted: it carries `motorsports` at 142 futures, carries no
// `motorsport` key at all, and carries no `poker` key at all.
//
// ═══ WHAT IS ASSERTED, AND WHERE ═══
//
// Every claim is read off the markup the real `CategoriesIndexPage` produces —
// not off a re-implementation of its `groups` memo. The filtering under test
// lives inline in that component, so a stand-in would be testing the stand-in.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import tagCounts from "../fixtures/uxp266_tag_counts.20260902.json";

let swrPayload: unknown = tagCounts;

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: swrPayload,
    error: undefined,
    isLoading: false,
    mutate: () => undefined,
  }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
jest.mock("@/hooks", () => ({
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
}));

import CategoriesIndexPage from "../../app/categories/page";
import { SPORT_CATEGORIES, getCategoryForFutures } from "@/lib/sportCategories";

const SPECIAL_KEYS = new Set([
  "politics",
  "entertainment",
  "economics",
  "tech",
  "weather",
  "geopolitics",
  "culture",
]);

/** The same filter `app/categories/page.tsx` applies to build DISPLAY_CATEGORIES. */
const DISPLAYED = SPORT_CATEGORIES.filter(
  (c) => c.prefixes.length > 0 || SPECIAL_KEYS.has(c.key),
);

const COUNTS = (tagCounts as { counts: Record<string, { events: number; futures: number }> })
  .counts;

// A default parameter would swallow the most important arm here: calling
// `render(undefined)` to simulate "SWR has not resolved" would silently fall
// back to the fixture and assert nothing. The payload is required.
function render(payload: unknown): string {
  swrPayload = payload;
  try {
    return renderToStaticMarkup(<CategoriesIndexPage />);
  } finally {
    swrPayload = tagCounts;
  }
}

/**
 * The markup of the single tile whose link is `/categories/<key>`, or null when
 * no such tile was rendered.
 *
 * Anchoring on the href rather than on the visible name is deliberate: "Poker"
 * and "Motorsport" are substrings of other content, and the href is the thing
 * the claim is actually about.
 */
function tileFor(html: string, key: string): string | null {
  const open = html.indexOf(`href="/categories/${key}"`);
  if (open === -1) return null;
  const start = html.lastIndexOf("<a ", open);
  const end = html.indexOf("</a>", open);
  if (start === -1 || end === -1) {
    throw new Error(`found href for ${key} but could not bound its anchor`);
  }
  return html.slice(start, end + 4);
}

// ───────────────────────────────────────────────────────────────────────────
// The fixture's own premises. If any of these stop holding, every claim below
// is measuring something other than what it says it is.
// ───────────────────────────────────────────────────────────────────────────

describe("the banked payload is the one that produced the defect", () => {
  it("carries motorsports (plural) with real markets behind it", () => {
    expect(COUNTS.motorsports).toEqual({ events: 0, futures: 142 });
  });

  it("carries NO singular 'motorsport' key — the tile's old key matched nothing", () => {
    expect(COUNTS.motorsport).toBeUndefined();
  });

  it("carries NO 'poker' key — poker's emptiness is real, not a lookup miss", () => {
    expect(COUNTS.poker).toBeUndefined();
  });

  it("leaves Poker as the only displayed category with no destination", () => {
    // On the parent this list is ["motorsport", "poker"] — two dead doors for
    // two different reasons. After the key fix only the genuinely-empty one is
    // left, which is what makes "hide empty tiles" a one-tile change rather
    // than a redesign of the grid.
    const dead = DISPLAYED.filter((c) => {
      const n = COUNTS[c.key];
      return !n || n.events + n.futures === 0;
    }).map((c) => c.key);
    expect(dead).toEqual(["poker"]);
  });

  it("accounts for all 29 displayed tiles: 28 populated, 1 empty", () => {
    const populated = DISPLAYED.filter((c) => {
      const n = COUNTS[c.key];
      return n && n.events + n.futures > 0;
    });
    expect(DISPLAYED.length).toBe(29);
    expect(populated.length).toBe(28);
  });
});

// ───────────────────────────────────────────────────────────────────────────
// Motorsport — the lookup half.
// ───────────────────────────────────────────────────────────────────────────

describe("the Motorsport tile", () => {
  const html = render(tagCounts);

  it("links to the slug the feed actually answers", () => {
    expect(html).toContain('href="/categories/motorsports"');
  });

  it("no longer links to the slug that serves an empty page", () => {
    expect(html).not.toContain('href="/categories/motorsport"');
  });

  it("prints the 142 markets it was hiding", () => {
    const tile = tileFor(html, "motorsports");
    expect(tile).not.toBeNull();
    expect(tile).toContain("142");
    expect(tile).toContain("market");
  });

  it("does not print 'No items' over a category with 142 markets", () => {
    expect(tileFor(html, "motorsports")).not.toContain("No items");
  });

  it("still calls itself Motorsport — the key changed, the label did not", () => {
    expect(tileFor(html, "motorsports")).toContain("Motorsport");
  });
});

// ───────────────────────────────────────────────────────────────────────────
// Poker — the dead-door half.
// ───────────────────────────────────────────────────────────────────────────

describe("a category with nothing behind it", () => {
  const html = render(tagCounts);

  it("renders no Poker tile at all", () => {
    expect(tileFor(html, "poker")).toBeNull();
  });

  it("leaves no tile anywhere in the grid saying 'No items'", () => {
    expect(html).not.toContain("No items");
  });

  it("leaves no section heading standing above an empty grid", () => {
    // Every rendered group label must be followed by at least one tile before
    // the next label (or the end of the document).
    const labels = ["Major Sports", "More Sports &amp; Topics", "Niche"];
    const present = labels.filter((l) => html.includes(l));
    expect(present.length).toBeGreaterThan(0);
    for (const label of present) {
      const from = html.indexOf(label);
      const nextLabelIdx = present
        .map((l) => html.indexOf(l))
        .filter((i) => i > from)
        .sort((a, b) => a - b)[0];
      const slice = html.slice(from, nextLabelIdx ?? html.length);
      expect(slice).toContain('href="/categories/');
    }
  });
});

// ───────────────────────────────────────────────────────────────────────────
// Fail-open. GREEN IN BOTH ARMS by design: its whole job is to pin that the
// hiding is conditional on counts having arrived, so a fetch that has not
// resolved cannot empty the browse grid.
// ───────────────────────────────────────────────────────────────────────────

describe("when counts have not arrived (green on main too)", () => {
  it("renders every displayed tile when SWR has no data", () => {
    const html = render(undefined);
    for (const cat of DISPLAYED) {
      expect(html).toContain(`href="/categories/${cat.key}"`);
    }
  });

  it("renders every displayed tile when the body has no counts object", () => {
    const html = render({});
    for (const cat of DISPLAYED) {
      expect(html).toContain(`href="/categories/${cat.key}"`);
    }
  });

  it("still shows Poker in that state rather than silently dropping it", () => {
    expect(render(undefined)).toContain('href="/categories/poker"');
  });
});

// ───────────────────────────────────────────────────────────────────────────
// Controls. GREEN IN BOTH ARMS: tiles that were already correct must not move.
// ───────────────────────────────────────────────────────────────────────────

describe("tiles that were already right (green on main too)", () => {
  const html = render(tagCounts);

  it("Darts still links to its own slug and still prints 107 markets", () => {
    const tile = tileFor(html, "darts");
    expect(tile).toContain("107");
    expect(tile).toContain("market");
  });

  it("Soccer still prints both halves of its count", () => {
    const tile = tileFor(html, "soccer");
    expect(tile).toContain("392");
    expect(tile).toContain("event");
    expect(tile).toContain("5264");
  });

  it("renders every tile that has items, whatever the grid's key vocabulary is", () => {
    // Deliberately phrased against DISPLAYED rather than a hardcoded count, so
    // it holds on both arms: on the parent this is the 27 tiles that resolved
    // under the old keys, here it is 28. Either way the invariant is the same —
    // a category with items always gets a door — and only that invariant is
    // asserted, so this cannot go green merely because the fix shrank the grid.
    const populated = DISPLAYED.filter((c) => {
      const n = COUNTS[c.key];
      return n && n.events + n.futures > 0;
    });
    expect(populated.length).toBeGreaterThan(20);
    for (const cat of populated) {
      expect(html).toContain(`href="/categories/${cat.key}"`);
    }
  });
});

// ───────────────────────────────────────────────────────────────────────────
// The class, not the instance. A singular/plural drift between a tile key and
// the store it is looked up in is what caused this; this catches the next one.
// ───────────────────────────────────────────────────────────────────────────

describe("no tile key may drift from the vocabulary it is looked up in", () => {
  it("has no displayed key that misses while a near-miss variant carries items", () => {
    const offenders: string[] = [];
    for (const cat of DISPLAYED) {
      if (COUNTS[cat.key]) continue;
      const variants = [`${cat.key}s`, cat.key.replace(/s$/, "")].filter(
        (v) => v !== cat.key,
      );
      for (const v of variants) {
        const n = COUNTS[v];
        if (n && n.events + n.futures > 0) {
          offenders.push(`${cat.key} → ${v} (${n.events + n.futures} items)`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});

// ───────────────────────────────────────────────────────────────────────────
// The third reader. `getCategoryForFutures` matches `llm_sport_category`
// against the key directly, so the singular key made every motorsports market
// fall through to a regex that knows five series names and no others.
// ───────────────────────────────────────────────────────────────────────────

describe("a market's own llm_sport_category resolves the category", () => {
  // Live names from GET /api/feed?category=motorsports, 2026-09-02. None of
  // these contain f1/nascar/indycar/motogp/wrc, so none of them can be rescued
  // by SPORT_PATTERNS — the llm key is the only thing that can classify them.
  const REGEX_INVISIBLE = [
    "Italian Grand Prix Winner",
    "Gran Premio de Aragon Winner",
    "Milwaukee Mile 1: Fastest Lap",
  ];

  it.each(REGEX_INVISIBLE)("classifies %s from its llm category alone", (name) => {
    const cat = getCategoryForFutures(null, name, undefined, "motorsports");
    expect(cat?.key).toBe("motorsports");
    expect(cat?.name).toBe("Motorsport");
  });

  it("proves those names are genuinely regex-invisible (control for the arm above)", () => {
    for (const name of REGEX_INVISIBLE) {
      expect(getCategoryForFutures(null, name)).toBeUndefined();
    }
  });

  it("still classifies NASCAR by name when no llm category is supplied (green on main too)", () => {
    // Asserted on `name`, not `key`, precisely because `key` is the thing this
    // ship changes — a `key` assertion here would be red on the parent for a
    // reason that has nothing to do with the regex path it exists to protect.
    expect(getCategoryForFutures(null, "NASCAR Cup Series Champion")?.name).toBe(
      "Motorsport",
    );
  });

  it("has not started classifying everything as motorsports (counter-case)", () => {
    expect(getCategoryForFutures(null, "Super Bowl LXI Winner")?.key).toBe("football");
    expect(getCategoryForFutures(null, "Kentucky Derby Winner")?.key).toBe("horse_racing");
  });
});
