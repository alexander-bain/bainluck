/**
 * UX-P142 — Alex's four findings from the live page on 2026-08-27, each
 * asserted AT THE RENDER over the REAL production payload.
 *
 *   (a) "The draw exists but the page shows none."
 *   (b) "The headline contender chart has NO x-axis."
 *   (c) "Players have no images."
 *   (d) "The Men's/Women's pills sit too close to the line above."
 *
 * Every one of them was, at root, a thing that no test could see. The x-axis
 * had unit tests over `axisTicks` and none over the chart drawn from the
 * shipped payload; the pills had no test anywhere in the repo; the draw had no
 * assertion that a released draw reaches a match list. So the guards here are
 * deliberately end-of-pipeline: the committed register -> the backend's own
 * `build_*` output (captured in `docs/mocks/us-open/payload-2026-08-27.json`)
 * -> `renderToStaticMarkup` of the shipped components -> a string search for
 * the thing Alex could not find.
 *
 * `reference_plant_must_hit_the_render`: a pure-library guard stays green the
 * day the component stops printing the feature.
 */

import fs from "node:fs";
import path from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ContenderChart from "@/components/tournament/ContenderChart";
import DrawToggle, { DRAW_TOGGLE_PADDING } from "@/components/tournament/DrawToggle";
import PlayerAvatar, { avatarKind, initialsOf } from "@/components/tournament/PlayerAvatar";
import PlayoffGrid from "@/components/tournament/PlayoffGrid";
import TournamentBoard from "@/components/tournament/TournamentBoard";
import TournamentMatches from "@/components/tournament/TournamentMatches";
import { defaultSelection } from "@/lib/contenderChart";
import { buildMatchList, matchDetailNote, type TitleChances } from "@/lib/matchList";
import { readPlayoffGrid } from "@/lib/playoffGrid";
import { slateRowFreshnessLabel, type SlateMatch } from "@/lib/slate";
import type { TournamentPayload } from "@/lib/tournament";

const PAYLOAD_PATH = path.join(
  __dirname,
  "..",
  "..",
  "..",
  "docs",
  "mocks",
  "us-open",
  "payload-2026-08-27.json"
);

const payload: TournamentPayload = JSON.parse(fs.readFileSync(PAYLOAD_PATH, "utf8"));

function matchesFor(draw: string) {
  const board = payload.boards.find((entry) => entry.draw === draw)!;
  const titleChances: TitleChances = {};
  for (const row of board.rows) titleChances[row.entity_key] = row.probability;
  return buildMatchList({
    slate: (payload.slate?.matches ?? []).filter((match) => match.draw === draw),
    rounds: [],
    titleChances,
    broadcasts: payload.broadcasts,
  });
}

// ---------------------------------------------------------------------------
// (a) THE REAL DRAW
// ---------------------------------------------------------------------------

describe("(a) the released main draw reaches the page", () => {
  it("the payload has the draw latched", () => {
    expect(payload.draw_released).toBe(true);
  });

  it("carries real R128 fixtures on BOTH draws, not an empty list", () => {
    const r128 = (payload.slate?.matches ?? []).filter((m) => m.round === "R128");
    expect(r128.length).toBeGreaterThanOrEqual(90);
    for (const draw of ["mens-singles", "womens-singles"]) {
      expect(r128.filter((m) => m.draw === draw).length).toBeGreaterThanOrEqual(45);
    }
  });

  it("every R128 fixture names two real players — never Yes/No, never a blank", () => {
    const r128 = (payload.slate?.matches ?? []).filter((m) => m.round === "R128");
    for (const match of r128) {
      expect(match.sides).toHaveLength(2);
      for (const side of match.sides) {
        expect(side.display_name).toBeTruthy();
        expect(side.display_name).not.toMatch(/^(Yes|No|TBD|Bye|Qualifier)$/i);
      }
      expect(match.sides[0].entity_key).not.toBe(match.sides[1].entity_key);
    }
  });

  it("RENDERS them: the match list prints a Round of 128 pill and its cards", () => {
    const entries = matchesFor("mens-singles");
    // The pill strip must SAY the draw is there, on the default view. Today
    // the list still opens on Qualifying — 17 of those are genuinely upcoming
    // this afternoon, and "the earliest round still being played" is UX-P138's
    // rule and the right one — so the count on the R128 pill is what tells a
    // reader the draw landed.
    const defaultView = renderToStaticMarkup(
      <TournamentMatches entries={entries} notice={null} />
    );
    expect(defaultView).toContain('data-testid="match-round-pill" data-round="R128"');
    expect(defaultView).toMatch(/data-round="R128"[^>]*>R128<span[^>]*>4\d</);

    const html = renderToStaticMarkup(
      <TournamentMatches entries={entries} initialRound="R128" initialExpanded notice={null} />
    );
    expect(html).toContain('data-testid="match-round-heading"');
    expect(html).toContain("Round of 128");
    const cards = (html.match(/data-testid="match-row" data-match="[^"]*" data-round="R128"/g) ?? [])
      .length;
    expect(cards).toBeGreaterThanOrEqual(45);
    // A name Alex can check against any published draw.
    expect(html).toContain("Alcaraz");
  });

  it("an UNPRICED fixture says so, and does NOT claim two prices disagree", () => {
    const unpriced = (payload.slate?.matches ?? []).find((m) => m.priced === false)!;
    expect(unpriced).toBeDefined();
    expect(unpriced.price_state).toBe("unpriced");
    expect(slateRowFreshnessLabel(unpriced)).toBe("No market yet");

    const note = matchDetailNote({
      coherent: false,
      decided: false,
      score: null,
      priced: false,
      sides: [{} as never, {} as never],
    });
    expect(note).toContain("Nobody is quoting this match yet");
    expect(note).not.toContain("do not agree");
  });

  it("REFUSES to invent a draw sheet: no fixture carries a draw slot", () => {
    // ESPN publishes pairings, not positions. `bracket` stays empty rather
    // than fabricating which first-round winner meets which — the claim that
    // would look exactly like a real draw and be unverifiable.
    for (const slots of Object.values(payload.bracket ?? {})) {
      expect(slots).toHaveLength(0);
    }
  });
});

// ---------------------------------------------------------------------------
// (b) THE X-AXIS
// ---------------------------------------------------------------------------

describe("(b) the headline chart has an x-axis on the real payload", () => {
  it.each(["mens-singles", "womens-singles"])("%s draws dated ticks", (draw) => {
    const board = payload.boards.find((entry) => entry.draw === draw)!;
    const html = renderToStaticMarkup(
      <ContenderChart
        rows={board.rows}
        draw={draw}
        selection={defaultSelection(board.rows)}
        onToggle={() => {}}
      />
    );
    // The axis strip, its rules, and its labels — all three, because the
    // labels are HTML positioned by the same fraction the SVG rules use and
    // either half can go missing on its own.
    expect(html).toContain('data-testid="chart-axis"');
    expect((html.match(/data-testid="chart-axis-tick"/g) ?? []).length).toBeGreaterThanOrEqual(2);
    expect((html.match(/data-testid="chart-axis-label"/g) ?? []).length).toBeGreaterThanOrEqual(2);
    // A tick is a DATE, not a decoration.
    expect(html).toMatch(/data-testid="chart-axis-label" data-date="\d{4}-\d{2}-\d{2}"/);
    // And the window is named in words beside the count.
    expect(html).toContain('data-testid="chart-span"');
  });
});

// ---------------------------------------------------------------------------
// (c) PLAYER IMAGES
// ---------------------------------------------------------------------------

describe("(c) players have images", () => {
  it("the three-step fallback picks the right step", () => {
    expect(avatarKind({ url: "https://x/a.jpg", flag_url: "https://y/f.png" })).toBe("face");
    expect(avatarKind({ url: null, flag_url: "https://y/f.png" })).toBe("flag");
    expect(avatarKind({ url: null, flag_url: null })).toBe("initials");
    expect(avatarKind(null)).toBe("initials");
    expect(initialsOf("Felix Auger-Aliassime")).toBe("FA");
  });

  it("a flag is CONTAINED, not cropped — a circle-cropped tricolour is one stripe", () => {
    const html = renderToStaticMarkup(
      <PlayerAvatar name="Gael Monfils" image={{ url: null, flag_url: "https://a.espncdn.com/f.png" }} />
    );
    expect(html).toContain("object-contain");
    expect(html).not.toContain("object-cover");
  });

  it("NEVER resolves an image in the browser — the wrong-face failure mode", () => {
    // `FighterAvatar` fires getWikipediaImage(name) at render. That returns a
    // Serbian footballer for Aleksandar Kovacevic. This component must have no
    // such path: given no image it renders initials and asks nobody.
    const source = fs
      .readFileSync(
        path.join(__dirname, "..", "..", "components", "tournament", "PlayerAvatar.tsx"),
        "utf8"
      )
      // Comments only DESCRIBE the failure mode; the code must not contain it.
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\/\/.*$/gm, "");
    expect(source).not.toContain("getWikipediaImage");
    expect(source).not.toContain("useEffect");
    expect(source).not.toContain("fetch(");
    const html = renderToStaticMarkup(<PlayerAvatar name="Nobody Here" image={null} />);
    expect(html).toContain('data-kind="initials"');
    expect(html).toContain("NH");
  });

  it("EVERY championship-board row renders an avatar, on both draws", () => {
    for (const board of payload.boards) {
      const html = renderToStaticMarkup(<TournamentBoard board={board} />);
      const rows = (html.match(/data-testid="board-row"/g) ?? []).length;
      const avatars = (html.match(/data-testid="player-avatar"/g) ?? []).length;
      expect(rows).toBeGreaterThan(0);
      expect(avatars).toBe(rows);
      // Alex's gate: ~complete per draw, and never a mixed column of faces
      // and holes. On the boards it is complete.
      const initials = (html.match(/data-kind="initials"/g) ?? []).length;
      expect(initials).toBe(0);
    }
  });

  it("EVERY match-list side renders an avatar, on the MAIN DRAW too", () => {
    for (const draw of ["mens-singles", "womens-singles"]) {
      const html = renderToStaticMarkup(
        <TournamentMatches
          entries={matchesFor(draw)}
          initialRound="R128"
          initialExpanded
          notice={null}
        />
      );
      const rows = (html.match(/data-testid="match-row"/g) ?? []).length;
      const sides = (html.match(/data-testid="match-side"/g) ?? []).length;
      const avatars = (html.match(/data-testid="player-avatar"/g) ?? []).length;
      // Two sides per row, and not one of them collapsed to a bare "A vs B"
      // line. This is the assertion that would have caught UX-P142's own first
      // draft, where 96 unpriced fixtures fell into the incoherent branch and
      // rendered as text with no faces at all — and `avatars === sides` was
      // vacuously true because both were zero.
      expect(rows).toBeGreaterThanOrEqual(45);
      expect(sides).toBe(rows * 2);
      expect(avatars).toBe(sides);
      expect(html).not.toContain('data-testid="match-incoherent"');
    }
  });

  it("an unpriced main-draw row prints its players, and no number at all", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches
        entries={matchesFor("mens-singles")}
        initialRound="R128"
        initialExpanded
        notice={null}
      />
    );
    // Every R128 fixture is unpriced today, so the number column is empty on
    // all of them — and empty means ABSENT, not two em-dashes per row.
    expect(html).not.toContain('data-testid="match-probability"');
    expect(html).not.toContain("—");
    // The absence is explained once, in words, on the row.
    expect(html).toContain("No market yet");
    // And the title chance, which we DO have, still prints.
    expect(html).toContain('data-testid="match-title-chip"');
    expect(html).toContain("% title");
  });

  it("EVERY playoff-grid row renders an avatar", () => {
    for (const draw of ["mens-singles", "womens-singles"]) {
      const grid = readPlayoffGrid(payload.grids?.[draw])!;
      const html = renderToStaticMarkup(<PlayoffGrid grid={grid} initialExpanded />);
      const rows = (html.match(/data-testid="grid-row"/g) ?? []).length;
      const avatars = (html.match(/data-testid="player-avatar"/g) ?? []).length;
      expect(rows).toBe(grid.rows.length);
      expect(avatars).toBe(rows);
    }
  });

  it("the images are PINNED hosts, never an arbitrary URL from a payload", () => {
    const urls: string[] = [];
    for (const board of payload.boards) {
      for (const row of board.rows) {
        if (row.image?.url) urls.push(row.image.url);
        if (row.image?.flag_url) urls.push(row.image.flag_url);
      }
    }
    expect(urls.length).toBeGreaterThan(50);
    for (const url of urls) {
      expect(url).toMatch(/^https:\/\/(upload\.wikimedia\.org|a\.espncdn\.com)\//);
    }
  });
});

// ---------------------------------------------------------------------------
// (d) THE PILLS
// ---------------------------------------------------------------------------

describe("(d) the draw pills are not flush against the line above", () => {
  it("the strip has top padding, and it matches the bottom", () => {
    expect(DRAW_TOGGLE_PADDING).toContain("pt-3");
    expect(DRAW_TOGGLE_PADDING).toContain("pb-3");
  });

  it("renders both pills with the padding actually applied", () => {
    const html = renderToStaticMarkup(<DrawToggle draw="mens-singles" onSelect={() => {}} />);
    expect(html).toContain('data-testid="draw-toggle"');
    // The class must be ON the rendered strip — a constant nothing spreads is
    // a constant, not a layout.
    const strip = html.slice(0, html.indexOf('data-testid="draw-pill"'));
    expect(strip).toContain("pt-3");
    expect(strip).toContain("pb-3");
    expect((html.match(/data-testid="draw-pill"/g) ?? []).length).toBe(2);
    expect(html).toContain('data-draw="mens-singles" data-active="true"');
  });
});

// ---------------------------------------------------------------------------
// The unpriced row must not smuggle a number back in
// ---------------------------------------------------------------------------

describe("an unpriced fixture prints no probability anywhere", () => {
  it("both sides are numberless and nothing is invented", () => {
    const unpriced = (payload.slate?.matches ?? []).filter(
      (m: SlateMatch) => m.priced === false
    );
    expect(unpriced.length).toBeGreaterThanOrEqual(90);
    for (const match of unpriced) {
      expect(match.coherent).toBe(false);
      expect(match.probability_is_live).toBe(false);
      for (const side of match.sides) {
        expect(side.probability).toBeNull();
        expect(side.raw_probability).toBeNull();
        expect(side.move).toBeNull();
      }
    }
  });
});
