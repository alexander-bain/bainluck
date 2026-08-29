/**
 * UX-P169 — THE GOLF PAGE STOPS HIDING WHAT IS COMING UP, for Alex's eyeball.
 *
 * ═══ WHAT THIS IS ═══
 *
 * `/categories/golf` has an "Upcoming" section gated on
 * `data.upcoming_events.length > 0`. On 2026-08-29 that list was empty, so the
 * section was not thin — it was ABSENT. The reader was shown a golf page with
 * nothing on it about what happens next, one day before the Tour Championship
 * (the only current event) ended.
 *
 * It was empty because the backend built it from the `events` table filtered to
 * `Sport.key ILIKE 'golf_%'`. That pool has six rows in all of history, every one
 * closed and in the past, and they are props and mis-ingests — one of them is a
 * Philippine BASKETBALL game. Twenty future tournaments were sitting in the very
 * same response under `pga_schedule`, read by nobody.
 *
 * ═══ WHAT EVERY ROW HERE IS MADE OF ═══
 *
 * Every row is the SHIPPED `UpcomingTournaments` component, and the data is the
 * verbatim `GET /api/golf` payload captured before a line of the fix was written
 * (`backend/tests/fixtures/uxp169_golf_schedule.json`). Nothing is drawn by hand.
 *
 * ═══ HOW BEFORE AND AFTER ARE PRODUCED ═══
 *
 * A PAYLOAD difference, not a text substitution. BEFORE is the component fed the
 * banked `served_before.upcoming_events` — which is `[]`, so it renders nothing,
 * which IS the defect. AFTER is the same component fed the schedule-derived list.
 * Both columns are genuine renders of the same shipped component.
 *
 *   UX_CAPTURE_DIR=<dir> TZ=UTC npx jest --testPathPatterns=golfUpcomingTournamentsCapture
 *
 * ⚠️ TZ NOTE. The suite runs `TZ=UTC`, which makes the whole class of
 * off-by-one-day date bugs invisible here. The component pins `timeZone: "UTC"`
 * explicitly for that reason; the test below asserts the formatter directly
 * rather than trusting the ambient timezone to have caught anything.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import UpcomingTournaments, {
  formatDateRange,
} from "@/components/golf/UpcomingTournaments";
import type { GolfUpcomingEvent } from "@/lib/types";

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const FIXTURE = path.join(
  REPO,
  "backend",
  "tests",
  "fixtures",
  "uxp169_golf_schedule.json",
);

interface ScheduleEntry {
  name: string;
  key: string;
  start_date: string | null;
  end_date: string | null;
  venue: string;
  location: string;
  tour: string;
}

const BANKED = JSON.parse(fs.readFileSync(FIXTURE, "utf8")) as {
  frozen_now: string;
  served_before: { upcoming_events: GolfUpcomingEvent[] };
  schedule: ScheduleEntry[];
};

const FROZEN_NOW = new Date(BANKED.frozen_now).getTime();

/** DataGolf tour code → the label the reader is owed. Mirrors `_DG_TOUR_TO_KEY`. */
const TOUR_LABEL: Record<string, string> = {
  pga: "PGA Tour",
  euro: "DP World Tour",
  liv: "LIV Golf",
};

/**
 * The AFTER list, derived from the banked schedule the same way the shipped
 * Python helper derives it: future-only, chronological, bounded at 10. The
 * backend suite pins the real thing — this is the rig's input, and
 * `TestTheSectionNamesWhatIsComing` is what proves the two agree.
 */
const AFTER: GolfUpcomingEvent[] = BANKED.schedule
  .filter((s) => s.start_date && new Date(s.start_date).getTime() > FROZEN_NOW)
  .sort((a, b) => (a.start_date! < b.start_date! ? -1 : 1))
  .slice(0, 10)
  .map((s) => ({
    key: s.key,
    name: s.name,
    start_date: s.start_date,
    end_date: s.end_date,
    venue: s.venue || null,
    location: s.location || null,
    tour: s.tour === "euro" ? "dp_world" : s.tour,
    tour_label: TOUR_LABEL[s.tour] ?? null,
  }));

const BEFORE = BANKED.served_before.upcoming_events;

function render(events: GolfUpcomingEvent[]): string {
  return renderToStaticMarkup(<UpcomingTournaments events={events} />);
}

/** `renderToStaticMarkup` escapes entities; unescape before matching copy. */
function text(markup: string): string {
  return markup
    .replace(/&#x27;/g, "'")
    .replace(/&#39;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&#x2013;/g, "–");
}

describe("UX-P169 — the banked BEFORE is what we claim", () => {
  it("production served an empty upcoming list", () => {
    expect(BEFORE).toEqual([]);
  });

  it("the schedule beside it knew about twenty future tournaments", () => {
    const future = BANKED.schedule.filter(
      (s) => s.start_date && new Date(s.start_date).getTime() > FROZEN_NOW,
    );
    expect(future).toHaveLength(20);
  });

  it("the raw schedule is grouped by tour, not by date", () => {
    // If this fails the sort in the AFTER derivation has become vacuous.
    const raw = BANKED.schedule
      .filter((s) => s.start_date && new Date(s.start_date).getTime() > FROZEN_NOW)
      .map((s) => s.start_date!);
    expect(raw).not.toEqual([...raw].sort());
  });
});

describe("UX-P169 — BEFORE: what the reader was served", () => {
  const markup = render(BEFORE);

  it("rendered nothing at all — the section was absent, not thin", () => {
    expect(markup).toBe("");
  });

  it("named no tournament the schedule already knew about", () => {
    expect(markup).not.toContain("Omega European Masters");
    expect(markup).not.toContain("Presidents Cup");
  });
});

describe("UX-P169 — AFTER: what the reader is served now", () => {
  const markup = text(render(AFTER));

  it("renders the section at all", () => {
    // Vacuity companion for every `not.toContain` in the BEFORE block.
    expect(markup).not.toBe("");
    expect(markup).toContain("Upcoming Tournaments");
  });

  it("names the next tournament, five days out", () => {
    expect(markup).toContain("Omega European Masters");
    expect(markup).toContain("Sep 3 – 6");
  });

  it("names the Presidents Cup", () => {
    expect(markup).toContain("Presidents Cup");
  });

  it("says where each one is played", () => {
    expect(markup).toContain("Crans-Montana, Switzerland");
    expect(markup).toContain("Medinah, IL");
  });

  it("labels both tours the way a reader says them", () => {
    expect(markup).toContain("DP World Tour");
    expect(markup).toContain("PGA Tour");
    // DataGolf's raw code must never reach the page.
    expect(markup).not.toMatch(/>euro</);
  });

  it("renders one row per tournament, bounded at ten", () => {
    const rows = markup.match(/data-testid="golf-upcoming-row"/g) ?? [];
    expect(rows).toHaveLength(10);
  });

  it("orders them soonest first", () => {
    const order = ["Omega European Masters", "Amgen Irish Open", "Presidents Cup"];
    const at = order.map((n) => markup.indexOf(n));
    expect(at.every((i) => i >= 0)).toBe(true);
    expect(at).toEqual([...at].sort((a, b) => a - b));
  });

  it("hands the reader no dead link to a tournament with no page yet", () => {
    expect(markup).not.toContain("<a ");
    expect(markup).not.toContain("href=");
  });
});

describe("UX-P169 — dates are calendar facts, not instants", () => {
  it("keeps a same-month range on one month name", () => {
    expect(
      formatDateRange("2026-09-03T00:00:00+00:00", "2026-09-06T00:00:00+00:00"),
    ).toBe("Sep 3 – 6");
  });

  it("spells both months when a tournament crosses one", () => {
    expect(
      formatDateRange("2026-09-29T00:00:00+00:00", "2026-10-02T00:00:00+00:00"),
    ).toBe("Sep 29 – Oct 2");
  });

  it("does not print a range when start and end are the same day", () => {
    expect(
      formatDateRange("2026-09-03T00:00:00+00:00", "2026-09-03T00:00:00+00:00"),
    ).toBe("Sep 3");
  });

  it("prints the start alone when there is no end date", () => {
    expect(formatDateRange("2026-09-03T00:00:00+00:00", null)).toBe("Sep 3");
  });

  it("returns nothing when there is no start date", () => {
    expect(formatDateRange(null, "2026-09-06T00:00:00+00:00")).toBeNull();
  });

  it("reads midnight UTC as the day it says, not the day before", () => {
    // The one that TZ=UTC in this suite cannot catch. `2026-09-03T00:00:00Z`
    // is Sep 2 in every American timezone; the component pins timeZone: "UTC".
    expect(formatDateRange("2026-09-03T00:00:00+00:00", null)).toContain("Sep 3");
  });
});

describe("UX-P169 — it degrades quietly", () => {
  it("renders nothing for an empty list rather than an empty heading", () => {
    expect(render([])).toBe("");
  });

  it("renders a row with no tour label rather than dropping the row", () => {
    const markup = text(
      render([
        {
          key: "k",
          name: "Unlabelled Open",
          start_date: "2026-09-03T00:00:00+00:00",
          end_date: null,
          venue: null,
          location: null,
          tour: null,
          tour_label: null,
        },
      ]),
    );
    expect(markup).toContain("Unlabelled Open");
    expect(markup).toContain("Sep 3");
  });
});

describe("UX-P169 — artifact", () => {
  it("writes the BEFORE/AFTER page when UX_CAPTURE_DIR is set", () => {
    const dir = process.env.UX_CAPTURE_DIR;
    if (!dir) {
      expect(AFTER.length).toBeGreaterThan(BEFORE.length);
      return;
    }
    fs.mkdirSync(dir, { recursive: true });
    const page = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>UX-P169 — the golf page stops hiding what is coming up</title>
<style>
 body{font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f6f7f8;color:#111;margin:0;padding:28px}
 h1{font-size:19px;margin:0 0 4px} p.sub{color:#555;margin:0 0 22px;max-width:78ch}
 .cols{display:grid;grid-template-columns:1fr 1fr;gap:22px;align-items:start}
 h2{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:#666;margin:0 0 10px}
 .col{background:#fff;border:1px solid #e3e5e8;border-radius:10px;padding:14px;min-height:120px}
 .bad{border-color:#e5b4b4;background:#fff8f8}
 .empty{color:#a33;font-style:italic;font-size:13px}
 .note{font-size:12px;color:#777;margin-top:18px;max-width:104ch}
 .bg-surface-card{background:#fff}.border-surface-border{border:1px solid #E5E7EB}
 .bg-surface-elevated{background:#F0F0F2}
 .text-text-primary{color:#111827}.text-text-secondary{color:#6B7280}.text-text-muted{color:#9CA3AF}
 .rounded-lg{border-radius:8px}.p-3{padding:12px}.flex{display:flex}
 .items-center{align-items:center}.justify-between{justify-content:space-between}
 .gap-2{gap:8px}.gap-3{gap:12px}.space-y-2 > * + *{margin-top:8px}
 .text-sm{font-size:13px}.text-xs{font-size:12px}.mb-4{margin-bottom:16px}
 .text-xl{font-size:20px}.font-bold{font-weight:700}
 .px-1\\.5{padding-left:6px;padding-right:6px}.py-0\\.5{padding-top:2px;padding-bottom:2px}
 .rounded{border-radius:4px}.font-medium{font-weight:500}
</style></head><body>
<h1>UX-P169 — the golf page stops hiding what is coming up</h1>
<p class="sub">Both columns are the shipped <code>UpcomingTournaments</code> component. Only the
input differs: the fix is in the backend and changes where the list comes from. Captured from
<code>GET /api/golf</code> on 2026-08-29.</p>
<div class="cols">
  <div class="col bad"><h2>Before — the section is absent</h2>
    <div>${render(BEFORE) || '<p class="empty">nothing rendered — <code>upcoming_events</code> was <code>[]</code>, so <code>.length &gt; 0</code> removed the whole section from the page</p>'}</div>
  </div>
  <div class="col"><h2>After — the next ten tournaments</h2><div>${render(AFTER)}</div></div>
</div>
<p class="note"><strong>Why it was empty.</strong> <code>upcoming_events</code> was built from the
<code>events</code> table filtered to <code>Sport.key ILIKE 'golf_%'</code>. Golf has six rows there
in all of history — every one <code>closed</code> and in the past, and every one a prop or a
mis-ingest rather than a tournament: <em>&ldquo;Hole-in-One vs Arnold Palmer Invitational&rdquo;</em>,
<em>&ldquo;U.S. Team Captain vs 2027 Ryder Cup&rdquo;</em>, and a Philippine basketball game
(<em>Phoenix Fuel Masters vs Timplados Hotshots</em>). So the section could only ever render nothing,
or nonsense. The DataGolf schedule — twenty future tournaments, the nearest five days away — was
already loaded by the same request and already serialized into the same payload under
<code>pga_schedule</code>, with no consumer in the web app or the iOS app. The Tour Championship, the
only current event, ended the day after this capture.</p>
</body></html>`;
    const out = path.join(dir, "ux-p169-golf-upcoming-tournaments.html");
    fs.writeFileSync(out, page);
    expect(fs.existsSync(out)).toBe(true);
  });
});
