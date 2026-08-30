/**
 * UX-P168 — THE GOLF PAGE STOPS SERVING A DARTS TOURNAMENT, for Alex's eyeball.
 *
 * ═══ WHAT THIS IS ═══
 *
 * `/api/golf` served six tournaments on 2026-08-29. Two of them were not golf:
 *
 *   • "New Zealand Darts Masters" — a 16-strong field of professional darts
 *     players (Simon Whitlock, Gerwyn Price, James Wade). The card leads with
 *     "Simon Whitlock 6.4%".
 *   • "Asia Masters 2026"         — four League of Legends teams. The card leads
 *     with "Dplus Challengers 21.6%" and lists "Academy" (T1 Esports Academy) as
 *     a chaser.
 *
 * and BOTH were badged **⛳ PGA Tour**, because `_classify_tour` defaults to PGA
 * when nothing declares a tour. So the reader was not merely shown a darts
 * tournament on the golf page — they were told it was a PGA Tour event.
 *
 * ═══ WHAT EVERY PANEL IS MADE OF ═══
 *
 * Every card here is the SHIPPED `TournamentCard`, and every tournament comes
 * from `backend/tests/fixtures/uxp168_golf_foreign_domain.json` — the verbatim
 * `GET /api/golf` payload captured before a line of the fix was written. Nothing
 * on this page is drawn by hand.
 *
 * ═══ HOW "BEFORE" AND "AFTER" ARE PRODUCED, EXACTLY ═══
 *
 * This is a PAYLOAD difference, not a text substitution: the fix is entirely in
 * the backend, and it changes which tournaments are served. So BEFORE is the six
 * banked tournaments rendered by the shipped component, and AFTER is the same
 * component over the subset the fixed backend serves. Both columns are genuine
 * renders of the same component; only the input differs, which is exactly what
 * changed in production.
 *
 * The AFTER subset is chosen by `survives_uxp168`, a flag computed by the SHIPPED
 * Python predicate when the fixture was built — and re-derived from that predicate
 * on every backend run by
 * `backend/tests/test_golf_foreign_domain_membership.py::TestTheSurvivalFlagsTheFrontendRigTrusts`.
 * If this rig and the backend ever disagree about what is served, that suite goes
 * red rather than this artifact quietly drawing a fictional page.
 *
 *   UX_CAPTURE_DIR=<dir> TZ=UTC npx jest --testPathPatterns=golfForeignTournamentCapture
 *
 * With no env var set it is an ordinary test that renders both columns and
 * asserts the rig works, same as the other capture rigs.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import TournamentCard from "@/components/TournamentCard";
import type { GolfTournament } from "@/lib/types";

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const FIXTURE = path.join(
  REPO,
  "backend",
  "tests",
  "fixtures",
  "uxp168_golf_foreign_domain.json",
);

interface BankedTournament extends GolfTournament {
  survives_uxp168: boolean;
  market_ids: number[];
  surviving_market_ids: number[];
}

const BANKED = JSON.parse(fs.readFileSync(FIXTURE, "utf8")) as {
  served_tournaments_before: BankedTournament[];
};

const BEFORE = BANKED.served_tournaments_before;
const AFTER = BEFORE.filter((t) => t.survives_uxp168);

/** The two intruders, by the names the reader actually saw. */
const DARTS = "New Zealand Darts Masters";
const ESPORTS = "Asia Masters 2026";
/**
 * Field members no golf page may ever print.
 *
 * `TournamentCard` prints the LEADER's full name and the chasers by surname only,
 * so this is deliberately the set the component actually renders — not every name
 * in the payload. Asserting on a name the card never prints would be a guard that
 * cannot fail.
 */
const INTRUDERS = [
  "Simon Whitlock", // darts leader, printed in full
  "Dplus Challengers", // esports leader, printed in full
  "Milne", // darts chaser surname (Kayden Milne)
  "Puha", // darts chaser surname (Haupai Puha)
];

function renderColumn(tournaments: BankedTournament[]): string {
  return tournaments
    .map((t) => renderToStaticMarkup(<TournamentCard tournament={t} />))
    .join("\n");
}

/** `renderToStaticMarkup` escapes entities; unescape before matching copy. */
function text(markup: string): string {
  return markup
    .replace(/&#x27;/g, "'")
    .replace(/&#39;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

describe("UX-P168 — the banked BEFORE is what we claim", () => {
  it("banked six tournaments", () => {
    expect(BEFORE).toHaveLength(6);
  });

  it("banked the darts and esports tournaments as PGA Tour", () => {
    for (const name of [DARTS, ESPORTS]) {
      const t = BEFORE.find((x) => x.name === name);
      expect(t).toBeDefined();
      expect(t!.tour_label).toBe("PGA Tour");
    }
  });

  it("drops exactly two, keeping four", () => {
    expect(AFTER).toHaveLength(4);
    expect(BEFORE.filter((t) => !t.survives_uxp168).map((t) => t.name).sort()).toEqual(
      [ESPORTS, DARTS].sort(),
    );
  });
});

describe("UX-P168 — BEFORE: what the reader was served", () => {
  const markup = text(renderColumn(BEFORE));

  it("printed the darts tournament", () => {
    expect(markup).toContain(DARTS);
  });

  it("printed the esports tournament", () => {
    expect(markup).toContain(ESPORTS);
  });

  it("printed darts players and esports teams as the field", () => {
    for (const intruder of INTRUDERS) {
      expect(markup).toContain(intruder);
    }
  });

  it("badged both of them PGA Tour", () => {
    // The badge and the name are in one card, so count the badge occurrences
    // against the six cards rather than asserting a bare substring.
    const pgaBadges = markup.match(/⛳ PGA Tour/g) ?? [];
    expect(pgaBadges.length).toBe(5);
  });
});

describe("UX-P168 — AFTER: what the reader is served now", () => {
  const markup = text(renderColumn(AFTER));

  it("does not print the darts tournament", () => {
    expect(markup).not.toContain(DARTS);
  });

  it("does not print the esports tournament", () => {
    expect(markup).not.toContain(ESPORTS);
  });

  it("prints no darts player and no esports team", () => {
    for (const intruder of INTRUDERS) {
      expect(markup).not.toContain(intruder);
    }
  });

  it("still prints the real tournaments — the page was not emptied", () => {
    // Vacuity companion for every `not.toContain` above.
    expect(markup).toContain("Tour Championship");
    expect(markup).toContain("Husqvarna British Masters");
    expect(markup).toContain("Scottie Scheffler");
  });

  it("still prints the DP World Tour badge it had earned", () => {
    expect(markup).toContain("DP World Tour");
  });

  it("does not print the word Darts anywhere", () => {
    expect(markup).not.toMatch(/\bDarts\b/);
  });
});

describe("UX-P168 — artifact", () => {
  it("writes the BEFORE/AFTER page when UX_CAPTURE_DIR is set", () => {
    const dir = process.env.UX_CAPTURE_DIR;
    if (!dir) {
      expect(BEFORE.length).toBeGreaterThan(AFTER.length);
      return;
    }
    fs.mkdirSync(dir, { recursive: true });
    const page = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>UX-P168 — the golf page stops serving a darts tournament</title>
<style>
 body{font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f6f7f8;color:#111;margin:0;padding:28px}
 h1{font-size:19px;margin:0 0 4px} p.sub{color:#555;margin:0 0 22px;max-width:70ch}
 .cols{display:grid;grid-template-columns:1fr 1fr;gap:22px;align-items:start}
 h2{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:#666;margin:0 0 10px}
 .col{background:#fff;border:1px solid #e3e5e8;border-radius:10px;padding:14px}
 .bad{border-color:#e5b4b4;background:#fff8f8}
 .note{font-size:12px;color:#777;margin-top:18px;max-width:100ch}
 .stack > *{margin-bottom:10px}
</style></head><body>
<h1>UX-P168 — the golf page stops serving a darts tournament and an esports tournament</h1>
<p class="sub">Every card below is the shipped <code>TournamentCard</code>, fed the verbatim
<code>GET /api/golf</code> payload captured 2026-08-29. Only the input differs between columns:
the fix is in the backend and changes which tournaments are served.</p>
<div class="cols">
  <div class="col bad"><h2>Before — 6 tournaments, 2 of them not golf</h2><div class="stack">${renderColumn(BEFORE)}</div></div>
  <div class="col"><h2>After — 4 tournaments</h2><div class="stack">${renderColumn(AFTER)}</div></div>
</div>
<p class="note"><strong>Read the badges.</strong> In the BEFORE column
&ldquo;New Zealand Darts Masters&rdquo; (Simon Whitlock, Gerwyn Price, James Wade) and
&ldquo;Asia Masters 2026&rdquo; (Dplus Challengers, T1 Esports Academy) both read
&ldquo;⛳ PGA Tour&rdquo;. Neither is golf, and nothing on the card told the reader so.
Both left on two gates: <code>darts</code> joined the #1625 membership authority, and the
authority's outcome-side check — specified since #1625, never run on the open-tournament
path — now sees the esports in the field of a market whose title names no sport at all.
Every real tournament kept every one of its markets (13/13, 16/16, 1/1, 1/1).</p>
</body></html>`;
    const out = path.join(dir, "ux-p168-golf-foreign-tournaments.html");
    fs.writeFileSync(out, page);
    expect(fs.existsSync(out)).toBe(true);
  });
});
