/**
 * ux/1002 — ARTIFACT: a card you can click and a card you cannot, side by side.
 *
 * Alex's second sentence — *"when none exists, render it visibly non-linked
 * (muted) so nobody clicks a dead card"* — is a claim about PIXELS, and the
 * only honest way to check it is to look. `data-linked="false"` was already on
 * the DOM before this change and it is not a thing anybody can see.
 *
 * Every card here is the shipped `TournamentMatches` fed the unedited
 * production payload (`tournamentHubLinkMap.20260901.json`). Nothing is drawn
 * by hand and no class is written into the page — the stylesheet is the REAL
 * one out of `.next/static/css`, so what renders is what Tailwind actually
 * shipped rather than a shim written to make the point.
 *
 *   UX_CAPTURE_DIR=<dir> npx jest --testPathPatterns=matchCardLinkStateCapture
 *   tools/render-captures.sh <dir>
 *
 * Two of the twelve rows cannot link, for two different and both-correct
 * reasons: `espn:182703` is the authority-named card whose register pairing was
 * withheld (Q503/Q505 — linking it would open "Jodar vs Kokkinakis" under two
 * names that are not those), and the Sherif–Bartunkova row has no market
 * pinned to dereference. Those are the two that must read as inert.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import TournamentMatches from "@/components/tournament/TournamentMatches";
import { matchListFromSlate } from "@/lib/matchList";
import type { SlateMatch } from "@/lib/slate";

const FRONTEND = path.join(__dirname, "..", "..");
const CAPTURE = JSON.parse(
  fs.readFileSync(
    path.join(FRONTEND, "__tests__", "fixtures", "tournamentHubLinkMap.20260901.json"),
    "utf8"
  )
) as { matches: SlateMatch[]; event_links: { by_matchup: Record<string, number> } };

const MATCHES = CAPTURE.matches;
const BY_MATCHUP = CAPTURE.event_links.by_matchup;

/** The real shipped Tailwind, so the artifact cannot flatter the change. */
function builtCss(): string {
  const dir = path.join(FRONTEND, ".next", "static", "css");
  if (!fs.existsSync(dir)) return "";
  return fs
    .readdirSync(dir)
    .filter((f) => f.endsWith(".css"))
    .map((f) => fs.readFileSync(path.join(dir, f), "utf8"))
    .join("\n");
}

describe("ux/1002 — artifact", () => {
  it("writes the link-state page when UX_CAPTURE_DIR is set", () => {
    const entries = matchListFromSlate(MATCHES);
    const withMap = renderToStaticMarkup(
      <TournamentMatches entries={entries} eventIds={BY_MATCHUP} initialExpanded />
    );
    /**
     * THE FAITHFUL BEFORE, and it is worth saying how it is built.
     *
     * The only visual change in this commit is the shell's `href === null`
     * branch, which used to draw the card with EXACTLY the linked card's
     * classes — the two states differed by `data-linked` and three `hover:`
     * rules, and a static shot renders no hover. So giving every row an id
     * reproduces the old appearance of all twelve rows precisely: twelve
     * identical white cards, two of which went nowhere.
     */
    const before = renderToStaticMarkup(
      <TournamentMatches
        entries={entries.map((e) => ({ ...e, eventId: e.eventId ?? 15293811 }))}
        initialExpanded
      />
    );

    const dir = process.env.UX_CAPTURE_DIR;
    if (!dir) {
      // Still a real assertion when nobody asked for pictures: ten of the
      // twelve link, and the BEFORE column really is twelve identical cards.
      expect(withMap.match(/data-linked="true"/g) ?? []).toHaveLength(10);
      expect(withMap.match(/border-dashed/g) ?? []).toHaveLength(2);
      expect(before.match(/border-dashed/g) ?? []).toHaveLength(0);
      return;
    }
    fs.mkdirSync(dir, { recursive: true });
    const page = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>ux/1002 — an unlinked match card looks unlinked</title>
<style>${builtCss()}</style>
<style>
 body{font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#F5F5F7;color:#111827;margin:0;padding:28px}
 h1{font-size:19px;margin:0 0 4px} p.sub{color:#6B7280;margin:0 0 22px;max-width:86ch}
 .cols{display:grid;grid-template-columns:1fr 1fr;gap:26px;align-items:start}
 h2{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:#6B7280;margin:0 0 10px}
 .col{background:#F5F5F7;border-radius:12px;padding:14px}
 .note{font-size:12px;color:#6B7280;margin-top:22px;max-width:110ch}
 mark{background:#FEF3C7;padding:0 3px;border-radius:3px}
</style></head><body>
<h1>ux/1002 — every Round-of-128 card links, and the two that cannot say so</h1>
<p class="sub">Both columns are the shipped <code>TournamentMatches</code> component rendered from the
unedited <code>GET /api/tournaments/us-open</code> payload of 2026-09-02 05:08 UTC, with the real
shipped stylesheet. Only the link source differs.</p>
<div class="cols">
  <div class="col"><h2>Before — twelve identical cards, two of them dead</h2>${before}</div>
  <div class="col"><h2>After — ten link, two are visibly inert</h2>${withMap}</div>
</div>
<p class="note"><strong>What to look at.</strong> In the LEFT column every row is a white card and
nothing distinguishes the two that go nowhere — <mark>Rafael Jodar v Bu Yunchaokete</mark> (8th) and
<mark>Nikola Bartunkova v Mayar Sherif</mark> (last) look exactly like the ten above them. That is the
shipped state: an unlinked card differed from a linked one only in <code>data-linked="false"</code>
and three <code>hover:</code> rules — nothing a phone can trigger and nothing an eye can see. In the
RIGHT column those same two rows are recessed onto the page grey with a dashed outline, and the other
ten are unchanged.</p>
<p class="note"><strong>Why those two.</strong> <code>espn:182703</code> is the authority-named row:
the register says the fixture is Jodar v Kokkinakis, ESPN says it is Bu Yunchaokete v Jodar, so
<code>build_slate</code> withholds the register pairing and rebuilds the card from the scoreboard with
no price. <code>event_links.by_matchup</code> holds a confident answer for the withheld key —
event 15300739, <em>"Jodar VS Kokkinakis"</em> — and following it would open a match page under two
names the card does not show. The <code>espn:</code> refusal in
<code>lib/tournamentEventLink.ts</code> is what stops that. Sherif–Bartunkova has no pinned market to
dereference at all.</p>
</body></html>`;
    const out = path.join(dir, "ux-1002-match-card-link-state.html");
    fs.writeFileSync(out, page);
    expect(fs.existsSync(out)).toBe(true);
  });
});
