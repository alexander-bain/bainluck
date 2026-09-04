"use client";

/**
 * The set-by-set score, as a tennis fan reads a scoreboard (live/058, #2746).
 *
 * ═══ WHAT THIS REPLACES ═══
 *
 * The hero prints `home_score` / `away_score`, which for tennis counts SETS.
 * live/057 measured what that costs a reader: in 45 minutes ESPN published 78
 * game-level score changes and our card moved 9 times. A viewer watching a
 * match saw a number that changed roughly twice an hour.
 *
 * `event.linescore` is the finer grain the API now carries. This renders it as
 * the grid the sport is actually scored in — one column per set, the set in
 * play marked, the tiebreak as a superscript.
 *
 * ═══ WHAT IT REFUSES TO DRAW ═══
 *
 * Nothing, when there is nothing. The component returns `null` for a missing or
 * empty linescore rather than rendering an empty strip — a rail that lies is
 * worse than one that is quiet (live/056), and a blank scoreboard beside a live
 * match reads as "0-0".
 */

import { cn } from "@/lib/utils";
import type { TennisLinescore as Linescore } from "@/lib/types";

/** The last word of a player's name — "Popyrin", not "Alexei Popyrin". */
function shortName(name: string): string {
  const parts = (name || "").trim().split(/\s+/);
  return parts.length ? parts[parts.length - 1] : name;
}

/**
 * The score in one set, for one side.
 *
 * `null` prints an en dash rather than `0`: ESPN writes the two sides' lines a
 * fraction apart, so the side it has not written yet is UNPUBLISHED, and a `0`
 * there is a score the reader would believe.
 */
function SetCell({
  games,
  tiebreak,
  emphasis,
}: {
  games: number | null;
  tiebreak: number | null;
  emphasis: boolean;
}) {
  return (
    <td
      className={cn(
        "px-1.5 py-0.5 text-center font-mono tabular-nums text-base leading-tight",
        emphasis ? "font-bold text-text-primary" : "text-text-secondary",
      )}
    >
      {games === null ? "–" : games}
      {tiebreak !== null && (
        <sup className="ml-0.5 text-[10px] font-normal text-text-muted">
          {tiebreak}
        </sup>
      )}
    </td>
  );
}

/**
 * ONE LINE, for a list of matches (live/061, #2746 scope item 1).
 *
 * `6-4 4-6 2-1` — set scores in play order, each set's winner bolded, the
 * tiebreak as a superscript on the loser, the set in play marked. That is the
 * same set of rules the grid above draws by, applied along one axis instead of
 * two, because a slate row's job is to be SCANNED.
 *
 * ═══ WHY IT PRINTS PAIRS AND NOT TWO ROWS ═══
 *
 * A reader scanning thirty rows wants "who is winning and how far in", and a
 * `6-4` pair answers both in four characters. The two-row grid answers it
 * better for one match and thirty times worse for thirty.
 *
 * ═══ WHAT IT WILL NOT DRAW ═══
 *
 * The point score and the serving dot, both of which the full variant shows.
 * They move every few seconds and this list refreshes every 180 seconds by
 * design, so on a slate row they would be the one element guaranteed to be
 * stale — a wrong "40-30" is worse than no point score, and the match page one
 * tap away is where the live-cadence answer lives.
 *
 * `state_disagrees` is not surfaced here either: it is a caveat about the
 * source, and a caveat needs room to be read. The row is still honest — it
 * shows a real line from a real read — and the match page states the caveat.
 */
function CompactLine({
  linescore,
  sets,
  current,
  className,
}: {
  linescore: Linescore;
  sets: NonNullable<Linescore["sets"]>;
  current: number | null;
  className?: string;
}) {
  const completionLabel =
    linescore.completion === "retired"
      ? "ret."
      : linescore.completion === "walkover"
        ? "w/o"
        : linescore.completion === "abandoned"
          ? "abd."
          : null;

  return (
    <span
      className={cn(
        "inline-flex items-baseline gap-1.5 font-mono tabular-nums text-xs leading-tight",
        className,
      )}
      aria-label={`Set scores: ${linescore.line}`}
    >
      {sets.map((set, index) => {
        const live = index + 1 === current;
        return (
          <span
            key={index}
            className={cn(
              "whitespace-nowrap",
              live ? "text-text-primary" : "text-text-secondary",
            )}
          >
            <span className={cn(set.won_by === "home" && "font-bold text-text-primary")}>
              {set.home === null ? "–" : set.home}
              {/* Same rule as the grid: the superscript belongs to the LOSER of
                  the set, and to nobody while the tiebreak is unfinished. */}
              {set.won_by !== null && set.won_by !== "home" && set.home_tiebreak !== null && (
                <sup className="text-[9px] font-normal text-text-muted">
                  {set.home_tiebreak}
                </sup>
              )}
            </span>
            <span className="text-text-muted">-</span>
            <span className={cn(set.won_by === "away" && "font-bold text-text-primary")}>
              {set.away === null ? "–" : set.away}
              {set.won_by !== null && set.won_by !== "away" && set.away_tiebreak !== null && (
                <sup className="text-[9px] font-normal text-text-muted">
                  {set.away_tiebreak}
                </sup>
              )}
            </span>
          </span>
        );
      })}
      {completionLabel && (
        <span className="font-sans text-[10px] uppercase tracking-wide text-text-muted">
          {completionLabel}
        </span>
      )}
    </span>
  );
}

export default function TennisLinescore({
  linescore,
  homeName,
  awayName,
  className,
  variant = "full",
}: {
  linescore: Linescore | null | undefined;
  homeName: string;
  awayName: string;
  className?: string;
  /**
   * `"full"` is the two-row grid above, for a page about ONE match.
   *
   * `"compact"` (live/061, #2746 scope item 1) is one line for a LIST of
   * matches — the tournament hub's slate row, where thirty of these sit under
   * each other and a two-row table per row would turn a scannable card into a
   * wall of grids. It prints the same sets in the same order off the same
   * payload; what it drops is the player-name column (the row already names
   * both players, directly above), the point score, and the serving dot.
   *
   * It is deliberately the SAME component rather than a second one. Two
   * renderers of one linescore is how the hub and the match page would come to
   * disagree about a tiebreak, and the superscript rule below is exactly the
   * kind of thing that only stays right in one place.
   */
  variant?: "full" | "compact";
}) {
  const sets = linescore?.sets;
  if (!linescore || !Array.isArray(sets) || sets.length === 0) return null;

  const current = linescore.current_set;

  if (variant === "compact") {
    return (
      <CompactLine
        linescore={linescore}
        sets={sets}
        current={current}
        className={className}
      />
    );
  }

  /**
   * The caption beside the grid.
   *
   * `completion` is an enum and `status_detail` is ESPN's own display text, and
   * the enum wins where it says something — "Retired" is a fact about the match
   * and "3rd Set" is a fact about the moment, so a retired match must not be
   * captioned by the set it stopped in. `unknown` is deliberately NOT rendered:
   * it means ESPN sent a status we hold no word for, and inventing one is the
   * defect the enum exists to avoid.
   */
  const completionLabel =
    linescore.completion === "retired"
      ? "Retired"
      : linescore.completion === "walkover"
        ? "Walkover"
        : linescore.completion === "abandoned"
          ? "Abandoned"
          : null;
  const caption = completionLabel ?? linescore.status_detail ?? null;

  const rows: Array<{ name: string; side: "home" | "away" }> = [
    { name: homeName, side: "home" },
    { name: awayName, side: "away" },
  ];

  /**
   * live/059 addendum (D59 = A′) — THE CURRENT GAME, when the line's source
   * carries one.
   *
   * `points` and `serving` are non-null only on a StatPal line, because ESPN's
   * tennis scoreboard publishes neither. They are read off THIS payload and
   * never off any other object, which is the renderer's half of the atomicity
   * rule: the sets above and the points below are the same source's reading of
   * the same instant, or the points are not shown at all.
   *
   * The point column is only drawn while a set is in play. A finished match has
   * no current game, and a trailing "40–30" beside a final score is the kind of
   * leftover a reader reads as live.
   */
  const points = current !== null ? linescore.points : null;
  const serving = current !== null ? linescore.serving : null;

  return (
    <div className={cn("flex flex-col items-center gap-1", className)}>
      <table
        className="border-separate border-spacing-0"
        aria-label={`Set scores: ${linescore.line}`}
      >
        <tbody>
          {rows.map(({ name, side }) => (
            <tr key={side}>
              <td className="pr-2 text-xs font-semibold text-text-primary whitespace-nowrap">
                {/* THE SERVER, as a scoreboard marks it — a dot beside the name.
                    Rendered only when the line's own source states it, so an
                    ESPN line is byte-for-byte what it was. */}
                {serving === side && (
                  <span
                    aria-label="serving"
                    title="Serving"
                    className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-accent-primary align-middle"
                  />
                )}
                {shortName(name)}
              </td>
              {sets.map((set, index) => (
                <SetCell
                  key={index}
                  games={side === "home" ? set.home : set.away}
                  /* THE SUPERSCRIPT GOES ON THE LOSER OF THE SET, and on
                     nobody while the tiebreak is still being played — the same
                     rule `format_set` prints `7-6(4)` by. Both sides carry
                     points in the payload; showing both would print `6⁴ 7⁷`,
                     which is two numbers for one tiebreak and reads as a
                     second set. A tiebreak with no winner yet shows none:
                     either number could be the loser's, and guessing puts a
                     7-5 result on the wrong side. */
                  tiebreak={
                    set.won_by === null || set.won_by === side
                      ? null
                      : side === "home"
                        ? set.home_tiebreak
                        : set.away_tiebreak
                  }
                  /* The set in play, and the sets this side WON. A completed set
                     nobody bolds reads as a list of numbers; bolding the winner
                     of each is how a scoreboard says who took it. */
                  emphasis={index + 1 === current || set.won_by === side}
                />
              ))}
              {/* THE POINT SCORE — its own column, set apart by a rule, because
                  it is a different unit from every cell to its left. A "40" in
                  the same run of columns as "6" and "7" reads as a set score of
                  forty. */}
              {points && (
                <td className="border-l border-surface-border pl-2 text-center font-mono tabular-nums text-base leading-tight font-bold text-text-primary">
                  {(side === "home" ? points.home : points.away) ?? "–"}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {caption && (
        <span className="text-[11px] uppercase tracking-wide text-text-muted">
          {caption}
        </span>
      )}
      {/* THE DISAGREEMENT, said out loud (D59 = A′). ESPN owns the state; when
          the source that owns the SCORE has not caught up with it, the reader is
          told the score is a moment old rather than shown a line that pretends
          the two agree. */}
      {linescore.state_disagrees && (
        <span className="text-[11px] text-text-muted">
          Score as of the last update from the live feed
        </span>
      )}
    </div>
  );
}
