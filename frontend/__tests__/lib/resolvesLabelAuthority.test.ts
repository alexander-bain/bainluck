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
      if (/["'`]Resolves\s/.test(stripComments(fs.readFileSync(full, "utf8")))) {
        hits.push(path.relative(FRONTEND, full));
      }
    }
  };
  for (const root of ["components", "lib"]) walk(path.join(FRONTEND, root));
  return [...new Set(hits)].sort();
}

/** The authority itself — the one file that is SUPPOSED to build the string. */
const AUTHORITY = "lib/gameTimeLabel.ts";

/**
 * RECORDED DEBT, not an allowlist that grows quietly.
 *
 * This predates the authority and is NOT restyled here, deliberately: converting
 * it would change what another surface prints in the commit that fixes the
 * Discover card, which is the unmeasured-restyle failure UX-P045 named. It is a
 * real inconsistency and it is filed on #1717.
 *
 *  - `components/FeedCard.tsx` runs its own ladder ("Resolves today" /
 *    "Resolves tomorrow" / weekday / month-day) and NEVER prints a year, so a
 *    2028 market reads as this week — the exact misreading #1708 called out.
 *
 * Also filed and NOT scanned, because it sits outside `components/` and `lib/`:
 * `app/futures/[id]/page.tsx:527` inlines a third `toLocaleDateString`. Named
 * here so the next reader knows the guard's blind spot rather than inferring
 * from its silence that no third copy exists.
 */
const RECORDED_LEGACY_SITES = ["components/FeedCard.tsx"];

/** Every file allowed to contain the construction today. */
const PERMITTED = [AUTHORITY, ...RECORDED_LEGACY_SITES];

describe("#1717 — one formatting authority for 'Resolves <date>'", () => {
  it("the futures card and the tournament card produce the IDENTICAL string", () => {
    // The same wire value, through the two independent call paths a reader sees
    // side by side on the landing page.
    const wire = "2026-12-31T15:00:00+00:00";
    const futuresCardLine = resolvesLabel(wire);
    const tournamentCardLine = formatTournamentTimingLabel(null, wire, NOW);

    expect(futuresCardLine).toBe(tournamentCardLine);
    expect(futuresCardLine).toBe(formatResolvesLabel(wire, NOW));
    expect(futuresCardLine).toMatch(/^Resolves /);
    // The year is the whole point of sharing the authority.
    expect(futuresCardLine).toContain("2026");
  });

  it("only the authority constructs the string; every other site is recorded debt", () => {
    const sites = resolvesConstructionSites();
    const unrecorded = sites.filter((s) => !PERMITTED.includes(s));
    expect(unrecorded).toEqual([]);
  });

  it("the authority is one file, and it is the one named here", () => {
    expect(resolvesConstructionSites()).toContain(AUTHORITY);
  });

  it("the recorded debt still exists — a stale exemption is its own drift", () => {
    // If FeedCard is ever converted, this fails and the exemption gets deleted
    // rather than quietly outliving its reason (the #1525 lesson).
    const sites = resolvesConstructionSites();
    for (const known of RECORDED_LEGACY_SITES) {
      expect(sites).toContain(known);
    }
  });

  it("`components/discover/utils.ts` builds no Resolves string of its own", () => {
    const src = fs.readFileSync(path.join(FRONTEND, "components/discover/utils.ts"), "utf8");
    expect(/["'`]Resolves\s/.test(stripComments(src))).toBe(false);
  });

  it("the guard tells a construction from a MENTION in documentation", () => {
    // Pinned because the first draft did not, and flagged three kernel prop-docs.
    expect(stripComments('/** state copy ("Resolves Sep 17"). */\nconst a = 1;')).not.toMatch(
      /["'`]Resolves\s/,
    );
    expect(stripComments('// design: red "Resolves Sunday"\nconst b = 2;')).not.toMatch(
      /["'`]Resolves\s/,
    );
    // ...and still catches a real one.
    expect(stripComments('return `Resolves ${d}`;')).toMatch(/["'`]Resolves\s/);
    expect(stripComments('const s = "Resolves today";')).toMatch(/["'`]Resolves\s/);
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
