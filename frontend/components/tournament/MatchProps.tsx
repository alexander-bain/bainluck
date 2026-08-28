"use client";

import React from "react";

import {
  PROPS_HEADING,
  PROPS_HEADING_DECIDED,
  answerPercents,
  formatAnswerPercent,
  hiddenPropCount,
  propFreshnessLabel,
  propIsPresentedAsLive,
  propsProvenance,
  visibleProps,
  type MatchDetailPayload,
  type MatchProp,
} from "@/lib/matchDetail";

/**
 * THE QUESTIONS UNDER THE MATCH (UX-P149) — the ship lane1's Q426 note routed
 * here and could not build, because there was no per-match surface to put them
 * on.
 *
 * ═══ WHAT A CARD IS, AND WHY IT IS NOT A ROW ═══
 *
 * Every card is ONE question with its answers listed under it. Not a title and
 * a headline number: half these markets have no single answer worth
 * headlining ("Who wins set 1" has two, "Total games" has three), and picking
 * one to fill a big-number slot is the guess `TournamentProps` already refuses
 * on the hub's field markets.
 *
 * ═══ THE THREE THINGS THIS COMPONENT REFUSES ═══
 *
 * 1. **`Yes` / `No` / `Over` / `Under`.** The words the source stores are not
 *    words a reader can act on. Every label here is a sentence the server
 *    built — a player's name, or "More than 22 games" — and where the server
 *    could not attribute a side to a player it sent no card at all rather than
 *    a `Yes`. See `attribute_yes_side`.
 *
 * 2. **A ladder printed as three cards.** `Match O/U 21.5`, `22.5` and `23.5`
 *    are one question at three heights; three cards is the ladder/bucket shape
 *    the Discover audit holds at zero, and it is unreadable besides. The
 *    server collapses them into one card whose three rungs ARE the curve.
 *
 * 3. **A live-looking number on a finished match.** A prop market does not
 *    reliably settle, so a decided match reads `opening_probability` and the
 *    section renames itself. See rule 1 in `lib/matchDetail.ts`.
 *
 * ═══ DESKTOP ═══
 *
 * Two columns at `lg`, one below it, `columns` rather than a grid so the cards
 * pack by height instead of leaving a ragged row — these are eight cards of
 * two to three rows each and a grid would give every one of them the height of
 * the tallest. `break-inside-avoid` is what keeps a card whole across the
 * column break.
 */

function AnswerRow({
  label,
  percent,
  live,
  entity,
}: {
  label: string;
  percent: number | null;
  live: boolean;
  entity: string | null;
}) {
  return (
    <li
      className="flex items-baseline justify-between gap-3 py-[3px]"
      data-testid="match-prop-answer"
      data-entity={entity ?? undefined}
    >
      <span className="min-w-0 truncate text-[13px] text-text-secondary">{label}</span>
      <span
        className={`shrink-0 text-[15px] font-semibold tabular-nums tracking-tight ${
          live ? "text-text-primary" : "text-text-secondary"
        }`}
        data-testid="match-prop-probability"
      >
        {formatAnswerPercent(percent)}
      </span>
    </li>
  );
}

function PropCard({ prop, decided }: { prop: MatchProp; decided: boolean }) {
  const percents = answerPercents(prop, decided);
  const live = propIsPresentedAsLive(prop, decided);
  const freshness = propFreshnessLabel(prop, decided);

  return (
    <li
      className="mb-3 break-inside-avoid rounded-2xl border border-surface-border bg-surface-card px-3.5 py-3"
      data-testid="match-prop"
      data-key={prop.key}
      data-kind={prop.kind}
      data-family={prop.family}
      data-live={live ? "true" : "false"}
      data-price-state={prop.price_state}
    >
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="min-w-0 text-[10px] font-bold uppercase tracking-[0.07em] text-text-muted">
          {prop.question}
        </h3>
        {/* THE STATED REASON. A muted card that does not say why it is muted
            is read as a bug, or not read at all (CERT-411 round 2). */}
        {freshness !== null && (
          <span
            className="shrink-0 text-[10.5px] text-accent-warning"
            data-testid="match-prop-age"
          >
            {freshness}
          </span>
        )}
      </div>

      <ul className="mt-1">
        {prop.answers.map((answer, index) => (
          <AnswerRow
            key={`${prop.key}:${answer.label}`}
            label={answer.label}
            percent={percents[index]}
            live={live && answer.probability_is_live}
            entity={answer.entity_key}
          />
        ))}
      </ul>

      {prop.note && (
        <p className="mt-1 text-[11px] leading-snug text-text-muted" data-testid="match-prop-note">
          {prop.note}
        </p>
      )}
    </li>
  );
}

export default function MatchProps({ payload }: { payload: MatchDetailPayload }) {
  const cards = visibleProps(payload);
  const hidden = hiddenPropCount(payload);
  const decided = payload.decided === true;
  const heading = decided ? PROPS_HEADING_DECIDED : PROPS_HEADING;

  if (cards.length === 0) {
    // An empty section still appears, with the same weight as a populated one,
    // and says WHY (UX-P139, Alex's item 10 — a section styled down to a
    // whisper reads as a divider and can tell the reader nothing, including
    // that something is wrong).
    return (
      <section className="mt-6" data-testid="match-props" data-count={0}>
        <h2 className="mb-2 text-xs font-bold uppercase tracking-[0.07em] text-text-muted">
          {heading}
        </h2>
        <div
          className="rounded-2xl border border-surface-border bg-surface-card px-3.5 py-3.5"
          data-testid="match-props-empty"
          data-hidden={hidden}
        >
          <div className="text-[14px] font-semibold text-text-primary">
            Nothing else on this match yet
          </div>
          <p className="mt-1 max-w-[62ch] text-[12.5px] leading-snug text-text-secondary">
            {decided
              ? "We hold no numbers from before this match beyond the winner."
              : "The only market on this match is the winner. Questions about sets, games and margins appear here as soon as anyone opens one."}
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="mt-6" data-testid="match-props" data-count={cards.length}>
      <h2
        className="mb-1 text-xs font-bold uppercase tracking-[0.07em] text-text-muted"
        data-testid="match-props-heading"
      >
        {heading}
        <span className="ml-1.5 font-normal normal-case tracking-normal">
          · {cards.length}
        </span>
      </h2>
      {/* WHERE THESE CAME FROM. A reader who has just read a match probability
          needs to know the numbers below are the same market answering other
          questions about the same match — not a second source, not a model,
          and not our opinion. `max-w-[74ch]` because prose does not follow the
          window (UX-P145). */}
      <p
        className="mb-2.5 max-w-[74ch] text-[11.5px] leading-snug text-text-muted"
        data-testid="match-props-provenance"
      >
        {propsProvenance(payload)}
      </p>

      <ul className="lg:columns-2 lg:gap-x-4" data-testid="match-props-list">
        {cards.map((prop) => (
          <PropCard key={prop.key} prop={prop} decided={decided} />
        ))}
      </ul>

      {/* NO SILENT SHRINKING. A card with no number on any answer is dropped,
          and the drop is counted — a section that quietly went from eight
          questions to three reads as "not much is happening" when the truth
          may be that five stopped updating. */}
      {hidden > 0 && (
        <p className="text-[11px] text-text-muted" data-testid="match-props-hidden">
          {hidden} more question{hidden === 1 ? "" : "s"} exist{hidden === 1 ? "s" : ""} on
          this match with no number against {hidden === 1 ? "it" : "them"} yet.
        </p>
      )}
    </section>
  );
}
