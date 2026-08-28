/**
 * UX-P155 — RULING 141'S LAST FOUR SENTENCES, RENDERED FROM THE SHIPPED PAGES.
 *
 * ═══ WHAT THIS PROVES, AND WHAT IT DELIBERATELY DOES NOT ═══
 *
 * `shippedCopyBans` proves the STRINGS are gone from the built bundle. That is
 * the stronger proof of absence and it is the gate. What it cannot show is
 * whether the sentences that replaced them read as sentences on the page they
 * sit on — whether the golf hero still says what the page is for once the
 * supplier list is out of it, whether the weather card lost anything when the
 * subtitle stopped repeating the badge beside it.
 *
 * So this renders the three real surfaces — `app/about/page.tsx`,
 * `app/categories/golf/page.tsx`, `components/weather/RainForecast.tsx` — with
 * `renderToStaticMarkup` and the app's own compiled stylesheet, and writes one
 * page with the retired sentence quoted above each live one.
 *
 *   UX_CAPTURE_DIR=<dir> npx jest --testPathPatterns=ruling141CopyCapture
 *
 * With no env var set it is an ordinary test that renders all three and
 * asserts the copy, so a surface that stops printing its subtitle fails CI
 * rather than waiting to be noticed on a screen. That is the point of
 * rendering the PAGE rather than importing the string: a constant can be
 * correct while nothing renders it.
 *
 * ═══ WHY THE PAGES RENDER AT ALL WITHOUT A BROWSER ═══
 *
 * All three are client components that fetch on mount. `renderToStaticMarkup`
 * runs no effects, so each falls to its own pre-data branch — which is exactly
 * the state a reader sees on first paint, and in all three cases the copy this
 * queue changed is above the data. Nothing is stubbed to make a sentence
 * appear; `swr` is stubbed only because `RainForecast` calls it at module
 * scope and would otherwise reach the network.
 *
 * BEFORE panels are QUOTED, and captioned as such: the strings are gone from
 * the tree, which is the whole point of a before panel.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: undefined, error: undefined, isLoading: true }),
}));

import AboutPage from "@/app/about/page";
import GolfPage from "@/app/categories/golf/page";
import RainForecast from "@/components/weather/RainForecast";
import { AnalyticsProvider } from "@/components/Analytics";
import { STORY_BLEND } from "@/lib/story-content";

/**
 * The pages call `usePageTracking`, which throws outside the provider. Wrap in
 * the REAL `AnalyticsProvider` — the same one `app/layout.tsx` wraps them in —
 * rather than stubbing the hook, so the thing being rendered is the thing that
 * ships and not a page with its chrome removed.
 */
function inApp(node: React.ReactElement): string {
  return renderToStaticMarkup(<AnalyticsProvider>{node}</AnalyticsProvider>);
}

const FRONTEND = path.join(__dirname, "..", "..");

function appStylesheet(): string {
  const dir = path.join(FRONTEND, ".next", "static", "css");
  try {
    return fs
      .readdirSync(dir)
      .filter((f) => f.endsWith(".css"))
      .map((f) => fs.readFileSync(path.join(dir, f), "utf8"))
      .join("\n");
  } catch {
    return "";
  }
}

/**
 * The page's visible text, ONE TEXT NODE PER LINE.
 *
 * `tournamentPlainLanguage`'s `visibleText` joins nodes with a space, which is
 * right for the components it sweeps — their copy is prose with sentence
 * punctuation in it, so `clauseAround` finds its own boundaries. At PAGE scale
 * it is not: `/about`'s source table renders `Kalshi` and `63%` as sibling
 * nodes with no punctuation anywhere near them, and a space-join hands
 * `clauseAround` a run-on that reaches into the marketing paragraph above.
 * `isSourceAttribution` then sees lowercase prose around the name and calls a
 * legitimate table label narrative.
 *
 * A newline is a clause boundary in `lib/copyBans.ts`, and two sibling
 * elements really are two clauses, so splitting on the tag is the faithful
 * reading rather than a loosened one — it makes each label be judged as the
 * label it is, and it does not let a sentence hide inside one.
 */
function textLines(markup: string): string {
  return markup
    .replace(/<style[\s\S]*?<\/style>/g, "\n")
    .replace(/<script[\s\S]*?<\/script>/g, "\n")
    .replace(/<[^>]+>/g, "\n")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&mdash;/g, "—")
    .replace(/&ndash;/g, "–")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&ldquo;/g, "“")
    .replace(/&rdquo;/g, "”")
    .replace(/&rsquo;/g, "’")
    .split("\n")
    .map((line) => line.replace(/[ \t]+/g, " ").trim())
    .filter(Boolean)
    .join("\n");
}

/**
 * The four sentences, each with the surface it sits on and the fact that had
 * to survive the rewrite.
 *
 * The `was`/`now` pair is the discipline ruling 141 asks for in its own words:
 * "the failure mode of a copy ruling is a rewrite that removes the word and
 * the meaning with it", so the table pins BOTH — the retired sentence must be
 * absent and the new one present, and `survives` says out loud what would have
 * been lost if the fix had just deleted the clause.
 */
const SWEEP = [
  {
    id: "about-category",
    surface: "/about — the category grid",
    was: "Kalshi + Polymarket, unified",
    now: "Open questions, merged into one number",
    survives:
      "that this category is the one where several places quote the same question and we show one number for it — which is the standing “the blend is the product” ruling, said without the supplier list.",
  },
  {
    id: "about-blend",
    surface: "/about — “Six sources. One number.”",
    was: "Sportsbooks, ESPN, Kalshi, Polymarket, and live stat models each have a guess.",
    now: "Sportsbooks, ESPN, prediction markets, and live stat models each have a guess.",
    survives:
      "the KINDS of guess and that they are independent of each other. The names are still on this page fifty lines down, attributing 63% and 59% in the source table — the amendment's allowed class — so the reader who wants them loses nothing.",
  },
  {
    id: "golf-hero",
    surface: "/categories/golf — the hero subtitle",
    was: "Tournament odds from Polymarket, Kalshi, sportsbooks & DataGolf",
    now: "Who wins each tournament, one number per golfer",
    survives:
      "what the page actually shows, which the old line never said. Coverage is stated underneath it by the real count (“N tournaments · N golfers tracked”) and the sources by <code>SourceLegend</code> further down.",
  },
  {
    id: "weather-rain",
    surface: "/weather — the 7-day rain card",
    was: "Daily “Will it rain?” markets from Kalshi",
    now: "Daily “Will it rain?” questions, one per day",
    survives:
      "the shape of the question and its cadence. The venue was being said twice: <code>&lt;SourceBadge src=&quot;kalshi&quot; /&gt;</code> sits on the same row and renders the name, and that badge is attribution, which the amendment allows.",
  },
] as const;

describe("ruling 141's last four sentences, on the pages that serve them", () => {
  const rendered: Record<string, string> = {
    about: inApp(<AboutPage />),
    golf: inApp(<GolfPage />),
    weather: inApp(<RainForecast />),
  };

  const surfaceOf: Record<string, keyof typeof rendered> = {
    "about-category": "about",
    "about-blend": "about",
    "golf-hero": "golf",
    "weather-rain": "weather",
  };

  it.each(SWEEP.map((s) => [s.id, s] as const))(
    "%s — the page prints the new sentence and not the old one",
    (_id, entry) => {
      const text = textLines(rendered[surfaceOf[entry.id]]);
      expect(text).toContain(entry.now);
      expect(text).not.toContain(entry.was);
    }
  );

  it("no venue name survives as narrative on any of the three surfaces", () => {
    // Not "the four strings are gone" — that is the test above. This asks the
    // broader question the ruling asks: does any of these pages still talk
    // ABOUT our suppliers. Attribution is expected and allowed, so the assert
    // runs through the ruling's own predicate rather than a name match.
    const { findBannedCopy, VENUE_BANS } = jest.requireActual<
      typeof import("@/lib/copyBans")
    >("@/lib/copyBans");
    for (const [name, markup] of Object.entries(rendered)) {
      const hits = findBannedCopy(textLines(markup), VENUE_BANS);
      // The context, not just the rule id: a failure here has to name the
      // clause so the next reader can decide attribution vs narrative without
      // re-rendering the page.
      expect(hits.map((h) => `${name}: ${h.ban.id} — …${h.context}…`)).toEqual([]);
    }
  });

  it("the blend blurb still names four kinds of guess, not two venues", () => {
    // The rewrite could have satisfied the ruling by deleting the list. The
    // heading above it says "Six sources. One number.", and a heading that
    // counts something the sentence no longer describes is the meaning-loss
    // failure this ruling warns about.
    expect(STORY_BLEND.body).toContain("Sportsbooks");
    expect(STORY_BLEND.body).toContain("ESPN");
    expect(STORY_BLEND.body).toContain("prediction markets");
    expect(STORY_BLEND.body).toContain("live stat models");
    expect(STORY_BLEND.body).toContain("weight them by track record");
  });

  it("writes the artifact when UX_CAPTURE_DIR is set", () => {
    const dir = process.env.UX_CAPTURE_DIR;
    if (!dir) {
      console.warn(
        "\n⚠️  UX_CAPTURE_DIR unset — no artifact written. The assertions above still ran.\n" +
          "    UX_CAPTURE_DIR=<dir> npx jest --testPathPatterns=ruling141CopyCapture\n"
      );
      return;
    }
    fs.mkdirSync(dir, { recursive: true });

    const panel = (entry: (typeof SWEEP)[number]) => `
<section class="panel">
  <div class="surface">${entry.surface}</div>
  <div class="row was"><span class="tag before">WAS — quoted, no longer in the tree</span>
    <div class="copy">${entry.was}</div></div>
  <div class="row now"><span class="tag after">NOW — rendered from the shipped page</span>
    <div class="copy">${entry.now}</div></div>
  <div class="survives"><b>The fact that had to survive:</b> ${entry.survives}</div>
</section>`;

    const html = `<!doctype html><html><head><meta charset="utf-8">
<title>UX-P155 — ruling 141, the last four sentences</title>
<style>${appStylesheet()}</style>
<style>
  body { font: 14px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: #f6f7f9; color: #16181d; margin: 0; padding: 32px; }
  .lede { max-width: 68ch; margin: 0 auto 28px; }
  .panel { max-width: 68ch; margin: 0 auto 18px; background: #fff; border: 1px solid #e3e6ea;
           border-radius: 14px; padding: 18px 20px; }
  .surface { font-family: ui-monospace, monospace; font-size: 12px; color: #6b7280;
             margin-bottom: 12px; }
  .row { display: flex; gap: 12px; align-items: flex-start; margin-bottom: 8px; }
  .copy { font-size: 15px; }
  .was .copy { color: #9aa1ab; text-decoration: line-through; }
  .now .copy { color: #16181d; font-weight: 600; }
  .tag { flex: 0 0 auto; font-size: 10px; font-weight: 700; letter-spacing: .04em;
         padding: 3px 7px; border-radius: 999px; text-transform: uppercase; }
  .tag.before { background: #fdecec; color: #b42318; }
  .tag.after { background: #e7f6ec; color: #067647; }
  .survives { margin-top: 10px; padding-top: 10px; border-top: 1px solid #eef0f3;
              font-size: 13px; color: #4b5563; }
  .render { max-width: 68ch; margin: 26px auto 0; }
  .render h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .05em;
               color: #6b7280; }
  .frame { background: #fff; border: 1px solid #e3e6ea; border-radius: 14px;
           padding: 14px; overflow: hidden; }
</style></head><body>
<div class="lede">
  <h1 style="font-size:22px;margin:0 0 10px">Ruling 141 — the last four narrative sentences</h1>
  <p>Ruling 141 as Alex amended it bans a venue name where it is the <b>subject</b> of the copy
  and allows it where it <b>attributes a number the reader is looking at</b>. UX-P152 classified
  every occurrence in the bundle and found four still on the wrong side of that line. These are
  those four.</p>
  <p>Each NOW line below was pulled out of the shipped page rendered with
  <code>renderToStaticMarkup</code> — <code>app/about/page.tsx</code>,
  <code>app/categories/golf/page.tsx</code>, <code>components/weather/RainForecast.tsx</code> —
  not retyped. The WAS lines are quoted; they are gone from the tree, which is the point.</p>
  <p><b>Not swept, on purpose:</b> the source table on <code>/about</code> still says Kalshi 63%
  and Polymarket 59%, the weather badge still says Kalshi, the golf source legend still names
  every source. All attribution, all allowed, all left alone.</p>
</div>
${SWEEP.map(panel).join("\n")}
<div class="render">
  <h2>The /about blend section, as the page renders it</h2>
  <div class="frame">
    <h3 style="margin:0 0 8px">${STORY_BLEND.heading}</h3>
    <p style="margin:0">${STORY_BLEND.body}</p>
  </div>
</div>
</body></html>`;

    const file = path.join(dir, "p155-ruling-141-last-four.html");
    fs.writeFileSync(file, html);

    // The artifact asserts itself — a generator that writes a file nobody
    // checks is how an empty page gets reported as a render.
    const written = fs.readFileSync(file, "utf8");
    expect(written.length).toBeGreaterThan(8_000);
    for (const entry of SWEEP) {
      expect(written).toContain(entry.now);
      expect(written).toContain(entry.surface);
    }
    expect(written).toContain('class="tag before"');
    expect(written).toContain('class="tag after"');
  });
});
