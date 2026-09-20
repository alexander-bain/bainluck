/**
 * #5666 — the golf movers strip, the LAST surface of the points-vs-percent
 * family; and the class guard that closes the family for good.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `/golf`, production 2026-09-12 17:21Z, 390px:
 *
 *     BIGGEST MOVERS (24H)
 *     ▲ 8.5%        ▲ 7.9%
 *
 * 8.5 POINTS printed as `8.5%`. `formatMovementPoints` returns POINTS —
 * `movement_24h` is a probability delta in 0-1 units, so `* 100` is percentage
 * POINTS — and the literal beside it said percent. A golfer who went 41.9% ->
 * 50.4% moved 8.5 points; "▲ 8.5%" reads as an 8.5% relative gain, about 3.6
 * points, under half the real move.
 *
 * ═══ THE FAMILY, AND WHY THIS FILE IS THE LAST ONE ═══
 *
 *   #4066  Discover golf pill        "18%"     -> "18 pts"        live
 *   #5619  eight backend sentences   "38.0"    -> "38 points"     live
 *   #5608  search chip               "+10.0%"  -> "+10 points"    live
 *   #5623  tournament card           "+9.7%"   -> "+9.7 pts"      live
 *   #5669  team page, TWO sites      "9.7%"    -> "9.7 pts"       at the desk
 *   #5666  this strip                "8.5%"    -> "8.5 pts"       here
 *
 * Six surfaces, one substrate fact, six independent literals. They drifted
 * because each call site spelled the unit itself. Part 2 below is the check
 * that makes a seventh impossible to add quietly: it is a CLASS scan over
 * `app/` and `components/`, not an assertion about this component.
 *
 * ═══ WHAT THIS COST IN ANOTHER SUITE'S FILE, AND WHAT THAT OWED ═══
 *
 * `golfMoversPrecisionUxp274.test.tsx` scrapes this badge through `magnitudeOf`,
 * whose regex hard-required the trailing `%`. Moving the strip to ` pts` reddened
 * **11 of its 20 arms** immediately — every one of them on the scrape, none on a
 * claim. So the helper moved with it, and editing another suite's guard owes a
 * mutation proving it still catches its OWN bug: restoring the original
 * whole-point `Math.round(movement_24h * 100)` arithmetic that UX-P274 was filed
 * on reddens **11 of 20**, control green. The scrape moved; the subject did not.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import fs from "node:fs";
import path from "node:path";

import { MoversStrip } from "../components/golf/MoversStrip";
import type { GolfMover } from "@/lib/types";

function mover(name: string, movement_24h: number, probability = 0.085): GolfMover {
  return {
    name,
    tournament_key: "amgen_irish_open",
    tournament_name: "Amgen Irish Open",
    movement_24h,
    probability,
  };
}

const render = (movers: GolfMover[]) =>
  renderToStaticMarkup(<MoversStrip movers={movers} />);

/** Every badge's plain text, in order. Raises if a badge grew a child element. */
function badges(markup: string): string[] {
  const out: string[] = [];
  const re = /<span[^>]*data-mover-delta="[^"]*"[^>]*>([^<]*)<\/span>/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(markup)) !== null) out.push(m[1].trim());
  expect(out).toHaveLength((markup.match(/data-mover-delta=/g) ?? []).length);
  return out;
}

// ---------------------------------------------------------------------------
// Part 1 — the rendered badge, both directions
// ---------------------------------------------------------------------------

describe("#5666 part 1 — the strip prints POINTS and says so", () => {
  test("the production specimen: a +0.085 mover reads '▲ 8.5 pts', not '8.5%'", () => {
    const [badge] = badges(render([mover("Shane Lowry", 0.085)]));
    expect(badge).toBe("▲ 8.5 pts");
    expect(badge).not.toContain("%");
  });

  test("a faller keeps its arrow and its unit", () => {
    const [badge] = badges(render([mover("Joaquin Niemann", -0.079)]));
    expect(badge).toBe("▼ 7.9 pts");
    expect(badge).not.toContain("%");
  });

  test("NO badge on the strip carries a percent sign", () => {
    // The whole strip, not one badge: a partial fix that moved the up arm and
    // left the down arm is exactly the shape this family keeps producing.
    const markup = render([
      mover("Shane Lowry", 0.085),
      mover("Joaquin Niemann", -0.079),
      mover("Rory McIlroy", 0.012),
      mover("Marco Penge", -0.005),
    ]);
    const all = badges(markup);
    expect(all).toHaveLength(4);
    for (const b of all) expect(b).not.toContain("%");
    expect(all.every((b) => b.endsWith(" pts"))).toBe(true);
  });

  test("the strip still DRAWS badges — this guard cannot pass by rendering nothing", () => {
    // gotcha #43's other direction. Every assertion above is satisfied by a
    // component that emits no badge at all.
    expect(badges(render([mover("Shane Lowry", 0.085)]))).toHaveLength(1);
  });

  test("WIDTH is unchanged by the unit: one decimal, trailing zero kept", () => {
    expect(badges(render([mover("Even Mover", 0.09)]))[0]).toBe("▲ 9.0 pts");
    expect(badges(render([mover("Ten Pointer", 0.1)]))[0]).toBe("▲ 10.0 pts");
  });

  test("the half-point floor the backend admits still prints, and prints its sign", () => {
    // `routes/golf.py` admits a mover at abs(movement_24h) >= 0.005. Under the
    // pre-UX-P274 `Math.round` that smallest DOWNWARD move printed "0%" in red.
    expect(badges(render([mover("Marco Penge", -0.005)]))[0]).toBe("▼ 0.5 pts");
  });
});

// ---------------------------------------------------------------------------
// Part 2 — the class: no surface puts a '%' against the points formatter
// ---------------------------------------------------------------------------

describe("#5666 part 2 — the family is closed: no seventh surface can spell it wrong", () => {
  const ROOT = path.join(__dirname, "..");
  const DIRS = ["app", "components"];

  /**
   * The family's source signature: the POINTS formatter's output with a `%`
   * next to it. Matches the RENDER, not prose — an earlier draft of the #5669
   * guard asserted `not.toContain("% today")` over a whole file and reddened on
   * a COMMENT quoting the old defect as history. A guard that fires on its own
   * incident notes gets deleted by whoever trips over it.
   */
  const PCT_AGAINST_POINTS = /\{formatMovementPoints\([^)]*\)\}\s*%/;

  function walk(dir: string, out: string[] = []): string[] {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) {
        if (e.name === "node_modules" || e.name === ".next") continue;
        walk(p, out);
      } else if (/\.tsx?$/.test(e.name)) out.push(p);
    }
    return out;
  }

  const files = DIRS.flatMap((d) => walk(path.join(ROOT, d)));

  test("scans a real population, so the assertion below is about something", () => {
    // Without this, a broken walk() makes the scan vacuously green.
    expect(files.length).toBeGreaterThan(200);
    expect(files.some((f) => f.endsWith(path.join("golf", "MoversStrip.tsx")))).toBe(true);
    expect(files.some((f) => f.includes("team") && f.endsWith("page.tsx"))).toBe(true);
  });

  test("the population actually USES the formatter, so the scan has live call sites to judge", () => {
    // A scan for a misuse is vacuous if nobody uses the thing at all. This is
    // the arm that fails if `formatMovementPoints` is ever renamed and the
    // pattern above silently stops matching anything anywhere.
    const users = files.filter((f) =>
      /\{formatMovementPoints\(/.test(fs.readFileSync(f, "utf8")),
    );
    expect(users.length).toBeGreaterThanOrEqual(3);
  });

  /**
   * THE ONE SURFACE STILL SPELLING IT WRONG, NAMED RATHER THAN EXCLUDED.
   *
   * This scan is what found surfaces SEVEN, EIGHT and NINE — the family was
   * believed to be six. Two of the three were Discover feed cards and are fixed
   * in this commit. The third is `components/futures/OutcomeRow.tsx`, which
   * standing notice 41 names for UX by name ("EventDetailView, OutcomeRow,
   * SearchView, FuturesDetailView and their web twins are UX single-owned").
   * Fable-5's ruling of 2026-09-12 10:06AM PT gave this lane #5666 and #5669,
   * not a licence over ux's file set, so it is FILED and ROUTED, not edited here.
   *
   * SUBSET, NOT EXACT EQUALITY, AND THAT IS A DELIBERATE CLIMBDOWN — kept after
   * the reason for it expired, on purpose.
   *
   * The first draft asserted exact equality on the `typecheck-baseline`
   * precedent (gotcha #10): one offender more fails, one fewer also fails. That
   * is the stronger instrument. It was wrong at the time because the list spanned
   * two of this lane's own in-flight branches — the team page was repaired by
   * #5669, then unmerged — so an exact list would have reddened master for
   * whichever of the two merged second. #5669 has since landed and this branch is
   * rebased onto it, so that particular hazard is gone and its entry is deleted
   * below.
   *
   * It stays SUBSET anyway, for the remaining entry, which belongs to ANOTHER
   * LANE. Exact equality would fail ux's repair PR until ux also edited this
   * file — a tripwire in someone else's path that they never agreed to, and the
   * usual way a guard gets deleted rather than satisfied. The typecheck ratchet
   * can be that strict because it ships a documented command to re-baseline; this
   * has no such affordance.
   *
   * The property that matters survives either way: a TENTH surface — a new call
   * site spelling the unit itself — still fails here. What is given up is
   * noticing a stale entry, so #5686 carries the instruction to delete it.
   */
  /**
   * EMPTY, and that is the whole point — #5659 (ux/1369) executing the deletion
   * this list was created carrying.
   *
   * `components/futures/OutcomeRow.tsx` was the single entry, routed to ux as
   * #5686 under notice 41. #5686 merged as `c356d1e1c` and its after-LOOK was
   * paid on production on 2026-09-12; the file has printed
   * `{formatMovementPoints(change as number)} pts` ever since. The entry then
   * sat here for a week permitting an offender that no longer existed — exactly
   * the stale entry the SUBSET climbdown above admits it can no longer notice.
   *
   * With the list empty, SUBSET and exact equality coincide, so the scan is now
   * as strict as the first draft wanted to be, with none of the cross-lane
   * tripwire that made strictness wrong at the time: the file it would have
   * tripped is repaired, and it is this lane's own.
   */
  const KNOWN_REMAINING: string[] = [];

  test("every remaining '%'-against-points site is the one known file routed to ux", () => {
    const offenders: string[] = [];
    for (const f of files) {
      fs.readFileSync(f, "utf8")
        .split("\n")
        .forEach((line, i) => {
          if (PCT_AGAINST_POINTS.test(line)) {
            offenders.push(`${path.relative(ROOT, f)}:${i + 1}  ${line.trim()}`);
          }
        });
    }
    const unexpected = offenders.filter(
      (o) => !KNOWN_REMAINING.some((k) => o.startsWith(`${k}:`)),
    );
    expect(unexpected).toEqual([]);
  });

  test("the three surfaces THIS commit repairs print ' pts' and carry no percent against the formatter", () => {
    // The positive half. Without it the scan above is satisfied by deleting every
    // call site rather than by repairing one.
    //
    // Per-file expected text rather than one pattern: `MoversStrip` binds the
    // formatter to `delta` first and renders `{delta} pts`, so a single regex
    // over `{formatMovementPoints(...)}` silently misses it — which is exactly
    // what the first draft of this arm did, and it failed loudly rather than
    // passing on two of three. A shape assumed across call sites is the same
    // mistake the family itself is made of.
    const repaired: Array<[string, string]> = [
      ["components/golf/MoversStrip.tsx", "{delta} pts"],
      ["components/FeedCard.tsx", "{formatMovementPoints(leader.movement)} pts"],
      ["components/CombinedFeedCard.tsx", "{formatMovementPoints(outcome.bestMovement)} pts"],
    ];
    for (const [rel, expected] of repaired) {
      const src = fs.readFileSync(path.join(ROOT, rel), "utf8");
      expect(PCT_AGAINST_POINTS.test(src)).toBe(false);
      expect(src).toContain(expected);
    }
  });

  /**
   * ── #5659: THE HOLE THIS SCAN HAD, AND WHY A TENTH SURFACE GOT THROUGH ──
   *
   * `PCT_AGAINST_POINTS` matches the formatter's output with a `%` NEXT TO IT.
   * Every surface in the family above spelled the unit WRONG, so that pattern
   * described all six of them and the file concluded the family was closed.
   *
   * It cannot see a surface that spells no unit AT ALL, and a bare number is
   * the one variant where the reader cannot even guess: `▲45.0` in a column
   * between a label and `89%`. Three such sites were live when #5659 was
   * measured — `QuantityGroup` (filed), `TeamChampionshipPath` and
   * `FuturesCard` (found by this scan, never filed) — and all three sat in the
   * scanned population the whole time, green.
   *
   * So the family's real invariant was never "no percent against the
   * formatter". It is: THE FORMATTER'S OUTPUT IS NEVER RENDERED WITHOUT ITS
   * UNIT. That is what this scans, and it subsumes the `%` arm — a `%` is not
   * in `UNIT`, so a regression to `{formatMovementPoints(x)}%` fails here too.
   *
   * BOUND SITES ARE THIS SCAN'S OWN BLIND SPOT, AND ARE NAMED RATHER THAN
   * ASSUMED. A call site that binds the result first
   * (`const delta = formatMovementPoints(...)`) renders the IDENTIFIER, on a
   * line this pattern never sees — which is how `FuturesCard`'s `↑ 9.7` hid
   * from a text scan for a whole family's worth of repairs. They are excluded
   * here and pinned individually below, and the exclusion is asserted to be
   * exactly two files, so a third bound site cannot appear silently.
   */
  const RENDERS_FORMATTER = /formatMovementPoints\(/;
  const BINDS_FORMATTER = /(?:const|let|var)\s+\w+\s*=\s*formatMovementPoints\(/;
  /** The call's `)`, an optional closing `}`, then the unit. */
  const UNIT_AFTER_CALL = /formatMovementPoints\([^)]*\)[^)]*\)?\s*\}?\s*(?:pts|points?)\b/;

  test("no surface renders the points formatter without a unit", () => {
    const offenders: string[] = [];
    const bound: string[] = [];
    for (const f of files) {
      fs.readFileSync(f, "utf8")
        .split("\n")
        .forEach((line, i) => {
          if (!RENDERS_FORMATTER.test(line)) return;
          const at = `${path.relative(ROOT, f)}:${i + 1}  ${line.trim()}`;
          if (BINDS_FORMATTER.test(line)) return void bound.push(at);
          if (!UNIT_AFTER_CALL.test(line)) offenders.push(at);
        });
    }
    expect(offenders).toEqual([]);
    // The blind spot stays exactly as wide as the two sites pinned below.
    expect(bound.map((b) => b.split(":")[0]).sort()).toEqual([
      "components/discover/FuturesCard.tsx",
      "components/golf/MoversStrip.tsx",
    ]);
  });

  test("the scan has unit-bearing render sites to judge, so it is not vacuously green", () => {
    // gotcha #43 / the vacuity arm: every assertion above is satisfied by a
    // population in which nothing renders the formatter at all.
    const rendering = files.filter((f) =>
      fs
        .readFileSync(f, "utf8")
        .split("\n")
        .some((l) => RENDERS_FORMATTER.test(l) && !BINDS_FORMATTER.test(l)),
    );
    expect(rendering.length).toBeGreaterThanOrEqual(6);
  });

  test("UNIT_AFTER_CALL rejects the three shapes #5659 was actually made of", () => {
    // The pattern is the instrument; an instrument that cannot fail is not one.
    // These are the literal pre-fix lines from the three repaired files.
    expect(UNIT_AFTER_CALL.test("{formatMovementPoints(entry.movement)}")).toBe(false);
    expect(
      UNIT_AFTER_CALL.test('`${(movement ?? 0) > 0 ? "▲" : "▼"}${formatMovementPoints(movement)}`'),
    ).toBe(false);
    expect(UNIT_AFTER_CALL.test("{formatMovementPoints(x)}%")).toBe(false);
    // ...and accepts the repaired shapes, including the two that carry trailing
    // prose and the aria-label that spells the unit out in full.
    expect(UNIT_AFTER_CALL.test("{formatMovementPoints(entry.movement)} pts")).toBe(true);
    expect(UNIT_AFTER_CALL.test("{formatMovementPoints(headline.movement)} pts today")).toBe(true);
    expect(UNIT_AFTER_CALL.test("{formatMovementPoints(change as number)} pts")).toBe(true);
    expect(UNIT_AFTER_CALL.test("`${formatMovementPoints(rung.movement)} points`")).toBe(true);
  });

  test("the two BOUND sites render their identifier with the unit", () => {
    // What earns the exclusion above. Asserted on the rendered string each file
    // builds, not on the binding — the binding was never the defect.
    const strip = fs.readFileSync(path.join(ROOT, "components/golf/MoversStrip.tsx"), "utf8");
    expect(strip).toContain("const delta = formatMovementPoints(mover.movement_24h);");
    expect(strip).toContain("{delta} pts");

    const card = fs.readFileSync(path.join(ROOT, "components/discover/FuturesCard.tsx"), "utf8");
    expect(card).toContain("const movementDisplay = formatMovementPoints(movementVal);");
    expect(card).toContain('${movementDisplay} pts`');
  });

  test("MoversStrip's `delta` really is the points formatter, so its ' pts' is not a coincidence", () => {
    // The arm above accepts `{delta} pts` on trust; this is what earns it. Part 1
    // renders the component for real, so this only has to pin the binding.
    const src = fs.readFileSync(path.join(ROOT, "components/golf/MoversStrip.tsx"), "utf8");
    expect(src).toContain("const delta = formatMovementPoints(mover.movement_24h);");
  });
});
