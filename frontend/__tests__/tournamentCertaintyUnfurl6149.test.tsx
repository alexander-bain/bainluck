/**
 * #6149 — A US OPEN LINK STOPS UNFURLING "ALEXANDER ZVEREV 100%" WHILE THE
 * FINAL IS STILL BEING PLAYED.
 *
 * ═══ THE DEFECT, MEASURED ON PRODUCTION DATA ═══
 *
 * `/tournaments/us-open` builds its copy and its card from `boardLeader`, which
 * withheld a board whose leader had NO price and printed one at 1.0. Both
 * halves therefore had one answer for a certainty — narrate it as a lead:
 *
 *   og:title        "US Open 2026: Alexander Zverev 100%"                   ❌
 *   og:description  "Alexander Zverev leads the Men's Singles at 100%."     ❌
 *
 * ═══ 🔴 THIS IS NOT #6029's STALE READ — THE PAYLOAD IS CORRECT ═══
 *
 * #6029's occasion was a cached body: the picture had settled and the words had
 * not. Here there is nothing stale to fix. Two production mechanisms hand the
 * board an honest, current 0.995+ on a draw nobody has won:
 *
 * 1. **A LIVE FINAL.** `apply_final_match_blend` (`tournament_board.py:874`,
 *    #5893) promotes a live final's event blend onto its two board rows the
 *    moment a draw is down to two. `apply_final_result` (#5917) only nulls the
 *    board once ESPN reports a champion — which cannot happen until the match
 *    ends. Between them is a window in which the board is correctly priced,
 *    correctly undecided, and prints as certain.
 *
 * 2. **A RESULT OVERLAY THAT MISSES.** `apply_final_result` settles nothing if
 *    the champion cannot be placed on the board; its own docstring concedes
 *    "a miss here is a real miss". #5917 exists because the board published
 *    "Elena Rybakina 99% TO WIN THE TITLE" seventeen hours after she won it.
 *    At 0.997 rather than 0.99, that same lag prints "100%".
 *
 * ═══ THE SPECIMEN — THE ACTUAL FINAL, MEASURED ═══
 *
 * Event 15310688, Zverev vs Shelton, men's singles final. `completed_at =
 * 2026-09-13 21:53:36Z`. Four Polymarket blend readings at or above 0.995
 * BEFORE it completed, from `win_prob_snapshots`:
 *
 *   21:47:16Z  0.9950   live, undecided
 *   21:50:21Z  0.9955   live, undecided
 *   21:52:10Z  0.9980   live, undecided
 *   21:53:20Z  0.9990   live, undecided   ← the fixture below
 *
 * A ~6.3-minute live window. Not a one-off: across the two draws,
 * `win_prob_snapshots` holds 363 readings at or above 0.995 on 102 of 229 match
 * events, max 0.9995.
 *
 * ═══ THE FIX IS AN ADOPTION — THE EIGHTH IN A ROW ═══
 *
 * `boardLeader` is the ONE function both the sentence and the picture read
 * (`tournamentShareFacts` → `leaders`), and it already withholds a whole board
 * for a leader with no price. #6149 adds one more reason to take that same
 * existing exit. No new branch is drawn, and the quiet rendering it falls to is
 * the one production is serving for this very slug today.
 *
 * ═══ WHAT IS DELIBERATELY *NOT* DONE ═══
 *
 * No result is claimed. The module header's refusal is unchanged: a champion is
 * read from `decided`/`state`, NEVER inferred from a price. This branch claims
 * strictly LESS — the reader gets the tournament's name and no number, and the
 * card upgrades itself the moment `apply_final_result` publishes.
 *
 * And the band is one rounding step wide. `womensSingles` below is Rybakina at
 * the 0.99 #5917 measured seventeen hours after her win: it still prints "99%"
 * and is deliberately untouched, because a rule that ate it would be a rule
 * about lopsidedness rather than about certainty.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  buildTournamentShareCopy,
  tournamentShareFacts,
  type TournamentShareBoard,
  type TournamentShareSource,
} from "@/lib/tournamentShareMeta";
import { ABOVE_NINETY_NINE_PERCENT } from "@/lib/probabilityDisplay";
import { formatShareProbability } from "@/lib/share";

/** The element `ImageResponse` was constructed with. `mock`-prefixed for jest hoisting. */
const mockImageResponseCalls: React.ReactElement[] = [];

jest.mock("next/og", () => ({
  __esModule: true,
  ImageResponse: function ImageResponse(element: React.ReactElement) {
    mockImageResponseCalls.push(element);
    return { __stub: "ImageResponse" };
  },
}));

import OgImage from "@/app/tournaments/[slug]/opengraph-image";

/* ───────────────────────────── the specimens ───────────────────────────── */

/**
 * The men's board as it stood at 21:53:20Z on 2026-09-13, sixteen seconds
 * before the final ended.
 *
 * Names and `display_name`s are production's own, read from
 * `GET /api/tournaments/us-open?sections=first`. The two finalists carry the
 * MEASURED blend — 0.9990 / 0.0010, the reading in the table above — because
 * that is what `apply_final_match_blend` had promoted onto their rows.
 *
 * Musetti and Bublik sit behind them at their last OUTRIGHT prices (0.02 and
 * 0.01, read from the same payload's `trend` tail for 2026-09-13). Whether the
 * venue had already settled those two rows by 21:53Z is not recoverable from
 * today's payload, and it is not what this fixture is for: carrying them priced
 * is the HARDER case, because it gives a narrow repair somebody to promote.
 */
const MENS_SINGLES_FINAL_LIVE: TournamentShareBoard = {
  label: "Men's Singles",
  rows: [
    { display_name: "Alexander Zverev", probability: 0.999 },
    { display_name: "Ben Shelton", probability: 0.001 },
    { display_name: "Lorenzo Musetti", probability: 0.02 },
    { display_name: "Alexander Bublik", probability: 0.01 },
  ],
};

/**
 * THE OVER-REACH CONTROL, and it is a real one: #5917's own measured board.
 *
 * Rybakina at 0.99 with the field behind her, exactly the state that route
 * published for seventeen hours after she won. 0.99 prints "99%", which is a
 * true statement about a market, so this board must go on printing. If the ship
 * is drawn one step too wide it goes quiet and a working surface is deleted.
 */
const WOMENS_SINGLES_LOPSIDED: TournamentShareBoard = {
  label: "Women's Singles",
  rows: [
    { display_name: "Elena Rybakina", probability: 0.99 },
    { display_name: "Alexandra Eala", probability: 0.011 },
    { display_name: "Iga Swiatek", probability: 0.0105 },
    { display_name: "Aryna Sabalenka", probability: 0.01 },
  ],
};

/** The hub, with both boards — production's own `title` and `subtitle`. */
const US_OPEN_DURING_MENS_FINAL: TournamentShareSource = {
  title: "US Open 2026",
  subtitle: "Flushing Meadows",
  boards: [MENS_SINGLES_FINAL_LIVE, WOMENS_SINGLES_LOPSIDED],
};

/** The same instant with only the men's draw on the hub — nothing left to print. */
const MENS_DRAW_ONLY: TournamentShareSource = {
  title: "US Open 2026",
  subtitle: "Flushing Meadows",
  boards: [MENS_SINGLES_FINAL_LIVE],
};

/* ─────────────────────────────── the harness ─────────────────────────────── */

/**
 * The card as the reader meets it, top to bottom.
 *
 * `UnfurlCard` is a plain function component, so the element the route hands
 * `ImageResponse` is rendered rather than prop-inspected — a prop assertion
 * would pass on a card that received `rows={[]}` and drew a number from
 * somewhere else.
 */
async function drawCard(payload: TournamentShareSource): Promise<string> {
  mockImageResponseCalls.length = 0;
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => payload,
  }) as unknown as typeof fetch;

  await OgImage({ params: Promise.resolve({ slug: "us-open" }) });

  return renderToStaticMarkup(mockImageResponseCalls[0])
    .replace(/<[^>]+>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

/** Every string the card and the copy put in front of a reader, as one blob. */
async function everythingSaid(payload: TournamentShareSource): Promise<string> {
  const { title, description } = buildTournamentShareCopy(payload);
  return `${title} ${description} ${await drawCard(payload)}`;
}

/* ──────────────────────────────── the ship ──────────────────────────────── */

describe("#6149 a live final does not unfurl as a decided one", () => {
  it("the defect's sentences are gone from BOTH halves", async () => {
    const { title, description } = buildTournamentShareCopy(MENS_DRAW_ONLY);

    expect(title).not.toBe("US Open 2026: Alexander Zverev 100%");
    expect(description).not.toBe(
      "Flushing Meadows. Alexander Zverev leads the Men's Singles at 100%.",
    );

    const said = await everythingSaid(MENS_DRAW_ONLY);
    expect(said).not.toMatch(/100\s*%/);
    expect(said).not.toMatch(/leads/i);
    expect(said).not.toContain("Alexander Zverev");
  });

  it("still names the tournament, so the card is quiet and not broken", async () => {
    const { title, description } = buildTournamentShareCopy(MENS_DRAW_ONLY);
    expect(title).toBe("US Open 2026");
    expect(description).toContain("Flushing Meadows");

    const card = await drawCard(MENS_DRAW_ONLY);
    expect(card).toContain("US Open 2026");
    expect(card).toContain("Flushing Meadows");
    expect(card).toContain("Tournament");
  });

  it("withholds the BOARD, not the player", async () => {
    // The mutant this exists to kill: "drop the certain row and take the next
    // one". Behind Zverev at 0.999 sits Shelton at 0.001, which
    // `formatShareProbability` does NOT drop — it only drops null/NaN/0 — so a
    // narrow repair does not go quiet, it publishes
    // "Ben Shelton leads the Men's Singles at 0%" over a match Shelton is
    // losing. Musetti at 0.02 is the next one after that.
    const said = await everythingSaid(MENS_DRAW_ONLY);

    for (const player of ["Ben Shelton", "Lorenzo Musetti", "Alexander Bublik"]) {
      expect([player, said.includes(player)]).toEqual([player, false]);
    }
    expect(said).not.toMatch(/\b0\s*%/);
    expect(said).not.toMatch(/\b2\s*%/);
  });

  it("withholds ONE board, not the hub — the other draw still prints", async () => {
    // Per-board, because that is the unit a ranking is meaningless within. The
    // men's draw goes quiet at 0.999 and the women's goes on saying 99%.
    const { title, description } = buildTournamentShareCopy(
      US_OPEN_DURING_MENS_FINAL,
    );

    expect(title).toBe("US Open 2026: Elena Rybakina 99%");
    expect(description).toBe(
      "Flushing Meadows. Elena Rybakina leads the Women's Singles at 99%.",
    );

    const card = await drawCard(US_OPEN_DURING_MENS_FINAL);
    expect(card).toContain("Elena Rybakina");
    expect(card).toContain("99%");
    expect(card).toContain("1 draw tracked");
    expect(card).not.toContain("Alexander Zverev");
  });
});

describe("#6149 the over-reach control — a lopsided draw is untouched", () => {
  /**
   * #5917's measured board, on its own. The seventeen-hour "Rybakina 99%" is a
   * DIFFERENT defect with a different fix (the result overlay), and this ship
   * must not quietly absorb it by going silent on anything one-sided.
   */
  it("Rybakina at 0.99 still leads the Women's Singles at 99%", async () => {
    const womensOnly: TournamentShareSource = {
      title: "US Open 2026",
      subtitle: "Flushing Meadows",
      boards: [WOMENS_SINGLES_LOPSIDED],
    };

    expect(buildTournamentShareCopy(womensOnly).description).toBe(
      "Flushing Meadows. Elena Rybakina leads the Women's Singles at 99%.",
    );
    expect(await drawCard(womensOnly)).toContain("99%");
  });

  it("an ordinary open draw is untouched", () => {
    const openDraw: TournamentShareSource = {
      title: "US Open 2026",
      subtitle: "Flushing Meadows",
      boards: [
        {
          label: "Men's Singles",
          rows: [
            { display_name: "Alexander Zverev", probability: 0.613478 },
            { display_name: "Ben Shelton", probability: 0.38087 },
          ],
        },
      ],
    };

    // The two finalists' real OUTRIGHT prices on 2026-09-13, before the match
    // blend was promoted over them. This is the number the board carries for
    // all but the last hour of a fortnight, and it must survive untouched.
    expect(buildTournamentShareCopy(openDraw).title).toBe(
      "US Open 2026: Alexander Zverev 61%",
    );
  });
});

describe("#6149 the threshold is the formatter's own boundary", () => {
  /**
   * The one assertion that keeps `PRINTS_AS_CERTAIN` honest. The constant is
   * 0.995 because that is where `formatShareProbability` turns over — not
   * because 0.995 is a nice number. Asserting the formatter directly means this
   * suite fails if the rounding ever changes, rather than the module silently
   * withholding the wrong band.
   *
   * #7716 IS THE DAY THAT HAPPENED. The formatter used to print "100%" from
   * 0.995 up and now prints the boundary marker `probabilityDisplay` owns. The
   * CONSTANT does not move: 0.995 is still the exact price at which a plain
   * rounded integer stops being available, so the withheld set below is
   * byte-identical and this ship's band is untouched. Pinned against the
   * exported constant rather than a typed-out string, because that spelling has
   * one home and a literal here would be a second copy of it.
   *
   * ⚠️ Whether the band should still withhold now that ">99% over a live final"
   * is a TRUE sentence is #6149's question to re-open, not #7716's to answer in
   * passing. Named residue; the behaviour is deliberately unchanged.
   */
  it("0.995 is where the formatter stops printing a plain integer", () => {
    expect(formatShareProbability(0.995)).toBe(ABOVE_NINETY_NINE_PERCENT);
    expect(formatShareProbability(0.994)).toBe("99%");
  });

  it("the withheld set is exactly the set at or above the boundary", () => {
    const withheld = (fraction: number) =>
      tournamentShareFacts({
        title: "T",
        boards: [{ label: "D", rows: [{ display_name: "A", probability: fraction }] }],
      }).leaders.length === 0;

    // Below the boundary: kept, and each prints a number under 100%.
    for (const fraction of [0.5, 0.9, 0.99, 0.994]) {
      expect([fraction, withheld(fraction)]).toEqual([fraction, false]);
    }
    // At and above it: withheld. 1.02 is in the list because a price over 1.0
    // prints "102%", which is no more a forecast than "100%" is.
    for (const fraction of [0.995, 0.999, 1.0, 1.02]) {
      expect([fraction, withheld(fraction)]).toEqual([fraction, true]);
    }
  });

  it("the existing no-price withhold is unchanged", () => {
    // The exit this ship reuses. If a repair replaced the null/NaN/0 refusal
    // rather than joining it, these would start printing "0%".
    const withheld = (probability: number | null) =>
      tournamentShareFacts({
        title: "T",
        boards: [{ label: "D", rows: [{ display_name: "A", probability }] }],
      }).leaders.length === 0;

    for (const probability of [null, 0, Number.NaN]) {
      expect([String(probability), withheld(probability)]).toEqual([
        String(probability),
        true,
      ]);
    }
  });
});
