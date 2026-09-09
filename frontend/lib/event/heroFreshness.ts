/**
 * live/122 (#4469) — THE LIVE HERO HAS ONE AGE, AND IT IS THE OLDEST FACT IN IT.
 *
 * ═══ WHAT ALEX'S WIFE SAW ═══
 *
 * Lisa used the site during Shelton–Alcaraz and said "the score was
 * significantly lagging the probability" (Fable-5, 2026-09-09 10:05am PT). It
 * reproduces. Measured on Andreeva v Gauff the same afternoon, 19 polls of
 * production 15s apart:
 *
 *     score stamp age (`linescore.observed_at`)   median 482.9s   max 629.2s
 *     price stamp age (freshest source write)     median   8.4s   max  36.7s
 *
 * The hero probability moved >=2% four times in that window (0.641 -> 0.610 ->
 * 0.646 -> 0.682) and the score never moved once. The score is on a ten-minute
 * background crontab (`sync-tennis-from-espn`) and the number beside it is on a
 * two-minute realtime one.
 *
 * ═══ WHY THAT IS A FRONTEND BUG AND NOT ONLY A CADENCE ONE ═══
 *
 * The cadence is the real fix and it belongs to lane1 (D39, the tennis sync
 * path); it is handed over on #4469. This file is the other arm of Fable's
 * rule — *either the score cadence matches the price cadence, or the number is
 * held/labelled until the score catches up*.
 *
 * The badge was labelled, and it was labelled wrong. `freshestSourceStamp` is
 * the MAX of `win_probability_sources[*].updated_at` — prices only. So the page
 * printed a green `live · 6s ago` over a score eight minutes old. `espn_sync.py`
 * had already written that finding into a comment on 2026-09-05 ("the
 * `LIVE · 1s ago` badge beside it is the win-prob write's age, a different
 * number entirely") and it was still live on the 9th.
 *
 * ═══ MAX FOR A BLEND, MIN FOR A HERO ═══
 *
 * These two rules look contradictory and are not, which is the whole reason
 * this is a named function instead of an inline `Math.min`.
 *
 * `freshestSourceStamp` takes the MAX across sources and is right to: the hero
 * probability IS a blend, one number, and its age is the age of the most recent
 * thing that went into it. Reading the oldest source there would make the
 * number look stale whenever a quiet feed happened not to tick.
 *
 * The HERO is not a blend. It is a set of separate facts a reader takes in at
 * one glance — a probability, a set score, a games line — and a glance is only
 * as current as the oldest thing in it. So: max WITHIN the number, min ACROSS
 * the facts.
 *
 * ═══ THE LABEL NAMES WHICH FACT IS OLD (CERT-411 round 2) ═══
 *
 * `FreshnessDot`'s header records the near-miss this rule comes from: a two-leg
 * row whose other half refreshed an hour ago would have claimed the WHOLE row
 * was 35 days stale. An age with no subject is not an admission, it is a new
 * confusion. So this returns `fact` alongside the stamp, and the caller spends
 * it on the tooltip and the screen-reader label — never on page-body prose,
 * which standing notice 34 forbids and D102 confirms is the actual complaint.
 */

/** Which visible fact the reported age belongs to. */
export type HeroFact = "price" | "score";

export interface HeroFreshness {
  /** ISO stamp of the oldest visible fact, or null when nothing is stamped. */
  stamp: string | null;
  /** Which fact `stamp` came from. `null` exactly when `stamp` is null. */
  fact: HeroFact | null;
}

function parsed(value: string | null | undefined): number | null {
  if (typeof value !== "string") return null;
  const t = Date.parse(value);
  return Number.isNaN(t) ? null : t;
}

/**
 * The age the live hero should report.
 *
 * `scoreStamp` is passed ONLY when the score is actually on the page. An
 * unrendered fact cannot mislead a reader, so it must not age the badge — this
 * is why the caller gates on the same condition that renders the games line
 * rather than on `linescore` merely existing. A finished match has no
 * `observed_at` at all (the line is final and has no freshness to report), so
 * settled heroes are untouched by construction.
 *
 * Ties go to `price`: when both stamps land on the same millisecond there is no
 * lag to describe, and the default label is the one that says least.
 */
export function heroFreshness({
  priceStamp,
  scoreStamp,
}: {
  priceStamp?: string | null;
  scoreStamp?: string | null;
}): HeroFreshness {
  const p = parsed(priceStamp);
  const s = parsed(scoreStamp);

  if (p === null && s === null) return { stamp: null, fact: null };
  if (s === null) return { stamp: priceStamp as string, fact: "price" };
  if (p === null) return { stamp: scoreStamp as string, fact: "score" };

  return s < p
    ? { stamp: scoreStamp as string, fact: "score" }
    : { stamp: priceStamp as string, fact: "price" };
}

/**
 * The complete admission, for a tooltip and a screen reader — never the body.
 *
 * `live` is the caller's own state, not re-derived here: the badge already
 * decides when it stops reading as current, and two functions deciding that
 * separately is how a dot and its own caption end up disagreeing
 * (`freshnessLabel`'s header states the same rule for the games-line chip).
 */
export function heroFreshnessLabel(fact: HeroFact | null, age: string): string {
  if (fact === "score") return `Score last confirmed ${age}. The probability is newer.`;
  return `Probability updated ${age}.`;
}
