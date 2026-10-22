/**
 * #7382 — the desktop lead hero prints up to six of its own priced rungs; side
 * cards and narrow widths keep three.
 *
 * At 1280px the lead spans both grid rows, so its height is the two side cards
 * stacked beside it (421px), not its content. With three rungs it carried a
 * 196px blank band (production 2026-10-22 03:52Z, "Oscar Winner: Best Picture",
 * 41 outcomes). The trending rows now carry six (backend
 * `test_entertainment_trending_carries_six_rungs_7382.py`), and this file pins
 * the page half:
 *
 *   ARM 1  the lead renders min(6, served) rungs, in served order, real values;
 *   ARM 2  rungs 4–6 carry `leadRowExtra` and rungs 1–3 never do;
 *   ARM 3  each side card renders three rungs even when six are served;
 *   ARM 4  a sparse lead prints what it has — no pad, no extra marker;
 *   ARM 5  the stylesheet hides `leadRowExtra` at <=900px and restores the side
 *          cards' 12px / 4px / 6px scale there, so the phone card is unchanged.
 *
 * jest applies no media query, so ARM 5 reads the stylesheet text, the way
 * `entertainmentLeadReservesNothingItCannotFill7356.test.ts` does.
 */

import fs from "fs";
import path from "path";
import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { EntertainmentData, EntMarketRow } from "@/lib/api";

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: (global as never as { __ENT__: EntertainmentData }).__ENT__, error: undefined }),
}));
jest.mock("@/hooks", () => ({
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
}));
jest.mock("@/lib/tmdb", () => ({
  hasTMDBToken: () => false,
  searchMovie: async () => null,
  posterUrl: (p: string) => p,
}));

import EntertainmentPage from "@/app/entertainment/page";

// Parser helpers copied from `entertainmentHeroLeadFillsItsCard5953.test.tsx`.
interface Node {
  tag: string;
  attrs: string;
  children: Node[];
  parent: Node | null;
}

const VOID = new Set([
  "area", "base", "br", "col", "embed", "hr", "img", "input",
  "link", "meta", "param", "source", "track", "wbr",
]);

function parse(html: string): Node {
  const root: Node = { tag: "#root", attrs: "", children: [], parent: null };
  let cur = root;
  /* The three attribute branches are DISJOINT on their first character, and
     that is load bearing rather than tidy. Written with `[^>]` as the catch-all
     — which can also match a quote — `""` is matchable two ways and CodeQL
     rejects the file outright: `js/redos`, high severity, "may cause
     exponential backtracking on strings starting with '<A' and containing many
     repetitions of '\"\"'". Excluding quotes from the catch-all makes exactly
     one branch able to consume a quote, so there is nothing to backtrack over.
     The cost is that an UNTERMINATED quote inside a tag stops that tag matching
     — `renderToStaticMarkup` never emits one, and a silently skipped tag would
     red the depth arms rather than pass them. */
  const re = /<(\/?)([a-zA-Z][a-zA-Z0-9-]*)((?:"[^"]*"|'[^']*'|[^>"'])*?)(\/?)>/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) !== null) {
    const [, closing, tag, attrs, selfClose] = m;
    const name = tag.toLowerCase();
    if (closing) {
      // Tolerate a stray close only by refusing to walk above the root.
      if (cur.parent) cur = cur.parent;
      continue;
    }
    const node: Node = { tag: name, attrs, children: [], parent: cur };
    cur.children.push(node);
    if (!selfClose && !VOID.has(name)) cur = node;
  }
  return root;
}

function walk(n: Node, out: Node[] = []): Node[] {
  for (const c of n.children) {
    out.push(c);
    walk(c, out);
  }
  return out;
}

/** Inline `style="a:b;c:d"` -> a lookup, so property ORDER cannot decide a test. */
function styleOf(n: Node): Record<string, string> {
  const m = /\bstyle="([^"]*)"/.exec(n.attrs);
  if (!m) return {};
  const out: Record<string, string> = {};
  for (const decl of m[1].split(";")) {
    const i = decl.indexOf(":");
    if (i > 0) out[decl.slice(0, i).trim()] = decl.slice(i + 1).trim();
  }
  return out;
}

function classOf(n: Node): string {
  return (/\bclass="([^"]*)"/.exec(n.attrs) || [, ""])[1] as string;
}


/* The production lead's field, `/api/futures/6173044` read 2026-10-22 04:08Z,
   priced legs in price order — two more than the six-rung ceiling, so ARM 1
   proves the page slices rather than echoing whatever the payload carries. */
const OSCAR = [
  { name: "The Odyssey", prob: 45.5, delta_24h: 0 },
  { name: "You Can See Everything", prob: 24.5, delta_24h: 0 },
  { name: "The Black Ball", prob: 16.5, delta_24h: 0 },
  { name: "Dune: Part Three", prob: 9.5, delta_24h: 0 },
  { name: "Wild Horse Nine", prob: 2.5, delta_24h: 0 },
  { name: "Artificial", prob: 1.5, delta_24h: 0 },
  { name: "Seventh Rung", prob: 1.0, delta_24h: 0 },
  { name: "Eighth Rung", prob: 0.5, delta_24h: 0 },
];

function market(over: Partial<EntMarketRow> = {}): EntMarketRow {
  return {
    q: "Oscar Winner: Best Picture",
    prob: 45.5,
    src: "kalshi",
    market_id: 6173044,
    external_id: "KXOSCARPIC-27",
    kind: "multi",
    top_outcomes: OSCAR,
    outcome_count: 41,
    volume_24h: 59366,
    resolution_date: "2027-12-31T15:00:00+00:00",
    image_url: null,
    hook: null,
    ...over,
  };
}

const SIDE_SIX = OSCAR.slice(0, 6).map((o, i) => ({ ...o, name: `Side ${i + 1}` }));
const SIDES: EntMarketRow[] = [2, 3, 4, 5].map((id) =>
  market({ q: `Side market ${id}`, market_id: id, outcome_count: 16, top_outcomes: SIDE_SIX }),
);

function entData(trending: EntMarketRow[]): EntertainmentData {
  const empty = { count: 0, side_markets: [] };
  return {
    total_markets: 97,
    updated_at: "2026-10-22T03:05:00Z",
    trending,
    themes: {
      music: { ...empty, spotify_race: [], billboard_watch: [], billboard_groups: [], album_drops: [], artist_streaming: [] },
      movies_tv: { ...empty, rt_groups: [], rt_markets: [], box_office_groups: [], box_office: [], reality_tv: [] },
      tech_culture: { count: 0, markets: [] },
    },
    cultural_moments: [],
    by_source: { kalshi: 0, polymarket: 0 },
  };
}

function renderHero(lead: EntMarketRow = market()) {
  (global as never as { __ENT__: EntertainmentData }).__ENT__ = entData([lead, ...SIDES]);
  const html = renderToStaticMarkup(React.createElement(EntertainmentPage));
  const grid = walk(parse(html)).find((n) => /heroGrid/.test(classOf(n))) as Node;
  expect(grid).toBeTruthy();
  expect(grid.children).toHaveLength(5);
  return grid;
}

const leadRows = (cell: Node) =>
  walk(cell).filter((n) => /data-testid="ent-lead-row"/.test(n.attrs));

/** A side card's rung: the `auto 1fr auto` grid row the side branch prints. */
const sideRows = (cell: Node) =>
  walk(cell).filter((n) => styleOf(n)["grid-template-columns"] === "auto 1fr auto");

/** The text of a node's subtree, from the raw markup the parser skipped. */
function textOf(html: string): string {
  return html.replace(/<[^>]*>/g, "");
}

describe("#7382 — the desktop lead shows more of its own field", () => {
  it("ARM 1: the lead renders six rungs of eight served, in served order", () => {
    const lead = renderHero().children[0];
    expect(leadRows(lead)).toHaveLength(6);
    // Each row's own markup, in document order: row i names served rung i.
    const html = renderToStaticMarkup(React.createElement(EntertainmentPage));
    const segments = html.split('data-testid="ent-lead-row"').slice(1).map(textOf);
    expect(segments).toHaveLength(6);
    OSCAR.slice(0, 6).forEach((o, i) => expect(segments[i]).toContain(o.name));
    expect(html).not.toContain("Seventh Rung");
    expect(html).not.toContain("Eighth Rung");
  });

  it("ARM 2: rungs 4–6 are marked narrow-hidden, rungs 1–3 never are", () => {
    const rows = leadRows(renderHero().children[0]);
    expect(rows.map((r) => /leadRowExtra/.test(classOf(r)))).toEqual([
      false, false, false, true, true, true,
    ]);
  });

  it("ARM 3: every side card renders three rungs although six are served", () => {
    const grid = renderHero();
    for (const cell of grid.children.slice(1)) {
      expect(leadRows(cell)).toHaveLength(0);
      expect(sideRows(cell)).toHaveLength(3);
    }
  });

  it("ARM 4: a sparse lead prints what it has — no pad, no extra marker", () => {
    const three = leadRows(renderHero(market({ outcome_count: 3, top_outcomes: OSCAR.slice(0, 3) })).children[0]);
    expect(three).toHaveLength(3);
    expect(three.some((r) => /leadRowExtra/.test(classOf(r)))).toBe(false);

    const four = leadRows(renderHero(market({ outcome_count: 4, top_outcomes: OSCAR.slice(0, 4) })).children[0]);
    expect(four).toHaveLength(4);

    // A one-leg contract keeps the binary body; it never becomes a rung list.
    const binary = renderHero(
      market({ kind: "binary", outcome_count: 1, prob: 51, top_outcomes: [{ name: "Yes", prob: 51, delta_24h: 0 }] }),
    ).children[0];
    expect(leadRows(binary)).toHaveLength(0);
  });
});

describe("#7382 ARM 5 — narrow widths keep the card they had", () => {
  const CSS = fs
    .readFileSync(path.join(__dirname, "..", "app", "entertainment", "entertainment.module.css"), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "");

  function body(selector: string, scope: string): string {
    const re = new RegExp(`(^|[},])\\s*([^{}]*?\\${selector}(?![\\w-])[^{}]*?)\\{`, "m");
    const m = re.exec(scope);
    if (!m) throw new Error(`#7382 guard: no rule for "${selector}"`);
    const open = scope.indexOf("{", m.index + m[1].length);
    return scope.slice(open + 1, scope.indexOf("}", open));
  }

  function narrowBlock(): string {
    const at = CSS.indexOf("@media (max-width: 900px)");
    expect(at).toBeGreaterThan(-1);
    const open = CSS.indexOf("{", at);
    let depth = 0;
    for (let i = open; i < CSS.length; i++) {
      if (CSS[i] === "{") depth++;
      else if (CSS[i] === "}" && --depth === 0) return CSS.slice(open + 1, i);
    }
    throw new Error("unbalanced 900px block");
  }

  const decl = (b: string, prop: string) =>
    (new RegExp(`(?:^|;)\\s*${prop}\\s*:\\s*([^;]+)`).exec(b) || [])[1]?.trim();

  it("hides rungs 4–6 at <=900px", () => {
    expect(decl(body(".leadRowExtra", narrowBlock()), "display")).toBe("none");
  });

  it("restores the side cards' 12px number, 4px bar, 6px gap and 12px name there", () => {
    const rows = body(".leadRows", narrowBlock());
    expect(decl(rows, "--ent-lead-pct")).toBe("12px");
    expect(decl(rows, "--ent-lead-bar")).toBe("4px");
    expect(decl(rows, "gap")).toBe("6px");
    expect(decl(body(".leadRowName", narrowBlock()), "font-size")).toBe("12px");
  });

  it("the desktop rule is the lead scale, and is not itself inside a media block", () => {
    const desk = body(".leadRows", CSS.slice(0, CSS.indexOf("@media")));
    expect(decl(desk, "--ent-lead-pct")).toBe("14px");
    expect(decl(desk, "--ent-lead-bar")).toBe("6px");
    expect(decl(desk, "gap")).toBe("10px");
  });
});
