/**
 * The copy a pasted `/tournaments/<slug>` link unfurls with (#5813).
 *
 * The fixtures below are the SHAPE of `GET /api/tournaments/us-open?sections=first`
 * as production served it on 2026-09-12 ~21:30 PT — two boards, `Men's Singles`
 * and `Women's Singles`, rows carrying `display_name` and a 0-1 `probability`.
 * The probabilities are the real ones (Zverev .57025, Rybakina .99475), because
 * the rounding they exercise is the whole of `formatShareProbability`'s job.
 */

import { buildTournamentShareCopy } from "@/lib/tournamentShareMeta";

/**
 * Written out rather than inferred, and with every field REQUIRED but nullable.
 *
 * Inference gives `probability: number`, which makes the "leader has no price"
 * cases — the ones that decide whether the card prints `0%` — unassignable. All
 * required so a fixture mutation is a plain assignment rather than a chain of
 * non-null assertions; structurally assignable to `TournamentShareSource`.
 */
type Row = { display_name: string | null; probability: number | null };
type Board = { draw?: string; label: string | null; rows: Row[] };
type Source = { title: string | null; subtitle: string | null; boards: Board[] };

const usOpen = (): Source => ({
  title: "US Open 2026",
  subtitle: "Flushing Meadows",
  boards: [
    {
      draw: "mens-singles",
      label: "Men's Singles",
      rows: [
        { display_name: "Alexander Zverev", probability: 0.57025 },
        { display_name: "Ben Shelton", probability: 0.4305 },
        { display_name: "Grigor Dimitrov", probability: 0.001 },
      ],
    },
    {
      draw: "womens-singles",
      label: "Women's Singles",
      rows: [
        { display_name: "Elena Rybakina", probability: 0.99475 },
        { display_name: "Aryna Sabalenka", probability: 0.00525 },
      ],
    },
  ],
});

describe("the title names the tournament and its leaders", () => {
  it("leads with the tournament, then one leader per draw", () => {
    const { title } = buildTournamentShareCopy(usOpen());
    expect(title).toBe("US Open 2026: Alexander Zverev 57%, Elena Rybakina 99%");
  });

  it("carries no site suffix, because the root template appends one", () => {
    // `app/layout.tsx` sets `title.template = "%s | Bain Luck"`. Appending here
    // is what printed `| Bain Luck | Bain Luck` on every event page.
    expect(buildTournamentShareCopy(usOpen()).title).not.toContain("Bain Luck");
  });

  it("names at most two leaders, so a many-board hub keeps its own name", () => {
    const source = usOpen();
    source.boards.push({
      draw: "mixed-doubles",
      label: "Mixed Doubles",
      rows: [{ display_name: "Errani / Vavassori", probability: 0.31 }],
    });

    const { title, description } = buildTournamentShareCopy(source);
    expect(title).toBe("US Open 2026: Alexander Zverev 57%, Elena Rybakina 99%");
    expect(title).not.toContain("Errani");
    // Capped in the title, never dropped: the description still names it.
    expect(description).toContain("Errani / Vavassori leads the Mixed Doubles at 31%");
  });

  it("a single-board hub reads as one race", () => {
    const { title } = buildTournamentShareCopy({
      title: "Biltmore Championship",
      subtitle: null,
      boards: [
        {
          label: "Winner",
          rows: [{ display_name: "Scottie Scheffler", probability: 0.22 }],
        },
      ],
    });
    expect(title).toBe("Biltmore Championship: Scottie Scheffler 22%");
  });
});

describe("the description resolves the title's ambiguity in one line", () => {
  it("names each leader's draw, which the title has no room for", () => {
    const { description } = buildTournamentShareCopy(usOpen());
    expect(description).toBe(
      "Flushing Meadows. Alexander Zverev leads the Men's Singles at 57%. " +
        "Elena Rybakina leads the Women's Singles at 99%."
    );
  });

  it("drops the venue clause rather than printing an empty one", () => {
    const source = usOpen();
    source.subtitle = "   ";
    expect(buildTournamentShareCopy(source).description).toBe(
      "Alexander Zverev leads the Men's Singles at 57%. " +
        "Elena Rybakina leads the Women's Singles at 99%."
    );
  });

  it("omits the draw when a board is unlabelled, rather than saying 'the null'", () => {
    const { description } = buildTournamentShareCopy({
      title: "Some Cup",
      subtitle: null,
      boards: [{ label: null, rows: [{ display_name: "A. Player", probability: 0.4 }] }],
    });
    expect(description).toBe("A. Player leads at 40%.");
  });

  it("goes through the shared truncator rather than growing without bound", () => {
    const source = usOpen();
    source.boards[0].rows[0].display_name = "X".repeat(400);
    const { description } = buildTournamentShareCopy(source);

    // 182, not 180. `truncateShareText(text, 180)` returns
    // `slice(0, 179).trim() + "..."`, so its own ceiling is `maxLength + 2` —
    // the ellipsis is added AFTER the budget rather than inside it. That
    // overshoot is the shared helper's, not this module's: `/events/[id]` and
    // `/futures/[id]` have shipped on it since #4149. Pinned at the true value
    // rather than the intended one, because a test that asserts 180 here would
    // be asserting something no caller has ever produced.
    expect(description.length).toBeLessThanOrEqual(182);
    expect(description.endsWith("...")).toBe(true);
  });
});

describe("the leader is chosen by price, not by arrival order", () => {
  it("sorts, so the copy does not depend on how the payload happened to arrive", () => {
    const source = usOpen();
    source.boards[0].rows.reverse();
    expect(buildTournamentShareCopy(source).title).toContain("Alexander Zverev 57%");
  });

  it("a decided draw reads as its price, and claims no result", () => {
    // Rybakina at .99475 is a women's final already decided in the market. The
    // copy says 99% — true, and not a claim about a winner. Nothing here
    // branches on a row's `state`: that field is price freshness, not
    // settlement, and reads "live" on every row of the served payload.
    const { title, description } = buildTournamentShareCopy(usOpen());
    expect(title).toContain("Elena Rybakina 99%");
    expect(description).not.toMatch(/\bwon\b|\bwins\b|champion/i);
  });
});

describe("a board with nothing to say says nothing numeric", () => {
  it("skips a leader with no price rather than printing 0%", () => {
    const source = usOpen();
    source.boards[1].rows = [
      { display_name: "Nobody Priced", probability: 0 },
      { display_name: "Also Unpriced", probability: null },
    ];
    const { title, description } = buildTournamentShareCopy(source);
    expect(title).toBe("US Open 2026: Alexander Zverev 57%");
    expect(description).not.toContain("Nobody Priced");
    expect(description).not.toContain("0%");
  });

  it("skips a leader with no name", () => {
    const source = usOpen();
    source.boards[1].rows = [{ display_name: "  ", probability: 0.8 }];
    expect(buildTournamentShareCopy(source).title).toBe(
      "US Open 2026: Alexander Zverev 57%"
    );
  });

  it("an unpriced hub names itself and claims nothing about who is ahead", () => {
    const { title, description } = buildTournamentShareCopy({
      title: "US Open 2026",
      subtitle: "Flushing Meadows",
      boards: [],
    });
    expect(title).toBe("US Open 2026");
    expect(description).toBe(
      "US Open 2026, Flushing Meadows. Every contender's chance of winning, as one clean probability."
    );
    expect(description).not.toMatch(/\d%/);
  });

  it("survives a payload missing the fields entirely", () => {
    // `generateMetadata` runs on every crawl. A shape change upstream must
    // degrade the card, never throw and take the page's metadata down.
    expect(() => buildTournamentShareCopy({})).not.toThrow();
    expect(buildTournamentShareCopy({}).title).toBe("Tournament");
    expect(
      buildTournamentShareCopy({ title: "Cup", boards: [{ rows: null }, null as never] })
        .title
    ).toBe("Cup");
  });
});

describe("the copy obeys the standing rules for reader-facing text", () => {
  it("names no sportsbook noun (notice 33)", () => {
    const { title, description } = buildTournamentShareCopy(usOpen());
    expect(`${title} ${description}`).not.toMatch(/\bbooks?\b|bookmaker/i);
  });

  it("carries no coverage count, limitation or method note (notice 34)", () => {
    // The three shapes notice 34 names. An unfurl card is the least forgiving
    // place for any of them: it is one line, and it is the whole first
    // impression of a link someone else pasted.
    const { description } = buildTournamentShareCopy(usOpen());
    expect(description).not.toMatch(/\d+ of \d+|hidden|last quote|we mark|grouped by/i);
  });
});
