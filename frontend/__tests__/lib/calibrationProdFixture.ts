// The 2026-08-02 production `/api/calibration` payload.
//
// CAL-P043 (#1643): this file used to be a hand-transcribed COPY of the 68 rows
// that `ios/Bain Luck/BainLuckTests/CalibrationProdFixture.swift` embeds. Two
// copies of one payload in two languages is why the cross-surface parity gate
// could not compare anything: there was no artifact both clients were held
// against, so the gate compared the native fixture to constants sitting beside
// it and proved nothing (codex C236).
//
// There is now exactly one authoritative copy — `fixtures/calibration/` at the
// repo root, belonging to neither client — and this module reads it. The rows
// below are gone, not moved: nothing here can drift from what native sees,
// because there is nothing here to drift.
//
// L2-231 froze this response on native and computed its expected metrics from
// the FULL 340 KB payload with an independent implementation of the web page's
// aggregation. Web's half of that queue has to be graded on the SAME bytes, or
// "parity" is two surfaces each agreeing with their own fixture. It now
// literally is the same bytes.
//
// The compaction is lossless for everything asserted here: the live payload is
// 1,606 buckets keyed by `(source, category, price_moved, bucket_idx)`, and
// every non-per-category metric is a sum of `n` / `winners` / `sum_prob` /
// `sum_sq_err` into `bucket_idx` bins, so pre-summing the category dimension
// away leaves those numbers bit-identical at 68 rows. `category` therefore
// reads "agg" on every row, and this fixture CANNOT prove anything about the
// per-category rollup or the sample gate — stated so nobody reads more into it.
//
// Frozen deliberately. It is a record of one real server response, not a live
// feed; regenerating it whenever production moves destroys the only thing it is
// for. See `fixtures/calibration/README.md`.

import * as fs from "fs";
import * as path from "path";

export interface ProdFixtureBucket {
  bucket_idx: number;
  source: string;
  category: string;
  price_moved: boolean | null;
  n: number;
  winners: number;
  sum_prob: number;
  sum_sq_err: number;
}

/** The shared, language-neutral fixture directory. Owned by no client. */
export const SHARED_FIXTURE_DIR = path.join(
  __dirname, "..", "..", "..", "fixtures", "calibration",
);

export const PROD_FIXTURE_PATH = path.join(SHARED_FIXTURE_DIR, "prod-2026-08-02.json");

export interface ProdFixturePayload {
  population_version: string;
  generated_at: string;
  total_markets: number;
  total_outcomes: number;
  total_winners: number;
  min_category_outcomes: number;
  mce_ci_lower: number;
  mce_ci_upper: number;
  date_range: { start: string; end: string };
  cache: { status: string; reason: string; age_s: number; generated_at: string };
  buckets: ProdFixtureBucket[];
}

/**
 * The whole payload, as the server sent it.
 *
 * Read at module load with `fs` rather than `import`ed: this is a test-only
 * module, the path deliberately crosses out of `frontend/`, and a missing file
 * must be a LOUD failure at the first read rather than a bundler-resolution
 * question. If it throws, the fixture moved — fix the path, do not re-inline
 * the rows.
 */
export const PROD_PAYLOAD: ProdFixturePayload = JSON.parse(
  fs.readFileSync(PROD_FIXTURE_PATH, "utf8"),
);

/** `population_version` as the server published it in this response. */
export const PROD_POPULATION_VERSION: string = PROD_PAYLOAD.population_version;

/** `cache` as served: a dated last-good copy, 86,461 s old. */
export const PROD_CACHE = PROD_PAYLOAD.cache;

export const PROD_TOTAL_OUTCOMES: number = PROD_PAYLOAD.total_outcomes;
export const PROD_TOTAL_MARKETS: number = PROD_PAYLOAD.total_markets;

export const PROD_BUCKETS: ProdFixtureBucket[] = PROD_PAYLOAD.buckets;
