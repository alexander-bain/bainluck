/**
 * CERT-1994 — A LATER ESPN CONFIRMATION REACHES A PAGE SOMEBODY LEFT OPEN.
 *
 * ═══ THE BUG ═══
 *
 * live/034 S2 set `refreshInterval` to **0** while the SSE stream is healthy.
 * Correct for the probability, which the frame carries. Wrong for everything
 * else: a frame holds one probability, one source and one stamp, and the cache
 * update spreads `...prev` for the rest — so on a page left open, the score, the
 * status, the tennis games line and its `observed_at` were all frozen at first
 * fetch.
 *
 * #3242's freshness chip turned that freeze into a false statement. The server
 * re-confirms the games line against ESPN every ~10 minutes; the page never
 * heard, so the chip counted up from a stamp nobody refreshed and said
 * `Stale · 40m ago` about a number re-confirmed a minute earlier. That is the
 * honesty mechanism itself lying, which is worse than the staleness it exists to
 * disclose.
 *
 * ═══ WHAT THIS PROVES, AND WHAT IT HONESTLY CANNOT ═══
 *
 * The cert asked for the new value to be shown reaching "the rendered hero"
 * across a live SSE session. This repo has **no jsdom and no React Testing
 * Library** — every component test is `renderToStaticMarkup` in the node
 * environment — so SWR's timer loop and React state cannot be driven here, and
 * standing up a DOM harness for one test is a bigger and riskier change than the
 * fix.
 *
 * So the data path is proved in the two places it can break, end to end, minus
 * SWR's own machinery:
 *
 *   1. the page must ASK again while connected — `eventRefreshInterval`, which
 *      was the whole defect and is now a pure function;
 *   2. the answer must SURVIVE the next pushed frame — `applyLiveFrame`;
 *   3. and the survivor must RENDER — the merged cache is fed to the real
 *      `FreshnessChip` and the real `liveHeroGamesLine`.
 *
 * Every clock is injected. Nothing here reads `Date.now()` (gotcha #44).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import FreshnessChip, { STALE_MS, isStale } from "@/components/event/FreshnessChip";
import { liveHeroGamesLine } from "@/lib/eventOutcome";
import {
  applyLiveFrame,
  eventRefreshInterval,
  pushedRefreshIntervalIsHonest,
  type LiveFrame,
} from "@/lib/eventLivePush";

const INTERVALS = { live: 32000, scheduled: 120000 };

const FRAME: LiveFrame = {
  p: 0.62,
  source: "kalshi",
  source_value: 0.61,
  updated_at: "2026-09-05T15:32:00+00:00",
};

/** What the page held at first fetch: a games line confirmed at 15:22. */
const FIRST_FETCH = {
  id: 15304504,
  status: "live",
  hero_probability: 0.58,
  hero_probability_away: 0.42,
  win_probability_sources: {
    kalshi: { value: 0.58, display_name: "Kalshi", type: "market", color: "#0af", updated_at: "2026-09-05T15:22:00+00:00" },
  },
  linescore: {
    sets: [[5, 4]] as [number, number][],
    home_games: 5,
    away_games: 4,
    source: "espn",
    observed_at: "2026-09-05T15:22:42+00:00",
  },
};

/** The same match ten minutes later: the server re-confirmed, score unchanged. */
const RE_CONFIRMED = {
  ...FIRST_FETCH,
  linescore: { ...FIRST_FETCH.linescore, observed_at: "2026-09-05T15:32:41+00:00" },
};

/** And a version where the games actually moved. */
const MOVED = {
  ...FIRST_FETCH,
  linescore: {
    sets: [[6, 4]] as [number, number][],
    home_games: 6,
    away_games: 4,
    source: "espn",
    observed_at: "2026-09-05T15:32:41+00:00",
  },
};

// ── 1. the page keeps asking ────────────────────────────────────────────────

describe("a pushed page still revalidates", () => {
  test("a healthy stream no longer means NEVER", () => {
    // The defect, stated as the assertion that would have caught it.
    expect(eventRefreshInterval("live", true, INTERVALS)).toBeGreaterThan(0);
  });

  test("and the cadence cannot itself manufacture a Stale chip", () => {
    // The derivation, pinned so editing either number alone breaks it: if the
    // page can go longer than `STALE_MS` without asking, then `Stale` stops
    // meaning "the data is old" and starts meaning one of two different things.
    const pushed = eventRefreshInterval("live", true, INTERVALS);
    expect(pushedRefreshIntervalIsHonest(pushed, STALE_MS)).toBe(true);
    expect(isStale(pushed)).toBe(false);
  });

  test("the control — with no stream, the 32s live poll is untouched", () => {
    // The push ship must not be undone in either direction. A live page with a
    // dead stream still polls at 32s, and a scheduled one still at 120s.
    expect(eventRefreshInterval("live", false, INTERVALS)).toBe(32000);
    expect(eventRefreshInterval("scheduled", false, INTERVALS)).toBe(120000);
    expect(eventRefreshInterval(undefined, false, INTERVALS)).toBe(120000);
  });
});

// ── 2. the answer survives the next frame ───────────────────────────────────

describe("a pushed frame carries the newer games line forward", () => {
  test("an unchanged line's NEW stamp survives a later frame", () => {
    // The re-confirmation has landed by poll; then a probability frame arrives.
    // If the frame reinstated its own snapshot the stamp would revert and the
    // chip would resume ageing from 15:22.
    const merged = applyLiveFrame(RE_CONFIRMED, FRAME)!;

    expect(merged.linescore.observed_at).toBe("2026-09-05T15:32:41+00:00");
    expect(merged.hero_probability).toBe(0.62);
  });

  test("a MOVED line keeps both its value and its stamp", () => {
    const merged = applyLiveFrame(MOVED, FRAME)!;

    expect(merged.linescore.sets).toEqual([[6, 4]]);
    expect(merged.linescore.home_games).toBe(6);
    expect(merged.linescore.observed_at).toBe("2026-09-05T15:32:41+00:00");
  });

  test("a frame never invents a games line where there is none", () => {
    const noLine = { ...FIRST_FETCH, linescore: undefined };
    expect(applyLiveFrame(noLine, FRAME)!.linescore).toBeUndefined();
  });

  test("the control — the frame DOES still move the probability", () => {
    // Otherwise "nothing was clobbered" would be satisfied by a merge that does
    // nothing at all, and the push ship would be silently dead.
    const merged = applyLiveFrame(FIRST_FETCH, FRAME)!;

    expect(merged.hero_probability).toBe(0.62);
    expect(merged.hero_probability_away).toBeCloseTo(0.38);
    expect(merged.win_probability_sources.kalshi.value).toBe(0.61);
    expect(merged.win_probability_sources.kalshi.updated_at).toBe("2026-09-05T15:32:00+00:00");
    // and the source's display metadata, which no frame knows, is preserved
    expect(merged.win_probability_sources.kalshi.display_name).toBe("Kalshi");
  });
});

// ── 3. and it renders ───────────────────────────────────────────────────────

describe("what the hero ends up showing", () => {
  const heroOf = (cache: typeof FIRST_FETCH) => {
    const games = liveHeroGamesLine({
      isFinished: false,
      isLive: true,
      hasStarted: true,
      linescore: cache.linescore,
    });
    const chip = renderToStaticMarkup(
      <FreshnessChip asOf={cache.linescore?.observed_at} />,
    );
    return { games, chip };
  };

  test("after a re-confirmation the chip carries the NEW stamp", () => {
    const before = heroOf(FIRST_FETCH);
    const after = heroOf(applyLiveFrame(RE_CONFIRMED, FRAME)!);

    expect(before.chip).toContain("Data as of 2026-09-05T15:22:42+00:00");
    expect(after.chip).toContain("Data as of 2026-09-05T15:32:41+00:00");
    expect(after.chip).not.toContain("15:22:42");
    // The score did not change, and it should not have.
    expect(after.games).toBe(before.games);
  });

  test("after a moved line the hero shows the new score AND the new stamp", () => {
    const before = heroOf(FIRST_FETCH);
    const after = heroOf(applyLiveFrame(MOVED, FRAME)!);

    expect(before.games).toBe("5-4");
    expect(after.games).toBe("6-4");
    expect(after.chip).toContain("Data as of 2026-09-05T15:32:41+00:00");
  });
});
