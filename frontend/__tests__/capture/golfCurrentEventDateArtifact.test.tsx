/**
 * UX-P179 artifact rig — renders `artifacts-ux-p179/golf-current-event.html`.
 *
 * Six panels, all real React renders of real components on ONE verbatim
 * production payload (`__tests__/fixtures/uxp179_golf_before.json`, the body of
 * `GET /api/golf` read 2026-08-29). Every panel states its own frozen clock,
 * because three different clocks are needed and a panel whose moment is implicit
 * is a panel the reader has to guess at:
 *
 *   BEFORE    `__tests__/fixtures/uxp179GolfCurrentEventBannerLegacy.tsx` — the
 *             verbatim pre-fix banner, `git show b79130bd:` of the route file,
 *             at 2026-08-29T20:39:00Z. A render of the code that shipped, not a
 *             drawing of it. It is the only way to show the defect at all,
 *             because the fixed component cannot produce a day-early date.
 *   AFTER     the shipped `components/golf/CurrentEventBanner.tsx`, same clock.
 *   CONTRA    the `TournamentCard` for the SAME tournament — a component that
 *             already read these values in UTC, and that sat further down the
 *             SAME page saying a different thing than the banner above it.
 *             At 2026-08-25T12:00:00Z; the panel's note says why.
 *   SUNDAY    the second symptom of the same root, at 2026-08-30T12:00:00Z:
 *             BEFORE says "Just Finished" during the final round and drops the
 *             dates; AFTER says "This Week" and keeps them.
 *   CONTROL   an untouched `TournamentCard` for a tournament that is not live,
 *             rendered with nothing adjusted, to show the sibling renderer as
 *             the page actually serves it.
 *
 * ⚠️ TIMEZONE. This rig runs under `TZ=America/Los_Angeles` and refuses to write
 * unless it is. Under `TZ=UTC` the BEFORE panel would render the CORRECT date and
 * the artifact would understate the defect to nothing. The zone is asserted, not
 * trusted. The guards live in `golfCurrentEventDateCapture.test.tsx`, which is
 * green under every zone; this file is a renderer, not a gate.
 *
 *   cd frontend && TZ=America/Los_Angeles npx jest --testPathPatterns=golfCurrentEventDateArtifact
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

import CurrentEventBanner from "@/components/golf/CurrentEventBanner";
import TournamentCard from "@/components/TournamentCard";
import type {
  GolfCurrentEvent,
  GolfResponse,
  GolfTournament,
} from "@/lib/types";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const CurrentEventBannerLegacy =
  require("../fixtures/uxp179GolfCurrentEventBannerLegacy").default;

import golfBefore from "../fixtures/uxp179_golf_before.json";

const SERVED = golfBefore as unknown as GolfResponse;
const CURRENT = SERVED.current_event as GolfCurrentEvent;
const TOUR_CHAMPIONSHIP = SERVED.tournaments.find(
  (t) => t.name === "Tour Championship",
) as GolfTournament;
const NOT_LIVE = SERVED.tournaments.find(
  (t) => t.name === "Omega European Masters",
) as GolfTournament;

/** Saturday afternoon UTC, inside the Thu Aug 27 → Sun Aug 30 window. */
const DURING = new Date("2026-08-29T20:39:00Z");
/**
 * Two days before the Thursday start. `TournamentCard` hides its dates while a
 * tournament is live — by 24h movement OR by the window — so the CONTRA panel,
 * whose whole point is the date it prints, has to be rendered from outside the
 * window. Same two values, a different moment; the panel's note says so.
 */
const PRE = new Date("2026-08-25T12:00:00Z");
/**
 * Midday on the tournament's final round. `end_date` is `2026-08-30T00:00:00Z`,
 * so the pre-fix banner had already retired the tournament — at 00:01Z, i.e.
 * 5:01pm PT on the SATURDAY — and said "Just Finished" for the whole of Sunday.
 */
const SUNDAY = new Date("2026-08-30T12:00:00Z");

function at<T>(now: Date, fn: () => T): T {
  jest.useFakeTimers({ now });
  try {
    return fn();
  } finally {
    jest.useRealTimers();
  }
}

function banner(Component: unknown, event: GolfCurrentEvent): string {
  return renderToStaticMarkup(
    React.createElement(Component as React.FC, {
      event,
      historyData: null,
    } as never),
  );
}

function card(tournament: GolfTournament): string {
  return renderToStaticMarkup(
    React.createElement(TournamentCard, { tournament }),
  );
}

function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&middot;/g, "·")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

/** `TournamentCard` hides its dates while a tournament is live. */
function notLive(t: GolfTournament): GolfTournament {
  return {
    ...t,
    schedule_status: "upcoming",
    golfers: (t.golfers || []).map((g) => ({ ...g, movement_24h: null })),
  };
}

const RESOLVED_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone;
const describeInLosAngeles =
  RESOLVED_TZ === "America/Los_Angeles" ? describe : describe.skip;

describeInLosAngeles(
  `UX-P179 artifact (needs TZ=America/Los_Angeles, saw ${RESOLVED_TZ})`,
  () => {
    it("renders the six panels and asserts what each one must show", () => {
      // ── preconditions, proven before anything is written ──
      expect(RESOLVED_TZ).toBe("America/Los_Angeles");
      expect(CURRENT.name).toBe("Tour Championship");
      expect(CURRENT.start_date).toBe("2026-08-27T00:00:00+00:00");
      expect(CURRENT.end_date).toBe("2026-08-30T00:00:00+00:00");
      expect(TOUR_CHAMPIONSHIP.start_date).toBe(CURRENT.start_date);
      expect(NOT_LIVE.start_date).toBe("2026-09-03T00:00:00+00:00");

      const before = at(DURING, () => banner(CurrentEventBannerLegacy, CURRENT));
      const after = at(DURING, () => banner(CurrentEventBanner, CURRENT));
      const contra = at(PRE, () => card(notLive(TOUR_CHAMPIONSHIP)));
      const control = at(DURING, () => card(NOT_LIVE));
      const sundayBefore = at(SUNDAY, () => banner(CurrentEventBannerLegacy, CURRENT));
      const sundayAfter = at(SUNDAY, () => banner(CurrentEventBanner, CURRENT));

      // ── BEFORE must show the defect, or this artifact is a strawman ──
      const beforeText = visibleText(before);
      expect(beforeText).toContain("Aug 26 – Sat, Aug 29");
      expect(beforeText).not.toContain("Aug 27");
      expect(beforeText).not.toContain("Aug 30");

      // ── AFTER must fix it and change nothing else ──
      const afterText = visibleText(after);
      expect(afterText).toContain("Aug 27 – Sun, Aug 30");
      expect(afterText).not.toContain("Aug 26");
      expect(afterText).not.toContain("Sat, Aug 29");
      expect(afterText).toContain("This Week");
      expect(beforeText).toContain("This Week");
      // Everything that is not the date is untouched between the two panels.
      expect(before.replace("Aug 26 – Sat, Aug 29", "")).toBe(
        after.replace("Aug 27 – Sun, Aug 30", ""),
      );

      // ── CONTRA: the same page already said Aug 27–30, one scroll down ──
      expect(visibleText(contra)).toContain("Aug 27–30");

      // ── CONTROL: an untouched sibling row, nothing adjusted ──
      expect(visibleText(control)).toContain("Sep 3–6");

      // ── SUNDAY: the second symptom of the same root ──
      const sundayBeforeText = visibleText(sundayBefore);
      expect(sundayBeforeText).toContain("Just Finished");
      expect(sundayBeforeText).not.toContain("Aug 30");
      const sundayAfterText = visibleText(sundayAfter);
      expect(sundayAfterText).toContain("This Week");
      expect(sundayAfterText).toContain("Aug 27 – Sun, Aug 30");

      const panel = (title: string, note: string, markup: string) => `
      <section>
        <h2>${title}</h2>
        <p class="note">${note}</p>
        <div class="frame">${markup}</div>
      </section>`;

      const html = `<!doctype html>
<html><head><meta charset="utf-8">
<title>UX-P179 — the golf page stops ending the Tour Championship a day early</title>
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
<h1>UX-P179 — the golf page stops ending the Tour Championship a day early</h1>
<p class="sub">Every panel is a real React render in <code>TZ=America/Los_Angeles</code> — the zone a
US reader is in, and the only zone in which the day-early date is visible at all. Three clocks are
used and each panel names its own; the first two are frozen at <code>2026-08-29T20:39:00Z</code>,
mid-tournament. BEFORE is
<code>__tests__/fixtures/uxp179GolfCurrentEventBannerLegacy.tsx</code>, the verbatim pre-fix banner
sliced out of <code>b79130bd</code>; AFTER, CONTRA and CONTROL are shipped components. All four read
one verbatim production <code>/api/golf</code> body captured 2026-08-29. Nothing here is assembled by
hand. The Tour Championship 2026 runs <b>Thu Aug 27 – Sun Aug 30</b>.</p>
${panel(
  "BEFORE — bainluck.com/categories/golf, today, from Los Angeles",
  'The banner is the first block on the page. <code>/api/golf</code> stamps every schedule date at midnight UTC — <b>94 of 94</b> <code>pga_schedule</code> rows and <b>3 of 3</b> tournament windows — and this banner called <code>toLocaleDateString</code> four times with no <code>timeZone</code>. So both ends move back a day: it names the Wednesday as the start and tells the reader the tournament <b>ends today, on the Saturday</b>. It ends Sunday.',
  before,
)}
${panel(
  "AFTER — the shipped fix",
  'Each of the four formats now pins <code>timeZone: "UTC"</code>, so the date the page publishes is the date the data states, in every zone. Nothing else about the banner changes — the two panels are byte-identical outside the date string, and this file asserts that rather than claiming it.',
  after,
)}
${panel(
  "CONTRA — the same tournament, further down the same page, all along",
  '<code>components/TournamentCard.tsx</code> reads the same two values with <code>getUTCMonth()</code>/<code>getUTCDate()</code> and has always printed <b>Aug 27–30</b>. So did the tournament page one click on (<code>timeZone: "UTC"</code>, three places) and the schedule rail (<code>utcPart</code>). The banner was the sole outlier of four, and the page contradicted itself. <i>Fixture honesty: this is the verbatim production row, rendered at <code>2026-08-25T12:00:00Z</code> with <code>schedule_status</code> "upcoming" and 24h movement cleared. <code>TournamentCard</code> hides its dates while a tournament is live — by movement or by the window — so a panel about the date it prints cannot be rendered from inside the window. Nothing else is altered, and the two values are the same two values.</i>',
  contra,
)}
${panel(
  "BEFORE — the same banner on Sunday, the final round",
  'The second symptom of the same root, and the louder one. <code>end_date</code> is <code>2026-08-30T00:00:00+00:00</code> — the tournament&rsquo;s last <b>day</b>. Comparing <code>now</code> against that raw instant retired it at <b>00:01Z, i.e. 5:01pm PT on the Saturday</b>, so the banner read <b>&ldquo;🏌️ Just Finished&rdquo;</b> for the whole of Sunday&rsquo;s final round — and dropped the dates entirely while it did. Rendered here at <code>2026-08-30T12:00:00Z</code>.',
  sundayBefore,
)}
${panel(
  "AFTER — the window closes when the last day is over",
  'The same instant, the shipped component: <b>This Week</b>, dates intact. A calendar date is a DAY when it is compared, not only when it is printed — so the window now ends at <code>end + 24h</code>. Both symptoms are one root and they ship together, because either one alone leaves the banner wrong about this tournament.',
  sundayAfter,
)}
${panel(
  "CONTROL — an untouched sibling row",
  'The Omega European Masters, rendered exactly as <code>/api/golf</code> serves it with nothing adjusted: <b>Sep 3–6</b>, correct in Los Angeles because this renderer never asked the reader&rsquo;s clock. A repair that moved dates by a day, or that changed the shape of these labels, would break this panel.',
  control,
)}
</body></html>`;

      const out = path.join(__dirname, "../../../artifacts-ux-p179");
      fs.mkdirSync(out, { recursive: true });
      const file = path.join(out, "golf-current-event.html");
      fs.writeFileSync(file, html);

      // The rig asserts its own output — a file that captured the wrong thing
      // is worse than no file.
      const written = fs.readFileSync(file, "utf8");
      expect(written).toContain("Aug 26 – Sat, Aug 29");
      expect(written).toContain("Just Finished");
      expect(written).toContain("Aug 27 – Sun, Aug 30");
      expect(written).toContain("Aug 27–30");
      expect(written).toContain("Sep 3–6");
    });
  },
);
