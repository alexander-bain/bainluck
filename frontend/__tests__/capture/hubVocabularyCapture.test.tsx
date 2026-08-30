/**
 * UX-P167 (#2167) — the tennis and golf hubs stop calling themselves fight
 * cards, for Alex's eyeball.
 *
 * ═══ WHAT A READER SEES TODAY ═══
 *
 * Read on the deployed build on 2026-08-29, during US Open week, over ALL FIVE
 * competition hubs — a census of the surface, not a sample. Headers computed
 * with the shipped chrome rule (`earnsSectionHeader`: >= 2 items AND >= 2
 * sections), so this is what actually printed, not what the map contains:
 *
 *     /hub/tennis     UPCOMING CARDS    over  12 tennis tournaments
 *                     FIGHT MARKETS     over 103 tennis markets
 *     /hub/esports    FIGHT MARKETS     over  98 esports markets
 *     /hub/golf       UPCOMING CARDS    over   3 golf tournaments
 *                     FIGHTER STATS     over   5 golf markets
 *     ------------------------------------------------------------
 *     /hub/mma        FIGHT MARKETS / UPCOMING CARDS   <- correct, the control
 *     /hub/boxing     UPCOMING CARDS                   <- correct, the control
 *
 * Five wrong headings across three hubs, over 206 markets and 15 tournaments,
 * on every load. "FIGHTER STATS" sits above five golf markets. During the US
 * Open, a page titled "🎾 Tennis" files 103 tennis markets under "FIGHT
 * MARKETS".
 *
 * ═══ WHY IT WAS WRONG ═══
 *
 * Not a data bug and not a matching bug. `SECTION_META` in
 * `app/hub/[competition]/page.tsx` was one competition-blind object written when
 * MMA was the only hub. The page is deliberately generic — its own header says
 * "adding boxing/esports is a backend config entry, not new page code" — so
 * every hub added afterwards inherited MMA's vocabulary verbatim. The config
 * entry WAS the whole adapter for the title, the emoji and the blurb; the
 * headings were the one thing that never made it in.
 *
 * ═══ THE DIRECTION OF THE FIX IS THE FIX ═══
 *
 * Defaults are now NEUTRAL and combat OVERRIDES. Every failure path therefore
 * lands on a word that is plain but true — a hub that declares nothing, an
 * unmapped section key, and a payload cached before this shipped (the hub mirror
 * lives up to 24h) all read "Matches". Combat defaults with per-hub escapes
 * would have made silence mean "Fight Markets" again, which is the bug.
 *
 * ═══ WHAT EVERY PANEL IS MADE OF ═══
 *
 * The SHIPPED default export of `app/hub/[competition]/page.tsx` — the same
 * component Next.js serves at `/hub/tennis` — rendered through
 * `renderToStaticMarkup` with the app's own compiled stylesheet.
 *
 * Neither arm is hand-written. `backend/tests/fixtures/uxp167_hub_vocabulary.json`
 * holds the real `GET /api/hub/{competition}` payloads pulled on 2026-08-29:
 * real section keys, real counts, real market rows, real upcoming rows.
 *
 * The BEFORE arm is honest rather than reconstructed: the old page hard-coded
 * combat words for every competition, which is exactly what this component does
 * when it is handed combat `section_labels` — so BEFORE renders the shipped
 * component with `_OLD_SECTION_META` as the served override. Same component,
 * same payload, one input changed. That is why the before/after diff is
 * attributable to the vocabulary and to nothing else.
 *
 *   UX_CAPTURE_DIR=<dir> TZ=UTC npx jest --testPathPatterns=hubVocabularyCapture
 *
 * With no env var set it is an ordinary test that renders every panel and
 * asserts the rig works, same as the sibling capture rigs.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

// The page reads the competition from the route, not from a prop.
let currentCompetition = "tennis";
jest.mock("next/navigation", () => ({
  useParams: () => ({ competition: currentCompetition }),
}));

// The page fetches through SWR. Feeding the hook directly keeps the fetch layer
// out of the render, so what a panel shows is the payload and the component and
// nothing in between.
let currentPayload: unknown = null;
jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: currentPayload, error: undefined }),
}));

// GA4 hooks — no-ops under renderToStaticMarkup.
jest.mock("@/hooks", () => ({
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
  useAnalytics: () => ({ trackEvent: () => undefined }),
}));

import CompetitionHubPage from "../../app/hub/[competition]/page";
import type { HubResponse } from "../../lib/api";

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const FIXTURE = path.join(
  REPO,
  "backend",
  "tests",
  "fixtures",
  "uxp167_hub_vocabulary.json",
);

type BeforeHeader = { where: string; header: string; over: number };
type HubFixture = Omit<HubResponse, "section_labels" | "upcoming_label"> & {
  section_sizes: Record<string, number>;
  upcoming_count: number;
  before_headers: BeforeHeader[];
};

const fixture: { _source: string; hubs: Record<string, HubFixture> } = JSON.parse(
  fs.readFileSync(FIXTURE, "utf8"),
);

const hub = (slug: string): HubFixture => {
  const found = fixture.hubs[slug];
  if (!found) throw new Error(`fixture is missing hub ${slug}`);
  return found;
};

/**
 * The vocabulary the page hard-coded for EVERY competition before this queue.
 * Kept here, in the test, because it is evidence rather than configuration —
 * feeding it back in is how the BEFORE panel is produced from shipped code.
 */
const _OLD_SECTION_META: Record<string, string> = {
  props: "Fight Props",
  matches: "Fight Markets",
  season_stats: "Fighter Stats",
};
const _OLD_UPCOMING_LABEL = "Upcoming Cards";

/** What `GET /api/hub/{slug}` serves after this queue, per the new HubConfig. */
const SERVED_LABELS: Record<string, { section_labels: Record<string, string>; upcoming_label: string }> = {
  mma: { section_labels: { ..._OLD_SECTION_META }, upcoming_label: "Upcoming Cards" },
  boxing: { section_labels: { ..._OLD_SECTION_META }, upcoming_label: "Upcoming Cards" },
  golf: { section_labels: {}, upcoming_label: "Upcoming Tournaments" },
  tennis: { section_labels: {}, upcoming_label: "Upcoming Tournaments" },
  esports: { section_labels: {}, upcoming_label: "Upcoming Tournaments" },
};

type Arm = "before" | "after" | "stale_cache";

function payloadFor(slug: string, arm: Arm): HubResponse {
  const f = hub(slug);
  const base = {
    competition: f.competition,
    label: f.label,
    title: f.title,
    emoji: f.emoji,
    blurb: f.blurb,
    sport_key: f.sport_key,
    upcoming: f.upcoming,
    sections: f.sections,
    total_markets: f.total_markets,
    tier: f.tier,
  } as HubResponse;
  if (arm === "before") {
    // The pre-fix page: MMA's words on every competition.
    return { ...base, section_labels: _OLD_SECTION_META, upcoming_label: _OLD_UPCOMING_LABEL };
  }
  if (arm === "stale_cache") {
    // A payload built before this shipped — the fields are simply absent.
    return base;
  }
  return { ...base, ...SERVED_LABELS[slug] };
}

function render(slug: string, arm: Arm): string {
  currentCompetition = slug;
  currentPayload = payloadFor(slug, arm);
  try {
    return renderToStaticMarkup(<CompetitionHubPage />);
  } finally {
    currentPayload = null;
  }
}

/**
 * `renderToStaticMarkup` HTML-escapes, and the extractor must undo that before
 * reading copy back (UX-P046's `&lt;1%` sentinel trap, inherited).
 */
function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/\s+/g, " ")
    .trim();
}

/** Only the section/rail HEADINGS, so an assertion cannot be satisfied by a
 *  market NAME that happens to contain the word (a real hazard here: several
 *  esports markets are literally about fighting games). */
function headings(html: string): string[] {
  return Array.from(html.matchAll(/<h2\b[^>]*>([\s\S]*?)<\/h2>/g)).map((m) =>
    visibleText(m[1]),
  );
}

/** The app's own compiled stylesheet, so the panels look like the product. */
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

const COMBAT_WORDS = ["Fight", "Fighter", "Cards"];
const DEFECTIVE = ["tennis", "golf", "esports"];
const CONTROL = ["mma", "boxing"];

describe("UX-P167 — the hub stops describing every sport as a fight card", () => {
  // ── The BEFORE side, reproduced from the shipped component ────────────────

  it("the fixture reproduces the five wrong headings production served", () => {
    const wrong = DEFECTIVE.flatMap((slug) =>
      hub(slug)
        .before_headers.filter((b) => COMBAT_WORDS.some((w) => b.header.includes(w)))
        .map((b) => `${slug}/${b.header}/${b.over}`),
    ).sort();
    expect(wrong).toEqual([
      "esports/Fight Markets/98",
      "golf/Fighter Stats/5",
      "golf/Upcoming Cards/3",
      "tennis/Fight Markets/103",
      "tennis/Upcoming Cards/12",
    ]);
    // …over this many markets and tournaments, so the size is pinned too.
    expect(hub("tennis").section_sizes.matches).toBe(103);
    expect(hub("esports").section_sizes.matches).toBe(98);
    expect(hub("golf").section_sizes.season_stats).toBe(5);
  });

  it.each(DEFECTIVE)("BEFORE: /hub/%s printed a combat heading", (slug) => {
    const hs = headings(render(slug, "before"));
    expect(hs.length).toBeGreaterThan(0); // vacuity: the page really rendered
    expect(hs.filter((h) => COMBAT_WORDS.some((w) => h.includes(w))).length).toBeGreaterThan(0);
  });

  // ── The AFTER side ────────────────────────────────────────────────────────

  it.each(DEFECTIVE)("AFTER: /hub/%s carries no fight vocabulary in any heading", (slug) => {
    const html = render(slug, "after");
    const hs = headings(html);
    expect(hs.length).toBeGreaterThan(0); // vacuity companion (gotcha #43)
    for (const h of hs) {
      for (const w of COMBAT_WORDS) {
        expect(h).not.toContain(w);
      }
    }
    // …and the page is still the page: the real market rows are present, so
    // "no fight words" cannot be satisfied by an empty or broken render.
    const text = visibleText(html);
    const firstSection = Object.keys(hub(slug).sections)[0];
    expect(text).toContain(hub(slug).sections[firstSection][0].name);
  });

  it("AFTER: tennis reads Matches and Upcoming Tournaments", () => {
    const hs = headings(render("tennis", "after"));
    expect(hs).toContain("Matches");
    expect(hs).toContain("Upcoming Tournaments");
    expect(hs).not.toContain("Fight Markets");
  });

  it("AFTER: golf reads Player Stats and Upcoming Tournaments", () => {
    const hs = headings(render("golf", "after"));
    expect(hs).toContain("Player Stats");
    expect(hs).toContain("Upcoming Tournaments");
    expect(hs).not.toContain("Fighter Stats");
  });

  it("AFTER: esports reads Matches", () => {
    const hs = headings(render("esports", "after"));
    expect(hs).toContain("Matches");
    expect(hs).not.toContain("Fight Markets");
  });

  // ── The other direction: combat must KEEP its words (gotcha #43) ──────────

  it.each(CONTROL)("AFTER: /hub/%s keeps its fight vocabulary", (slug) => {
    const hs = headings(render(slug, "after"));
    expect(hs).toContain("Upcoming Cards");
    if (hub(slug).section_sizes?.matches >= 2) {
      expect(hs).toContain("Fight Markets");
    }
    expect(hs.length).toBeGreaterThan(0);
  });

  // ── Degradation: a payload cached before this shipped ─────────────────────

  it.each([...DEFECTIVE, ...CONTROL])(
    "a pre-fix cached payload for /hub/%s degrades to neutral, never to another sport",
    (slug) => {
      const hs = headings(render(slug, "stale_cache"));
      expect(hs.length).toBeGreaterThan(0);
      for (const h of hs) {
        for (const w of COMBAT_WORDS) {
          expect(h).not.toContain(w);
        }
      }
    },
  );

  it("the neutral fallback for the upcoming rail is a real word, not an empty heading", () => {
    // A blank <h2> would technically pass every "not.toContain" above.
    const hs = headings(render("tennis", "stale_cache"));
    expect(hs).toContain("Upcoming");
    expect(hs.every((h) => h.length > 0)).toBe(true);
  });

  // ── Artifact ──────────────────────────────────────────────────────────────

  it("renders the before/after artifact", () => {
    const dir = process.env.UX_CAPTURE_DIR;
    const panels = DEFECTIVE.map((slug) => {
      const before = render(slug, "before");
      const after = render(slug, "after");
      return { slug, before, after, headings: { before: headings(before), after: headings(after) } };
    });
    // The rig asserts its own artifact: every panel differs, in the headings.
    for (const p of panels) {
      expect(p.headings.before).not.toEqual(p.headings.after);
      expect(p.before).not.toEqual(p.after);
    }
    if (!dir) return;

    const css = appStylesheet();
    const body = panels
      .map(
        (p) => `
<section class="cmp">
  <h2 class="cmp-title">/hub/${p.slug}</h2>
  <div class="cmp-grid">
    <div><div class="cmp-tag bad">BEFORE — shipped 2026-08-29</div><div class="frame">${p.before}</div></div>
    <div><div class="cmp-tag good">AFTER</div><div class="frame">${p.after}</div></div>
  </div>
  <p class="cmp-note">headings: <code>${p.headings.before.join(" · ")}</code> → <code>${p.headings.after.join(" · ")}</code></p>
</section>`,
      )
      .join("\n");
    const html = `<!doctype html><html><head><meta charset="utf-8">
<title>UX-P167 — the hub stops calling every sport a fight card</title>
<style>${css}</style>
<style>
 body{background:#f6f7f9;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;padding:28px}
 .cmp{max-width:1600px;margin:0 auto 40px}
 .cmp-title{font:600 20px/1.2 ui-monospace,monospace;margin:0 0 12px}
 .cmp-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}
 .cmp-tag{font:700 11px/1 ui-monospace,monospace;letter-spacing:.1em;padding:6px 8px;border-radius:6px;margin-bottom:8px;display:inline-block}
 .bad{background:#fde2e1;color:#8a1c13}.good{background:#dcf5e3;color:#0f6b32}
 .frame{background:#fff;border:1px solid #e3e6ea;border-radius:12px;overflow:hidden;max-height:900px;overflow-y:auto}
 .cmp-note{font:12px/1.5 ui-monospace,monospace;color:#555}
 h1{max-width:1600px;margin:0 auto 6px;font-size:26px}
 .sub{max-width:1600px;margin:0 auto 28px;color:#555;font-size:14px;line-height:1.6}
</style></head><body>
<h1>UX-P167 — the tennis and golf hubs stop calling themselves fight cards</h1>
<p class="sub">Both columns are the SHIPPED default export of <code>app/hub/[competition]/page.tsx</code>, rendered from the real
<code>GET /api/hub/{competition}</code> payloads pulled 2026-08-29 during US Open week
(<code>backend/tests/fixtures/uxp167_hub_vocabulary.json</code>). The only difference between the columns is the served
section vocabulary: BEFORE feeds the component the combat words the page used to hard-code for every competition.<br>
Live census: <b>FIGHT MARKETS</b> over 103 tennis markets and 98 esports markets, <b>FIGHTER STATS</b> over 5 golf markets,
<b>UPCOMING CARDS</b> over 12 tennis and 3 golf tournaments — five wrong headings, three hubs, every load.
MMA and boxing keep their fight vocabulary and are the control.</p>
${body}
</body></html>`;
    fs.mkdirSync(dir, { recursive: true });
    const out = path.join(dir, "ux-p167-hub-vocabulary.html");
    fs.writeFileSync(out, html, "utf8");
    expect(fs.statSync(out).size).toBeGreaterThan(2000);
  });
});
