"use client";
/* eslint-disable @next/next/no-img-element */

import Link from "next/link";
import {
  formatDeckBuiltDate,
  formatDeckCountLine,
  formatReaderLeague,
  type GameNuggetItem,
  type GameNuggetsDeckResponse,
  type GameNuggetsGame,
  type NuggetGrade,
} from "@/lib/ranking/gameNuggetsSession";

export interface GameNuggetsDeckViewProps {
  deck: GameNuggetsDeckResponse;
  grader: string;
  gamesById: Record<number, GameNuggetsGame>;
  selectedGameIdx: number;
  loadingEventId: number | null;
  notice: string | null;
  error: string | null;
  gameError: string | null;
  notesByKey: Record<string, string>;
  savingKey: string | null;
  onSelectGame: (idx: number) => void;
  onChangeNote: (itemKey: string, value: string) => void;
  onSubmitGrade: (game: GameNuggetsGame, nugget: GameNuggetItem, grade: NuggetGrade) => void;
}

export default function GameNuggetsDeckView({
  deck,
  grader,
  gamesById,
  selectedGameIdx,
  loadingEventId,
  notice,
  error,
  gameError,
  notesByKey,
  savingKey,
  onSelectGame,
  onChangeNote,
  onSubmitGrade,
}: GameNuggetsDeckViewProps) {
  const activeSummaryGame = deck.games[selectedGameIdx] || deck.games[0] || null;
  const activeEventId = activeSummaryGame?.event_id ?? null;
  const currentGame = activeEventId !== null ? gamesById[activeEventId] : undefined;
  const pct =
    deck.summary.repeat_rate !== null ? Math.round(deck.summary.repeat_rate * 100) : null;
  const builtLabel = formatDeckBuiltDate(deck.built_at);

  return (
    <main className="mx-auto max-w-5xl px-4 py-6">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs text-text-muted">
        <div className="flex flex-wrap items-center gap-3">
          <Link href="/grade/groupings" className="hover:underline">
            ← Groupings
          </Link>
          <span>Slate: {deck.slate_id}</span>
          <span>Grader: {grader}</span>
          {builtLabel && <span>Built {builtLabel}</span>}
        </div>
        <span className="font-medium text-text-secondary">
          Repeat rate: {pct !== null ? `${pct}%` : "—"} ({deck.summary.yes_count} yes /{" "}
          {deck.summary.no_count} no · target 75%)
        </span>
      </div>

      <p className="mb-4 text-xs text-text-secondary">{formatDeckCountLine(deck)}</p>

      {notice && (
        <p className="mb-3 text-sm text-text-muted" role="status">
          {notice}
        </p>
      )}
      {error && <p className="mb-3 text-sm text-text-secondary">{error}</p>}

      {deck.games.length === 0 ? (
        <div className="rounded-xl border border-surface-border bg-surface-card p-6 text-sm text-text-secondary">
          0 games qualify to grade right now (every dealt game needs at least 6 items across 3 or
          more kinds).
        </div>
      ) : (
        <div className="mb-5 flex gap-2 overflow-x-auto pb-2">
          {deck.games.map((g, idx) => {
            const loaded = gamesById[g.event_id];
            const gDone = loaded
              ? loaded.nuggets.filter((n) => n.saved_grade).length
              : (g.graded_count ?? 0);
            const gTotal = loaded ? loaded.nuggets.length : (g.nugget_count ?? 8);
            const active = idx === selectedGameIdx;
            return (
              <button
                key={g.event_id}
                onClick={() => onSelectGame(idx)}
                className={`shrink-0 rounded-lg border px-3 py-2 text-left text-xs ${
                  active
                    ? "border-accent-primary bg-surface-elevated font-semibold text-text-primary"
                    : "border-surface-border bg-surface-card text-text-secondary"
                }`}
              >
                <div className="text-[11px] font-medium text-text-muted">
                  {formatReaderLeague(g.sport, g.sport_name)}
                </div>
                <div className="truncate max-w-[160px]">
                  {g.away_team} at {g.home_team}
                </div>
                <div className="text-[11px] text-text-muted">
                  {gDone}/{gTotal} graded
                </div>
              </button>
            );
          })}
        </div>
      )}

      {activeEventId !== null && loadingEventId === activeEventId && !currentGame && (
        <p className="text-sm text-text-muted animate-pulse">
          Loading {activeSummaryGame?.away_team} at {activeSummaryGame?.home_team}…
        </p>
      )}
      {gameError && !currentGame && (
        <p className="mb-3 text-sm text-text-secondary">{gameError}</p>
      )}

      {currentGame && (
        <section>
          <header className="mb-4 rounded-xl border border-surface-border bg-surface-card p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-xs font-medium text-text-muted">
                  {formatReaderLeague(currentGame.sport, currentGame.sport_name)} ·{" "}
                  {currentGame.status || "scheduled"}
                </p>
                <h1 className="text-lg font-semibold text-text-primary">
                  {currentGame.away_team} at {currentGame.home_team}
                </h1>
              </div>
              {currentGame.nuggets.length > 0 && (
                <div className="text-xs text-text-secondary">
                  {currentGame.first_eight_kinds} kinds represented in top{" "}
                  {currentGame.nuggets.length}
                </div>
              )}
            </div>
            {currentGame.nuggets.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {currentGame.everything_map.map((entry) => (
                  <span
                    key={entry.kind}
                    className="rounded-full border border-surface-border bg-surface-elevated px-2.5 py-0.5 text-xs text-text-secondary"
                  >
                    {entry.label}: {entry.count}
                  </span>
                ))}
              </div>
            )}
          </header>

          {currentGame.nuggets.length === 0 ? (
            <div className="rounded-xl border border-surface-border bg-surface-card p-6 text-sm text-text-secondary">
              Nothing to grade for this game
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {currentGame.nuggets.map((nugget) => {
                const itemKey = nugget.item_key || `event:${currentGame.event_id}:${nugget.id}`;
                const absMove =
                  nugget.change_points !== null ? Math.abs(nugget.change_points) : 0;
                const moveText =
                  nugget.change_points !== null && nugget.change_points !== 0
                    ? `${nugget.change_points > 0 ? "+" : ""}${nugget.change_points} ${
                        absMove === 1 ? "point" : "points"
                      } ${nugget.change_since === "pregame" ? "since pregame" : "in 24h"}`
                    : null;
                const markSourceText =
                  nugget.pregame_mark_source === "kickoff_pin"
                    ? "mark: kickoff pin"
                    : nugget.pregame_mark_source === "opening"
                      ? "mark: first reading"
                      : null;
                return (
                  <article
                    key={itemKey}
                    className="flex flex-col justify-between rounded-xl border border-surface-border bg-surface-card p-4"
                  >
                    <div>
                      <div className="flex items-center justify-between gap-2">
                        <span className="rounded-full bg-surface-elevated px-2 py-0.5 text-xs font-medium text-text-secondary">
                          #{nugget.position} · {nugget.kind_label}
                        </span>
                        <span className="text-xs text-text-muted">
                          {markSourceText ? `${markSourceText} · ${nugget.form}` : nugget.form}
                        </span>
                      </div>

                      <div className="mt-3 flex items-start gap-3">
                        {nugget.subject.image_url && (
                          <img
                            src={nugget.subject.image_url}
                            alt={nugget.subject.name}
                            className="h-10 w-10 shrink-0 rounded-full border border-surface-border object-cover"
                          />
                        )}
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-text-primary">{nugget.claim}</p>
                          <div className="mt-1 flex items-baseline gap-2">
                            <span className="text-xl font-bold text-text-primary">
                              {nugget.percent}%
                            </span>
                            {moveText && (
                              <span className="text-xs text-text-secondary">{moveText}</span>
                            )}
                          </div>
                          <p className="mt-1 text-xs text-text-muted">{nugget.rank_reason}</p>
                        </div>
                      </div>
                    </div>

                    <div className="mt-3 border-t border-surface-border pt-3">
                      <input
                        className="mb-2 w-full rounded border border-surface-border bg-surface-elevated px-2.5 py-1.5 text-xs text-text-primary"
                        placeholder="Optional note"
                        maxLength={300}
                        value={notesByKey[itemKey] ?? nugget.saved_note ?? ""}
                        onChange={(e) => onChangeNote(itemKey, e.target.value)}
                      />
                      <div className="flex gap-2">
                        <button
                          disabled={savingKey === itemKey}
                          onClick={() => onSubmitGrade(currentGame, nugget, "yes")}
                          className={`flex-1 rounded-lg border px-3 py-1.5 text-xs font-semibold ${
                            nugget.saved_grade === "yes"
                              ? "border-accent-primary bg-accent-primary text-surface-primary"
                              : "border-surface-border bg-surface-elevated text-text-primary"
                          }`}
                        >
                          Yes — would repeat
                        </button>
                        <button
                          disabled={savingKey === itemKey}
                          onClick={() => onSubmitGrade(currentGame, nugget, "no")}
                          className={`flex-1 rounded-lg border px-3 py-1.5 text-xs font-semibold ${
                            nugget.saved_grade === "no"
                              ? "border-accent-primary bg-surface-elevated text-text-primary underline"
                              : "border-surface-border bg-surface-elevated text-text-secondary"
                          }`}
                        >
                          No
                        </button>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      )}
    </main>
  );
}
