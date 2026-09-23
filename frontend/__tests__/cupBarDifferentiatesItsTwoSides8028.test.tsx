/**
 * #8028 — a cup card's probability bar shows its two sides apart.
 *
 * ═══ THE DEFECT, AS A READER SAW IT ═══
 *
 * `/categories/golf` at 390px, 2026-09-22, BOTH live cup cards:
 *
 *     Presidents Cup   Team USA 81.5%  vs  Team World 14.5%   [one grey bar]
 *     Ryder Cup        Team Europe 53.5%  vs  Team USA 40.0%  [one grey bar]
 *
 * Read off the live DOM with `tools/cup-bar-colours-8028.mjs`, all four
 * segments resolved to `rgb(107, 114, 128)` / `bg-text-secondary`. A reader
 * could not see where one side ended and the other began. The Ryder Cup is the
 * worse of the two: a near coin-flip drawn as a single 93.5% block.
 *
 * ═══ WHY THE ASSERTION IS ON THE PAIR, NOT ON ONE SIDE ═══
 *
 * The old map was individually correct for every key it held — `"usa"` really
 * is blue. It shipped this bug anyway, because nothing anywhere asked the only
 * question that matters to a reader: **are these two segments different?** So
 * the assertions here are relational (`barA !== barB`) before they are nominal
 * (`bg-blue-500`). A future palette change is free; losing the split is not.
 *
 * ═══ THE SPECIMENS ARE THE TWO CUPS PRODUCTION SERVED ═══
 *
 * Both fixtures carry the names `GET /api/golf` returned at 2026-09-22 23:4xZ,
 * with the wire probabilities (0.815 / 0.145, 0.535 / 0.40) rather than the
 * rendered percentages — the `* 100` is the component's job. Team ORDER is
 * part of each fixture: the Ryder Cup leads with Europe, so a fix that assumed
 * "side A is always USA" fails here.
 */

import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import TournamentCard from "../components/TournamentCard";
import { normalizeCupSideName, cupSideColorFor, resolveCupSideColors } from "../lib/cupTeamSides";
import type { GolfTournament } from "../lib/types";

/** One `golfers[]` entry in the shape `routes/golf.py` promotes a team into. */
function teamEntry(name: string, probability: number, rank: number) {
  return {
    name,
    probability,
    rank,
    movement_24h: null,
    movement_is_dated: false,
    sources: ["kalshi"],
    opening_probability: null,
  };
}

function cup(key: string, name: string, golfers: ReturnType<typeof teamEntry>[]): GolfTournament {
  return {
    key,
    slug: key.replace(/_/g, "-"),
    name,
    tour: "pga",
    tour_label: "PGA Tour",
    location: "Medinah Country Club",
    venue: "Medinah Country Club",
    start_date: "2026-09-24",
    end_date: "2026-09-27",
    commence_time: "2026-09-24T12:00:00Z",
    resolution_date: null,
    is_major: false,
    is_marquee: true,
    schedule_status: "upcoming",
    source_count: 1,
    market_ids: [16757297],
    golfers,
    prop_markets: [],
    h2h_matchups: [],
  } as unknown as GolfTournament;
}

/** The two production specimens, exactly as `GET /api/golf` served them. */
const presidentsCup = () =>
  cup("presidents_cup", "Presidents Cup", [
    teamEntry("Team USA", 0.815, 1),
    teamEntry("Team World", 0.145, 2),
  ]);

const ryderCup = () =>
  cup("ryder_cup", "Ryder Cup", [
    teamEntry("Team Europe", 0.535, 1),
    teamEntry("Team USA", 0.4, 2),
  ]);

const render = (t: GolfTournament) => renderToStaticMarkup(<TournamentCard tournament={t} />);

/**
 * The two bar segments' classes and widths, IN RENDER ORDER.
 *
 * Anchored on the bar container's own class string rather than on "the last two
 * divs", so a layout change that adds a sibling cannot silently make this read
 * something else — and an empty result fails the length assertion below rather
 * than passing as "no identical colours found".
 */
function barSegments(markup: string): Array<{ cls: string; width: string }> {
  // `[\s\S]` rather than the `s` flag: the tsconfig target predates dotAll.
  const bar = /<div class="flex h-2 rounded-full overflow-hidden">([\s\S]*?)<\/div><\/div>/.exec(markup);
  if (!bar) return [];
  const out: Array<{ cls: string; width: string }> = [];
  const re = /<div class="([^"]*) transition-all" style="width:([^"]*)"/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(bar[1])) !== null) out.push({ cls: m[1], width: m[2] });
  return out;
}

/** The two team-name divs' classes, in render order. */
function nameClasses(markup: string): string[] {
  const re = /<div class="text-xs font-semibold ([^"]*)">/g;
  const out: string[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(markup)) !== null) out.push(m[1]);
  return out;
}

// ---------------------------------------------------------------------------

describe("#8028 — the bar shows the split, on both cups production served", () => {
  test("THE PRESIDENTS CUP SPECIMEN: Team USA and Team World paint different bars", () => {
    const segs = barSegments(render(presidentsCup()));

    expect(segs).toHaveLength(2);
    expect(segs[0].cls).not.toEqual(segs[1].cls);
    // Nominal, second: USA is the blue side, World folds onto International.
    expect(segs[0].cls).toBe("bg-blue-500");
    expect(segs[1].cls).toBe("bg-emerald-500");
  });

  test("THE RYDER CUP SPECIMEN: Europe leads, so side A is not USA", () => {
    const segs = barSegments(render(ryderCup()));

    expect(segs).toHaveLength(2);
    expect(segs[0].cls).not.toEqual(segs[1].cls);
    expect(segs[0].cls).toBe("bg-amber-500");
    expect(segs[1].cls).toBe("bg-blue-500");
  });

  test("the team names carry their side's colour, not body text", () => {
    // The other half of the filing: both names rendered `text-text-primary`.
    expect(nameClasses(render(presidentsCup()))).toEqual(["text-blue-800", "text-emerald-800"]);
    expect(nameClasses(render(ryderCup()))).toEqual(["text-amber-800", "text-blue-800"]);
  });

  test("THE STRAWMAN: the pre-fix lookup would fail every one of these", () => {
    // Without this, the tests above pass for a component that hardcodes two
    // colours. This is the OLD key set, asked the OLD way — raw lowercased
    // name, no folding — and it proves the specimens really do exercise the
    // prefix that broke them.
    const oldKeys = ["usa", "united states", "u.s.", "europe", "international", "great britain & ireland"];
    for (const served of ["Team USA", "Team World", "Team Europe"]) {
      expect(oldKeys).not.toContain(served.toLowerCase());
    }
    // ...and the new lookup resolves all three.
    for (const served of ["Team USA", "Team World", "Team Europe"]) {
      expect(cupSideColorFor(served)).not.toBeNull();
    }
  });

  test("the rider: the width is the printed figure, not 14.499999999999998%", () => {
    expect(barSegments(render(presidentsCup())).map((s) => s.width)).toEqual(["81.5%", "14.5%"]);
    expect(barSegments(render(ryderCup())).map((s) => s.width)).toEqual(["53.5%", "40.0%"]);
  });

  test("...and on the LEFT side too, which the two live specimens cannot show", () => {
    // Measured, and it changed this test: on both production pairs side A's raw
    // product is already exact (`0.815 * 100 === 81.5`, `0.535 * 100 === 53.5`),
    // so dropping `toFixed` from side A alone is invisible there — a mutation
    // that did exactly that SURVIVED the case above. The artifact is symmetric;
    // only these specimens are not. Same sides, probabilities swapped, so the
    // left segment is the one carrying it.
    const flipped = cup("presidents_cup", "Presidents Cup", [
      teamEntry("Team World", 0.145, 1),
      teamEntry("Team USA", 0.815, 2),
    ]);

    expect(barSegments(render(flipped)).map((s) => s.width)).toEqual(["14.5%", "81.5%"]);
  });
});

describe("#8028 — an unrecognised side still shows a reader the split", () => {
  test("two unknown sides get two DIFFERENT neutrals, not one grey block", () => {
    // The defect class, as the thing that cannot return. A colour map is never
    // complete; the day a cup names a side this file has not heard of, the bar
    // must still divide.
    const segs = barSegments(
      render(cup("walker_cup", "Walker Cup", [
        teamEntry("Team Atlantis", 0.5, 1),
        teamEntry("Team Pacifica", 0.5, 2),
      ])),
    );

    expect(segs).toHaveLength(2);
    expect(segs[0].cls).not.toEqual(segs[1].cls);
    // Neutral, not a borrowed team identity.
    expect(segs.map((s) => s.cls)).toEqual(["bg-text-secondary", "bg-text-muted"]);
  });

  test("one known side keeps its colour and the unknown one cannot collide", () => {
    const segs = barSegments(
      render(cup("ryder_cup", "Ryder Cup", [
        teamEntry("Team USA", 0.6, 1),
        teamEntry("Team Atlantis", 0.4, 2),
      ])),
    );

    expect(segs[0].cls).toBe("bg-blue-500");
    expect(segs[1].cls).not.toBe("bg-blue-500");
  });

  test("two names that fold to ONE side do not paint one block either", () => {
    // `select_team_side_matchup` refuses such a pair upstream, but `CupCard`
    // reads `golfers[]` and does not go through it.
    const [a, b] = resolveCupSideColors("USA", "Team U.S.A.");
    expect(a.bar).not.toEqual(b.bar);
  });

  test("an absent name never borrows a team's colour", () => {
    expect(cupSideColorFor(null)).toBeNull();
    expect(cupSideColorFor("")).toBeNull();
    expect(cupSideColorFor("   ")).toBeNull();
  });
});

describe("#8028 — the folding is the backend's, character for character", () => {
  test.each([
    ["Team USA", "usa"],
    ["team usa", "usa"],
    ["U.S.A.", "usa"],
    ["U.S.", "us"],
    ["Team World", "world"],
    ["Great Britain & Ireland", "great britain and ireland"],
    ["GB and I", "gb and i"],
    ["  Team   Europe  ", "europe"],
  ])("%s folds to %s", (served, folded) => {
    expect(normalizeCupSideName(served)).toBe(folded);
  });

  test("the prefix is stripped only at the START, and only as a whole word", () => {
    // "Teamsters" is not a cup side, but a `replace(/team/,"")` would make it
    // one — this pins the anchor and the \s+ that the backend's regex carries.
    expect(normalizeCupSideName("Teamsters")).toBe("teamsters");
    expect(normalizeCupSideName("Dream Team")).toBe("dream team");
  });
});

describe("#8028 — every side the backend recognises has a colour here", () => {
  /**
   * `TEAM_SIDE_NAMES` in `backend/app/utils/golf_event_format.py` is the
   * authority for what counts as a cup side — it is the predicate that decides
   * which matchup gets promoted onto this card in the first place. A name added
   * there and not coloured here is #8028 again, one release later, so this
   * reads the Python source rather than trusting a copied list.
   */
  const SOURCE = join(process.cwd(), "..", "backend", "app", "utils", "golf_event_format.py");

  function backendTeamSideNames(): string[] {
    const src = readFileSync(SOURCE, "utf8");
    const block = /TEAM_SIDE_NAMES:\s*Final\[frozenset\[str\]\]\s*=\s*frozenset\(\{([\s\S]*?)\}\)/.exec(src);
    if (!block) throw new Error(`TEAM_SIDE_NAMES not found in ${SOURCE} — this test is blind, not passing`);
    // Comment lines inside the set would otherwise contribute quoted words.
    const body = block[1]
      .split("\n")
      .map((l) => l.replace(/#.*$/, ""))
      .join("\n");
    return [...body.matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  }

  test("the reader is alive: it finds the names we know are in that file", () => {
    // Without this the suite below passes vacuously on an empty parse — the
    // failure mode that makes a broken instrument read as a clean result.
    const names = backendTeamSideNames();
    expect(names.length).toBeGreaterThanOrEqual(8);
    expect(names).toEqual(expect.arrayContaining(["usa", "world", "europe", "international"]));
    expect(names).not.toContain("great britain and ireland".toUpperCase());
  });

  test.each(backendTeamSideNames())("backend side %s resolves to a team colour", (name) => {
    const color = cupSideColorFor(name);
    expect(color).not.toBeNull();
    // A neutral would mean "recognised as a side by the backend, painted as an
    // unknown here" — which is the bug, not a pass.
    expect(color!.bar).not.toBe("bg-text-secondary");
    expect(color!.bar).not.toBe("bg-text-muted");
  });
});
