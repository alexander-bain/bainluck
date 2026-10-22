/**
 * #10346 pilot — three supported takeaways for one completed MLB game
 * (event 15319563, Boston at New York, AL Wild Card Series Game 1), behind
 * `?highlights=preview`, with the full catalogue one tap away.
 *
 * What this pins:
 *   - the gate: nothing renders without the exact parameter, before the game is
 *     completed, or on an event we hold no evidence for — so every other page is
 *     unchanged;
 *   - the fixture against its receipts: the official facts, the quote values and
 *     their clocks relative to the official first pitch and final out;
 *   - the claims the copy may never make (first-pitch odds, "exactly two",
 *     causation, anything about Game 2);
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
  highlightsPreviewFor,
} from "@/lib/eventHighlightsPreview";

const EVENT = 15319563;
// MLB Stats API feed/live, gamePk 849851: first pitch event and the final play's end.
const FIRST_PITCH = Date.parse("2026-09-30T00:15:26.152Z");
const FINAL_OUT = Date.parse("2026-09-30T03:16:33.590Z");

function preview() {
  const p = highlightsPreviewFor(EVENT, "completed", "preview");
  if (!p) throw new Error("fixture missing");
  return p;
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

  it("states the official facts and the stored quotes", () => {
    const [k, hr, series] = preview().highlights;
    expect(k.headline).toBe("Schlittler struck out 10");
    expect(k.detail).toBe("6⅓ scoreless innings, two hits allowed");
    expect(k.before).toMatchObject({ question: "10+ strikeouts", probability: 0.185, source: "Kalshi" });
    expect(hr.headline).toBe("Rice homered twice, the second a grand slam");
    expect(hr.detail).toBe("4 for 5; drove in 6 of the Yankees' 9 runs");
    expect(hr.before).toMatchObject({ question: "2+ home runs", probability: 0.02, source: "Kalshi" });
    expect(hr.before.caveat).toMatch(/no one was bidding/i);
    expect(series.headline).toBe("Yankees won Game 1, 9–0");
    expect(series.before).toMatchObject({ question: "Yankees win the series", probability: 0.56 });
    expect(series.after).toMatchObject({ question: "Yankees win the series", probability: 0.805, label: "After Game 1" });
  });

  it("dates every before-quote ahead of first pitch and the after-quote past the final out", () => {
    for (const h of preview().highlights) {
      const at = Date.parse(h.before.observedAt);
      expect(at).toBeLessThan(FIRST_PITCH);
      expect(FIRST_PITCH - at).toBeLessThan(30 * 60_000);
      expect(h.before.when).toBe(`${Math.round((FIRST_PITCH - at) / 60_000)} min before first pitch`);
      if (h.after) {
        const after = Date.parse(h.after.observedAt);
        expect(after).toBeGreaterThan(FINAL_OUT);
        expect(h.after.when).toBe(`${Math.round((after - FINAL_OUT) / 60_000)} min after the final out`);
      }
    }
  });

  it("never makes a claim the evidence does not support", () => {
    const text = JSON.stringify(
      preview().highlights.map(({ rationale: _omitted, ...reader }) => reader),
    ).toLowerCase();
    expect(text).not.toMatch(/at first pitch/);
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
    expect(html).toContain("Three takeaways");
    expect(html).toContain("Official MLB box score");
    expect(html).toContain('dateTime="2026-09-29T23:52:03.774Z"');
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
