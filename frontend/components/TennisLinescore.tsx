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

export default function TennisLinescore({
  linescore,
  homeName,
  awayName,
  className,
}: {
  linescore: Linescore | null | undefined;
  homeName: string;
  awayName: string;
  className?: string;
}) {
  const sets = linescore?.sets;
  if (!linescore || !Array.isArray(sets) || sets.length === 0) return null;

  const current = linescore.current_set;

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
            </tr>
          ))}
        </tbody>
      </table>
      {caption && (
        <span className="text-[11px] uppercase tracking-wide text-text-muted">
          {caption}
        </span>
      )}
    </div>
  );
}
