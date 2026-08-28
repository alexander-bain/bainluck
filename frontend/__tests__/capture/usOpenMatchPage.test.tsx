/**
 * THE RENDERED ANSWER TO ALEX'S QUESTION (UX-P149).
 *
 *     "Will those flow into the event page for each match, and will they look
 *      good?"
 *
 * Three panels, in one file, full width, so every media query is the one his
 * own window fires:
 *
 *   1. **A match still to come** — the primary state. Eight questions under a
 *      live match-winner pair.
 *   2. **A match that is over** — the same page, reading the opening numbers,
 *      with the section renamed. This is the state that is easy to get wrong:
 *      a prop market does not reliably settle, so the current number on
 *      "Who wins set 1" is still the pre-match one hours after that set was
 *      played and lost.
 *   3. **The way in** — the match list row that now carries a link, because a
 *      page nobody can reach is not a ship.
 *
 *   UX_CAPTURE_DIR=<dir> TZ=UTC npx jest --testPathPatterns=usOpenMatchPage
 *     → p149-match-page.html
 *
 * With no env var set it is an ordinary test that renders every panel and
 * asserts the rig still works.
 *
 * ═══ WHAT IS FAITHFUL ═══
 *
 * All of it. The components are the shipped ones, the CSS is the app's own
 * compiled bundle from `.next/static/css`, and both payloads were captured
 * from production by `backend/scripts/capture_match_payload.py` — which
 * reproduces the route by calling the same `build_*` functions rather than
 * re-implementing them. There is no BEFORE panel here because there was no
 * before: this surface did not exist.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import MatchHero from "@/components/tournament/MatchHero";
import MatchProps from "@/components/tournament/MatchProps";
import TournamentMatches from "@/components/tournament/TournamentMatches";
import { visibleProps, type MatchDetailPayload } from "@/lib/matchDetail";
import { buildMatchList } from "@/lib/matchList";

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const MOCKS = path.join(REPO, "docs", "mocks", "us-open");
/** Fixed, so the artifact does not redraw itself differently every run. */
const NOW = new Date("2026-08-28T12:00:00Z");

function load(name: string): MatchDetailPayload {
  return JSON.parse(fs.readFileSync(path.join(MOCKS, name), "utf8"));
}

const UPCOMING = load("match-upcoming-2026-08-28.json");
const DECIDED = load("match-decided-2026-08-28.json");

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

/** The page body, exactly as `app/tournaments/[slug]/matches/[key]/page.tsx` lays it out. */
function MatchPagePanel({ payload }: { payload: MatchDetailPayload }) {
  return (
    <div className="w-full">
      <div className="px-4 pb-10 pt-3 lg:px-6">
        <span className="inline-block text-[12px] font-semibold text-text-secondary">
          ← {payload.title}
        </span>
        <div className="mt-2.5">
          <MatchHero
            match={payload.match}
            result={payload.result}
            decided={payload.decided}
            now={NOW}
          />
        </div>
        <MatchProps payload={payload} />
      </div>
    </div>
  );
}

/**
 * The panel captions are DERIVED, not written.
 *
 * The first draft hard-coded "Wendelken v Gaubas, eight questions, three rungs
 * at 21.5 / 22.5 / 23.5" — and then the specimen changed (ESPN decided that
 * match mid-queue) and the caption described a page that was no longer in the
 * artifact. A caption that can disagree with the picture above it is worse
 * than no caption: it is the artifact lying with authority.
 */
function who(payload: MatchDetailPayload): string {
  return payload.match.sides.map((side) => side.display_name).join(" v ");
}

function ladderNote(payload: MatchDetailPayload): string {
  const ladder = visibleProps(payload).find((prop) => prop.kind === "ladder");
  if (!ladder) return "";
  return `${ladder.question} is ${ladder.market_ids.length} separate markets collapsed into one card — ${ladder.answers
    .map((answer) => answer.label)
    .join(" / ")} as rungs of one falling curve rather than near-identical cards.`;
}

function heroMove(payload: MatchDetailPayload): string {
  const move = payload.match.sides[0]?.move;
  if (typeof move !== "number") return "since it opened";
  return `${move > 0 ? "+" : "−"}${Math.abs(Math.round(move * 100))} points`;
}

function settledPct(payload: MatchDetailPayload): string {
  const winner = payload.match.sides.find(
    (side) => side.entity_key === payload.result?.winner_entity_key
  );
  const value = winner?.probability;
  // `toFixed(1)` on 0.9995 prints "100.0%", which is a caption rounding a
  // number up into a claim. Two places, so the artifact never overstates.
  return typeof value === "number" ? `${(value * 100).toFixed(2)}%` : "its settled number";
}

function matchListPanel(payload: MatchDetailPayload): string {
  const entries = buildMatchList({
    slate: [payload.match],
    rounds: [],
    prematch: {},
    titleChances: {},
  });
  return renderToStaticMarkup(
    <div className="px-4 lg:px-6">
      <TournamentMatches
        entries={entries}
        slug={payload.slug}
        initialExpanded
        initialOpenMatchId={entries[0]?.id}
      />
    </div>
  );
}

describe("UX-P149 — the match page, rendered", () => {
  it("both payloads carry what the panels are for", () => {
    expect(UPCOMING.decided).toBe(false);
    expect(DECIDED.decided).toBe(true);
    expect(visibleProps(UPCOMING).length).toBeGreaterThanOrEqual(6);
    expect(visibleProps(DECIDED).length).toBeGreaterThanOrEqual(6);
  });

  it("every panel renders something", () => {
    for (const payload of [UPCOMING, DECIDED]) {
      const html = renderToStaticMarkup(<MatchPagePanel payload={payload} />);
      expect(html).toContain('data-testid="match-hero"');
      expect(html).toContain('data-testid="match-prop"');
    }
    expect(matchListPanel(UPCOMING)).toContain('data-testid="match-page-link"');
  });

  it("writes the artifact when UX_CAPTURE_DIR is set", () => {
    const dir = process.env.UX_CAPTURE_DIR;
    if (!dir) {
      expect(true).toBe(true);
      return;
    }
    fs.mkdirSync(dir, { recursive: true });

    const css = appStylesheet();
    const panel = (tag: string, tone: string, head: string, body: string) => `
<div class="panel-head"><span class="tag ${tone}">${tag}</span> ${head}</div>
<div class="rule"></div>
<div class="panel">${body}</div>`;

    const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>UX-P149 — match props on the match's own page</title>
<style>${css}</style>
<style>
  body{background:#F5F5F7;margin:0;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",Segoe UI,Roboto,sans-serif}
  .banner{padding:16px 22px;font-size:13px;line-height:1.65;color:#374151;background:#fff;border-bottom:1px solid #E5E7EB}
  .banner b{color:#111827}
  .banner ul{margin:8px 0 0;padding-left:18px}
  .tag{display:inline-block;margin-right:10px;padding:3px 9px;border-radius:6px;font:700 11px inherit;letter-spacing:.06em;text-transform:uppercase}
  .tag.a{background:#EFF6FF;color:#1E40AF}
  .tag.b{background:#FFF7ED;color:#9A3412}
  .tag.c{background:#ECFDF5;color:#065F46}
  .panel{padding:8px 0 44px;background:#F5F5F7}
  .panel-head{padding:20px 22px 6px;font-size:13px;color:#4B5563;line-height:1.6;background:#fff}
  .rule{height:1px;background:#E5E7EB}
</style></head>
<body>
<div class="banner">
  <b>UX-P149 — match props, on each match's own page, grouped under the match-winner market.</b>
  This is the surface lane1's Q426 note routed the props to and could not build, because tennis
  matches have no <code>events</code> row. It is keyed on the register's <code>matchup_key</code>
  instead, so it needed no new identity decision.
  <ul>
    <li>Both pages are drawn from <b>production payloads captured minutes before this ran</b>,
        through the same builders the route calls. Real Polymarket numbers, real ESPN result.</li>
    <li><b>Resize the window</b> — the questions go to two columns at <code>lg</code>, and the
        page has no width of its own (UX-P146).</li>
    <li>Nothing here says <i>Yes</i>, <i>No</i>, <i>Over</i>, <i>Under</i>, <i>O/U</i>,
        <i>handicap</i> or <i>spread</i>. Those are the words the market stores; the guard suite
        fails if any of them reaches the screen.</li>
  </ul>
</div>
${panel(
  "1 — still to come",
  "a",
  `${who(UPCOMING)}. ${visibleProps(UPCOMING).length} questions under a live match-winner pair.
   <b>${ladderNote(UPCOMING)}</b>
   Note what the freshness treatment is doing here: the winner market is live and has
   moved ${heroMove(UPCOMING)}, while every question under it was last quoted a day ago and is
   drawn muted with its age against it. That gap is real, and the page is meant to show it
   rather than paint the old numbers in the confident type.`,
  renderToStaticMarkup(<MatchPagePanel payload={UPCOMING} />)
)}
${panel(
  "2 — over",
  "b",
  `${who(DECIDED)}. The same page after the result. <b>Every number is the OPENING one</b>
   and the section is renamed, because a prop market does not reliably settle: on this match the
   winner market reads ${settledPct(DECIDED)} for the winner while &ldquo;Who wins set 1&rdquo;
   still reads its pre-match number for the man who won that set and then lost the match.
   Showing the current number here would be a live-looking question with a stale answer — and
   the hero would read 100 / 0, which is just the result handed back.`,
  renderToStaticMarkup(<MatchPagePanel payload={DECIDED} />)
)}
${panel(
  "3 — the way in",
  "c",
  "The match list row, tapped. The link is keyed on the register's matchup key, which is why it renders — the <code>event_id</code> affordance beside it has been dead on every US Open match since UX-P139 because no <code>events</code> row exists.",
  matchListPanel(UPCOMING)
)}
</body></html>`;

    fs.writeFileSync(path.join(dir, "p149-match-page.html"), html);

    // The rig asserts its own artifact — a capture that writes an empty page
    // reports success exactly like one that works.
    const written = fs.readFileSync(path.join(dir, "p149-match-page.html"), "utf8");
    expect(written.length).toBeGreaterThan(20000);
    expect(written.split('data-testid="match-hero"').length - 1).toBe(2);
    expect(written).toContain("What the market thought beforehand");
    expect(written).toContain("More on this match");
    expect(written).toContain('data-testid="match-page-link"');
    expect(css.length).toBeGreaterThan(1000);
  });
});
