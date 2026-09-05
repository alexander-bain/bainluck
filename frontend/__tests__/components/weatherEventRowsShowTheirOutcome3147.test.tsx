// ux/1083 (#3147) — the weather event rows show the outcome their number prices.
//
// 🔴 WHAT A READER SAW. `/weather`'s "Hurricane markets" rows printed a
// probability and then cut the outcome that probability is about:
//
//     Hurricane Marie category?   Categ…   ● Kalshi  ▬▬▬▬▬  95%
//     …name of the first hurricane…  E.    ● Kalshi  ▬▬     40%
//
// The 95% prices "Category 1 or above"; the 40% prices the NAME "Edouard".
// Cut to "Categ…" and "E.", the row reads as "95% chance this hurricane
// happens", which is not what the market says. The `leader` element exists for
// exactly that reason — a source comment in the component says so — and it was
// the element the layout sacrificed.
//
// 🔴 MEASURED, NOT ARGUED, AND NOT A PHONE BUG. `tools/look-local.mjs
// --clipped` (scrollWidth past clientWidth) over the production payload:
// 8 of 8 hurricane leaders cut at 390px AND 8 of 8 cut at 1280px; in the
// sibling card, even a leader as short as "50 - 74" cut to "50 -…" at both.
// The card lives in NaturalEvents' `1.4fr 1fr 1fr` grid capped at 1280px, so
// its content box is ~314px on a phone and only ~346-452px on a desktop. That
// is why the fix has no breakpoint in it: a `sm:` rule would have left every
// desktop reader with "Categ…".
//
// 🔴 WHY THESE ASSERTIONS AND NOT A WIDTH. jest here runs `testEnvironment:
// 'node'` — there is no layout engine, so no test in this file can measure a
// pixel, and one that claimed to would be lying. What a guard CAN pin is the
// mechanism: the ellipsis is gone (`truncate`), the outcome no longer shares a
// line with the question (a block closes between them), and the two elements
// that used to squeeze it cannot shrink. Each arm below was run red against the
// pre-fix component; the pixel claim is the rig's job and lives in the report.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import HurricaneTracker from "@/components/weather/HurricaneTracker";
import EventList from "@/components/weather/EventList";
import type { EventMarket } from "@/components/weather/data";

const LONG_LEADER = "Category 1 or above";
const QUESTION = "Hurricane Marie category?";

function hurricaneRow(over: Partial<EventMarket> = {}): EventMarket {
  return { q: QUESTION, leader: LONG_LEADER, prob: 95, src: "kalshi", closes: "Wed, Dec 2", ...over };
}

/** The markup between two rendered strings, in render order. */
function between(html: string, first: string, second: string): string {
  const a = html.indexOf(first);
  const b = html.indexOf(second);
  expect(a).toBeGreaterThan(-1);
  expect(b).toBeGreaterThan(a);
  return html.slice(a + first.length, b);
}

describe("HurricaneTracker — the outcome is not the part that gets cut", () => {
  it("renders the leader in full, with no ellipsis mechanism on it", () => {
    const html = renderToStaticMarkup(<HurricaneTracker items={[hurricaneRow()]} />);

    expect(html).toContain(LONG_LEADER);
    // `truncate` IS the defect: overflow-hidden + text-overflow-ellipsis on the
    // one element whose whole job is to be read.
    expect(html).not.toContain('class="truncate"');
  });

  it("puts the outcome on its own line — a block closes between question and leader", () => {
    const html = renderToStaticMarkup(<HurricaneTracker items={[hurricaneRow()]} />);

    // Pre-fix the two were siblings in one flex row and only `</span>` separated
    // them, so the leader could be squeezed to nothing by the question's wrap.
    expect(between(html, QUESTION, LONG_LEADER)).toContain("</div>");
  });

  it("keeps the source badge from compressing the line the outcome now sits on", () => {
    const html = renderToStaticMarkup(<HurricaneTracker items={[hurricaneRow()]} />);

    // SourceBadge is an inline-flex with no flex-shrink of its own, so as a bare
    // flex child it shrinks — and a shrinking badge takes the room back off the
    // leader beside it.
    //
    // The terminator is `rounded-full`, the badge's OWN opening tag, not the
    // word "Kalshi" inside it. Written the obvious way this arm passed against
    // the unfixed component: the badge's coloured dot carries `flexShrink: 0`
    // of its own, and it renders between the two, so the assertion was matching
    // the dot and proving nothing.
    expect(between(html, LONG_LEADER, "rounded-full")).toContain("flex-shrink:0");
  });

  it("wraps that line rather than squeezing it", () => {
    const html = renderToStaticMarkup(<HurricaneTracker items={[hurricaneRow()]} />);

    expect(between(html, QUESTION, LONG_LEADER)).toContain("flex-wrap");
  });

  it("still renders a row whose market has no leader", () => {
    // `leader` is optional and genuinely absent for self-answering questions —
    // the stacked layout must not depend on it existing.
    const html = renderToStaticMarkup(<HurricaneTracker items={[hurricaneRow({ leader: null })]} />);

    expect(html).toContain(QUESTION);
    expect(html).toContain("95%");
    expect(html).not.toContain(LONG_LEADER);
  });
});

describe("EventList — the same class in the card next door", () => {
  const list = (items: EventMarket[]) =>
    renderToStaticMarkup(
      <EventList title="Tornadoes" sub="Season-long count markets." icon="x" items={items} accent="#F59E0B" />,
    );

  it("renders the leader in full, with no ellipsis mechanism on it", () => {
    const html = list([{ q: "US Tornadoes in September 2026", leader: "50 - 74", prob: 55, src: "polymarket", closes: "Thu, Oct 15" }]);

    expect(html).toContain("50 - 74");
    expect(html).not.toContain('class="truncate"');
  });

  it("lets the badge, the outcome and the close date wrap instead of shrink", () => {
    const html = list([{ q: "US Tornadoes in September 2026", leader: "50 - 74", prob: 55, src: "polymarket", closes: "Thu, Oct 15" }]);

    // The meta row: everything between the question and the close date.
    const metaRow = between(html, "US Tornadoes in September 2026", "Thu, Oct 15");
    expect(metaRow).toContain("flex-wrap");
    // The badge kept whole — terminated on `rounded-full`, the badge's own tag,
    // for the reason given in the HurricaneTracker arm above (its inner dot
    // carries a flex-shrink that makes the naive assertion vacuous)...
    expect(between(html, "US Tornadoes in September 2026", "rounded-full")).toContain("flex-shrink:0");
    // ...and the date kept whole: squeezed, it broke mid-date across two lines
    // ("Thu, Oct" / "15"), which is a worse read than moving down one line.
    expect(between(html, "50 - 74", "Thu, Oct 15")).toContain("flex-shrink:0");
  });

  it("still renders a row whose market has no leader", () => {
    const html = list([{ q: "8.0 magnitude earthquake in Japan before 2030?", leader: null, prob: 38, src: "kalshi", closes: "Tue, Jan 1" }]);

    expect(html).toContain("8.0 magnitude earthquake in Japan before 2030?");
    expect(html).toContain("38%");
  });
});
