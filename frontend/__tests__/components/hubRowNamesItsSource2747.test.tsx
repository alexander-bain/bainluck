/**
 * ux/1040 — THE HUB'S FINISHED ROW NAMES ITS OWN RUNG (CERT-812 repair, #2747).
 *
 * ═══ WHAT WAS BLOCKED ═══
 *
 * CERT-812, on PR #2781: *"the Shelton–Hurkacz 68/32 books row renders bare
 * percentages, and each accessible sentence falsely says 'the market gave'; only
 * an aggregate footer says some unidentified rows are sportsbook openings."*
 * Required repair: *"consume `prematch_source` at each hub result row for visible
 * and spoken attribution and add both books/prediction-market rendered guards."*
 *
 * Round one carried `prematch_source` all the way to the row type and then read
 * it in exactly one place — `prematchSourceNote`, an aggregate count in the
 * footer. `/sports` and Discover both got per-value attribution; the hub, which
 * is the surface Alex was reading when he asked for the label, did not.
 *
 * ═══ THE FIXTURE IS THE SHIPPED CODE PATH'S OWN OUTPUT ═══
 *
 * `tournamentHubBooksRung.20260903T0310Z.json` was not hand-written. It is the
 * live `GET /api/tournaments/us-open` results block (2026-09-03T03:10Z) with the
 * **real `apply_books_prematch`** run over it, fed the real `Event.espn_id` links
 * and the real `opening_*` columns for the 63 rows that resolve. That matters
 * because a hand-edited books row is a population that may not exist (ux/1008's
 * lesson #2); this one is what production serves the moment #2781 deploys.
 *
 * What it contains, and every number here is asserted below rather than trusted:
 *
 *   245 result rows
 *   111 matches / 222 player slots  prior from the market rung   <- CONTROL ARM
 *    61 matches / 122 player slots  prior from the books rung    <- SHIP ARM
 *   172 with_prematch, 61 with_prematch_books
 *
 * So the books rung is **35% of every prior on the page**, not an edge case, and
 * on the parent all 61 render a bare percentage under "the market gave". Round
 * one's comment in `tournamentResults.ts` said this population was *"empty on
 * today's served payload"* — true of commit 1, and left unchanged by commit 2,
 * which added the rung that fills it.
 *
 * ═══ WHY THE MARKET ARM'S SOURCE IS ABSENT AND THAT IS CORRECT ═══
 *
 * The 222 market slots carry `prematch_source: null`, because the live payload
 * was served by master, where `_prematch_by_pair` predates the field. That is the
 * rollout / cached-payload path and it is the one that must NOT acquire a books
 * marker — absent means "a prediction-market opening", never "unknown rung". The
 * explicit `kalshi` / `polymarket` values get their own arm below, written the
 * way `_prematch_by_pair` writes them.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentResults from "@/components/tournament/TournamentResults";
import {
  BOOKS_MARKER,
  prematchAttribution,
  prematchSourceNote,
  type ResultPlayer,
  type TournamentResult,
  type TournamentResults as ResultsModel,
} from "@/lib/tournamentResults";
import { PREMATCH_SAID, isPredictionMarketSource } from "@/lib/prematchReading";

import hub from "../fixtures/tournamentHubBooksRung.20260903T0310Z.json";

const RESULTS = (hub as unknown as { results: ResultsModel }).results;
const MATCHES = RESULTS.matches as unknown as TournamentResult[];

/**
 * D65 (Alex, 2026-09-04): *"Shouldn't reference sportsbooks."*
 *
 * This file was written when the SPOKEN clause forked by rung — "sportsbooks
 * opened" on a books median, "the market gave" on Kalshi — and most of it
 * asserted that fork. The fork is gone: one venue-free phrase on every rung, so
 * a phrase that names no venue cannot name the wrong one.
 *
 * The file keeps its job, on the register that still forks. CERT-812's defect
 * was "a books number renders as if it were a market number", and the VISIBLE
 * marker is now the only thing that answers it — so every assertion that used to
 * read the clause reads the marker, and the clause gets one new assertion of its
 * own: that it is the SAME on all 344 slots. Both directions still fail loudly.
 */
const SAID = PREMATCH_SAID;

/**
 * `initialExpanded` is TRUE on purpose, and it is not a convenience.
 *
 * Collapsed, the section renders a head of the list — 18 of the 122 books slots
 * on my first run — so every "all 122" claim below would have been quietly
 * asserted over a sample, and a defect in the tail would be invisible. That is
 * ux/1032's lesson #3 (a truncated verification is invisible from inside the
 * check) arriving as a test-harness question rather than a re-shoot one. The
 * collapsed head is exercised by its own test at the bottom.
 */
function render(
  draw: string,
  results: ResultsModel = RESULTS,
  expanded = true,
): string {
  return renderToStaticMarkup(
    <TournamentResults results={results} draw={draw} initialExpanded={expanded} />,
  );
}

/**
 * Depth-counted rather than a lazy `[\s\S]*?` — the prior cell CONTAINS spans
 * (the clause and the marker), so a non-greedy match closes on the first inner
 * `</span>` and silently drops cells. My first run yielded 9 where the markup
 * declared 10, which is why `priorsChecked` exists.
 */
function cellsOf(html: string, testid: string): string[] {
  const open = new RegExp(`<span[^>]*data-testid="${testid}"[^>]*>`, "g");
  const out: string[] = [];
  let match: RegExpExecArray | null;
  while ((match = open.exec(html)) !== null) {
    let depth = 1;
    let i = match.index + match[0].length;
    const start = i;
    while (depth > 0 && i < html.length) {
      const nextOpen = html.indexOf("<span", i);
      const nextClose = html.indexOf("</span>", i);
      if (nextClose === -1) break;
      if (nextOpen !== -1 && nextOpen < nextClose) {
        depth += 1;
        i = nextOpen + 5;
      } else {
        depth -= 1;
        i = nextClose + 7;
      }
    }
    out.push(`${match[0]}${html.slice(start, i)}`);
  }
  return out;
}

/**
 * Every rendered prior, as a `(source, marker, clause, subject)` TUPLE.
 *
 * Read off the prior cell itself and not off free text, for the reason
 * ux/1016's lesson #6 gives: a `toContain` on "sportsbooks opened" is satisfied
 * by the footnote at the bottom of the page and is green on the bug. So the
 * source attribute and the two renderings it is supposed to drive come out of
 * one element, together.
 *
 * The spoken sentence is `"{clause} {player name} "` in ONE text node, so the
 * clause and the name it is about come out together. That is deliberate: a
 * clause-only extractor cannot tell "the right rows say sportsbooks" from "the
 * rows say sportsbooks about each other's players", which is exactly the
 * near-miss a positional re-index produces (ux/1039's lesson #2). Every
 * assertion below reads the pair.
 */
function priors(html: string): Array<{
  source: string | null;
  marker: string | null;
  clause: string | null;
  said: string | null;
}> {
  return cellsOf(html, "result-prematch").map((cell) => {
    const sourceMatch = cell.match(/data-prematch-source="([^"]*)"/);
    const markerMatch = cell.match(
      /data-testid="result-prematch-marker"[^>]*>([^<]*)</,
    );
    const saidMatch = cell.match(/class="sr-only">([^<]*)</);
    const said = saidMatch ? saidMatch[1].trim() : null;
    // One recognised clause now, so `clause` is "did this cell speak the
    // sanctioned phrase at all" rather than "which of two". A cell that speaks
    // something else reads as `null` here and fails the coverage assertions,
    // exactly as an unrecognised fork used to.
    const clause: string | null = said?.startsWith(SAID) ? SAID : null;
    return {
      source: sourceMatch ? sourceMatch[1] : null,
      marker: markerMatch ? markerMatch[1].trim() : null,
      clause,
      said,
    };
  });
}

/** The name the clause is ABOUT, which must be this row's player. */
function subjectOf(row: { clause: string | null; said: string | null }): string {
  if (!row.clause || !row.said) return "";
  return row.said.slice(row.clause.length).trim();
}

/** The extractor must not silently under-report — ux/1023's lesson #5. */
function priorsChecked(html: string): ReturnType<typeof priors> {
  const found = priors(html);
  const declared = (html.match(/data-testid="result-prematch"/g) ?? []).length;
  if (found.length !== declared) {
    throw new Error(
      `extractor yielded ${found.length} prior cells but the markup declares ${declared}`,
    );
  }
  return found;
}

function withSource(source: string | null): ResultsModel {
  const clone = JSON.parse(JSON.stringify(RESULTS)) as ResultsModel;
  for (const match of clone.matches as unknown as TournamentResult[]) {
    for (const player of match.players) {
      if (player.prematch_probability !== null) player.prematch_source = source;
    }
  }
  return clone;
}

function player(source: string | null, probability: number | null = 0.68): ResultPlayer {
  return {
    display_name: "Ben Shelton",
    entity_key: "player:shelton",
    image: null,
    is_winner: true,
    seed: null,
    prematch_probability: probability,
    prematch_source: source,
  } as unknown as ResultPlayer;
}

// ───────────────────────── the fixture is what I claim it is ────────────────

describe("the corpus", () => {
  test("is the shipped ladder's own output: 61 books matches, 111 market", () => {
    let books = 0;
    let market = 0;
    let bookSlots = 0;
    for (const match of MATCHES) {
      const sources = match.players
        .filter((p) => p.prematch_probability !== null)
        .map((p) => p.prematch_source ?? null);
      if (sources.length === 0) continue;
      if (sources.some((s) => s === "books")) {
        books += 1;
        bookSlots += sources.filter((s) => s === "books").length;
      } else market += 1;
    }
    expect(MATCHES).toHaveLength(245);
    expect(books).toBe(61);
    expect(bookSlots).toBe(122);
    expect(market).toBe(111);
    expect(books + market).toBe(172);
  });

  test("the books rung is 35% of priors — this is not an edge case", () => {
    expect(Math.round((61 / 172) * 100)).toBe(35);
  });
});

// ─────────────────────────────── THE SHIP ARM: books ────────────────────────

/**
 * EXPECTATIONS COME FROM THE FIXTURE, NOT FROM RENDERED ATTRIBUTES.
 *
 * My first draft filtered the books rows with `r.source === "books"`, read off
 * the `data-prematch-source` attribute — which THIS DIFF ADDS. On the parent the
 * filter therefore matched nothing, `[].every(...)` was vacuously true, and the
 * spoken-sentence test — half of what CERT-812 blocked — passed on the bug. That
 * is ux/1022's lesson #5: a guard that selects on a marker your own diff adds
 * cannot go red on the parent, because absence of the marker and absence of the
 * defect are the same observation.
 *
 * So the books population is derived from the FIXTURE's own `prematch_source`
 * values, which exist in both arms, and the assertions are counts and
 * subject-bindings over that.
 */
const EXPECTED_BOOKS_SLOTS = 122;
const EXPECTED_MARKET_SLOTS = 222;

/**
 * name -> the markers the fixture says that player may legitimately WEAR.
 *
 * Was `allowedClauses`, keyed on the spoken fork; D65 removed that fork, so the
 * same binding is now expressed over the marker, which is the register that
 * still distinguishes a books median from a market opening. `null` is a real
 * member — "this player's prior is a market one and must wear nothing".
 */
function allowedMarkers(): Map<string, Set<string | null>> {
  const out = new Map<string, Set<string | null>>();
  for (const match of MATCHES) {
    for (const p of match.players) {
      if (p.prematch_probability === null) continue;
      const want = p.prematch_source === "books" ? BOOKS_MARKER : null;
      const set = out.get(p.display_name) ?? new Set<string | null>();
      set.add(want);
      out.set(p.display_name, set);
    }
  }
  return out;
}

function allRendered() {
  return [
    ...priorsChecked(render("mens-singles")),
    ...priorsChecked(render("womens-singles")),
  ];
}

describe("SHIP — a books prior says so, in both registers", () => {
  test("the VISIBLE marker lands on exactly the books slots", () => {
    const rows = allRendered();
    expect(rows.filter((r) => r.marker === BOOKS_MARKER)).toHaveLength(
      EXPECTED_BOOKS_SLOTS,
    );
    expect(rows.filter((r) => r.marker !== null)).toHaveLength(EXPECTED_BOOKS_SLOTS);
  });

  test("the SPOKEN clause is the SAME on every slot, books or market (D65)", () => {
    // The inverse of what this test asserted before, and the assertion Alex's
    // ruling actually needs: 344 slots, one phrase. A regression that
    // reintroduces the fork in EITHER direction leaves some slots not starting
    // with the sanctioned phrase, so they extract as `clause === null` and the
    // count falls short.
    const rows = allRendered();
    expect(rows).toHaveLength(EXPECTED_BOOKS_SLOTS + EXPECTED_MARKET_SLOTS);
    expect(rows.filter((r) => r.clause === SAID)).toHaveLength(rows.length);
    expect(new Set(rows.map((r) => r.clause))).toEqual(new Set([SAID]));
  });

  test("no rendered clause references a venue, in any casing", () => {
    // Belt to the braces above: the phrase could be changed to another
    // venue-naming string and still be uniform. This reads the raw spoken text
    // rather than the classified clause, so it is not satisfied by the
    // extractor agreeing with itself.
    for (const row of allRendered()) {
      expect(row.said?.toLowerCase()).not.toContain("sportsbook");
      expect(row.said?.toLowerCase()).not.toContain("book");
      expect(row.said?.toLowerCase()).not.toContain("kalshi");
      expect(row.said?.toLowerCase()).not.toContain("polymarket");
    }
  });

  test("each MARKER is bound to a player the fixture permits it for", () => {
    // The near-miss this catches: right rows marked, wrong names attached — a
    // positional re-index that keeps the counts and permutes the subjects.
    // Reads the marker now that the clause no longer varies; the subject still
    // comes out of the spoken text, so the pair is still read together.
    const allowed = allowedMarkers();
    const wrong = allRendered().filter((r) => {
      const permitted = allowed.get(subjectOf(r));
      return !permitted || !permitted.has(r.marker);
    });
    expect(wrong).toHaveLength(0);
  });

  test("CONTROL (green on the parent too) — the marker tracks the rung exactly", () => {
    // Arm-independent by design: on the parent nothing is marked and no row is
    // a books rung by the cell's own attribute, so the biconditional holds
    // there too. It is here to catch a HALF-fix, and it now reads the DOM's own
    // `data-prematch-source` rather than the clause, which no longer forks.
    for (const row of allRendered()) {
      expect(row.marker === BOOKS_MARKER).toBe(row.source === "books");
    }
  });

  test("the rung reaches the DOM as a queryable fact on the cell", () => {
    expect(render("mens-singles")).toContain('data-prematch-source="books"');
  });
});

// ────────────────────── THE CONTROL ARM: prediction market ──────────────────

describe("CONTROL — a prediction-market prior renders exactly as it always did", () => {
  test("a market-only player never gets a marker", () => {
    const allowed = allowedMarkers();
    const marketOnly = allRendered().filter((r) => {
      const permitted = allowed.get(subjectOf(r));
      return permitted?.size === 1 && permitted.has(null);
    });
    // 154, not 222: a player who won a books-priced round AND a market-priced
    // one is legitimately allowed both markers, so they are not "market-only"
    // and are excluded here. I expected >200 and was wrong — the measured
    // number is the useful one, and the gap is what proves the binding test
    // above is doing work a count could not (ux/1016's lesson #5).
    expect(marketOnly).toHaveLength(154);
    expect(marketOnly.every((r) => r.marker === null)).toBe(true);
    // The clause is the same one everybody hears — asserted here too, because
    // "market-only" is the population most likely to be special-cased back into
    // a distinct sentence by a well-meaning revert.
    expect(marketOnly.every((r) => r.clause === SAID)).toBe(true);
  });

  test("the number of priors on the page is unchanged by this diff", () => {
    expect(allRendered()).toHaveLength(
      EXPECTED_BOOKS_SLOTS + EXPECTED_MARKET_SLOTS,
    );
  });

  test.each(["kalshi", "polymarket"])(
    "an explicit %s source is silent too — the label is books-only",
    (source) => {
      const rows = priorsChecked(render("mens-singles", withSource(source)));
      expect(rows.length).toBeGreaterThan(0);
      expect(rows.every((r) => r.marker === null)).toBe(true);
      expect(rows.every((r) => r.clause === SAID)).toBe(true);
    },
  );

  test("a row with no prior at all renders no cell, no marker, no clause", () => {
    // Men's: 116 rows, 232 player slots, but only 170 carry a prior
    // (106 market + 64 books). The other 62 get an empty grid cell with no
    // testid — the column keeps its place and claims nothing.
    const rows = priorsChecked(render("mens-singles"));
    expect(rows).toHaveLength(170);
    expect(rows.every((r) => r.clause !== null)).toBe(true);
  });

  test("COLLAPSED — the head of the list obeys the same rule", () => {
    const rows = priorsChecked(render("mens-singles", RESULTS, false));
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.length).toBeLessThan(170);
    for (const row of rows) {
      expect(row.marker === BOOKS_MARKER).toBe(row.source === "books");
      expect(row.clause).toBe(SAID);
    }
  });
});

// ─────────────────────────── the decision has ONE owner ─────────────────────

describe("one decision, one owner", () => {
  test("prematchAttribution agrees with isPredictionMarketSource on every rung", () => {
    for (const source of ["kalshi", "polymarket", "books", "betfair", "", null]) {
      const attribution = prematchAttribution(player(source));
      const isMarket = source === null || isPredictionMarketSource(source);
      expect(attribution.marker === null).toBe(isMarket);
      // The clause no longer varies with the rung — that IS the ruling, so it
      // is asserted inside the loop that walks every rung rather than once.
      expect(attribution.said).toBe(SAID);
    }
  });

  test("the hub speaks the same phrase the two card surfaces do", () => {
    // Three components used to build this clause privately, three files apart,
    // which is how the `isPredictionMarketSource` set had already drifted once.
    // `PREMATCH_SAID` is the single owner; this asserts the hub reads it rather
    // than holding a fourth copy that merely matches today.
    expect(prematchAttribution(player("kalshi")).said).toBe(PREMATCH_SAID);
    expect(prematchAttribution(player("books")).said).toBe(PREMATCH_SAID);
  });

  test("an unrecognised rung is MARKED, not silently passed as a market", () => {
    // The safe direction, unchanged by D65: anything that is not a named
    // prediction market gets the caveat. A new sportsbook rung must not arrive
    // unmarked. Only the register moved — the caveat is now carried by the
    // marker alone, so this is the test that has to hold it.
    const attribution = prematchAttribution(player("draftkings"));
    expect(attribution.marker).toBe(BOOKS_MARKER);
    expect(attribution.said).toBe(SAID);
  });

  test("a player with no prior gets no marker whatever its source says", () => {
    expect(prematchAttribution(player("books", null)).source).toBe("books");
    // The component gates on `prior`, so the marker never renders; assert the
    // rendered fact rather than the helper's opinion.
    const html = render("mens-singles");
    const cells = html.match(/data-testid="result-prematch-marker"/g) ?? [];
    const bookCells = (html.match(/data-prematch-source="books"/g) ?? []).length;
    expect(cells.length).toBe(bookCells);
  });
});

// ───────────────────────── the footer is now a legend ───────────────────────

describe("the footnote stops being the only attribution", () => {
  test("it names the marker so the count points at findable rows", () => {
    const note = prematchSourceNote(MATCHES);
    expect(note).toContain(BOOKS_MARKER);
    expect(note).toMatch(/^61 of them are a sportsbook opening/);
  });

  test("it is silent when nothing needs the caveat (CONTROL)", () => {
    const marketOnly = (withSource("kalshi").matches as unknown as TournamentResult[]);
    expect(prematchSourceNote(marketOnly)).toBe("");
  });

  test("the legend and the rows agree on the count", () => {
    const html = `${render("mens-singles")}${render("womens-singles")}`;
    const marked = (html.match(/data-testid="result-prematch-marker"/g) ?? []).length;
    // 61 matches, both players marked.
    expect(marked).toBe(122);
    expect(prematchSourceNote(MATCHES)).toContain("61 of them");
  });
});
