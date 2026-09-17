// THE ADMIN HEALTH CARD STOPS PAINTING ELEVEN GREEN DOTS DURING A REDIS OUTAGE.
//
// ── WHAT THE OPERATOR SAW ────────────────────────────────────────────────────
//
// `backend/app/routes/health.py` builds `checks.last_polls` as a source→stamp
// map, and falls back to the bare STRING `"unavailable"` when its Redis read
// raises:
//
//     except Exception:
//         checks["last_polls"] = "unavailable"
//
// The admin PREQ card typed the field as `Record<string, string | null>` and
// handed it to `Object.entries`. That does not throw on a string — it
// enumerates the characters. Measured against the real render path:
//
//     rows: 11
//     [{"label":"0","dot":"GREEN","ts":"NaNd ago"},
//      {"label":"1","dot":"GREEN","ts":"NaNd ago"}, …]
//
// Eleven sources that do not exist, every dot GREEN (each character is truthy),
// every age "NaNd ago". The dot is the only thing on that card an operator
// scans, and it went green at exactly the moment Redis went down.
//
// ── THE RULE ─────────────────────────────────────────────────────────────────
//
// This is the failure `health.py`'s own comment argues against one screen
// upstream — "a probe whose reading is wrong in the reassuring direction is
// worse than no probe, because the one that means it gets ignored too". So the
// three cases are kept apart and only one of them may draw a dot: a real map
// (`stamps`), a field we could not read (`unavailable`, said out loud), and a
// field never served (`absent`, silent).
//
// A green dot in these tests means `ts` is truthy — that is exactly the
// expression the card renders (`ts ? "bg-green-400" : "bg-text-muted"`), so a
// stamp that survives as a truthy non-ISO value is the defect, not a detail.

import { readLastPolls } from "@/lib/adminLastPolls";

/** The card's own dot expression, so the assertions bind to what is drawn. */
function greenDots(stamps: Record<string, string | null>): string[] {
  return Object.entries(stamps)
    .filter(([, ts]) => Boolean(ts))
    .map(([source]) => source);
}

describe("readLastPolls", () => {
  it("does not enumerate the 'unavailable' string into eleven green sources", () => {
    const reading = readLastPolls("unavailable");

    expect(reading.kind).toBe("unavailable");
    // The regression, stated as the operator would: no rows, so no dots.
    expect(reading).not.toHaveProperty("stamps");
  });

  it("reads a real map and keeps null stamps grey", () => {
    const reading = readLastPolls({
      odds_api: "2026-09-17T14:00:00+00:00",
      kalshi: null,
    });

    expect(reading).toEqual({
      kind: "stamps",
      stamps: { odds_api: "2026-09-17T14:00:00+00:00", kalshi: null },
    });
    if (reading.kind !== "stamps") throw new Error("expected stamps");
    expect(greenDots(reading.stamps)).toEqual(["odds_api"]);
  });

  it("treats an absent field as absent, not as a degraded probe", () => {
    expect(readLastPolls(undefined).kind).toBe("absent");
    expect(readLastPolls(null).kind).toBe("absent");
  });

  it("nulls a non-string stamp rather than letting it draw a green dot", () => {
    // A number is truthy, so the old path drew a green dot and "NaNd ago".
    const reading = readLastPolls({ odds_api: 1758117600, kalshi: true });

    if (reading.kind !== "stamps") throw new Error("expected stamps");
    expect(reading.stamps).toEqual({ odds_api: null, kalshi: null });
    expect(greenDots(reading.stamps)).toEqual([]);
  });

  it("refuses an array, which enumerates as happily as a string", () => {
    expect(readLastPolls(["2026-09-17T14:00:00+00:00"]).kind).toBe("unavailable");
  });

  it("keeps an empty map distinct from a probe that failed", () => {
    expect(readLastPolls({})).toEqual({ kind: "stamps", stamps: {} });
  });
});
