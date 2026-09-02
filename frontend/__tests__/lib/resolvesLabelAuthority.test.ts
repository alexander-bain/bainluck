import fs from "fs";
import path from "path";

import { resolvesLabel } from "@/components/discover/utils";
import { formatResolvesLabel, formatTournamentTimingLabel } from "@/lib/gameTimeLabel";

/**
 * UX-P053 (#1717) — ONE formatting authority for "Resolves <date>".
 *
 * THE DEFECT. On 2026-08-11T01:10Z, at the deployed sha `8bf7cce5`, the Discover
 * landing page answered "when does this resolve?" two opposite ways on one
 * screen. Across 60 unique futures cards — the dominant card type now that #1698
 * is fixed — 49 carried a `resolution_date` on the wire and printed NOTHING,
 * because `resolvesLabel` returned "" beyond 7 days. The tournament card beside
 * them printed "Resolves Aug 17, 2026", because #1708 had taught it to one day
 * earlier.
 *
 * Eighth instance of the #1620 shape on this lane, and the answer already existed
 * in a sibling module — again.
 *
 * ── UX-P054 (#1719) — THE NINTH INSTANCE WAS THIS FILE'S OWN RECORDED DEBT ──
 *
 * UX-P053 shipped with two known copies exempted and a scan that stopped at
 * `components/` + `lib/`. One cycle later the exempted copy was measured on the
 * live Sports tab: 46 of 60 cards there are futures cards, 41 carry a date, and
 * **29 of those 41 printed a year that was not the current one** — "2030 FIFA
 * World Cup Champion" rendering "Resolves Jan 14" about January 2031, which is
 * verbatim the misreading `formatResolvesLabel`'s docstring exists to prevent.
 *
 * Both copies are converted, the exemption list is deleted, and the scan reaches
 * `app/`. The guard's assertion is therefore now an EQUALITY — one file builds
 * this string — rather than a subset check against a list that could grow.
 *
 * WHY THIS FILE EXISTS RATHER THAN JUST A UNIT TEST. Alex's ruling was not
 * "extend it" but "use the IDENTICAL formatter — one formatting authority, so
 * the next drift is unrepresentable rather than refiled." A unit test proves
 * today's two callers agree; it does nothing about the third copy someone writes
 * next month. So the guard below reads the tree and fails on a NEW construction
 * of the string.
 */

const FRONTEND = path.resolve(__dirname, "..", "..");
const NOW = Date.parse("2026-08-11T01:10:00.000Z");

/**
 * Comments out, code in.
 *
 * A CONSTRUCTION is the string being built; a MENTION is documentation naming
 * the string a component renders. The first draft of this guard conflated them
 * and flagged three kernel prop-docs (`/** Header-left state copy ("Resolves Sep
 * 17"). *\/`) — which would have taught the next reader that the guard cries
 * wolf, and a guard nobody believes is worse than no guard.
 */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

/**
 * A CONSTRUCTION of the timing rule, as opposed to any string starting "Resolves".
 *
 * UX-P054 (#1719) — THE SCAN WIDENED TO `app/`, SO THE PATTERN HAD TO NARROW.
 *
 * UX-P053 scanned only `components/` and `lib/`, and named `app/futures/[id]/
 * page.tsx` as its blind spot. Widening to `app/` closes that, but the old
 * `["'`]Resolves\s` pattern picks up three sites there that implement no date
 * rule at all:
 *
 *   - `app/economics/page.tsx`      "Resolves post-FOMC", "Resolves daily."
 *                                   — prose in a footnote and a section subtitle
 *   - `app/kernels-preview/page.tsx` "Resolves Sep 17", "Resolves Sunday"
 *                                   — static fixture props in a design preview
 *
 * Exempting three innocent sites to widen the scan would have taught the next
 * reader that this guard cries wolf, which is the failure standing note 4 names:
 * a guard nobody believes is worse than no guard. So the pattern now matches what
 * a construction actually looks like — the string being BUILT from a date
 * (interpolation) or a relative-time ladder rung — and the exemption list is
 * empty instead.
 *
 * KNOWN RESIDUAL, stated rather than left for someone to discover: a hand-written
 * weekday literal (`return "Resolves Sunday"`) inside a ladder would not be
 * caught, because it is indistinguishable by regex from the preview fixture that
 * legitimately contains that exact string. Interpolation and the relative rungs
 * are what every real drift on this lane has actually looked like.
 */
const CONSTRUCTION = /["'`]Resolves \$\{|["'`]Resolves (today|tomorrow|tonight)\b/;

/** Files that construct a "Resolves ..." string, discovered rather than listed. */
function resolvesConstructionSites(): string[] {
  const hits: string[] = [];
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.name === "node_modules" || entry.name.startsWith(".")) continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full);
        continue;
      }
      if (!/\.(ts|tsx)$/.test(entry.name)) continue;
      if (CONSTRUCTION.test(stripComments(fs.readFileSync(full, "utf8")))) {
        hits.push(path.relative(FRONTEND, full));
      }
    }
  };
  for (const root of ["components", "lib", "app"]) walk(path.join(FRONTEND, root));
  return [...new Set(hits)].sort();
}

/** The authority itself — the one file that is SUPPOSED to build the string. */
const AUTHORITY = "lib/gameTimeLabel.ts";

/**
 * Every file allowed to construct the string.
 *
 * UX-P054 (#1719) — THE EXEMPTION LIST IS EMPTY, AND THAT IS THE DELIVERABLE.
 *
 * UX-P053 recorded two sites as named debt rather than restyling them unmeasured
 * (the UX-P045 rule). Both are now converted, so the list is deleted rather than
 * edited — an exemption that outlives its reason is its own drift (#1525):
 *
 *   - `components/FeedCard.tsx` ran a private ladder whose last rung printed a
 *     month-day with no year. On the live Sports tab that was 29 of the 41 dated
 *     futures cards implying the wrong year — "2030 FIFA World Cup Champion"
 *     rendering "Resolves Jan 14" about January 2031. It now calls
 *     `resolvesLabel`, the same function the Discover futures card calls.
 *   - `app/futures/[id]/page.tsx` inlined a third `toLocaleDateString`. It now
 *     calls `formatResolvesLabel` and thereby gains the past-date rule it lacked.
 *
 * With both gone, ONE file may build this string. That is what makes the next
 * drift unrepresentable rather than merely refiled — which was Alex's #1717
 * ruling, and it is only true now that the list is empty.
 */
const PERMITTED = [AUTHORITY];

describe("#1717 — one formatting authority for 'Resolves <date>'", () => {
  it("the futures card and the tournament card produce the IDENTICAL string", () => {
    // The same wire value, through the two independent call paths a reader sees
    // side by side on the landing page.
    const wire = "2026-12-31T15:00:00+00:00";
    const futuresCardLine = resolvesLabel(wire);
    const tournamentCardLine = formatTournamentTimingLabel(null, null, wire, NOW);

    expect(futuresCardLine).toBe(tournamentCardLine);
    expect(futuresCardLine).toBe(formatResolvesLabel(wire, NOW));
    expect(futuresCardLine).toMatch(/^Resolves /);
    // The year is the whole point of sharing the authority.
    expect(futuresCardLine).toContain("2026");
  });

  it("ONE file constructs the string, and it is the authority", () => {
    // UX-P054: this is now an equality, not a subset check. While an exemption
    // list existed the guard could only say "no NEW copies"; with the list empty
    // it says "no copies", which is the property that makes drift unrepresentable.
    expect(resolvesConstructionSites()).toEqual([AUTHORITY]);
  });

  it("the authority is one file, and it is the one named here", () => {
    expect(resolvesConstructionSites()).toContain(AUTHORITY);
  });

  it("the scan reaches `app/`, where the last legacy copy lived", () => {
    // The blind spot UX-P053 named. Proven by construction: the walk covers the
    // directory that contains the converted file, so a new copy there is caught.
    const roots = ["components", "lib", "app"];
    for (const r of roots) expect(fs.existsSync(path.join(FRONTEND, r))).toBe(true);
    expect(fs.existsSync(path.join(FRONTEND, "app/futures/[id]/page.tsx"))).toBe(true);
    // ...and that file no longer builds the string.
    const src = fs.readFileSync(path.join(FRONTEND, "app/futures/[id]/page.tsx"), "utf8");
    expect(CONSTRUCTION.test(stripComments(src))).toBe(false);
  });

  it("`components/FeedCard.tsx` no longer runs a ladder of its own", () => {
    // The converted debt. Pinned by name because it is the specific regression
    // #1719 fixed, and a generic "one site" assertion would not name it.
    const src = fs.readFileSync(path.join(FRONTEND, "components/FeedCard.tsx"), "utf8");
    expect(CONSTRUCTION.test(stripComments(src))).toBe(false);
    expect(stripComments(src)).not.toMatch(/function formatResolutionDate/);
  });

  it("`components/discover/utils.ts` builds no Resolves string of its own", () => {
    const src = fs.readFileSync(path.join(FRONTEND, "components/discover/utils.ts"), "utf8");
    expect(/["'`]Resolves\s/.test(stripComments(src))).toBe(false);
  });

  it("the guard tells a construction from a MENTION in documentation", () => {
    // Pinned because the first draft did not, and flagged three kernel prop-docs.
    expect(stripComments('/** state copy ("Resolves Sep 17"). */\nconst a = 1;')).not.toMatch(
      CONSTRUCTION,
    );
    expect(stripComments('// design: red "Resolves Sunday"\nconst b = 2;')).not.toMatch(
      CONSTRUCTION,
    );
    // ...and still catches a real one.
    expect(stripComments("return `Resolves ${d}`;")).toMatch(CONSTRUCTION);
    expect(stripComments('const s = "Resolves today";')).toMatch(CONSTRUCTION);
  });

  it("narrowing the pattern did NOT weaken it — both directions (gotcha #43)", () => {
    // UX-P054 widened the scan and narrowed the pattern in one change, so the
    // narrowing has to be proven, not asserted. CATCHES every real shape this
    // lane has actually seen drift:
    for (const real of [
      "return `Resolves ${d.toLocaleDateString([], { weekday: 'short' })}`;", // FeedCard rung 3
      "return `Resolves ${d.toLocaleDateString([], { month: 'short' })}`;", //   FeedCard rung 4
      '? `Resolves ${new Date(market.resolution_date).toLocaleDateString("en-US", {})}`', // detail page
      "return `Resolves ${end.toLocaleDateString([], { year: 'numeric' })}`;", // the authority
      'if (diffDays < 1) return "Resolves today";', //                          relative rungs
      'if (diffDays < 2) return "Resolves tomorrow";',
    ]) {
      expect(real).toMatch(CONSTRUCTION);
    }

    // ...and does NOT fire on the three sites that widening to `app/` newly
    // exposed, none of which implements a date rule. If any of these regressed
    // into a false positive the exemption list would grow back.
    for (const innocent of [
      '<FooterNote left="Each column = one FOMC meeting" right="Resolves post-FOMC" />',
      'title="Resolves daily. Highest-velocity section."',
      'stateLabel="Resolves Sep 17"',
      'angle={{ kind: "resolving_soon", label: "Resolves Sunday" }}',
    ]) {
      expect(innocent).not.toMatch(CONSTRUCTION);
    }
  });

  it("the three newly-scanned prose/fixture files stay clean in the real tree", () => {
    // The literals above are transcriptions; assert against the actual files so
    // the proof cannot rot if those pages are reworded.
    for (const f of ["app/economics/page.tsx", "app/kernels-preview/page.tsx"]) {
      const full = path.join(FRONTEND, f);
      if (!fs.existsSync(full)) continue;
      expect(CONSTRUCTION.test(stripComments(fs.readFileSync(full, "utf8")))).toBe(false);
    }
  });
});

describe("#1717 — what the futures card now prints", () => {
  const at = (iso: string) => {
    const spy = jest.spyOn(Date, "now").mockReturnValue(NOW);
    try {
      return resolvesLabel(iso);
    } finally {
      spy.mockRestore();
    }
  };

  it("prints a dated line beyond 7 days, where it used to print nothing", () => {
    // The real shape of the silent majority: 22 of 60 live cards resolved 7-30
    // days out, 13 in 1-4 months, 11 in 4-13 months.
    expect(at("2026-08-25T00:00:00+00:00")).toMatch(/^Resolves /);
    expect(at("2026-11-04T00:00:00+00:00")).toMatch(/^Resolves /);
    expect(at("2028-01-14T00:00:00+00:00")).toMatch(/^Resolves .*2028/);
  });

  it("leaves the inside-7-days ladder EXACTLY as it was", () => {
    // Both directions per gotcha #43: the 6 cards that were already correct must
    // be byte-identical, or the acceptance for the other 49 is unmeasurable.
    expect(at("2026-08-11T01:40:00+00:00")).toBe("Closes in 30m");
    expect(at("2026-08-11T20:10:00+00:00")).toBe("Closes in 19h");
    expect(at("2026-08-12T12:00:00+00:00")).toBe("Closes tomorrow");
    expect(at("2026-08-15T12:00:00+00:00")).toBe("Closes Aug 15");
  });

  it("says NOTHING about a date that has gone, and never 'Closes in 1m'", () => {
    // The declared behaviour change, and the trap inside it. `diffH < 1` is also
    // true of every negative diff, so removing the old "Resolved" branch without
    // deciding the past FIRST would print "Closes in 1m" about last year.
    expect(at("2026-08-10T00:00:00+00:00")).toBe("");
    expect(at("2024-02-11T00:00:00+00:00")).toBe("");
    expect(at("2026-08-11T01:09:00+00:00")).toBe("");
  });

  it("no longer infers settlement from a scheduled date merely passing", () => {
    // `resolution_date` is the SCHEDULED resolution, never an observed one
    // (reference_futures_markets_no_transition_timestamp). 8,609 open markets
    // carry a passed one; 2,260 of those are tier 1-2.
    expect(at("2025-12-19T00:00:00+00:00")).not.toBe("Resolved");
  });

  it("is silent on absent or malformed input rather than throwing", () => {
    expect(at("")).toBe("");
    expect(resolvesLabel(null)).toBe("");
    expect(resolvesLabel(undefined)).toBe("");
    expect(at("not-a-date")).toBe("");
  });
});
