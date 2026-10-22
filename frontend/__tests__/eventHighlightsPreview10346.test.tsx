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
 *   - the card anatomy Design chose (2026-10-22): one Sources fold per card
 *     holding every provider, contributor and recorded time; no provider or clock
 *     row on a closed card; the series card led by its chance change with a
 *     visible recorded-day cue; no clamp or truncation; the fold at each card's
 *     foot on a stretched row, so a short card leaves no pocket under it;
 *   - times in the READER's zone through the one precise-stamp formatter, never
 *     a hard-coded ballpark zone;
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
  formatRecordedDays,
  highlightsPreviewFor,
} from "@/lib/eventHighlightsPreview";
import { preciseObservedAt } from "@/lib/liquidity";

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
    // Box score: Rice 5 AB, 4 H, 2 HR, 6 RBI.
    expect(hr.headline).toBe("Rice homered twice");
    expect(hr.detail).toBe("4 hits · 6 RBI");
    // Box score HR note: "Rice 2 (2, 5th inning off Miller, E, 0 on, 2 out, 8th inning off Bello, 3 on, 2 out)."
    expect(hr.visual).toEqual({ kind: "count", unit: "home run", actual: 2, line: 2, marks: ["5th", "8th · grand slam"] });
    // The series card leads with its chance change; the 9–0 result is dated context in its Sources fold.
    expect(series.headline).toBe("Series win chance rose");
    expect(series.detail).toBe("Yankees led 1–0 after Game 1");
    expect(series.sourceNote).toBe("Game 1 of the best-of-three: Yankees 9, Red Sox 0");
    expect(series.after!.probability).toBeGreaterThan(series.before.probability);
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

  it("each Rice contributor carries its OWN admitted clock from the excerpt, never a borrowed one", () => {
    // lane1b A3 on c0: pin every contributor's instant against the excerpt, not just its id and value.
    const served = artifact("served-admission-excerpt.json").after_player_props_rice_2plus.expectation;
    const hr = preview().highlights[1];
    const ms = (iso: string) => Math.floor(Date.parse(iso));
    expect(ms(hr.before.observedAt)).toBe(ms(served.observed_at));
    expect(hr.before.contributors).toHaveLength(served.contributors.length);
    served.contributors.forEach((c: { outcome_id: number; probability: number; observed_at: string }, i: number) => {
      const shown = hr.before.contributors[i];
      expect([shown.outcomeId, shown.probability]).toEqual([c.outcome_id, c.probability]);
      expect(ms(shown.observedAt)).toBe(ms(c.observed_at));
    });
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
    // Word-bounded: "Pregame 2%" in a Sources line is not Game 2.
    expect(text).not.toMatch(/\bgame (2|two)\b/);
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
    // This realm is pinned to UTC (jest.config.js), so the reader's zone is UTC here.
    expect(html).toContain("29 Sep, 11:52 PM UTC");
    expect(html).toContain("30 Sep, 3:55 AM UTC");
    expect(html).not.toMatch(/ ET\b/);
    expect(html).toContain("combines:");
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

  it("dates values in the reader's own zone, named, through the one precise-stamp formatter", () => {
    for (const iso of ["2026-09-29T23:50:23.519Z", "2026-09-30T03:55:42.969Z"]) {
      expect(formatRecordedAt(iso)).toBe(`${preciseObservedAt(iso)} UTC`);
    }
    expect(formatRecordedAt("2026-09-30T03:55:42.969Z")).toBe("30 Sep, 3:55 AM UTC");
    // No ballpark zone hard-coded anywhere in the pilot: the reader's zone is the default zone.
    const lib = readFileSync(join(__dirname, "..", "lib", "eventHighlightsPreview.ts"), "utf8");
    expect(lib).not.toMatch(/timeZone\s*:/);
    expect(lib).not.toMatch(/America\//);
  });

  it("names the reader-local day(s) each observation was recorded on", () => {
    expect(formatRecordedDays(["2026-09-29T23:51:28.157Z", "2026-09-30T03:55:42.969Z"])).toBe("29–30 Sep");
    expect(formatRecordedDays(["2026-09-29T20:00:00Z", "2026-09-29T23:51:28.157Z"])).toBe("29 Sep");
    expect(formatRecordedDays(["2026-10-01T03:00:00Z", "2026-09-30T23:00:00Z"])).toBe("30 Sep – 1 Oct");
  });
});

describe("#10346 card anatomy", () => {
  const html = () => renderToStaticMarkup(<EventHighlightsPreview preview={preview()} catalogueAvailable />);
  const cards = () => html().split("data-highlight-id=").slice(1);
  const visible = (card: string) => card.replace(/<details[\s\S]*?<\/details>/g, "");

  it("gives every card one Sources fold and keeps providers and clocks inside it", () => {
    const all = cards();
    expect(all).toHaveLength(3);
    for (const card of all) {
      expect(card.match(/<details/g)).toHaveLength(1);
      expect(card).toContain("data-sources");
      expect(card).toMatch(/<summary[^>]*>Sources<\/summary>/);
      const closed = visible(card);
      expect(closed).not.toContain("<time");
      expect(closed).not.toMatch(/Kalshi|Polymarket|UTC/);
    }
  });

  it("puts every contributor and recorded time in the folds", () => {
    const text = html();
    for (const iso of ["2026-09-29T23:52:03.774Z", "2026-09-29T23:50:23.519Z", "2026-09-29T23:50:22.756Z", "2026-09-29T23:51:28.157Z", "2026-09-30T03:55:42.969Z"]) {
      expect(text).toContain(`dateTime="${iso}"`);
    }
    const [, rice, series] = cards();
    expect(rice).toMatch(/Kalshi 2% · /);
    expect(rice).toMatch(/Polymarket 1\.1% · /);
    expect(series).toContain("Game 1 of the best-of-three: Yankees 9, Red Sox 0");
  });

  it("leads the series card with its chance change and keeps its recorded day visible", () => {
    const [k, rice, series] = cards().map(visible);
    expect(series).toContain("Series win chance rose");
    expect(series).toContain("Yankees led 1–0 after Game 1");
    expect(series).not.toContain("9–0");
    expect(series).toMatch(/data-recorded-days[^>]*>Recorded 29–30 Sep</);
    expect(series).toContain(">Pregame<");
    expect(series).toContain(">After Game 1<");
    expect(k).not.toContain("data-recorded-days");
    expect(rice).not.toContain("data-recorded-days");
  });

  it("states the grand slam once, on its home-run mark", () => {
    const rice = visible(cards()[1]).replace(/<[^>]+>/g, " ");
    expect(rice.match(/grand slam/g)).toHaveLength(1);
    expect(rice).toContain("8th · grand slam");
  });

  it("puts every chance on a card in ONE grid, so paired bars share a track at any text size", () => {
    for (const card of cards()) {
      const grids = card.match(/<div class="grid [^"]*" data-chance-grid="true">/g) ?? [];
      expect(grids).toHaveLength(1);
      // Label wraps between words (never inside one), the bar keeps a visible minimum, the number fits its widest value.
      expect(grids[0]).toContain("grid-cols-[minmax(min-content,5.5rem)_minmax(2.5rem,1fr)_auto]");
      // Too narrow at the reader's text size: the phase takes its own line above bar and number.
      expect(grids[0]).toContain("[@container(max-width:14rem)]:grid-cols-[minmax(2.5rem,1fr)_auto]");
      expect(card).toMatch(/class="[^"]*\[container-type:inline-size\][^"]*" data-visual="(chance|paired)"/);
      expect(card.match(/\[@container\(max-width:14rem\)\]:col-span-2/g)?.length).toBe(card.match(/data-when=/g)?.length);
    }
    const series = cards()[2];
    const grid = series.slice(series.indexOf("data-chance-grid"));
    // Both series rows are cells of that one grid, not grids of their own.
    expect(grid.match(/data-when="[^"]+" class="contents"/g)).toEqual([
      'data-when="Pregame" class="contents"',
      'data-when="After Game 1" class="contents"',
    ]);
  });

  it("never clamps, truncates or fixes a card's height, and seats the fold at each card's foot", () => {
    const text = html();
    expect(text).not.toMatch(/\btruncate\b|line-clamp|\bh-\[|max-h-/);
    expect(text).toMatch(/<ol class="[^"]*\bitems-stretch\b[^"]*\bmd:items-stretch\b/);
    expect(text).not.toMatch(/<ol class="[^"]*items-start/);
    for (const card of cards()) expect(card).toMatch(/<details class="mt-auto /);
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
