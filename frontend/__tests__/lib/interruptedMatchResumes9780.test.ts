/**
 * #9780 — AN INTERRUPTED MATCH STOPS ANNOUNCING THAT IT HAS NOT STARTED.
 *
 * Production, 2026-09-30 14:47Z, 390px: `/events/15320485` Lehecka v Bergs
 * (China Open) read "Starts in 14h 13m · Sep 30, 2026 · 10:00 PM PDT" with no
 * score. ESPN 183490 had Lehecka up a set, 6-3, and had moved the rest of the
 * match to 2026-10-01T05:00Z; Kalshi was pricing "Lehecka wins Set 2". The
 * served row (fixture below, verbatim fields) carried both facts at once:
 * a future `commence_time` and a linescore with games on it.
 */
import { playedBeforeItsClock, startBadgeLabel } from "@/lib/eventState";
import { liveHeroGamesLine } from "@/lib/eventOutcome";

/** `GET /api/events/15320485`, 2026-09-30 14:47Z — the fields the hero reads. */
const LEHECKA_BERGS = {
  status: "scheduled",
  commence_time: "2026-10-01T05:00:00+00:00",
  linescore: {
    sets: [[6, 3]] as [number, number][],
    source: "espn",
    observed_at: "2026-09-30T14:45:36.906782+00:00",
  },
};
const NOW = Date.parse("2026-09-30T14:47:00Z");
const hasStarted = Date.parse(LEHECKA_BERGS.commence_time) <= NOW; // false

describe("#9780 — the specimen", () => {
  const played = playedBeforeItsClock({
    hasStarted,
    isFinished: false,
    linescore: LEHECKA_BERGS.linescore,
  });

  it("reads a set on the board under a future clock as interrupted", () => {
    expect(hasStarted).toBe(false);
    expect(played).toBe(true);
  });

  it("the badge says the match resumes, not that it starts", () => {
    const label = startBadgeLabel(hasStarted, "14h 13m", false, played);
    expect(label).toBe("Resumes in 14h 13m");
    expect(label).not.toMatch(/^Starts/);
  });

  it("with no countdown it is paused, never pregame", () => {
    expect(startBadgeLabel(hasStarted, "", false, played)).toBe("Paused");
  });

  it("the hero shows the games the match has produced", () => {
    // The page passes `hasStarted || playedBeforeClock`.
    expect(
      liveHeroGamesLine({
        isFinished: false,
        isLive: false,
        hasStarted: hasStarted || played,
        linescore: LEHECKA_BERGS.linescore,
      })
    ).toBe("6-3");
  });
});

describe("#9780 — the rows that must not move", () => {
  it("an ordinary pregame row (no line, or a 0-0 line) still starts", () => {
    for (const linescore of [null, undefined, { sets: [] }, { sets: [[0, 0]] as [number, number][] }]) {
      const played = playedBeforeItsClock({ hasStarted: false, isFinished: false, linescore });
      expect(played).toBe(false);
      expect(startBadgeLabel(false, "2h 10m", false, played)).toBe("Starts in 2h 10m");
      expect(startBadgeLabel(false, "", false, played)).toBe("Pregame");
    }
  });

  it("a match past its clock is Started, whatever its board says", () => {
    const played = playedBeforeItsClock({
      hasStarted: true,
      isFinished: false,
      linescore: LEHECKA_BERGS.linescore,
    });
    expect(played).toBe(false);
    expect(startBadgeLabel(true, "", false, played)).toBe("Started");
  });

  it("a finished match is never interrupted", () => {
    expect(
      playedBeforeItsClock({ hasStarted: false, isFinished: true, linescore: LEHECKA_BERGS.linescore })
    ).toBe(false);
  });

  it("the three-argument call is byte-for-byte what it was", () => {
    expect(startBadgeLabel(false, "2h 10m", false)).toBe("Starts in 2h 10m");
    expect(startBadgeLabel(false, "")).toBe("Pregame");
    expect(startBadgeLabel(true, null, true)).toBe("Pregame");
  });
});
