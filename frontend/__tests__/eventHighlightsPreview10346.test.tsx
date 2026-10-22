/**
 * #10346 pilot — three supported takeaways for one completed MLB game
 * (event 15319563, Boston at New York, AL Wild Card Series Game 1), behind
 * `?highlights=preview`, with the full catalogue one tap away.
 *
 * What this pins:
 *   - the gate: nothing renders without the exact parameter, before the game is
 *     completed, or on an event we hold no evidence for — so every other page is
 *     unchanged;
 *   - the fixture against its receipts: the official facts, the chances the page
 *     already serves for the same questions (literals from
 *     served-admission-excerpt.json), and their recorded instants against the
 *     committed MLB witnesses (first pitch, final play);
 *   - the reader copy: phases only ("Pregame" / "After Game 1"), never a clock
 *     interval, never a present-tense series standing, never contract mechanics,
 *     never "exactly two", causation or Game 2;
 *   - the three stories stay distinct: subject, question and kind;
 *   - the button opens the catalogue's fold and scrolls to it, and the page wraps
 *     the catalogue in the anchor the button looks for.
 */
import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";
import EventHighlightsPreview, { openAllMarkets } from "@/components/event/EventHighlightsPreview";
import {
  ALL_MARKETS_ANCHOR_ID,
  HIGHLIGHTS_PREVIEW_PARAM,
  formatQuotePercent,
  formatRecordedAt,
  highlightsPreviewFor,
} from "@/lib/eventHighlightsPreview";

const EVENT = 15319563;
const ARTIFACTS = join(__dirname, "..", "..", "artifacts", "discover-10346-highlights-pilot-20261022");
const artifact = (name: string) => JSON.parse(readFileSync(join(ARTIFACTS, name), "utf8"));
// MLB Stats API feed/live excerpt (source sha256 committed beside it): first pitch and the final play's end.
const FEED = artifact("feedlive-849851-excerpt.json");
const FIRST_PITCH = Date.parse(FEED.first_pitch_startTime);
const FINAL_OUT = Date.parse(FEED.final_play_endTime);

function preview() {
  const p = highlightsPreviewFor(EVENT, "completed", "preview");
  if (!p) throw new Error("fixture missing");
  return p;
}

/** Every string a reader can see: the fixture minus the reviewer-only rationale, plus the render. */
function readerText(): string {
  const fields = JSON.stringify(preview().highlights.map(({ rationale: _omitted, ...reader }) => reader));
  const html = renderToStaticMarkup(<EventHighlightsPreview preview={preview()} catalogueAvailable />);
  return `${fields}\n${html.replace(/<[^>]+>/g, " ")}`.toLowerCase();
}

describe("#10346 gate", () => {
  it("renders only for ?highlights=preview on a completed event with evidence", () => {
    expect(HIGHLIGHTS_PREVIEW_PARAM).toBe("highlights");
    expect(highlightsPreviewFor(EVENT, "completed", "preview")?.eventId).toBe(EVENT);
    expect(highlightsPreviewFor(EVENT, "completed", null)).toBeNull();
    expect(highlightsPreviewFor(EVENT, "completed", "")).toBeNull();
    expect(highlightsPreviewFor(EVENT, "completed", "1")).toBeNull();
    expect(highlightsPreviewFor(EVENT, "completed", "Preview")).toBeNull();
    expect(highlightsPreviewFor(EVENT, "in_progress", "preview")).toBeNull();
    expect(highlightsPreviewFor(EVENT, "upcoming", "preview")).toBeNull();
    expect(highlightsPreviewFor(EVENT + 1, "completed", "preview")).toBeNull();
    expect(highlightsPreviewFor(undefined, "completed", "preview")).toBeNull();
  });
});

describe("#10346 fixture against its receipts", () => {
  it("holds exactly three distinct stories", () => {
    const { highlights } = preview();
    expect(highlights).toHaveLength(3);
    expect(new Set(highlights.map((h) => h.subject)).size).toBe(3);
    expect(new Set(highlights.map((h) => h.before.question)).size).toBe(3);
    expect(new Set(highlights.map((h) => h.id)).size).toBe(3);
    for (const h of highlights) expect(h.rationale.length).toBeGreaterThan(40);
  });

  it("states the official facts", () => {
    const [k, hr, series] = preview().highlights;
    expect(FEED).toMatchObject({ gamePk: 849851, away: { name: "Boston Red Sox" }, home: { name: "New York Yankees" } });
    expect(FEED.final_runs).toEqual({ away: 0, home: 9 });
    expect(k.headline).toBe("Schlittler struck out 10");
    expect(k.detail).toBe("6⅓ scoreless innings, two hits allowed");
    expect(k.visual).toEqual({ kind: "count", unit: "strikeout", actual: 10, line: 10 });
    expect(hr.headline).toBe("Rice homered twice, the second a grand slam");
    expect(hr.detail).toBe("4 for 5; drove in 6 of the Yankees' 9 runs");
    // Box score HR note: "Rice 2 (2, 5th inning off Miller, E, 0 on, 2 out, 8th inning off Bello, 3 on, 2 out)."
    expect(hr.visual).toEqual({ kind: "count", unit: "home run", actual: 2, line: 2, marks: ["5th", "8th · slam"] });
    expect(series.headline).toBe("Yankees won Game 1, 9–0");
    expect(series.detail).toBe("Yankees led the best-of-three 1–0 after Game 1");
  });

  it("prints the chance the page already serves for each question", () => {
    const [k, hr, series] = preview().highlights;
    // served-admission-excerpt.json — player_props "Cam Schlittler: 10+" (Strikeouts): pregame_mark 0.185, outcome 237550446.
    expect(k.before).toMatchObject({ question: "10+ strikeouts", probability: 0.185 });
    expect(k.before.contributors).toEqual([
      { source: "Kalshi", outcomeId: 237550446, probability: 0.185, observedAt: k.before.observedAt },
    ]);
    // served-admission-excerpt.json — after_player_props "s:ben rice|home_runs|full_game|ge:2|over":
    // expectation blend_mean 0.0155 at 2026-09-29T23:50:23.519482Z from Kalshi 237550483 0.02 and
    // Polymarket 238585485 0.011 (both pregame_pin_5509). The card shows the typed one number, rounded whole.
    expect(hr.before).toMatchObject({
      question: "2+ home runs",
      probability: 0.0155,
      whole: true,
      observedAt: "2026-09-29T23:50:23.519Z",
    });
    expect(hr.before.contributors.map((c) => [c.source, c.outcomeId, c.probability])).toEqual([
      ["Kalshi", 237550483, 0.02],
      ["Polymarket", 238585485, 0.011],
    ]);
    // Same outcome both times: Kalshi Series Winner 235705604, New York Yankees.
    expect(series.before).toMatchObject({ question: "the Yankees winning the series", probability: 0.56 });
    expect(series.after).toMatchObject({ question: "the Yankees winning the series", probability: 0.805 });
    expect(series.before.contributors[0].outcomeId).toBe(235705604);
    expect(series.after?.contributors[0].outcomeId).toBe(235705604);
  });

  it("the cited excerpt holds those literals", () => {
    const served = artifact("served-admission-excerpt.json");
    const mark = (name: string) => served.player_props.find((m: { outcome_name: string }) => m.outcome_name === name).pregame_mark;
    expect(mark("Cam Schlittler: 10+")).toBe(0.185);
    expect(mark("Ben Rice: 2+")).toBe(0.02);
    const e = served.after_player_props_rice_2plus.expectation;
    expect([e.basis, e.probability, e.observed_at]).toEqual(["blend_mean", 0.0155, "2026-09-29T23:50:23.519482+00:00"]);
  });

  it("labels phases, never clocks, and the recorded instants agree with them", () => {
    for (const h of preview().highlights) {
      expect(h.before.when).toBe("Pregame");
      expect(Date.parse(h.before.observedAt)).toBeLessThan(FIRST_PITCH);
      for (const c of h.before.contributors) expect(Date.parse(c.observedAt)).toBeLessThan(FIRST_PITCH);
      if (h.after) {
        expect(h.after.when).toBe("After Game 1");
        expect(Date.parse(h.after.observedAt)).toBeGreaterThan(FINAL_OUT);
      }
    }
    expect(preview().highlights.filter((h) => h.after)).toHaveLength(1);
  });

  it("never makes a claim the evidence does not support", () => {
    const text = readerText();
    expect(text).not.toMatch(/min(ute)?s? (before|after)/);
    expect(text).not.toMatch(/first pitch/);
    expect(text).not.toMatch(/final out/);
    expect(text).not.toMatch(/\blead(s)?\b/);
    expect(text).not.toMatch(/\bbid/);
    expect(text).not.toMatch(/asking/);
    expect(text).not.toMatch(/exactly/);
    expect(text).not.toMatch(/because/);
    expect(text).not.toMatch(/game 2|game two/);
    expect(text).not.toMatch(/clinch|advanced|eliminated/);
    expect(text).not.toMatch(/odds/);
    expect(text).not.toMatch(/book/);
  });
});

describe("#10346 render", () => {
  it("prints the three cards and the catalogue button", () => {
    const html = renderToStaticMarkup(<EventHighlightsPreview preview={preview()} catalogueAvailable />);
    expect(html.match(/data-highlight-id=/g)).toHaveLength(3);
    for (const pct of ["18.5%", "2%", "56%", "80.5%"]) expect(html).toContain(`>${pct}<`);
    expect(html).not.toContain(">1.6%<");
    expect(html).toContain("Three takeaways");
    expect(html).toContain("Official MLB box score");
    expect(html).toContain('dateTime="2026-09-29T23:52:03.774Z"');
    expect(html).toContain("Sep 29, 7:52 PM ET");
    expect(html).toContain("Sep 29, 11:55 PM ET");
    expect(html).toContain("Kalshi + Polymarket");
    // The count visuals: 10 strikeout marks and 2 home-run marks, all hit, no percent.
    expect(html.match(/data-mark="hit"/g)).toHaveLength(12);
    expect(html).not.toContain('data-mark="open"');
    expect(html.match(/data-visual="count"/g)).toHaveLength(2);
    expect(html.match(/data-visual="paired"/g)).toHaveLength(1);
    // No grey number panel: the chances sit on the card itself.
    expect(html).not.toContain("rounded-lg bg-surface-elevated p-3");
    expect(html).toContain("data-testid=\"event-highlights-all-markets\"");
    expect(html).toContain("See every prop and market");
  });

  it("drops the button when the page has no catalogue to open", () => {
    const html = renderToStaticMarkup(<EventHighlightsPreview preview={preview()} catalogueAvailable={false} />);
    expect(html).not.toContain("event-highlights-all-markets");
  });

  it("formats quotes with a decimal only when they carry one", () => {
    expect(formatQuotePercent(0.185)).toBe("18.5%");
    expect(formatQuotePercent(0.02)).toBe("2%");
    expect(formatQuotePercent(0.56)).toBe("56%");
    expect(formatQuotePercent(0.805)).toBe("80.5%");
    expect(formatQuotePercent(0.011)).toBe("1.1%");
    expect(formatQuotePercent(0.0155, true)).toBe("2%");
  });

  it("dates values in ballpark time", () => {
    expect(formatRecordedAt("2026-09-29T23:50:23.519Z")).toBe("Sep 29, 7:50 PM ET");
    expect(formatRecordedAt("2026-09-30T03:55:42.969Z")).toBe("Sep 29, 11:55 PM ET");
  });
});

describe("#10346 one tap to the full catalogue", () => {
  it("opens the fold and scrolls the anchor into view", () => {
    const fold = { open: false };
    const scrolls: unknown[] = [];
    const anchor = {
      querySelector: (sel: string) => (sel === "details" ? fold : null),
      scrollIntoView: (opts: unknown) => scrolls.push(opts),
    };
    const doc = { getElementById: (id: string) => (id === ALL_MARKETS_ANCHOR_ID ? anchor : null) };
    expect(openAllMarkets(doc as unknown as Document)).toBe(true);
    expect(fold.open).toBe(true);
    expect(scrolls).toHaveLength(1);
  });

  it("does nothing when the anchor is absent", () => {
    expect(openAllMarkets({ getElementById: () => null } as unknown as Document)).toBe(false);
  });

  it("the event page wraps the catalogue in that anchor and gates the mount", () => {
    const src = readFileSync(join(__dirname, "..", "app", "events", "[id]", "page.tsx"), "utf8");
    expect(src).toMatch(
      /<div id=\{ALL_MARKETS_ANCHOR_ID\}[^>]*>\s*<QuestionCatalog data=\{gameMarkets\} status=\{event\.status\} \/>\s*<\/div>/,
    );
    expect(src).toContain(
      "highlightsPreviewFor(event?.id, event?.status, searchParams.get(HIGHLIGHTS_PREVIEW_PARAM))",
    );
    expect(src).toMatch(/\{highlightsPreview && !venueVoided && \(\s*<SectionErrorBoundary label="Three takeaways"/);
  });
});
