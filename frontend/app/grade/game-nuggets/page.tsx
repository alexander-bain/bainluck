"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import AdminAuthProvider, { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import GameNuggetsDeckView from "@/components/admin/GameNuggetsDeckView";
import { adminFetch, adminFetchJSON } from "@/lib/adminFetch";
import { saveWithOneRetry } from "@/lib/ranking/gradeSession";
import { handleGradeDeckReadError } from "@/lib/ranking/groupingGradeSession";
import {
  formatDeckCountLine,
  type GameNuggetItem,
  type GameNuggetsDeckResponse,
  type GameNuggetsGame,
  type NuggetGrade,
  type SingleGameNuggetsResponse,
} from "@/lib/ranking/gameNuggetsSession";
import { useRetryNotice } from "@/lib/ranking/useRetryNotice";

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
        handleGradeDeckReadError(e, "Could not load game-nuggets deck", {
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
    const init = { headers: { "X-Grader-Name": encodeURIComponent(grader) } };
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
        <p className="text-sm text-text-muted animate-pulse">Loading game-nuggets deck…</p>
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
          {formatDeckCountLine(deck)} Grade each nugget on one question: &ldquo;Would a fan repeat
          this?&rdquo; Target: 3 in 4 (75%).
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

  return (
    <GameNuggetsDeckView
      deck={deck}
      grader={grader}
      gamesById={gamesById}
      selectedGameIdx={selectedGameIdx}
      loadingEventId={loadingEventId}
      notice={notice}
      error={error}
      gameError={gameError}
      notesByKey={notesByKey}
      savingKey={savingKey}
      onSelectGame={setSelectedGameIdx}
      onChangeNote={(itemKey, value) =>
        setNotesByKey((prev) => ({ ...prev, [itemKey]: value }))
      }
      onSubmitGrade={(game, nugget, grade) => void submitGrade(game, nugget, grade)}
    />
  );
}
