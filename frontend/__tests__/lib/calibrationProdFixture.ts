// L2-236 — the 2026-08-02 production `/api/calibration` payload, ported
// verbatim from `ios/Bain Luck/BainLuckTests/CalibrationProdFixture.swift`.
//
// L2-231 froze this response on native and computed its expected metrics from
// the FULL 340 KB payload with an independent implementation of the web page's
// aggregation. Web's half of that queue has to be graded on the SAME bytes, or
// "parity" is two surfaces each agreeing with their own fixture.
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
// for.

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

/** `population_version` as the server published it in this response. */
export const PROD_POPULATION_VERSION = "q267";

/** `cache` as served: a dated last-good copy, 86,461 s old. */
export const PROD_CACHE = {
  status: "stale",
  reason: "main_key_absent",
  age_s: 86461,
  generated_at: "2026-08-02T03:23:54.886392+00:00",
} as const;

export const PROD_TOTAL_OUTCOMES = 652407;
export const PROD_TOTAL_MARKETS = 534269;

export const PROD_BUCKETS: ProdFixtureBucket[] = [
  { bucket_idx: 0, source: "kalshi", category: "agg", price_moved: false, n: 30105, winners: 1069, sum_prob: 1205.7544, sum_sq_err: 1004.4945 },
  { bucket_idx: 0, source: "kalshi", category: "agg", price_moved: true, n: 48921, winners: 1664, sum_prob: 2004.0701, sum_sq_err: 1571.4241 },
  { bucket_idx: 1, source: "kalshi", category: "agg", price_moved: false, n: 22148, winners: 3442, sum_prob: 3251.855, sum_sq_err: 2881.8111 },
  { bucket_idx: 1, source: "kalshi", category: "agg", price_moved: true, n: 34320, winners: 4868, sum_prob: 5026.8249, sum_sq_err: 4141.0572 },
  { bucket_idx: 2, source: "kalshi", category: "agg", price_moved: false, n: 19493, winners: 4863, sum_prob: 4794.7026, sum_sq_err: 3628.6875 },
  { bucket_idx: 2, source: "kalshi", category: "agg", price_moved: true, n: 33401, winners: 8221, sum_prob: 8248.2518, sum_sq_err: 6178.5158 },
  { bucket_idx: 3, source: "kalshi", category: "agg", price_moved: false, n: 16519, winners: 5411, sum_prob: 5725.8385, sum_sq_err: 3628.4335 },
  { bucket_idx: 3, source: "kalshi", category: "agg", price_moved: true, n: 29098, winners: 9621, sum_prob: 10088.1994, sum_sq_err: 6416.5374 },
  { bucket_idx: 4, source: "kalshi", category: "agg", price_moved: false, n: 19137, winners: 8319, sum_prob: 8632.9299, sum_sq_err: 4694.2691 },
  { bucket_idx: 4, source: "kalshi", category: "agg", price_moved: true, n: 29850, winners: 12821, sum_prob: 13431.3187, sum_sq_err: 7300.0362 },
  { bucket_idx: 5, source: "kalshi", category: "agg", price_moved: false, n: 14838, winners: 7842, sum_prob: 7999.011, sum_sq_err: 3699.8138 },
  { bucket_idx: 5, source: "kalshi", category: "agg", price_moved: true, n: 26400, winners: 14694, sum_prob: 14343.2895, sum_sq_err: 6512.4965 },
  { bucket_idx: 6, source: "kalshi", category: "agg", price_moved: false, n: 9985, winners: 6564, sum_prob: 6445.9555, sum_sq_err: 2235.9594 },
  { bucket_idx: 6, source: "kalshi", category: "agg", price_moved: true, n: 20860, winners: 13779, sum_prob: 13484.3891, sum_sq_err: 4673.4291 },
  { bucket_idx: 7, source: "kalshi", category: "agg", price_moved: false, n: 7524, winners: 5744, sum_prob: 5591.0644, sum_sq_err: 1358.3287 },
  { bucket_idx: 7, source: "kalshi", category: "agg", price_moved: true, n: 19189, winners: 14687, sum_prob: 14328.7136, sum_sq_err: 3436.5986 },
  { bucket_idx: 8, source: "kalshi", category: "agg", price_moved: false, n: 4600, winners: 3920, sum_prob: 3886.3947, sum_sq_err: 574.6627 },
  { bucket_idx: 8, source: "kalshi", category: "agg", price_moved: true, n: 14471, winners: 12220, sum_prob: 12250.0619, sum_sq_err: 1906.8605 },
  { bucket_idx: 9, source: "kalshi", category: "agg", price_moved: false, n: 9124, winners: 9030, sum_prob: 8923.48, sum_sq_err: 93.363 },
  { bucket_idx: 9, source: "kalshi", category: "agg", price_moved: true, n: 10611, winners: 9894, sum_prob: 10079.055, sum_sq_err: 668.603 },
  { bucket_idx: 0, source: "odds_api", category: "agg", price_moved: null, n: 358, winners: 25, sum_prob: 21.9098, sum_sq_err: 24.1755 },
  { bucket_idx: 1, source: "odds_api", category: "agg", price_moved: null, n: 761, winners: 110, sum_prob: 116.6779, sum_sq_err: 93.7015 },
  { bucket_idx: 2, source: "odds_api", category: "agg", price_moved: null, n: 1241, winners: 305, sum_prob: 317.1097, sum_sq_err: 230.2371 },
  { bucket_idx: 3, source: "odds_api", category: "agg", price_moved: null, n: 1829, winners: 671, sum_prob: 649.1661, sum_sq_err: 422.8593 },
  { bucket_idx: 4, source: "odds_api", category: "agg", price_moved: null, n: 3170, winners: 1486, sum_prob: 1427.7676, sum_sq_err: 789.494 },
  { bucket_idx: 5, source: "odds_api", category: "agg", price_moved: null, n: 3412, winners: 1805, sum_prob: 1863.2323, sum_sq_err: 849.9939 },
  { bucket_idx: 6, source: "odds_api", category: "agg", price_moved: null, n: 1829, winners: 1158, sum_prob: 1179.8341, sum_sq_err: 422.8593 },
  { bucket_idx: 7, source: "odds_api", category: "agg", price_moved: null, n: 1241, winners: 936, sum_prob: 923.8904, sum_sq_err: 230.237 },
  { bucket_idx: 8, source: "odds_api", category: "agg", price_moved: null, n: 755, winners: 645, sum_prob: 638.9222, sum_sq_err: 93.6414 },
  { bucket_idx: 9, source: "odds_api", category: "agg", price_moved: null, n: 364, winners: 339, sum_prob: 341.4903, sum_sq_err: 24.2355 },
  { bucket_idx: 0, source: "odds_api_spreads", category: "agg", price_moved: null, n: 5, winners: 0, sum_prob: 0.3383, sum_sq_err: 0.025 },
  { bucket_idx: 1, source: "odds_api_spreads", category: "agg", price_moved: null, n: 3, winners: 0, sum_prob: 0.4221, sum_sq_err: 0.0603 },
  { bucket_idx: 2, source: "odds_api_spreads", category: "agg", price_moved: null, n: 36, winners: 12, sum_prob: 10.1786, sum_sq_err: 8.2404 },
  { bucket_idx: 3, source: "odds_api_spreads", category: "agg", price_moved: null, n: 683, winners: 239, sum_prob: 248.5348, sum_sq_err: 154.8208 },
  { bucket_idx: 4, source: "odds_api_spreads", category: "agg", price_moved: null, n: 4505, winners: 2136, sum_prob: 2136.6653, sum_sq_err: 1121.4393 },
  { bucket_idx: 5, source: "odds_api_spreads", category: "agg", price_moved: null, n: 6761, winners: 3550, sum_prob: 3493.6614, sum_sq_err: 1684.8433 },
  { bucket_idx: 6, source: "odds_api_spreads", category: "agg", price_moved: null, n: 363, winners: 228, sum_prob: 230.8864, sum_sq_err: 84.8817 },
  { bucket_idx: 7, source: "odds_api_spreads", category: "agg", price_moved: null, n: 28, winners: 19, sum_prob: 20.1748, sum_sq_err: 6.3278 },
  { bucket_idx: 8, source: "odds_api_spreads", category: "agg", price_moved: null, n: 17, winners: 8, sum_prob: 14.4206, sum_sq_err: 6.7482 },
  { bucket_idx: 9, source: "odds_api_spreads", category: "agg", price_moved: null, n: 9, winners: 5, sum_prob: 8.5354, sum_sq_err: 3.532 },
  { bucket_idx: 0, source: "odds_api_totals", category: "agg", price_moved: null, n: 22, winners: 5, sum_prob: 1.827, sum_sq_err: 4.2943 },
  { bucket_idx: 1, source: "odds_api_totals", category: "agg", price_moved: null, n: 22, winners: 9, sum_prob: 3.4453, sum_sq_err: 6.6365 },
  { bucket_idx: 2, source: "odds_api_totals", category: "agg", price_moved: null, n: 21, winners: 5, sum_prob: 5.1902, sum_sq_err: 3.8069 },
  { bucket_idx: 3, source: "odds_api_totals", category: "agg", price_moved: null, n: 92, winners: 23, sum_prob: 35.0081, sum_sq_err: 19.0408 },
  { bucket_idx: 4, source: "odds_api_totals", category: "agg", price_moved: null, n: 4613, winners: 2104, sum_prob: 2198.3425, sum_sq_err: 1145.5325 },
  { bucket_idx: 5, source: "odds_api_totals", category: "agg", price_moved: null, n: 7865, winners: 4009, sum_prob: 4029.312, sum_sq_err: 1963.3489 },
  { bucket_idx: 6, source: "odds_api_totals", category: "agg", price_moved: null, n: 68, winners: 40, sum_prob: 42.4462, sum_sq_err: 17.0238 },
  { bucket_idx: 7, source: "odds_api_totals", category: "agg", price_moved: null, n: 2, winners: 0, sum_prob: 1.4407, sum_sq_err: 1.0382 },
  { bucket_idx: 0, source: "polymarket", category: "agg", price_moved: false, n: 20849, winners: 1013, sum_prob: 924.2361, sum_sq_err: 941.6644 },
  { bucket_idx: 0, source: "polymarket", category: "agg", price_moved: true, n: 22832, winners: 866, sum_prob: 994.5766, sum_sq_err: 828.4271 },
  { bucket_idx: 1, source: "polymarket", category: "agg", price_moved: false, n: 11894, winners: 1795, sum_prob: 1718.8509, sum_sq_err: 1517.1893 },
  { bucket_idx: 1, source: "polymarket", category: "agg", price_moved: true, n: 10540, winners: 1457, sum_prob: 1485.7869, sum_sq_err: 1263.3773 },
  { bucket_idx: 2, source: "polymarket", category: "agg", price_moved: false, n: 13162, winners: 2918, sum_prob: 3239.0234, sum_sq_err: 2275.9411 },
  { bucket_idx: 2, source: "polymarket", category: "agg", price_moved: true, n: 8267, winners: 1511, sum_prob: 2023.3454, sum_sq_err: 1252.2602 },
  { bucket_idx: 3, source: "polymarket", category: "agg", price_moved: false, n: 12010, winners: 4225, sum_prob: 4164.9841, sum_sq_err: 2729.2094 },
  { bucket_idx: 3, source: "polymarket", category: "agg", price_moved: true, n: 8676, winners: 2438, sum_prob: 2997.3679, sum_sq_err: 1774.8375 },
  { bucket_idx: 4, source: "polymarket", category: "agg", price_moved: false, n: 14379, winners: 6337, sum_prob: 6498.602, sum_sq_err: 3552.3037 },
  { bucket_idx: 4, source: "polymarket", category: "agg", price_moved: true, n: 12217, winners: 3852, sum_prob: 5637.4024, sum_sq_err: 2943.2934 },
  { bucket_idx: 5, source: "polymarket", category: "agg", price_moved: false, n: 17911, winners: 9018, sum_prob: 9369.8898, sum_sq_err: 4423.6767 },
  { bucket_idx: 5, source: "polymarket", category: "agg", price_moved: true, n: 10146, winners: 4596, sum_prob: 5348.3031, sum_sq_err: 2531.5903 },
  { bucket_idx: 6, source: "polymarket", category: "agg", price_moved: false, n: 7017, winners: 4811, sum_prob: 4533.54, sum_sq_err: 1515.2816 },
  { bucket_idx: 6, source: "polymarket", category: "agg", price_moved: true, n: 2902, winners: 1905, sum_prob: 1872.8431, sum_sq_err: 651.3405 },
  { bucket_idx: 7, source: "polymarket", category: "agg", price_moved: false, n: 6051, winners: 4657, sum_prob: 4493.1272, sum_sq_err: 1078.9885 },
  { bucket_idx: 7, source: "polymarket", category: "agg", price_moved: true, n: 2570, winners: 2017, sum_prob: 1918.059, sum_sq_err: 435.732 },
  { bucket_idx: 8, source: "polymarket", category: "agg", price_moved: false, n: 3184, winners: 2549, sum_prob: 2693.6701, sum_sq_err: 516.2893 },
  { bucket_idx: 8, source: "polymarket", category: "agg", price_moved: true, n: 1650, winners: 1393, sum_prob: 1394.9429, sum_sq_err: 216.0698 },
  { bucket_idx: 9, source: "polymarket", category: "agg", price_moved: false, n: 3092, winners: 2809, sum_prob: 2844.6062, sum_sq_err: 261.5865 },
  { bucket_idx: 9, source: "polymarket", category: "agg", price_moved: true, n: 2389, winners: 2280, sum_prob: 2223.6185, sum_sq_err: 107.6429 },
];
