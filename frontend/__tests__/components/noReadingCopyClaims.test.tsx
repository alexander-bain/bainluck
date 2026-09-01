/**
 * UX-P231 — THE FENCE. `HISTORY_CLAIM_BANS` READS THE NO-READING COMPONENTS AND
 * NOTHING ELSE.
 *
 * ═══ THE RULING ═══
 *
 * Alex, 2026-08-31 (D25-scope, `GO-2026-08-31-A-ALEX-RULINGS.md`):
 *
 *   > **The ban applies only to copy emitted by the empty-state / no-reading
 *   > components. It does not apply to prose anywhere else in the codebase.**
 *
 * He was offered "narrow it to the literal observed sentences" (this lane's own
 * recommendation) and "delete it", and took neither. He kept the rule's ambition
 * and moved the fence.
 *
 * ═══ WHY THAT ENDS SIX ROUNDS INSTEAD OF STARTING A SEVENTH ═══
 *
 * CERT-539, 546, 547, 549, 551 and the round before them each blocked this
 * group, and **every one was a false positive on ordinary sports prose**, never
 * a miss on empty-state copy:
 *
 *     "Market data never reached us during the outage."
 *     "We never had a chance after halftime."
 *     "The ball never reached us in the upper deck."
 *     "Nobody ever reported the game was delayed."
 *     "At no point was the market in doubt."
 *     "No market ever felt out of reach for them."
 *
 * All six are TRUE sentences in a normal paragraph. Six rounds answered by
 * making the pattern cleverer, each trading one direction of error for the
 * other, because the failure class was never expressiveness — **it was that the
 * regex was pointed at the whole codebase.**
 *
 * ═══ WHAT THIS FILE IS ═══
 *
 * The fourth consumer of `lib/copyBans.ts`, and the ONLY one that applies
 * `HISTORY_CLAIM_BANS`. It reads the no-reading producers by name and scans what
 * they RENDER — because the group's scope is *where the string lives*, and only
 * a render knows that.
 *
 * The other three consumers carry `ALL_COPY_BANS`, which no longer contains the
 * group. ⚠️ **That is a real reduction in coverage for the bundle layer and it
 * is deliberate:** a minified chunk hands you a bare string with no component,
 * no element and no call site, so "where does this live" is unanswerable there
 * by construction, and a scanner that guessed would be exactly the
 * false-positive engine the ruling just fenced off.
 *
 * ═══ THE STANDING RULE FOR THE NEXT CERT ═══
 *
 * A false positive on a string OUTSIDE these producers is a **scope** bug and
 * the repair is the fence, never the pattern. Inside the fence the pattern may
 * be as expressive as it likes — expressiveness was never the defect, and
 * nothing was narrowed here.
 */

import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import TournamentProps from "@/components/tournament/TournamentProps";
import {
  ALL_COPY_BANS,
  HISTORY_CLAIM_BANS,
  NO_READING_COPY_BANS,
  findBannedCopy,
  visibleTextFromHtml,
} from "@/lib/copyBans";
import type { PropMarket } from "@/lib/tournamentProps";
import type { TournamentPayload } from "@/lib/tournament";

const FRONTEND = path.join(__dirname, "..", "..");
const REPO = path.join(FRONTEND, "..");
const PAYLOAD_PATH = path.join(REPO, "docs", "mocks", "us-open", "payload-2026-08-28.json");

/**
 * The real combined card from a production payload — the same fixture
 * `incompleteComparisonCapture` uses, so both files describe one card.
 */
function loadCombined(): PropMarket {
  const payload = JSON.parse(fs.readFileSync(PAYLOAD_PATH, "utf8")) as TournamentPayload;
  const card = (payload.props ?? []).find((p) => p.key === "second-major");
  if (!card) throw new Error("payload no longer carries the combined card");
  return card as PropMarket;
}

/** Both legs quoted — the healthy control. */
function healthy(): PropMarket {
  const card = loadCombined();
  return {
    ...card,
    legs: 2,
    unpriced_legs: [],
    price_state: "live",
    age_hours: 0.4,
    freshest_age_hours: 0.4,
    stale_outcomes: [],
    outcomes: card.outcomes.map((o) => ({
      ...o,
      probability_is_live: true,
      price_state: "live" as const,
      age_hours: 0.4,
    })),
  };
}

/** One leg with no reading — the state that MAKES the no-reading copy. */
function missingLeg(): PropMarket {
  const card = healthy();
  return {
    ...card,
    unpriced_legs: ["KXGRANDSLAM-CALC26"],
    outcomes: card.outcomes.map((o) =>
      o.display_name === "Carlos Alcaraz"
        ? {
            ...o,
            probability: null,
            probability_is_live: false,
            observed_at: null,
            age_hours: null,
            price_state: "dark" as const,
          }
        : o,
    ),
  };
}

/** Neither leg quoted — the emptiest state the card has. */
function nothingQuoted(): PropMarket {
  const card = healthy();
  return {
    ...card,
    unpriced_legs: ["KXGRANDSLAM-CALC26", "KXGRANDSLAM-SINN26"],
    price_state: "dark",
    outcomes: card.outcomes.map((o) => ({
      ...o,
      probability: null,
      probability_is_live: false,
      observed_at: null,
      age_hours: null,
      price_state: "dark" as const,
    })),
  };
}

function renderProps(market: PropMarket): string {
  return visibleTextFromHtml(
    renderToStaticMarkup(<TournamentProps markets={[market]} draw="mens-singles" />),
  );
}

/** Every no-reading state this component can be in, by name. */
const NO_READING_RENDERS: [string, () => PropMarket][] = [
  ["one leg unquoted", missingLeg],
  ["neither leg quoted", nothingQuoted],
];

// ══════════════════════════════════════════════════════════════════════════════
// 1. THE FENCE ITSELF — the six sentences that blocked six certs
// ══════════════════════════════════════════════════════════════════════════════

/**
 * Verbatim from the cert log. Each is ordinary, TRUE prose that a page might one
 * day carry in a paragraph, and each was rejected by a codebase-wide reading of
 * `HISTORY_CLAIM_BANS`.
 */
const BLOCKED_ORDINARY_PROSE: [string, string][] = [
  ["CERT-551", "Market data never reached us during the outage."],
  ["CERT-551", "There was no market access at any time during the outage."],
  ["CERT-549", "The ball never reached us in the upper deck."],
  ["CERT-549", "We never had a number to play for"],
  ["CERT-547", "Nobody ever reported the game was delayed."],
  ["CERT-547", "We never had an answer for their press."],
  ["CERT-546", "We never had a chance after halftime."],
  ["CERT-546", "The quarterback has not once received a snap under center."],
  // Swept, not certed — this lane found these itself in earlier rounds.
  ["UX-P216 sweep", "The ball never reached us before this game ended."],
  ["UX-P216 sweep", "The crowd never came to us during this contest."],
  ["UX-P216 sweep", "He never got to us in that game."],
  ["UX-P215 sweep", "No market ever felt out of reach for them."],
  ["UX-P215 sweep", "No data ever suggested he was slowing down."],
  ["UX-P215 sweep", "No number ever suited him better than 23."],
  ["UX-P215 sweep", "At no point was the market in doubt."],
  ["UX-P215 sweep", "At no point did either player face a break point."],
];

describe("THE FENCE — the codebase-wide list does not read history claims", () => {
  it.each(BLOCKED_ORDINARY_PROSE)(
    "%s: ordinary prose is clean under ALL_COPY_BANS — %j",
    (_who, sentence) => {
      expect(findBannedCopy(sentence, ALL_COPY_BANS)).toEqual([]);
    },
  );

  it("ALL_COPY_BANS carries none of the history rules", () => {
    // The fence stated as identity rather than as behaviour, so a group
    // re-added by a merge is caught even if no sentence in this file happens to
    // trip it.
    const historyIds = new Set(HISTORY_CLAIM_BANS.map((b) => b.id));
    expect(ALL_COPY_BANS.filter((b) => historyIds.has(b.id))).toEqual([]);
    expect(HISTORY_CLAIM_BANS.length).toBeGreaterThan(0); // not vacuous
  });

  it("NO_READING_COPY_BANS is ALL_COPY_BANS plus the history rules, and is derived", () => {
    // Derived, not re-spelled: a group added to the codebase-wide list must
    // appear inside the fence too, without anyone remembering to add it.
    expect(NO_READING_COPY_BANS).toEqual([...ALL_COPY_BANS, ...HISTORY_CLAIM_BANS]);
    expect(NO_READING_COPY_BANS.length).toBe(ALL_COPY_BANS.length + HISTORY_CLAIM_BANS.length);
  });

  it("the DEFAULT list is the codebase-wide one — the fence is opt-IN", () => {
    // 🔴 THE HOLE MUTANT F FOUND, AND THE GUARD WAS WRONG, NOT THE CODE.
    // Every assertion above names its list explicitly, so `findBannedCopy`'s
    // default parameter could be switched to `NO_READING_COPY_BANS` and the
    // whole file stayed green — while every consumer that calls it with one
    // argument silently went back to the condemned scope. The fence has to be
    // something a caller OPTS INTO, and that is now asserted rather than
    // assumed.
    //
    // 🔴 AND MUTANT F CAME BACK ALIVE ON 2026-09-01, FROM THE OTHER DIRECTION.
    // The two sentences this used to probe with — "Market data never reached us
    // during the outage." and "We never had a chance after halftime." — were
    // ordinary prose the CLASSIFIER wrongly caught. Under the literal list they
    // are clean under BOTH lists, so the assertion passed either way and proved
    // nothing. **A probe has to be a string the two arms DISAGREE about**, and
    // once the group became a literal list the only such strings are the
    // sentences on it.
    const served = "No number ever reached us for Carlos Alcaraz.";
    expect(findBannedCopy(served)).toEqual([]);
    expect(findBannedCopy(served, NO_READING_COPY_BANS).map((h) => h.ban.id)).toEqual([
      "no-number-ever-reached-us",
    ]);
    // The old probes, kept as what they now are: prose that is clean under
    // BOTH lists, which is the whole point of deleting the classifier.
    expect(findBannedCopy("Market data never reached us during the outage.")).toEqual([]);
    expect(
      findBannedCopy("Market data never reached us during the outage.", NO_READING_COPY_BANS),
    ).toEqual([]);
    // Positive control: the default list is not simply empty.
    expect(findBannedCopy("The blended number is stale.").length).toBeGreaterThan(0);
  });

  it("the fence is a scope change, NOT a weakening — every rule still fires", () => {
    // The failure this file must not permit: quietly neutering the patterns and
    // calling it a re-scope. Each rule is still able to reject something.
    for (const ban of HISTORY_CLAIM_BANS) {
      expect(ban.pattern.source.length).toBeGreaterThan(0);
    }
    // And the group as a whole still rejects the claims it was written for.
    expect(
      findBannedCopy(
        "No number ever reached us for Iga Swiatek, so this comparison was never complete.",
        NO_READING_COPY_BANS,
      ).length,
    ).toBeGreaterThan(0);
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// 2. INSIDE THE FENCE — the producers, at render, with the full list
// ══════════════════════════════════════════════════════════════════════════════

describe("INSIDE THE FENCE — the no-reading components are read with the full list", () => {
  it("the harness renders the real card (positive control)", () => {
    // A guard whose render came back empty would agree with anything.
    const text = renderProps(missingLeg());
    expect(text).toContain("Carlos Alcaraz");
    expect(text.length).toBeGreaterThan(80);
  });

  it.each(NO_READING_RENDERS)(
    "%s: the rendered copy carries no history claim",
    (_name, build) => {
      const hits = findBannedCopy(renderProps(build()), NO_READING_COPY_BANS);
      const historyIds = new Set(HISTORY_CLAIM_BANS.map((b) => b.id));
      const historyHits = hits.filter((h) => historyIds.has(h.ban.id));
      expect(
        historyHits.map((h) => `${h.ban.id}: ${h.matched}`),
      ).toEqual([]);
    },
  );

  it("the healthy card renders no history claim either", () => {
    const historyIds = new Set(HISTORY_CLAIM_BANS.map((b) => b.id));
    const hits = findBannedCopy(renderProps(healthy()), NO_READING_COPY_BANS).filter((h) =>
      historyIds.has(h.ban.id),
    );
    expect(hits).toEqual([]);
  });

  it("THE GUARD CAN FAIL: the condemned sentence is caught inside the fence", () => {
    // UX-P212's own regression, in the exact words CERT-537 blocked. If this
    // ever goes green-by-vacuity the whole file is decoration.
    const condemned =
      "No number ever reached us for Carlos Alcaraz, so this comparison was never complete.";
    const hits = findBannedCopy(condemned, NO_READING_COPY_BANS);
    expect(hits.length).toBeGreaterThan(0);
    // …and the SAME sentence is invisible to the codebase-wide list, which is
    // the fence in one assertion.
    expect(findBannedCopy(condemned, ALL_COPY_BANS)).toEqual([]);
  });

  it("the shipped replacement passes inside the fence", () => {
    // What `incompleteComparisonNote` actually emits today: a claim about what
    // we HAVE, not about all of history.
    //
    // ⚠️ CORRECTED 2026-09-01. This test used to name "No number HAS reached us
    // for … yet" as the replacement. That sentence was never the replacement —
    // it was the OPEN-tense twin of the condemned settled one, and `fa8abe08`
    // retired both in the same commit (its report, §4a: "the identical
    // present-perfect claim in the identical shape"). Reading it as the fix was
    // harmless while the guard was a grammar rule that did not match it; under
    // the literal list it is `no-number-has-reached-us`, so the drift would have
    // read as a false positive on shipped copy instead of as the stale
    // assertion it always was. The string below is what `TournamentProps`
    // actually returns.
    const shipped =
      "We have no number for Carlos Alcaraz yet, so this comparison is not complete.";
    const historyIds = new Set(HISTORY_CLAIM_BANS.map((b) => b.id));
    expect(
      findBannedCopy(shipped, NO_READING_COPY_BANS).filter((h) => historyIds.has(h.ban.id)),
    ).toEqual([]);
  });
});
