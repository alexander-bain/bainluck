// L2-232 Item 1 — the population-version decision table.
//
// `decideCalibrationContract` is the only thing standing between a payload built
// under one population and a page that describes a different one. Every branch
// of it is graded here, including the ones that must NOT refuse: over-refusing
// is not the safe direction, it is the second outage this module documents (a
// client-side constant blanking a page over perfectly good data).
//
// The fixtures are named after the queue's list — match, missing, malformed,
// previous-compatible, previous-incompatible, future, stale last-good, poison
// ordering — so a reader can check coverage against the brief without reading
// the assertions.

import {
  decideCalibrationContract,
  COMPATIBLE_POPULATION_VERSIONS,
  CONTRACT_REFUSAL_MESSAGE,
  type CalibrationContractInput,
} from "@/lib/calibrationContract";

/** The version this build is written against, taken from the list itself. */
const CURRENT = COMPATIBLE_POPULATION_VERSIONS[0];

/** A version that is well-formed and deliberately NOT in the compatible list. */
const UNKNOWN_PREVIOUS = "q262";
const UNKNOWN_FUTURE = "q400";

function payload(over: Partial<CalibrationContractInput> = {}): CalibrationContractInput {
  return { population_version: CURRENT, ...over };
}

const stale = (generatedAt: string | null = "2026-08-02T03:23:54.886392+00:00") => ({
  status: "stale",
  reason: "main_key_absent",
  ...(generatedAt === null ? {} : { generated_at: generatedAt }),
});

describe("the compatible set itself", () => {
  test("is non-empty, unique, and holds only well-formed tokens", () => {
    // An empty list would refuse EVERY payload and take the page dark on a
    // typo — the exact class of failure this module exists to prevent, so it is
    // asserted rather than assumed.
    expect(COMPATIBLE_POPULATION_VERSIONS.length).toBeGreaterThan(0);
    expect(new Set(COMPATIBLE_POPULATION_VERSIONS).size).toBe(
      COMPATIBLE_POPULATION_VERSIONS.length,
    );
    for (const v of COMPATIBLE_POPULATION_VERSIONS) {
      expect(typeof v).toBe("string");
      expect(v.trim()).toBe(v);
      expect(v).not.toBe("");
    }
  });
});

describe("match — the served version is one this build can label", () => {
  test("renders, and says why", () => {
    const d = decideCalibrationContract(payload());
    expect(d.state).toBe("match");
    expect(d.render).toBe(true);
    expect(d.servedVersion).toBe(CURRENT);
    expect(d.degraded).toBe(false);
  });

  test("every listed version is accepted, not just the first", () => {
    // "previous-compatible": a version kept in the list precisely so a server
    // roll-BACK between listed versions is a non-event. If only the newest
    // entry rendered, the list would be decoration.
    for (const v of COMPATIBLE_POPULATION_VERSIONS) {
      const d = decideCalibrationContract(payload({ population_version: v }));
      expect([v, d.state]).toEqual([v, "match"]);
      expect(d.render).toBe(true);
    }
  });

  test("surrounding whitespace is tolerated, not treated as a break", () => {
    const d = decideCalibrationContract(payload({ population_version: `  ${CURRENT}\n` }));
    expect(d.state).toBe("match");
    expect(d.servedVersion).toBe(CURRENT);
  });

  test("membership is exact — a version that merely contains a listed one is refused", () => {
    for (const near of [`${CURRENT}x`, `x${CURRENT}`, `${CURRENT}-rc1`, CURRENT.toUpperCase()]) {
      const d = decideCalibrationContract(payload({ population_version: near }));
      expect([near, d.state]).toEqual([near, "incompatible"]);
    }
  });
});

describe("missing — the payload names no population at all", () => {
  // Rendered, never claimed as verified. Refusing here would hand any older
  // cached copy the power to blank the page, and would diverge from native's
  // `.unverified` (L2-231).
  // Built WITHOUT the `payload()` helper on purpose: the helper seeds a valid
  // default, so an "absent" row written as `{}` would silently test the happy
  // path instead. These are the literal payloads.
  test.each([
    ["absent — the key is not in the object at all", {}],
    ["explicit null", { population_version: null }],
    ["explicit undefined", { population_version: undefined }],
    ["empty string", { population_version: "" }],
    ["whitespace only", { population_version: "   " }],
  ])("%s renders as unverified", (_name, input) => {
    const d = decideCalibrationContract(input as CalibrationContractInput);
    expect(d.state).toBe("unverified");
    expect(d.render).toBe(true);
    // It rendered, but it must not claim a version it never received.
    expect(d.servedVersion).toBe("");
  });

  test("a null payload does not throw — it decides", () => {
    // The caller is a render path. An exception here is the blank page.
    for (const bad of [null, undefined]) {
      const d = decideCalibrationContract(bad);
      expect(d.state).toBe("unverified");
      expect(d.render).toBe(true);
    }
  });
});

describe("malformed — something is there, and it is not a version", () => {
  test.each([
    ["a number", 299],
    ["zero", 0],
    ["a boolean", true],
    ["an object", { version: "q267" }],
    ["an array", ["q267"]],
  ])("%s refuses", (_name, raw) => {
    const d = decideCalibrationContract(payload({ population_version: raw }));
    expect(d.state).toBe("malformed");
    expect(d.render).toBe(false);
  });

  test.each([
    ["a sentence", "the population version is q267"],
    ["a token that is far too long", "q".repeat(64)],
    ["a leading separator", "-q267"],
    ["path traversal", "../../etc/passwd"],
    ["an HTML fragment", "<script>alert(1)</script>"],
  ])("%s refuses without adopting the value as a version", (_name, raw) => {
    const d = decideCalibrationContract(payload({ population_version: raw }));
    expect(d.state).toBe("malformed");
    expect(d.render).toBe(false);
  });

  test("malformed is graded apart from unknown, so the rail can tell them apart", () => {
    // Both refuse and both show the reader the same sentence — the distinction
    // is diagnostic, and it only exists if it survives into the decision.
    expect(decideCalibrationContract(payload({ population_version: 299 })).state).toBe(
      "malformed",
    );
    expect(
      decideCalibrationContract(payload({ population_version: UNKNOWN_FUTURE })).state,
    ).toBe("incompatible");
  });
});

describe("incompatible — a real version this build cannot label", () => {
  test("previous-incompatible: an older population that was dropped from the list", () => {
    const d = decideCalibrationContract(payload({ population_version: UNKNOWN_PREVIOUS }));
    expect(d.state).toBe("incompatible");
    expect(d.render).toBe(false);
    // The served value is retained as evidence even though we refuse it — the
    // rail grades the exact mismatch, and a refusal that cannot say what it
    // refused is not diagnosable.
    expect(d.servedVersion).toBe(UNKNOWN_PREVIOUS);
  });

  test("future: a population newer than anything this build knows", () => {
    const d = decideCalibrationContract(payload({ population_version: UNKNOWN_FUTURE }));
    expect(d.state).toBe("incompatible");
    expect(d.render).toBe(false);
    expect(d.servedVersion).toBe(UNKNOWN_FUTURE);
  });

  test("future is NOT quietly treated as safe", () => {
    // Optimistically rendering anything newer is how "current labels on an
    // incompatible artifact" happens — the failure this queue exists to close.
    expect(decideCalibrationContract(payload({ population_version: "q999" })).render).toBe(
      false,
    );
  });
});

describe("stale last-good — degradation is the server's call", () => {
  test("a dated stale copy renders WITH the dated banner", () => {
    const d = decideCalibrationContract(payload({ cache: stale() }));
    expect(d.render).toBe(true);
    expect(d.degraded).toBe(true);
    expect(d.degradedDated).toBe(true);
  });

  test("an undated stale copy still banners, but cannot claim a date", () => {
    const d = decideCalibrationContract(payload({ cache: stale(null) }));
    expect(d.degraded).toBe(true);
    expect(d.degradedDated).toBe(false);
  });

  test("a blank generated_at is not a date", () => {
    const d = decideCalibrationContract(payload({ cache: stale("   ") }));
    expect(d.degraded).toBe(true);
    expect(d.degradedDated).toBe(false);
  });

  test.each([
    ["fresh (no cache block)", undefined],
    ["explicit null cache", null],
    ["a non-stale status", { status: "fresh" }],
    ["a status of the wrong type", { status: 1 }],
  ])("%s is NOT degraded — the banner is never inferred", (_name, cache) => {
    const d = decideCalibrationContract(
      payload({ cache: cache as CalibrationContractInput["cache"] }),
    );
    expect(d.degraded).toBe(false);
    expect(d.degradedDated).toBe(false);
  });
});

describe("poison ordering — which check wins when several apply at once", () => {
  test("a stale AND incompatible payload REFUSES; it does not render with a caveat", () => {
    // The dangerous shape. Reading `cache.status` first renders the curve with
    // a mild "here's an older snapshot" frame around numbers built under rules
    // this build cannot describe — a major refusal downgraded to a minor note.
    const d = decideCalibrationContract(
      payload({ population_version: UNKNOWN_PREVIOUS, cache: stale() }),
    );
    expect(d.state).toBe("incompatible");
    expect(d.render).toBe(false);
    expect(d.degraded).toBe(false);
    expect(d.degradedDated).toBe(false);
  });

  test("a stale AND malformed payload refuses the same way", () => {
    const d = decideCalibrationContract(
      payload({ population_version: { v: 1 }, cache: stale() }),
    );
    expect(d.render).toBe(false);
    expect(d.degraded).toBe(false);
  });

  test("`degraded` is never true while `render` is false — an invariant, not a coincidence", () => {
    const versions: unknown[] = [
      CURRENT, UNKNOWN_PREVIOUS, UNKNOWN_FUTURE, "", null, undefined, 42, {}, [], "x".repeat(99),
    ];
    const caches = [undefined, null, stale(), stale(null), { status: "fresh" }];
    for (const v of versions) {
      for (const c of caches) {
        const d = decideCalibrationContract({
          population_version: v,
          cache: c as CalibrationContractInput["cache"],
        });
        if (!d.render) {
          expect([v, c, d.degraded]).toEqual([v, c, false]);
        }
        // And the weaker direction: a dated flag never outlives its banner.
        if (!d.degraded) expect(d.degradedDated).toBe(false);
      }
    }
  });

  test("a stale, unverified payload renders AND banners", () => {
    // The combination that must NOT be swept up by the refusal: no version
    // claimed, server says dated. Both facts are honest and both are kept.
    const d = decideCalibrationContract({ cache: stale() });
    expect(d.state).toBe("unverified");
    expect(d.render).toBe(true);
    expect(d.degraded).toBe(true);
  });
});

describe("the refusal copy", () => {
  test("names no version — a bare token is jargon to every reader outside this repo", () => {
    expect(CONTRACT_REFUSAL_MESSAGE).not.toMatch(/\bq\d{2,}\b/i);
    expect(CONTRACT_REFUSAL_MESSAGE).not.toMatch(/population_version|population version/i);
  });

  test("does not invite a retry that cannot succeed", () => {
    // Retrying the same build against the same payload reproduces the same
    // refusal. Recovery is a republish or a redeploy.
    expect(CONTRACT_REFUSAL_MESSAGE).not.toMatch(/try again|retry|reload|refresh the page/i);
  });

  test("tells the reader what happens next", () => {
    expect(CONTRACT_REFUSAL_MESSAGE).toMatch(/automatically|check back/i);
  });
});
