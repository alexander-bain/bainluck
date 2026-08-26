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
 * Two jobs, and the second is why it lives under `__tests__`:
 *
 *   1. `UX_CAPTURE_DIR=<dir> npx jest --testPathPatterns=usOpenBracketCapture`
 *      writes `us-open-bracket.html`, every state at a 390px viewport.
 *
 *   2. With no env var set it is an ordinary test that renders each state and
 *      asserts the rig still works — a capture harness that has silently
 *      rotted is discovered at exactly the wrong moment.
 *
 * The fixture is a TEST ASSET. It lives under `__tests__/`, which the Next.js
 * app tree does not compile, so it cannot reach a production bundle even by
 * accident. On the real page this tab reads "Draw not released" until
 * `ingest_tournament_draw.py` latches `draw_released`.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import TournamentBracket from "@/components/tournament/TournamentBracket";
import { buildBracket, bracketProgress, type RoundName } from "@/lib/bracket";
import {
  SYNTHETIC_MENS_DRAW,
  SYNTHETIC_WOMENS_DRAW,
  syntheticFirstRoundResults,
  syntheticPartialResults,
} from "@/__tests__/fixtures/syntheticDraw";

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

const MENS_FRESH = buildBracket(SYNTHETIC_MENS_DRAW);
const WOMENS_FRESH = buildBracket(SYNTHETIC_WOMENS_DRAW);
const MENS_DAY = buildBracket(SYNTHETIC_MENS_DRAW, syntheticPartialResults(SYNTHETIC_MENS_DRAW, 33));
const MENS_R1_DONE = buildBracket(
  SYNTHETIC_MENS_DRAW,
  syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW)
);
const WOMENS_R1_DONE = buildBracket(
  SYNTHETIC_WOMENS_DRAW,
  syntheticFirstRoundResults(SYNTHETIC_WOMENS_DRAW)
);

describe("the bracket capture rig still renders every state", () => {
  it("renders the pre-ceremony state", () => {
    const html = renderToStaticMarkup(<TournamentBracket rounds={[]} drawReleased={false} />);
    expect(html).toContain('data-testid="bracket-unreleased"');
  });

  it("renders a fresh 128 draw for BOTH sides", () => {
    for (const rounds of [MENS_FRESH, WOMENS_FRESH]) {
      const html = renderToStaticMarkup(
        <TournamentBracket rounds={rounds} drawReleased initialRound="R128" />
      );
      expect((html.match(/data-testid="bracket-match"/g) ?? []).length).toBe(64);
      expect(html).toContain('data-testid="bracket-round-strip"');
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
    // was ~1,360px wide with a ~3,450px first column at a 390px viewport.
    for (const rounds of [MENS_FRESH, MENS_DAY, MENS_R1_DONE, WOMENS_R1_DONE]) {
      for (const round of ["R128", "R64", "R32", "QF", "F"] as RoundName[]) {
        const html = renderToStaticMarkup(
          <TournamentBracket rounds={rounds} drawReleased initialRound={round} />
        );
        expect((html.match(/data-testid="bracket-match"/g) ?? []).length).toBeLessThanOrEqual(64);
      }
    }
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
      rounds: ReturnType<typeof buildBracket>,
      released: boolean,
      initialRound?: RoundName
    ) => {
      const { played, total } = bracketProgress(rounds);
      return `
  <div class="col">
    <div class="cap">${caption}</div>
    <div class="phone">
      <header class="hero"><h1>US Open 2026</h1><p>Flushing Meadows &middot; 08-30 to 09-13</p></header>
      <div class="tabs"><span>Tournament</span><span class="on">Bracket</span></div>
      <div class="pills"><span${caption.includes("Women") ? "" : ' class="on"'}>Men's</span><span${
        caption.includes("Women") ? ' class="on"' : ""
      }>Women's</span></div>
      <div class="pad">${renderToStaticMarkup(
        <TournamentBracket rounds={rounds} drawReleased={released} initialRound={initialRound} />
      )}</div>
    </div>
    <div class="sub">${note}<br><b>${played} of ${total}</b> decided in this state.</div>
  </div>`;
    };

    const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>US Open bracket — dummy draw, for verdict</title>
<style>${appStylesheet()}</style>
<style>
  body{background:#F5F5F7;margin:0;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",Segoe UI,Roboto,sans-serif}
  .note{max-width:1300px;margin:0 auto;padding:16px;font-size:12.5px;line-height:1.6;color:#374151;background:#fff;border-bottom:1px solid #E5E7EB}
  .note b{color:#111827}
  .note ul{margin:8px 0 0;padding-left:18px}
  .rail{display:flex;gap:22px;justify-content:center;align-items:flex-start;flex-wrap:wrap;padding:20px 16px 60px;max-width:1400px;margin:0 auto}
  .col{width:390px}
  .phone{width:390px;background:#F5F5F7;border:1px solid #E5E7EB;border-radius:12px;overflow:hidden;max-height:760px;overflow-y:auto}
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
</style></head>
<body>
<div class="note">
<b>US Open bracket &mdash; DUMMY 128-slot draw, for verdict before Thursday.</b>
These are the SHIPPED component and the app's own compiled CSS at a 390px viewport. The names are
a synthetic fixture that lives under <code>__tests__/</code> and cannot reach a production bundle;
on the live page this tab reads &ldquo;Draw not released&rdquo; until the ceremony latches
<code>draw_released</code>. Each phone is scrollable &mdash; scroll inside one to see the full round.
<ul>
<li><b>One round at a time, chosen from the chip strip.</b> The first cut was seven side-by-side
columns; against a real 128 draw at this width that is ~1,360px wide and ~3,450px tall in the first
column alone, so finding a player meant scrolling in two dimensions through mostly whitespace. A
128 draw does not fit on a phone as a tree. The fold logic is unchanged, so a desktop tree can be
added later without touching the data path.</li>
<li><b>Nothing is projected.</b> An undecided match shows two names and no winner. A round nobody
has reached shows one sentence, not sixteen empty cards.</li>
<li><b>Most of the field carries no probability</b> &mdash; as a real 128 field does. A slot with no
priced source prints no number rather than a plausible one.</li>
</ul>
</div>
<div class="rail">
${phone(
  "1 &middot; Before the ceremony",
  "What the tab shows today, and until Thursday.",
  [],
  false
)}
${phone(
  "2 &middot; Men's &mdash; draw out, nothing played",
  "Thursday afternoon. 64 first-round matches, two names each, no winners.",
  MENS_FRESH,
  true,
  "R128"
)}
${phone(
  "3 &middot; Women's &mdash; draw out, nothing played",
  "The other draw, same component, a genuinely different field.",
  WOMENS_FRESH,
  true,
  "R128"
)}
${phone(
  "4 &middot; Men's &mdash; mid-day, 33 of 64 done",
  "The state a tournament day is actually in. Winners sit in R64 and go no further.",
  MENS_DAY,
  true,
  "R64"
)}
${phone(
  "5 &middot; Men's &mdash; first round complete",
  "Opens on R64 by itself: the round the tournament is in, not one that finished.",
  MENS_R1_DONE,
  true
)}
${phone(
  "6 &middot; Men's &mdash; a round nobody has reached",
  "One sentence instead of eight empty cards.",
  MENS_R1_DONE,
  true,
  "QF"
)}
${phone(
  "7 &middot; Women's &mdash; first round complete",
  "Decided matches: winner in bold, loser muted.",
  WOMENS_R1_DONE,
  true,
  "R128"
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
    // BOTH draws, which is the half of the ask a single-draw capture would miss.
    expect(html).toContain('data-entity="syn-m-1"');
    expect(html).toContain('data-entity="syn-w-1"');
    // And the stylesheet actually loaded — an unstyled capture is not a verdict.
    expect(appStylesheet().length).toBeGreaterThan(1000);
  });
});
