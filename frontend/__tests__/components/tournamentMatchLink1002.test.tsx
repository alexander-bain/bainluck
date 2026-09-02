/**
 * ux/1002 — THE LIVE HALF OF THE US OPEN HUB LINKS TO ITS MATCHES, AND THE
 * CARDS THAT CANNOT LINK SAY SO.
 *
 * Alex, on production at 22:00 PT 2026-09-01: *"the Zverev–Sonego card (LIVE,
 * '4TH SET') is not clickable. CERT-703 wired only the FINISHED list. The API
 * already provides the mapping (event_links.by_matchup -> 15293811 for
 * Zverev)."*
 *
 * The fixture is the unedited payload from that hour
 * (`tournamentHubLinkMap.20260901.json`): 12 slate rows, a 91-entry
 * `by_matchup`, and — the part that makes this file worth its length — a live
 * TRAP that the obvious reading of the directive walks straight into.
 *
 * ═══ THE TRAP, ON TODAY'S REAL DATA ═══
 *
 * "Link every card from `by_matchup`" is one line and it would ship a lie.
 *
 * One of the 12 rows is `espn:182703`. The register says that fixture is
 * **Jodar v Kokkinakis**; ESPN, who is watching it, says it is **Bu
 * Yunchaokete v Jodar**. `build_slate` withholds the register's pairing
 * (`PAIRING_DISAGREES`), rebuilds the card from the authority with no price,
 * and re-keys it `espn:182703` so it cannot reach a consumer that keys on the
 * register (Q503/Q505). Meanwhile the register's key for that same fixture,
 * `mens-singles:rafael-jodar-vs-thanasi-kokkinakis:2026-08-30`, IS in
 * `by_matchup` and points at **event 15300739, "Jodar VS Kokkinakis"** —
 * verified against `/api/events/15300739` on the day.
 *
 * So the map holds a confident answer for a card whose two names it does not
 * describe. A reader who taps "Bu Yunchaokete v Jodar" and lands on "Jodar vs
 * Kokkinakis" has been lied to by the one surface whose posture is that
 * identity is pinned. The `espn:` refusal is the only thing standing between
 * those two facts, and it is asserted here on the real rows rather than on a
 * hand-built one, because a hand-built row cannot go stale into a wrong link.
 *
 * ═══ THE FIVE ARMS ═══
 *
 *  1. **The cohort is still the cohort.** If the fixture is edited or replaced,
 *     everything below is measuring a population it was not written for.
 *  2. **The live card is an anchor** to `/events/15293811` — the ship.
 *  3. **RED-FIRST on the bracket path.** A bracket-sourced row carries no
 *     `event_id` of its own; before this change it could only inherit one from
 *     a slate row joined BY NAME PAIR, and the slate holds only fixtures still
 *     to come. Resolved through the map it links; through the old rule it does
 *     not. This is the arm that fails on `main`.
 *  4. **The `espn:` row never links** — the trap above.
 *  5. **An unlinked card is visibly unlinked** — Alex's second sentence. Not
 *     `data-linked="false"`, which is a hook for a harness; a treatment a
 *     person can see without hovering, on a phone that has no hover.
 *
 * ═══ WHY THE NEW SYMBOLS ARE REQUIRED LAZILY ═══
 *
 * `matchEventHref`, `matchupEventHref` and `UNLINKED_CARD_CLASS` do not exist
 * before this change, so importing them at module scope makes the pre-change
 * run fail with `Could not locate module` — a story about the harness, not a
 * detected defect (gotcha #124: read the exit code's VALUE). The arms that
 * carry the red-first claim therefore assert on **rendered markup**, which
 * exists identically in both arms, and the unit-level arms `require()` the new
 * modules inside the test body where a missing one is plainly a missing module.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import TournamentMatches from "@/components/tournament/TournamentMatches";
import { matchListFromSlate } from "@/lib/matchList";
import type { MatchListEntry } from "@/lib/matchList";
import type { SlateMatch } from "@/lib/slate";

/* eslint-disable @typescript-eslint/no-require-imports */
const lazy = {
  get matchEventHref() {
    return require("@/lib/matchList").matchEventHref as (
      entry: Pick<MatchListEntry, "eventId" | "matchupKey">,
      eventIds?: Record<string, number> | null
    ) => string | null;
  },
  get matchupEventHref() {
    return require("@/lib/tournamentEventLink").matchupEventHref as (
      key: string | null | undefined,
      eventIds?: Record<string, number> | null
    ) => string | null;
  },
  get UNLINKED_CARD_CLASS() {
    return require("@/components/EventCardShell").UNLINKED_CARD_CLASS as string;
  },
};
/* eslint-enable @typescript-eslint/no-require-imports */

const CAPTURE = JSON.parse(
  fs.readFileSync(
    path.join(__dirname, "..", "fixtures", "tournamentHubLinkMap.20260901.json"),
    "utf8"
  )
) as {
  slate: { count: number; in_progress: number; authority_pairings: number };
  matches: SlateMatch[];
  event_links: { by_matchup: Record<string, number>; linked: number };
};

const MATCHES = CAPTURE.matches;
const BY_MATCHUP = CAPTURE.event_links.by_matchup;

/** Zverev v Sonego — the card in Alex's report. */
const LIVE_KEY = "mens-singles:alexander-zverev-vs-lorenzo-sonego:2026-08-30";
const LIVE_EVENT = 15293811;

/** The authority-named row: shown as Bu Yunchaokete v Jodar, keyed off ESPN. */
const AUTHORITY_KEY = "espn:182703";
/** …whose register key resolves, confidently and wrongly, to another match. */
const WITHHELD_KEY = "mens-singles:rafael-jodar-vs-thanasi-kokkinakis:2026-08-30";
const WRONG_EVENT = 15300739;

describe("ux/1002 — the cohort this guard was written for", () => {
  it("is the captured payload, unedited", () => {
    expect(MATCHES).toHaveLength(CAPTURE.slate.count);
    expect(MATCHES).toHaveLength(12);
    expect(Object.keys(BY_MATCHUP)).toHaveLength(91);

    // The live row Alex named, with the id he said the API already had.
    const live = MATCHES.filter((m) => m.live_state === "in_progress");
    expect(live).toHaveLength(1);
    expect(live[0].matchup_key).toBe(LIVE_KEY);
    expect(BY_MATCHUP[LIVE_KEY]).toBe(LIVE_EVENT);

    // The trap is still armed: the withheld pairing has a confident entry in
    // the map, and the card that replaced it carries a different key.
    expect(CAPTURE.slate.authority_pairings).toBe(1);
    expect(BY_MATCHUP[WITHHELD_KEY]).toBe(WRONG_EVENT);
    expect(MATCHES.some((m) => m.matchup_key === AUTHORITY_KEY)).toBe(true);
    expect(BY_MATCHUP[AUTHORITY_KEY]).toBeUndefined();

    // Exactly two of the twelve cannot link — the two arm 5 is about. Stated
    // from the fixture's own fields rather than through the resolver, so this
    // arm describes the DATA and cannot be satisfied by the code under test.
    const unlinkable = MATCHES.filter(
      (m) =>
        !m.event_id &&
        !(
          typeof m.matchup_key === "string" &&
          !m.matchup_key.startsWith("espn:") &&
          BY_MATCHUP[m.matchup_key] > 0
        )
    );
    expect(unlinkable.map((m) => m.matchup_key).sort()).toEqual([
      AUTHORITY_KEY,
      "womens-singles:mayar-sherif-vs-nikola-bartunkova:2026-08-30",
    ]);
  });
});

describe("ux/1002 — the live card opens its match page", () => {
  it("renders the live row as an anchor to /events/15293811", () => {
    const entries = matchListFromSlate(MATCHES);
    const html = renderToStaticMarkup(
      <TournamentMatches entries={entries} eventIds={BY_MATCHUP} />
    );

    const row = html.slice(
      html.indexOf(`data-match="${LIVE_KEY}"`),
      html.indexOf("</li>", html.indexOf(`data-match="${LIVE_KEY}"`))
    );
    // The row IS the live one — without this the assertion below could pass on
    // any card that happens to sit at that offset.
    expect(row).toContain('data-testid="match-live"');
    expect(row).toContain(`href="/events/${LIVE_EVENT}"`);
    expect(row).toContain('data-linked="true"');
    // An anchor, not a div wearing an href attribute.
    expect(row).toMatch(/<a[^>]+href="\/events\/15293811"/);
  });

  it("links the upcoming R128 cards too, not only the live one", () => {
    // Alex's ask is "every Round-of-128 card (live + upcoming)". A fix that
    // special-cased `live_state === "in_progress"` would pass the arm above.
    const entries = matchListFromSlate(MATCHES);
    const html = renderToStaticMarkup(
      <TournamentMatches entries={entries} eventIds={BY_MATCHUP} initialExpanded />
    );
    const hrefs = html.match(/href="\/events\/\d+"/g) ?? [];
    expect(hrefs).toHaveLength(10);
    expect(html.match(/data-linked="false"/g) ?? []).toHaveLength(2);
  });
});

describe("ux/1002 — a bracket-sourced row resolves off the published map", () => {
  /**
   * ═══ THE RED-FIRST ARM, AND IT IS ASSERTED ON MARKUP ═══
   *
   * A bracket row's `eventId` is `null` by construction: `matchListFromBracket`
   * inherits one only from a slate row joined by unordered NAME PAIR, and the
   * slate drops every fixture already played or decided (28 + 84 on this very
   * payload). The matchup key survives that join failure; the name pair does
   * not. So the population is simulated exactly — the real rows with the one
   * field a bracket row lacks removed — and rendered through the real
   * component. Under the old rule every card here is dead; under the new one
   * the ten resolvable ones link.
   */
  const asBracketRows = () =>
    matchListFromSlate(MATCHES.map((m) => ({ ...m, event_id: null })));

  it("links rows that have a matchup key and no event_id of their own", () => {
    const html = renderToStaticMarkup(
      <TournamentMatches entries={asBracketRows()} eventIds={BY_MATCHUP} initialExpanded />
    );
    expect(html.match(/href="\/events\/\d+"/g) ?? []).toHaveLength(10);
    expect(html).toContain(`href="/events/${LIVE_EVENT}"`);
  });

  it("CONTROL: the same rows with no map stay dead", () => {
    // Without this the arm above passes just as well against a change that
    // linked every card from something other than the map.
    const html = renderToStaticMarkup(
      <TournamentMatches entries={asBracketRows()} initialExpanded />
    );
    expect(html.match(/href="\/events\/\d+"/g) ?? []).toHaveLength(0);
    expect(html.match(/data-linked="false"/g) ?? []).toHaveLength(12);
  });

  it("prefers the row's own id when it has one, and never invents", () => {
    const { matchEventHref } = lazy;
    expect(matchEventHref({ eventId: 42, matchupKey: LIVE_KEY }, BY_MATCHUP)).toBe(
      "/events/42"
    );
    expect(matchEventHref({ eventId: null, matchupKey: null }, BY_MATCHUP)).toBeNull();
    expect(
      matchEventHref({ eventId: null, matchupKey: "not-in-the-map" }, BY_MATCHUP)
    ).toBeNull();
    // A map that round-tripped through Redis badly must cost a link, not a render.
    expect(matchEventHref({ eventId: null, matchupKey: "x" }, { x: 0 })).toBeNull();
    expect(matchEventHref({ eventId: null, matchupKey: "x" }, { x: -1 })).toBeNull();
    expect(
      matchEventHref(
        { eventId: null, matchupKey: "x" },
        { x: Number.NaN } as Record<string, number>
      )
    ).toBeNull();
  });
});

describe("ux/1002 — the authority-named card never links to the withheld pairing", () => {
  it("refuses the espn: key even though the map answers for that fixture", () => {
    const { matchupEventHref } = lazy;
    // The refusal, at the resolver.
    expect(matchupEventHref(AUTHORITY_KEY, BY_MATCHUP)).toBeNull();
    // And it is a REFUSAL, not a miss: the map really does hold a wrong answer
    // one key away. Without this line the arm above passes for the boring
    // reason that nothing was there.
    expect(matchupEventHref(WITHHELD_KEY, BY_MATCHUP)).toBe(`/events/${WRONG_EVENT}`);
    // Hostile arm: even if an overlay starts writing espn:-prefixed entries.
    expect(matchupEventHref(AUTHORITY_KEY, { [AUTHORITY_KEY]: 999 })).toBeNull();
  });

  it("renders that card with no anchor at all", () => {
    const entries = matchListFromSlate(MATCHES);
    const html = renderToStaticMarkup(
      <TournamentMatches entries={entries} eventIds={BY_MATCHUP} initialExpanded />
    );
    const row = html.slice(
      html.indexOf(`data-match="${AUTHORITY_KEY}"`),
      html.indexOf("</li>", html.indexOf(`data-match="${AUTHORITY_KEY}"`))
    );
    expect(row).toContain('data-linked="false"');
    expect(row).not.toContain("href=");
    // The wrong event id appears nowhere on the page, in any attribute.
    expect(html).not.toContain(String(WRONG_EVENT));
  });
});

describe("ux/1002 — a card that cannot link looks like one", () => {
  it("gives the unlinked card a treatment that survives having no mouse", () => {
    const entries = matchListFromSlate(MATCHES);
    const html = renderToStaticMarkup(
      <TournamentMatches entries={entries} eventIds={BY_MATCHUP} initialExpanded />
    );

    const unlinkedRow = html.slice(
      html.indexOf(`data-match="${AUTHORITY_KEY}"`),
      html.indexOf("</li>", html.indexOf(`data-match="${AUTHORITY_KEY}"`))
    );
    const linkedRow = html.slice(
      html.indexOf(`data-match="${LIVE_KEY}"`),
      html.indexOf("</li>", html.indexOf(`data-match="${LIVE_KEY}"`))
    );

    // ═══ THE RED-FIRST CLAIM, ON MARKUP AND NOTHING ELSE ═══
    //
    // Asserted before the constant is touched, so a pre-change run fails
    // HERE — on the rendered difference a reader would see — rather than on a
    // missing export, which would be a story about the harness.
    //
    // CONTROL in the same breath: the LINKED card must NOT carry the
    // treatment. Without it, a change that muted every card on the page passes.
    expect(unlinkedRow).toContain("border-dashed");
    expect(linkedRow).not.toContain("border-dashed");
    expect(unlinkedRow).toContain("bg-surface-elevated");
    expect(linkedRow).toContain("cursor-pointer");
    expect(unlinkedRow).not.toContain("cursor-pointer");

    // And every token of the shared constant really is on the card, with NONE
    // of them a hover state — that was the whole defect, since the two card
    // kinds differed only in classes a phone can never trigger.
    for (const token of lazy.UNLINKED_CARD_CLASS.split(" ")) {
      expect(token).not.toMatch(/^hover:/);
      expect(unlinkedRow).toContain(token);
    }
  });

  it("still says which component drew it, and still prints the fixture", () => {
    // The card recedes; it does not disappear. These rows carry real names and
    // a real clock and all of it is true — see UNLINKED_CARD_CLASS.
    const entries = matchListFromSlate(MATCHES);
    const html = renderToStaticMarkup(
      <TournamentMatches entries={entries} eventIds={BY_MATCHUP} initialExpanded />
    );
    const row = html.slice(
      html.indexOf(`data-match="${AUTHORITY_KEY}"`),
      html.indexOf("</li>", html.indexOf(`data-match="${AUTHORITY_KEY}"`))
    );
    expect(row).toContain('data-testid="event-card"');
    expect(row).toContain("Bu Yunchaokete");
    expect(row).toContain("Rafael Jodar");
    // Nothing that reads as broken or disabled — it is neither.
    expect(row).not.toContain("cursor-not-allowed");
    expect(row).not.toContain("aria-disabled");
  });
});
