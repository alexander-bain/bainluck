"use client";

// L2-176 — THE PLAY PAGE (/play). A kid-safe rating game for Alex's kids.
// Unlisted from nav; rides existing feed + prediction APIs. FRONTEND-ONLY.
//   • Pick-your-player (emoji + name + "things you love") → deterministic kid:<slug> id
//   • Game 1: "Cool or Boring?" swipe cards (like/unlike under the kid id)
//   • Game 2: "Higher or Lower?" (Today's Challenge mechanic under the kid id)
//   • Two-player leaderboard (rating COUNT + best streak = the score)

import { useCallback, useEffect, useMemo, useState } from "react";
import ErrorBoundary from "@/components/ErrorBoundary";
import { useEngagementTime, usePageTracking, useScrollDepth } from "@/hooks";
import { usePlayPool } from "@/lib/play/usePlayPool";
import type { PlayPoolStatus } from "@/lib/play/poolState";
import { useStableDeck } from "@/lib/play/stableDeck";
import {
  LOVE_CHIPS,
  getPlayers,
  upsertPlayer,
  getActivePlayerName,
  setActivePlayerName,
  getAllStats,
  getStats,
  kidSlug,
  type KidPlayer,
} from "@/lib/play/session";
import CoolOrBoring from "./CoolOrBoring";
import HigherLower from "./HigherLower";

const AVATARS = ["🦖", "🦄", "🐯", "🦊", "🐸", "🐙", "🦩", "🐳", "🦁", "🐼", "👾", "🤖"];

type Mode = "menu" | "cool" | "higher";

export default function PlayPage() {
  usePageTracking({ pageType: "play", pageTitle: "Play" });
  useScrollDepth({ pageType: "play" });
  useEngagementTime({ pageType: "play" });

  const [players, setPlayers] = useState<KidPlayer[]>([]);
  const [active, setActive] = useState<KidPlayer | null>(null);
  const [mode, setMode] = useState<Mode>("menu");
  const [statsVersion, setStatsVersion] = useState(0);

  // signup form state
  const [newName, setNewName] = useState("");
  const [newAvatar, setNewAvatar] = useState(AVATARS[0]);
  const [newLoves, setNewLoves] = useState<string[]>([]);

  // Explicit card-pool state machine (L2-194). It owns loading/ready/error/
  // exhausted, carries the server page boundary separately from usable-card
  // count, and hands both games a single honest terminal.
  const { pool, status: poolStatus, hasMore, loadMore, retry, refresh } = usePlayPool();

  // Load stored players + active player on mount.
  useEffect(() => {
    const stored = getPlayers();
    setPlayers(stored);
    const activeName = getActivePlayerName();
    const found = activeName ? stored.find((p) => kidSlug(p.name) === kidSlug(activeName)) : null;
    if (found) setActive(found);
  }, []);

  // Deck for the active player: a prefix-STABLE, per-round ordered queue built
  // from the kid-safe pool and biased toward their loves. Appending a page never
  // reorders the visible prefix or the card/question under the child (L2-195);
  // switching player starts a fresh round.
  const roundKey = active ? kidSlug(active.name) : "__none__";
  const loves = useMemo(() => active?.loves ?? [], [active]);
  const deck = useStableDeck(pool, loves, roundKey);

  const choosePlayer = useCallback((p: KidPlayer) => {
    setActive(p);
    setActivePlayerName(p.name);
    setMode("menu");
  }, []);

  const createPlayer = useCallback(() => {
    const name = newName.trim();
    if (!name) return;
    const player: KidPlayer = { name, emoji: newAvatar, loves: newLoves };
    const updated = upsertPlayer(player);
    setPlayers(updated);
    choosePlayer(player);
    setNewName("");
    setNewLoves([]);
  }, [newName, newAvatar, newLoves, choosePlayer]);

  const toggleLove = useCallback((id: string) => {
    setNewLoves((cur) =>
      cur.includes(id) ? cur.filter((x) => x !== id) : cur.length >= 3 ? cur : [...cur, id]
    );
  }, []);

  const onStatsChange = useCallback(() => setStatsVersion((v) => v + 1), []);

  // ---- Pick-your-player screen ----
  if (!active) {
    return (
      <ErrorBoundary fallback={<div className="p-8 text-center">Something went wrong</div>}>
        <main className="min-h-screen bg-surface-deep px-5 py-8">
          <div className="mx-auto max-w-md text-center">
            <div className="text-5xl mb-2">🍀🎮</div>
            <h1 className="text-3xl font-black text-text-primary">Bain Luck Play</h1>
            <p className="text-text-secondary mt-1 mb-6">Who&apos;s playing?</p>

            {players.length > 0 && (
              <div className="grid grid-cols-2 gap-3 mb-6">
                {players.map((p) => (
                  <button
                    key={kidSlug(p.name)}
                    onClick={() => choosePlayer(p)}
                    className="rounded-3xl border-2 border-surface-border bg-surface-card px-4 py-5 shadow-sm active:scale-95 transition-transform"
                    style={{ minHeight: 96 }}
                  >
                    <div className="text-5xl">{p.emoji}</div>
                    <div className="mt-2 font-black text-text-primary">{p.name}</div>
                    <div className="text-xs text-text-muted">{getStats(p.name).rated} rated</div>
                  </button>
                ))}
              </div>
            )}

            {/* New player */}
            <div className="rounded-3xl border-2 border-dashed border-surface-border bg-surface-card p-5 text-left">
              <div className="font-black text-text-primary mb-3 text-center">✨ New player</div>
              <div className="flex flex-wrap gap-2 justify-center mb-4">
                {AVATARS.map((a) => (
                  <button
                    key={a}
                    onClick={() => setNewAvatar(a)}
                    className={`text-3xl rounded-2xl p-1.5 transition-transform ${
                      newAvatar === a ? "bg-accent-brand/15 scale-110 ring-2 ring-accent-brand" : ""
                    }`}
                    style={{ minWidth: 48, minHeight: 48 }}
                    aria-label={`avatar ${a}`}
                  >
                    {a}
                  </button>
                ))}
              </div>
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Your name"
                maxLength={16}
                className="w-full rounded-2xl border-2 border-surface-border bg-surface-elevated px-4 py-3 text-lg font-bold text-text-primary text-center outline-none focus:border-accent-brand"
              />

              <div className="mt-4 mb-2 text-sm font-bold text-text-secondary text-center">
                Pick up to 3 things you love
              </div>
              <div className="flex flex-wrap gap-2 justify-center">
                {LOVE_CHIPS.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => toggleLove(c.id)}
                    className={`rounded-full px-4 py-2 text-sm font-bold border-2 transition-colors ${
                      newLoves.includes(c.id)
                        ? "bg-accent-brand text-white border-accent-brand"
                        : "bg-surface-elevated text-text-secondary border-surface-border"
                    }`}
                    style={{ minHeight: 44 }}
                  >
                    {c.emoji} {c.label}
                  </button>
                ))}
              </div>

              <button
                onClick={createPlayer}
                disabled={!newName.trim()}
                className="mt-5 w-full rounded-2xl bg-accent-brand px-6 py-4 text-white font-black text-lg disabled:opacity-40 active:scale-95 transition-transform"
                style={{ minHeight: 56 }}
              >
                Let&apos;s play! 🚀
              </button>
            </div>
          </div>
        </main>
      </ErrorBoundary>
    );
  }

  // ---- Games ----
  if (mode === "cool") {
    return (
      <ErrorBoundary fallback={<div className="p-8 text-center">Something went wrong</div>}>
        <main className="min-h-screen bg-surface-deep">
          <CoolOrBoring
            deck={deck}
            playerName={active.name}
            playerEmoji={active.emoji}
            initialRated={getStats(active.name).rated}
            poolStatus={poolStatus}
            hasMore={hasMore}
            onRatedChange={onStatsChange}
            onNeedMore={loadMore}
            onRetry={retry}
            onRefresh={refresh}
            onExit={() => {
              onStatsChange();
              setMode("menu");
            }}
          />
        </main>
      </ErrorBoundary>
    );
  }

  if (mode === "higher") {
    return (
      <ErrorBoundary fallback={<div className="p-8 text-center">Something went wrong</div>}>
        <main className="min-h-screen bg-surface-deep">
          <HigherLower
            deck={deck}
            playerName={active.name}
            playerEmoji={active.emoji}
            initialBestStreak={getStats(active.name).bestStreak}
            poolStatus={poolStatus}
            hasMore={hasMore}
            onNeedMore={loadMore}
            onRetry={retry}
            onRefresh={refresh}
            onExit={() => {
              onStatsChange();
              setMode("menu");
            }}
          />
        </main>
      </ErrorBoundary>
    );
  }

  // ---- Menu + leaderboard ----
  return (
    <ErrorBoundary fallback={<div className="p-8 text-center">Something went wrong</div>}>
      <Menu
        active={active}
        players={players}
        statsVersion={statsVersion}
        poolCount={deck.length}
        poolStatus={poolStatus}
        onRetry={retry}
        onPlay={setMode}
        onSwitchPlayer={() => {
          setActivePlayerName(null);
          setActive(null);
        }}
      />
    </ErrorBoundary>
  );
}

function Menu({
  active,
  players,
  statsVersion,
  poolCount,
  poolStatus,
  onRetry,
  onPlay,
  onSwitchPlayer,
}: {
  active: KidPlayer;
  players: KidPlayer[];
  statsVersion: number;
  poolCount: number;
  poolStatus: PlayPoolStatus;
  onRetry: () => void;
  onPlay: (m: Mode) => void;
  onSwitchPlayer: () => void;
}) {
  // Leaderboard: rating COUNT is the score; crown the leader.
  const board = useMemo(() => {
    const stats = getAllStats();
    return players
      .map((p) => ({ p, s: stats[kidSlug(p.name)] || { rated: 0, bestStreak: 0 } }))
      .sort((a, b) => b.s.rated - a.s.rated);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [players, statsVersion]);

  const topRated = board.length > 0 ? board[0].s.rated : 0;

  return (
    <main className="min-h-screen bg-surface-deep px-5 py-8">
      <div className="mx-auto max-w-md">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <span className="text-4xl">{active.emoji}</span>
            <div>
              <div className="text-xl font-black text-text-primary">Hi, {active.name}!</div>
              <div className="text-xs text-text-muted" role="status" aria-live="polite">
                {poolStatus === "loading" && poolCount === 0
                  ? "Loading cards…"
                  : poolStatus === "error" && poolCount === 0
                    ? "Couldn't load cards"
                    : `${poolCount} cards ready`}
              </div>
            </div>
          </div>
          {poolStatus === "error" && poolCount === 0 ? (
            <button
              onClick={onRetry}
              className="text-sm font-bold text-accent-brand px-2 py-2"
              aria-label="Retry loading cards"
            >
              Retry
            </button>
          ) : (
            <button
              onClick={onSwitchPlayer}
              className="text-sm font-bold text-accent-brand px-2 py-2"
            >
              Switch
            </button>
          )}
        </div>

        <div className="grid gap-4">
          <button
            onClick={() => onPlay("cool")}
            className="rounded-3xl border-2 border-surface-border bg-surface-card p-6 text-left shadow-sm active:scale-[0.98] transition-transform"
            style={{ minHeight: 120 }}
          >
            <div className="text-4xl mb-2">😎😴</div>
            <div className="text-2xl font-black text-text-primary">Cool or Boring?</div>
            <div className="text-text-secondary">Swipe through real predictions — 👍 or 👎!</div>
          </button>

          <button
            onClick={() => onPlay("higher")}
            className="rounded-3xl border-2 border-surface-border bg-surface-card p-6 text-left shadow-sm active:scale-[0.98] transition-transform"
            style={{ minHeight: 120 }}
          >
            <div className="text-4xl mb-2">⬆️⬇️</div>
            <div className="text-2xl font-black text-text-primary">Higher or Lower?</div>
            <div className="text-text-secondary">Guess the odds and build a streak!</div>
          </button>
        </div>

        {/* Leaderboard */}
        <div className="mt-8 rounded-3xl border-2 border-surface-border bg-surface-card p-5">
          <div className="font-black text-text-primary mb-3">🏆 Scoreboard</div>
          {board.length === 0 ? (
            <div className="text-sm text-text-muted">Play a game to get on the board!</div>
          ) : (
            <div className="space-y-2">
              {board.map(({ p, s }, i) => (
                <div
                  key={kidSlug(p.name)}
                  className="flex items-center gap-3 rounded-2xl bg-surface-elevated px-4 py-3"
                >
                  <span className="text-2xl">{p.emoji}</span>
                  <span className="font-bold text-text-primary flex-1">{p.name}</span>
                  <span className="text-sm text-text-secondary">
                    {s.rated} rated · 🔥 {s.bestStreak}
                  </span>
                  {i === 0 && s.rated > 0 && s.rated === topRated && <span className="text-xl">👑</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
