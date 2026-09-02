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
 * ═══ WHAT THE SHIP IS, AFTER ux/1008 RE-MEASURED IT (CERT-724) ═══
 *
 * Round one of this change claimed two ships and only one of them was real.
 * CERT-724 blocked it for the second, and re-measuring proved the block
 * understated the problem. Both corrections are pinned below, because a claim
 * that was disproved once will be re-made by the next reader of the directive.
 *
 * **THE SHIP IS THE MUTED CARD, AND ONLY THE MUTED CARD.** Alex's second
 * sentence — *"when none exists, render it visibly non-linked (muted) so
 * nobody clicks a dead card"* — is a real, reachable, currently-broken thing:
 * two of the twelve cards on this very payload cannot link, and on `main` they
 * render pixel-identical to the ten that can.
 *
 * **THE LINK RESOLUTION IS A NO-OP, AND THAT IS ASSERTED, NOT ASSUMED.** The
 * claim was that reading `event_links.by_matchup` links cards that the row's
 * own `event_id` could not. It does not, and it cannot, because the server
 * builds one from the other — `tournament_slate.py:692`:
 *
 *     "event_id": matchup.get("event_id") or (event_ids or {}).get(...)
 *
 * where `event_ids` **is** `by_matchup`. A slate row's own id is therefore a
 * SUPERSET of the map, and the fallback can never fire productively. Measured
 * on this fixture, rendered through the real component: the two rules produce
 * the identical set of ten hrefs, and the live Zverev–Sonego row is an anchor
 * under BOTH. `noOp` below pins that so the claim cannot come back unmeasured.
 *
 * **AND THE BRACKET PATH IS UNREACHABLE BY DESIGN.** CERT-724's finding, kept
 * as a guard rather than papered over: `matchListFromBracket` nulls `eventId`
 * and `matchupKey` together, so a bracket row with no joined slate row has no
 * key for the map either. Round one's guard hid this by calling
 * `matchListFromSlate` on rows with only `event_id` removed and labelling them
 * "asBracketRows" — which preserves the very key the real adapter discards.
 * The honest arm goes through `buildMatchList`, and it asserts the card is
 * DEAD. Fixing it is not queued, because there is no ship behind it:
 * `ingest_espn_draw.py` deliberately never writes `draw_slot`, so
 * `build_bracket` returns `[]` and production has no bracket rows at all.
 *
 * ═══ THE ARMS ═══
 *
 *  1. **The cohort is still the cohort.** If the fixture is edited or replaced,
 *     everything below is measuring a population it was not written for.
 *  2. **The link rule is a no-op** — map and no-map render the same hrefs.
 *  3. **A bracket row cannot use the map** — CERT-724's finding, pinned.
 *  4. **The `espn:` row never links** — the trap above.
 *  5. **An unlinked card is visibly unlinked** — Alex's second sentence, and
 *     THE SHIP. Not `data-linked="false"`, which is a hook for a harness; a
 *     treatment a person can see without hovering, on a phone that has no
 *     hover.
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
import { buildBracket } from "@/lib/bracket";
import { buildMatchList, matchListFromSlate } from "@/lib/matchList";
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

/**
 * REGRESSION, NOT THE SHIP. Every arm in here is green on `main` as well —
 * deliberately, and it is labelled so no future reader mistakes it for
 * evidence that this change did something. It pins that the live half of the
 * hub routes to its match pages AT ALL, which is worth keeping nailed down.
 */
describe("ux/1002 — the live card opens its match page (green on main too)", () => {
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

/**
 * ═══ THE MEASUREMENT THAT RETIRES ROUND ONE'S CLAIM ═══
 *
 * Round one said reading the map links cards the row's own `event_id` cannot,
 * and measured "0 of 12 -> 10 of 12" to prove it. That measurement was taken
 * on rows it had itself stripped of `event_id`; on the unedited payload the
 * two rules are indistinguishable, because the server derives one from the
 * other (see the header). This is the arm that says so, and it is written to
 * FAIL if anyone ever makes the map matter — at which point the claim becomes
 * true and this guard, correctly, becomes the thing that has to change.
 */
describe("ux/1002 — reading the published map changes nothing on real rows", () => {
  const hrefsOf = (html: string) => (html.match(/href="\/events\/\d+"/g) ?? []).sort();

  it("renders the identical link set with the map and without it", () => {
    const entries = matchListFromSlate(MATCHES);

    // The rule this branch ships.
    const withMap = renderToStaticMarkup(
      <TournamentMatches entries={entries} eventIds={BY_MATCHUP} initialExpanded />
    );
    // `eventIds` omitted IS `main`'s rule: the row's own `eventId`, nothing else.
    const withoutMap = renderToStaticMarkup(
      <TournamentMatches entries={entries} initialExpanded />
    );

    expect(hrefsOf(withMap)).toEqual(hrefsOf(withoutMap));
    expect(hrefsOf(withoutMap)).toHaveLength(10);
    // Including Alex's card, which `main` already linked.
    expect(withoutMap).toContain(`href="/events/${LIVE_EVENT}"`);
    expect(withoutMap.match(/data-linked="false"/g) ?? []).toHaveLength(2);
  });

  it("holds because every mapped key is already stamped on its row", () => {
    // The structural reason, asserted on the DATA so it cannot be satisfied by
    // the code under test. `build_slate` fills `event_id` from `by_matchup`
    // when the register does not pin one, so "in the map" implies "on the row".
    const mappedButUnstamped = MATCHES.filter(
      (m) =>
        !m.event_id &&
        typeof m.matchup_key === "string" &&
        !m.matchup_key.startsWith("espn:") &&
        typeof BY_MATCHUP[m.matchup_key] === "number"
    );
    expect(mappedButUnstamped).toHaveLength(0);
  });
});

/**
 * ═══ CERT-724's FINDING, KEPT AS A GUARD RATHER THAN FIXED ═══
 *
 * The cert was right: `matchListFromBracket` sets `eventId` and `matchupKey`
 * from the same joined slate row, so a bracket fixture the slate has dropped
 * has NEITHER, and the map it could otherwise consult is keyed on the key it
 * just threw away. Round one's guard could not see this because it built its
 * "bracket" rows with `matchListFromSlate`, which keeps the key.
 *
 * This goes through `buildMatchList` — the function the page actually calls —
 * and asserts the card is dead, because it is. It is NOT queued as a fix:
 * `ingest_espn_draw.py` deliberately leaves `draw_slot` null, `build_bracket`
 * returns `[]`, and production ships `{"mens-singles": [], "womens-singles": []}`
 * today. There is no user behind this path to ship to, and building an
 * id-anchored bracket key with no reachable reader would be architecture for
 * its own sake. When draw slots are populated, THIS is the guard that will go
 * red first and name the work.
 */
describe("ux/1002 — a bracket row with no slate row cannot use the map (CERT-724)", () => {
  const slot = (entity_key: string, display_name: string) => ({
    entity_key,
    display_name,
    seed: null,
    probability: null,
  });

  /** A 4-slot draw: two semi-finals feeding a final. */
  const SLOTS = [
    slot("alexander-zverev", "Alexander Zverev"),
    slot("lorenzo-sonego", "Lorenzo Sonego"),
    slot("carlos-alcaraz", "Carlos Alcaraz"),
    slot("jaume-munar", "Jaume Munar"),
  ];

  it("renders the card dead even though the map holds its answer", () => {
    const rounds = buildBracket(SLOTS);
    // The slate is EMPTY — exactly the case the map was supposed to cover: a
    // fixture already played or decided, dropped from the slate, still in
    // `by_matchup`. 28 ALREADY_PLAYED + 85 DECIDED on today's live payload.
    const entries = buildMatchList({ rounds, slate: [] });

    const zverev = entries.find((e) => e.sides.some((s) => s.entityKey === "alexander-zverev"));
    expect(zverev).toBeDefined();
    expect(zverev!.source).toBe("bracket");
    // BOTH null — this is the finding. The key the map needs is discarded with
    // the id, so the fallback has nothing to look up.
    expect(zverev!.eventId).toBeNull();
    expect(zverev!.matchupKey).toBeNull();

    const html = renderToStaticMarkup(
      <TournamentMatches entries={entries} eventIds={BY_MATCHUP} initialExpanded />
    );
    expect(html.match(/href="\/events\/\d+"/g) ?? []).toHaveLength(0);
    // …and the map really did hold an answer for this pair, so the arm above
    // is a refusal to reach it and not an empty map.
    expect(BY_MATCHUP[LIVE_KEY]).toBe(LIVE_EVENT);
  });

  it("CONTROL: the same bracket links when the slate row survives", () => {
    // Proves the deadness above is caused by the DROPPED SLATE ROW and not by
    // something structural about bracket rendering. Same draw, same map, one
    // slate row restored — the card links.
    const rounds = buildBracket(SLOTS);
    const liveRow = MATCHES.find((m) => m.matchup_key === LIVE_KEY)!;
    const entries = buildMatchList({ rounds, slate: [liveRow] });

    const zverev = entries.find((e) => e.sides.some((s) => s.entityKey === "alexander-zverev"));
    expect(zverev!.matchupKey).toBe(LIVE_KEY);
    const html = renderToStaticMarkup(
      <TournamentMatches entries={entries} eventIds={BY_MATCHUP} initialExpanded />
    );
    expect(html).toContain(`href="/events/${LIVE_EVENT}"`);
  });

  it("and production has no bracket rows to be wrong about", () => {
    // The reason this is a guard and not a queued fix. `build_bracket` refuses
    // anything that is not a power of two, and an all-null draw yields rounds
    // whose every slot is undetermined — which `roundIsUnreached` then drops.
    expect(buildBracket([])).toEqual([]);
    expect(buildMatchList({ rounds: buildBracket([]), slate: [] })).toEqual([]);
  });
});

describe("ux/1002 — the resolver prefers the row's own id and never invents", () => {
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
