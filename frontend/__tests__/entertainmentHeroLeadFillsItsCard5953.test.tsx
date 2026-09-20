/**
 * #5953 — the /entertainment lead hero card reserved up to 227px it could not fill.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `/entertainment`, production 2026-09-13, release v4493. The lead card —
 * "Which movie has biggest opening weekend in 2026?" — ended at its source
 * mark and then ran on as white space to the bottom of the grid row:
 *
 *     1280px  hole 227px of a 421px card (54%)
 *      800px  hole  86px
 *      390px  hole  86px
 *
 * lane1b found it on its own owed AFTER-LOOK for #5926 (which stopped the page
 * serving retired-prompt prose). The prose had been filling the card.
 *
 * ═══ WHY THE THREE CANDIDATE REPAIRS IN #5953 ARE ALL THE WRONG SHAPE ═══
 *
 * The issue offered: release `.heroCardLead { min-height }` and the grid's
 * two-row span; or fill the space with more outcome rungs; or centre the
 * content in the reserved box. All three treat the RESERVATION as the cause.
 * It is not. It only made the breakage visible.
 *
 * `HeroCardContent` opens with a header and then a `<div style={{ flex: 1 }} />`
 * whose entire job is to push `CardBodyByKind` and `MetaRow` to the bottom of
 * the card. The four sibling cards hand `inner` straight into `.heroCard` — a
 * flex column — and wrap their `<Link>` on the OUTSIDE. The lead card wrapped
 * on the INSIDE, so `.heroCardLead`'s flex column held exactly one item, the
 * `<a>`, and the spacer was a child of the `<a>` rather than of the flex
 * container. `flex-grow` only grows against the container you are an item of,
 * so it resolved to 0px.
 *
 * MEASURED ON PRODUCTION, `tools/ent-hero-lead-fill-5953.mjs` at 1280px, with
 * the four siblings as the control — which is the whole weight of the finding,
 * because they render the SAME `HeroCardContent`:
 *
 *     LEAD  h=421 minH=280 flex/column  HOLE=227
 *             item <A> block grow=0 h=157 kids=4
 *             spacer grow=1 h=0px parent=<A> flexCol=false -> INERT
 *     side  h=205 minH=0   flex/column  HOLE=1      (x4)
 *             spacer grow=1 h=16px parent=<DIV> flexCol=true -> GROWS
 *
 * One component, filling in four cards and not in the fifth ⇒ structural.
 *
 * ═══ WHAT THIS FILE CAN AND CANNOT PROVE ═══
 *
 * This suite is `testEnvironment: 'node'` and renders with
 * `renderToStaticMarkup`, so there is no layout engine and no CSSOM. It cannot
 * measure the 227px hole and does not pretend to — the hole is measured by the
 * tool above, against production, and that is where the before/after number
 * comes from.
 *
 * What static markup CAN decide is exactly the thing the tool identified as the
 * mechanism: the flex CHAIN. A `flex: 1` spacer grows if and only if its parent
 * is a flex column. Nesting is fully determined by the markup, so:
 *
 *   ARM 1  the lead's <a> declares `display:flex` + `flex-direction:column`
 *   ARM 2  it declares `flex:1`, so it fills the card slot it occupies
 *   ARM 3  the spacer is a DIRECT CHILD of that <a>   <- read from real nesting
 *   ARM 4  the four siblings are untouched: spacer still a direct child of the
 *          card div, and no sibling picked up the lead's inline flex column
 *
 * ARM 3 and ARM 4 are the two that cannot go vacuous. They are computed by
 * walking the rendered tag stream and taking DEPTH, not by matching a style
 * string — so a future refactor that re-introduces any wrapper between the flex
 * column and the spacer reds this file even when every style literal is still
 * correct. That is the precise regression #5953 was.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { EntertainmentData, EntMarketRow } from "@/lib/api";

/* `TrendingHero` is a module-local of `app/entertainment/page.tsx` and MUST stay
   that way: a Next page file may export only the allowlisted route names, and
   exporting it costs a real typecheck error
   (`OmitWithTag<...> does not satisfy '{ [x: string]: never }'`, measured).
   So this guard mounts the page's DEFAULT export — the real component tree, the
   real CSS-module class names, the real grid — and finds the hero in the
   rendered markup. Nothing in `app/` changed shape to make this file possible,
   which is the point: a guard that needs the production code rearranged to be
   testable is testing the rearrangement. */
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

// ─────────────────────────────────────────────────────────────────────────────
// A depth walker over rendered static markup.
//
// There is no HTML parser in this workspace (checked: no jsdom, cheerio, parse5
// or htmlparser2) and the suite runs in `node`, so nesting is recovered from the
// tag stream directly. This is sound for `renderToStaticMarkup` output, which
// emits no comments, no CDATA, no unclosed tags and no raw `>` inside an
// attribute value — the three things that make ad-hoc HTML scanning wrong.
// ─────────────────────────────────────────────────────────────────────────────

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

/** The spacer: an empty div whose only job is `flex: 1`. Exactly one per card. */
function spacerIn(card: Node): Node {
  const found = walk(card).filter(
    (n) => n.tag === "div" && n.children.length === 0 && styleOf(n).flex === "1",
  );
  expect(found).toHaveLength(1);
  return found[0];
}

// ─────────────────────────────────────────────────────────────────────────────

function market(over: Partial<EntMarketRow> = {}): EntMarketRow {
  return {
    q: "Which movie has biggest opening weekend in 2026?",
    prob: 0.53,
    src: "polymarket",
    market_id: 12345,
    external_id: "ext-12345",
    kind: "boxoffice",
    top_outcomes: [
      { name: "Avengers: Doomsday", prob: 0.53, delta_24h: 0.01 },
      { name: "Spider-Man: Brand New Day", prob: 0.41, delta_24h: -0.01 },
      { name: "Dune: Messiah", prob: 0.004, delta_24h: 0 },
    ],
    outcome_count: 6,
    volume_24h: 67000,
    resolution_date: "2026-12-30T00:00:00Z",
    image_url: null,
    /* The prose #5926 retired. Absent is the POST-#5926 shape and therefore the
       shape the defect lives on — a fixture that still carried a hook would fill
       the card by accident and this file would prove nothing. */
    hook: null,
    ...over,
  };
}

/** The five markets the live grid renders: one lead + four siblings. */
const MARKETS: EntMarketRow[] = [
  market(),
  market({ q: "Oscar Winner: Best Picture", market_id: 2, kind: "market" }),
  market({ q: "Next James Bond film", market_id: 3, kind: "market" }),
  market({ q: "Big Brother Season 28 · Winner", market_id: 4, kind: "reality" }),
  market({ q: "#2 on the Billboard 200", market_id: 5, kind: "billboard" }),
];

/** A complete `EntertainmentData` whose only interesting field is `trending`. */
function entData(trending: EntMarketRow[]): EntertainmentData {
  const empty = { count: 0, side_markets: [] };
  return {
    total_markets: 1002,
    updated_at: "2026-09-13T22:30:00Z",
    trending,
    themes: {
      music: {
        ...empty,
        spotify_race: [],
        billboard_watch: [],
        billboard_groups: [],
        album_drops: [],
        artist_streaming: [],
      },
      movies_tv: {
        ...empty,
        rt_groups: [],
        rt_markets: [],
        box_office_groups: [],
        box_office: [],
        reality_tv: [],
      },
      tech_culture: { count: 0, markets: [] },
    },
    cultural_moments: [],
    by_source: { kalshi: 0, polymarket: 0 },
  };
}

/** Mount the real page and return the hero grid out of the rendered markup. */
function renderHero(markets: EntMarketRow[] = MARKETS) {
  (global as never as { __ENT__: EntertainmentData }).__ENT__ = entData(markets);
  const html = renderToStaticMarkup(React.createElement(EntertainmentPage));
  const grid = walk(parse(html)).find((n) => /heroGrid/.test(classOf(n)));
  return { html, grid: grid as Node };
}

describe("#5953 — the lead hero card's spacer can actually grow", () => {
  it("mounts the real grid: one lead cell and four sibling cells", () => {
    const { grid } = renderHero();
    expect(grid).toBeTruthy();
    expect(grid.children).toHaveLength(5);
    expect(classOf(grid.children[0])).toMatch(/heroCardLead/);
    for (const c of grid.children.slice(1)) {
      expect(classOf(c)).not.toMatch(/heroCardLead/);
    }
  });

  it("ARM 1+2: the lead's <a> is a flex column that fills its card", () => {
    const { grid } = renderHero();
    const anchors = walk(grid.children[0]).filter((n) => n.tag === "a");
    expect(anchors).toHaveLength(1);
    const st = styleOf(anchors[0]);
    expect(st.display).toBe("flex");
    expect(st["flex-direction"]).toBe("column");
    expect(st.flex).toBe("1");
  });

  it("ARM 3: the spacer is a DIRECT child of that flex column", () => {
    const { grid } = renderHero();
    const lead = grid.children[0];
    const anchor = walk(lead).filter((n) => n.tag === "a")[0];
    const spacer = spacerIn(lead);

    // Depth, not a style string. Before the fix the parent was also the <a> —
    // but the <a> was not a flex column, which ARM 1 catches. After any future
    // refactor that re-wraps `inner`, THIS is what reds.
    expect(spacer.parent).toBe(anchor);
    const st = styleOf(anchor);
    expect(st.display).toBe("flex");
    expect(st["flex-direction"]).toBe("column");
  });

  it("ARM 4: the four siblings are untouched — spacer still a direct child of the flex card", () => {
    const { grid } = renderHero();
    for (const cell of grid.children.slice(1)) {
      const card = walk(cell).find((n) => /heroCard/.test(classOf(n)));
      expect(card).toBeTruthy();
      const spacer = spacerIn(cell);
      // The sibling grammar: Link OUTSIDE, `inner` handed straight to the card,
      // so the spacer's parent is the card div itself.
      expect(spacer.parent).toBe(card);
      // And no sibling acquired the lead's inline flex column.
      expect(styleOf(card as Node).display).not.toBe("flex");
    }
  });

  it("the lead is still a link to its own market, and still the lead", () => {
    const { grid } = renderHero();
    const lead = grid.children[0];
    const anchor = walk(lead).filter((n) => n.tag === "a")[0];
    expect(anchor.attrs).toContain('href="/futures/12345"');
    /* THE RESERVATION IS GONE — #7356, and this comment used to say the opposite.
       It read: "deliberately LEFT IN PLACE … with the spacer live it is a floor
       the content fills, and it is what keeps the lead reading as the lead on a
       phone." The first half was true at 1280px and false below 900px, where the
       content did NOT fill it and the now-live spacer rendered the surplus as one
       55px blank block between the title and the first outcome. The second half
       was never tested: the lead reads as the lead on the marks the card actually
       carries — a 72px cover against the siblings' 44px, an 18px title against
       14px, 18px padding against 14px — and all three survive.
       Nothing in THIS file changes. The fix above is the one that matters at
       1280px, where the grid still holds the card open and the spacer still fills
       196px of it; #7356 only stopped the card reserving a height the grid was
       not asking for. The stylesheet half is pinned in
       `entertainmentLeadReservesNothingItCannotFill7356.test.ts`. */
    expect(classOf(lead)).toMatch(/heroLead/);
  });

  it("renders no hero grid at all below two markets (unchanged guard)", () => {
    const { grid } = renderHero([market()]);
    expect(grid).toBeUndefined();
  });

  it("the depth walker itself is not vacuous", () => {
    // A walker that returned a flat list, or that never set `parent`, would make
    // ARM 3 and ARM 4 pass against anything. Pin it on markup with a known shape.
    const root = parse(
      '<div id="a"><span id="b"><i id="c"></i></span><img id="d"/><b id="e"></b></div>',
    );
    const a = root.children[0];
    expect(a.children.map((n) => n.tag)).toEqual(["span", "img", "b"]);
    const c = walk(a).find((n) => n.tag === "i") as Node;
    // `i` is a GRANDCHILD: a walker that flattened would report `a` here.
    expect(c.parent?.tag).toBe("span");
    expect(c.parent).not.toBe(a);
    // A void element must not swallow its siblings.
    expect(a.children[1].children).toHaveLength(0);
  });
});
