/**
 * #4117 — every chart gutter on iOS draws the same crest, asserted by reading
 * the Swift.
 *
 * On any live MLB event page the Win Probability gutter drew a red sock beside
 * `SOX`, and the Score Differential gutter ~200pt below it — same page, same two
 * teams, same sideways-label idiom — drew `SOX` bare. #3988 had fixed the crest
 * inside `OddsChartView`; doing so is what promoted its neighbour to the next
 * private rung of the ladder #2977 named, and the page contradicted itself
 * within one scroll.
 *
 * Reading the source for this ship also found a THIRD bare gutter: the
 * fullscreen chart inside `OddsChartView` itself, 120 lines below the one #3988
 * fixed. One file, two gutters, one of them corrected. That is the failure mode
 * this file exists to make impossible to repeat — a crest that is a call-site
 * detail is a crest the next gutter forgets.
 *
 * WHY THIS FILE AND NOT AN XCTEST. CI compiles no Swift (#4302), and a Swift
 * test cannot see a view BODY in any case: `ChartGutterCrestTests` proves
 * `resolvedURL` and stays green while every call site is deleted. The assertions
 * below are what kill that mutant, and they run in CI.
 */

import { readFileSync, existsSync, readdirSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const CANONICAL = join(IOS_ROOT, "Components/ChartGutterLabel.swift");

function swiftFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return swiftFiles(path);
    return entry.isFile() && entry.name.endsWith(".swift") ? [path] : [];
  });
}

/**
 * Comments only. The `(?<!:)` on the trailing rule keeps `https://` out of it —
 * and note the block rule runs FIRST, so a `/* … *\/` inside a Swift string
 * literal would be eaten too. Nothing in these files has one; the control at the
 * bottom is what keeps that honest.
 */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

/**
 * Every gutter in the tree, sliced to the block that DRAWS it.
 *
 * Slicing matters more than it looks. `OddsChartView.swift` holds two gutters
 * 120 lines apart and only one of them was right; a whole-file `toMatch` for
 * `ChartGutterCrest` passes on that file while half of what it draws is bare.
 * A gutter starts at its run — every one of them derives it from
 * `ChartGutter.run(` — and ends at the `.frame(width:` its `VStack` carries.
 */
function gutterBlocks(source: string): string[] {
  const code = stripComments(source);
  const blocks: string[] = [];
  let from = 0;
  for (;;) {
    const start = code.indexOf("ChartGutter.run(", from);
    if (start === -1) break;
    const end = code.indexOf(".frame(width:", start);
    // An unterminated block is a shape change, not a pass: take the rest of the
    // file rather than silently skipping the gutter.
    blocks.push(code.slice(start, end === -1 ? code.length : end));
    from = end === -1 ? code.length : end;
  }
  return blocks;
}

/** One call's argument list, to its MATCHING close paren. */
function callArguments(source: string, callee: string): string {
  const open = source.indexOf(callee);
  if (open === -1) return "";
  let depth = 0;
  for (let i = open + callee.length - 1; i < source.length; i += 1) {
    if (source[i] === "(") depth += 1;
    if (source[i] === ")") {
      depth -= 1;
      if (depth === 0) return source.slice(open + callee.length, i);
    }
  }
  return "";
}

/** A gutter label whose content begins with the abbreviation and nothing else. */
const BARE_LABEL = /ChartGutterLabel\([^)]*\)\s*\{\s*Text\(/;

// A path typo would otherwise read as a clean pass — the unrunnable-check
// failure mode this whole file exists to stop.
const iosPresent = existsSync(CANONICAL);
const d = iosPresent ? describe : describe.skip;

d("iOS chart gutters draw one shared crest", () => {
  const canonical = () => readFileSync(CANONICAL, "utf8");
  const odds = () => readFileSync(join(IOS_ROOT, "Components/OddsChartView.swift"), "utf8");
  const diff = () =>
    readFileSync(join(IOS_ROOT, "Components/ScoreDifferentialChartView.swift"), "utf8");

  it("the shared crest exists beside the label it sits next to", () => {
    expect(canonical()).toMatch(/struct ChartGutterCrest: View/);
    expect(canonical()).toMatch(
      /static func resolvedURL\(servedURL: String\?, teamName: String\?, sportKey: String\?\) -> URL\?/
    );
  });

  it("the crest asks the ladder and keeps no rung of its own", () => {
    // #2977: a private one-rung ladder is what drew a letter tile beside a
    // Sports row showing the real crest. The whole sport key is passed on
    // purpose — `isInternationalSport` matches `soccer_fifa_world_cup`, so a
    // truncated "soccer" compiles, reads right and blinds the flag rung.
    expect(canonical()).toMatch(
      /teamAvatarURL\(servedURL: servedURL, teamName: teamName \?\? "", sportKey: sportKey\)/
    );
  });

  it("a failed load collapses instead of holding a hole", () => {
    // #2977's second defect: `placeholder:` is the FAILURE state as well as the
    // loading one, so a 404 reserved 14pt beside the abbreviation forever.
    // Stripped first: the doc comment beside the fix QUOTES the defective line,
    // and a raw scan reads that quotation as the defect. (It failed this way on
    // the first run.)
    expect(canonical()).toMatch(/phase\.error != nil/);
    expect(stripComments(canonical())).not.toMatch(/placeholder: \{ EmptyView\(\) \}/);
  });

  it("EVERY gutter block in the two chart views draws the crest — all three of them", () => {
    // Three: the inline Win Probability gutter, its fullscreen twin, and the
    // Score Differential gutter. The count is asserted because a gutter that
    // stops being found by the slicer would otherwise pass this vacuously.
    const blocks = [...gutterBlocks(odds()), ...gutterBlocks(diff())];
    expect(blocks).toHaveLength(3);
    for (const block of blocks) {
      expect(block).toMatch(/ChartGutterCrest\.resolvedURL\(\s*servedURL: homeTeamLogo,/);
      expect(block).toMatch(/ChartGutterCrest\.resolvedURL\(\s*servedURL: awayTeamLogo,/);
      expect(block.match(/ChartGutterCrest\(url: url\)/g) ?? []).toHaveLength(2);
      // Both calls hand over the WHOLE sport key. `sportKey: nil` compiles, draws
      // a crest for every domestic team, and silently blinds the flag rung on the
      // one competition it exists for.
      expect(block.match(/sportKey: sportKey\)/g) ?? []).toHaveLength(2);
      expect(block).not.toMatch(BARE_LABEL);
    }
  });

  it("the Score Differential chart is HANDED the served crest", () => {
    // The ladder derives a crest from the team name for most teams, so the
    // gutter looks fixed on an MLB page even with the served rung missing. The
    // props are what let a served crest outrank a derived one, and a nil
    // default makes forgetting them silent.
    expect(diff()).toMatch(/var homeTeamLogo: String\?/);
    expect(diff()).toMatch(/var awayTeamLogo: String\?/);
    const caller = readFileSync(join(IOS_ROOT, "Views/EventDetailView.swift"), "utf8");
    // Balanced, not "to the first `)`" — the argument list contains
    // `teamColors(event)`, so the naive slice ends four arguments early and the
    // assertion fails on a call that is correct. (It did, on the first run.)
    const call = callArguments(caller, "ScoreDifferentialChartView(");
    expect(call).toMatch(/homeTeamLogo: event\.homeTeamData\?\.logoSmall/);
    expect(call).toMatch(/awayTeamLogo: event\.awayTeamData\?\.logoSmall/);
  });

  it("no chart view keeps a private copy of the crest", () => {
    // The point of #4117 is that the ninth line is not copied a fourth time.
    for (const source of [odds(), diff()]) {
      expect(stripComments(source)).not.toMatch(/AsyncImage/);
      expect(stripComments(source)).not.toMatch(/func gutterCrest/);
    }
  });

  it("no OTHER Swift file draws a bare gutter label — discovered, not listed", () => {
    const offenders: string[] = [];
    for (const path of swiftFiles(IOS_ROOT)) {
      for (const block of gutterBlocks(readFileSync(path, "utf8"))) {
        if (BARE_LABEL.test(block)) offenders.push(path.slice(IOS_ROOT.length + 1));
      }
    }
    expect(offenders).toEqual([]);
  });

  /**
   * #6612 — the crest is drawn UPRIGHT, not just drawn.
   *
   * The assertions above are exactly why this section exists. #4117 made the
   * crest universal across all three gutters and pinned its presence; nothing
   * pinned its orientation, so what went universal was a crest lying on its
   * side. `ChartGutterLabel` turns its whole content `-90°` — right for an
   * abbreviation that has to run along the axis, wrong for an image — and the
   * crest is composed inside that content. Photographed on the live
   * Cardinals–Giants game (15313231, `Bottom 9th`, 2026-09-16): the
   * interlocking `StL` and `SF` wordmarks drew as illegible tangles of strokes
   * beneath perfectly upright `STL` / `SF` text, in both gutters of one page.
   *
   * These read the SOURCE because that is the only thing that can see it.
   * `ChartGutterCrestTests` proves `resolvedURL` and stays green with the
   * counter-rotation deleted; a Swift test cannot reach a view body, and CI
   * compiles no Swift (#4302) so it would not run if it could.
   */
  describe("the crest stands up inside the rotated gutter (#6612)", () => {
    it("the gutter's turn is ONE named constant, not a literal per site", () => {
      // The fix is only durable if both halves read the same number. Two
      // literals is #1832's shape — free to drift, healthy copy hides the
      // broken one.
      expect(stripComments(canonical())).toMatch(
        /static let rotationDegrees: Double = -90/
      );
    });

    it("the LABEL's rotation reads that constant", () => {
      // Without this the crest's derivation is anchored to nothing: the
      // constant could say -90 while the label turned by a literal -90, and
      // changing the constant would rotate the crest alone.
      expect(stripComments(canonical())).toMatch(
        /\.rotationEffect\(\.degrees\(ChartGutter\.rotationDegrees\)\)/
      );
    });

    it("the CREST counter-rotates, and by the negation of that same constant", () => {
      const code = stripComments(canonical());
      expect(code).toMatch(
        /static var counterRotationDegrees: Double \{ -ChartGutter\.rotationDegrees \}/
      );
      expect(code).toMatch(
        /\.rotationEffect\(\.degrees\(Self\.counterRotationDegrees\)\)/
      );
    });

    it("the crest's turn is not written as a bare number anywhere", () => {
      // The mutant this kills: `.rotationEffect(.degrees(90))` on the crest.
      // It renders correctly TODAY and silently stops tracking the label.
      const crest = stripComments(canonical()).slice(
        stripComments(canonical()).indexOf("struct ChartGutterCrest")
      );
      expect(crest).not.toMatch(/\.rotationEffect\(\.degrees\(-?\d/);
    });

    it("the two turns cancel — stated as arithmetic the reader can check", () => {
      // Deliberately NOT the load-bearing assertion, and saying so matters:
      // `counterRotationDegrees` is DEFINED as the negation, so this can only
      // fail if someone writes a literal — which the scan above is what
      // actually catches. What this adds is the other half, which is not
      // derivable: that the label turns AT ALL. A `rotationDegrees` of 0 makes
      // every assertion in this block pass while no gutter is sideways and no
      // crest needs righting.
      const code = stripComments(canonical());
      const degrees = Number(
        /static let rotationDegrees: Double = (-?\d+)/.exec(code)?.[1]
      );
      expect(degrees).toBe(-90);
      expect(-degrees + degrees).toBe(0);
    });

    it("fires on the REAL pre-fix crest body", () => {
      // Copied verbatim from ChartGutterLabel.swift at origin/master
      // c21df0409 — the code #6612 was filed about. Frozen: a control
      // re-snapshotted from a fixed tree contains no defect (notice 50).
      const preFix = `
    var body: some View {
        AsyncImage(url: url) { phase in
            if let image = phase.image {
                image.resizable().scaledToFit().frame(width: Self.side, height: Self.side)
            } else if phase.error != nil {
                EmptyView()
            } else {
                Color.clear.frame(width: Self.side, height: Self.side)
            }
        }
    }
`;
      expect(preFix).not.toMatch(
        /\.rotationEffect\(\.degrees\(Self\.counterRotationDegrees\)\)/
      );
    });

    it("does NOT fire on a crest righted with a literal — it fires for the RIGHT reason", () => {
      // The negative control that isolates the clause. This body renders
      // upright, so a scan that merely looked for "some rotation on the crest"
      // would pass it. The drift clause is what must reject it, and only that
      // clause: it fails the bare-number rule and nothing else.
      const literal = `
struct ChartGutterCrest: View {
    var body: some View {
        AsyncImage(url: url) { phase in
            EmptyView()
        }
        .rotationEffect(.degrees(90))
    }
}
`;
      expect(literal).toMatch(/\.rotationEffect\(\.degrees\(-?\d/);
      expect(literal).not.toMatch(
        /\.rotationEffect\(\.degrees\(Self\.counterRotationDegrees\)\)/
      );
    });
  });

  it("the check fires on the REAL pre-fix source", () => {
    // Copied verbatim from ScoreDifferentialChartView.swift at origin/master
    // 4c419cb7 — the code this issue was filed about. A guard is only proven by
    // the source it was built to catch, and this one is scoped to a BLOCK, so a
    // synthetic one-liner would not have exercised the slicer at all.
    const preFix = `
                    VStack {
                        let run = ChartGutter.run(chartHeight: Self.chartHeight, verticalPadding: 8)
                        ChartGutterLabel(run: run, width: Self.gutterWidth) {
                            Text(homeShort.uppercased())
                                .font(.system(size: 10, weight: .bold))
                                .foregroundStyle(homeTeamColor ?? .blue)
                                .lineLimit(1)
                        }
                        Spacer()
                        ChartGutterLabel(run: run, width: Self.gutterWidth) {
                            Text(awayShort.uppercased())
                                .font(.system(size: 10, weight: .bold))
                                .foregroundStyle(awayTeamColor ?? .red)
                                .lineLimit(1)
                        }
                    }
                    .frame(width: Self.gutterWidth)
`;
    const blocks = gutterBlocks(preFix);
    expect(blocks).toHaveLength(1);
    expect(blocks[0]).toMatch(BARE_LABEL);
    expect(blocks[0]).not.toMatch(/ChartGutterCrest/);
  });

  it("the check does NOT fire on the shipped shape", () => {
    // The inverse hazard: a scan that flags a correct gutter gets suppressed.
    const shipped = `
                        let run = ChartGutter.run(chartHeight: Self.chartHeight, verticalPadding: 8)
                        ChartGutterLabel(run: run, width: Self.gutterWidth) {
                            HStack(spacing: 3) {
                                if let url = ChartGutterCrest.resolvedURL(
                                    servedURL: homeTeamLogo, teamName: homeTeam, sportKey: sportKey) {
                                    ChartGutterCrest(url: url)
                                }
                                Text(homeShort.uppercased())
                            }
                        }
                        .frame(width: Self.gutterWidth)
`;
    expect(gutterBlocks(shipped)[0]).not.toMatch(BARE_LABEL);
  });

  it("a commented-out crest does not read as a drawn one", () => {
    // The blinding that matters here: the crest lines survive as a comment while
    // the label goes bare, and a scan that reads comments as code passes.
    const commented = `
                        let run = ChartGutter.run(chartHeight: Self.chartHeight, verticalPadding: 8)
                        ChartGutterLabel(run: run, width: Self.gutterWidth) {
                            // if let url = ChartGutterCrest.resolvedURL(
                            //     servedURL: homeTeamLogo, teamName: homeTeam, sportKey: sportKey) {
                            //     ChartGutterCrest(url: url)
                            // }
                            Text(homeShort.uppercased())
                        }
                        .frame(width: Self.gutterWidth)
`;
    const block = gutterBlocks(commented)[0];
    expect(block).toMatch(BARE_LABEL);
    expect(block).not.toMatch(/ChartGutterCrest/);
  });
});
