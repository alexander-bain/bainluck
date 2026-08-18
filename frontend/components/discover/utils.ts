import type {
  FeedItem,
  FeedEventData,
  FeedFuturesData,
  FeedConceptData,
  FeedConceptLeader,
  FeedTournamentData,
  FeedBundleData,
} from "@/lib/types";
import { marketEventKey, tournamentEventKey, eventPath } from "@/lib/eventKey";
// UX-P053 (#1717) — the ONE formatter for "Resolves <date>", shared with the
// tournament card rather than reimplemented here. See `resolvesLabel` below.
import { formatResolvesLabel } from "@/lib/gameTimeLabel";

// L2-175 Item 1: the single detail destination for a feed card, mirroring each leaf
// card's own <Link href>. Used for whole-card tap navigation so the hero (which is
// NOT a link) is clickable, not just the small title. Returns null for card types
// that own their internal navigation (bundles/groups/comparison sub-links).
export function feedItemHref(item: FeedItem): string | null {
  switch (item.type) {
    case "event": {
      const d = item.data as FeedEventData;
      return d?.id != null ? `/events/${d.id}` : null;
    }
    case "futures": {
      const d = item.data as FeedFuturesData;
      const conceptKey = marketEventKey(d);
      if (conceptKey) return eventPath(conceptKey);
      return d?.id != null ? `/futures/${d.id}` : null;
    }
    case "concept": {
      const d = item.data as FeedConceptData;
      return d?.key ? eventPath(d.key) : null;
    }
    case "tournament": {
      const d = item.data as FeedTournamentData;
      const key = tournamentEventKey(d);
      return key ? eventPath(key) : "/sport/golf";
    }
    default:
      return null;
  }
}

/**
 * The timing line on a futures / comparison card.
 *
 * UX-P053 (#1717) — BEYOND 7 DAYS IT USED TO SAY NOTHING, AND THE CARD BESIDE IT
 * SAID SOMETHING.
 *
 * The old rule ended `// Beyond 7 days: don't show on the card (available in
 * detail view)`. That was a defensible choice in isolation and stopped being one
 * the moment #1708 taught the tournament card to fall back to its resolution
 * date: one feed, one question ("when does this resolve?"), one wire field, two
 * opposite answers. Measured on production 2026-08-11T01:10Z at the deployed sha
 * `8bf7cce5`, across 60 unique futures cards — the dominant card type on the
 * default landing page now that #1698 is fixed:
 *
 *   - 6 printed a timing line (all resolving inside 7 days)
 *   - 49 carried a `resolution_date` on the wire and printed NOTHING
 *   - 5 had no `resolution_date` at all
 *
 * So 49 of 60 cards on the first screen of every session were silent about a
 * date they were holding, next to a golf card that printed it.
 *
 * THE FIX IS A DELEGATION, NOT A SECOND LADDER. Alex's ruling this cycle was to
 * use the IDENTICAL formatter, "one formatting authority, so the next drift is
 * unrepresentable rather than refiled" — so the far-horizon branch calls
 * `formatResolvesLabel`, the same function the tournament card calls, and this
 * module constructs no "Resolves" string of its own.
 *
 * WHAT DELIBERATELY DID NOT CHANGE. The inside-7-days ladder is untouched:
 * "Closes in 45m" is a better line than "Resolves Aug 11" for a market closing
 * today, and rewriting it would have moved the 6 cards that were already correct
 * in the same commit that fixed the 49 that were silent — making the acceptance
 * unmeasurable (the UX-P045 rule).
 *
 * DECLARED BEHAVIOUR CHANGE: a past `resolution_date` used to print "Resolved".
 * That is the guess #1700 refused and #1708 explicitly banked against —
 * `resolution_date` is the SCHEDULED resolution, never an observed one
 * (`reference_futures_markets_no_transition_timestamp`), so a date merely passing
 * is not evidence a market settled. It is now silent, and the authority is the
 * one place that decides. Measured blast radius: ZERO cards. The feed hard-
 * excludes past-resolution markets in SQL (`feed.py:5043`) and blocks them again
 * as `past_resolution_date` (`feed.py:3054`), and 0 of 60 live cards reached the
 * branch — though 8,609 open markets (2,260 of them tier 1-2) are in the class,
 * so it was a live landmine behind two filters rather than dead code.
 */
export function resolvesLabel(d: string | null | undefined): string {
  if (!d) return "";
  const date = new Date(d);
  if (Number.isNaN(date.getTime())) return "";
  const diffH = (date.getTime() - Date.now()) / 36e5;
  // A date already gone is decided FIRST, and by the authority — which answers
  // "" for it. Ordering matters and is load-bearing: `diffH < 1` is also true of
  // every negative diff, so letting a past date reach the ladder would print
  // "Closes in 1m" about a market whose date went by last year. Removing the old
  // "Resolved" branch without this line replaces one wrong claim with a worse one.
  if (diffH < 0) return formatResolvesLabel(d);
  if (diffH < 1) return `Closes in ${Math.max(1, Math.round(diffH * 60))}m`;
  if (diffH < 24) return `Closes in ${Math.round(diffH)}h`;
  if (diffH < 48) return "Closes tomorrow";
  if (diffH < 168) return `Closes ${date.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
  // Beyond 7 days the shared authority answers. It prints the year — a
  // multi-year question misread as months away is the failure #1708 named.
  return formatResolvesLabel(d);
}

/**
 * L2-164 Item 3 — 0% card display guard (web parity with #240's native
 * suppression). A default futures card's hero is its LEADING outcome's
 * probability; a leader sitting below 1% renders as a bare, live-looking "0%" —
 * the stale post-Open golf-card class Alex flagged. This is the belt-and-
 * suspenders DISPLAY check (the real ranking-side suppression is #240's backend):
 * a futures card is suppressed when its leader is sub-1% AND it carries no
 * settled/resolved context to label the number honestly.
 *
 * Never suppresses:
 *  - distribution / heatmap formats — they render a ladder (with "—" for zeros),
 *    not a bare live hero, so a low leader reads fine there.
 *  - settled markets — a resolved flag, a named winner, a settled status, or a
 *    past resolution_date mean the low number is contextual, not bare-live.
 * Non-futures items are never affected.
 *
 * UX-P053 (#1717) — THIS COMMENT USED TO CITE A LABEL THAT NO LONGER EXISTS. It
 * read "...already give the card a 'Resolved' label", which was true when
 * `resolvesLabel` printed "Resolved" for a passed date and is not true now that
 * the shared authority stays silent about one. The BEHAVIOUR here is unchanged —
 * `settledByDate` below reads `resolution_date` itself and never consulted that
 * label — but a comment asserting something the code does not do is the exact
 * defect C185 shipped behind this cycle, so it is corrected rather than left to
 * mislead the next reader into thinking suppression depends on the label.
 */
export function suppressBareZeroFuturesCard(
  item: FeedItem,
  now: number = Date.now(),
): boolean {
  if (item.type !== "futures") return false;
  const data = item.data as FeedFuturesData;
  // `discover_card` isn't in the shared FeedFuturesData type yet (same loose access
  // as DiscoverCard/FuturesCard); read it via a narrow local cast to stay
  // self-contained and avoid editing lib/types.ts.
  const format = (data as { discover_card?: { suggested_format?: string } }).discover_card
    ?.suggested_format;
  // Ladder-style formats don't show a bare hero number — leave them alone.
  if (format === "outcome_distribution" || format === "threshold_heatmap") return false;
  const leaderProb = data.top_outcomes?.[0]?.probability ?? null;
  // Only the sub-1% ("0%" when rounded) leader is the problem; a null leader
  // already renders name-only (no bare hero), so it's fine.
  if (leaderProb == null || leaderProb >= 0.01) return false;
  const status = (data.status || "").toLowerCase();
  const settledByState =
    data.resolved === true ||
    !!data.winner ||
    ["resolved", "closed", "settled", "finalized", "final"].includes(status);
  const settledByDate =
    !!data.resolution_date && new Date(data.resolution_date).getTime() < now;
  return !(settledByState || settledByDate);
}

// L2-215 Item 1 — fail-closed empty-envelope guard (#1486). A card presented as a
// prediction must carry EITHER a renderable outcome/probability OR an authoritative
// result; otherwise it renders as a bare tile (colored image + title + Like/Share,
// nothing to predict) — the concept/bundle "empty envelope" class Alex flagged
// (Tour de France 2026, Belgian GP Winner). This is the SHARED client eligibility
// boundary consumed by both the Discover and Sports feed dispatchers.
//
// It NEVER fabricates a percentage/label — it only keeps or drops. It sits ABOVE
// the leaf render (unlike `suppressBareZeroFuturesCard`, which is a per-card
// sub-1%-hero display fix) so an empty envelope contributes no card, group slot,
// or bundle member.
const _SETTLED_STATUSES = new Set([
  "resolved",
  "closed",
  "settled",
  "finalized",
  "final",
]);

function _futuresIsSettled(d: FeedFuturesData, now: number): boolean {
  const status = (d.status || "").toLowerCase();
  if (d.resolved === true || !!d.winner || _SETTLED_STATUSES.has(status)) return true;
  return !!d.resolution_date && new Date(d.resolution_date).getTime() < now;
}

/**
 * #1939 — the 24h movement chip on a concept leader, or `null` for "say nothing".
 *
 * ONE implementation, exported, because this surface has TWO concept renderers
 * (`discover/ConceptCard` and `FeedCard`'s `ConceptFeedCard`) and the whole
 * subject of this fix is a rule that drifted between surfaces. A second copy here
 * would be the same mistake at smaller scale.
 *
 * Matches native's `movementLabel` exactly, including the sub-1-point deadband:
 * a probability that moved a third of a point is noise, and "▲0" is worse than
 * silence.
 */
export function formatConceptMovement(
  movement: number | null | undefined,
): string | null {
  if (typeof movement !== "number" || !Number.isFinite(movement)) return null;
  const points = movement * 100;
  if (Math.abs(points) < 1) return null;
  const rounded = Math.round(points);
  return rounded > 0 ? `▲${rounded}` : `▼${Math.abs(rounded)}`;
}

/**
 * #1939 — is a concept `leader` something the card can actually PRINT?
 *
 * Native writes this test as `concept.leader != nil` and that is complete THERE,
 * because `FeedConceptLeader` decodes `name: String` / `probability: Double` as
 * non-optional: a malformed leader throws during decode and the field is already
 * nil by the time the predicate runs. TypeScript has no such gate — the interface
 * is erased at runtime, so a `{}` or a `{name: ""}` on the wire would satisfy a
 * bare `leader != null` and admit a card whose hero renders "undefined%".
 *
 * So the two surfaces reach the SAME rule by different amounts of code, and this
 * function is the difference. Writing it as a presence test to "match native"
 * would have matched the source and not the behaviour.
 *
 * Mirrors the backend's own guards (`_resolve_concept_leader`): a non-empty name
 * and a finite probability in [0, 1]. The range check is not defensive padding —
 * an independent-binary field can sum well past 100% (gotcha #23), so a single
 * leader reading over 1.0 is corrupt rather than merely confident.
 */
function _conceptLeaderIsUsable(
  leader: FeedConceptLeader | null | undefined,
): boolean {
  if (!leader || typeof leader !== "object") return false;
  if (typeof leader.name !== "string" || !leader.name.trim()) return false;
  const p = leader.probability;
  return typeof p === "number" && Number.isFinite(p) && p >= 0 && p <= 1;
}

/**
 * Returns a short, identity-free machine reason when a feed card should be
 * SUPPRESSED as an empty predictive envelope, or `null` when it carries renderable
 * content. Rules (fail closed — an unknown/empty card is dropped, never shown bare):
 *  - `event`: always kept — an event card shows a real matchup + status/score, never
 *    a bare tile.
 *  - `futures`: kept when it carries ≥1 outcome row OR an authoritative result
 *    (resolved / named winner / settled status / past resolution_date). A
 *    zero-outcome, unsettled futures → `"empty_futures"`.
 *  - `tournament`: kept when it carries ≥1 golfer OR a settled marquee result;
 *    otherwise → `"empty_tournament"`.
 *  - `concept`: hub cards carry NO inline outcomes by design, so a concept is kept
 *    ONLY when it leads with an authoritative result (WHAT-HIT window + a
 *    winner/result summary). A live/upcoming concept with nothing to predict →
 *    `"empty_concept"` (this is the #1486 TdF / Belgian GP class).
 *  - `bundle`: kept when ≥1 member is itself renderable; an all-empty bundle →
 *    `"empty_bundle"`.
 *  - unknown type → `"unknown_type"`.
 *  - a card whose `data` never arrived, or arrived as a non-object →
 *    `"malformed_envelope"`.
 *
 * THE DECISION THIS ENCODES IS SHARED, NOT LOCAL. Every row it must satisfy lives
 * in `contracts/feed_card_admission.json`, and the other two implementations of
 * this same rule are driven through the same rows. See that file's header before
 * changing any arm here — an arm changed on one surface only is #1939, #1935 and
 * #1951 in turn, three times in five weeks.
 */
export function feedItemSuppressionReason(
  item: FeedItem,
  now: number = Date.now(),
  depth = 0,
): string | null {
  // THE ENVELOPE, BEFORE ITS CONTENTS (#1951). Each arm below reads `item.data`
  // through an `as` cast, which is erased at runtime — so a card that arrived
  // with no `data` at all made `d.marquee_whathit` throw a TypeError. This
  // function is called inside a `.filter()` in a render memo
  // (`app/discover/page.tsx`) and inside `DiscoverCard`/`FeedCard` bodies, so
  // that throw does not drop one card, it blanks the main region — #1909's exact
  // failure mode, arriving through the predicate whose stated property is that it
  // "fails closed". A throw is not falling closed.
  //
  // Measured 2026-08-18 while folding the three copies onto one table: of the
  // five malformed-envelope shapes, web THREW on two (`data` absent, `data`
  // null), while the Python mirror suppressed all five and native — whose
  // decoder rejects the payload long before its predicate runs — suppressed all
  // five too. Web was the only surface that could take the page down, and it was
  // the only one on the page.
  //
  // Named distinctly rather than folded into `empty_*`: a card with no envelope
  // is not a card with an empty envelope, and reporting the second for the first
  // would put a lie in the suppression telemetry. If this code ever appears in
  // those counts, a payload contract broke upstream.
  if (!item || typeof item !== "object") return "unknown_type";
  const data: unknown = (item as { data?: unknown }).data;
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    return "malformed_envelope";
  }
  switch (item.type) {
    case "event":
      return null;
    case "futures": {
      const d = item.data as FeedFuturesData;
      if ((d.top_outcomes?.length ?? 0) > 0) return null;
      if (_futuresIsSettled(d, now)) return null;
      return "empty_futures";
    }
    case "tournament": {
      const d = item.data as FeedTournamentData;
      if ((d.golfers?.length ?? 0) > 0) return null;
      // #1935: the bare `marquee_whathit` arm is GONE. `TournamentCard.tsx`
      // renders its entire hero inside `{leader && (...)}` where
      // `leader = data.golfers?.[0]`, so a golferless WHAT-HIT tournament is a
      // green gradient, a "Golf" chip, a "Final" chip and a title — no champion,
      // no probability, nothing that happened. Since the arm above already
      // admits every tournament WITH golfers, this one only ever fired for the
      // case the card cannot render.
      //
      // Worth recording, because it is why this survived: native added its
      // matching arm in L2-224 as a deliberate PARITY fix ("web keeps a
      // golfer-less settled marquee; native dropped it"). It was accurate — web
      // did keep it — and parity was reached with a card that is equally empty
      // here. Agreement between two surfaces is not evidence either is right.
      return "empty_tournament";
    }
    case "concept": {
      const d = item.data as FeedConceptData;
      // #1935: WHAT-HIT admits the card only when it can NAME the result. The
      // "FINAL / see the recap" framing is not itself a result — a settled card
      // that cannot say what happened is the #1486 empty tile wearing a badge,
      // and `_resolve_concept_champion` returns nil for an ungradeable crown by
      // design, so this is reachable rather than theoretical.
      if (d.marquee_whathit === true) {
        const named = (d.winner ?? "").trim();
        const summary = (d.result_summary ?? "").trim();
        return named || summary ? null : "empty_concept";
      }
      // #1939: NOW extended to #1882's `leader`, and only because the other two
      // pieces landed in the same commit. The previous revision of this comment
      // refused the extension on the grounds that admitting the card without a
      // render branch "would produce exactly the probability-free tile the clause
      // above just closed" — that reasoning was right and is the reason the type
      // (`FeedConceptLeader`), both renderers (`ConceptCard`, `ConceptFeedCard`)
      // and this predicate move together. A classifier-only fix here would have
      // re-opened #1935 while closing #1939.
      //
      // Measured on production `5542f8c4` (identified, `limit=50`): 7 of 50 cards
      // were concepts, ALL unsettled, and ALL SEVEN carried a real leader —
      // Pogačar 0.751 (field 30), Joshua Van 0.5217, Anthony Hernandez 0.635.
      // Web was dropping 14% of the page while iOS rendered it. This is not a
      // card with nothing to predict (the #1486 class this gate exists for); it
      // is an answer the surface already had and declined to print.
      //
      // Order matches native exactly (`DiscoverViewModel.suppressionReason`):
      // the settled arm is FIRST so that "settled means settled" holds — a card
      // with a result leads with the result and never falls back to a
      // probability that is now history.
      if (_conceptLeaderIsUsable(d.leader)) return null;
      return "empty_concept";
    }
    case "bundle": {
      // Recursion backstop — bundles are not expected to nest, but a malformed
      // deep chain must never blow the stack.
      if (depth > 3) return "empty_bundle";
      const d = item.data as FeedBundleData;
      const members = d.items ?? [];
      const anyRenderable = members.some(
        (m) => feedItemSuppressionReason(m, now, depth + 1) === null,
      );
      return anyRenderable ? null : "empty_bundle";
    }
    default:
      return "unknown_type";
  }
}

/** Boolean convenience wrapper over {@link feedItemSuppressionReason}. */
export function feedItemHasRenderableContent(
  item: FeedItem,
  now: number = Date.now(),
): boolean {
  return feedItemSuppressionReason(item, now) === null;
}

/**
 * Collect the identity-free `{type, reason}` of every suppressed card in a list —
 * the input for suppression telemetry. Carries only the card type and the machine
 * reason (no ids, names, sessions, or market text).
 */
export function collectSuppressedEnvelopes(
  items: FeedItem[],
  now: number = Date.now(),
): { type: string; reason: string }[] {
  const out: { type: string; reason: string }[] = [];
  for (const item of items) {
    const reason = feedItemSuppressionReason(item, now);
    if (reason) out.push({ type: item?.type ?? "unknown", reason });
  }
  return out;
}

export function isTrending(item: FeedItem): boolean {
  if (item.type === "futures") {
    const m = (item.data as FeedFuturesData).top_outcomes?.[0]?.movement;
    return !!m && Math.abs(m) >= 0.05;
  }
  if (item.type === "event") {
    const ed = item.data as FeedEventData;
    return ed.status === "live" || (ed.ei?.score ?? 0) >= 70;
  }
  return false;
}

/** A settled game — the state whose caption must read in the past tense. */
function eventIsSettled(item: FeedItem): boolean {
  if (item?.type !== "event") return false;
  const status = (item.data as FeedEventData)?.status;
  return status === "completed" || status === "closed";
}

export function feedContextSnippet(item: FeedItem): string {
  if (item.context_summary) return item.context_summary;
  if (item.type === "futures") {
    const data = item.data as FeedFuturesData;
    return item.headline || item.reason || data.hook_description || "";
  }
  // UX-P045 — on a SETTLED event card, prefer `reason` over `headline`.
  //
  // `headline` is a BUCKET LABEL tensed for a live market; `reason` is the
  // specific sentence the backend already wrote for the settled state. Measured
  // 2026-08-10, five of fifteen finished games were captioned "Line moving" —
  // present progressive, over a game that ended 13-19 hours earlier — while the
  // wire carried "San Diego Padres odds shifted 49% during the game" in `reason`
  // and this `||` chain threw it away (`context_summary` was null on 15 of 15).
  //
  // This is a preference order, not an inference: both strings come from the
  // backend and neither is derived here (ruling 003). Unsettled cards are
  // untouched.
  if (eventIsSettled(item)) return item.reason || item.headline || "";
  return item.headline || item.reason || "";
}

export function feedExpandedContext(item: FeedItem): string {
  const snippet = feedContextSnippet(item);
  const candidates: string[] = [];

  if (item.type === "futures") {
    const data = item.data as FeedFuturesData;
    if (data.hook_description) candidates.push(data.hook_description);
  }
  if (item.reason) candidates.push(item.reason);

  // Expanded must be a superset: start with the full snippet text,
  // then append any distinct additional context that isn't already
  // contained within the snippet (near-duplicate check via word overlap).
  const snippetWords = new Set(snippet.trim().replace(/\s+/g, " ").toLowerCase().split(/\s+/));
  const extras = candidates.filter((c) => {
    const norm = c.trim().replace(/\s+/g, " ").toLowerCase();
    if (norm.length <= 10) return false;
    const candidateWords = norm.split(/\s+/);
    const overlap = candidateWords.filter((w) => snippetWords.has(w)).length;
    const ratio = overlap / Math.max(candidateWords.length, 1);
    return ratio < 0.7; // less than 70% word overlap = genuinely distinct
  });

  if (extras.length > 0) {
    return snippet + " — " + extras[0];
  }
  return snippet;
}

const CONTEXT_PREVIEW_CHARS = 145;

export function sentencePreview(text: string, maxChars = CONTEXT_PREVIEW_CHARS): string {
  const trimmed = text.trim().replace(/\s+/g, " ");
  if (trimmed.length <= maxChars) return trimmed;
  const sentenceEnd = trimmed.slice(0, maxChars + 1).search(/[.!?]\s/);
  if (sentenceEnd >= 64) return trimmed.slice(0, sentenceEnd + 1);
  const cut = trimmed.slice(0, maxChars);
  const wordBoundary = cut.lastIndexOf(" ");
  return `${cut.slice(0, wordBoundary > 80 ? wordBoundary : maxChars).trim()}...`;
}

export function getSessionId(): string {
  if (typeof window === "undefined") return "";
  let id = localStorage.getItem("bainluck_session_id");
  if (!id) {
    id = `sess_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem("bainluck_session_id", id);
  }
  return id;
}

export function generateThreshold(actualProb: number): number {
  const minGap = 0.10;
  // Randomly go higher or lower, at least 10% away
  const goHigher = Math.random() > 0.5;
  const offset = minGap + Math.random() * 0.15; // 10-25% away
  let threshold = goHigher ? actualProb + offset : actualProb - offset;
  // Clamp to 5%-95% range
  threshold = Math.max(0.05, Math.min(0.95, threshold));
  // Ensure still at least 10% away after clamping
  if (Math.abs(threshold - actualProb) < minGap) {
    threshold = actualProb > 0.5 ? actualProb - offset : actualProb + offset;
    threshold = Math.max(0.05, Math.min(0.95, threshold));
  }
  return Math.round(threshold * 100);
}
