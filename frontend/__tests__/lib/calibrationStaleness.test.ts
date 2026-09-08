/**
 * #2007 item 1b (Fable ruling (c), CAL-P077) — the banner reads what
 * `availability` discloses, and says the true sentence for each state.
 *
 * The two defects under test, both measured on the deployed payload:
 *
 *   1. A payload the server declared `availability: "stale"` rendered NO banner,
 *      because the page's only degradation authority was `cache.status`, which
 *      the main serve path never sets. The disclosure existed in the JSON and
 *      nowhere a reader could see it.
 *   2. Had it rendered, it would have said "not being refreshed right now" — a
 *      true sentence about a dated last-good and a false one about a frozen
 *      input bank, whose curve is rebuilt on time every hour.
 */

import {
  decideCalibrationStaleness,
  stalenessDriftClause,
  stalenessHeadline,
} from "@/lib/calibrationStaleness";

/** The measured 2026-08-19 shape: complete bank, frozen, drifting underneath. */
const FROZEN_BANK = {
  availability: "stale",
  staged: {
    measured: true,
    staged_at: "2026-08-19T17:16:31+00:00",
    staged_age_s: 21_642,
    units_banked: 128,
    units_this_beat: 0,
    units_drifted: 115,
    units_drift_checkable: 127,
    units_drift_unknown: 1,
    units_drifted_as_of: "2026-08-19T17:16:31+00:00",
    bank_advanced_this_beat: false,
    frozen_over_drift: true,
  },
};

describe("decideCalibrationStaleness", () => {
  it("says nothing about a healthy payload", () => {
    expect(
      decideCalibrationStaleness({ availability: "fresh", staged: { measured: true } }),
    ).toBeNull();
  });

  it("is total: null, undefined and junk all produce an answer, never a throw", () => {
    expect(decideCalibrationStaleness(null)).toBeNull();
    expect(decideCalibrationStaleness(undefined)).toBeNull();
    expect(decideCalibrationStaleness({ availability: 7 as unknown })).toBeNull();
    expect(
      decideCalibrationStaleness({ availability: "stale", staged: "nope" as never }),
    ).toMatchObject({ kind: "undisclosed" });
  });

  describe("the defect: a not-fresh payload with no cache block", () => {
    it("banners, where the old cache-only gate showed nothing", () => {
      const notice = decideCalibrationStaleness(FROZEN_BANK);
      expect(notice).not.toBeNull();
      expect(notice!.kind).toBe("frozen-inputs");
    });

    it("carries the input as-of and the drift, not the publish time", () => {
      const notice = decideCalibrationStaleness(FROZEN_BANK)!;
      expect(notice.stagedAt).toBe("2026-08-19T17:16:31+00:00");
      expect(notice.stagedAgeS).toBe(21_642);
      expect(notice.unitsDrifted).toBe(115);
      expect(notice.unitsBanked).toBe(128);
      // No `cache` block on this path, so there is no artifact date to publish.
      // Absent, not invented.
      expect(notice.generatedAt).toBeNull();
      expect(notice.ageS).toBeNull();
    });

    it("does not say the false thing", () => {
      expect(stalenessHeadline(decideCalibrationStaleness(FROZEN_BANK)!)).not.toMatch(
        /not being refreshed/i,
      );
    });
  });

  describe("the states are distinguished, not merged", () => {
    it("a dated last-good is last-good even when it also has a staged block", () => {
      // Precedence, deliberately this way round: the whole artifact being old
      // and unreplaced SUBSUMES its inputs being old. Leading with the
      // frozen-inputs sentence would tell a reader the curve is refreshing
      // while the server is explicitly serving a copy that is not.
      const notice = decideCalibrationStaleness({
        ...FROZEN_BANK,
        cache: { status: "stale", reason: "redis_unavailable", generated_at: "2026-08-19T02:00:00Z", age_s: 7200 },
      })!;
      expect(notice.kind).toBe("last-good");
      expect(notice.reason).toBe("redis_unavailable");
      // and it still carries the staged facts for the rail
      expect(notice.stagedAt).toBe("2026-08-19T17:16:31+00:00");
    });

    it("an unreadable staged block is `undisclosed`, never a clean bill", () => {
      const notice = decideCalibrationStaleness({
        availability: "stale",
        staged: { measured: false, reason: "phase_ledger_unreadable: expired" },
      })!;
      expect(notice.kind).toBe("undisclosed");
      expect(notice.reason).toBe("phase_ledger_unreadable: expired");
      expect(notice.unitsDrifted).toBeNull();
    });

    it("a not-fresh payload with a HEALTHY bank is still disclosed", () => {
      // e.g. `producer.stalled` clamped it. The staged block cannot explain the
      // downgrade, and inventing an explanation is worse than saying so.
      const notice = decideCalibrationStaleness({
        availability: "stale",
        staged: { measured: true, staged_at: "2026-08-20T00:00:00Z", units_banked: 128, units_this_beat: 9, units_drifted: 0, units_drift_unknown: 0, frozen_over_drift: false },
      })!;
      expect(notice.kind).toBe("undisclosed");
    });
  });

  /**
   * #4046 — a fallback TIER answering is not a claim about the artifact's AGE.
   *
   * Measured on production 2026-09-08. Publishing had just been repaired
   * (#3893) and the curve was republishing hourly, on time — and the page told
   * every reader, over a seven-minute-old artifact, that these numbers "are not
   * being refreshed right now". `cache.status === "stale"` was doing double
   * duty: it is set by whichever fallback tier answers, and `main` (2h TTL) is
   * evicted ahead of `last_good` (7d) on a 50MB `allkeys-lru` instance, so a
   * durable serve is documented steady state rather than an incident.
   *
   * The guard is the CLASS, not the string: a serving-tier signal may not be
   * read as a statement about content age when the payload separately measures
   * that age. Hence the pair — the current artifact loses the sentence, and
   * every case where health is not positively proven keeps it.
   */
  describe("#4046: a fallback tier serving a CURRENT artifact", () => {
    /** The 19:42Z production payload, verbatim in the fields that decide. */
    const DURABLE_BUT_CURRENT = {
      ...FROZEN_BANK,
      cache: {
        status: "stale",
        reason: "main_key_absent_durable",
        generated_at: "2026-09-08T19:16:16.079814+00:00",
        age_s: 1563,
      },
      producer: { stalled: false, beats_missed: 0 },
    };

    it("does not tell a reader the curve is not being refreshed", () => {
      const notice = decideCalibrationStaleness(DURABLE_BUT_CURRENT)!;
      expect(notice.kind).not.toBe("last-good");
      expect(stalenessHeadline(notice)).not.toMatch(/not being refreshed|last complete snapshot/i);
    });

    it("falls through to what the payload actually discloses", () => {
      // The bank really is frozen over drift, so that — not the storage tier —
      // is the honest subject of the banner.
      expect(decideCalibrationStaleness(DURABLE_BUT_CURRENT)!.kind).toBe("frozen-inputs");
    });

    it("says nothing at all when a current fallback serve has nothing to disclose", () => {
      // No envelope, no frozen bank, beat landing. The reader is looking at
      // current numbers; which Redis key they came out of is not their problem.
      expect(
        decideCalibrationStaleness({
          cache: { status: "stale", reason: "main_key_absent_durable", age_s: 300 },
          producer: { stalled: false, beats_missed: 0 },
        }),
      ).toBeNull();
    });

    it("still reads a genuinely dated copy as last-good", () => {
      // The three-day outage this banner was RIGHT about. `beats_missed` is the
      // difference, and it must keep making it.
      const notice = decideCalibrationStaleness({
        ...FROZEN_BANK,
        cache: { status: "stale", reason: "main_key_absent_durable", age_s: 264_000 },
        producer: { stalled: true, beats_missed: 73 },
      })!;
      expect(notice.kind).toBe("last-good");
      expect(notice.beatsMissed).toBe(73);
    });

    it.each([
      ["no producer block at all (an older payload)", undefined],
      ["a stalled beat", { stalled: true, beats_missed: 5 }],
      ["one missed beat — health is not 'nearly current'", { stalled: false, beats_missed: 1 }],
      ["an unknown artifact age, which the server publishes as stalled", { stalled: true, beats_missed: null }],
      ["a beat count the payload could not state", { stalled: false, beats_missed: null }],
      ["a non-boolean `stalled`", { stalled: "false" as unknown, beats_missed: 0 }],
      ["a non-finite beat count", { stalled: false, beats_missed: Number.NaN }],
    ])("fails closed to last-good on %s", (_label, producer) => {
      // Gotcha #53, and the whole reason the downgrade is a POSITIVE proof of
      // health: an unreadable producer must never become the one input that
      // talks the banner out of a warning.
      const notice = decideCalibrationStaleness({
        ...FROZEN_BANK,
        cache: { status: "stale", reason: "main_key_absent_durable", age_s: 1563 },
        ...(producer === undefined ? {} : { producer }),
      })!;
      expect(notice.kind).toBe("last-good");
    });
  });

  describe("absence is never the reassuring reading", () => {
    it("a payload with no `availability` falls back to cache.status, not to fresh", () => {
      // An older cached artifact predates the envelope. It is not broken and it
      // is not fresh — it simply carries no claim, and the pre-#2007 authority
      // is the only one left.
      expect(decideCalibrationStaleness({ staged: null })).toBeNull();
      expect(
        decideCalibrationStaleness({ cache: { status: "stale", generated_at: "x" } })!.kind,
      ).toBe("last-good");
    });

    it("a missing drift count is unknown, not zero", () => {
      const notice = decideCalibrationStaleness({
        availability: "stale",
        staged: { measured: true, staged_at: "2026-08-20T00:00:00Z", frozen_over_drift: true },
      })!;
      expect(notice.unitsDrifted).toBeNull();
      expect(stalenessDriftClause(notice)).toMatch(/unknown number/);
    });

    it("rejects a non-finite count rather than rendering NaN at a reader", () => {
      const notice = decideCalibrationStaleness({
        availability: "stale",
        staged: {
          measured: true,
          staged_at: "2026-08-20T00:00:00Z",
          frozen_over_drift: true,
          units_drifted: Number.NaN,
          units_banked: Number.POSITIVE_INFINITY,
        },
      })!;
      expect(notice.unitsDrifted).toBeNull();
      expect(notice.unitsBanked).toBeNull();
    });
  });
});

describe("stalenessDriftClause", () => {
  const notice = (staged: Record<string, unknown>) =>
    decideCalibrationStaleness({ availability: "stale", staged: { measured: true, staged_at: "2026-08-20T00:00:00Z", frozen_over_drift: true, ...staged } })!;

  it("reads the measured case in a person's words", () => {
    expect(stalenessDriftClause(notice({ units_drifted: 115, units_banked: 128, units_drift_unknown: 0 }))).toBe(
      "115 of 128 units have drifted since",
    );
  });

  it("names the unmeasurable remainder rather than folding it in", () => {
    // CAL-P069's find: six unmeasurable units published as `units_drifted: 0`.
    // A partial count presented as a whole one is that failure with extra steps.
    expect(stalenessDriftClause(notice({ units_drifted: 115, units_banked: 128, units_drift_unknown: 6 }))).toContain(
      "(6 more couldn't be checked)",
    );
  });

  it("says nothing when there is nothing honest to say", () => {
    const clean = decideCalibrationStaleness({
      availability: "stale",
      staged: { measured: false, reason: "staged_cursor_unreadable: expired" },
    })!;
    expect(stalenessDriftClause(clean)).toBeNull();
  });

  it("agrees with itself on singular and plural", () => {
    expect(stalenessDriftClause(notice({ units_drifted: 1, units_banked: 128 }))).toContain("1 of 128 unit has drifted");
  });

  it("reports zero drift as zero, not as silence", () => {
    // A measured zero is a real disclosure and must survive: it is the
    // difference between "we checked and nothing moved" and "we did not check".
    // `frozen_over_drift` can still be true with 0 drifted when units are
    // unknown, which is exactly the case worth printing.
    expect(stalenessDriftClause(notice({ units_drifted: 0, units_banked: 128, units_drift_unknown: 4 }))).toBe(
      "0 of 128 units have drifted since (4 more couldn't be checked)",
    );
  });
});

describe("stalenessHeadline", () => {
  it("gives each state its own sentence", () => {
    const kinds = ["last-good", "frozen-inputs", "undisclosed"] as const;
    const lines = kinds.map(kind =>
      stalenessHeadline({
        kind,
        reason: "",
        generatedAt: null,
        ageS: null,
        stagedAt: null,
        stagedAgeS: null,
        unitsDrifted: null,
        unitsDriftUnknown: null,
        unitsBanked: null,
        producerStalled: null,
        beatsMissed: null,
      }),
    );
    expect(new Set(lines).size).toBe(3);
    expect(lines.every(l => l.trim().length > 0)).toBe(true);
  });
});
