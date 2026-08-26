/**
 * CAPTURE RIG — the bracket, both draws, at phone width, ahead of the ceremony.
 *
 * UX-P136, charter amendment 2026-08-25 ("blockers block items, never lanes").
 * Alex's verdict on the DUMMY bracket has to land before the real draw does,
 * so this renders the finished component against the synthetic 128-slot
 * fixture and writes one file he can open.
 *
 * Chromium is dead in this sandbox (Mach bootstrap denied), so a screenshot is
 * not available to this lane. This is the substitute the repo already uses and
 * that `usOpenBoardCapture` established: render the ACTUAL shipped component
 * with `renderToStaticMarkup`, wrap it in the app's OWN compiled stylesheet
 * from `.next/static/css`, and write a self-contained HTML file. It is the
 * real component and the real CSS — not a re-creation in mock markup.
 *
 * UX-P137 re-renders it with Alex's five bracket rulings applied, and the
 * PRE-DRAW panel leads, because the ceremony is tomorrow and that panel is
 * what a real visitor sees first today.
 *
 * Two jobs, and the second is why it lives under `__tests__`:
 *
 *   1. `UX_CAPTURE_DIR=<dir> npx jest --testPathPatterns=usOpenBracketCapture`
 *      writes `us-open-bracket.html`, every state at a 390px viewport.
 *
 *   2. With no env var set it is an ordinary test that renders each state and
 *      asserts the rig still works — a capture harness that has silently
 *      rotted is discovered at exactly the wrong moment.
 *
 * The draw fixture is a TEST ASSET. It lives under `__tests__/`, which the
 * Next.js app tree does not compile, so it cannot reach a production bundle
 * even by accident. On the real page this tab reads "Draw not released" until
 * `ingest_tournament_draw.py` latches `draw_released`.
 *
 * The BOARDS and the ADVANCE MARKETS in it are not synthetic — they are the
 * real production reads committed under `docs/mocks/us-open/`, which is what
 * makes the pre-draw panel a preview of Thursday rather than a drawing of one.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import TournamentBracket from "@/components/tournament/TournamentBracket";
import {
  buildBracket,
  bracketProgress,
  type PrematchPair,
  type RoundName,
} from "@/lib/bracket";
import type { PropMarket } from "@/lib/tournamentProps";
import type { TournamentPayload } from "@/lib/tournament";
import {
  SYNTHETIC_MENS_DRAW,
  SYNTHETIC_WOMENS_DRAW,
  syntheticDrawWithHoles,
  syntheticFirstRoundResults,
  syntheticPartialResults,
  syntheticPrematch,
} from "@/__tests__/fixtures/syntheticDraw";

const MOCKS = path.join(__dirname, "..", "..", "..", "docs", "mocks", "us-open");

/** The app's real compiled Tailwind, so the capture is not a lookalike. */
function appStylesheet(): string {
  const dir = path.join(__dirname, "..", "..", ".next", "static", "css");
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

/** The real championship boards — a bounded production read, committed. */
const PAYLOAD = JSON.parse(
  fs.readFileSync(path.join(MOCKS, "payload-2026-08-25.json"), "utf8")
) as TournamentPayload;

/** The register's eleven curated props, priced by the backend's own build_props. */
const PROPS = JSON.parse(
  fs.readFileSync(path.join(MOCKS, "props-2026-08-26.json"), "utf8")
) as PropMarket[];

const MENS_FRESH = buildBracket(SYNTHETIC_MENS_DRAW);
const WOMENS_FRESH = buildBracket(SYNTHETIC_WOMENS_DRAW);

const DAY_RESULTS = syntheticPartialResults(SYNTHETIC_MENS_DRAW, 33);
const MENS_DAY = buildBracket(SYNTHETIC_MENS_DRAW, DAY_RESULTS);
const MENS_DAY_PREMATCH = syntheticPrematch(DAY_RESULTS, SYNTHETIC_MENS_DRAW);

/**
 * EARLY AFTERNOON — three matches in.
 *
 * Needed because the 33-of-64 state, collapsed to five, shows five COMPLETE
 * R64 pairs: 33 decided fills matches 1-16 outright and only leaves match 17
 * half-filled, which is off the bottom of a collapsed list. The panel Alex
 * called uninterpretable would have rendered with no feeder text in it at all
 * and the artifact would have claimed a fix it did not show. At three decided,
 * R64's second card is a name against a hole, on screen, first five.
 */
const EARLY_RESULTS = syntheticPartialResults(SYNTHETIC_MENS_DRAW, 3);
const MENS_EARLY = buildBracket(SYNTHETIC_MENS_DRAW, EARLY_RESULTS);
const MENS_EARLY_PREMATCH = syntheticPrematch(EARLY_RESULTS, SYNTHETIC_MENS_DRAW);

const R1_RESULTS = syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW);
const MENS_R1_DONE = buildBracket(SYNTHETIC_MENS_DRAW, R1_RESULTS);
const MENS_R1_PREMATCH = syntheticPrematch(R1_RESULTS, SYNTHETIC_MENS_DRAW);

const W_R1_RESULTS = syntheticFirstRoundResults(SYNTHETIC_WOMENS_DRAW);
const WOMENS_R1_DONE = buildBracket(SYNTHETIC_WOMENS_DRAW, W_R1_RESULTS);
const WOMENS_R1_PREMATCH = syntheticPrematch(W_R1_RESULTS, SYNTHETIC_WOMENS_DRAW);

const HOLED = buildBracket(syntheticDrawWithHoles(SYNTHETIC_MENS_DRAW, [1, 4, 9]));

describe("the bracket capture rig still renders every state", () => {
  it("renders the pre-ceremony state WITH both winner boards", () => {
    // Ruling 1. The panel that leads the artifact, because the ceremony is
    // tomorrow and this is what a visitor sees until it happens.
    const html = renderToStaticMarkup(
      <TournamentBracket rounds={[]} drawReleased={false} preDrawBoards={PAYLOAD.boards} />
    );
    expect(html).toContain('data-testid="bracket-unreleased"');
    expect((html.match(/data-testid="tournament-board"/g) ?? []).length).toBe(2);
  });

  it("renders a fresh 128 draw for BOTH sides, collapsed", () => {
    for (const rounds of [MENS_FRESH, WOMENS_FRESH]) {
      const html = renderToStaticMarkup(
        <TournamentBracket rounds={rounds} drawReleased initialRound="R128" />
      );
      expect((html.match(/data-testid="bracket-match"/g) ?? []).length).toBe(5);
      expect(html).toContain('data-testid="bracket-round-strip"');
      expect(html).toContain('data-testid="bracket-column-label"');
    }
  });

  it("renders a part-played day and a completed first round", () => {
    for (const rounds of [MENS_DAY, MENS_R1_DONE, WOMENS_R1_DONE]) {
      const html = renderToStaticMarkup(<TournamentBracket rounds={rounds} drawReleased />);
      expect(html).toContain('data-testid="tournament-bracket"');
    }
  });

  it("the two draws are genuinely different fields, not the same one twice", () => {
    // A capture that shows the men's draw in both phones would pass every
    // other assertion here and still fail the thing Alex is being asked to
    // verdict — "both draws".
    const men = renderToStaticMarkup(
      <TournamentBracket rounds={MENS_FRESH} drawReleased initialRound="R128" />
    );
    const women = renderToStaticMarkup(
      <TournamentBracket rounds={WOMENS_FRESH} drawReleased initialRound="R128" />
    );
    expect(men).toContain('data-entity="syn-m-1"');
    expect(men).not.toContain('data-entity="syn-w-1"');
    expect(women).toContain('data-entity="syn-w-1"');
    expect(women).not.toContain('data-entity="syn-m-1"');
  });

  it("no state ever puts the whole 127-match draw on the page", () => {
    // The layout gate this rig exists to prove. The old seven-column render
    // was ~1,360px wide with a ~3,450px first column at a 390px viewport, and
    // since UX-P137 even one round is five cards until the reader asks.
    for (const rounds of [MENS_FRESH, MENS_DAY, MENS_R1_DONE, WOMENS_R1_DONE]) {
      for (const round of ["R128", "R64", "R32", "QF", "F"] as RoundName[]) {
        const html = renderToStaticMarkup(
          <TournamentBracket rounds={rounds} drawReleased initialRound={round} />
        );
        expect((html.match(/data-testid="bracket-match"/g) ?? []).length).toBeLessThanOrEqual(5);
      }
    }
  });

  it("the committed props file really carries the advance-to-stage markets", () => {
    // If this file goes stale the ruling-4 panel silently renders empty, and
    // an empty panel is exactly what the ruling was issued about.
    expect(PROPS.length).toBe(11);
    const advance = PROPS.filter((p) => /(-semifinals|-quarterfinals|-round-of-16)$/.test(p.key));
    expect(advance.length).toBe(8);
  });

  it("writes the capture when UX_CAPTURE_DIR is set", () => {
    const dir = process.env.UX_CAPTURE_DIR;
    if (!dir) {
      expect(true).toBe(true);
      return;
    }
    fs.mkdirSync(dir, { recursive: true });

    const phone = (
      caption: string,
      note: string,
      body: React.ReactElement,
      progress: { played: number; total: number } | null,
      women = false
    ) => `
  <div class="col">
    <div class="cap">${caption}</div>
    <div class="phone">
      <header class="hero"><h1>US Open 2026</h1><p>Flushing Meadows &middot; 08-30 to 09-13</p></header>
      <div class="tabs"><span>Tournament</span><span class="on">Bracket</span></div>
      <div class="pills"><span${women ? "" : ' class="on"'}>Men's</span><span${
        women ? ' class="on"' : ""
      }>Women's</span></div>
      <div class="pad">${renderToStaticMarkup(body)}</div>
    </div>
    <div class="sub">${note}${
      progress
        ? `<br><b>${progress.played} of ${progress.total}</b> decided in this state.`
        : ""
    }</div>
  </div>`;

    const bracket = (props: {
      rounds: ReturnType<typeof buildBracket>;
      initialRound?: RoundName;
      prematch?: Record<string, PrematchPair>;
      initialExpanded?: boolean;
      draw?: string;
    }) => (
      <TournamentBracket
        rounds={props.rounds}
        drawReleased
        initialRound={props.initialRound}
        prematch={props.prematch}
        initialExpanded={props.initialExpanded}
        propMarkets={PROPS}
        draw={props.draw ?? "mens-singles"}
      />
    );

    const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>US Open bracket — Alex's five rulings applied</title>
<style>${appStylesheet()}</style>
<style>
  body{background:#F5F5F7;margin:0;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",Segoe UI,Roboto,sans-serif}
  .note{max-width:1300px;margin:0 auto;padding:16px;font-size:12.5px;line-height:1.6;color:#374151;background:#fff;border-bottom:1px solid #E5E7EB}
  .note b{color:#111827}
  .note ol{margin:8px 0 0;padding-left:20px}
  .note li{margin-bottom:5px}
  .rail{display:flex;gap:22px;justify-content:center;align-items:flex-start;flex-wrap:wrap;padding:20px 16px 60px;max-width:1400px;margin:0 auto}
  .col{width:390px}
  .phone{width:390px;background:#F5F5F7;border:1px solid #E5E7EB;border-radius:12px;overflow:hidden;max-height:820px;overflow-y:auto}
  .cap{font:700 11.5px inherit;letter-spacing:.07em;text-transform:uppercase;color:#6B7280;padding:0 2px 7px}
  .sub{padding:9px 2px 0;font-size:11.5px;line-height:1.5;color:#6B7280}
  .sub b{color:#111827}
  .tabs{display:flex;border-bottom:1px solid #E5E7EB;background:#fff}
  .tabs span{flex:1;text-align:center;padding:13px 0;font:600 13.5px inherit;color:#9CA3AF;border-bottom:2px solid transparent}
  .tabs span.on{color:#111827;border-bottom-color:#111827}
  .pills{display:flex;gap:6px;padding:12px 16px;background:#fff;border-bottom:1px solid #E5E7EB}
  .pills span{border-radius:999px;padding:6px 14px;font:600 13px inherit;background:#F0F0F2;color:#6B7280}
  .pills span.on{background:#111827;color:#F8FAFC}
  header.hero{padding:16px;background:#fff;border-bottom:1px solid #E5E7EB}
  header.hero h1{margin:0;font-size:24px;letter-spacing:-.02em;color:#111827}
  header.hero p{margin:2px 0 0;font-size:13px;color:#6B7280}
  .pad{padding:16px}
  .lead{background:#111827;color:#F8FAFC;padding:10px 16px;font:700 12px inherit;letter-spacing:.06em;text-transform:uppercase}
</style></head>
<body>
<div class="note">
<b>US Open bracket &mdash; Alex's five rulings applied. Panel 1 leads, because the ceremony is tomorrow.</b>
These are the SHIPPED component and the app's own compiled CSS at a 390px viewport. The DRAW names are
a synthetic fixture that lives under <code>__tests__/</code> and cannot reach a production bundle; the
BOARDS and the advance-to-stage markets are real production reads. Each phone scrolls &mdash; scroll
inside one to see the whole panel.
<ol>
<li><b>The pre-draw view is not empty.</b> Both winner markets exist before the draw does, so the tab
shows both boards under the honest sentence. This is the state every visitor sees until Thursday.</li>
<li><b>Every percentage carries its column header.</b> The answer to your question: it is the chance of
winning the WHOLE TOURNAMENT &mdash; <code>build_bracket</code> fills each slot from the register
player's <code>kind: "outright"</code> sources, the champion market, the same outcomes the board reads.
It now says so. A decided card means something different by its number, so it says <b>Pre-match</b>
itself.</li>
<li><b>Nothing renders blank.</b> An undetermined slot names the match its occupant comes from
(&ldquo;Winner of R128 #23&rdquo;); a round-one hole says &ldquo;No registered player&rdquo;, which is
what the backend contract calls it. A decided match prints the pre-match probability and an explicit
<b>Won</b>/<b>Out</b>.</li>
<li><b>An unreached round shows the markets on reaching it</b> &mdash; the register carries eight,
priced. Pattern borrowed from <code>ProgressionLadder</code>, the MLB/NBA playoff table. (You recalled
the Masters doing this; it does not &mdash; golf buckets props into sections and has no stage ladder.)</li>
<li><b>Five, then expand</b>, on every list in every view.</li>
</ol>
</div>

<div class="lead">1 &mdash; What a visitor sees today, and until the ceremony</div>
<div class="rail">
${phone(
  "1 &middot; Before the draw &mdash; ruling 1",
  "Real production boards, both draws, on the Bracket tab. The old version of this panel was one sentence and nothing else.",
  <TournamentBracket rounds={[]} drawReleased={false} preDrawBoards={PAYLOAD.boards} />,
  null
)}
</div>

<div class="lead">2 &mdash; The draw is out</div>
<div class="rail">
${phone(
  "2 &middot; Men's &mdash; nothing played",
  "Thursday afternoon. Five of sixty-four, then an expander &mdash; and the column says what its number is.",
  bracket({ rounds: MENS_FRESH, initialRound: "R128" }),
  bracketProgress(MENS_FRESH)
)}
${phone(
  "3 &middot; Men's &mdash; the same round, expanded",
  "What &ldquo;Show all 64&rdquo; opens onto. This is the state that used to be the DEFAULT.",
  bracket({ rounds: MENS_FRESH, initialRound: "R128", initialExpanded: true }),
  bracketProgress(MENS_FRESH)
)}
${phone(
  "4 &middot; Women's &mdash; nothing played",
  "The other draw, same component, a genuinely different field.",
  bracket({ rounds: WOMENS_FRESH, initialRound: "R128", draw: "womens-singles" }),
  bracketProgress(WOMENS_FRESH),
  true
)}
</div>

<div class="lead">3 &mdash; Ruling 3: no blank rows, in the two states that produce them</div>
<div class="rail">
${phone(
  "5 &middot; Early afternoon, 3 of 64 &mdash; ruling 3",
  "The first results land. Card 2 of the next round is a name against a slot that names its feeder &mdash; this is the row that used to read &ldquo;&mdash; v &mdash;&rdquo;.",
  bracket({ rounds: MENS_EARLY, initialRound: "R64", prematch: MENS_EARLY_PREMATCH }),
  bracketProgress(MENS_EARLY)
)}
${phone(
  "6 &middot; Mid-day, 33 of 64, expanded &mdash; ruling 3",
  "The state a tournament day is actually in, whole. Sixteen filled pairs, then seventeen cards each naming what they are waiting on.",
  bracket({
    rounds: MENS_DAY,
    initialRound: "R64",
    prematch: MENS_DAY_PREMATCH,
    initialExpanded: true,
  }),
  bracketProgress(MENS_DAY)
)}
${phone(
  "7 &middot; Decided matches &mdash; ruling 3",
  "Pre-match probability and an explicit outcome on both sides. The header says <b>Pre-match</b>, not the title label, because that is what the number is.",
  bracket({ rounds: MENS_R1_DONE, initialRound: "R128", prematch: MENS_R1_PREMATCH }),
  bracketProgress(MENS_R1_DONE)
)}
${phone(
  "8 &middot; A draw with register holes &mdash; ruling 3",
  "A round-one hole is not an unplayed feeder and does not get the feeder sentence.",
  bracket({ rounds: HOLED, initialRound: "R128" }),
  bracketProgress(HOLED)
)}
${phone(
  "9 &middot; Women's &mdash; first round complete",
  "The same decided treatment on the other draw.",
  bracket({
    rounds: WOMENS_R1_DONE,
    initialRound: "R128",
    prematch: WOMENS_R1_PREMATCH,
    draw: "womens-singles",
  }),
  bracketProgress(WOMENS_R1_DONE),
  true
)}
</div>

<div class="lead">4 &mdash; Ruling 4: an unreached round is content, not emptiness</div>
<div class="rail">
${phone(
  "10 &middot; Men's semi-finals &mdash; ruling 4",
  "Nobody is there yet, and four real markets say who the market thinks gets there. Real Polymarket prices, 24-27h old, muted accordingly.",
  bracket({ rounds: MENS_R1_DONE, initialRound: "SF", prematch: MENS_R1_PREMATCH }),
  bracketProgress(MENS_R1_DONE)
)}
${phone(
  "11 &middot; Men's quarter-finals &mdash; ruling 4",
  "A different round, a different question, its own column label.",
  bracket({ rounds: MENS_R1_DONE, initialRound: "QF", prematch: MENS_R1_PREMATCH }),
  bracketProgress(MENS_R1_DONE)
)}
${phone(
  "12 &middot; Women's second week &mdash; ruling 4",
  "The women's tab has one. It shows one &mdash; not a padded five.",
  bracket({
    rounds: WOMENS_R1_DONE,
    initialRound: "R16",
    draw: "womens-singles",
  }),
  bracketProgress(WOMENS_R1_DONE),
  true
)}
${phone(
  "13 &middot; The final &mdash; no market, no table",
  "The other direction: a bordered empty table under a round we hold nothing for would re-add the emptiness ruling 4 removes.",
  bracket({ rounds: MENS_R1_DONE, initialRound: "F", prematch: MENS_R1_PREMATCH }),
  bracketProgress(MENS_R1_DONE)
)}
</div>
</body></html>`;

    const out = path.join(dir, "us-open-bracket.html");
    fs.writeFileSync(out, html);

    // The rig must not silently write a page whose panels failed to render.
    expect(fs.existsSync(out)).toBe(true);
    expect(html.length).toBeGreaterThan(20000);
    expect(html).toContain('data-testid="bracket-unreleased"');
    expect(html).toContain('data-testid="tournament-bracket"');
    expect(html).toContain('data-testid="bracket-round-strip"');
    expect(html).toContain('data-testid="bracket-round-unreached"');
    expect(html).toContain('data-won="true"');

    // ---- one assertion per ruling, so a panel cannot go quietly empty ----
    // 1. The pre-draw panel really carries BOTH boards.
    expect((html.match(/data-testid="tournament-board"/g) ?? []).length).toBe(2);
    // 2. Both column vocabularies are on the page and neither is missing.
    expect(html).toContain("To win the title");
    expect(html).toContain("Pre-match");
    expect(html).toContain("To reach the semi-finals");
    expect(html).toContain("To reach the quarter-finals");
    // 3. No blank row survives anywhere in the artifact.
    // Not just the prose above: the RENDERED rows must carry it. An earlier
    // cut of this rig matched only the explanatory note, because the panel it
    // was meant to prove had five complete pairs at the top of a collapsed
    // list and no feeder text on screen at all.
    expect(
      (html.match(/data-testid="bracket-slot-empty" data-from="R128-/g) ?? []).length
    ).toBeGreaterThan(10);
    expect(html).toContain("No registered player");
    expect(html).toContain('data-outcome="won"');
    expect(html).toContain('data-outcome="out"');
    expect(html).toContain('data-testid="bracket-prematch"');
    // 4. The advance table rendered with real rows, not an empty frame.
    expect(html).toContain('data-testid="bracket-advance"');
    expect((html.match(/data-testid="bracket-advance-row"/g) ?? []).length).toBeGreaterThan(4);
    // 5. Collapsed and expanded are BOTH on the page.
    expect(html).toContain("Show all 64");
    expect((html.match(/data-testid="bracket-match"/g) ?? []).length).toBeGreaterThan(64);
    // BOTH draws, which is the half of the ask a single-draw capture would miss.
    expect(html).toContain('data-entity="syn-m-1"');
    expect(html).toContain('data-entity="syn-w-1"');
    // And the stylesheet actually loaded — an unstyled capture is not a verdict.
    expect(appStylesheet().length).toBeGreaterThan(1000);
  });
});
