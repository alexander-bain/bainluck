/**
 * #6444 — Browse draws a featured hub in one of TWO places, and which one is a
 * question for the clock. Asserted by reading the Swift.
 *
 * Alex, on the phone on 2026-09-16: "Stale US Open leads." #6600 had fixed the
 * LINE under that card — "Results and title odds", which was the lie — but the
 * tournament whose final was played on 13 September was still the first thing in
 * the tab, above every destination useful in an ordinary week. Leading the tab is
 * itself a claim that this is the thing to look at today.
 *
 * WHY THIS FILE EXISTS AND `BrowseFeaturedHubOrder6444Tests` DOES NOT SUFFICE.
 * Those XCTest cases prove `browseFeaturedHubs(in:asOf:)`. They cannot prove the
 * view BODY draws the two arms where it says it does, and the body is where this
 * defect lived — the pre-fix render site was a bare `ForEach(featuredTournaments)`
 * at the head of `featuredGrid`, invisible to XCTest. The mutants that matter are
 * all body-shaped:
 *
 *   * `ForEach(hubs.leading)` followed immediately by `ForEach(hubs.trailing)` —
 *     the partition computed and then discarded, which restores the defect
 *     exactly while every Swift test stays green;
 *   * the trailing arm deleted, which demotes a finished hub off the tab
 *     altogether rather than down it;
 *   * the whole thing reverted to `ForEach(featuredTournaments)`.
 *
 * CI compiles no Swift (#4302), so these assertions are the only ones that run on
 * every push. Comments are stripped first: the prose above names every needle
 * below, and prose must never satisfy a claim about code.
 *
 * Sibling scan: `featuredHubSubtitleGoesThroughTheClock.test.ts` owns the LINE on
 * the card. This one owns the PLACE. They are deliberately two files because they
 * are two claims — a card can be honest and badly placed, which is precisely what
 * 16 September looked like after #6600 landed.
 */

import { readFileSync, existsSync } from "fs";
import { join } from "path";

const IOS_ROOT = join(__dirname, "../../../ios/Bain Luck/Bain Luck");
const LEAGUES_VIEW = join(IOS_ROOT, "Views/LeaguesView.swift");

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "")
    .replace(/(?<!:)\/\/.*$/gm, "");
}

/**
 * The body of `featuredGrid`, comments stripped.
 *
 * Sliced to the next member declaration rather than to a brace count, because a
 * brace counter that gets it wrong returns a SHORTER string, and every
 * "does not contain" assertion below passes on a shorter string. The length
 * check in the first describe is what stops a bad slice reading as a clean pass.
 */
function featuredGridBody(): string {
  const source = stripComments(readFileSync(LEAGUES_VIEW, "utf8"));
  const start = source.indexOf("private var featuredGrid");
  if (start < 0) return "";
  const next = source.indexOf("\n    private ", start + 10);
  return source.slice(start, next < 0 ? source.length : next);
}

describe("the scan can actually see what it claims to check", () => {
  it("finds the view", () => {
    expect(existsSync(LEAGUES_VIEW)).toBe(true);
  });

  it("finds a featuredGrid body worth reading", () => {
    // A rename, a move to another file, or a slice that stopped early all show
    // up here rather than as a green run over an empty string.
    const body = featuredGridBody();
    expect(body.length).toBeGreaterThan(400);
    expect(body).toMatch(/LazyVGrid/);
    expect(body).toMatch(/BrowseFeatureCard/);
  });
});

describe("#6444 — the grid orders the hubs on the clock", () => {
  it("asks the shared partition rather than drawing the catalog straight", () => {
    const body = featuredGridBody();
    expect(body).toMatch(/browseFeaturedHubs\(/);
    // The pre-fix render site, by name.
    expect(body).not.toMatch(/ForEach\(featuredTournaments\)/);
    // And no second partition invented at the render site.
    expect(body).not.toMatch(/featuredTournaments\s*\.\s*filter/);
  });

  it("reads ONE clock for the whole grid", () => {
    // Two `Date()` calls can straddle the boundary, and a hub that led by the
    // first while printing its resting line by the second is the disagreement
    // the pair exists to prevent, moved inside a single render.
    const body = featuredGridBody();
    expect(body.match(/Date\(\)/g) ?? []).toHaveLength(1);
  });

  it("draws BOTH arms", () => {
    // The positive half. Every "is not at the top" assertion below is also
    // satisfied by a hub that is nowhere at all — and "nowhere" is a worse
    // answer than the defect, because the hub keeps results and title odds all
    // year. This asserts the surface is still a surface.
    const body = featuredGridBody();
    expect(body).toMatch(/ForEach\(hubs\.leading\)/);
    expect(body).toMatch(/ForEach\(hubs\.trailing\)/);
  });

  it("puts the evergreen destinations BETWEEN the two arms", () => {
    // The mutant this kills: both `ForEach`es adjacent at the head of the grid,
    // which computes the partition, ignores it, and restores 16 September.
    const body = featuredGridBody();
    const leading = body.indexOf("ForEach(hubs.leading)");
    const trailing = body.indexOf("ForEach(hubs.trailing)");
    const evergreen = body.indexOf('title: "Futures Markets"');

    expect(leading).toBeGreaterThanOrEqual(0);
    expect(evergreen).toBeGreaterThan(leading);
    expect(trailing).toBeGreaterThan(evergreen);
  });
});

describe("#6444 — the two placements draw the same card", () => {
  it("both arms render through one card builder", () => {
    // A reader who finds the US Open lower down gets the tile they would have
    // got at the top; the clock moves it, it does not restyle it. Two inlined
    // `BrowseFeatureCard` literals would drift apart the first time either is
    // touched.
    const body = featuredGridBody();
    expect(body.match(/featuredHubCard\(/g) ?? []).toHaveLength(2);

    const source = stripComments(readFileSync(LEAGUES_VIEW, "utf8"));
    expect(source).toMatch(/private func featuredHubCard\(/);
    // Still through the clock, per the sibling scan's rule: the shared builder
    // is now the one place the subtitle is read, so it is the one place that
    // can drop the clock.
    expect(source).toMatch(/subtitle:\s*tournament\.subtitle\(asOf:/);
  });
});
