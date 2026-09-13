/**
 * A PASTED CATEGORY, BRACKET, SPORT OR LEAGUE LINK UNFURLS AS ITSELF.
 *
 * ═══ WHAT WAS ON PRODUCTION BEFORE THIS, MEASURED 2026-09-13 WITH A CRAWLER UA ═══
 *
 *   /categories/politics  <title>        Bain Luck — Prediction Market Discovery
 *                         og:title       Bain Luck — Prediction Market Discovery
 *                         og:description See what the world thinks will happen. …
 *                         og:image       https://www.bainluck.com/opengraph-image
 *   /playoffs/nfl         byte-identical in all four.
 *   /sport/football       og:title       Football - BainLuck
 *                         twitter:title  Bain Luck — Prediction Market Discovery
 *   /sport/football/nfl   og:title       NFL - BainLuck
 *                         twitter:title  Bain Luck — Prediction Market Discovery
 *
 * Two routes said nothing about themselves at all; two said it in `openGraph`
 * only and let X inherit the home page's title. All four named one picture,
 * `https://www.bainluck.com/opengraph-image` — the house card. They were the
 * last four entries on check 8's ratchet (`__tests__/shareUnfurl.test.ts`),
 * which is now empty.
 *
 * ═══ WHAT THIS ASSERTS, AND IN WHICH DIRECTION ═══
 *
 * Both directions, per gotcha #43. It is not enough that each route draws A
 * card: the obvious way to "pass" a one-directional version of this file is to
 * draw the SAME quiet card on all four, which is the defect (one house picture)
 * with extra steps. So the positive rules assert each route's own name, its own
 * sentence and its own colour, and the negative rules assert the two things
 * these cards must never grow — a probability they do not have, and a count of
 * our inventory (notice 34).
 *
 * ⚠️ THE RIG IS PROVED NOT BLIND BEFORE ANY ABSENCE IS ASSERTED. `UnfurlCard`
 * is rendered as `<UnfurlCard {...props} />`, so every string it draws is a
 * PROP, not a child: a reader that walks the element tree returns `[]` and
 * every "does not print X" passes vacuously — which is what happened to the
 * first cut of `deadLinkUnfurlCard5846.test.tsx`. `renderToStaticMarkup` is the
 * fix, and the first test below blinds the reader deliberately and fails.
 *
 * Rendering rather than reading the copy table also puts `clampText` and
 * `clampWords` INSIDE the test, which is the only way the census below can
 * claim these sentences reach the canvas whole.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const mockImageResponseCalls: React.ReactElement[] = [];

jest.mock("next/og", () => ({
  __esModule: true,
  ImageResponse: function ImageResponse(element: React.ReactElement) {
    mockImageResponseCalls.push(element);
    return { __stub: "ImageResponse" };
  },
}));

import fs from "fs";
import path from "path";

import CategoryOgImage from "@/app/categories/[slug]/opengraph-image";
import PlayoffsOgImage from "@/app/playoffs/[sport]/opengraph-image";
import SportOgImage from "@/app/sport/[sport]/opengraph-image";
import LeagueOgImage from "@/app/sport/[sport]/[league]/opengraph-image";
import { generateMetadata as categoryMetadata } from "@/app/categories/[slug]/layout";
import { generateMetadata as playoffsMetadata } from "@/app/playoffs/[sport]/layout";
import { generateMetadata as sportMetadata } from "@/app/sport/[sport]/layout";
import { generateMetadata as leagueMetadata } from "@/app/sport/[sport]/[league]/layout";
import {
  LEAGUE_DISPLAY_NAMES,
  categoryShare,
  collectionCardCopy,
  leagueDisplayName,
  leagueShare,
  playoffShare,
  sportShare,
} from "@/lib/collectionShareMeta";
import {
  PLAYOFF_LEAGUES,
  PLAYOFF_LEAGUE_MAP,
  playoffDisplayName,
} from "@/lib/playoffLeagues";
import { SPORT_CATEGORIES, getCategoryByKey } from "@/lib/sportCategories";
import { unresolvedShareCopy } from "@/lib/unresolvedShareMeta";
import {
  DEFAULT_ACCENT,
  SUBTITLE_MAX_QUIET,
  UnfurlCard,
  accentFor,
} from "@/components/og/UnfurlCard";

/* ────────────────────────────── the harness ────────────────────────────── */

const ENTITIES: Record<string, string> = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#x27;": "'",
  "&#39;": "'",
  "&#x2F;": "/",
};

/**
 * Every string the card DRAWS, in render order.
 *
 * Split on TAG boundaries rather than whitespace, because these assertions name
 * whole sentences and a word-split list can never contain one. The sentinel is
 * written as an escape so no raw control byte sits in the file.
 */
function textNodes(element: React.ReactElement): string[] {
  const TAG_BOUNDARY = "\u0000";
  return renderToStaticMarkup(element)
    .replace(/<[^>]*>/g, TAG_BOUNDARY)
    .split(TAG_BOUNDARY)
    .map((text) =>
      text.replace(/&(?:amp|lt|gt|quot|#x27|#39|#x2F);/g, (e) => ENTITIES[e]).trim(),
    )
    .filter(Boolean);
}

/** Every fill/stroke colour the card drew. */
function colours(element: React.ReactElement): string {
  return renderToStaticMarkup(element).toLowerCase();
}

/** Drive an image route the way Next does, and hand back what it drew. */
async function drawn(
  route: (args: { params: Promise<never> }) => Promise<unknown>,
  params: Record<string, string>,
): Promise<React.ReactElement> {
  mockImageResponseCalls.length = 0;
  await route({ params: Promise.resolve(params) as unknown as Promise<never> });
  expect(mockImageResponseCalls).toHaveLength(1);
  return mockImageResponseCalls[0];
}

const APP_DIR = path.join(__dirname, "..", "app");
const read = (...segments: string[]) =>
  fs.readFileSync(path.join(APP_DIR, ...segments), "utf8");

/* ───────────────────────────── the rig itself ──────────────────────────── */

describe("the reader is not blind", () => {
  it("sees a string that IS drawn, and would fail if it walked props", () => {
    const drawnText = textNodes(
      <UnfurlCard {...collectionCardCopy(leagueShare("football", "nfl"))} />,
    );
    expect(drawnText).toContain("NFL");
    expect(drawnText).toContain("League");

    // The blinding this guards against: the element's own children are empty,
    // so a reader built on `props.children` returns nothing and every absence
    // assertion below would pass for free.
    const element = <UnfurlCard {...collectionCardCopy(leagueShare("football", "nfl"))} />;
    expect(React.Children.count(element.props.children)).toBe(0);
  });
});

/* ──────────────────────── each route draws ITSELF ──────────────────────── */

describe("each of the four routes draws its own card", () => {
  it("/categories/<slug> draws the category the page shows as its h1", async () => {
    const text = textNodes(await drawn(CategoryOgImage, { slug: "politics" }));
    expect(text).toContain("Politics");
    expect(text).toContain("Category");
    expect(text).toContain(
      "Every Politics market we track, translated into plain probabilities.",
    );
    // The page's own h1 call, so the picture and the page cannot drift.
    expect(text).toContain(getCategoryByKey("politics")!.name);
  });

  it("/categories/<slug> draws an unlisted slug rather than refusing it", async () => {
    // 26 of the 48 counted categories are not in `SPORT_CATEGORIES`, and the
    // PAGE renders them — so the card must too. Claiming "not on Bain Luck"
    // here would be false about a page that works.
    expect(getCategoryByKey("table_tennis")).toBeUndefined();
    const text = textNodes(await drawn(CategoryOgImage, { slug: "table_tennis" }));
    expect(text).toContain("Table Tennis");
    expect(text.join(" ")).not.toContain("isn't on Bain Luck");
  });

  it("/sport/<sport> draws the sport", async () => {
    const text = textNodes(await drawn(SportOgImage, { sport: "football" }));
    expect(text).toContain("Football");
    expect(text).toContain("Sport");
    expect(text).toContain(
      "Every Football league we cover, with win probabilities and championship odds as one clean number.",
    );
  });

  it("/sport/<sport>/<league> draws the league, not the segment", async () => {
    const text = textNodes(
      await drawn(LeagueOgImage, { sport: "soccer", league: "epl" }),
    );
    // The map's answer, not `"EPL"` — the segment upper-cased is the FALLBACK
    // and a mutant that returns it always would still look plausible.
    expect(text).toContain("Premier League");
    expect(text).not.toContain("EPL");
    expect(text).toContain("League");
  });

  it("/sport/<sport>/<league> falls back to the segment for a league it has no name for", async () => {
    const text = textNodes(
      await drawn(LeagueOgImage, { sport: "soccer", league: "eredivisie" }),
    );
    expect(text).toContain("EREDIVISIE");
  });

  it("/playoffs/<slug> draws the page's own heading, golf included", async () => {
    const nfl = textNodes(await drawn(PlayoffsOgImage, { sport: "nfl" }));
    expect(nfl).toContain("NFL Championship Grid");
    expect(nfl).toContain("Playoffs");
    expect(nfl).toContain(
      "Every team's road to the NFL title, as one clean probability.",
    );

    // `/playoffs/golf` is a tournament schedule, not a bracket, and the page
    // says so. A card reading "Golf Championship Grid" would name something the
    // reader does not find there.
    const golf = textNodes(await drawn(PlayoffsOgImage, { sport: "golf" }));
    expect(golf).toContain("Golf Tournament Odds");
    expect(golf.join(" ")).not.toContain("Championship Grid");
  });

  it("/playoffs/<alias> draws the bracket, not a refusal", async () => {
    // Five aliases are live addresses. A card that says "this bracket isn't on
    // Bain Luck" while the page renders the NCAAB grid is worse than the
    // generic picture it replaced.
    for (const [alias, expected] of [
      ["ncaab", "NCAAB Championship Grid"],
      ["ncaaf", "NCAAF Championship Grid"],
      ["wncaab", "WNCAAB Championship Grid"],
      ["ucl", "UCL Championship Grid"],
      ["ncaa", "NCAAB Championship Grid"],
    ] as const) {
      const text = textNodes(await drawn(PlayoffsOgImage, { sport: alias }));
      expect(text).toContain(expected);
    }
  });

  it("/playoffs/<slug> with no bracket says so, in the family's existing voice", async () => {
    const text = textNodes(
      await drawn(PlayoffsOgImage, { sport: "not-a-league-99999" }),
    );
    expect(playoffShare("not-a-league-99999")).toBeNull();
    // Taken from `unresolvedShareCopy`, not retyped here, so the card and the
    // `<title>` cannot say two different things.
    expect(text).toContain(unresolvedShareCopy("bracket", "not-found").title);
    expect(text).toContain("This bracket isn't on Bain Luck");
    expect(text).toContain("Playoffs");
  });
});

/* ─────────── the negative half: four cards, not one house card ─────────── */

describe("the four cards are four pictures", () => {
  const specimens = () => [
    collectionCardCopy(categoryShare("politics")),
    collectionCardCopy(categoryShare("weather")),
    collectionCardCopy(sportShare("basketball")),
    collectionCardCopy(leagueShare("baseball", "mlb")),
    collectionCardCopy(playoffShare("nhl")!),
  ];

  it("no two of them share a headline", () => {
    const titles = specimens().map((card) => card.title);
    expect(new Set(titles).size).toBe(titles.length);
  });

  it("the accent is the SEGMENT's, and the segments differ", () => {
    // The mutation this exists for: `accentFor(null)` — every card the same
    // default green — which is precisely what survived the suite on
    // `/hub/[competition]` until `hubCardCopy` took the decision.
    const accents = specimens().map((card) => card.accent);
    expect(accents.every((accent) => accent !== DEFAULT_ACCENT)).toBe(true);
    expect(new Set(accents).size).toBeGreaterThanOrEqual(4);
  });

  it("a league's colour comes from its SPORT, because CATEGORY_ACCENT has no league keys", () => {
    expect(accentFor("nfl")).toBe(DEFAULT_ACCENT);
    expect(accentFor("mlb")).toBe(DEFAULT_ACCENT);

    expect(leagueShare("football", "nfl").accent).toBe(accentFor("football"));
    expect(leagueShare("football", "nfl").accent).not.toBe(DEFAULT_ACCENT);
    // …and a bracket's, from the `sport` field the registry gained for it.
    expect(playoffShare("nfl")!.accent).toBe(accentFor("football"));
    expect(playoffShare("mlb")!.accent).toBe(accentFor("baseball"));
    expect(playoffShare("mlb")!.accent).not.toBe(playoffShare("nfl")!.accent);
  });

  it("the accent actually reaches the canvas", async () => {
    const markup = colours(await drawn(LeagueOgImage, { sport: "baseball", league: "mlb" }));
    expect(markup).toContain(accentFor("baseball").toLowerCase());
  });

  it("every league in the playoff registry has a real sport key", () => {
    for (const league of PLAYOFF_LEAGUES) {
      expect(accentFor(league.sport)).not.toBe(DEFAULT_ACCENT);
    }
  });
});

describe("a collection card prints no number", () => {
  // A collection has no single question, so there is nothing honest to
  // headline — and a count of what we hold is a fact about our inventory
  // rather than about the world (notice 34). Both would be inventions of the
  // #5846 shape: authoritative-looking, saying nothing.
  const cards: [string, React.ReactElement][] = [
    ["category", <UnfurlCard key="c" {...collectionCardCopy(categoryShare("politics"))} />],
    ["sport", <UnfurlCard key="s" {...collectionCardCopy(sportShare("basketball"))} />],
    ["league", <UnfurlCard key="l" {...collectionCardCopy(leagueShare("football", "nfl"))} />],
    ["playoffs", <UnfurlCard key="p" {...collectionCardCopy(playoffShare("nba")!)} />],
  ];

  it.each(cards)("%s draws no probability and no inventory count", (_name, element) => {
    const text = textNodes(element).join(" ");
    expect(text).not.toMatch(/\d+%/);
    expect(text).not.toMatch(/\d+\s+(markets?|outcomes?|events?|matches|props)/i);
    expect(text).not.toContain("- -");
  });

  it.each(cards)("%s hands UnfurlCard no rows at all", (_name, element) => {
    expect(element.props.rows).toEqual([]);
    expect(element.props.note).toBeUndefined();
    expect(element.props.verdict).toBeUndefined();
  });
});

/* ─── the census: every real segment's sentence fits, whole, on the canvas ── */

describe("every sentence these tables can produce fits the card", () => {
  const everyShare = () => [
    ...SPORT_CATEGORIES.map((category) => categoryShare(category.key)),
    ...SPORT_CATEGORIES.map((category) => sportShare(category.key)),
    ...Object.keys(LEAGUE_DISPLAY_NAMES).map((league) => leagueShare("football", league)),
    ...Object.keys(PLAYOFF_LEAGUE_MAP).map((slug) => playoffShare(slug)!),
  ];

  it("has a non-trivial population", () => {
    // The `.map()`s above are vacuously satisfiable by an empty table.
    expect(everyShare().length).toBeGreaterThanOrEqual(100);
    expect(SPORT_CATEGORIES.length).toBeGreaterThanOrEqual(30);
    expect(Object.keys(LEAGUE_DISPLAY_NAMES).length).toBeGreaterThanOrEqual(26);
    expect(Object.keys(PLAYOFF_LEAGUE_MAP).length).toBeGreaterThanOrEqual(19);
  });

  it("renders every one of them without an ellipsis", () => {
    // `clampWords` cuts at `SUBTITLE_MAX_QUIET`; a sentence that reaches it
    // ships as "…every market translated in…" on the most public screen we
    // have, which is what taught `/hub/[competition]` to raise the limit.
    for (const share of everyShare()) {
      const text = textNodes(<UnfurlCard {...collectionCardCopy(share)} />).join(" ");
      expect(share.description.length).toBeLessThanOrEqual(SUBTITLE_MAX_QUIET);
      expect(text).toContain(share.description);
      expect(text).toContain(share.name);
      expect(text).not.toContain("…");
    }
  });

  it("never says 'books' or 'bookmaker', anywhere (notice 33)", () => {
    for (const share of everyShare()) {
      const words = `${share.name} ${share.pageTitle} ${share.description} ${share.eyebrow}`;
      expect(words.toLowerCase()).not.toMatch(/\bbooks?\b|bookmaker/);
    }
  });
});

/* ─────────────────────── both namespaces, one picture ──────────────────── */

describe("the tags name the route's own card in BOTH namespaces", () => {
  const cases: [string, () => Promise<Record<string, unknown>>, string][] = [
    [
      "/categories/politics",
      () => categoryMetadata({ params: Promise.resolve({ slug: "politics" }) }) as never,
      "https://www.bainluck.com/categories/politics/opengraph-image",
    ],
    [
      "/playoffs/nfl",
      () => playoffsMetadata({ params: Promise.resolve({ sport: "nfl" }) }) as never,
      "https://www.bainluck.com/playoffs/nfl/opengraph-image",
    ],
    [
      "/sport/football",
      () => sportMetadata({ params: Promise.resolve({ sport: "football" }) }) as never,
      "https://www.bainluck.com/sport/football/opengraph-image",
    ],
    [
      "/sport/football/nfl",
      () =>
        leagueMetadata({
          params: Promise.resolve({ sport: "football", league: "nfl" }),
        }) as never,
      "https://www.bainluck.com/sport/football/nfl/opengraph-image",
    ],
  ];

  it.each(cases)("%s", async (route, build, expectedImage) => {
    const meta = (await build()) as {
      title: string;
      description: string;
      alternates: { canonical: string };
      openGraph: { title: string; url: string; images: { url: string }[] };
      twitter: { title: string; images: string[] };
    };

    expect(meta.openGraph.images[0].url).toBe(expectedImage);
    // The half that was broken on two of these four: X reads `twitter:`, and an
    // omitted block inherits the ROOT's card and the ROOT's title.
    expect(meta.twitter.images[0]).toBe(expectedImage);
    expect(meta.twitter.title).toBe(meta.openGraph.title);

    // …and none of them is the home page any more.
    expect(meta.alternates.canonical).toBe(route);
    expect(meta.openGraph.url).toBe(route);
    expect(meta.title).not.toContain("Prediction Market Discovery");
    expect(meta.openGraph.title).not.toContain("Prediction Market Discovery");
    expect(meta.description).not.toContain("See what the world thinks will happen.");
  });

  it("a bracket that does not exist is self-canonical, noindex, and keeps its own card", async () => {
    const meta = (await playoffsMetadata({
      params: Promise.resolve({ sport: "not-a-league-99999" }),
    })) as unknown as {
      title: string;
      robots: { index: boolean; follow: boolean };
      alternates: { canonical: string };
      openGraph: { images: { url: string }[] };
      twitter: { images: string[] };
    };

    expect(meta.title).toBe("This bracket isn't on Bain Luck");
    expect(meta.robots).toEqual({ index: false, follow: true });
    expect(meta.alternates.canonical).toBe("/playoffs/not-a-league-99999");
    const dead = "https://www.bainluck.com/playoffs/not-a-league-99999/opengraph-image";
    expect(meta.openGraph.images[0].url).toBe(dead);
    expect(meta.twitter.images[0]).toBe(dead);
  });

  it("a bracket that DOES exist is never noindex-ed", async () => {
    // The direction that matters more: `robots` is the durable half, and
    // deindexing `/playoffs/nfl` would be a worse outcome than the defect.
    for (const slug of ["nfl", "ncaab", "golf"]) {
      const meta = (await playoffsMetadata({
        params: Promise.resolve({ sport: slug }),
      })) as unknown as { robots?: unknown };
      expect(meta.robots).toBeUndefined();
    }
  });

  it("a user-supplied segment cannot become a path that is not this page", async () => {
    const meta = (await categoryMetadata({
      params: Promise.resolve({ slug: "../../evil" }),
    })) as unknown as { alternates: { canonical: string } };
    expect(meta.alternates.canonical).toBe("/categories/..%2F..%2Fevil");
  });
});

/* ───────────── the suffix split, read off the tree not remembered ───────── */

describe("the <title> carries the brand exactly once", () => {
  /**
   * The asymmetry this asserts is real and invisible in any one file:
   * `app/sport/layout.tsx` sets a plain-string `title`, which REPLACES the
   * root's `%s | Bain Luck` template for everything beneath it, while
   * `app/categories/layout.tsx` and `app/playoffs/layout.tsx` set none and let
   * the template through. So two of these four routes must carry the suffix
   * themselves and two must not — and a reader who "fixes the inconsistency"
   * ships either a brandless tab or "NFL | Bain Luck | Bain Luck".
   */
  it("the ancestors really are shaped the way the split assumes", () => {
    expect(read("sport", "layout.tsx")).toMatch(/title:\s*"/);
    expect(read("categories", "layout.tsx")).not.toMatch(/^\s*title:/m);
    expect(read("playoffs", "layout.tsx")).not.toMatch(/^\s*title:/m);
  });

  it("the /sport routes suffix their own title and the other two do not", async () => {
    const sport = (await sportMetadata({
      params: Promise.resolve({ sport: "football" }),
    })) as unknown as { title: string };
    const league = (await leagueMetadata({
      params: Promise.resolve({ sport: "football", league: "nfl" }),
    })) as unknown as { title: string };
    const category = (await categoryMetadata({
      params: Promise.resolve({ slug: "politics" }),
    })) as unknown as { title: string };
    const playoffs = (await playoffsMetadata({
      params: Promise.resolve({ sport: "nfl" }),
    })) as unknown as { title: string };

    expect(sport.title).toBe("Football Odds & Probabilities | Bain Luck");
    expect(league.title).toBe("NFL Odds & Schedule | Bain Luck");
    // The template appends the suffix to these two at render time.
    expect(category.title).toBe("Politics Odds & Probabilities");
    expect(playoffs.title).toBe("NFL Championship Grid");

    for (const title of [sport.title, league.title, category.title, playoffs.title]) {
      expect(title.match(/Bain Luck/g) ?? []).toHaveLength(
        title.endsWith("| Bain Luck") ? 1 : 0,
      );
    }
  });

  it("the wordmark is spaced, in every string these four routes emit", async () => {
    // "BainLuck" unspaced was in the tab and the `og:title` of both /sport
    // routes on production. `chartFooterOneSourceLegend4083.test.tsx` asserts
    // the same rule one surface over.
    const metas = await Promise.all([
      sportMetadata({ params: Promise.resolve({ sport: "football" }) }),
      leagueMetadata({ params: Promise.resolve({ sport: "football", league: "nfl" }) }),
      categoryMetadata({ params: Promise.resolve({ slug: "politics" }) }),
      playoffsMetadata({ params: Promise.resolve({ sport: "nfl" }) }),
    ]);
    expect(JSON.stringify(metas)).not.toContain("BainLuck");

    for (const file of [
      ["sport", "[sport]", "layout.tsx"],
      ["sport", "[sport]", "[league]", "layout.tsx"],
      ["categories", "[slug]", "layout.tsx"],
      ["playoffs", "[sport]", "layout.tsx"],
    ]) {
      // The comment blocks quote the old tags, so only the CODE is read.
      const source = read(...file).replace(/\/\*[\s\S]*?\*\//g, "");
      expect(source).not.toContain("BainLuck");
      // None of the four may quietly fall back to the house picture.
      expect(source).not.toContain("defaultShareCard");
    }
  });
});

/* ─────────────────── the page and the card say one thing ───────────────── */

describe("the card's words are the page's words", () => {
  it("the playoffs page builds its h1 from the same function the card does", () => {
    const source = read("playoffs", "[sport]", "page.tsx");
    expect(source).toContain("playoffDisplayName(league)");
    // …and the registry it reads is the one the card reads, not a second copy.
    expect(source).toContain('from "@/lib/playoffLeagues"');
    expect(source).not.toMatch(/const LEAGUES:\s*LeagueInfo\[\]\s*=/);

    for (const league of PLAYOFF_LEAGUES) {
      expect(playoffShare(league.slug)!.name).toBe(playoffDisplayName(league));
    }
  });

  it("the category page and the category card resolve the name the same way", () => {
    const source = read("categories", "[slug]", "page.tsx");
    expect(source).toContain("getCategoryByKey(slug)");
    expect(source).toContain("toTitleCaseAcronymSafe(slug)");
    expect(categoryShare("politics").name).toBe(getCategoryByKey("politics")!.name);
    expect(categoryShare("table_tennis").name).toBe("Table Tennis");
  });

  it("the league layout's title and the league card's headline are one string", () => {
    expect(leagueShare("football", "nfl").name).toBe(leagueDisplayName("nfl"));
    expect(leagueShare("soccer", "ucl").name).toBe("Champions League");
    // Case-insensitive, because a pasted URL is not guaranteed lower-cased.
    expect(leagueShare("soccer", "UCL").name).toBe("Champions League");
  });
});
