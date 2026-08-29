/**
 * #1933 — `contracts/rendered_percent.json` drives web, and this suite is also
 * the only CROSS-runtime check that runs in CI.
 *
 * The server fingerprints a graded card at this resolution so that a refused
 * judgment is always explicable as "the number on screen changed". Three
 * runtimes print that number and no import spans them, so the shared unit is the
 * table (ruling 021).
 *
 * ## What this file is responsible for that no other file can be
 *
 * The Swift arm executes under `scripts/ios_native_gate.sh test`, which is a
 * local gate — xcodebuild does not run in CI. So the Swift TEST's inlined case
 * table is compared against the contract HERE, where CI will see it. Without
 * this, native could quietly stop being the same rule and the only thing that
 * would notice is whoever next ran the native gate by hand.
 *
 * UX-P110's near-miss is the reason the bar is set here: it shipped the Python
 * arm using banker's rounding, under a comment stating the JavaScript answer,
 * with a test that asserted the Python one. Everything was green and two
 * runtimes disagreed at every .5.
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

import {
  isComplementPair,
  renderedCardPercents,
  renderedDuelPercents,
  renderedPercent,
} from "../../lib/renderedPercent";

const REPO_ROOT = join(__dirname, "..", "..", "..");
const CONTRACT_PATH = join(REPO_ROOT, "contracts/rendered_percent.json");

interface Case {
  probability: number | null;
  percent: number | null;
  discriminates?: boolean;
}
interface CardCase {
  probabilities: (number | null)[];
  percents: (number | null)[];
  complement_pair: boolean;
  naive: (number | null)[];
  discriminates?: boolean;
}
interface DuelCase {
  away: number | null;
  home: number | null;
  percents: (number | null)[];
  complement_pair: boolean;
  naive: (number | null)[];
  positional: (number | null)[];
  discriminates?: boolean;
}
interface Contract {
  version: number;
  rule: string;
  card_rule: string;
  implementations: {
    runtime: string;
    path: string;
    symbol: string;
    card_symbol: string;
    driven_by: string;
  }[];
  cases: Case[];
  card_cases: CardCase[];
  duel_rule: string;
  duel_implementations: { runtime: string; path: string; symbol: string }[];
  duel_cases: DuelCase[];
}

const CONTRACT: Contract = JSON.parse(readFileSync(CONTRACT_PATH, "utf8"));

describe("web prints what the contract says", () => {
  it.each(CONTRACT.cases.map((c) => [String(c.probability), c] as const))(
    "%s",
    (_label, c) => {
      expect(renderedPercent(c.probability)).toBe(c.percent);
    }
  );

  it("undefined behaves like null — a missing field is not a zero", () => {
    expect(renderedPercent(undefined)).toBeNull();
  });

  it("a non-finite number is not a percent", () => {
    expect(renderedPercent(NaN)).toBeNull();
    expect(renderedPercent(Infinity)).toBeNull();
  });
});

describe("the contract still discriminates", () => {
  // Same guard as the Python suite: a table can be defanged by deleting rows
  // while every remaining assertion stays green.
  it("keeps at least five rows where banker's rounding would differ", () => {
    const discriminating = CONTRACT.cases.filter((c) => c.discriminates);
    expect(discriminating.length).toBeGreaterThanOrEqual(5);
  });

  it("every flagged row really does disagree with banker's rounding", () => {
    // Banker's rounding, implemented here so the flag is checked against
    // arithmetic rather than trusted.
    const bankers = (x: number) => {
      const floor = Math.floor(x);
      const frac = x - floor;
      if (frac > 0.5) return floor + 1;
      if (frac < 0.5) return floor;
      return floor % 2 === 0 ? floor : floor + 1;
    };
    for (const c of CONTRACT.cases) {
      if (c.probability === null) continue;
      const differs = bankers(c.probability * 100) !== c.percent;
      expect([c.probability, differs]).toEqual([c.probability, Boolean(c.discriminates)]);
    }
  });
});

// ── THE CARD RULE (#2060) ────────────────────────────────────────────────────

describe("web renders the CARD the way the contract says", () => {
  it.each(CONTRACT.card_cases.map((c) => [JSON.stringify(c.probabilities), c] as const))(
    "%s",
    (_label, c) => {
      expect(renderedCardPercents(c.probabilities)).toEqual(c.percents);
      expect(isComplementPair(c.probabilities)).toBe(c.complement_pair);
    }
  );

  it("a complement pair always sums to exactly 100 — THE display invariant", () => {
    const pairs = CONTRACT.card_cases.filter((c) => c.complement_pair);
    expect(pairs.length).toBeGreaterThanOrEqual(6);
    for (const c of pairs) {
      const rendered = renderedCardPercents(c.probabilities) as number[];
      expect([c.probabilities, rendered.reduce((a, b) => a + b, 0)]).toEqual([
        c.probabilities,
        100,
      ]);
    }
  });

  it("leaves non-complement cards exactly as independent rounding had them", () => {
    // Gotcha #43 — the guard must be proved in BOTH directions, or a future
    // "simplification" that normalizes every pair passes the whole suite while
    // inventing probabilities on thin books.
    const left = CONTRACT.card_cases.filter((c) => !c.complement_pair);
    expect(left.length).toBeGreaterThanOrEqual(6);
    for (const c of left) {
      expect(renderedCardPercents(c.probabilities)).toEqual(
        c.probabilities.map((p) => renderedPercent(p))
      );
    }
  });

  it("keeps the rows where the card rule differs from independent rounding", () => {
    const discriminating = CONTRACT.card_cases.filter((c) => c.discriminates);
    expect(discriminating.length).toBeGreaterThanOrEqual(6);
    for (const c of CONTRACT.card_cases) {
      const naive = c.probabilities.map((p) => renderedPercent(p));
      // The `naive` column is checked against arithmetic, not trusted…
      expect([c.probabilities, naive]).toEqual([c.probabilities, c.naive]);
      // …and so is the flag derived from it.
      const differs = JSON.stringify(c.percents) !== JSON.stringify(naive);
      expect([c.probabilities, differs]).toEqual([
        c.probabilities,
        Boolean(c.discriminates),
      ]);
    }
  });

  it("the exemplar from #2060 renders 93 and 7, not 93 and 8", () => {
    expect(renderedCardPercents([0.925, 0.075])).toEqual([93, 7]);
    // …and the naive rendering it replaces really did sum to 101.
    expect([renderedPercent(0.925), renderedPercent(0.075)]).toEqual([93, 8]);
  });

  it("undefined and empty are not a pair", () => {
    expect(renderedCardPercents(undefined)).toEqual([]);
    expect(renderedCardPercents(null)).toEqual([]);
    expect(isComplementPair([0.6, undefined])).toBe(false);
    expect(isComplementPair([NaN, 0.4])).toBe(false);
  });
});

// ── THE DUEL RULE (UX-P114) ──────────────────────────────────────────────────

describe("web renders the DUEL the way the contract says", () => {
  it.each(CONTRACT.duel_cases.map((c) => [`${c.away}v${c.home}`, c] as const))(
    "%s",
    (_label, c) => {
      expect(renderedDuelPercents(c.away, c.home)).toEqual(c.percents);
      expect(isComplementPair([c.away, c.home])).toBe(c.complement_pair);
    }
  );

  it("a game card's two sides always sum to exactly 100 — THE display invariant", () => {
    const pairs = CONTRACT.duel_cases.filter((c) => c.complement_pair);
    expect(pairs.length).toBeGreaterThanOrEqual(5);
    for (const c of pairs) {
      const rendered = renderedDuelPercents(c.away, c.home) as number[];
      expect([[c.away, c.home], rendered.reduce((a, b) => a + b, 0)]).toEqual([
        [c.away, c.home],
        100,
      ]);
    }
  });

  it("the naive column is arithmetic, not annotation", () => {
    // It is what the four surfaces printed before the rule, and it is what makes
    // `discriminates` mean anything. Believed rather than checked, it silently
    // disarms the row-preservation test below.
    for (const c of CONTRACT.duel_cases) {
      expect([[c.away, c.home], [renderedPercent(c.away), renderedPercent(c.home)]]).toEqual([
        [c.away, c.home],
        c.naive,
      ]);
    }
  });

  it("the positional column is arithmetic too — the REJECTED alternative", () => {
    for (const c of CONTRACT.duel_cases) {
      const expected = isComplementPair([c.away, c.home])
        ? renderedCardPercents([c.away, c.home])
        : [renderedPercent(c.away), renderedPercent(c.home)];
      expect([[c.away, c.home], expected]).toEqual([[c.away, c.home], c.positional]);
    }
  });

  it("keeps the rows where independent rounding printed 101", () => {
    const discriminating = CONTRACT.duel_cases.filter((c) => c.discriminates);
    expect(discriminating.length).toBeGreaterThanOrEqual(5);
    for (const c of CONTRACT.duel_cases) {
      const differs = JSON.stringify(c.percents) !== JSON.stringify(c.naive);
      expect([[c.away, c.home], differs]).toEqual([
        [c.away, c.home],
        Boolean(c.discriminates),
      ]);
    }
  });

  it("still distinguishes favourite-first from away-first derivation", () => {
    // Without a row where the two disagree, `renderedDuelPercents` could collapse
    // into a bare `renderedCardPercents([away, home])` and this suite stays green
    // — while every home favourite has its own number moved by a point.
    const differing = CONTRACT.duel_cases.filter(
      (c) => JSON.stringify(c.percents) !== JSON.stringify(c.positional)
    );
    expect(differing.length).toBeGreaterThanOrEqual(3);
    expect(
      differing.some((c) => c.home !== null && c.away !== null && c.home > c.away)
    ).toBe(true);
  });

  it("pins the leave-alone direction too (gotcha #43)", () => {
    const untouched = CONTRACT.duel_cases.filter((c) => !c.discriminates);
    expect(untouched.length).toBeGreaterThanOrEqual(5);
    expect(untouched.some((c) => c.complement_pair)).toBe(true);
    expect(untouched.some((c) => !c.complement_pair)).toBe(true);
  });

  it("undefined behaves like null on either side", () => {
    expect(renderedDuelPercents(undefined, 0.6)).toEqual([null, 60]);
    expect(renderedDuelPercents(0.6, undefined)).toEqual([60, null]);
  });
});

// ── THE SWIFT ARM. This is the CI half of a runtime check CI cannot run. ─────

const SWIFT_IMPL = join(
  REPO_ROOT,
  "ios/Bain Luck/Bain Luck/Utilities/RenderedPercent.swift"
);
const SWIFT_TEST = join(
  REPO_ROOT,
  "ios/Bain Luck/BainLuckTests/RenderedPercentContractTests.swift"
);
const iosPresent = existsSync(SWIFT_IMPL);
const d = iosPresent ? describe : describe.skip;

d("native encodes the SAME rule", () => {
  const impl = readFileSync(SWIFT_IMPL, "utf8");
  const code = impl
    .split("\n")
    .filter((l) => !l.trim().startsWith("///") && !l.trim().startsWith("//"))
    .join("\n");

  it("multiplies before rounding, in Double", () => {
    expect(code).toMatch(/\(probability \* 100\)\.rounded\(\)/);
  });

  it("does not name a rounding rule other than the default half-away-from-zero", () => {
    // `.rounded(.down)`, `.rounded(.toNearestOrEven)` — either would leave the
    // contract while still looking deliberate.
    expect(code).not.toMatch(/\.rounded\(\s*\./);
  });

  it("returns nil for nil and for non-finite, like the other two arms", () => {
    expect(code).toContain("probability.isFinite");
    expect(code).toContain("return nil");
  });
});

d("the Swift test table has not drifted from the contract", () => {
  const src = readFileSync(SWIFT_TEST, "utf8");
  const start = src.indexOf("CONTRACT ROWS BEGIN");
  const end = src.indexOf("CONTRACT ROWS END");

  it("has the delimited block the drift check reads", () => {
    expect(start).toBeGreaterThan(-1);
    expect(end).toBeGreaterThan(start);
  });

  it("contains exactly the contract's rows, in order", () => {
    const block = src.slice(start, end);
    const rows = [...block.matchAll(/\(\s*(nil|-?[0-9.]+)\s*,\s*(nil|-?\d+)\s*\)/g)].map(
      (m) => ({
        probability: m[1] === "nil" ? null : Number(m[1]),
        percent: m[2] === "nil" ? null : Number(m[2]),
      })
    );
    expect(rows).toEqual(
      CONTRACT.cases.map((c) => ({ probability: c.probability, percent: c.percent }))
    );
  });

  it("is non-vacuous — the parse finds rows at all", () => {
    // Without this, a regex that silently matched nothing would make the
    // comparison above `[] === []` on an empty contract and pass forever.
    const block = src.slice(start, end);
    const rows = [...block.matchAll(/\(\s*(nil|-?[0-9.]+)\s*,\s*(nil|-?\d+)\s*\)/g)];
    expect(rows.length).toBe(CONTRACT.cases.length);
    expect(rows.length).toBeGreaterThan(10);
  });
});

d("the Swift CARD table has not drifted from the contract", () => {
  const src = readFileSync(SWIFT_TEST, "utf8");
  const start = src.indexOf("CARD ROWS BEGIN");
  const end = src.indexOf("CARD ROWS END");

  const parseList = (s: string): (number | null)[] =>
    s.trim() === ""
      ? []
      : s
          .split(",")
          .map((t) => t.trim())
          .filter((t) => t.length > 0)
          .map((t) => (t === "nil" ? null : Number(t)));

  const rows = () => {
    const block = src.slice(start, end);
    // ([probs], [percents], bool, [naive])
    return [
      ...block.matchAll(
        /\(\s*\[([^\]]*)\]\s*,\s*\[([^\]]*)\]\s*,\s*(true|false)\s*,\s*\[([^\]]*)\]\s*\)/g
      ),
    ].map((m) => ({
      probabilities: parseList(m[1]),
      percents: parseList(m[2]),
      complement_pair: m[3] === "true",
      naive: parseList(m[4]),
    }));
  };

  it("has the delimited block the drift check reads", () => {
    expect(start).toBeGreaterThan(-1);
    expect(end).toBeGreaterThan(start);
  });

  it("contains exactly the contract's card rows, in order", () => {
    expect(rows()).toEqual(
      CONTRACT.card_cases.map((c) => ({
        probabilities: c.probabilities,
        percents: c.percents,
        complement_pair: c.complement_pair,
        naive: c.naive,
      }))
    );
  });

  it("is non-vacuous — the parse finds rows at all", () => {
    expect(rows().length).toBe(CONTRACT.card_cases.length);
    expect(rows().length).toBeGreaterThan(10);
  });
});

d("the Swift DUEL table has not drifted from the contract", () => {
  const src = readFileSync(SWIFT_TEST, "utf8");
  const start = src.indexOf("DUEL ROWS BEGIN");
  const end = src.indexOf("DUEL ROWS END");

  const num = (t: string): number | null => (t.trim() === "nil" ? null : Number(t));
  const parseList = (s: string): (number | null)[] =>
    s.trim() === ""
      ? []
      : s
          .split(",")
          .map((t) => t.trim())
          .filter((t) => t.length > 0)
          .map(num);

  const rows = () => {
    const block = src.slice(start, end);
    // (away, home, [percents], bool, [naive], [positional])
    return [
      ...block.matchAll(
        /\(\s*([\d.]+|nil)\s*,\s*([\d.]+|nil)\s*,\s*\[([^\]]*)\]\s*,\s*(true|false)\s*,\s*\[([^\]]*)\]\s*,\s*\[([^\]]*)\]\s*\)/g
      ),
    ].map((m) => ({
      away: num(m[1]),
      home: num(m[2]),
      percents: parseList(m[3]),
      complement_pair: m[4] === "true",
      naive: parseList(m[5]),
      positional: parseList(m[6]),
    }));
  };

  it("has the delimited block the drift check reads", () => {
    expect(start).toBeGreaterThan(-1);
    expect(end).toBeGreaterThan(start);
  });

  it("contains exactly the contract's duel rows, in order", () => {
    expect(rows()).toEqual(
      CONTRACT.duel_cases.map((c) => ({
        away: c.away,
        home: c.home,
        percents: c.percents,
        complement_pair: c.complement_pair,
        naive: c.naive,
        positional: c.positional,
      }))
    );
  });

  it("is non-vacuous — the parse finds rows at all", () => {
    expect(rows().length).toBe(CONTRACT.duel_cases.length);
    expect(rows().length).toBeGreaterThanOrEqual(10);
  });
});

d("native implements the duel rule, and the widget consumes it instead", () => {
  // Two different obligations, because the widget is a SEPARATE target that
  // cannot import the main app's utilities ("Widgets cannot share code with the
  // main app target directly" — WidgetAPIClient's own header). The main app owes
  // an implementation; the widget owes the ABSENCE of a fourth copy of the band.
  const impl = readFileSync(SWIFT_IMPL, "utf8");
  const code = impl
    .split("\n")
    .filter((l) => !l.trim().startsWith("///") && !l.trim().startsWith("//"))
    .join("\n");

  it("the main app defines renderedDuelPercents", () => {
    expect(code).toContain("func renderedDuelPercents");
  });

  it("every native surface that prints BOTH sides consumes the decision", () => {
    // The native gate does not run in CI, so this is the only place a regression
    // here is caught before someone runs xcodebuild by hand. Four surfaces draw
    // the pair; each must either read the served percents or go through
    // `renderedDuelPercents`, and none may round the two sides independently.
    //
    // 🔴 LAT-P120 (#2279) — THIS CHECK USED TO REQUIRE THE DEFECT. Its second half
    // asserted `awayRenderedPercent ??` and `homeRenderedPercent ??` — a coalesce
    // PER SIDE — on every surface, as proof that the served value was preferred.
    // Per side is exactly the shape that prints a served value beside a locally
    // derived one when a payload carries one field and not the other, which is
    // the 101 this contract exists to close, arriving from the other direction.
    // So the shape that was mandated here is the shape #2279 was filed about, and
    // that is why it survived on three surfaces: the guard was holding it in
    // place. What the old check was really reaching for — "preferred, not
    // computed and ignored" — is asserted below without prescribing the mechanism
    // that breaks it.
    const surfaces = [
      "ios/Bain Luck/Bain Luck/Components/DiscoverEventCard.swift",
      "ios/Bain Luck/Bain Luck/Components/RelatedByTagView.swift",
      "ios/Bain Luck/Bain Luck/Views/MenuBarView.swift",
    ];
    // Comments stripped first, and BOTH sides checked. The first draft of this
    // check did neither, and two planted mutations survived it: deleting the
    // fallback still matched the comment that explains the fallback, and dropping
    // the served value on the AWAY side still matched the HOME side's `??`. A
    // per-file substring test over commented source is not a test of the code.
    const codeOf = (src: string) =>
      src
        .split("\n")
        .filter((l) => {
          const t = l.trim();
          return !t.startsWith("//") && !t.startsWith("///") && !t.startsWith("*");
        })
        .join("\n");

    for (const rel of surfaces) {
      const code = codeOf(readFileSync(join(REPO_ROOT, rel), "utf8"));
      // The shared fallback, so a pre-deploy or cached payload still sums to 100.
      // Reached EITHER directly or through `duelPercents`, which is the pair
      // decision defined in this same contract arm (`RenderedPercent.swift`) and
      // whose entire else-branch is a call to `renderedDuelPercents`. A check
      // that names only the inner call is a check an extraction breaks while the
      // behaviour is intact — the failure LAT-P119 hit on `npm run contract`.
      expect([
        rel,
        "fallback",
        /renderedDuelPercents\s*\(/.test(code) || /duelPercents\s*\(/.test(code),
      ]).toEqual([rel, "fallback", true]);
      // The served values PREFERRED over it, and taken as a PAIR. Both sides are
      // still checked — the mutation that dropped the away side and passed on the
      // home side's `??` is still killed — but the required shape is now
      // both-or-neither rather than one coalesce per side.
      for (const side of ["away", "home"] as const) {
        const field = `${side}RenderedPercent`;
        expect([rel, side, new RegExp(`${field}\\b`).test(code)]).toEqual([
          rel,
          side,
          true,
        ]);
        // 🔴 And the per-side coalesce is now BANNED where it was once required.
        expect([rel, side, new RegExp(`${field}\\s*\\n?\\s*\\?\\?`).test(code)]).toEqual([
          rel,
          side,
          false,
        ]);
      }
    }
  });

  it("the widget reads the served percents rather than re-deriving the band", () => {
    const widget = join(REPO_ROOT, "ios/Bain Luck/BainLuckWidget/WidgetAPIClient.swift");
    const decoding = join(
      REPO_ROOT,
      "ios/Bain Luck/BainLuckWidget/WidgetFeedDecoding.swift"
    );
    expect(existsSync(widget)).toBe(true);
    expect(readFileSync(decoding, "utf8")).toContain("homeRenderedPercent");
    expect(readFileSync(widget, "utf8")).toContain("homeRenderedPercent");
    // The band must NOT appear in the widget target — a copied constant is a
    // constant that drifts, which is the whole reason the contract exists.
    //
    // Comments stripped FIRST, like the sibling check below. Without that this
    // matches the comment explaining why the band is absent — which it did on the
    // first run, and a check that flags the documentation of a rule as a
    // violation of it is a check that gets deleted rather than fixed.
    const codeOf = (src: string) =>
      src
        .split("\n")
        .filter((l) => {
          const t = l.trim();
          return !t.startsWith("//") && !t.startsWith("///") && !t.startsWith("*");
        })
        .join("\n");
    const widgetCode =
      codeOf(readFileSync(widget, "utf8")) + codeOf(readFileSync(decoding, "utf8"));
    expect(widgetCode).not.toContain("0.99");
    expect(widgetCode).not.toContain("1.01");
  });
});

d("native implements the card rule, not just the scalar one", () => {
  const impl = readFileSync(SWIFT_IMPL, "utf8");
  const code = impl
    .split("\n")
    .filter((l) => !l.trim().startsWith("///") && !l.trim().startsWith("//"))
    .join("\n");

  it("defines renderedCardPercents and isComplementPair", () => {
    expect(code).toContain("func renderedCardPercents");
    expect(code).toContain("func isComplementPair");
  });

  it("derives the second side rather than rounding it", () => {
    expect(code).toContain("100 - leader");
  });

  it("carries the same band as the contract", () => {
    expect(code).toContain("0.99");
    expect(code).toContain("1.01");
  });
});

d("the labeling card renders through the shared function, not a second copy", () => {
  const view = readFileSync(
    join(REPO_ROOT, "ios/Bain Luck/Bain Luck/Views/DiscoverLabelingView.swift"),
    "utf8"
  );
  const page = readFileSync(
    join(REPO_ROOT, "frontend/app/admin/label-pass/page.tsx"),
    "utf8"
  );

  const labelingPage = readFileSync(
    join(REPO_ROOT, "frontend/app/admin/labeling/page.tsx"),
    "utf8"
  );
  // #2060 extracted the card body out of the page so its rendered output could be
  // asserted (see `__tests__/components/labelingCardDisplayInvariant.test.tsx`).
  // The source-level claims below follow it to where the rendering now lives —
  // a grep pointed at the file the code LEFT is a grep that passes forever.
  const labeling = readFileSync(
    join(REPO_ROOT, "frontend/components/admin/LabelingCard.tsx"),
    "utf8"
  );

  it("native calls renderedPercent", () => {
    expect(view).toContain("renderedPercent(value)");
    expect(view).not.toMatch(/Int\(\(value \* 100\)\.rounded\(\)\)/);
  });

  it("web calls renderedPercent", () => {
    expect(page).toContain("renderedPercent");
    expect(page).not.toMatch(/Math\.round\(features\.probability \* 100\)/);
  });

  // ── #2060: THERE WAS A FOURTH COPY, AND IT WAS ON THE PAGE THAT WROTE 61 OF
  // THE STORE'S 88 ROWS ──────────────────────────────────────────────────────
  //
  // `frontend/app/admin/labeling/page.tsx` carried `Math.round(val * 100)`
  // inline and never imported the shared function at all, so the contract that
  // exists to keep runtimes agreeing was not consulted by one of the surfaces it
  // is about. It computed the same answer, which is how this drift survives: it
  // is right until the rule changes, and then it is silently the only place that
  // did not change.

  it("the labeling card imports the shared rule instead of inlining one", () => {
    expect(labeling).toContain('from "@/lib/renderedPercent"');
    // …and the page renders that card rather than a second copy of the JSX.
    expect(labelingPage).toContain("@/components/admin/LabelingCard");
  });

  it("no admin labeling surface re-implements the percent inline", () => {
    // Comments are stripped first, the same way the Swift arm above does it.
    // Without that this matches its OWN prose describing the banned expression —
    // which it did on the first run, and a check that flags the documentation of
    // a bug as the bug is a check that gets deleted rather than fixed.
    const codeOf = (src: string) =>
      src
        .split("\n")
        .filter((l) => !l.trim().startsWith("//") && !l.trim().startsWith("*"))
        .join("\n");
    for (const [name, src] of [["label-pass", page], ["labeling", labeling]] as const) {
      // `Math.round(<anything> * 100)` — the shape of every copy found so far.
      expect([name, codeOf(src).match(/Math\.round\([^)]*\*\s*100\)/)]).toEqual([
        name,
        null,
      ]);
    }
  });

  it("both pages prefer the SERVER's rendered_percent over re-deriving it", () => {
    // Since #2060 the card rule can move the leader by a point, so a client that
    // re-rounds the raw float can print 71 against a digest taken over 70 and
    // refuse its own write for a drift nobody could see.
    expect(page).toContain("rendered_percent");
    expect(labeling).toContain("rendered_percent");
  });

  it("both pages show the card's commence time", () => {
    expect(page).toContain("commence_time");
    expect(labeling).toContain("commence_time");
  });
});

describe("the contract's own registry is honest", () => {
  it("every declared implementation and driver exists and names its symbol", () => {
    for (const impl of CONTRACT.implementations) {
      const p = join(REPO_ROOT, impl.path);
      expect(existsSync(p)).toBe(true);
      expect(readFileSync(p, "utf8")).toContain(impl.symbol);
      expect(existsSync(join(REPO_ROOT, impl.driven_by))).toBe(true);
    }
  });

  it("declares all three runtimes", () => {
    expect(CONTRACT.implementations.map((i) => i.runtime).sort()).toEqual([
      "python",
      "swift",
      "typescript",
    ]);
  });

  it("every declared DUEL implementation exists and names its symbol", () => {
    // UX-P114 keeps its own registry because the widget target deliberately has
    // NO implementation — it consumes the served integers — so this list is three
    // entries, not four, and that asymmetry should be stated rather than inferred.
    for (const impl of CONTRACT.duel_implementations) {
      const p = join(REPO_ROOT, impl.path);
      expect([impl.path, existsSync(p)]).toEqual([impl.path, true]);
      expect([impl.path, readFileSync(p, "utf8").includes(impl.symbol)]).toEqual([
        impl.path,
        true,
      ]);
    }
  });

  it("the duel registry covers all three runtimes too", () => {
    expect(CONTRACT.duel_implementations.map((i) => i.runtime).sort()).toEqual([
      "python",
      "swift",
      "typescript",
    ]);
  });
});
