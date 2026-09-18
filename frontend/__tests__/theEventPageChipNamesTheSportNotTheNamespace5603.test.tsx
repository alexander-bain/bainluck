/**
 * #5603 (Brief18), EVENT-PAGE HALF — THE OTHER COMPONENT THAT PRINTED THE
 * ROUTING TOKEN AS IF IT WERE A SPORT.
 *
 * ═══ THE SPECIMEN, PHOTOGRAPHED ON PRODUCTION 2026-09-18 02:47Z ═══
 *
 * `https://bainluck.com/event/ufc/power-slap-23-26sep18powerslap23` at 390px
 * (`artifacts/ux-1324/5603b-BEFORE-eventpage-ufc-chip-390.png`):
 *
 *     UFC   LIVE
 *     # Power Slap 23
 *     Sep 18 · 1 market tracked
 *
 * Slap fighting, on its own page, headed by the name of a mixed-martial-arts
 * promotion it has nothing to do with. `8c40442e0` fixed the Discover and
 * Sports CARDS for this exact event; `EventHeader.tsx:49` was
 * `<span>{event.domain}</span>` and kept the lie on the page the card links to.
 *
 * ═══ WHY IT IS THE SAME BUG AND NOT A LOOKALIKE ═══
 *
 * `domain` is the event-key NAMESPACE this codebase routes on —
 * `event:ufc:<token>` — and `UFC_CONFIG` (`backend/app/utils/event_ufc.py`)
 * declares its width: schedule keys `mma_ufc` AND `mma_mixed_martial_arts`, plus
 * every `KXUFC*` Kalshi ticker. The adapter is named after its biggest tenant,
 * so the token is a route, never a claim about the sport. Same wrong source,
 * same wrong word, different component.
 *
 * The server now answers: PR #6801 (`6db7b2599`, merged 2026-09-17 21:43Z)
 * serves `event.sport_label` on the `/api/event` combat envelope. Read live
 * while writing this file:
 *
 *     event:ufc:26sep18powerslap23  →  sport_label "Combat"  (Power Slap 23)
 *     event:ufc:26sep19             →  sport_label "UFC"     (331: Van vs Pantoja)
 *
 * ═══ ONE CARD FAMILY, ONE LABEL (notice 35) ═══
 *
 * This calls `conceptDomainLabel` — the SAME function the two card renderers
 * call — rather than restating the rule. A rule fixed on one surface and
 * restated on another is #1935, #1939 and #1951 in turn; the arms below
 * therefore pin this component's OUTPUT, and the helper's own arms live with
 * the helper in `aSlapFightingCardStopsWearingAUfcChip5603.test.tsx`.
 *
 * ═══ WHAT EACH TEST IS FOR ═══
 *
 * Only the first is the ship clause. Every other test is a control, because the
 * ship clause alone is satisfied by hard-coding "COMBAT" — or by deleting the
 * chip:
 *
 *   - `a real UFC card keeps its name` kills the delete-UFC-everywhere mutant
 *     and is the reason the fix is a lookup and not a rename.
 *   - `the unevidenced arm` is the one a reader actually meets: `/api/event`
 *     carries an 86400s positive mirror, so for up to a DAY after the backend
 *     half releases the envelope arrives with no `sport_label` at all. A
 *     `sport_label || domain` consumer would have shipped the defect straight
 *     back for that whole day.
 *   - `a non-combat domain is untouched` proves the scope did not widen: golf
 *     and boxing are their own adapters and their tokens are true.
 *   - `the rest of the header is untouched` proves the change is the chip and
 *     not the header — the H1, the phase chip, the date and the markets count
 *     are four true things a suppression would have taken with it.
 */
import { renderToStaticMarkup } from "react-dom/server";

import EventHeader from "@/components/event/EventHeader";
import type { EventConceptResponse } from "@/lib/types";

type ConceptEvent = EventConceptResponse["event"];

/**
 * THE CHIP, AND ONLY THE CHIP. The header's first row opens with the domain
 * span, and asserting a bare word against whole-header markup is how a chip
 * gets passed by an unrelated string: "UFC" is legitimately allowed to appear
 * in `event.name` ("331: Van vs Pantoja" does not, but "UFC 331" would), and
 * the section nav renders `href="#..."` values this component does not own.
 * So read the span the component actually puts the label in.
 */
function chipText(html: string): string {
  const m = html.match(/<span[^>]*>([^<]*)<\/span>/);
  return m ? m[1].trim() : "";
}

/** What a reader sees: tags dropped, entities folded, whitespace collapsed. */
function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Production, `GET /api/event/event:ufc:26sep18powerslap23`, 2026-09-18 02:47Z. */
const POWER_SLAP: ConceptEvent = {
  key: "event:ufc:26sep18powerslap23",
  slug: "power-slap-23-26sep18powerslap23",
  domain: "ufc",
  sport_label: "Combat",
  name: "Power Slap 23",
  status: "live",
  start_date: "2026-09-18T00:00:00+00:00",
  end_date: null,
  venue: null,
  location: null,
  is_major: false,
};

/** Production, `GET /api/event/event:ufc:26sep19`, same minute. */
const UFC_331: ConceptEvent = {
  key: "event:ufc:26sep19",
  slug: null,
  domain: "ufc",
  sport_label: "UFC",
  name: "331: Van vs Pantoja",
  status: "upcoming",
  start_date: "2026-09-20T07:20:00+00:00",
  end_date: null,
  venue: null,
  location: null,
  is_major: false,
};

function render(event: ConceptEvent, marketsTracked = 1): string {
  return renderToStaticMarkup(
    <EventHeader
      event={event}
      marketsTracked={marketsTracked}
      nav={[{ id: "main-event", label: "Main event" }]}
      fallbackName="Event"
    />,
  );
}

describe("#5603 event page — the chip names the sport, not the namespace", () => {
  it("SHIP: a slap-fighting card on its own page is not headed UFC", () => {
    const chip = chipText(render(POWER_SLAP));

    expect(chip).toBe("COMBAT");
    expect(chip).not.toBe("ufc");
    expect(chip.toLowerCase()).not.toContain("ufc");
  });

  it("CONTROL: a real UFC card keeps its name", () => {
    // Without this arm the ship clause is satisfied by renaming every event in
    // the namespace, which trades one wrong chip for eight.
    expect(chipText(render(UFC_331))).toBe("UFC");
  });

  it("CONTROL: the unevidenced arm — a cached envelope with no sport_label", () => {
    // `/api/event` carries an 86400s positive mirror, so this is what a reader
    // gets for up to a day after the backend half releases, and it is also
    // every envelope served before it did. Absent and blank are separate cases
    // because `||` treats them alike and a chip of spaces is worse than either.
    const absent = { ...POWER_SLAP };
    delete (absent as { sport_label?: string | null }).sport_label;

    expect(chipText(render(absent))).toBe("COMBAT");
    expect(chipText(render({ ...POWER_SLAP, sport_label: null }))).toBe("COMBAT");
    expect(chipText(render({ ...POWER_SLAP, sport_label: "   " }))).toBe("COMBAT");
  });

  it("CONTROL: a non-combat domain is untouched", () => {
    // Golf and boxing are their own adapters, so their tokens are already true;
    // widening the unevidenced set would spend a truthful label to fix an
    // untruthful one.
    const golf: ConceptEvent = {
      ...POWER_SLAP,
      key: "event:golf:26sep17procamp",
      domain: "golf",
      name: "The Open",
      status: "upcoming",
    };
    delete (golf as { sport_label?: string | null }).sport_label;

    expect(chipText(render(golf))).toBe("GOLF");
    expect(chipText(render({ ...golf, domain: "boxing" }))).toBe("BOXING");
  });

  it("CONTROL: the rest of the header is untouched", () => {
    const text = visibleText(render(POWER_SLAP, 1));

    expect(text).toContain("Power Slap 23"); // the H1
    expect(text).toContain("Live"); // the phase chip, #3673's arm
    expect(text).toContain("1 market tracked"); // singular, not "1 markets"
    expect(text).toContain("Main event"); // the section nav
  });
});
