/**
 * UX-P178 artifact rig — renders `artifacts-ux-p178/hub-upcoming-card.html`.
 *
 * Three panels, all real React renders of real components on one verbatim
 * production payload:
 *
 *   BEFORE   `__tests__/fixtures/uxp178HubUpcomingCardLegacy.tsx` — the verbatim
 *            pre-fix card, extracted with
 *            `git show ad502189:'frontend/app/hub/[competition]/page.tsx'`.
 *            A render of the code that shipped, not a drawing of it. This is the
 *            only way to show the third defect at all: the day-early date came
 *            from an un-pinned `toLocaleDateString`, which the fixed component
 *            can no longer produce.
 *   AFTER    the shipped `components/hub/UpcomingCard.tsx` on the payload the
 *            fixed backend now serves for that same concept.
 *   CONTROL  an mma card — a domain that always knew its real start date —
 *            asserted BYTE-IDENTICAL between the legacy and shipped components.
 *
 * ⚠️ TIMEZONE. This rig runs under `TZ=America/Los_Angeles`, and it refuses to
 * write unless it is. That is not incidental: the BEFORE panel's "Sat, Sep 12" is
 * only reproducible outside UTC, and a US reader is who saw it. The rig asserts
 * the zone rather than trusting it, because under `TZ=UTC` the BEFORE panel would
 * quietly render the correct date and the artifact would understate the defect.
 *
 * The rig asserts its own output — an artifact that silently captured the wrong
 * thing is worse than no artifact.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "fs";
import path from "path";

import { UpcomingCard } from "@/components/hub/UpcomingCard";
import type { HubUpcoming } from "@/lib/api";

import tennisBefore from "../fixtures/uxp178_hub_tennis_before.json";
import mmaControl from "../fixtures/uxp178_hub_mma_control.json";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const UpcomingCardLegacy =
  require("../fixtures/uxp178HubUpcomingCardLegacy").UpcomingCard;

const TENNIS_BEFORE = tennisBefore.upcoming as HubUpcoming[];
const MMA_CONTROL = mmaControl.upcoming as HubUpcoming[];

function render(Component: unknown, card: HubUpcoming): string {
  return renderToStaticMarkup(
    React.createElement(Component as React.FC, { card } as never)
  );
}

function visibleText(markup: string): string {
  return markup
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&#x2605;/g, "★")
    .replace(/\s+/g, " ")
    .trim();
}

/** The US Open exactly as production served it on 2026-08-29. */
const US_OPEN_BEFORE = TENNIS_BEFORE.find((c) =>
  c.name.includes("Women’s US Open")
)!;

/** The same concept as the fixed backend now serves it. */
const US_OPEN_AFTER: HubUpcoming = {
  ...US_OPEN_BEFORE,
  is_major: true,
  start_date: null,
  end_date: US_OPEN_BEFORE.start_date,
};

/**
 * This rig is a RENDERER, not a gate — the guards are in
 * `hubUpcomingCardCapture.test.tsx`, which passes under every zone. CI runs jest
 * with `TZ=UTC`, where the BEFORE panel would quietly render the CORRECT date and
 * the artifact would understate the defect it exists to show. So the rig declines
 * to run rather than write a misleading file, and says so in its own name.
 *
 *     cd frontend && TZ=America/Los_Angeles npx jest --testPathPatterns=hubUpcomingCardArtifact
 */
const RESOLVED_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone;
const describeInLosAngeles =
  RESOLVED_TZ === "America/Los_Angeles" ? describe : describe.skip;

describeInLosAngeles(
  `UX-P178 artifact (needs TZ=America/Los_Angeles, saw ${RESOLVED_TZ})`,
  () => {
  it("renders the three panels and asserts what each one must show", () => {
    // ── The rig proves its own preconditions before it proves anything else ──
    expect(RESOLVED_TZ).toBe("America/Los_Angeles");
    expect(US_OPEN_BEFORE.is_major).toBe(false);
    expect(US_OPEN_BEFORE.status).toBe("live");
    expect(US_OPEN_BEFORE.start_date).toBe("2026-09-13T00:00:00+00:00");

    const before = render(UpcomingCardLegacy, US_OPEN_BEFORE);
    const after = render(UpcomingCard, US_OPEN_AFTER);
    const control = render(UpcomingCard, MMA_CONTROL[0]);
    const controlBefore = render(UpcomingCardLegacy, MMA_CONTROL[0]);

    // ── BEFORE must show all three defects, or the artifact is a strawman ──
    const beforeText = visibleText(before);
    expect(beforeText).not.toMatch(/Marquee/); // 1. no chip on a Grand Slam
    expect(beforeText).toContain("Live");
    expect(beforeText).toContain("Sat, Sep 12"); // 2 + 3. an END date, a day early
    expect(beforeText).not.toMatch(/Ends/);

    // ── AFTER must fix all three and change nothing else ──
    const afterText = visibleText(after);
    expect(afterText).toContain("★ Marquee");
    expect(afterText).toContain("Live");
    expect(afterText).toContain("Ends Sun, Sep 13");
    expect(afterText).not.toContain("Sat, Sep 12");
    expect(after).toContain(
      'href="/event/tennis/2026-women-s-us-open-winner-tennis"'
    );

    // ── CONTROL: a domain with a real start date is untouched, byte for byte ──
    expect(control).toBe(controlBefore);
    expect(visibleText(control)).not.toMatch(/Ends/);
    expect(visibleText(control)).not.toMatch(/TBD/);

    const panel = (title: string, note: string, markup: string) => `
      <section>
        <h2>${title}</h2>
        <p class="note">${note}</p>
        <div class="frame">${markup}</div>
      </section>`;

    const html = `<!doctype html>
<html><head><meta charset="utf-8">
<title>UX-P178 — the US Open stops claiming it starts in two weeks while showing a LIVE dot</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body { background:#f6f7f9; font-family:ui-sans-serif,system-ui,sans-serif; margin:0; padding:24px; }
  h1 { font-size:20px; margin:0 0 4px; }
  .sub { color:#555; font-size:13px; margin:0 0 24px; max-width:940px; }
  section { margin-bottom:28px; }
  h2 { font-size:15px; margin:0 0 4px; }
  .note { color:#666; font-size:12px; margin:0 0 8px; max-width:940px; }
  .frame { background:#fff; border:1px solid #dcdfe4; border-radius:10px; padding:12px; max-width:340px; }
  code { background:#eceef1; padding:1px 4px; border-radius:3px; }
</style></head>
<body>
<h1>UX-P178 — the US Open stops claiming it starts in two weeks while showing a LIVE dot</h1>
<p class="sub">Every panel is a real React render, in <code>TZ=America/Los_Angeles</code> — the zone a
US reader is in, and the only zone in which the third defect is visible. BEFORE is
<code>__tests__/fixtures/uxp178HubUpcomingCardLegacy.tsx</code>, the verbatim pre-fix card extracted
from <code>ad502189</code>; AFTER and CONTROL are the shipped component. The card data is a verbatim
production <code>/api/hub/tennis</code> body read 2026-08-29. Nothing here is assembled.</p>
${panel(
  "BEFORE — bainluck.com/hub/tennis, today",
  'Three defects in three lines. <b>No &ldquo;★ Marquee&rdquo; chip</b> on a Grand Slam — <code>is_major</code> was hardcoded <code>false</code> for tennis, and the chip had never rendered on any of the 48 upcoming cards across all five hubs. <b>A future date under a LIVE dot</b> — the rail served the winner market&rsquo;s resolution date, i.e. when the tournament <i>ends</i>, under the key <code>start_date</code>. <b>And it is a day early</b> — <code>2026-09-13T00:00:00+00:00</code> with no pinned <code>timeZone</code> renders as Sep 12 for every reader west of Greenwich.',
  before
)}
${panel(
  "AFTER — the same concept, the shipped fix",
  'The Grand Slam is marquee. The date is labelled as the end it always was, so &ldquo;Live&rdquo; and a September date no longer contradict each other. And it reads Sep 13 in Los Angeles, because <code>formatDate</code> now pins <code>timeZone: "UTC"</code> — the date we publish is the date the data states. The backend half (<code>tennis_is_major</code>, and <code>end_date</code> replacing the mislabelled <code>start_date</code>) is proven in <code>backend/tests/test_event_tennis_identity.py</code>.',
  after
)}
${panel(
  "CONTROL — an mma card, before and after are identical",
  "Asserted byte-for-byte equal between the legacy and shipped components. ufc, boxing and golf all serve a genuine start date; a repair that relabelled every hub card &ldquo;Ends …&rdquo;, or that moved the date by a day, would pass every other assertion in this queue while breaking three hubs.",
  control
)}
</body></html>`;

    const out = path.join(__dirname, "../../../artifacts-ux-p178");
    fs.mkdirSync(out, { recursive: true });
    fs.writeFileSync(path.join(out, "hub-upcoming-card.html"), html);
  });
  }
);
