"use client";

// GUESS THE CHANCE — the game itself. See `page.tsx` for what the page is and
// is not. This file is the screens and the state; every rule (scoring, the
// line after a card, the chance of winning, the link) lives in `lib/guess/`
// and is tested there.
//
// THREE STEPS, EASIEST FIRST (430: A). Five taps (above or below 50%, which is
// more likely), then five picks out of four, then five sliders. Each step is
// scored on its own as well as in the total, each can be sent on its own, and
// the time a player takes is shown beside the score and never added to it.
//
// What playtesting asked for, and where it is:
//   • a name before the first card                      → Home
//   • a board that is always there, with each player's
//     chance of winning                                 → Board
//   • a line about whoever was farthest or dead on      → lib/guess/roast.ts
//   • five faces to rate the line, not two              → the reveal
//   • a little context with every answer                → the reveal
//   • "which of these were good?" after each step       → the step screen
//   • the group against the Coin, and "without ___"     → Results
//   • charts of the game at the end                     → Results
//   • something to play against when you are first      → the Coin
//   • easy, medium and hard, and a score for each       → the step screen, Results

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import BainLuckMark from "@/components/BainLuckMark";
import {
  cleanName,
  coinEntry,
  COIN_NAME,
  emptyEntry,
  FOUR_WAY_POINTS,
  FULL_POINTS,
  fullPoints,
  guessLabel,
  isTap,
  isValidGuess,
  joinNames,
  kindLabel,
  MAX_CARD_SECONDS,
  pointsByCard,
  pointsFor,
  standings,
  startGuess,
  stepIsTaps,
  stepMax,
  stepOf,
  stepScore,
  stepScoreLabel,
  stepWins,
  tapNote,
  timeLabel,
  TOGETHER_NAME,
  togetherReport,
  TWO_WAY_POINTS,
  topicWins,
  totalPoints,
} from "@/lib/guess/engine";
import { decodeGroup, encodeGroup, mergeFromLink, shareMessage, stepShareMessage, uniqueName } from "@/lib/guess/link";
import { roastHistory } from "@/lib/guess/roast";
import { LATEST_PACK } from "@/lib/guess/packs";
import { clearGame, loadGame, saveGame, type Phase, type SavedGame } from "@/lib/guess/storage";
import type { GamePack, PackCard, PlayerEntry, RoastLine } from "@/lib/guess/types";
import { winChanceHistory, winChances } from "@/lib/guess/winChance";

import CardFace, { tintFor } from "./CardFace";
import CardReveal, { type RevealSlot } from "./CardReveal";
import { LineChart, type ChartSeries } from "./GameCharts";

const DOTS = [
  "bg-emerald-600",
  "bg-violet-600",
  "bg-amber-500",
  "bg-sky-600",
  "bg-rose-500",
  "bg-teal-600",
  "bg-fuchsia-600",
  "bg-orange-500",
];
const LINES = [
  "text-emerald-600",
  "text-violet-600",
  "text-amber-500",
  "text-sky-600",
  "text-rose-500",
  "text-teal-600",
  "text-fuchsia-600",
  "text-orange-500",
];
const HOUSE_DOT = "bg-text-muted";
const HOUSE_LINE = "text-text-muted";

const FACES: { emoji: string; label: string }[] = [
  { emoji: "😐", label: "No" },
  { emoji: "🙂", label: "Okay" },
  { emoji: "😄", label: "Good" },
  { emoji: "😂", label: "Funny" },
  { emoji: "💀", label: "Too good" },
];

const MAX_HERE = 6;
const CHART_LINES = 8;

interface Game {
  phase: Phase;
  index: number;
  turn: number;
  here: PlayerEntry[];
  link: PlayerEntry[];
}

const FRESH: Game = { phase: "home", index: 0, turn: 0, here: [], link: [] };

const PRIMARY =
  "min-h-[52px] w-full rounded-2xl bg-text-primary px-5 text-base font-black text-white transition-transform active:scale-95 disabled:opacity-40";
const QUIET =
  "min-h-[44px] rounded-2xl border-2 border-surface-border bg-surface-card px-4 text-sm font-bold text-text-primary active:scale-95";
const PANEL = "rounded-3xl border-2 border-surface-border bg-surface-card p-4";

// The chance of winning is an estimate from played-out games, so
// it never prints a flat 0% or 100% while cards are still to come.
function percent(value: number): string {
  if (value >= 0.995) return "99%+";
  if (value < 0.005) return "<1%";
  return `${Math.round(value * 100)}%`;
}

// ---------------------------------------------------------------------------

interface BoardRow {
  name: string;
  points: number;
  chance: number | null;
  dot: string;
  /** True for the player whose guess this is, when several people share the phone. */
  turn: boolean;
}

/** The board that is always there: every player's points, and our estimate of their chance to win. */
function Board({ rows }: { rows: BoardRow[] }) {
  if (rows.length === 0) return null;
  return (
    <ol
      className="sticky top-14 z-40 -mx-1 flex gap-1.5 overflow-x-auto bg-surface-deep px-1 py-1.5"
      data-testid="board"
      aria-label="The board"
    >
      {rows.map((row) => (
        <li
          key={row.name}
          className={`flex shrink-0 items-center gap-1.5 rounded-full border-2 bg-surface-card py-1 pl-2 pr-3 ${
            row.turn ? "border-text-primary" : "border-surface-border"
          }`}
          data-turn={row.turn ? "yes" : undefined}
        >
          <span className={`h-2.5 w-2.5 rounded-full ${row.dot}`} aria-hidden="true" />
          <span className="max-w-[84px] truncate text-sm font-bold text-text-primary">{row.name}</span>
          <span className="text-sm font-black tabular-nums text-text-primary">{row.points}</span>
          {row.chance !== null && <span className="text-xs font-bold tabular-nums text-text-secondary">{percent(row.chance)}</span>}
        </li>
      ))}
    </ol>
  );
}

function Header({ pack, right }: { pack: GamePack; right: string }) {
  return (
    <header className="mb-1 flex items-center justify-between">
      <div className="flex items-center gap-2">
        <BainLuckMark size={26} />
        <span className="whitespace-nowrap text-sm font-black text-text-primary">Guess the Chance</span>
      </div>
      <span className="min-w-0 text-right text-xs font-bold text-text-secondary" data-testid="progress">
        {right || `as of ${pack.asOf}`}
      </span>
    </header>
  );
}

interface StepRow {
  name: string;
  dot: string;
  /** True for someone whose game came in the link. */
  earlier: boolean;
  /** Each step's score as the player reads it: "4 of 5", or points. */
  labels: string[];
  /** Seconds spent deciding in each step; 0 when not timed (the Coin, an older link). */
  times: number[];
  total: number;
  /** Our estimate of this player's chance to finish first, or null when it is not shown. */
  chance: number | null;
}

/** Every player's score step by step. `shown` is how many steps have been played. */
function StepTable({ pack, rows, shown }: { pack: GamePack; rows: StepRow[]; shown: number }) {
  const steps = pack.steps.slice(0, shown);
  return (
    <div className={`${PANEL} overflow-x-auto`} data-testid="step-table">
      <table className="w-full text-left">
        <thead>
          <tr className="text-xs font-black uppercase tracking-wide text-text-secondary">
            <th className="pb-1 font-black">Step by step</th>
            {steps.map((step) => (
              <th key={step.name} className="pb-1 text-right font-black">
                {step.name}
              </th>
            ))}
            {shown > 1 && <th className="pb-1 text-right font-black">Total</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.name} className="border-t border-surface-border align-top">
              <td className="py-1.5 pr-2">
                <span className="flex items-center gap-1.5">
                  <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${row.dot}`} aria-hidden="true" />
                  <span className="max-w-[96px] truncate text-sm font-bold text-text-primary">{row.name}</span>
                </span>
                {row.earlier && <span className="block pl-4 text-xs text-text-secondary">played earlier</span>}
                {row.chance !== null && <span className="block pl-4 text-xs tabular-nums text-text-secondary">{percent(row.chance)} to win</span>}
              </td>
              {steps.map((step, s) => (
                <td key={step.name} className="py-1.5 pl-1 text-right">
                  <span className="block whitespace-nowrap text-sm font-black tabular-nums text-text-primary">{row.labels[s]}</span>
                  {row.times[s] > 0 && <span className="block text-xs tabular-nums text-text-secondary">{timeLabel(row.times[s])}</span>}
                </td>
              ))}
              {shown > 1 && <td className="py-1.5 pl-1 text-right text-sm font-black tabular-nums text-text-primary">{row.total}</td>}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-sm text-text-secondary">
        The time is how long you took to decide. It is not part of the score.
        {rows.some((row) => row.chance !== null) && " The chance to win is our estimate, from the cards so far."}
      </p>
    </div>
  );
}

/** The message to send, with a button to share it and one to copy it. */
function SharePanel({ message, canShare, testId }: { message: string; canShare: boolean; testId: string }) {
  const [copied, setCopied] = useState<"" | "yes" | "select">("");
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message);
      setCopied("yes");
    } catch {
      setCopied("select");
    }
  };
  const share = async () => {
    try {
      await navigator.share({ text: message });
    } catch {
      // The person closed the share sheet. Nothing to do.
    }
  };
  return (
    <div data-testid={testId}>
      <textarea
        readOnly
        value={message}
        rows={4}
        onFocus={(e) => e.currentTarget.select()}
        data-testid={`${testId}-text`}
        aria-label="The message to send"
        className="mt-2 w-full rounded-2xl border-2 border-surface-border bg-surface-elevated p-3 text-sm text-text-primary [overflow-wrap:anywhere]"
      />
      <div className="mt-2 flex gap-2">
        {canShare && (
          <button type="button" className={PRIMARY} onClick={share} data-testid={`${testId}-share`}>
            Share
          </button>
        )}
        <button type="button" className={canShare ? QUIET : PRIMARY} onClick={copy} data-testid={`${testId}-copy`}>
          {copied === "yes" ? "Copied" : "Copy"}
        </button>
      </div>
      {copied === "select" && <p className="mt-2 text-sm text-text-secondary">Copying is blocked here. Tap the message, select all, and copy it.</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------

export default function ChanceGame({ pack }: { pack: GamePack }) {
  const [game, setGame] = useState<Game>(FRESH);
  const [saved, setSaved] = useState<SavedGame | null>(null);
  const [linkNote, setLinkNote] = useState<"" | "other-edition" | "unreadable">("");
  const [names, setNames] = useState<string[]>([]);
  const [nameDraft, setNameDraft] = useState("");
  const [draftState, setDraftState] = useState<{ at: string; value: number | null }>({ at: "", value: null });
  const [goodDraft, setGoodDraft] = useState<boolean[]>([]);
  const [canShare, setCanShare] = useState(false);
  // When the card in front of the current player was shown, to time the decision.
  const shownAt = useRef<{ at: string; time: number }>({ at: "", time: 0 });

  const total = pack.cards.length;
  const coin = useMemo(() => coinEntry(pack), [pack]);

  // Read the link and anything kept on this phone, once, after the first paint.
  useEffect(() => {
    const decoded = decodeGroup(pack, window.location.hash);
    const fromLink = decoded.ok ? decoded.players : [];
    if (!decoded.ok && decoded.reason !== "none") setLinkNote(decoded.reason);
    const stored = loadGame(pack);
    if (stored && stored.phase !== "home") {
      const extra = mergeFromLink([...stored.here, ...stored.link], fromLink);
      setSaved({ ...stored, link: [...stored.link, ...extra] });
    }
    setGame((g) => ({ ...g, link: fromLink }));
    setCanShare(typeof navigator !== "undefined" && typeof navigator.share === "function");
  }, [pack]);

  useEffect(() => {
    if (game.phase !== "home") saveGame({ packId: pack.id, ...game });
  }, [game, pack.id]);

  const card: PackCard = pack.cards[Math.min(game.index, total - 1)];
  const step = stepOf(pack, Math.min(game.index, total - 1));
  const people = useMemo(() => [...game.link, ...game.here], [game.link, game.here]);
  const coinOn = people.length <= 2;
  const board = useMemo(() => (coinOn ? [...people, coin] : people), [coinOn, people, coin]);
  const done = game.phase === "play" || game.phase === "home" ? game.index : game.phase === "results" ? total : game.index + 1;

  const dotOf = useCallback(
    (name: string) => {
      const i = people.findIndex((p) => p.name === name);
      return i < 0 ? HOUSE_DOT : DOTS[i % DOTS.length];
    },
    [people],
  );

  const chances = useMemo(() => winChances(pack, board, done), [pack, board, done]);

  const rows: BoardRow[] = useMemo(() => {
    const chanceOf = new Map(board.map((entry, i) => [entry.name, chances[i]]));
    return standings(pack, board, done).map((s) => ({
      name: s.entry.name,
      points: s.points,
      chance: board.length > 1 && done < total ? (chanceOf.get(s.entry.name) ?? null) : null,
      dot: s.entry.from === "house" ? HOUSE_DOT : dotOf(s.entry.name),
      turn: game.phase === "play" && game.here.length > 1 && game.here[game.turn]?.name === s.entry.name,
    }));
  }, [pack, board, chances, done, dotOf, total, game.phase, game.here, game.turn]);

  // Every player's score step by step, in the order of the board.
  const stepRows: StepRow[] = useMemo(() => {
    const chanceOf = new Map(rows.map((row) => [row.name, row.chance]));
    return standings(pack, board, done).map((s) => ({
      name: s.entry.name,
      dot: s.entry.from === "house" ? HOUSE_DOT : dotOf(s.entry.name),
      earlier: s.entry.from === "link",
      labels: pack.steps.map((_, i) => stepScoreLabel(pack, s.entry, i)),
      times: pack.steps.map((_, i) => s.entry.times[i] ?? 0),
      total: s.points,
      chance: chanceOf.get(s.entry.name) ?? null,
    }));
  }, [pack, board, done, dotOf, rows]);

  const line: RoastLine | null = useMemo(() => {
    if (game.phase !== "reveal") return null;
    const history = roastHistory(pack, game.index, people, coinOn ? coin : null);
    return history[game.index] ?? null;
  }, [pack, game.phase, game.index, people, coinOn, coin]);

  // A slider starts in the middle and a tap card with nothing tapped. The guess
  // being made belongs to one card and one turn, so a new card or a new player
  // never inherits the last one.
  const draftAt = `${card.id}:${game.turn}`;
  const draft = draftState.at === draftAt ? draftState.value : startGuess(card);
  const setDraft = useCallback((value: number) => setDraftState({ at: draftAt, value }), [draftAt]);
  const ready = isValidGuess(card, draft);

  // The clock for a decision starts when the card is in front of the player.
  useEffect(() => {
    if (game.phase === "play" && shownAt.current.at !== draftAt) shownAt.current = { at: draftAt, time: Date.now() };
  }, [game.phase, draftAt]);

  // ---- actions -------------------------------------------------------------

  const addName = useCallback(() => {
    const clean = cleanName(nameDraft);
    if (!clean || names.length >= MAX_HERE) return;
    const taken = new Set([...names, ...game.link.map((p) => p.name), COIN_NAME, TOGETHER_NAME].map((n) => n.toLowerCase()));
    setNames((all) => [...all, uniqueName(clean, taken)]);
    setNameDraft("");
  }, [nameDraft, names, game.link]);

  const start = useCallback(() => {
    const pending = cleanName(nameDraft);
    const taken = new Set([...names, ...game.link.map((p) => p.name), COIN_NAME, TOGETHER_NAME].map((n) => n.toLowerCase()));
    const all = pending && names.length < MAX_HERE ? [...names, uniqueName(pending, taken)] : names;
    if (all.length === 0) return;
    setNameDraft("");
    setGame((g) => ({ phase: "play", index: 0, turn: 0, here: all.map((n) => emptyEntry(pack, n, "here")), link: g.link }));
  }, [nameDraft, names, game.link, pack]);

  const carryOn = useCallback(() => {
    if (!saved) return;
    setGame({ phase: saved.phase, index: saved.index, turn: saved.turn, here: saved.here, link: saved.link });
    setSaved(null);
  }, [saved]);

  const startOver = useCallback(() => {
    clearGame(pack.id);
    setSaved(null);
    setNames([]);
    setGame((g) => ({ ...FRESH, link: g.link }));
  }, [pack.id]);

  // From the results: the people who just played become "played earlier", so a
  // second group at the same table plays against the first.
  const playAgain = useCallback(() => {
    clearGame(pack.id);
    setSaved(null);
    setNames([]);
    setGame((g) => ({
      ...FRESH,
      link: [...g.link, ...g.here.filter((p) => p.guesses.some((v) => v !== null)).map((p) => ({ ...p, from: "link" as const }))],
    }));
    window.scrollTo(0, 0);
  }, [pack.id]);

  const lockIn = useCallback(() => {
    if (draft === null || !isValidGuess(card, draft)) return;
    const waited = shownAt.current.at === draftAt ? (Date.now() - shownAt.current.time) / 1000 : 0;
    const seconds = Math.max(0, Math.min(MAX_CARD_SECONDS, Math.round(waited * 10) / 10));
    setGame((g) => {
      const inStep = stepOf(pack, g.index);
      const here = g.here.map((p, i) =>
        i === g.turn
          ? {
              ...p,
              guesses: p.guesses.map((v, c) => (c === g.index ? draft : v)),
              times: p.times.map((t, s) => (s === inStep ? t + seconds : t)),
            }
          : p,
      );
      if (g.turn < g.here.length - 1) return { ...g, here, turn: g.turn + 1 };
      return { ...g, here, turn: 0, phase: "reveal" };
    });
  }, [draft, card, draftAt, pack]);

  const next = useCallback(
    (rating: number) => {
      setGame((g) => {
        const here = g.here.map((p, i) => (i === 0 && rating > 0 ? { ...p, ratings: p.ratings.map((v, c) => (c === g.index ? rating : v)) } : p));
        if ((g.index + 1) % pack.perRound === 0) return { ...g, here, phase: "round" };
        return { ...g, here, index: g.index + 1, phase: "play", turn: 0 };
      });
      window.scrollTo(0, 0);
    },
    [pack.perRound],
  );

  const roundStart = Math.floor(game.index / pack.perRound) * pack.perRound;
  useEffect(() => {
    if (game.phase === "round") setGoodDraft(pack.cards.map(() => false));
  }, [game.phase, pack.cards]);

  const leaveRound = useCallback(() => {
    setGame((g) => {
      const here = g.here.map((p, i) => (i === 0 ? { ...p, good: p.good.map((v, c) => v || goodDraft[c] === true) } : p));
      if (g.index + 1 >= total) return { ...g, here, phase: "results" };
      return { ...g, here, index: g.index + 1, phase: "play", turn: 0 };
    });
    window.scrollTo(0, 0);
  }, [goodDraft, total]);

  const voteFun = useCallback((which: number) => {
    setGame((g) => ({ ...g, here: g.here.map((p, i) => (i === 0 ? { ...p, fun: p.fun === which ? 0 : which } : p)) }));
  }, []);

  const url = typeof window === "undefined" ? "" : `${window.location.origin}/guess#${encodeGroup(pack, people)}`;

  // ---- screens -------------------------------------------------------------

  if (game.phase === "home") {
    const earlier = game.link.map((p) => p.name);
    return (
      <div className="px-1 pb-4">
        <div className="mx-auto max-w-md space-y-4">
          <div className="pt-4 text-center">
            <div className="mb-2 inline-flex items-center justify-center gap-2 text-5xl">
              <BainLuckMark size={44} />
              <span aria-hidden="true">🎲</span>
            </div>
            <h1 className="text-3xl font-black text-text-primary">Guess the Chance</h1>
            <p className="mt-1 text-base text-text-secondary">
              {total} cards in {pack.steps.length} steps. Guess what the world thinks will happen.
            </p>
          </div>

          {pack.id !== LATEST_PACK.id && (
            <p className={`${PANEL} text-sm font-semibold text-text-primary`} data-testid="set-note">
              You are playing the set this link was made on, so you can compare with everyone in it.{" "}
              <a href="/guess" className="font-black text-accent-brand underline">
                Play today&apos;s cards
              </a>
            </p>
          )}
          {linkNote === "other-edition" && (
            <p className={`${PANEL} text-sm font-semibold text-text-primary`} data-testid="link-note">
              That link is from an earlier set of cards. This is the current set, so you start a new group.
            </p>
          )}
          {linkNote === "unreadable" && (
            <p className={`${PANEL} text-sm font-semibold text-text-primary`} data-testid="link-note">
              That link did not come through whole, so nobody else&apos;s guesses are loaded. Ask for it again, or play and send your own.
            </p>
          )}

          {earlier.length > 0 && (
            <div className={PANEL} data-testid="earlier-players">
              <div className="text-sm font-black text-text-primary">
                {joinNames(earlier)} {earlier.length === 1 ? "has" : "have"} already played.
              </div>
              <p className="mt-1 text-sm text-text-secondary">You see their guess on each card after you lock in yours.</p>
            </div>
          )}

          {saved && (
            <div className={PANEL} data-testid="saved-game">
              <div className="text-sm font-black text-text-primary">
                A game for {joinNames(saved.here.map((p) => p.name))} is waiting on this phone.
              </div>
              <div className="mt-3 flex gap-2">
                <button type="button" className={PRIMARY} onClick={carryOn} data-testid="carry-on">
                  Carry on
                </button>
                <button type="button" className={QUIET} onClick={startOver}>
                  Start over
                </button>
              </div>
            </div>
          )}

          <div className={PANEL}>
            <label htmlFor="guess-name" className="text-sm font-black text-text-primary">
              Who is playing on this phone?
            </label>
            {names.length > 0 && (
              <ul className="mt-2 flex flex-wrap gap-2">
                {names.map((n) => (
                  <li key={n} className="flex items-center gap-1 rounded-full bg-surface-elevated py-1 pl-3 pr-1 text-sm font-bold text-text-primary">
                    {n}
                    <button
                      type="button"
                      aria-label={`Remove ${n}`}
                      onClick={() => setNames((all) => all.filter((x) => x !== n))}
                      className="flex h-7 w-7 items-center justify-center rounded-full text-text-secondary"
                    >
                      ✕
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-2 flex gap-2">
              <input
                id="guess-name"
                data-testid="name-input"
                value={nameDraft}
                onChange={(e) => setNameDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") addName();
                }}
                maxLength={12}
                autoComplete="given-name"
                placeholder={names.length === 0 ? "Your first name" : "Another name"}
                className="min-h-[48px] min-w-0 flex-1 rounded-2xl border-2 border-surface-border bg-surface-card px-4 text-base font-bold text-text-primary placeholder:text-text-muted"
              />
              <button type="button" className={QUIET} onClick={addName} disabled={!cleanName(nameDraft) || names.length >= MAX_HERE}>
                Add
              </button>
            </div>
            <p className="mt-2 text-sm text-text-secondary">
              One name to play alone. Add more to pass one phone around. Names stay on this phone and in the link you send.
            </p>
            <button
              type="button"
              className={`${PRIMARY} mt-3`}
              onClick={start}
              disabled={names.length === 0 && !cleanName(nameDraft)}
              data-testid="start-button"
            >
              Start
            </button>
          </div>

          <ol className="space-y-1.5" data-testid="steps">
            {pack.steps.map((info, i) => (
              <li key={info.name} className="flex items-start gap-3 rounded-2xl border-2 border-surface-border bg-surface-card px-3 py-2">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-text-primary text-sm font-black text-white">{i + 1}</span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-black text-text-primary">{info.name}</span>
                  <span className="block text-sm text-text-secondary">{info.how}</span>
                </span>
              </li>
            ))}
          </ol>

          <ul className="space-y-2 text-sm text-text-primary">
            <li className="flex gap-2">
              <span aria-hidden="true">🎯</span>
              <span>
                A right tap is worth {TWO_WAY_POINTS} when there are two to choose from and {FOUR_WAY_POINTS} when there are four. A slider is worth{" "}
                {FULL_POINTS} for dead on, and less the further off you are.
              </span>
            </li>
            <li className="flex gap-2">
              <span aria-hidden="true">🪙</span>
              <span>The Coin plays too. It flips for every tap and leaves every slider in the middle. Beat it.</span>
            </li>
            <li className="flex gap-2">
              <span aria-hidden="true">🔗</span>
              <span>After any step you can send a link. Whoever opens it plays the same cards against you.</span>
            </li>
          </ul>
          <p className="pb-6 text-center text-sm text-text-secondary">Numbers as of {pack.asOf}.</p>
        </div>
      </div>
    );
  }

  const tint = tintFor(card.topic);
  const inStep = (game.index % pack.perRound) + 1;
  // The play screen has to fit a phone with the answer in view above the Lock in
  // button, so the head is kept short: tags, the place in the step, the sentence.
  const cardHead = (answered: boolean) => (
    <div>
      {!answered && (
        <div className="mb-2 flex items-center gap-1.5">
          <span className="shrink-0 whitespace-nowrap rounded-full bg-text-primary px-2.5 py-1 text-xs font-black uppercase tracking-wide text-white">
            {kindLabel(card)}
          </span>
          <span className={`min-w-0 truncate rounded-full px-2.5 py-1 text-xs font-black uppercase tracking-wide ${tint.chip}`}>{card.topic}</span>
          <span className="ml-auto shrink-0 text-sm font-bold tabular-nums text-text-secondary" data-testid="progress">
            {pack.steps[step].name} {inStep} of {pack.perRound}
          </span>
        </div>
      )}
      <h2
        className={`font-black leading-tight text-text-primary ${answered ? "text-lg" : card.prompt.length > 36 ? "text-xl" : "text-2xl"}`}
        data-testid="prompt"
      >
        {card.prompt}
      </h2>
      {card.sub && !answered && <p className="mt-1 text-sm font-semibold text-text-secondary">{card.sub}</p>}
    </div>
  );

  if (game.phase === "play") {
    const who = game.here[game.turn];
    const earlier = game.link.filter((p) => p.guesses[game.index] !== null).map((p) => p.name);
    // A tap card has nothing to lock in until something is tapped.
    const action = ready ? `lock in ${guessLabel(card, draft)}` : "tap your answer";
    const lockLabel = game.here.length > 1 ? `${who.name}: ${action}` : `${action.charAt(0).toUpperCase()}${action.slice(1)}`;
    return (
      <div className="px-1 pb-4">
        <div className="mx-auto max-w-md">
          <Board rows={rows} />
          <section className={`${PANEL} mt-2 space-y-3`} data-testid="card" data-kind={card.kind} data-flavor={card.flavor}>
            {cardHead(false)}
            <CardFace key={`${card.id}:${game.turn}`} card={card} value={draft} onChange={setDraft} />
          </section>
          <div className="sticky bottom-20 z-30 mt-3 md:bottom-4">
            <button
              type="button"
              className={`${PRIMARY} flex items-center justify-center gap-2 shadow-lg`}
              onClick={lockIn}
              disabled={!ready}
              data-testid="lock-button"
            >
              {game.here.length > 1 && <span className={`h-3 w-3 shrink-0 rounded-full border-2 border-white ${dotOf(who.name)}`} aria-hidden="true" />}
              <span data-testid="lock-label">{lockLabel}</span>
            </button>
          </div>
          <details className="mt-3 rounded-2xl border-2 border-surface-border bg-surface-card px-3 py-2 text-sm text-text-primary">
            <summary className="min-h-[28px] cursor-pointer font-bold">What is this about?</summary>
            <p className="mt-1 text-text-secondary">{card.context}</p>
          </details>
          {earlier.length > 0 && (
            <p className="mt-3 text-center text-sm text-text-secondary">
              {joinNames(earlier)} played this card earlier. You see {earlier.length === 1 ? "that guess" : "those guesses"} after you lock in.
            </p>
          )}
        </div>
      </div>
    );
  }

  if (game.phase === "reveal") {
    const slots: RevealSlot[] = board
      .filter((entry) => entry.guesses[game.index] !== null)
      .map((entry) => ({
        name: entry.name,
        guess: entry.guesses[game.index] as number,
        points: pointsFor(card, entry.guesses[game.index]),
        dot: entry.from === "house" ? HOUSE_DOT : dotOf(entry.name),
        house: entry.from === "house",
      }))
      .sort((a, b) => b.points - a.points);
    const lastOfRound = (game.index + 1) % pack.perRound === 0;
    const nextWord = lastOfRound ? `See how ${pack.steps[step].name} went` : "Next card";
    const answered = people.filter((p) => p.guesses[game.index] !== null);
    const note = isTap(card)
      ? tapNote(
          answered.map((p) => p.name),
          answered.map((p) => pointsFor(card, p.guesses[game.index]) === fullPoints(card)),
        )
      : "";
    return (
      <div className="px-1 pb-4">
        <div className="mx-auto max-w-md">
          <Board rows={rows} />
          <section className={`${PANEL} mt-2 space-y-3`} data-testid="reveal" data-kind={card.kind} data-flavor={card.flavor}>
            {cardHead(true)}
            <CardReveal card={card} slots={slots} />
            {note && (
              <p className="text-center text-base font-black text-text-primary" data-testid="tap-note">
                {note}
              </p>
            )}
            {/* A tap card's answer already shows who tapped what, so the chips are for sliders. */}
            <ul className={isTap(card) ? "hidden" : "flex flex-wrap gap-1.5"} data-testid="slots">
              {slots.map((slot) => (
                <li key={slot.name} className="flex items-center gap-1.5 rounded-full bg-surface-elevated py-1 pl-2 pr-2.5 text-sm">
                  <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${slot.dot}`} aria-hidden="true" />
                  <span className="font-black text-text-primary">{slot.name}</span>
                  <span className="text-text-secondary">{guessLabel(card, slot.guess)}</span>
                  <span className="font-black tabular-nums text-text-primary">+{slot.points}</span>
                </li>
              ))}
            </ul>
            <p className="text-sm leading-snug text-text-secondary" data-testid="context">
              {card.context}
            </p>
            {line ? (
              <div className="space-y-3">
                <p className="rounded-2xl bg-text-primary px-4 py-3 text-base font-bold leading-snug text-white" data-testid="line" data-rule={line.rule}>
                  {line.text}
                </p>
                <div>
                  <div className="mb-1.5 text-center text-sm font-bold text-text-secondary">How was that line? Tap one to go on.</div>
                  <div className="grid grid-cols-5 gap-1.5">
                    {FACES.map((face, i) => (
                      <button
                        key={face.label}
                        type="button"
                        onClick={() => next(i + 1)}
                        data-testid={`rate-${i + 1}`}
                        className="flex min-h-[56px] flex-col items-center justify-center rounded-2xl border-2 border-surface-border bg-surface-card active:scale-95"
                      >
                        <span className="text-2xl" aria-hidden="true">
                          {face.emoji}
                        </span>
                        <span className="text-xs font-bold text-text-secondary">{face.label}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <button type="button" className={PRIMARY} onClick={() => next(0)} data-testid="next-button">
                {nextWord}
              </button>
            )}
          </section>
        </div>
      </div>
    );
  }

  if (game.phase === "round") {
    const steps = pack.steps.length;
    const last = game.index + 1 >= total;
    const info = pack.steps[step];
    const taps = stepIsTaps(pack, step);
    const mine = game.here.map((p) => ({ name: p.name, label: stepScoreLabel(pack, p, step), points: stepScore(pack, p, step).points }));
    const headline =
      game.here.length === 1
        ? taps
          ? `You got ${mine[0].label}.`
          : `You scored ${mine[0].label} of ${stepMax(pack, step)}.`
        : `${info.name} is done.`;
    const stepMessage = stepShareMessage(info.name, taps, stepMax(pack, step), mine, url);
    return (
      <div className="px-1 pb-4">
        <div className="mx-auto max-w-md space-y-4" data-testid="step-end" data-step={step + 1}>
          <Header pack={pack} right={`Step ${step + 1} of ${steps}`} />
          <div>
            <div className="text-sm font-black uppercase tracking-wide text-text-secondary">{info.name}</div>
            <h2 className="text-2xl font-black text-text-primary" data-testid="step-headline">
              {headline}
            </h2>
          </div>
          <StepTable pack={pack} rows={stepRows} shown={step + 1} />
          <section className={PANEL} data-testid="good-cards">
            <div className="text-sm font-black text-text-primary">Which of these were good? Tap any you liked.</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {pack.cards.slice(roundStart, roundStart + pack.perRound).map((c, offset) => {
                const i = roundStart + offset;
                const on = goodDraft[i] === true;
                return (
                  <button
                    key={c.id}
                    type="button"
                    aria-pressed={on}
                    onClick={() => setGoodDraft((all) => all.map((v, k) => (k === i ? !v : v)))}
                    className={`min-h-[44px] rounded-2xl border-2 px-3 text-left text-sm font-bold active:scale-95 ${
                      on ? "border-text-primary bg-text-primary text-white" : "border-surface-border bg-surface-card text-text-primary"
                    }`}
                  >
                    <span aria-hidden="true">{c.emoji}</span> {c.short}
                  </button>
                );
              })}
            </div>
          </section>
          <button type="button" className={PRIMARY} onClick={leaveRound} data-testid="round-button">
            {last ? "See how it ended" : `On to ${pack.steps[step + 1].name}`}
          </button>
          {!last && <p className="-mt-2 text-center text-sm text-text-secondary">{pack.steps[step + 1].how}</p>}
          {!last && (
            <details className="rounded-2xl border-2 border-surface-border bg-surface-card px-3 py-2 text-sm text-text-primary" data-testid="step-share">
              <summary className="min-h-[28px] cursor-pointer font-bold">Send just {info.name} to someone</summary>
              <p className="mt-1 text-text-secondary">They play the same cards and see your answers as they go. You can carry on here either way.</p>
              <SharePanel message={stepMessage} canShare={canShare} testId="step-share-panel" />
            </details>
          )}
        </div>
      </div>
    );
  }

  // ---- results -------------------------------------------------------------

  const final = standings(pack, board, total);
  const winners = final.filter((s) => s.place === 1).map((s) => s.entry.name);
  const coinPoints = totalPoints(pack, coin);
  const report = togetherReport(pack, people);
  const wins = topicWins(pack, people);
  const byStep = stepWins(pack, people);
  const solo = people.length === 1;
  const me = game.here[0];

  const charted = final.slice(0, CHART_LINES).map((s) => s.entry);
  const colorOf = (entry: PlayerEntry) => {
    if (entry.from === "house") return HOUSE_LINE;
    const i = people.findIndex((p) => p.name === entry.name);
    return LINES[(i < 0 ? 0 : i) % LINES.length];
  };
  const pointSeries: ChartSeries[] = charted.map((entry) => {
    const by = pointsByCard(pack, entry);
    const running = [0];
    by.forEach((p) => running.push(running[running.length - 1] + p));
    return { name: entry.name, values: running, color: colorOf(entry), dashed: entry.from === "house" };
  });
  const history = winChanceHistory(pack, board, total);
  const chanceSeries: ChartSeries[] = charted.map((entry) => {
    const at = board.findIndex((b) => b.name === entry.name);
    return { name: entry.name, values: history.map((h) => (h[at] ?? 0) * 100), color: colorOf(entry), dashed: entry.from === "house" };
  });
  const topPoints = Math.max(20, ...pointSeries.map((s) => s.values[s.values.length - 1]));

  const message = shareMessage(
    game.here.map((p) => ({ name: p.name, points: totalPoints(pack, p) })),
    coinPoints,
    url,
    me ? pack.steps.map((info, i) => `${info.name} ${stepScoreLabel(pack, me, i)}`) : [],
  );

  const together = report.together;
  const togetherLine =
    report.together > report.best
      ? `Together you scored ${together}. That is better than any one of you.`
      : report.beat === 0
        ? `Together you scored ${together}. Every one of you did better alone.`
        : `Together you scored ${together}. That beats ${report.beat} of the ${people.length} of you.`;
  const coinLine =
    together > report.coin
      ? `The Coin scored ${report.coin}. Together you beat it by ${together - report.coin}.`
      : together < report.coin
        ? `The Coin scored ${report.coin}. It beat the lot of you by ${report.coin - together}.`
        : `The Coin scored ${report.coin}. A tie with a coin.`;
  const withoutLine = report.without
    ? `Without ${report.without.name}, together you score ${report.without.score}.${
        together <= report.coin && report.without.score > report.coin ? " You would have beaten the Coin." : ""
      }`
    : "";

  return (
    <div className="px-1 pb-4">
      <div className="mx-auto max-w-md space-y-4" data-testid="results">
        <Header pack={pack} right="" />
        <div className="text-center">
          <div className="text-5xl" aria-hidden="true">
            {winners.includes(COIN_NAME) ? "🪙" : "🏆"}
          </div>
          <h2 className="mt-1 text-3xl font-black text-text-primary" data-testid="winner">
            {winners.length === 1 && winners[0] === COIN_NAME
              ? "The Coin wins. Ouch."
              : `${joinNames(winners)} ${winners.length === 1 ? "wins" : "tie for first"}.`}
          </h2>
          {solo && me && (
            <p className="mt-1 text-base text-text-secondary">
              {totalPoints(pack, me) > coinPoints
                ? `You beat a coin flip by ${totalPoints(pack, me) - coinPoints}.`
                : totalPoints(pack, me) < coinPoints
                  ? `A coin flip beat you by ${coinPoints - totalPoints(pack, me)}. It happens to the best.`
                  : "You tied a coin flip."}
            </p>
          )}
        </div>

        <StepTable pack={pack} rows={stepRows} shown={pack.steps.length} />

        <section className={PANEL} data-testid="fun-vote">
          <div className="text-sm font-black text-text-primary">Which step was the most fun?</div>
          <div className="mt-2 grid grid-cols-3 gap-2">
            {pack.steps.map((info, i) => {
              const on = me?.fun === i + 1;
              return (
                <button
                  key={info.name}
                  type="button"
                  aria-pressed={on}
                  onClick={() => voteFun(i + 1)}
                  data-testid={`fun-${i + 1}`}
                  className={`min-h-[48px] rounded-2xl border-2 px-2 text-sm font-black active:scale-95 ${
                    on ? "border-text-primary bg-text-primary text-white" : "border-surface-border bg-surface-card text-text-primary"
                  }`}
                >
                  {info.name}
                </button>
              );
            })}
          </div>
          <p className="mt-2 text-sm text-text-secondary">Your pick travels with the link you send.</p>
        </section>

        <section className={PANEL} data-testid="share">
          <div className="text-sm font-black text-text-primary">{solo ? "You set the bar. Send it." : "Send it on."}</div>
          <p className="mt-1 text-sm text-text-secondary">
            Whoever opens the link plays the same cards and sees your guess after each one. They can send it on, and the link keeps everyone.
          </p>
          <SharePanel message={message} canShare={canShare} testId="share-panel" />
        </section>

        {!solo && (
          <section className={PANEL} data-testid="step-wins">
            <div className="text-sm font-black text-text-primary">Who won each step</div>
            <ul className="mt-2 space-y-1.5">
              {byStep.map((w) => (
                <li key={w.step} className="flex items-start gap-2">
                  <span className="rounded-full bg-text-primary px-2.5 py-1 text-xs font-black uppercase tracking-wide text-white">
                    {pack.steps[w.step].name}
                  </span>
                  <span className="min-w-0 flex-1 text-sm font-bold leading-snug text-text-primary">
                    {w.names.length === 0 ? "Nobody scored" : joinNames(w.names)}
                  </span>
                  {w.names.length > 0 && <span className="shrink-0 text-sm tabular-nums text-text-secondary">{w.points} points</span>}
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className={PANEL} data-testid="topic-wins">
          <div className="text-sm font-black text-text-primary">{solo ? "Where you were sharpest" : "Who won what"}</div>
          <ul className="mt-2 space-y-1.5">
            {wins
              .slice()
              .sort((a, b) => b.average - a.average)
              .map((w) => (
                <li key={w.topic} className="flex items-start gap-2">
                  <span className={`rounded-full px-2.5 py-1 text-xs font-black uppercase tracking-wide ${tintFor(w.topic).chip}`}>{w.topic}</span>
                  <span className="min-w-0 flex-1 text-sm font-bold leading-snug text-text-primary">
                    {solo ? `${Math.max(0, w.average).toFixed(1)} a card` : w.names.length === 0 ? "Nobody scored" : joinNames(w.names)}
                  </span>
                  {!solo && w.names.length > 0 && <span className="shrink-0 text-sm tabular-nums text-text-secondary">{w.average.toFixed(1)} a card</span>}
                </li>
              ))}
          </ul>
        </section>

        {!solo && (
          <section className={PANEL} data-testid="together">
            <div className="text-sm font-black text-text-primary">All of you against the Coin</div>
            <p className="mt-1 text-sm text-text-primary">{togetherLine}</p>
            <p className="mt-1 text-sm text-text-primary">{coinLine}</p>
            {withoutLine && (
              <p className="mt-1 text-sm font-bold text-text-primary" data-testid="without">
                {withoutLine}
              </p>
            )}
            <p className="mt-2 text-sm text-text-secondary">
              &quot;Together&quot; is your most common tap and your average slider on every card, scored as one more player.
            </p>
          </section>
        )}

        <LineChart title="Points, card by card" series={pointSeries} yMax={topPoints} yLabel={(v) => String(Math.round(v))} roundAt={pack.perRound} />
        {board.length > 1 && (
          <LineChart
            title="Chance of winning, card by card"
            note="Our estimate after each card, from the cards played so far."
            series={chanceSeries}
            yMax={100}
            yLabel={(v) => `${Math.round(v)}%`}
            roundAt={pack.perRound}
          />
        )}

        <button type="button" className={QUIET} onClick={playAgain} data-testid="again-button">
          Someone else&apos;s turn on this phone
        </button>
        <p className="pb-6 text-center text-sm text-text-secondary">Numbers as of {pack.asOf}.</p>
      </div>
    </div>
  );
}
