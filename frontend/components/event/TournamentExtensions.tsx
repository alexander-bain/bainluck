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

import React from "react";
import Link from "next/link";
import useSWR from "swr";

import MatchProps from "@/components/tournament/MatchProps";
import PlayerAvatar from "@/components/tournament/PlayerAvatar";
import AdvancementPath, {
  type AdvancementStage,
} from "@/components/event/AdvancementPath";
import SectionErrorBoundary from "@/components/SectionErrorBoundary";
import { broadcastFor, type PlayerImage } from "@/lib/slate";
import { fetchEventTournament } from "@/lib/api";
import { eventTournamentKey, isTournamentSportKey } from "@/lib/eventOutcome";
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
  const eligible = isTournamentSportKey(sportKey);
  const { data } = useSWR<EventTournamentResponse>(
    eligible ? eventTournamentKey(eventId) : null,
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
 * The eligibility test and the SWR key both moved to `lib/eventOutcome.ts`
 * (#2443), where the hero can share them.
 *
 * They are shared rather than copied for a reason this file already implies:
 * the request this section makes is now also the request the hero's winner
 * name comes from, and two regexes that agree today are two chances to fire
 * one and not the other — which reads as a hero saying "Final" above a section
 * that knows the score.
 */
/**
 * ═══ THE WAY BACK UP (#2448, Alex's third item) ═══
 *
 * *"no link back to the tournament (only `Back to events`)"*.
 *
 * A tournament is a container for related events (Alex's own architecture note,
 * quoted at the top of this file), and a container you can only descend into is
 * a one-way door. The tournament page routes a match card to `/events/{id}`;
 * the event page routed back to `/`, which is Discover — not the tournament,
 * not even the sport.
 *
 * ### Why this lives here rather than in the page
 *
 * The link needs the tournament's slug and title, and this module is already
 * the one thing on the event page that knows them. It shares the SWR key
 * `["event-tournament", eventId]` with `TournamentExtensions` verbatim, so the
 * two components are ONE request — SWR dedupes on the key, and a second key
 * spelled differently would be a silent doubling of the round trip that the
 * eligibility gate above exists to avoid.
 *
 * Renders NOTHING for the ~94-events-in-the-whole-site case where the event is
 * not in a register, and nothing while the request is in flight. A back link
 * that appears a beat late is better than a placeholder that reserves space for
 * a link most events will never have.
 */
/**
 * ═══ ONE RESOLVER, BOTH SURFACES (#2447) ═══
 *
 * Alex: *"`/events/15293846` renders `MB` and `SW` avatar initials for
 * Berrettini and Wawrinka. The tournament page renders photographs for the same
 * two players. One resolver should serve both."*
 *
 * The event hero's face ladder is `home_team_data.logo_large` →
 * `espnTeamLogoByName(name, sport_key)` → initials. Both of the first two are
 * TEAM resolvers. A tennis player is not a team, has no `teams` row and no ESPN
 * team logo, so the ladder falls straight through to step three on every match
 * at this tournament — while the register, four sections down the same page,
 * holds a verified photograph of the same person.
 *
 * The register's resolver is `player_image`, censused offline by
 * `backend/scripts/census_player_images.py` against the article's own
 * description, precisely because a bare-name lookup returns a Serbian
 * footballer for `Aleksandar Kovacevic` and a US President for `Andrew
 * Johnson`. That verification is the whole value of the pin, and it is why this
 * reads the register rather than adding a fourth guess to the ladder.
 *
 * ### Matched BY NAME, in both branches, deliberately
 *
 * The payload's `result.players` carry no home/away semantics, and
 * `advancement.home_team` carries them but is built by a different path. A
 * positional read would swap two faces the day either ordering changes, and a
 * wrong face is the exact failure the census exists to prevent — instant,
 * confident, and unverifiable by the reader. So both branches match the event's
 * own `home_team` / `away_team` strings and return `null` when they do not,
 * which drops that side back to initials rather than to somebody else.
 *
 * ### Two branches because one is not enough
 *
 * `result` covers finished matches and carries the full `{url, flag_url}`
 * block. `advancement` covers quoted players and carries a photo only. Measured
 * on the live `/api/tournaments/by-event/15293846`: `advancement.away_team` is
 * `null` — Wawrinka is not on the reach board — while `result.players` has both
 * faces. Either branch alone leaves half of that match on initials.
 */
export function useTournamentPlayerFaces(
  eventId: number,
  sportKey: string | null | undefined,
  homeName: string,
  awayName: string
): { home: PlayerImage | null; away: PlayerImage | null } {
  const eligible = isTournamentSportKey(sportKey);
  const { data } = useSWR<EventTournamentResponse>(
    eligible ? eventTournamentKey(eventId) : null,
    () => fetchEventTournament(eventId),
    { revalidateOnFocus: false, refreshInterval: 120000 },
  );

  return {
    home: registerFace(data, homeName),
    away: registerFace(data, awayName),
  };
}

const sameName = (a: string | null | undefined, b: string | null | undefined) =>
  !!a && !!b && a.trim().toLowerCase() === b.trim().toLowerCase();

/** The register's pinned image for one named player, or `null`. Never a guess. */
export function registerFace(
  data: EventTournamentResponse | undefined,
  name: string
): PlayerImage | null {
  if (!data || !name) return null;

  const played = (data.result?.players ?? []).find((player) =>
    sameName(player.display_name, name)
  );
  if (played?.image && (played.image.url || played.image.flag_url)) return played.image;

  for (const row of [data.advancement?.home_team, data.advancement?.away_team]) {
    if (row && sameName(row.name, name) && row.logo_url) {
      // The reach board carries a photo and no flag. `flag_url: null` rather
      // than an absent key, so `avatarKind` reads it the same way it reads the
      // register's own block and cannot land on `flag` with nothing to draw.
      return { url: row.logo_url, flag_url: null };
    }
  }
  return null;
}

/**
 * The event payload's own pinned image for one participant, or `null` (#3787).
 *
 * #3784 gave `_format_event` the four keys `/api/feed` has served since #2919,
 * so the detail route now carries `home_image_url` / `home_flag_url` for every
 * INDIVIDUAL-sport event. This packs that pair into the `{url, flag_url}` block
 * `PlayerAvatar` already reads, and returns `null` when neither is there so the
 * caller falls to the next rung rather than rendering an empty `<img>`.
 *
 * `undefined` (team sport — the formatter omits the keys) and `null` ("we
 * looked and this player has no photo") both mean "not this rung", which is the
 * same answer, so they are deliberately not distinguished here.
 */
export function servedParticipantImage(
  url?: string | null,
  flagUrl?: string | null
): PlayerImage | null {
  if (!url && !flagUrl) return null;
  return { url: url ?? null, flag_url: flagUrl ?? null };
}

/**
 * The event hero's avatar slot for ONE player (#2447, extended by #3787).
 *
 * A component rather than a call to `useTournamentPlayerFaces` inside the page,
 * for the ordinary reason: the hero sits below the page's loading and error
 * returns, and a hook called there would change hook order between renders.
 * Wrapping it means the page passes props and this decides.
 *
 * ═══ THE LADDER, AND WHY THE SERVED PAIR GOES IN FRONT (#3787) ═══
 *
 * #2447 put the TOURNAMENT REGISTER in front of the hero's team-logo ladder.
 * That register is keyed to the BRACKET, and the bracket is not the whole
 * tournament: read live on 2026-09-07, `/api/tournaments/by-event/15304939`
 * (Medvedev v Tiafoe, a completed US Open round-of-16) answers
 * `reason: NOT_IN_REGISTER` — no `result`, no `advancement`. So the rung fired,
 * found nothing, and the hero drew `DM` and `FT` while the feed drew both
 * faces. The rung was never missing; it was answering a narrower question.
 *
 * The served pair is keyed by NAME against the same censused register, so it
 * answers for any player in it whether or not they are on this bracket:
 * replayed for those two names it returns both Wikipedia headshots AND both
 * ESPN country flags. It therefore goes in FRONT, which also makes this hero
 * agree with `FeedCard` and `EventCard` — the point of #3787 being that four
 * renderers answer one question and had drifted apart.
 *
 * The register rung STAYS behind it, and is not redundant: it covers a bracket
 * player the name register has no row for. `fallback` — the hero's existing
 * team-logo-then-initials markup — is untouched and is still the answer for
 * every team sport and for a player neither register holds.
 *
 * Geometry is not decided here. `PlayerAvatar` already draws a face
 * `object-cover` and a flag `object-contain`, at whatever `size` it is given,
 * which is why this hero can pass 56 where a match row passes 26 and neither
 * squashes a flag into a square.
 */
export function TournamentPlayerFace({
  eventId,
  sportKey,
  homeName,
  awayName,
  side,
  size,
  servedImage,
  fallback,
}: {
  eventId: number;
  sportKey?: string | null;
  homeName: string;
  awayName: string;
  side: "home" | "away";
  size: number;
  /**
   * The event payload's pinned image for THIS side, via
   * `servedParticipantImage`. Optional so the two existing call sites and the
   * #2447 guards keep their meaning: absent means "ask the register only".
   */
  servedImage?: PlayerImage | null;
  fallback: React.ReactNode;
}) {
  const faces = useTournamentPlayerFaces(eventId, sportKey, homeName, awayName);
  const image = servedImage ?? (side === "home" ? faces.home : faces.away);
  if (!image) return <>{fallback}</>;
  return (
    <PlayerAvatar name={side === "home" ? homeName : awayName} image={image} size={size} />
  );
}

export function TournamentBackLink({
  eventId,
  sportKey,
  onNavigate,
}: {
  eventId: number;
  sportKey?: string | null;
  /** Analytics hook, so this link is tracked exactly as its sibling is. */
  onNavigate?: (href: string) => void;
}) {
  const eligible = isTournamentSportKey(sportKey);
  const { data } = useSWR<EventTournamentResponse>(
    eligible ? eventTournamentKey(eventId) : null,
    () => fetchEventTournament(eventId),
    { revalidateOnFocus: false, refreshInterval: 120000 },
  );

  const tournament = data?.tournament;
  if (!tournament) return null;

  return (
    <Link
      href={tournament.url}
      onClick={() => onNavigate?.(tournament.url)}
      className="inline-flex items-center text-caption text-text-secondary transition-colors hover:text-text-primary"
      data-testid="tournament-back-link"
      data-slug={tournament.slug}
    >
      <svg className="mr-1 h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M15 19l-7-7 7-7"
        />
      </svg>
      {tournament.title}
    </Link>
  );
}
