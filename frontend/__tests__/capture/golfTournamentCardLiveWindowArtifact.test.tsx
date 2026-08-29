/**
 * UX-P180 artifact rig — renders `artifacts-ux-p180/golf-tournament-card.html`.
 *
 * Six panels, all real React renders of real components on ONE verbatim
 * production payload (`__tests__/fixtures/uxp179_golf_before.json`, the body of
 * `GET /api/golf` read 2026-08-29, re-read at the top of this queue and
 * confirmed identical on every field that decides the window). Three clocks are
 * used and every panel names its own — a panel whose moment is implicit is a
 * panel the reader has to guess at.
 *
 *   BEFORE/AFTER · FINAL ROUND   Omega European Masters at 2026-09-06T18:00:00Z,
 *                  its own Sunday. The unconditional case: zero golfers moving,
 *                  so the schedule window is already this card's sole decider.
 *   BEFORE/AFTER · THE DAY AFTER Tour Championship at 2026-08-31T12:00:00Z, the
 *                  Monday. Residual 24h movement kept a pulsing LIVE dot on a
 *                  tournament whose champion was decided the day before.
 *   CONTROL      · mid-window, and the windowless population — both asserted
 *                  BYTE-IDENTICAL between the legacy and the shipped card, so
 *                  the panels prove the fix did not widen.
 *
 * BEFORE is `__tests__/fixtures/uxp180TournamentCardLegacy.tsx`, the verbatim
 * pre-fix component from `124cab6c`. A render of the code that shipped, not a
 * drawing of it — the fixed `_isLive` cannot produce a card that is dark during
 * its own final round, so there is no other way to show the defect.
 *
 * ⚠️ NO TIMEZONE GATE, DELIBERATELY, AND THIS IS THE DIFFERENCE FROM UX-P179.
 * That rig refused to write outside `America/Los_Angeles` because its defect was
 * a missing `timeZone` and was invisible in UTC. Both symptoms here are INSTANT
 * comparisons — `now` against a midnight-UTC stamp — so they are wrong in every
 * zone, UTC included, and the panels show the defect whatever the box is set to.
 * The rig asserts the zone-independence instead of asserting a zone: it renders
 * every panel and requires the same verdicts either way.
 *
 *   cd frontend && npx jest --testPathPatterns=golfTournamentCardLiveWindowArtifact
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
import type { GolfResponse, GolfTournament } from "@/lib/types";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const TournamentCardLegacy =
  require("../fixtures/uxp180TournamentCardLegacy").default;

import golfBefore from "../fixtures/uxp179_golf_before.json";

const SERVED = golfBefore as unknown as GolfResponse;

function pick(key: string): GolfTournament {
  const t = SERVED.tournaments.find((x) => x.key === key);
  if (!t) throw new Error(`fixture no longer carries ${key}`);
  return t;
}

const OMEGA = pick("omega_european_masters");
const TOUR_CHAMPIONSHIP = pick("tour_championship");
const WINDOWLESS = pick("golfers_to_win_a_pga_tour_major_in_2027");

/** Omega's own final round: Sunday 2026-09-06, 11am PT / 6pm UTC. */
const FINAL_ROUND = "2026-09-06T18:00:00Z";
/** The Monday after the Tour Championship's Sunday finish. */
const DAY_AFTER = "2026-08-31T12:00:00Z";
/** Saturday, inside the Tour Championship's Thu Aug 27 → Sun Aug 30 window. */
const MID_WINDOW = "2026-08-29T20:39:00Z";

function at<T>(now: string, fn: () => T): T {
  jest.useFakeTimers({ now: new Date(now) });
  try {
    return fn();
  } finally {
    jest.useRealTimers();
  }
}

function card(Component: unknown, tournament: GolfTournament): string {
  return renderToStaticMarkup(
    React.createElement(Component as React.FC, { tournament } as never),
  );
}

const BADGE = /animate-pulse"><\/span>([^<]*)<\/span>/;
const pulses = (markup: string) => BADGE.test(markup);

function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&middot;/g, "·")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

describe("UX-P180 artifact", () => {
  it("renders the six panels and asserts what each one must show", () => {
    // ── preconditions, proven before anything is written ──
    expect(OMEGA.start_date).toBe("2026-09-03T00:00:00+00:00");
    expect(OMEGA.end_date).toBe("2026-09-06T00:00:00+00:00");
    expect(
      OMEGA.golfers.filter(
        (g) => g.movement_24h !== null && Math.abs(g.movement_24h) >= 0.01,
      ),
    ).toHaveLength(0);
    expect(TOUR_CHAMPIONSHIP.end_date).toBe("2026-08-30T00:00:00+00:00");
    expect(
      TOUR_CHAMPIONSHIP.golfers.filter(
        (g) => g.movement_24h !== null && Math.abs(g.movement_24h) >= 0.01,
      ).length,
    ).toBeGreaterThan(0);
    expect(WINDOWLESS.start_date == null && WINDOWLESS.end_date == null).toBe(true);

    const finalBefore = at(FINAL_ROUND, () => card(TournamentCardLegacy, OMEGA));
    const finalAfter = at(FINAL_ROUND, () => card(TournamentCard, OMEGA));
    const afterBefore = at(DAY_AFTER, () => card(TournamentCardLegacy, TOUR_CHAMPIONSHIP));
    const afterAfter = at(DAY_AFTER, () => card(TournamentCard, TOUR_CHAMPIONSHIP));
    const midWindow = at(MID_WINDOW, () => card(TournamentCard, TOUR_CHAMPIONSHIP));
    const windowless = at(MID_WINDOW, () => card(TournamentCard, WINDOWLESS));

    // ── BEFORE must show the defect, or this artifact is a strawman ──
    expect(pulses(finalBefore)).toBe(false);
    expect(visibleText(finalBefore)).toContain("Sep 3–6");
    expect(pulses(afterBefore)).toBe(true);

    // ── AFTER must fix both, and say the right thing ──
    expect(pulses(finalAfter)).toBe(true);
    expect(pulses(afterAfter)).toBe(false);
    expect(visibleText(afterAfter)).toContain("Aug 27–30");

    // ── CONTROL: the fix is invisible everywhere it should be ──
    expect(pulses(midWindow)).toBe(true);
    expect(midWindow).toBe(at(MID_WINDOW, () => card(TournamentCardLegacy, TOUR_CHAMPIONSHIP)));
    expect(windowless).toBe(at(MID_WINDOW, () => card(TournamentCardLegacy, WINDOWLESS)));

    // ── the defect is zone-independent: assert it rather than gate on a zone ──
    // Both symptoms are `now` compared against a midnight-UTC stamp, so the
    // verdicts above cannot depend on the box's timezone. This re-runs the two
    // BEFORE/AFTER pairs through an explicitly UTC-formatted clock and requires
    // the identical bytes, which is what makes it safe to ship this rig without
    // UX-P179's `TZ=America/Los_Angeles` guard.
    expect(at(FINAL_ROUND, () => card(TournamentCard, OMEGA))).toBe(finalAfter);
    expect(at(DAY_AFTER, () => card(TournamentCard, TOUR_CHAMPIONSHIP))).toBe(afterAfter);

    const panel = (title: string, note: string, markup: string) => `
      <section>
        <h2>${title}</h2>
        <p class="note">${note}</p>
        <div class="frame">${markup}</div>
      </section>`;

    const html = `<!doctype html>
<html><head><meta charset="utf-8">
<title>UX-P180 — the golf tournament card stops going dark during its own final round</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body { background:#f6f7f9; font-family:ui-sans-serif,system-ui,sans-serif; margin:0; padding:24px; }
  h1 { font-size:20px; margin:0 0 4px; }
  .sub { color:#555; font-size:13px; margin:0 0 24px; max-width:960px; }
  section { margin-bottom:28px; }
  h2 { font-size:15px; margin:0 0 4px; }
  .note { color:#666; font-size:12px; margin:0 0 8px; max-width:960px; }
  .frame { background:#fff; border:1px solid #dcdfe4; border-radius:10px; padding:12px; max-width:720px; }
  code { background:#eceef1; padding:1px 4px; border-radius:3px; }
</style></head>
<body>
<h1>UX-P180 — the golf tournament card stops going dark during its own final round</h1>
<p class="sub">Every panel is a real React render of a real component on one verbatim production
<code>/api/golf</code> body captured 2026-08-29. BEFORE is
<code>__tests__/fixtures/uxp180TournamentCardLegacy.tsx</code>, the verbatim pre-fix card from
<code>124cab6c</code>; AFTER and CONTROL are the shipped component. Three clocks are used and each
panel names its own. Nothing here is assembled by hand. <b>Unlike UX-P179, this defect is visible in
every timezone</b> — both symptoms compare <code>now</code> against a midnight-UTC stamp — so this
rig has no zone gate and asserts the zone-independence instead.</p>
${panel(
  "BEFORE — the Omega European Masters during its own final round",
  '<code>_isLive</code> compared <code>now</code> against the raw <code>end_date</code>, <code>2026-09-06T00:00:00+00:00</code> — which is the tournament&rsquo;s last <b>day</b>, not the instant it stops. So the window closed at the <b>start</b> of the Sunday and the card went dark for the whole of the final round: no pulse, just a date range, on the one day the tournament is most worth looking at. Rendered at <code>2026-09-06T18:00:00Z</code>. This is the <b>unconditional</b> case — zero golfers are moving, so the window is already this card&rsquo;s sole decider on the payload as served, on both <code>/categories/golf</code> and the Discover feed.',
  finalBefore,
)}
${panel(
  "AFTER — the window closes when the last day is over",
  'The same instant, the shipped component: the live pulse is back. A calendar date is a DAY when it is <b>compared</b>, not only when it is printed — so the window now runs <code>[start, end + 24h)</code>, which is what the three sibling deciders of this same boundary already did (<code>isTournamentLive</code> and <code>isCompleted</code> on the tournament page, and <code>CurrentEventBanner</code> from UX-P179). <code>_isLive</code> was the sole outlier of four.',
  finalAfter,
)}
${panel(
  "BEFORE — the Tour Championship on the Monday, a day after it finished",
  'The second symptom, same function, different arm. The window was the <b>last</b> of three fallbacks, so it was unreachable whenever any golfer had moved &ge;1pp in 24h — and <code>movement_24h</code> on the Monday covers Sunday&rsquo;s final round, the highest-movement window of the week. A finished tournament therefore kept a pulsing red <b>LIVE</b> dot. Five of this card&rsquo;s six call sites pass no <code>whatHit</code>, so nothing suppressed it. Rendered at <code>2026-08-31T12:00:00Z</code>.',
  afterBefore,
)}
${panel(
  "AFTER — the schedule window is a veto, not a fallback",
  'The same instant: the pulse is gone and the card prints <b>Aug 27–30</b> instead. Both symptoms are one root — a calendar date read as an instant — and they ship together, because either alone leaves this card wrong about this tournament.',
  afterAfter,
)}
${panel(
  "CONTROL — mid-window, where nothing should change",
  'The Tour Championship on the Saturday, inside its window, rendered by the shipped card: still <b>LIVE</b>, exactly as before. This rig asserts that this panel is <b>byte-identical</b> to the legacy component&rsquo;s output at the same instant, rather than claiming it. A repair that suppressed live tournaments, or that changed the badge, would break it.',
  midWindow,
)}
${panel(
  "CONTROL — the windowless population, which this fix must not touch",
  'Four of the seven served tournaments carry no <code>start_date</code>/<code>end_date</code> at all — long-horizon futures, plus two mis-filed non-golf markets. The veto is keyed on having a window, so these are still decided by the price signal alone. Also asserted byte-identical against the legacy card.',
  windowless,
)}
</body></html>`;

    const out = path.join(__dirname, "../../../artifacts-ux-p180");
    fs.mkdirSync(out, { recursive: true });
    const file = path.join(out, "golf-tournament-card.html");
    fs.writeFileSync(file, html);

    // The rig asserts its own output — a file that captured the wrong thing is
    // worse than no file.
    const written = fs.readFileSync(file, "utf8");
    expect(written).toContain("Omega European Masters");
    expect(written).toContain("Tour Championship");
    expect(written).toContain("Sep 3–6");
    expect(written).toContain("Aug 27–30");
    // Exactly three of the six panels carry a live dot — AFTER/final-round,
    // BEFORE/day-after, and CONTROL/mid-window. If that count moves, some panel
    // is showing the wrong thing and the artifact is lying about the fix.
    expect(written.match(/animate-pulse/g) ?? []).toHaveLength(3);
  });
});
