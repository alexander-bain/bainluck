/**
 * THE DISCOVER CARD-ADMISSION RULE, ASSERTED ACROSS ALL THREE SURFACES.
 *
 * `contracts/feed_card_admission.json` is the rule. This file drives web through
 * every row of it, source-asserts native against the same arms, source-asserts
 * the Python mirror, and — new in #1951 — enforces the REGISTRY, so a fourth
 * implementation cannot appear without being declared.
 *
 * ── the history this file is made of ─────────────────────────────────────────
 *
 * #1939: the backend served a concept `leader` and iOS admitted on it while web's
 * predicate still required `marquee_whathit`. Measured on production `5542f8c4`:
 * 7 of 50 cards were concepts, every one carrying a real leader — Pogačar 0.751
 * of a 30-rider field, Joshua Van 0.5217, Anthony Hernandez 0.635. Web dropped
 * all seven. 14% of the landing page, withheld by one surface and printed by the
 * other, for a week. This file was created to connect the two.
 *
 * #1951: it turned out there was a THIRD copy the file did not know about —
 * `feed_item_is_renderable` in the Flow Sentinel, shipped in UX-P092, carrying
 * the pre-#1935 reading on two arms. It feeds the dark-class limb, which IS the
 * #1935-family detector, so a predicate more permissive than the clients made the
 * family it hunts invisible: seven golferless-whathit tournaments, 100% dark on
 * both surfaces, scored `7 built, 7 renderable`. A PASS over a dark tier.
 *
 * ── why cycle 90's fix was not enough, which is the point of this revision ────
 *
 * Cycle 90 corrected the third copy's arms and pinned them with a second matrix,
 * written here in TypeScript and again in Python. That fixed the instance and
 * left the mechanism: two matrices a reader must diff by eye. Ruling 021 already
 * settled this — *when two consumers must agree about the same input, the unit to
 * share is the DECISION, not the ingredient; a shared predicate under two
 * policies is still two policies.* Three implementations that merely AGREE are
 * three policies. So the matrices are gone and the table is the decision.
 *
 * ── what this can and cannot guarantee, stated so nobody over-reads it ───────
 *
 * CAN: every non-test implementation of the rule is enumerated (`registry`); each
 * one that can execute is driven through every row; every card type a producer
 * emits is pinned in BOTH directions; every emitted type is declared, so a new
 * card type cannot ship with no arms — that last one is #1935 restated as a build
 * error.
 *
 * CANNOT: catch a new PERMISSIVE arm for which no row exists. A rule is only
 * tested against stated cases, and that is inherent rather than an oversight —
 * which is why the contract's header says to add rows FIRST and watch all three
 * suites go red.
 *
 * Native and Python are asserted against SOURCE for the reason
 * `periodLabelSingleSource.test.ts` gives: jest is a deploy gate here and neither
 * the Swift target nor pytest is reachable from it. That buys less than executing
 * all three, and it is what is available — a source assertion that runs on every
 * push beats an execution assertion that runs on someone's laptop. The
 * behavioural half for Python lives in
 * `backend/tests/test_flow_sentinel_admission_parity.py`, which executes the same
 * rows.
 */

import { readFileSync, existsSync, readdirSync, statSync } from "fs";
import { join } from "path";
import type { FeedItem } from "@/lib/types";
import { feedItemSuppressionReason } from "@/components/discover/utils";

const REPO_ROOT = join(__dirname, "../../..");
const CONTRACT_PATH = join(REPO_ROOT, "contracts/feed_card_admission.json");

// A path typo must not read as a clean pass — an unrunnable check and a passing
// check are indistinguishable from the outside (gotcha #54's cousin).
if (!existsSync(CONTRACT_PATH)) {
  throw new Error(`the shared decision is missing: ${CONTRACT_PATH}`);
}

type Row = {
  id: string;
  why: string;
  item: unknown;
  expected_reason?: string | null;
  malformed_envelope?: boolean;
  expected_suppressed?: boolean;
};

type Contract = {
  now: string;
  emitted_types: string[];
  unconditional_types: string[];
  producers: { path: string; emits: string[] }[];
  implementations: {
    id: string;
    path: string;
    symbol: string;
    executes_table: boolean;
    driven_by: string;
  }[];
  consumers: { path: string }[];
  not_this_rule: { path: string }[];
  cases: Row[];
};

const CONTRACT: Contract = JSON.parse(readFileSync(CONTRACT_PATH, "utf8"));
const NOW = new Date(CONTRACT.now).getTime();

const wellFormed = CONTRACT.cases.filter((c) => !c.malformed_envelope);
const malformed = CONTRACT.cases.filter((c) => c.malformed_envelope);

describe("web is driven by the shared decision", () => {
  it.each(wellFormed.map((c) => [c.id, c] as const))("%s", (_id, c) => {
    expect(feedItemSuppressionReason(c.item as FeedItem, NOW)).toBe(c.expected_reason);
  });

  // Malformed ENVELOPES carry a verdict but not a shared reason string: native
  // never sees one, because its decoder rejects the payload before the predicate
  // runs. What all three owe is falling closed.
  it.each(malformed.map((c) => [c.id, c] as const))("%s — falls closed", (_id, c) => {
    const reason = feedItemSuppressionReason(c.item as FeedItem, NOW);
    expect(reason).not.toBeNull();
    expect(Boolean(c.expected_suppressed)).toBe(true);
  });

  // Web-specific, and the reason it is here rather than in the table: until
  // #1951 web THREW on two of those shapes instead of returning anything, inside
  // a render-path `.filter()` — which blanks the main region rather than dropping
  // a card (#1909's failure mode). This pins that the guard exists AND that it
  // reports the malformed envelope honestly instead of borrowing an `empty_*`
  // code from a card whose envelope never arrived.
  it("names a malformed envelope rather than mislabelling it as empty", () => {
    expect(feedItemSuppressionReason({ type: "concept" } as unknown as FeedItem, NOW)).toBe(
      "malformed_envelope",
    );
    expect(
      feedItemSuppressionReason({ type: "futures", data: null } as unknown as FeedItem, NOW),
    ).toBe("malformed_envelope");
    // Even the unconditional arm. `case "event": return null` sat in front of any
    // envelope check and admitted a card with nothing behind it.
    expect(feedItemSuppressionReason({ type: "event" } as unknown as FeedItem, NOW)).toBe(
      "malformed_envelope",
    );
  });
});

describe("the table is worth answering to", () => {
  // A table can only ratchet what it covers, so its coverage is asserted too.
  // Without this the fold degrades quietly into what it replaced.
  it.each(CONTRACT.emitted_types)("%s is pinned in both directions", (cardType) => {
    const rows = CONTRACT.cases.filter(
      (c) =>
        typeof c.item === "object" &&
        c.item !== null &&
        (c.item as { type?: string }).type === cardType,
    );
    const verdicts = new Set(
      rows.filter((c) => !c.malformed_envelope).map((c) => c.expected_reason === null),
    );
    if (CONTRACT.unconditional_types.includes(cardType)) {
      expect([...verdicts]).toEqual([true]);
      expect(rows.some((c) => c.malformed_envelope)).toBe(true);
      return;
    }
    expect([...verdicts].sort()).toEqual([false, true]);
  });

  it("every executable implementation is actually wired to the table", () => {
    // The wiring assertion. An implementation declared `executes_table` whose
    // suite does not read the contract is a declaration, not a link.
    for (const impl of CONTRACT.implementations) {
      if (!impl.executes_table) continue;
      const suite = join(REPO_ROOT, impl.driven_by);
      expect(existsSync(suite)).toBe(true);
      expect(readFileSync(suite, "utf8")).toContain("feed_card_admission.json");
    }
  });

  it("the producers emit exactly the declared types", () => {
    // The guard that makes a NEW card type impossible to ship dark: a type the
    // server can build and the table does not name is `unknown_type` on web and
    // false in the sentinel — dark on arrival, and silent, because no limb can
    // report a class nobody enumerated.
    const found = new Set<string>();
    for (const producer of CONTRACT.producers) {
      const src = readFileSync(join(REPO_ROOT, producer.path), "utf8");
      const emitted = new Set(
        [...src.matchAll(/"type": *"([a-z_]+)"/g)].map((m) => m[1]),
      );
      expect([...emitted].sort()).toEqual([...producer.emits].sort());
      emitted.forEach((t) => found.add(t));
    }
    expect([...found].sort()).toEqual([...CONTRACT.emitted_types].sort());
  });
});

/**
 * THE REGISTRY — #1951's structural half.
 *
 * `feed_item_is_renderable` existed for three cycles as an undeclared third copy.
 * Nothing was capable of noticing, because "how many implementations does this
 * rule have" was not a question anything asked. This asks it on every push.
 *
 * The fingerprint was MEASURED rather than guessed, and two earlier candidates
 * were discarded on the measurement: a suppression-reason-code scan misses the
 * Python copy entirely (it returns a bool and emits no codes), and a
 * card-type-literal scan misses the Swift copy (it branches on `item.futures`,
 * never on the string `"futures"`). The union below — a declaration whose NAME is
 * about suppression/renderability, in a file carrying ≥3 terms of the admission
 * vocabulary — catches all three, and catches five adjacent files besides, each
 * of which is declared with a reason. Eight declarations is the price of the
 * question being asked at all.
 */
describe("registry — a fourth copy cannot appear undeclared", () => {
  const SKIP = ["node_modules", ".next", ".git", "DerivedData", "build", "artifacts"];
  const EXT = [".py", ".ts", ".tsx", ".swift"];
  const VOCAB = [
    '"event"',
    "'event'",
    '"futures"',
    "'futures'",
    '"tournament"',
    "'tournament'",
    '"concept"',
    "'concept'",
    '"bundle"',
    "'bundle'",
    "empty_futures",
    "empty_tournament",
    "empty_concept",
    "empty_bundle",
    "unknown_type",
  ];
  const DECL = /(?:def|func|function|const|let|var|static func)\s+([A-Za-z_][A-Za-z0-9_]*)/g;
  const NAME = /suppress|renderable|admissib|admission/i;

  function isTest(path: string): boolean {
    const base = path.split("/").pop() ?? "";
    return (
      /test/i.test(base) ||
      path.includes("__tests__") ||
      path.includes("/tests/") ||
      path.includes("Tests/")
    );
  }

  function walk(dir: string, out: string[] = []): string[] {
    for (const entry of readdirSync(dir)) {
      if (SKIP.includes(entry)) continue;
      const full = join(dir, entry);
      let st;
      try {
        st = statSync(full);
      } catch {
        continue;
      }
      if (st.isDirectory()) walk(full, out);
      else if (EXT.some((e) => entry.endsWith(e))) out.push(full);
    }
    return out;
  }

  it("every file that decides card admission is declared in the contract", () => {
    const declared = new Set(
      [
        ...CONTRACT.implementations,
        ...CONTRACT.consumers,
        ...CONTRACT.not_this_rule,
        ...CONTRACT.producers,
      ].map((d) => d.path),
    );

    const undeclared: string[] = [];
    for (const full of walk(REPO_ROOT)) {
      const rel = full.slice(REPO_ROOT.length + 1);
      if (isTest(rel)) continue;
      const src = readFileSync(full, "utf8");
      if (VOCAB.filter((v) => src.includes(v)).length < 3) continue;
      const names = [...src.matchAll(DECL)].map((m) => m[1]).filter((n) => NAME.test(n));
      if (names.length && !declared.has(rel)) undeclared.push(`${rel} → ${names.join(", ")}`);
    }

    expect(undeclared).toEqual([]);
  });

  it("finds the three known implementations — the non-vacuity control", () => {
    // Without this, a fingerprint that matches NOTHING passes the check above
    // forever and the registry becomes a green light wired to no sensor. This is
    // the same failure the dark-class limb had before #1948: perfectly healthy,
    // measuring nothing.
    const hits = walk(REPO_ROOT)
      .map((f) => f.slice(REPO_ROOT.length + 1))
      .filter((rel) => {
        if (isTest(rel)) return false;
        const src = readFileSync(join(REPO_ROOT, rel), "utf8");
        if (VOCAB.filter((v) => src.includes(v)).length < 3) return false;
        return [...src.matchAll(DECL)].map((m) => m[1]).some((n) => NAME.test(n));
      });

    for (const impl of CONTRACT.implementations) {
      expect(hits).toContain(impl.path);
    }
  });

  it("every declared path exists and still contains its symbol", () => {
    for (const impl of CONTRACT.implementations) {
      const full = join(REPO_ROOT, impl.path);
      expect(existsSync(full)).toBe(true);
      expect(readFileSync(full, "utf8")).toContain(impl.symbol);
    }
    for (const d of [...CONTRACT.consumers, ...CONTRACT.not_this_rule, ...CONTRACT.producers]) {
      expect(existsSync(join(REPO_ROOT, d.path))).toBe(true);
    }
  });
});

const IOS_ROOT = join(REPO_ROOT, "ios/Bain Luck/Bain Luck");
const NATIVE_PREDICATE = join(IOS_ROOT, "ViewModels/DiscoverViewModel.swift");
const iosPresent = existsSync(NATIVE_PREDICATE);
const d = iosPresent ? describe : describe.skip;

d("native encodes the SAME rule (source)", () => {
  const swift = readFileSync(NATIVE_PREDICATE, "utf8");

  // Narrow to the concept arm so a `leader` mention elsewhere in a 900-line file
  // cannot satisfy these assertions.
  const arm = (() => {
    const start = swift.indexOf("if let concept = item.concept {");
    expect(start).toBeGreaterThan(-1);
    const end = swift.indexOf("if let bundle = item.bundle {", start);
    expect(end).toBeGreaterThan(start);
    return swift.slice(start, end);
  })();

  it("admits an unsettled concept on its leader", () => {
    // The exact line web was missing. If someone deletes it on the native side,
    // native starts withholding what web now prints — the same divergence with
    // the surfaces swapped.
    expect(arm).toMatch(/if concept\.leader != nil \{\s*return nil\s*\}/);
  });

  it("requires a NAMEABLE result on the settled arm (#1935)", () => {
    expect(arm).toContain("concept.marqueeWhathit == true");
    expect(arm).toMatch(/winner/);
    expect(arm).toMatch(/resultSummary/);
    expect(arm).toMatch(/named\.isEmpty && summary\.isEmpty/);
  });

  it("checks settled BEFORE leader, so a result is never displaced", () => {
    const settledAt = arm.indexOf("concept.marqueeWhathit == true");
    const leaderAt = arm.indexOf("concept.leader != nil");
    expect(settledAt).toBeGreaterThan(-1);
    expect(leaderAt).toBeGreaterThan(-1);
    expect(settledAt).toBeLessThan(leaderAt);
  });

  it("the tournament arm admits on golfers ALONE (#1935)", () => {
    const tArm = (() => {
      const start = swift.indexOf("if let tournament = item.tournament {");
      const end = swift.indexOf("if let concept = item.concept {", start);
      expect(start).toBeGreaterThan(-1);
      return swift.slice(start, end);
    })();
    const code = tArm
      .split("\n")
      .filter((l) => !l.trim().startsWith("//"))
      .join("\n");
    expect(code).toMatch(/golfers, !golfers\.isEmpty \{ return nil \}/);
    // `marqueeWhathit` must not appear as an ADMITTING term: both clients
    // deleted it, and its survival in the Python copy is what blinded the
    // detector for three cycles.
    expect(code).not.toContain("marqueeWhathit");
  });

  it("falls closed — the arm's LAST return is still empty_concept", () => {
    const returns = arm.match(/return [^\n]+/g) ?? [];
    expect(returns.length).toBeGreaterThan(0);
    expect(returns[returns.length - 1]).toBe('return "empty_concept"');
  });
});

d("both web renderers can print what the gate admits", () => {
  // The half of this fix that is easiest to skip and most expensive to skip:
  // admitting a card the renderer has no branch for is how you rebuild #1935's
  // probability-free tile while closing #1939. Web has TWO concept renderers and
  // ONE gate, so both must be able to print a leader.
  const RENDERERS = [
    join(REPO_ROOT, "frontend/components/discover/ConceptCard.tsx"),
    join(REPO_ROOT, "frontend/components/FeedCard.tsx"),
  ];

  it.each(RENDERERS)("%s renders leader name + probability", (path) => {
    const src = readFileSync(path, "utf8");
    expect(src).toContain("leader.name");
    expect(src).toMatch(/leader\.probability \* 100/);
    // One movement formatter, shared — not a second copy per renderer.
    expect(src).toContain("formatConceptMovement");
  });
});

const SENTINEL_PREDICATE = join(REPO_ROOT, "backend/app/tasks/flow_sentinel.py");
const dp = existsSync(SENTINEL_PREDICATE) ? describe : describe.skip;

dp("the flow sentinel encodes the SAME rule (source)", () => {
  const py = readFileSync(SENTINEL_PREDICATE, "utf8");

  // Narrow to the function, so a `marquee_whathit` mention anywhere else in a
  // 2,000-line module cannot satisfy these assertions.
  const fn = (() => {
    const start = py.indexOf("def feed_item_is_renderable(");
    expect(start).toBeGreaterThan(-1);
    const end = py.indexOf("\ndef feed_dark_card_classes(", start);
    expect(end).toBeGreaterThan(start);
    return py.slice(start, end);
  })();

  const armBetween = (from: string, to: string) => {
    const start = fn.indexOf(from);
    const end = fn.indexOf(to, start);
    expect(start).toBeGreaterThan(-1);
    expect(end).toBeGreaterThan(start);
    return fn.slice(start, end);
  };

  it("the tournament arm admits on golfers ALONE (#1935)", () => {
    const arm = armBetween('if kind == "tournament":', 'if kind == "concept":');
    expect(arm).toMatch(/return bool\(data\.get\("golfers"\)\)/);
    const code = arm
      .split("\n")
      .filter((l) => !l.trim().startsWith("#"))
      .join("\n");
    expect(code).not.toContain("marquee_whathit");
  });

  it("the concept arm requires a nameable result, then a USABLE leader", () => {
    const arm = armBetween('if kind == "concept":', 'if kind == "bundle":');
    expect(arm).toContain('data.get("marquee_whathit") is True');
    expect(arm).toMatch(/return bool\(named or summary\)/);
    // A bare `data.get("leader")` is the TypeScript-erasure failure mode in
    // Python: `{}` is truthy. Native can write a presence test because its
    // decoder rejects malformed leaders first; Python, like TS, cannot.
    expect(arm).toContain('_concept_leader_is_usable(data.get("leader"))');
    expect(arm).not.toMatch(/return bool\(\s*data\.get\("leader"\)\s*\)/);
    expect(arm.indexOf("marquee_whathit")).toBeLessThan(
      arm.indexOf("_concept_leader_is_usable"),
    );
  });

  it("the futures arm carries the resolution_date authority web has", () => {
    // The one drift in the STRICT direction: without this the sentinel calls a
    // settled-by-date card unrenderable while both clients print it, so the
    // mirror under-counts a healthy page and the floor limb drifts toward noise.
    expect(fn).toContain("_futures_is_settled(data, now)");
    expect(py).toContain('raw = data.get("resolution_date")');
  });

  it("falls closed — the function's last statement is `return False`", () => {
    expect(fn.trimEnd().endsWith("return False")).toBe(true);
  });
});
