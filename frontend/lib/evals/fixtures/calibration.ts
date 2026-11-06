/**
 * A small `GET /api/calibration` payload for the /evals tests (#12102, S3).
 *
 * Shaped like the served one (read 8:28 PM PT Nov 5): per-source, per-category
 * buckets with `price_moved` true, false and null; a `scorecard` block; and a
 * `staged` block whose inputs are frozen behind a current curve. The numbers
 * are made up and deliberately unround, so a test that passes is comparing
 * computations rather than coincidences. `total_outcomes` is far larger than
 * the traded cohort on purpose: printing it beside the cohort's error is the
 * #7202 / #7564 defect, and the tests need the two to differ to catch it.
 *
 * Not a test file and never imported by the page: it lives outside `__tests__`
 * because components/evals/__tests__ imports it, and no file under app/,
 * components/ or lib/ may import a `__tests__` path (vercelIgnoreBuild contract).
 */

interface FixtureBucket {
  bucket_idx: number;
  source: string;
  category: string;
  price_moved: boolean | null;
  n: number;
  winners: number;
  avg_prob: number;
  sum_prob: number;
  sum_sq_err: number;
}

function bucket(
  idx: number,
  source: string,
  category: string,
  priceMoved: boolean | null,
  n: number,
  drift: number
): FixtureBucket {
  const p = idx / 10 + 0.05;
  const winners = Math.max(0, Math.min(n, Math.round(n * (p + drift))));
  return {
    bucket_idx: idx,
    source,
    category,
    price_moved: priceMoved,
    n,
    winners,
    avg_prob: Math.round(p * 10000) / 10000,
    sum_prob: Math.round(n * p * 10000) / 10000,
    sum_sq_err: Math.round(n * p * (1 - p) * 10000) / 10000,
  };
}

export function calibrationFixtureBuckets(): FixtureBucket[] {
  const rows: FixtureBucket[] = [];
  for (let idx = 0; idx < 10; idx += 1) {
    rows.push(bucket(idx, "kalshi", "politics", true, 1237 + idx * 41, 0.013));
    rows.push(bucket(idx, "polymarket", "nfl", true, 811 + idx * 17, -0.021));
    rows.push(bucket(idx, "kalshi", "nfl", false, 2903 + idx * 7, 0.034));
    rows.push(bucket(idx, "odds_api_bookmaker", "nba", null, 563 + idx * 29, -0.008));
  }
  return rows;
}

export function calibrationFixture(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    generated_at: "2026-11-06T03:28:13.171793+00:00",
    availability: "stale",
    staged: {
      measured: true,
      staged_at: "2026-10-27T20:54:56+00:00",
      frozen_over_drift: true,
      units_banked: 514,
      units_drifted: 511,
      reason: null,
    },
    producer: { stalled: false, beats_missed: 0, age_s: 3318 },
    cache: null,
    buckets: calibrationFixtureBuckets(),
    total_outcomes: 2126471,
    scorecard: { categories_at_bar: 24, categories_total: 53, categories_bar_pp: 3.0 },
    ...overrides,
  };
}
