// L2-146 Item 2: the Alcaraz trust exhibit reads from the committed raw-series
// archive (belt-and-suspenders vs Polymarket CLOB pruning). These tests prove
// the chart is sourced from the archive JSON, not an inline copy that could
// silently drift, and that the archive carries enough provenance to re-derive
// the series independently.

import { CASE_STUDIES } from "../../lib/story-content";
import alcarazSeries from "../../lib/data/alcaraz-ao-2026-series.json";

describe("Alcaraz case-study archive (L2-146 Item 2)", () => {
  const alcaraz = CASE_STUDIES.find((c) => c.id === "alcaraz-ao-2026");

  test("the case study exists and renders a line chart", () => {
    expect(alcaraz).toBeDefined();
    expect(alcaraz!.chart.type).toBe("line");
  });

  test("the chart reads its points from the committed archive (single source of truth)", () => {
    if (alcaraz!.chart.type !== "line") throw new Error("expected line chart");
    // Same object identity as the archive — proves it is read from the file,
    // not a copy that can drift.
    expect(alcaraz!.chart.points).toBe(alcarazSeries.points);
    expect(alcaraz!.chart.points).toEqual(alcarazSeries.points);
    expect(alcaraz!.chart.annotationIndex).toBe(alcarazSeries.annotation_index);
    expect(alcaraz!.chart.annotationLabel).toBe(alcarazSeries.annotation_label);
    expect(alcaraz!.chart.caption).toBe(alcarazSeries.caption);
  });

  test("the archived series is the real 14-point downsample with the 14% brink", () => {
    expect(alcarazSeries.points).toEqual([
      84, 82, 78, 90, 96, 98, 77, 14, 42, 53, 36, 23, 40, 100,
    ]);
    // Annotation points at the injury brink.
    expect(alcarazSeries.points[alcarazSeries.annotation_index]).toBe(14);
    // Every plotted value is a valid 0–100 probability.
    for (const p of alcarazSeries.points) {
      expect(p).toBeGreaterThanOrEqual(0);
      expect(p).toBeLessThanOrEqual(100);
    }
  });

  test("the archive carries the provenance needed to re-derive the series", () => {
    const p = alcarazSeries.provenance;
    expect(p.platform).toBe("Polymarket");
    expect(p.slug).toBe("atp-alcaraz-zverev-2026-01-30");
    expect(p.market_id).toBe("1276989");
    expect(p.source_endpoint).toContain("polymarket.com/prices-history");
    expect(typeof p.fetch_recipe).toBe("string");
    expect(p.fetch_recipe.length).toBeGreaterThan(0);
  });
});
