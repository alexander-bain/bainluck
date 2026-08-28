"use client";

import React from "react";

import ShowMore, { COLLAPSED_LIST_COUNT } from "./ShowMore";
import {
  FIELD_RANK_LIMIT,
  FRESHNESS_DEFINITION,
  answerOutcome,
  curatedProps,
  curatedPropsEmptyReason,
  formatPropProbability,
  printedOutcomes,
  propFreshness,
  propIsPresentedAsLive,
  propIsResolved,
  rankedOutcomes,
  type PropMarket,
} from "@/lib/tournamentProps";

/**
 * The curated questions section (UX-P132 re-skin, Alex's item 5).
 *
 * Renders only what the register curated. There is no "show everything" path
 * and no query behind this — a market not in the register cannot appear here,
 * which is what keeps "curated, not a dump" true as the tournament grows.
 *
 * The honesty treatment is the page's, unchanged: a non-live number is muted
 * and never presented in the confident type.
 *
 * THE NAME (UX-P137, Alex's ruling 7). "Props/Futures" is gambling vocabulary
 * and the label was doing real damage: it is the only heading on a
 * probability-first page that requires a sportsbook to parse.
 *
 * `SECTION_HEADING` is a single constant because Alex picks the final wording
 * on his next pass and it should be a one-line change, not a search. The
 * alternatives, and why the rendered default won, are in the UX-P137 report.
 *
 * ALEX RULED (UX-P140): the name is **"More predictions"**. It is the last
 * section on the page, and what it holds is more of exactly what the page has
 * already been printing — predictions. Naming it by its content rather than by
 * its rhetoric means the reader never has to work out what a new noun means.
 *
 * WHAT THIS SECTION IS NOW (UX-P138, Alex's ruling 8). It used to hold eleven
 * questions, eight of which were "Does <player> reach the <round>?". Those are
 * not props — they are the playoff grid, and they render there. What is left
 * is the section's actual brief, in Alex's words: "genuinely fun items — 'Will
 * Sinner actually play?' is the archetype", rotated by
 * `lib/tournamentProps.curatedProps` so a question that resolves, goes dark, or
 * is the second copy of a template drops out rather than sitting here forever.
 *
 * ═══ UX-P139, ALEX'S ITEM 10: "THE SECTION WAS INVISIBLE" ═══
 *
 * "The questions/props section was INVISIBLE in the artifact Alex viewed —
 * find why and make the demo state obvious."
 *
 * WHY, measured. The section rendered, in all nine panels of the UX-P138
 * artifact; it rendered its EMPTY state, and the empty state was a small
 * dashed box in muted 12.5px type with no heading weight and no border colour.
 * Between two bordered white cards it reads as a divider. That is the finding:
 * not a missing section, a section that had been styled down to invisibility
 * on the assumption it would rarely be empty. It is empty every time, because
 * every card it holds is dark:
 *
 *     sinner-competes        Yes .63    last observed 2026-08-19  (~188h)
 *     sinner-second-major    2+ .555    last observed 2026-07-24  (~810h)
 *
 * Two changes, and neither of them is "show a stale number":
 *
 * 1. **The empty state now has the same visual weight as a populated one** —
 *    the same card border, the same heading treatment, and the reason in
 *    readable type rather than in a caption. A section the reader cannot see
 *    cannot tell them anything, including that something is wrong.
 * 2. **It says what WILL be here**, because during the tournament there will
 *    be real Kalshi and Polymarket props beyond round-advancement (Alex's item
 *    10). An empty section that only apologises reads as a dead feature; one
 *    that names the next thing reads as a section between deliveries.
 *
 * The eight "does X reach the Y" cards are gone from the register entirely as
 * of v7 — they are grid cells, `reaches` pins all 336, and a market in two
 * collections is a divergence waiting to happen. The runtime rotation rule
 * that used to drop them stays, as the guard it always was.
 */

/** Alex's pick, ruled UX-P140. Every surface reads it from here. */
export const SECTION_HEADING = "More predictions";

/**
 * ═══ HOW A QUIET QUESTION SHOWS ITS AGE — AN OPEN RIFF (UX-P154, item 3) ═══
 *
 * Alex, 2026-08-28: *"continuing to riff on this until we have a better
 * solution would be great"*, and: *"this is an open riff, not a settled
 * design."* So the treatment is a named variant rather than a hard-coded
 * layout, and the artifact renders all three from THIS component with the same
 * data — a drawing of an alternative proves nothing about what it would look
 * like on the page.
 *
 *   • `labelled` — the shipped default. A self-labelling chip beside the
 *     number: `Last number 32 hours ago`. Cheapest in space, and it answers
 *     the "32 hours since WHAT" question inline.
 *   • `sentence` — a full line under the number: "We have not seen a new
 *     number for this question in 32 hours." Least ambiguous, most vertical.
 *   • `dot` — a three-state dot plus a compact age (`32h`), with the meaning
 *     given once in the section header. Densest; scales to a long section
 *     where a sentence per card would drown the questions.
 *
 * The default is `labelled` because the ambiguity Alex named is a WORDING
 * problem, and the chip is the only one of the three that carries the label on
 * every card without spending a line on it. `dot` is the one to try if the
 * section grows past a handful of cards.
 */
export type FreshnessVariant = "labelled" | "sentence" | "dot";

export const DEFAULT_FRESHNESS_VARIANT: FreshnessVariant = "labelled";

function FreshnessMark({
  market,
  variant,
}: {
  market: PropMarket;
  variant: FreshnessVariant;
}) {
  const fresh = propFreshness(market);
  if (fresh.state === "fresh") return null;

  // NAME THE OLD ONES WHEN ONLY SOME ARE OLD (CERT-411 round 2). A row built
  // from a one-hour reading and a twenty-day one is muted, and the bare age
  // would read as "we have not looked at this in three weeks", which is false.
  const printedCount = printedOutcomes(market).length;
  const partial =
    fresh.staleOutcomes.length > 0 && fresh.staleOutcomes.length < printedCount
      ? `${fresh.staleOutcomes.map((o) => o.display_name).join(" + ")}: `
      : "";
  const tone = fresh.state === "quiet" ? "text-accent-warning" : "text-text-muted";

  if (variant === "sentence") {
    return (
      <p
        className={`mt-1 text-[11.5px] leading-snug ${tone}`}
        data-testid="prop-age"
        data-variant="sentence"
        data-state={fresh.state}
      >
        {partial}
        {fresh.ageHours === null
          ? "We have not seen a number for this question yet."
          : `We have not seen a new number for this question in ${fresh.age.replace(
              / ago$/,
              ""
            )}.`}
      </p>
    );
  }

  if (variant === "dot") {
    return (
      <span
        className={`ml-2 inline-flex shrink-0 items-center gap-1 text-[10.5px] tabular-nums ${tone}`}
        data-testid="prop-age"
        data-variant="dot"
        data-state={fresh.state}
        title={fresh.label}
      >
        <span
          aria-hidden="true"
          className={`h-1.5 w-1.5 rounded-full ${
            fresh.state === "quiet" ? "bg-accent-warning" : "bg-text-muted"
          }`}
        />
        <span className="sr-only">{fresh.label}. </span>
        <span aria-hidden="true">{compactAge(fresh.ageHours)}</span>
      </span>
    );
  }

  return (
    <span
      className={`shrink-0 rounded bg-surface-border/40 px-1.5 py-px text-[10.5px] font-medium ${tone}`}
      data-testid="prop-age"
      data-variant="labelled"
      data-state={fresh.state}
    >
      {partial}
      {fresh.label}
    </span>
  );
}

/** "32h" / "20d" / "—". Only the `dot` variant, which labels itself elsewhere. */
function compactAge(ageHours: number | null): string {
  if (ageHours === null || !Number.isFinite(ageHours)) return "—";
  if (ageHours < 48) return `${Math.floor(ageHours)}h`;
  return `${Math.floor(ageHours / 24)}d`;
}

function PropCard({
  market,
  variant,
}: {
  market: PropMarket;
  variant: FreshnessVariant;
}) {
  // The headline number is the CURATED answer, never the biggest number in the
  // market. See `answerOutcome` for the measured specimen this rule exists to
  // stop: a 99% printed under a question whose true answer was 1%.
  const answer = answerOutcome(market);
  const ranked = answer === null ? rankedOutcomes(market) : [];

  // LIVENESS IS THE AND OVER EVERY PRINTED OUTCOME (CERT-411 round 2).
  // This used to read `ranked[0].probability_is_live` — the leader's flag,
  // standing in for the whole card. A field card whose leader refreshed an
  // hour ago and whose runner-up is twenty days old rendered fully confident,
  // with no age on it anywhere. The rule now lives in the pure layer with the
  // board's and the slate's, so all three surfaces cannot drift apart again.
  const isLive = propIsPresentedAsLive(market);
  const fresh = propFreshness(market);
  // A CARD THAT LOOKS DECIDED SAYS SO — IT IS NOT DELETED (Alex, item 4).
  // `propIsResolved` infers settlement from the number sitting at a rail, which
  // on an illiquid market is a guess. So the card is labelled rather than
  // hidden, and the label says "looks", because that is the strength of the
  // evidence we have. Real settlement detection is lane1's.
  const looksDecided = propIsResolved(market);

  return (
    <li
      className="border-t border-surface-border px-3.5 py-3 first:border-t-0"
      data-testid="prop-market"
      data-key={market.key}
      data-live={isLive ? "true" : "false"}
      data-price-state={market.price_state}
      data-freshness={fresh.state}
      data-shape={answer ? "answer" : "field"}
      data-decided={looksDecided ? "true" : "false"}
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="min-w-0 text-[14px] font-semibold text-text-primary">
          {market.title}
        </span>
        <span className="flex shrink-0 items-baseline gap-2">
          {variant !== "sentence" && (
            <FreshnessMark market={market} variant={variant} />
          )}
          {answer && (
            <span
              className={`shrink-0 text-[17px] font-bold tabular-nums tracking-tight ${
                isLive ? "text-text-primary" : "text-text-secondary"
              }`}
              data-testid="prop-probability"
            >
              {formatPropProbability(answer.probability)}
            </span>
          )}
        </span>
      </div>

      {(answer || looksDecided) && (
        <div className="mt-px text-[11.5px] text-text-muted">
          {answer && <span data-testid="prop-answer">{answer.display_name}</span>}
          {looksDecided && (
            <span data-testid="prop-decided">
              {answer ? " · " : ""}Looks decided
            </span>
          )}
        </div>
      )}
      {variant === "sentence" && <FreshnessMark market={market} variant={variant} />}

      {/* A field market ranks instead. There is deliberately no headline
          number here: "who will win a slam" has no single answer, and picking
          the leader to fill the slot is exactly the guess this card refuses. */}
      {answer === null && ranked.length > 0 && (
        <ol className="mt-1.5 space-y-0.5" data-testid="prop-field">
          {ranked.slice(0, FIELD_RANK_LIMIT).map((outcome) => (
            <li
              key={outcome.entity_key}
              className="flex items-baseline justify-between gap-3 text-[12px]"
              data-testid="prop-field-row"
            >
              <span className="min-w-0 truncate text-text-secondary">
                {outcome.display_name}
              </span>
              <span
                className={`shrink-0 tabular-nums ${
                  outcome.probability_is_live ? "text-text-primary" : "text-text-secondary"
                }`}
              >
                {formatPropProbability(outcome.probability)}
              </span>
            </li>
          ))}
        </ol>
      )}

      {market.hook && (
        <p className="mt-1 text-[11.5px] leading-snug text-text-secondary" data-testid="prop-hook">
          {market.hook}
        </p>
      )}
    </li>
  );
}

/**
 * WHERE THE ROUND QUESTIONS WENT — and why this sentence is unconditional.
 *
 * UX-P138 printed it only when `curated.dropped.advance > 0`, i.e. only when a
 * reach question was in the payload and got rotated out at render. UX-P139
 * removed those eight from the register itself (`props_declined`), which is the
 * more correct fix — one market in two collections is a divergence waiting to
 * happen — and the side effect was that the pointer disappeared with them.
 *
 * That made the sentence a fact about our BUILD PIPELINE rather than about the
 * page: it appeared when the rotation happened to fire and vanished once the
 * same decision was made one layer earlier, even though what it tells the
 * reader ("reach-a-round questions live on the Bracket tab") became MORE true,
 * not less. On a page whose ship is "a hub that orients at a glance", an
 * orientation line that blinks out when the underlying structure hardens is
 * backwards. So it is structural now, and the count rides it only while a
 * rotation is genuinely what happened.
 */
function MovedToGrid({ dropped }: { dropped: number }) {
  return (
    <p
      className="mt-2 text-[11px] text-text-muted"
      data-testid="props-moved-to-grid"
      data-dropped={dropped}
    >
      {dropped > 0
        ? `${dropped} question${dropped === 1 ? " about reaching a round is" : "s about reaching a round are"} on the Bracket tab.`
        : "Questions about reaching a round — the quarters, the semis, the final — are on the Bracket tab."}
    </p>
  );
}

export default function TournamentProps({
  markets,
  draw,
  variant = DEFAULT_FRESHNESS_VARIANT,
}: {
  markets: PropMarket[];
  draw: string;
  /**
   * The illiquidity treatment (UX-P154, item 3). Alex asked for variants to
   * look at and said the design is *"an open riff, not a settled design"*, so
   * this is a real seam rather than a test hook: the artifact renders all three
   * from this component, and production takes the default. See
   * `FreshnessVariant`.
   */
  variant?: FreshnessVariant;
}) {
  // Advance-to-round questions move to the grid; template families combine into
  // one card; most interesting first. NOTHING is hidden for age or for looking
  // decided — Alex's item 4, 2026-08-28.
  const curated = curatedProps(markets, draw);
  const visible = curated.markets;
  const [expanded, setExpanded] = React.useState(false);

  if (visible.length === 0) {
    // An empty section still appears, and says WHY, with a number. A section
    // that vanishes teaches the reader it does not exist; one that says
    // "nothing curated yet" over a register holding eleven markets is simply
    // wrong, and it is the only channel by which a curation gap reaches anyone
    // who can close it.
    const reason = curatedPropsEmptyReason(curated);
    return (
      <section data-testid="tournament-props" data-considered={curated.considered}>
        <h2
          className="mb-2 mt-6 text-xs font-bold uppercase tracking-[0.07em] text-text-muted"
          data-testid="props-heading"
        >
          {SECTION_HEADING}
        </h2>
        {/* ITEM 10. Same border, same background, same padding as a populated
            card. The old dashed 12.5px whisper between two solid cards read as
            a divider, which is how a section that renders in every panel can
            still be invisible. */}
        <div
          className="overflow-hidden rounded-2xl border border-surface-border bg-surface-card px-3.5 py-3.5"
          data-testid="props-empty"
          /* Kept at its old name and always "0" (UX-P154). The attribute was a
             contract this page's guards read; deleting it would make the guards
             pass by having nothing to check, where holding it at zero makes
             "no question is hidden for age" an assertable fact. */
          data-dropped-dark={curated.dropped.dark}
          data-dropped-advance={curated.dropped.advance}
        >
          <div className="text-[14px] font-semibold text-text-primary">
            {reason === null ? "Nothing to ask yet" : "Nothing worth asking right now"}
          </div>
          <p
            className="mt-1 max-w-[62ch] text-[12.5px] leading-snug text-text-secondary"
            data-testid="props-empty-reason"
          >
            {/* Ruling 142: the fallback ended "New questions are coming — check
                back soon." A section that cannot name a date should not name a
                time at all; what it owes the reader is the present fact. */}
            {reason ??
              "Beyond the title race and today’s matches, we only show questions worth asking. This draw has none with a probability against them."}
          </p>
          {/* WHAT THIS SECTION IS. Ruling 142 (Alex, 2026-08-28): a section
              states what it IS, not what it WILL be — "we should make it the
              thing it's supposed to be", not describe the thing it might
              become. The old line promised a future ("Once the main draw
              starts… show up here as soon as they have a number") and named
              two venues while doing it, which ruling 141 bans outright.
              Present tense, our number, no date we do not control. */}
          <p className="mt-2 max-w-[62ch] border-t border-surface-border pt-2 text-[11.5px] leading-snug text-text-muted">
            This section holds the questions about this draw worth asking beyond who
            reaches which round — <i>Will Sinner actually play?</i> is the shape of one.
            None have a probability against them today.
          </p>
        </div>
        <MovedToGrid dropped={curated.dropped.advance} />
      </section>
    );
  }

  const shown = expanded ? visible : visible.slice(0, COLLAPSED_LIST_COUNT);
  // WHETHER ANY CARD OWES THE READER AN AGE. The definition line is printed
  // once per section and only when something on screen needs it — a definition
  // standing over a section of live numbers is a footnote about nothing.
  const anyQuiet = shown.some((market) => propFreshness(market).state !== "fresh");

  return (
    <section data-testid="tournament-props" data-considered={curated.considered}>
      <h2
        className="mb-2 mt-6 text-xs font-bold uppercase tracking-[0.07em] text-text-muted"
        data-testid="props-heading"
      >
        {SECTION_HEADING}
        <span className="ml-1.5 font-normal normal-case tracking-normal">
          · {visible.length}
        </span>
      </h2>
      <div className="overflow-hidden rounded-2xl border border-surface-border bg-surface-card">
        <ul>
          {shown.map((market) => (
            <PropCard key={market.key} market={market} variant={variant} />
          ))}
        </ul>
        {visible.length > COLLAPSED_LIST_COUNT && (
          <ShowMore
            expanded={expanded}
            total={visible.length}
            onToggle={() => setExpanded((value) => !value)}
          />
        )}
      </div>

      {/* WHAT THE AGE MEANS, ONCE (UX-P154, Alex's item 3).

          "32 hours ago" is ambiguous — created? updated? last traded? — and
          the answer is none of those: it is when a probability for that
          question last reached us. That is a definition, so it belongs once
          under the section and not on every card, where it would be four
          repetitions of a footnote. The cards carry the STATUS; this carries
          the UNIT. */}
      {anyQuiet && (
        <p
          className="mt-2 max-w-[62ch] text-[11px] leading-snug text-text-muted"
          data-testid="props-freshness-definition"
        >
          {FRESHNESS_DEFINITION}
        </p>
      )}

      {/* A COMBINED CARD SAYS IT IS ONE (UX-P154, Alex's item 1). Not an
          apology — the opposite. Two questions became one card and every
          subject is on it, which is a thing worth being told rather than a
          shrinkage to explain away. `props-rotated-out` was the old testid for
          the sentence that counted HIDDEN cards; nothing is hidden now, so the
          name went with the behaviour. */}
      {curated.combined > 0 && (
        <p
          className="mt-2 max-w-[62ch] text-[11px] text-text-muted"
          data-testid="props-combined"
          data-combined={curated.combined}
        >
          {curated.combined + 1} of the questions above ask the same thing, so they share
          one card.
        </p>
      )}
      <MovedToGrid dropped={curated.dropped.advance} />
    </section>
  );
}
