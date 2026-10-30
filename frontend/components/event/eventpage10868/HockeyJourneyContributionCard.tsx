"use client";

/**
 * #10868 — a hockey journey player story (web): points as columns, assists as
 * bars. Every number, word and default is the view model's
 * (`HockeyJourneyContribution`). The reader's choice of player and milestone
 * is HELD BY THE PAGE (`held` / `onHold`, native host state) and resolved by
 * `resolveContributionChoice`: the first player at its default milestone only
 * until the reader chooses; a held player or milestone that is no longer
 * served stays held and says so ("Selected player unavailable."), with the
 * chooser still reachable — only a new explicit choice substitutes, and a
 * refresh never rewrites the choice. A milestone with no pregame chance keeps
 * its place and its absence words — it never borrows a neighbour's number. A
 * count is performance, never a chance, and appears only once play starts:
 * before play there is no count, progress, in-game or result block at all
 * (native `PlayerContributionInput10868.actualPresentation` / `currentReading`
 * / `result`).
 */

import { useId } from "react";
import { propVerdictLabel } from "@/lib/propGrade";
import {
  CONTRIBUTION_WORDS,
  resolveContributionChoice,
  type HockeyJourneyContribution,
  type HockeyJourneyCurrent,
  type HockeyJourneyHeldChoice,
  type HockeyJourneyMilestone,
  type HockeyJourneyPhase,
} from "@/lib/eventPage10868/hockeyJourney";

function currentWords(current: HockeyJourneyCurrent): { text: string; strong: boolean } {
  if (current.kind === "recorded") return { text: current.observation.text, strong: true };
  return { text: current.words, strong: current.kind === "reached" };
}

function MilestoneFoot({ milestone, phase }: { milestone: HockeyJourneyMilestone; phase: HockeyJourneyPhase }) {
  // The in-game slot during play only; the result after the final only.
  const current = phase === "live" ? milestone.current : null;
  const result = phase === "final" ? milestone.result : null;
  if (!current && !result) return null;
  return (
    <span className="mt-1 block space-y-0.5 text-sm">
      {current && (
        <span className={`block ${currentWords(current).strong ? "font-semibold text-text-primary" : "text-text-secondary"}`}>
          {current.kind === "recorded" ? "In-game " : ""}
          {currentWords(current).text}
        </span>
      )}
      {result && (
        <span
          className={`inline-block rounded-full border border-surface-border px-2 py-0.5 ${
            result.kind === "reached" ? "bg-surface-elevated font-semibold text-text-primary" : "text-text-secondary"
          }`}
        >
          {/* Web's one settled vocabulary (lib/propGrade.ts); unknown is not loss. */}
          {result.kind === "unconfirmed" ? result.words : propVerdictLabel(result.kind === "reached")}
        </span>
      )}
    </span>
  );
}

export default function HockeyJourneyContributionCard({
  card,
  held,
  onHold,
}: {
  card: HockeyJourneyContribution;
  /** The page's held choice for this story. */
  held: HockeyJourneyHeldChoice;
  /** Called only on the reader's own explicit choice. */
  onHold: (next: HockeyJourneyHeldChoice) => void;
}) {
  const chooserId = useId();
  const titleId = useId();
  const noticeId = useId();

  const { player, selected, notice } = resolveContributionChoice(card, held);
  const columns = card.orientation === "columns";
  // A held player no longer served keeps the chooser reachable even if fewer than two remain.
  const chooserLabel = card.chooserTitle ?? (player ? null : card.chooseLabel);
  // Choosing a milestone also pins the player shown, so a refresh that reorders
  // the players cannot move the held milestone onto someone else.
  const chooseMilestone = (id: string) => {
    if (player) onHold({ playerId: player.id, milestoneId: id });
  };

  return (
    <article aria-labelledby={titleId} className="space-y-3">
      <header>
        <p className="text-xs font-semibold tracking-wide text-text-secondary">{card.eyebrow}</p>
        <h4 id={titleId} className="text-lg font-bold">
          {card.title}
        </h4>
        <p className="text-sm text-text-secondary">{card.definition}</p>
      </header>

      {chooserLabel ? (
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor={chooserId} className="text-sm font-medium">
            {chooserLabel}
          </label>
          <select
            id={chooserId}
            value={player ? player.id : ""}
            aria-describedby={notice ? noticeId : undefined}
            onChange={(e) => {
              if (e.target.value) onHold({ playerId: e.target.value, milestoneId: null });
            }}
            className="min-h-11 rounded-md border border-surface-border bg-surface-card px-2 text-base"
          >
            {/* The held player is no longer served: the chooser says so rather than showing someone else. */}
            {!player && notice && (
              <option value="" disabled>
                {notice}
              </option>
            )}
            {card.players.map((p) => (
              <option key={p.id} value={p.id}>
                {p.team ? `${p.name} · ${p.team}` : p.name}
              </option>
            ))}
          </select>
        </div>
      ) : (
        player && (
          <p className="text-base font-semibold">
            {player.name}
            {player.team && <span className="font-normal text-text-secondary"> · {player.team}</span>}
          </p>
        )
      )}

      {notice && (
        <p id={noticeId} role="status" className="text-sm font-medium text-text-secondary">
          {notice}
        </p>
      )}

      {/* The count: none before play; "Count so far" during; "Final count" after. */}
      {player && card.phase !== "before" && (
        <div className="rounded-lg bg-surface-deep p-3">
          <p className="text-sm font-medium text-text-secondary">{card.phase === "live" ? CONTRIBUTION_WORDS.countSoFarTitle : CONTRIBUTION_WORDS.finalCountTitle}</p>
          {player.actual.kind === "count" ? (
            <p>
              <span className="text-2xl font-bold tabular-nums">{player.actual.count}</span>{" "}
              <span className="text-base font-medium">{player.actual.unit}</span>
              {player.actual.breakdown && <span className="block text-sm text-text-secondary">{player.actual.breakdown}</span>}
            </p>
          ) : (
            <p className="text-sm font-medium text-text-secondary">{player.actual.words}</p>
          )}
        </div>
      )}

      {player && <p className="text-sm font-medium text-text-secondary">{card.chartTitle}</p>}
      {player && (
        <div role="group" aria-label={`${player.name} milestones`}>
          {columns ? (
            <ul className="flex items-end gap-2 overflow-x-auto pb-1">
              {player.milestones.map((m) => {
                const pressed = selected?.id === m.id;
                return (
                  <li key={m.id} className="min-w-[4.5rem] flex-1">
                    <button
                      type="button"
                      aria-pressed={pressed}
                      onClick={() => chooseMilestone(m.id)}
                      className={`flex w-full flex-col items-stretch rounded-md p-1 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand ${
                        pressed ? "ring-2 ring-text-primary" : ""
                      }`}
                    >
                      <span className={m.before ? "text-lg font-bold tabular-nums" : "text-sm font-medium text-text-secondary"}>
                        {m.before ? m.before.text : m.beforeMissing}
                      </span>
                      <span className="relative mt-1 block h-28 w-full rounded-sm bg-surface-elevated" aria-hidden="true">
                        {m.before && (
                          <span
                            className="absolute inset-x-0 bottom-0 block rounded-sm"
                            style={{ height: `${m.before.probability * 100}%`, background: "var(--series-1)" }}
                          />
                        )}
                      </span>
                      <span className="mt-1 block text-base font-semibold">{m.target}</span>
                      <MilestoneFoot milestone={m} phase={card.phase} />
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : (
            <ul className="space-y-2">
              {player.milestones.map((m) => {
                const pressed = selected?.id === m.id;
                return (
                  <li key={m.id}>
                    <button
                      type="button"
                      aria-pressed={pressed}
                      onClick={() => chooseMilestone(m.id)}
                      className={`w-full rounded-md p-1 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand ${
                        pressed ? "ring-2 ring-text-primary" : ""
                      }`}
                    >
                      <span className="flex flex-wrap items-baseline justify-between gap-2">
                        <span className="text-base font-semibold">{m.target}</span>
                        <span className={m.before ? "text-lg font-bold tabular-nums" : "text-sm font-medium text-text-secondary"}>
                          {m.before ? m.before.text : m.beforeMissing}
                        </span>
                      </span>
                      <span className="relative mt-1 block h-3 w-full rounded-sm bg-surface-elevated" aria-hidden="true">
                        {m.before && (
                          <span
                            className="absolute inset-y-0 left-0 block rounded-sm"
                            style={{ width: `${m.before.probability * 100}%`, background: "var(--series-2)" }}
                          />
                        )}
                      </span>
                      <MilestoneFoot milestone={m} phase={card.phase} />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}

      {player && selected && (
        <div className="rounded-lg border border-surface-border p-3">
          <p className="text-sm font-semibold">{selected.timingTitle}</p>
          {card.phase === "live" && selected.progress && (
            <p className="mt-1 text-sm">
              {selected.progress.status}
            </p>
          )}
          <ul className="mt-1 space-y-0.5 text-sm text-text-secondary">
            {selected.timing.map((line, i) => (
              <li key={`${i}:${line}`} className="break-words">
                {line}
              </li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}
