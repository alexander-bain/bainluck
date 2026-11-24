"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import AdminAuthProvider, { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { adminFetch, adminFetchJSON } from "@/lib/adminFetch";
import { saveWithOneRetry } from "@/lib/ranking/gradeSession";
import { handleGradeDeckReadError } from "@/lib/ranking/groupingGradeSession";
import { useRetryNotice } from "@/lib/ranking/useRetryNotice";

type NuggetGrade = "yes" | "no";

interface NuggetSubject {
  name: string;
  image_url?: string | null;
  image_kind?: "headshot" | "logo" | null;
}

interface GameNuggetItem {
  id: string;
  item_key?: string;
  position: number;
  kind: string;
  kind_label: string;
  subject: NuggetSubject;
  claim: string;
  probability: number;
  percent: number;
  change_points: number | null;
  change_since: string | null;
  pregame_percent: number | null;
  form: string;
  rank_reason: string;
  saved_grade?: NuggetGrade;
  saved_note?: string | null;
}

interface KindCountEntry {
  kind: string;
  label: string;
  count: number;
  target_section: string;
}

interface GameNuggetsDeckSummaryGame {
  event_id: number;
  home_team: string;
  away_team: string;
  sport: string | null;
  status: string | null;
  commence_time: string | null;
  graded_count?: number;
}

interface GameNuggetsGame extends GameNuggetsDeckSummaryGame {
  nuggets: GameNuggetItem[];
  first_eight_kinds: number;
  everything_map: KindCountEntry[];
}

interface NuggetGradeSummary {
  graded_count: number;
  yes_count: number;
  no_count: number;
  repeat_rate: number | null;
  target_rate: number;
  meets_target: boolean;
}

interface GameNuggetsDeckResponse {
  slate_id: string;
  surface: string;
  games_count: number;
  games: GameNuggetsDeckSummaryGame[];
  summary: NuggetGradeSummary;
}

interface SingleGameNuggetsResponse {
  slate_id: string;
  surface: string;
  event_id: number;
  game: GameNuggetsGame;
  summary: NuggetGradeSummary;
}

const GRADER_STORAGE_KEY = "bainluck_game_nuggets_grader";

export default function GameNuggetsGradePage() {
  usePageTracking({ pageType: "admin_grade" });
  useScrollDepth({ pageType: "admin_grade" });
  useEngagementTime({ pageType: "admin_grade" });

  return (
    <AdminAuthProvider>
      <GameNuggetsGradeSession />
    </AdminAuthProvider>
  );
}

function GameNuggetsGradeSession() {
  const { secret, clearSecret } = useAdminAuth();
  const [deck, setDeck] = useState<GameNuggetsDeckResponse | null>(null);
  const [gamesById, setGamesById] = useState<Record<number, GameNuggetsGame>>({});
  const [loadingEventId, setLoadingEventId] = useState<number | null>(null);
  const [gameError, setGameError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nameInput, setNameInput] = useState("Alex");
  const [grader, setGrader] = useState<string | null>(null);
  const [selectedGameIdx, setSelectedGameIdx] = useState(0);
  const [notesByKey, setNotesByKey] = useState<Record<string, string>>({});
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const { notice, startWait, clearNotice } = useRetryNotice();

  useEffect(() => {
    try {
      const saved = localStorage.getItem(GRADER_STORAGE_KEY);
      if (saved) setNameInput(saved);
    } catch {
      // storage unavailable
    }
  }, []);

  const loadDeck = useCallback(
    async (graderHeader: string | null) => {
      try {
        const init = graderHeader
          ? { headers: { "X-Grader-Name": encodeURIComponent(graderHeader) } }
          : undefined;
        const data = await adminFetchJSON<GameNuggetsDeckResponse>(
          "/api/admin/ranking/game-nuggets/deck?limit=20",
          secret,
          init,
        );
        setDeck(data);
        setGamesById({});
      } catch (e: unknown) {
        handleGradeDeckReadError(e, "Could not load 20-game nuggets slate", {
          clearSecret,
          setError,
        });
      }
    },
    [secret, clearSecret],
  );

  useEffect(() => {
    void loadDeck(grader);
  }, [grader, loadDeck]);

  const activeSummaryGame = deck?.games[selectedGameIdx] || deck?.games[0] || null;
  const activeEventId = activeSummaryGame?.event_id ?? null;

  useEffect(() => {
    if (!deck || !grader || activeEventId === null) return;
    if (gamesById[activeEventId]) return;
    let cancelled = false;
    setLoadingEventId(activeEventId);
    setGameError(null);
    const params = new URLSearchParams({ limit: "8", slate: deck.slate_id });
    const init = grader ? { headers: { "X-Grader-Name": encodeURIComponent(grader) } } : undefined;
    adminFetchJSON<SingleGameNuggetsResponse>(
      `/api/admin/ranking/game-nuggets/games/${activeEventId}?${params.toString()}`,
      secret,
      init,
    )
      .then((res) => {
        if (cancelled) return;
        setGamesById((prev) => ({ ...prev, [activeEventId]: res.game }));
        setDeck((prev) => (prev ? { ...prev, summary: res.summary } : prev));
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        handleGradeDeckReadError(e, `Could not load game ${activeEventId}`, {
          clearSecret,
          setError: setGameError,
        });
      })
      .finally(() => {
        if (!cancelled) setLoadingEventId((cur) => (cur === activeEventId ? null : cur));
      });
    return () => {
      cancelled = true;
    };
  }, [deck, grader, activeEventId, gamesById, secret, clearSecret]);

  const startSession = () => {
    const cleaned = nameInput.trim();
    if (!cleaned) return;
    try {
      localStorage.setItem(GRADER_STORAGE_KEY, cleaned);
    } catch {
      // storage unavailable
    }
    setGrader(cleaned);
  };

  const submitGrade = async (
    game: GameNuggetsGame,
    nugget: GameNuggetItem,
    grade: NuggetGrade,
  ) => {
    const activeGrader = grader || nameInput.trim();
    if (!deck || !activeGrader || savingKey) return;
    const itemKey = nugget.item_key || `event:${game.event_id}:${nugget.id}`;
    const noteText = (notesByKey[itemKey] || "").trim();
    setSavingKey(itemKey);
    setError(null);
    try {
      const body = JSON.stringify({
        slate_id: deck.slate_id,
        event_id: game.event_id,
        nugget_id: nugget.id,
        position: nugget.position,
        grade,
        grader: activeGrader,
        note: noteText || null,
      });
      const res = await saveWithOneRetry(
        () =>
          adminFetch("/api/admin/ranking/game-nuggets/grades", secret, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body,
          }),
        (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
        startWait,
      );
      clearNotice();
      if (!res.ok) {
        setError(`Not saved (${res.status}): ${(await res.text()).slice(0, 180)}`);
        return;
      }
      const prevGrade = nugget.saved_grade ?? null;
      setGamesById((prev) => {
        const cur = prev[game.event_id] || game;
        return {
          ...prev,
          [game.event_id]: {
            ...cur,
            nuggets: cur.nuggets.map((n) =>
              n.id === nugget.id ? { ...n, saved_grade: grade, saved_note: noteText || null } : n,
            ),
          },
        };
      });
      setDeck((prev) => {
        if (!prev) return prev;
        let yesCount = prev.summary.yes_count;
        let noCount = prev.summary.no_count;
        if (prevGrade === "yes") yesCount = Math.max(0, yesCount - 1);
        if (prevGrade === "no") noCount = Math.max(0, noCount - 1);
        if (grade === "yes") yesCount += 1;
        if (grade === "no") noCount += 1;
        const total = yesCount + noCount;
        const rate = total > 0 ? yesCount / total : null;
        const addedNew = prevGrade === null;
        return {
          ...prev,
          games: prev.games.map((g) =>
            g.event_id === game.event_id
              ? { ...g, graded_count: (g.graded_count || 0) + (addedNew ? 1 : 0) }
              : g,
          ),
          summary: {
            graded_count: total,
            yes_count: yesCount,
            no_count: noCount,
            repeat_rate: rate,
            target_rate: 0.75,
            meets_target: rate !== null && rate >= 0.75,
          },
        };
      });
    } catch {
      clearNotice();
      setError("Not saved: network dropped. Please try again.");
    } finally {
      setSavingKey(null);
    }
  };

  if (error && !deck) {
    return (
      <main className="mx-auto max-w-4xl px-4 py-6">
        <p className="text-sm text-text-secondary">{error}</p>
      </main>
    );
  }

  if (!deck) {
    return (
      <main className="mx-auto max-w-4xl px-4 py-6">
        <p className="text-sm text-text-muted animate-pulse">Loading 20-game slate…</p>
      </main>
    );
  }

  if (!grader) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-8">
        <div className="mb-4 text-xs text-text-muted">
          <Link href="/grade/groupings" className="hover:underline">
            ← Grouping grade deck
          </Link>
        </div>
        <h1 className="text-xl font-semibold text-text-primary">
          Game Page Nuggets Grading (#13511)
        </h1>
        <p className="mt-2 text-sm text-text-secondary">
          {deck.games_count} games queued (loaded one game at a time). Grade each nugget on one
          question: &ldquo;Would a fan repeat this?&rdquo; Target: 3 in 4 (75%).
        </p>
        <div className="mt-4 flex flex-col gap-3 sm:flex-row">
          <input
            className="flex-1 rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-sm text-text-primary"
            value={nameInput}
            onChange={(e) => setNameInput(e.target.value)}
            placeholder="Grader name"
            maxLength={40}
          />
          <button
            className="rounded-lg bg-accent-primary px-4 py-2 text-sm font-semibold text-surface-primary"
            onClick={startSession}
          >
            Start grading
          </button>
        </div>
      </main>
    );
  }

  const currentGame = activeEventId !== null ? gamesById[activeEventId] : undefined;
  const pct =
    deck.summary.repeat_rate !== null ? Math.round(deck.summary.repeat_rate * 100) : null;

  return (
    <main className="mx-auto max-w-5xl px-4 py-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2 text-xs text-text-muted">
        <div className="flex items-center gap-3">
          <Link href="/grade/groupings" className="hover:underline">
            ← Groupings
          </Link>
          <span>Slate: {deck.slate_id}</span>
          <span>Grader: {grader}</span>
        </div>
        <span className="font-medium text-text-secondary">
          Repeat rate: {pct !== null ? `${pct}%` : "—"} ({deck.summary.yes_count} yes /{" "}
          {deck.summary.no_count} no · target 75%)
        </span>
      </div>

      {notice && (
        <p className="mb-3 text-sm text-text-muted" role="status">
          {notice}
        </p>
      )}
      {error && <p className="mb-3 text-sm text-text-secondary">{error}</p>}

      <div className="mb-5 flex gap-2 overflow-x-auto pb-2">
        {deck.games.map((g, idx) => {
          const loaded = gamesById[g.event_id];
          const gDone = loaded
            ? loaded.nuggets.filter((n) => n.saved_grade).length
            : (g.graded_count ?? 0);
          const gTotal = loaded ? loaded.nuggets.length : 8;
          const active = idx === selectedGameIdx;
          return (
            <button
              key={g.event_id}
              onClick={() => setSelectedGameIdx(idx)}
              className={`shrink-0 rounded-lg border px-3 py-2 text-left text-xs ${
                active
                  ? "border-accent-primary bg-surface-elevated font-semibold text-text-primary"
                  : "border-surface-border bg-surface-card text-text-secondary"
              }`}
            >
              <div className="text-[11px] uppercase text-text-muted">{g.sport || "game"}</div>
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
                <p className="text-xs uppercase text-text-muted">
                  {currentGame.sport || "sport"} · {currentGame.status || "scheduled"}
                </p>
                <h1 className="text-lg font-semibold text-text-primary">
                  {currentGame.away_team} at {currentGame.home_team}
                </h1>
              </div>
              <div className="text-xs text-text-secondary">
                {currentGame.first_eight_kinds} kinds represented in top {currentGame.nuggets.length}
              </div>
            </div>
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
          </header>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {currentGame.nuggets.map((nugget) => {
              const itemKey = nugget.item_key || `event:${currentGame.event_id}:${nugget.id}`;
              const absMove = nugget.change_points !== null ? Math.abs(nugget.change_points) : 0;
              const moveText =
                nugget.change_points !== null && nugget.change_points !== 0
                  ? `${nugget.change_points > 0 ? "+" : ""}${nugget.change_points} ${
                      absMove === 1 ? "point" : "points"
                    } ${nugget.change_since === "pregame" ? "since pregame" : "in 24h"}`
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
                      <span className="text-xs text-text-muted">{nugget.form}</span>
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
                      onChange={(e) =>
                        setNotesByKey((prev) => ({ ...prev, [itemKey]: e.target.value }))
                      }
                    />
                    <div className="flex gap-2">
                      <button
                        disabled={savingKey === itemKey}
                        onClick={() => void submitGrade(currentGame, nugget, "yes")}
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
                        onClick={() => void submitGrade(currentGame, nugget, "no")}
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
        </section>
      )}
    </main>
  );
}
