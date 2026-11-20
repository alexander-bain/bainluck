/**
 * #12628 — Win probability & futures charts use ONE consistent local clock
 * across x-axis ticks, reading mark aria-labels, mark key, and tapped readouts.
 * A reader outside Pacific Time (e.g. America/New_York) never sees EST ticks
 * beside a PT tap readout.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  AtlasChartMarkKey,
  AtlasSelectedReadingReadout,
  AtlasSeriesReadingMarks,
} from "@/components/atlas/AtlasChartMarks";
import { formatAtlasTimestampLocal } from "@/components/atlas/atlasStateCopy";
import { formatAxisTime } from "@/lib/chartAxisTimeLabel";

describe("#12628 — single chart clock outside Pacific Time", () => {
  // 2026-11-07T01:45:00Z = Nov 6, 2026 8:45:00 PM EST (5:45:00 PM PST)
  const ISO = "2026-11-07T01:45:00Z";
  const MS = Date.parse(ISO);

  it("mark key does not promise Pacific Time (PT)", () => {
    const html = renderToStaticMarkup(<AtlasChartMarkKey />);
    expect(html).toContain("Tap any reading for exact time");
    expect(html).not.toContain("(PT)");
  });

  it("tapped readout matches the x-axis clock in America/New_York (EST, never PT)", () => {
    const axisTick = formatAxisTime(MS, "clock", "America/New_York");
    expect(axisTick).toBe("8:45 PM");

    const localLabel = formatAtlasTimestampLocal(ISO, {
      includeSeconds: true,
      timeZone: "America/New_York",
    });
    expect(localLabel).toContain("Nov 6, 2026");
    expect(localLabel).toContain("8:45:00 PM");
    expect(localLabel).toContain("EST");
    expect(localLabel).not.toContain("5:45");
    expect(localLabel).not.toMatch(/\b(PT|PST|PDT)\b/);

    const readoutHtml = renderToStaticMarkup(
      <AtlasSelectedReadingReadout
        reading={{
          outcomeId: 1,
          outcomeName: "Denver Nuggets",
          probability: 0.64,
          timestamp: ISO,
          x: 120,
          y: 40,
          color: "#0D9488",
          isOpening: false,
        }}
        timeZone="America/New_York"
      />,
    );
    expect(readoutHtml).toContain("8:45:00 PM");
    expect(readoutHtml).toContain("EST");
    expect(readoutHtml).not.toContain("5:45");

    const marksHtml = renderToStaticMarkup(
      <svg>
        <AtlasSeriesReadingMarks
          outcomeId={1}
          outcomeName="Denver Nuggets"
          points={[{ t: MS, x: 120, y: 40, prob: 0.64, timestamp: ISO }]}
          color="#0D9488"
          timeZone="America/New_York"
        />
      </svg>,
    );
    expect(marksHtml).toContain("8:45:00 PM");
    expect(marksHtml).toContain("EST");
    expect(marksHtml).not.toContain("5:45");
  });

  it("tapped readout matches the x-axis clock in Europe/London (GMT, never PT)", () => {
    const axisTick = formatAxisTime(MS, "clock", "Europe/London");
    expect(axisTick).toBe("1:45 AM");

    const readoutHtml = renderToStaticMarkup(
      <AtlasSelectedReadingReadout
        reading={{
          outcomeId: 1,
          outcomeName: "Denver Nuggets",
          probability: 0.64,
          timestamp: ISO,
          x: 120,
          y: 40,
          color: "#0D9488",
          isOpening: false,
        }}
        timeZone="Europe/London"
      />,
    );
    expect(readoutHtml).toContain("1:45:00 AM");
    expect(readoutHtml).not.toContain("5:45");
    expect(readoutHtml).not.toMatch(/\b(PT|PST|PDT)\b/);
  });
});
