"use client";

/**
 * THE TOURNAMENT'S SECTIONS **OF** AN EVENT PAGE (UX-P152).
 *
 * ═══ WHAT THIS REPLACED ═══
 *
 * Alex, 2026-08-28, on the UX-P149 artifact: *"It seems like we're reinventing
 * the event page here"*, followed by the architecture note: *"I thought that
 * tournaments were containers for related events."*
 *
 * UX-P149 built `/tournaments/us-open/matches/{key}` — a whole parallel match
 * surface with its own hero, its own layout and no probability-over-time graph
 * at all — on the premise that a tennis match has no `events` row.  That
 * premise expired the evening before it shipped: the Odds API began carrying US
 * Open main-draw singles on 2026-08-27, and 94 standard events now exist for
 * the 96 registered R128 fixtures.
 *
 * So there is no match page.  A match card routes to `/events/{id}` exactly as
 * any other game card does, that page renders the graph and the hero and
 * everything else it renders for an NBA game, and the tournament adds these two
 * sections **below** it:
 *
 *   1. **Advancement** — each player's chance of reaching each later round,
 *      through `AdvancementPath`, which is the same component the MLB/NBA event
 *      page's `CHAMPIONSHIP PATH` block goes through.  Alex asked for the same
 *      component family; this is the component, not a family resemblance.
 *   2. **The match's other questions** — through `MatchProps`, kept whole from
 *      UX-P149.  That component was the good half of that queue and none of it
 *      is rewritten here; only its container changed.
 *
 * ═══ WHY IT CAN RENDER NOTHING, OFTEN ═══
 *
 * A reach board is quoted for the top of a draw.  Measured 2026-08-28 against
 * the live register: of 96 R128 fixtures, **14** have both players carrying
 * reach cells, **56** have one, and **26** have neither.  An unseeded
 * first-rounder is simply not quoted to reach the quarter-finals.
 *
 * The section therefore suppresses itself rather than rendering a titled empty
 * box, and a one-sided fixture renders the one side it has.  Both are honest
 * outputs of "the market has not been asked"; a placeholder column would be a
 * promise of something that is not there.
 */

import Link from "next/link";
import useSWR from "swr";

import MatchProps from "@/components/tournament/MatchProps";
import AdvancementPath, {
  type AdvancementStage,
} from "@/components/event/AdvancementPath";
import SectionErrorBoundary from "@/components/SectionErrorBoundary";
import { broadcastFor } from "@/lib/slate";
import { fetchEventTournament } from "@/lib/api";
import type {
  EventTournamentResponse,
  TournamentAdvancementRow,
} from "@/lib/types";

/** The advancement block's own name. One constant, so a re-wording is one line. */
export const ADVANCEMENT_HEADING = "CHANCE OF REACHING";

/**
 * A register reach row -> the stages `AdvancementPath` prints.
 *
 * `resolved` is deliberately NOT derived from a probability threshold here.
 * The league path calls a stage clinched at >= 0.995 because a season's
 * playoff market really does settle to 1.0 once the maths is done. A draw's
 * reach market does not reliably settle (UX-P149 measured a match-winner
 * market at 0.05% while a prop on the same match still read its pre-match
 * number hours later), so a 99.6% here would print `✓ clinched` about a round
 * that has not been played. It stays a probability until something authoritative
 * says otherwise.
 */
export function toStages(row: TournamentAdvancementRow | null): AdvancementStage[] {
  if (!row) return [];
  return row.stages
    .filter((s) => s.probability !== null && s.probability !== undefined)
    .map((s) => ({
      label: s.label,
      prob: s.probability as number,
      // The register pins a reading, not a history. `null` is the component's
      // own "no move to show"; a 0 would print "no change" about a number
      // nobody measured twice.
      change: s.trend_24h ?? null,
      resolved: false,
    }));
}

/**
 * WHERE TO WATCH — ALEX'S RULING 7, AT ITS NEW ADDRESS (UX-P154).
 *
 * Ruling 7: *"where-to-watch moves to the DETAIL view"* — off every row of a
 * long list, where a single line at the top is wrong and a line per row is
 * noise. UX-P138 implemented the detail view as an accordion inside the match
 * row.
 *
 * Alex's item 2, 2026-08-28: the whole match card is clickable, no link row. So
 * the accordion is gone and the detail view is THIS page — the one the tap
 * arrives at. The ruling did not change; its venue did. The match list carries
 * no broadcast at all now, and `tournamentMatches.test.tsx` holds that negative
 * in both the region-wide and the per-match case.
 *
 * Exported so a guard can render it directly: the parent is a SWR client
 * component that returns `null` server-side with no data, so a test that mounted
 * only the parent would prove the line renders by never rendering it.
 */
export function WhereToWatch({
  broadcasts,
}: {
  broadcasts?: EventTournamentResponse["broadcasts"];
}) {
  const watch = broadcastFor(broadcasts);
  if (!watch || watch.channels.length === 0) return null;
  return (
    <p
      className="-mt-2 mb-4 text-[12px] text-text-secondary"
      data-testid="tournament-where-to-watch"
      data-region={watch.region}
    >
      <span className="font-semibold text-text-primary">Where to watch</span>{" "}
      {watch.channels.join(", ")}
      <span className="text-text-muted"> ({watch.region})</span>
    </p>
  );
}

function PlayerCard({
  row,
  testId,
}: {
  row: TournamentAdvancementRow | null;
  testId: string;
}) {
  const stages = toStages(row);
  // An empty column, not a titled empty box: the sibling keeps its half of the
  // grid so the one player who IS quoted does not stretch across the row and
  // read as the only entrant.
  if (!row || stages.length === 0) return <div data-testid={`${testId}-empty`} />;

  return (
    <div
      className="bg-surface-card border border-surface-border rounded-xl shadow-sm p-5"
      data-testid={testId}
      data-player={row.name}
    >
      <div className="flex items-center gap-3 mb-4">
        {row.logo_url ? (
          <img
            src={row.logo_url}
            alt=""
            className="w-11 h-11 rounded-full object-cover shrink-0"
          />
        ) : (
          <div className="w-11 h-11 rounded-full grid place-items-center font-mono font-bold text-white shrink-0 bg-text-muted">
            {row.short_name.slice(0, 3).toUpperCase()}
          </div>
        )}
        <div>
          <div className="font-semibold text-lg leading-tight">{row.short_name}</div>
          {row.record && (
            <div className="text-xs text-text-muted font-mono tabular-nums">
              {row.record}
            </div>
          )}
        </div>
      </div>
      <AdvancementPath
        stages={stages}
        heading={ADVANCEMENT_HEADING}
        testId={`${testId}-path`}
      />
      {/* A LADDER THAT DOES NOT CLIMB SAYS SO (UX-P152).
          The market sometimes prices "reach the final" above "reach the
          semis" — 21 of 84 ladder players on 2026-08-26, all in the sub-5%
          tail. The grid's standing ruling is report, not correct, because
          fixing it would be the page lying on the market's behalf. On the
          grid that inversion is two cells in an 84-row table and reads as
          noise; here it is two of five large rows on one card, and silence
          would read as our arithmetic rather than theirs. */}
      {row.monotonic === false && (
        <p
          className="-mt-3 text-[11px] leading-snug text-text-muted"
          data-testid={`${testId}-incoherent`}
        >
          These came from separate questions and they disagree — one later round
          is priced above an earlier one, which cannot both be true. Shown as
          the market has them.
        </p>
      )}
    </div>
  );
}

export default function TournamentExtensions({
  eventId,
  sportKey,
}: {
  eventId: number;
  /**
   * Gated on the client as well as the server. The endpoint answers "no" for a
   * non-tournament event in one indexed read, but the cheapest request is the
   * one never sent, and an event page must not grow a round trip for a feature
   * that applies to 94 events on the whole site.
   */
  sportKey?: string | null;
}) {
  const eligible = !!sportKey && TOURNAMENT_SPORT_KEY.test(sportKey);
  const { data } = useSWR<EventTournamentResponse>(
    eligible ? ["event-tournament", eventId] : null,
    () => fetchEventTournament(eventId),
    { revalidateOnFocus: false, refreshInterval: 120000 },
  );

  if (!data?.tournament) return null;

  const advancement = data.advancement;
  const hasAdvancement = !!(
    advancement &&
    (toStages(advancement.home_team).length > 0 ||
      toStages(advancement.away_team).length > 0)
  );
  const hasProps = (data.props?.length ?? 0) > 0;
  // Where to watch keeps the section alive on its own (UX-P154): a match whose
  // reach board is unquoted and whose props have not listed still has a
  // channel, and that is the most useful thing on the page an hour before play.
  const watch = broadcastFor(data.broadcasts);
  const hasWatch = !!watch && watch.channels.length > 0;
  if (!hasAdvancement && !hasProps && !hasWatch) return null;

  return (
    <section className="mt-6" data-testid="tournament-extensions">
      <div className="flex items-end justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold tracking-tight">
            {data.tournament.title}
          </h3>
          {data.draw_label && (
            <p className="text-sm text-text-secondary mt-0.5">
              {data.draw_label}
              {data.round ? ` · ${data.round}` : ""}
            </p>
          )}
        </div>
        <Link
          href={data.tournament.url}
          className="text-[11px] font-semibold text-text-secondary hover:text-text-primary underline decoration-dotted underline-offset-2"
          data-testid="tournament-hub-link"
        >
          The whole draw →
        </Link>
      </div>

      <WhereToWatch broadcasts={data.broadcasts} />

      {hasAdvancement && advancement && (
        <SectionErrorBoundary label="Advancement" resetKey={eventId}>
          <div
            className="grid grid-cols-1 md:grid-cols-2 gap-4"
            data-testid="tournament-advancement"
          >
            <PlayerCard row={advancement.home_team} testId="advancement-home" />
            <PlayerCard row={advancement.away_team} testId="advancement-away" />
          </div>
        </SectionErrorBoundary>
      )}

      {hasProps && (
        <SectionErrorBoundary label="Match questions" resetKey={eventId}>
          <MatchProps payload={data} />
        </SectionErrorBoundary>
      )}
    </section>
  );
}

/**
 * Which sport keys can possibly be in a tournament container.
 *
 * A prefix test and not the server's exact list: the client must not carry a
 * second copy of `REGISTERED_TOURNAMENTS` that goes stale the day a second
 * tournament is registered. Over-asking is one cheap `null` answer; under-asking
 * is a section that silently stops appearing.
 */
const TOURNAMENT_SPORT_KEY = /^tennis_(atp|wta)_/;
