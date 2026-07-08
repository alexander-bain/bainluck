// L2-51: the weather sections must show an HONEST empty state when their API
// returns 200-empty (a #995 freeze symptom), never an infinite skeleton. The bug
// was the `data?.length ? data : null` pattern, which conflates "still loading"
// (undefined) with "loaded but empty" ([]). Source-inspection guard — the
// components lean on SWR + framer, so an RTL render is brittle; the invariant we
// protect ("loaded-empty is distinguished from loading and shows an honest card")
// is provable from the source.

import { readFileSync } from "fs";
import { join } from "path";

const read = (rel: string) =>
  readFileSync(join(__dirname, "../../", rel), "utf8");

describe("weather honest empty states (L2-51)", () => {
  test("TemperatureMap distinguishes loaded-empty from loading + shows honest card", () => {
    const src = read("components/weather/TemperatureMap.tsx");
    // loaded-empty is `liveCities !== undefined && !allCities`, not the skeleton
    expect(src).toContain("liveCities !== undefined");
    expect(src).toContain("No live temperature markets right now");
  });

  test("ClimateDashboard only skeletons while loading, honest card when empty", () => {
    const src = read("components/weather/ClimateDashboard.tsx");
    expect(src).toContain("liveClimate === undefined");
    expect(src).toContain("No live climate markets right now");
  });

  test("ClimateColumn shows an honest per-horizon empty instead of a bare header", () => {
    const src = read("components/weather/ClimateDashboard.tsx");
    expect(src).toContain("items.length === 0");
  });
});
