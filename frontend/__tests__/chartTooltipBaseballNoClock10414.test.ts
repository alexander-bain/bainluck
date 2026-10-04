/**
 * #10414 — the win-probability tooltip printed a game clock baseball does not
 * have: "Top 9th 0:00".
 *
 * Production /events/15322620 (NLDS, Brewers 3–2), 2026-10-04: the served
 * `espn_history` carries `game_clock: "0:00"` on 209 of 210 rows (the last says
 * "Final"); the newest in-game row is `period: "Top 9th"`, `game_clock: "0:00"`.
 * #6684 stopped the header, cards and feed printing it through
 * `trustedLiveClock`'s sport arm, but the tooltip called the helper with no
 * sport key, so that arm could not fire there.
 */
import { readFileSync } from "fs";
import { join } from "path";
import { formatLiveClockLabel } from "@/lib/gameTimeLabel";

const CHART = readFileSync(join(__dirname, "..", "components", "OddsChart.tsx"), "utf8");
const PAGE = readFileSync(join(__dirname, "..", "app", "events", "[id]", "page.tsx"), "utf8");

describe("#10414 the chart tooltip prints no clock for a sport that has none", () => {
  it("the served specimen: a baseball half-inning keeps its period and loses the placeholder", () => {
    expect(formatLiveClockLabel("Top 9th", "0:00", " ", "baseball_mlb")).toBe("Top 9th");
  });

  it("CONTROL — clocked sports keep their clock, and #7860's de-dup still applies", () => {
    expect(formatLiveClockLabel("3rd Quarter", "4:12", " ", "americanfootball_nfl")).toBe("3rd Quarter 4:12");
    expect(formatLiveClockLabel("9:44 - 2nd Quarter", "9:44", " ", "americanfootball_nfl")).toBe("9:44 - 2nd Quarter");
    expect(formatLiveClockLabel("13 - 2nd Period", "13", " ", "icehockey_nhl")).toBe("13 - 2nd Period");
    expect(formatLiveClockLabel("2nd Half", "67'", " ", "soccer_epl")).toBe("2nd Half 67'");
    // No key at all: exactly what #7860 rendered.
    expect(formatLiveClockLabel("Top 9th", "0:00")).toBe("Top 9th 0:00");
  });

  it("the tooltip's clock line is handed the chart's own sportKey prop", () => {
    const span = CHART.match(/\{matchingPoint\._period && \(\s*<span[^>]*>([\s\S]*?)<\/span>/);
    expect(span).not.toBeNull();
    expect((span as RegExpMatchArray)[1]).toMatch(/formatLiveClockLabel\([\s\S]*?,\s*" ",\s*sportKey,?\s*\)/);
    // `sportKey` there is the component prop, destructured once and never rebound.
    expect(CHART.match(/^\s*sportKey,\s*$/gm)?.length ?? 0).toBeGreaterThanOrEqual(1);
    expect(CHART).not.toMatch(/\b(?:const|let|var)\s+sportKey\b/);
  });

  it("both event-page charts pass the event's sport", () => {
    const sites = PAGE.split("<OddsChart").slice(1).map((s) => s.slice(0, s.indexOf("/>")));
    expect(sites).toHaveLength(2);
    for (const site of sites) expect(site).toMatch(/sportKey=\{event\.sport/);
  });
});
