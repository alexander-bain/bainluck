/**
 * #6816 — the native arm of "a fight's two percentages are ONE decision", pinned
 * from the one place this repo's CI can read Swift: as source.
 *
 * WHAT THIS IS NOT. It is not a compile and it is not a run. The executing proof
 * of the native arm is `BainLuckTests/AFightsTwoPercentsAgree6816Tests.swift`,
 * which needs Xcode. This guard exists because a server field the phone ignores
 * is not a fix: it fails if the fight-card row stops handing the served pair to
 * the formatter, if the pair is ever coalesced per side, or if the fixture the two
 * clients share stops being one file.
 */
import { existsSync, readFileSync } from "fs";
import { join } from "path";

import { servedBoutPercents } from "@/lib/servedBoutPercents";

import { swiftCodeKeepingStrings, swiftFunctionBody } from "../helpers/swiftSource";

const REPO_ROOT = join(__dirname, "../../..");
const APP_ROOT = join(REPO_ROOT, "ios/Bain Luck/Bain Luck");
const MODELS = join(APP_ROOT, "Models/ConceptCardModels.swift");
const VIEW = join(APP_ROOT, "Views/ConceptCardView.swift");
const FORMATTING = join(APP_ROOT, "Utilities/FormattingUtilities.swift");
const IOS_FIXTURE = join(
  REPO_ROOT,
  "ios/Bain Luck/BainLuckTests/Fixtures/event-ufc-26sep19.served6816.SYNTHETIC.json",
);
const WEB_FIXTURE = join(
  __dirname,
  "../fixtures/eventConceptUfc26sep19.served6816.SYNTHETIC.json",
);
const NATIVE_TEST = join(
  REPO_ROOT,
  "ios/Bain Luck/BainLuckTests/AFightsTwoPercentsAgree6816Tests.swift",
);

const code = (path: string) => swiftCodeKeepingStrings(readFileSync(path, "utf8"));

describe("#6816 — the files this guard reads all exist", () => {
  it.each([MODELS, VIEW, FORMATTING, IOS_FIXTURE, WEB_FIXTURE, NATIVE_TEST])("%s", (path) => {
    expect(existsSync(path)).toBe(true);
  });
});

describe("#6816 — the fight-card row prints the served pair", () => {
  it("the row hands `bout.percents` to the app's canonical formatter", () => {
    const view = code(VIEW);
    expect(view).toMatch(
      /formatProbabilityOrDash\(\s*fighter\.probability,\s*renderedPercent:\s*bout\.percents/,
    );
    // …and no second, bare call survives beside it to print the unserved number.
    expect(view.match(/formatProbabilityOrDash\(/g) ?? []).toHaveLength(1);
  });

  it("the formatter it calls still takes a served integer, and still guards the boundaries first", () => {
    const body = swiftFunctionBody(code(FORMATTING), "func formatProbability(_ value: Double") ?? "";
    expect(body).not.toBe("");
    const below = body.indexOf('"<1%"');
    const above = body.indexOf('">99%"');
    const served = body.indexOf("if let renderedPercent");
    expect(below).toBeGreaterThan(-1);
    expect(above).toBeGreaterThan(-1);
    expect(served).toBeGreaterThan(Math.max(below, above));
  });

  it("the outcome decodes `rendered_percent` and the row carries it index for index", () => {
    const models = code(MODELS);
    expect(models).toMatch(/let renderedPercent: Int\?/);
    expect(models).toMatch(/let percents: \[Int\?\]/);
    expect(models).toMatch(/percents: Self\.servedPercents\(/);
  });

  it("a malformed served value cannot throw the bout away", () => {
    expect(code(MODELS)).toMatch(
      /renderedPercent = try\? c\.decodeIfPresent\(Int\.self, forKey: \.renderedPercent\)/,
    );
  });
});

describe("#6816 — both served or neither, on the phone too", () => {
  const body = () =>
    swiftFunctionBody(code(MODELS), "static func servedPercents(") ?? "";

  it("the function this guard watches exists", () => {
    expect(body()).not.toBe("");
  });

  it("it takes exactly two fighters of a two-outcome market", () => {
    expect(body()).toMatch(/fighters\.count == 2, outcomeCount == 2/);
  });

  it("it needs BOTH values, each a whole percent, or returns nothing for either", () => {
    expect(body()).toMatch(/served\.count == 2/);
    expect(body()).toMatch(/\(0\.\.\.100\)\.contains/);
  });

  it("it never coalesces one side, and never normalises locally", () => {
    expect(body()).not.toMatch(/\?\?/);
    expect(body()).not.toMatch(/renderedDuelPercents|renderedCardPercents|duelPercents\(/);
    expect(code(MODELS)).not.toMatch(/renderedPercent\s*\?\?/);
    expect(code(VIEW)).not.toMatch(/renderedPercent\s*\?\?/);
  });
});

describe("#6816 — web and native read ONE served payload", () => {
  it("the two fixture copies are byte-identical", () => {
    expect(readFileSync(IOS_FIXTURE, "utf8")).toBe(readFileSync(WEB_FIXTURE, "utf8"));
  });

  it("the native expectations are the web reader's answer for the same rows", () => {
    const payload = JSON.parse(readFileSync(WEB_FIXTURE, "utf8"));
    const native = readFileSync(NATIVE_TEST, "utf8");
    for (const [title, pair] of [
      ["331: Tsarukyan vs Ruffy", [73, 27]],
      ["331: Chikadze vs Brito", [78, 22]],
      ["331: Pitbull vs Choi", [72, 28]],
      ["331: Aswell vs Yoo", [67, 33]],
    ] as Array<[string, number[]]>) {
      const child = payload.children.find(
        (c: { market_name: string }) => c.market_name === title,
      );
      expect(servedBoutPercents(child.outcomes)).toEqual(pair);
      expect(native).toContain(`"${title}": ["${pair[0]}%", "${pair[1]}%"]`);
    }
  });
});
