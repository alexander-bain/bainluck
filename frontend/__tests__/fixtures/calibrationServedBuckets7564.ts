// Distilled from the served `GET /api/calibration` payload,
// `generated_at` 2026-09-15T11:16:10.215051+00:00, read 2026-09-20.
//
// The live payload carries 2,211 bucket rows split by source x category x
// `price_moved`. Summing is associative, so pooling them on
// (`bucket_idx`, `price_moved`) gives these 30 rows and preserves BOTH
// figures exactly: the population ECE (0.675pp) and the `price_moved=true`
// cohort's equal-weight bucket average (1.49pp, the number /about printed).
// Keeping both means the control below is measured, not invented.
//
// Totals: 747,028 rows = 293,900 `true` + 298,001 `false` + 155,127 `null`.
export const SERVED_BUCKETS_20260915 = [
  { bucket_idx: 0, price_moved: false, n: 58203, winners: 2720, sum_prob: 2660.5091 },
  { bucket_idx: 0, price_moved: null, n: 1673, winners: 186, sum_prob: 114.2014 },
  { bucket_idx: 0, price_moved: true, n: 64883, winners: 2318, sum_prob: 2702.0515 },
  { bucket_idx: 1, price_moved: false, n: 39262, winners: 5755, sum_prob: 5691.7884 },
  { bucket_idx: 1, price_moved: null, n: 3777, winners: 546, sum_prob: 577.6435 },
  { bucket_idx: 1, price_moved: true, n: 39483, winners: 5655, sum_prob: 5752.2967 },
  { bucket_idx: 2, price_moved: false, n: 38582, winners: 9367, sum_prob: 9515.6446 },
  { bucket_idx: 2, price_moved: null, n: 6342, winners: 1354, sum_prob: 1612.1177 },
  { bucket_idx: 2, price_moved: true, n: 35194, winners: 8568, sum_prob: 8691.9313 },
  { bucket_idx: 3, price_moved: false, n: 34462, winners: 12026, sum_prob: 11954.5766 },
  { bucket_idx: 3, price_moved: null, n: 11220, winners: 4109, sum_prob: 4004.1233 },
  { bucket_idx: 3, price_moved: true, n: 32423, winners: 10800, sum_prob: 11248.1168 },
  { bucket_idx: 4, price_moved: false, n: 36544, winners: 16539, sum_prob: 16427.1846 },
  { bucket_idx: 4, price_moved: null, n: 34934, winners: 16317, sum_prob: 16091.3311 },
  { bucket_idx: 4, price_moved: true, n: 34019, winners: 14140, sum_prob: 15327.557 },
  { bucket_idx: 5, price_moved: false, n: 37359, winners: 20540, sum_prob: 19909.5851 },
  { bucket_idx: 5, price_moved: null, n: 52174, winners: 27460, sum_prob: 28017.6804 },
  { bucket_idx: 5, price_moved: true, n: 29862, winners: 16187, sum_prob: 16133.3465 },
  { bucket_idx: 6, price_moved: false, n: 18737, winners: 12663, sum_prob: 12079.7392 },
  { bucket_idx: 6, price_moved: null, n: 20502, winners: 13065, sum_prob: 13190.0738 },
  { bucket_idx: 6, price_moved: true, n: 19026, winners: 12722, sum_prob: 12286.6264 },
  { bucket_idx: 7, price_moved: false, n: 14217, winners: 11136, sum_prob: 10566.415 },
  { bucket_idx: 7, price_moved: null, n: 12587, winners: 9595, sum_prob: 9370.7522 },
  { bucket_idx: 7, price_moved: true, n: 15888, winners: 12399, sum_prob: 11858.5235 },
  { bucket_idx: 8, price_moved: false, n: 8789, winners: 7579, sum_prob: 7435.5283 },
  { bucket_idx: 8, price_moved: null, n: 8215, winners: 7033, sum_prob: 6974.947 },
  { bucket_idx: 8, price_moved: true, n: 11711, winners: 10089, sum_prob: 9915.228 },
  { bucket_idx: 9, price_moved: false, n: 11846, winners: 11513, sum_prob: 11323.6113 },
  { bucket_idx: 9, price_moved: null, n: 3703, winners: 3441, sum_prob: 3453.9814 },
  { bucket_idx: 9, price_moved: true, n: 11411, winners: 11084, sum_prob: 10918.239 },
];
