// CAL-P043 (#1643, codex C236) — web's half of the cross-surface parity gate.
//
// ## What was wrong, precisely
//
// `frontend/e2e/contract/calibrationSurfaceParity.contract.test.js` was named
// for comparing two surfaces and compared one. Its central test — "the native
// fixture records the same production response web's fixture does" — opened the
// NATIVE fixture and checked it against constants declared beside it in the same
// file. It never opened web's fixture, never called web code, and never read a
// web-computed value. Both clients could disagree completely while it was green,
// and it was cited as coverage for calibration exit-exam item 5.
//
// ## How the two surfaces are compared now
//
// They cannot meet in one process: native's figures require Swift, web's require
// TypeScript. So they meet in an artifact —
// `fixtures/calibration/parity-record-2026-08-02.json` — and each side asserts,
// in its own language and its own runner, that it reproduces that record from
// the shared payload.
//
//   - THIS file is web's assertion. It calls `buildCalibrationParity`, the
//     PRODUCTION function `app/calibration/page.tsx` renders and publishes from.
//   - `ios/Bain Luck/BainLuckTests/CalibrationParityTests.swift` is native's.
//   - `e2e/contract/calibrationSurfaceParity.contract.test.js` recomputes the
//     record from the payload with its own independent arithmetic and checks
//     that both clients are still bound to it.
//
// Neither client can drift without going red, and re-baselining the record to
// match a drifted client turns the OTHER client red. That is the property the
// old gate lacked.
//
// This file lives in jest rather than in the `node --test` contract dir for one
// reason: it imports TypeScript. `npm run test:ci` is a deploy gate, so it is
// not a weaker home — it is the only home from which web's real code is
// callable.

import * as fs from "fs";
import * as path from "path";

import { decideCalibrationContract } from "@/lib/calibrationContract";
import {
  buildCalibrationParity,
  parityReconciles,
  parityValue,
  CalibrationParity,
} from "@/lib/calibrationParity";
import { PROD_PAYLOAD, SHARED_FIXTURE_DIR } from "./calibrationProdFixture";

interface RecordCohort {
  key: string;
  include_never_moved: boolean;
  n: number;
  ece: number;
  mce: number;
  brier: number;
}

interface ParityRecord {
  payload_fixture: string;
  surface: {
    population_version: string;
    contract_state: string;
    cache_status: string;
    generated_at: string;
    markets: number;
    full_n: number;
    moved_n: number;
    unchanged_n: number;
    not_applicable_n: number;
    reconciles: boolean;
  };
  cohorts: RecordCohort[];
}

const RECORD_PATH = path.join(SHARED_FIXTURE_DIR, "parity-record-2026-08-02.json");
const RECORD: ParityRecord = JSON.parse(fs.readFileSync(RECORD_PATH, "utf8"));

/** ECE/MCE/Brier are floating point crossing a language boundary. */
const FP_TOLERANCE = 1e-6;

function webParity(includeNeverMoved: boolean): CalibrationParity {
  // The contract state is DECIDED by the real module, not asserted here. If
  // `decideCalibrationContract` ever judged this payload differently, the record
  // comparison below must notice — passing a literal would hide exactly that.
  const contract = decideCalibrationContract(PROD_PAYLOAD);
  return buildCalibrationParity(PROD_PAYLOAD, includeNeverMoved, contract.state);
}

describe("the parity record is the artifact both surfaces are graded on", () => {
  test("it names the payload this suite actually loaded", () => {
    // A record pointing at a different payload would compare two unrelated
    // things and pass, which is a subtler version of the bug being fixed.
    expect(RECORD.payload_fixture).toBe("prod-2026-08-02.json");
    expect(fs.existsSync(path.join(SHARED_FIXTURE_DIR, RECORD.payload_fixture))).toBe(true);
  });

  test("it covers BOTH cohort-toggle states, and they are genuinely different", () => {
    // C236 asked for both states by name. The second half of this assertion is
    // the one that matters: if the toggle made no difference to the figures, a
    // surface that ignored the toggle entirely would pass both checks.
    expect(RECORD.cohorts.map(c => c.key)).toEqual(["default", "include_never_moved"]);
    expect(RECORD.cohorts.map(c => c.include_never_moved)).toEqual([false, true]);

    const [def, all] = RECORD.cohorts;
    expect(def.n).not.toBe(all.n);
    expect(def.ece).not.toBeCloseTo(all.ece, 3);
    expect(def.brier).not.toBeCloseTo(all.brier, 5);
  });

  test("the default cohort is moved + not-applicable, never the whole population", () => {
    const def = RECORD.cohorts[0];
    expect(def.n).toBe(RECORD.surface.moved_n + RECORD.surface.not_applicable_n);
    expect(def.n).not.toBe(RECORD.surface.full_n);
  });

  test("the activity partition reconciles to the full population", () => {
    const s = RECORD.surface;
    expect(s.moved_n + s.unchanged_n + s.not_applicable_n).toBe(s.full_n);
    expect(s.full_n).toBe(PROD_PAYLOAD.total_outcomes);
    expect(s.reconciles).toBe(true);
  });
});

describe("web reproduces the parity record from the shared payload", () => {
  test.each(RECORD.cohorts.map(c => [c.key, c] as const))(
    "cohort %s",
    (_key, expected) => {
      const p = webParity(expected.include_never_moved);
      const s = RECORD.surface;

      // Toggle-independent facts about the payload and this build's judgement
      // of it. Native publishes every one of these under the same name.
      expect(p.populationVersion).toBe(s.population_version);
      expect(p.contractState).toBe(s.contract_state);
      expect(p.cacheStatus).toBe(s.cache_status);
      expect(p.generatedAt).toBe(s.generated_at);
      expect(p.markets).toBe(s.markets);
      expect(p.fullN).toBe(s.full_n);
      expect(p.movedN).toBe(s.moved_n);
      expect(p.unchangedN).toBe(s.unchanged_n);
      expect(p.notApplicableN).toBe(s.not_applicable_n);
      expect(parityReconciles(p)).toBe(s.reconciles);

      // The figures that move with the toggle.
      expect(p.cohortN).toBe(expected.n);
      expect(p.ece).toBeCloseTo(expected.ece, 6);
      expect(p.mce).toBeCloseTo(expected.mce, 6);
      expect(p.brier).toBeCloseTo(expected.brier, 6);

      expect(Math.abs(p.ece - expected.ece)).toBeLessThan(FP_TOLERANCE);
    },
  );

  test("the published record is the RENDERED record, not a second derivation", () => {
    // Ruling 003 — clients format, never adjudicate. The page passes exactly
    // this value to `data-parity`, so a figure that disagreed with the screen
    // could not be published without the screen changing too.
    const p = webParity(false);
    const value = parityValue(p);

    const pairs = Object.fromEntries(
      value.split(" ").map(kv => {
        const i = kv.indexOf("=");
        return [kv.slice(0, i), kv.slice(i + 1)];
      }),
    );

    expect(pairs.population).toBe(RECORD.surface.population_version);
    expect(pairs.contract).toBe(RECORD.surface.contract_state);
    expect(pairs.cache).toBe(RECORD.surface.cache_status);
    expect(pairs.generated).toBe(RECORD.surface.generated_at);
    expect(Number(pairs.cohort_n)).toBe(RECORD.cohorts[0].n);
    expect(Number(pairs.full_n)).toBe(RECORD.surface.full_n);
    expect(Number(pairs.moved_n)).toBe(RECORD.surface.moved_n);
    expect(Number(pairs.unchanged_n)).toBe(RECORD.surface.unchanged_n);
    expect(Number(pairs.not_applicable_n)).toBe(RECORD.surface.not_applicable_n);
    expect(Number(pairs.markets)).toBe(RECORD.surface.markets);
    expect(pairs.reconciles).toBe("true");

    // Raw, not display-formatted. "1.5pp" here would mean the parity check
    // compares presentation across surfaces — which fails on a thousands
    // separator and passes on a wrong number (C236's second P1).
    expect(pairs.ece).toBe(RECORD.cohorts[0].ece.toFixed(4));
    expect(pairs.mce).toBe(RECORD.cohorts[0].mce.toFixed(4));
    expect(pairs.brier).toBe(RECORD.cohorts[0].brier.toFixed(4));
    expect(value).not.toMatch(/pp\b/);
    expect(value).not.toMatch(/,/);
  });

  test("the toggle moves the published record, not just the screen", () => {
    // The failure this catches: a surface that renders the toggle but publishes
    // the default cohort's numbers in both states. Both records would look
    // plausible; only the comparison between them shows the toggle is inert.
    const a = parityValue(webParity(false));
    const b = parityValue(webParity(true));
    expect(a).not.toBe(b);
    expect(b).toContain(`cohort_n=${RECORD.cohorts[1].n}`);
    expect(b).toContain(`ece=${RECORD.cohorts[1].ece.toFixed(4)}`);
  });
});

describe("the record is not self-fulfilling", () => {
  // Everything above compares web against the record. These compare the record
  // against the PAYLOAD, arithmetic that does not route through
  // `buildCalibrationParity` at all — so a bug shared by the record and the
  // production function still fails here.
  const rows = PROD_PAYLOAD.buckets;
  const sum = (pred: (b: typeof rows[number]) => boolean) =>
    rows.filter(pred).reduce((a, b) => a + b.n, 0);

  test("the counts are the payload's own counts", () => {
    expect(sum(() => true)).toBe(RECORD.surface.full_n);
    expect(sum(b => b.price_moved === true)).toBe(RECORD.surface.moved_n);
    expect(sum(b => b.price_moved === false)).toBe(RECORD.surface.unchanged_n);
    expect(sum(b => b.price_moved === null)).toBe(RECORD.surface.not_applicable_n);
    expect(RECORD.surface.markets).toBe(PROD_PAYLOAD.total_markets);
    expect(RECORD.surface.population_version).toBe(PROD_PAYLOAD.population_version);
    expect(RECORD.surface.cache_status).toBe(PROD_PAYLOAD.cache.status);
    expect(RECORD.surface.generated_at).toBe(PROD_PAYLOAD.cache.generated_at);
  });

  test("the brier scores are the payload's own sum_sq_err / n", () => {
    // Independent of the bucket aggregation entirely — Brier is a straight ratio
    // over the rows, so it can be checked without replicating any binning.
    for (const c of RECORD.cohorts) {
      const keep = (b: typeof rows[number]) => c.include_never_moved || b.price_moved !== false;
      const n = rows.filter(keep).reduce((a, b) => a + b.n, 0);
      const sq = rows.filter(keep).reduce((a, b) => a + b.sum_sq_err, 0);
      expect(sq / n).toBeCloseTo(c.brier, 6);
      expect(n).toBe(c.n);
    }
  });
});
