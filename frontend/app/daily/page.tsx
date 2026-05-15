"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  CheckCircle2,
  Clock3,
  Copy,
  RotateCcw,
  Share2,
  Trophy,
  XCircle,
} from "lucide-react";
import { fetchFeed } from "@/lib/api";
import type {
  FeedEventData,
  FeedFuturesData,
  FeedItem,
  FeedResponse,
} from "@/lib/types";
import { trackEvent } from "@/lib/analytics";
import { useEngagementTime, usePageTracking, useScrollDepth } from "@/hooks";

const DAILY_GOAL = 5;
const DAILY_STATE_KEY = "bainluck_daily_state_v1";
const DAILY_META_KEY = "bainluck_daily_meta_v1";

type GuessDirection = "higher" | "lower";

interface DailyQuestion {
  item: FeedItem;
  id: string;
  marketId: number;
  contentType: "event" | "futures";
  title: string;
  subject: string;
  category: string;
  probability: number;
  detailHref: string;
  context: string;
}

interface DailyAnswer {
  questionId: string;
  marketId: number;
  contentType: "event" | "futures";
  title: string;
  subject: string;
  category: string;
  guess: GuessDirection;
  threshold: number;
  actualPct: number;
  correct: boolean;
  answeredAt: string;
}

interface DailyState {
  date: string;
  questionIds: string[];
  answers: DailyAnswer[];
  completedAt?: string;
}

interface DailyMeta {
  streak: number;
  bestStreak: number;
  totalCompleted: number;
  lastCompletedDate: string | null;
}

const EMPTY_META: DailyMeta = {
  streak: 0,
  bestStreak: 0,
  totalCompleted: 0,
  lastCompletedDate: null,
};

function todayKey(): string {
  return new Date().toLocaleDateString("en-CA");
}

function addDays(dateKey: string, days: number): string {
  const date = new Date(`${dateKey}T12:00:00`);
  date.setDate(date.getDate() + days);
  return date.toLocaleDateString("en-CA");
}

function nextMidnightLabel(now = new Date()): string {
  const midnight = new Date(now);
  midnight.setHours(24, 0, 0, 0);
  const diffMs = midnight.getTime() - now.getTime();
  const hours = Math.floor(diffMs / 36e5);
  const minutes = Math.max(0, Math.floor((diffMs % 36e5) / 60000));
  if (hours <= 0) return `${minutes}m`;
  return `${hours}h ${minutes}m`;
}

function getSessionId(): string {
  if (typeof window === "undefined") return "";
  let id = localStorage.getItem("bainluck_session_id");
  if (!id) {
    id = `sess_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem("bainluck_session_id", id);
  }
  return id;
}

function readJson<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key: string, value: unknown) {
  if (typeof window === "undefined") return;
  localStorage.setItem(key, JSON.stringify(value));
}

function questionIdFor(item: FeedItem): string | null {
  if (item.type === "event") return `event-${(item.data as FeedEventData).id}`;
  if (item.type === "futures") return `futures-${(item.data as FeedFuturesData).id}`;
  return null;
}

function categoryLabel(question: DailyQuestion): string {
  return question.category
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function asDailyQuestion(item: FeedItem): DailyQuestion | null {
  const id = questionIdFor(item);
  if (!id) return null;

  if (item.type === "event") {
    const data = item.data as FeedEventData;
    const probability = data.current_odds?.home_probability;
    if (probability == null || probability < 0.05 || probability > 0.95) return null;
    if (data.status === "completed" || data.status === "closed") return null;

    return {
      item,
      id,
      marketId: data.id,
      contentType: "event",
      title: `${data.away_team} vs ${data.home_team}`,
      subject: `${data.home_team} to win`,
      category: data.sport_name || data.sport || "Sports",
      probability,
      detailHref: `/events/${data.id}`,
      context: item.context_summary || item.headline || item.reason || "",
    };
  }

  if (item.type === "futures") {
    const data = item.data as FeedFuturesData;
    const leader = data.top_outcomes?.[0];
    const probability = leader?.probability;
    if (!leader || probability == null || probability < 0.05 || probability > 0.95) return null;
    if (data.resolved || data.status === "closed" || data.status === "resolved") return null;

    return {
      item,
      id,
      marketId: data.id,
      contentType: "futures",
      title: data.name,
      subject: leader.name,
      category: data.sport_name || data.llm_sport_category || "Markets",
      probability,
      detailHref: `/futures/${data.id}`,
      context: item.context_summary || item.headline || item.reason || data.hook_description || "",
    };
  }

  return null;
}

function hashString(value: string): number {
  let hash = 2166136261;
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function deterministicThreshold(question: DailyQuestion, dateKey: string): number {
  const seed = hashString(`${dateKey}:${question.id}`);
  const actual = question.probability;
  const goHigher = seed % 2 === 0;
  const offset = 0.12 + ((seed % 1000) / 1000) * 0.13;
  let threshold = goHigher ? actual + offset : actual - offset;
  threshold = Math.max(0.05, Math.min(0.95, threshold));

  if (Math.abs(threshold - actual) < 0.1) {
    threshold = goHigher ? actual - offset : actual + offset;
    threshold = Math.max(0.05, Math.min(0.95, threshold));
  }

  let pct = Math.round(threshold * 100);
  const actualPct = Math.round(actual * 100);
  if (pct === actualPct) pct = actualPct >= 50 ? pct - 1 : pct + 1;
  return Math.max(5, Math.min(95, pct));
}

function curateQuestions(response: FeedResponse | null, state: DailyState | null): DailyQuestion[] {
  const questions = (response?.items ?? [])
    .map(asDailyQuestion)
    .filter((question): question is DailyQuestion => question !== null);

  if (!state?.questionIds.length) {
    return questions.slice(0, DAILY_GOAL);
  }

  const byId = new Map(questions.map((question) => [question.id, question]));
  const restored = state.questionIds
    .map((id) => byId.get(id))
    .filter((question): question is DailyQuestion => question !== undefined);
  const extras = questions.filter((question) => !state.questionIds.includes(question.id));
  return [...restored, ...extras].slice(0, DAILY_GOAL);
}

function syncTodayState(existing: DailyState | null, questions: DailyQuestion[]): DailyState {
  const date = todayKey();
  if (existing?.date === date) {
    const questionIds = existing.questionIds.length
      ? existing.questionIds
      : questions.map((question) => question.id);
    return {
      ...existing,
      questionIds: questionIds.slice(0, DAILY_GOAL),
      answers: existing.answers.filter((answer) => questionIds.includes(answer.questionId)),
    };
  }

  return {
    date,
    questionIds: questions.map((question) => question.id).slice(0, DAILY_GOAL),
    answers: [],
  };
}

function applyCompletion(meta: DailyMeta, date: string): DailyMeta {
  if (meta.lastCompletedDate === date) return meta;

  const continued = meta.lastCompletedDate === addDays(date, -1);
  const streak = continued ? meta.streak + 1 : 1;
  return {
    streak,
    bestStreak: Math.max(meta.bestStreak, streak),
    totalCompleted: meta.totalCompleted + 1,
    lastCompletedDate: date,
  };
}

function resultText(score: number, total: number, streak: number): string {
  return `I went ${score}/${total} on today's Bain Luck Daily${streak > 1 ? ` and kept a ${streak}-day streak` : ""}.`;
}

export default function DailyPage() {
  usePageTracking({ pageType: "daily", pageTitle: "Daily Challenge" });
  useScrollDepth({ pageType: "daily" });
  useEngagementTime({ pageType: "daily" });

  const [feed, setFeed] = useState<FeedResponse | null>(null);
  const [state, setState] = useState<DailyState | null>(null);
  const [meta, setMeta] = useState<DailyMeta>(EMPTY_META);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [now, setNow] = useState(() => new Date());
  const [shareCopied, setShareCopied] = useState(false);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadDaily() {
      setLoading(true);
      setLoadError(null);
      try {
        const [nextFeed] = await Promise.all([
          fetchFeed({ limit: 30, include_futures: true, include_events: true, event_pct: 0.35 }),
        ]);
        if (cancelled) return;

        const storedState = readJson<DailyState | null>(DAILY_STATE_KEY, null);
        const nextQuestions = curateQuestions(nextFeed, storedState);
        const nextState = syncTodayState(storedState, nextQuestions);
        const nextMeta = readJson<DailyMeta>(DAILY_META_KEY, EMPTY_META);

        setFeed(nextFeed);
        setState(nextState);
        setMeta(nextMeta);
        writeJson(DAILY_STATE_KEY, nextState);
      } catch {
        if (!cancelled) {
          setLoadError("Daily questions are not available right now.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadDaily();
    return () => {
      cancelled = true;
    };
  }, []);

  const questions = useMemo(() => curateQuestions(feed, state), [feed, state]);
  const answers = useMemo(() => state?.answers ?? [], [state]);
  const answeredIds = useMemo(() => new Set(answers.map((answer) => answer.questionId)), [answers]);
  const activeIndex = Math.min(answers.length, Math.max(questions.length - 1, 0));
  const activeQuestion = questions[activeIndex] ?? null;
  const completed = questions.length > 0 && answers.length >= questions.length;
  const score = answers.filter((answer) => answer.correct).length;

  const persistState = useCallback((nextState: DailyState) => {
    setState(nextState);
    writeJson(DAILY_STATE_KEY, nextState);
  }, []);

  const submitAnswer = useCallback(
    (question: DailyQuestion, guess: GuessDirection) => {
      if (!state || answeredIds.has(question.id)) return;

      const threshold = deterministicThreshold(question, state.date);
      const actualPct = Math.round(question.probability * 100);
      const correct = guess === "higher" ? actualPct > threshold : actualPct < threshold;
      const answer: DailyAnswer = {
        questionId: question.id,
        marketId: question.marketId,
        contentType: question.contentType,
        title: question.title,
        subject: question.subject,
        category: question.category,
        guess,
        threshold,
        actualPct,
        correct,
        answeredAt: new Date().toISOString(),
      };

      const nextAnswers = [...state.answers, answer];
      const done = nextAnswers.length >= questions.length;
      const nextState: DailyState = {
        ...state,
        questionIds: questions.map((entry) => entry.id),
        answers: nextAnswers,
        completedAt: done ? state.completedAt || new Date().toISOString() : state.completedAt,
      };

      persistState(nextState);

      if (done) {
        const nextMeta = applyCompletion(meta, state.date);
        setMeta(nextMeta);
        writeJson(DAILY_META_KEY, nextMeta);
      }

      trackEvent("prediction_submit", {
        market_id: question.marketId,
        guess,
        threshold,
        actual_probability: question.probability,
        correct,
        content_type: question.contentType,
        category: question.category,
        surface: "daily",
      }, { immediate: true });

      void fetch("/api/predictions", {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-session-id": getSessionId() },
        body: JSON.stringify({
          market_id: question.marketId,
          guess,
          threshold,
          actual_probability: question.probability,
          correct,
        }),
      }).catch(() => {});
    },
    [answeredIds, meta, persistState, questions, state]
  );

  const restartToday = useCallback(() => {
    if (!state) return;
    const nextState: DailyState = {
      date: state.date,
      questionIds: questions.map((question) => question.id),
      answers: [],
    };
    persistState(nextState);
  }, [persistState, questions, state]);

  const shareSummary = useCallback(async () => {
    const text = `${resultText(score, questions.length, meta.streak)} Try it: ${window.location.origin}/daily`;
    try {
      if (navigator.share) {
        await navigator.share({ title: "Bain Luck Daily", text, url: `${window.location.origin}/daily` });
      } else {
        await navigator.clipboard.writeText(text);
        setShareCopied(true);
        window.setTimeout(() => setShareCopied(false), 1800);
      }
      trackEvent("share", {
        content_type: "daily_challenge",
        method: navigator.share ? "native" : "clipboard",
        score,
        total: questions.length,
        source_section: "daily_summary",
      }, { immediate: true });
    } catch {}
  }, [meta.streak, questions.length, score]);

  if (loading) {
    return (
      <main className="min-h-screen bg-surface-deep text-text-primary">
        <div className="mx-auto flex min-h-screen max-w-3xl items-center justify-center px-4">
          <div className="h-7 w-7 rounded-full border-2 border-surface-border border-t-accent-brand animate-spin" />
        </div>
      </main>
    );
  }

  if (loadError || questions.length === 0 || !state) {
    return (
      <main className="min-h-screen bg-surface-deep text-text-primary">
        <DailyHeader streak={meta.streak} countdown={nextMidnightLabel(now)} />
        <section className="mx-auto max-w-3xl px-4 py-16 text-center">
          <div className="mx-auto max-w-md rounded-lg border border-surface-border bg-surface-card p-6 shadow-sm">
            <h1 className="text-title-2">No daily set yet</h1>
            <p className="mt-2 text-sm text-text-secondary">
              {loadError || "There are not enough guessable markets in the feed right now."}
            </p>
            <Link
              href="/discover"
              className="mt-5 inline-flex items-center justify-center rounded-md bg-accent-brand px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-accent-live"
            >
              Browse Discover
            </Link>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-surface-deep text-text-primary">
      <DailyHeader streak={meta.streak} countdown={nextMidnightLabel(now)} />

      <section className="mx-auto grid max-w-5xl gap-6 px-4 py-6 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="space-y-4">
          <div className="rounded-lg border border-surface-border bg-surface-card p-4 shadow-sm">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Daily Challenge</p>
                <h1 className="mt-1 text-title-1">Five probability calls</h1>
                <p className="mt-1 max-w-xl text-sm text-text-secondary">
                  Guess whether the real market probability is higher or lower than the line.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-2 sm:w-48">
                <Metric label="Score" value={`${score}/${answers.length || questions.length}`} />
                <Metric label="Progress" value={`${answers.length}/${questions.length}`} />
              </div>
            </div>
            <div className="mt-4 h-2 overflow-hidden rounded-full bg-surface-elevated">
              <div
                className="h-full rounded-full bg-accent-brand transition-all duration-500"
                style={{ width: `${(answers.length / questions.length) * 100}%` }}
              />
            </div>
          </div>

          {completed ? (
            <SummaryCard
              answers={answers}
              score={score}
              total={questions.length}
              streak={meta.streak}
              bestStreak={meta.bestStreak}
              countdown={nextMidnightLabel(now)}
              copied={shareCopied}
              onShare={shareSummary}
              onRestart={restartToday}
            />
          ) : (
            activeQuestion && (
              <QuestionCard
                key={activeQuestion.id}
                question={activeQuestion}
                index={activeIndex}
                total={questions.length}
                threshold={deterministicThreshold(activeQuestion, state.date)}
                onAnswer={submitAnswer}
              />
            )
          )}
        </div>

        <aside className="space-y-4">
          <div className="rounded-lg border border-surface-border bg-surface-card p-4 shadow-sm">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Trophy className="h-4 w-4 text-accent-warning" />
              Habit Loop
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2">
              <Metric label="Streak" value={`${meta.streak}`} />
              <Metric label="Best" value={`${meta.bestStreak}`} />
              <Metric label="Done" value={`${meta.totalCompleted}`} />
            </div>
            <div className="mt-4 flex items-center gap-2 rounded-md bg-surface-elevated px-3 py-2 text-xs text-text-secondary">
              <Clock3 className="h-4 w-4 shrink-0 text-text-muted" />
              Next set in {nextMidnightLabel(now)}
            </div>
          </div>

          <div className="rounded-lg border border-surface-border bg-surface-card p-4 shadow-sm">
            <p className="text-sm font-semibold">Today&apos;s Answers</p>
            <div className="mt-3 space-y-2">
              {questions.map((question, index) => {
                const answer = answers.find((entry) => entry.questionId === question.id);
                const current = !answer && index === activeIndex && !completed;
                return (
                  <div
                    key={question.id}
                    className={`flex items-center gap-3 rounded-md border px-3 py-2 ${
                      current ? "border-accent-brand bg-accent-brand/5" : "border-surface-border bg-surface-card"
                    }`}
                  >
                    <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-elevated text-xs font-bold">
                      {answer ? (
                        answer.correct ? (
                          <CheckCircle2 className="h-4 w-4 text-accent-live" />
                        ) : (
                          <XCircle className="h-4 w-4 text-accent-danger" />
                        )
                      ) : (
                        index + 1
                      )}
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-xs font-semibold">{question.subject}</p>
                      <p className="truncate text-[11px] text-text-muted">{categoryLabel(question)}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </aside>
      </section>
    </main>
  );
}

function DailyHeader({ streak, countdown }: { streak: number; countdown: string }) {
  return (
    <header className="sticky top-0 z-20 border-b border-surface-border bg-surface-card/90 backdrop-blur">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-4 py-3">
        <Link href="/discover" className="inline-flex items-center gap-2 text-sm font-semibold text-text-secondary hover:text-text-primary">
          <ArrowLeft className="h-4 w-4" />
          Discover
        </Link>
        <div className="flex items-center gap-2 text-xs text-text-secondary">
          <span className="rounded-full bg-accent-brand/10 px-2.5 py-1 font-semibold text-accent-brand">
            {streak} day streak
          </span>
          <span className="rounded-full bg-surface-elevated px-2.5 py-1">
            {countdown}
          </span>
        </div>
      </div>
    </header>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-surface-border bg-surface-card px-3 py-2 text-center">
      <div className="font-mono text-lg font-bold tabular-nums">{value}</div>
      <div className="text-[11px] font-medium text-text-muted">{label}</div>
    </div>
  );
}

function QuestionCard({
  question,
  index,
  total,
  threshold,
  onAnswer,
}: {
  question: DailyQuestion;
  index: number;
  total: number;
  threshold: number;
  onAnswer: (question: DailyQuestion, guess: GuessDirection) => void;
}) {
  return (
    <article className="overflow-hidden rounded-lg border border-surface-border bg-surface-card shadow-sm">
      <div className="border-b border-surface-border bg-surface-elevated px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-text-muted">
            Question {index + 1} of {total}
          </span>
          <span className="rounded-full bg-surface-card px-2.5 py-1 text-xs font-semibold text-text-secondary">
            {categoryLabel(question)}
          </span>
        </div>
      </div>

      <div className="p-5 sm:p-6">
        <h2 className="text-title-2">{question.title}</h2>
        {question.context && (
          <p className="mt-3 max-w-2xl text-sm leading-6 text-text-secondary">{question.context}</p>
        )}

        <div className="mt-6 rounded-lg border border-surface-border bg-surface-deep p-4">
          <p className="text-sm text-text-secondary">Market line</p>
          <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-lg font-semibold">{question.subject}</p>
              <p className="text-sm text-text-muted">Is the probability higher or lower than this?</p>
            </div>
            <div className="font-mono text-5xl font-black tabular-nums">{threshold}%</div>
          </div>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <button
            type="button"
            onClick={() => onAnswer(question, "higher")}
            className="inline-flex min-h-14 items-center justify-center gap-2 rounded-md border border-accent-live/30 bg-accent-live/10 px-4 py-3 text-sm font-bold text-accent-live transition-colors hover:bg-accent-live/15"
          >
            <ArrowUp className="h-5 w-5" />
            Higher than {threshold}%
          </button>
          <button
            type="button"
            onClick={() => onAnswer(question, "lower")}
            className="inline-flex min-h-14 items-center justify-center gap-2 rounded-md border border-accent-danger/30 bg-accent-danger/10 px-4 py-3 text-sm font-bold text-accent-danger transition-colors hover:bg-accent-danger/15"
          >
            <ArrowDown className="h-5 w-5" />
            Lower than {threshold}%
          </button>
        </div>

        <Link href={question.detailHref} className="mt-4 inline-flex text-sm font-semibold text-accent-brand hover:text-accent-live">
          Open market details
        </Link>
      </div>
    </article>
  );
}

function SummaryCard({
  answers,
  score,
  total,
  streak,
  bestStreak,
  countdown,
  copied,
  onShare,
  onRestart,
}: {
  answers: DailyAnswer[];
  score: number;
  total: number;
  streak: number;
  bestStreak: number;
  countdown: string;
  copied: boolean;
  onShare: () => void;
  onRestart: () => void;
}) {
  return (
    <section className="rounded-lg border border-surface-border bg-surface-card p-5 shadow-sm sm:p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Complete</p>
          <h2 className="mt-1 text-title-1">You went {score}/{total}</h2>
          <p className="mt-2 text-sm text-text-secondary">
            {streak > 1
              ? `Current streak: ${streak} days. Best streak: ${bestStreak} days.`
              : `Next daily set unlocks in ${countdown}.`}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:w-48">
          <Metric label="Accuracy" value={`${Math.round((score / total) * 100)}%`} />
          <Metric label="Streak" value={`${streak}`} />
        </div>
      </div>

      <div className="mt-5 rounded-lg border border-surface-border bg-surface-deep p-4">
        <p className="text-sm font-semibold">Share summary</p>
        <p className="mt-2 rounded-md bg-surface-card px-3 py-2 text-sm text-text-secondary">
          {resultText(score, total, streak)}
        </p>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          <button
            type="button"
            onClick={onShare}
            className="inline-flex items-center justify-center gap-2 rounded-md bg-accent-brand px-4 py-2.5 text-sm font-bold text-white transition-colors hover:bg-accent-live"
          >
            {copied ? <Copy className="h-4 w-4" /> : <Share2 className="h-4 w-4" />}
            {copied ? "Copied" : "Share Score"}
          </button>
          <button
            type="button"
            onClick={onRestart}
            className="inline-flex items-center justify-center gap-2 rounded-md border border-surface-border bg-surface-card px-4 py-2.5 text-sm font-bold text-text-secondary transition-colors hover:text-text-primary"
          >
            <RotateCcw className="h-4 w-4" />
            Replay Today
          </button>
        </div>
      </div>

      <div className="mt-5 space-y-2">
        {answers.map((answer, index) => (
          <div key={answer.questionId} className="flex items-start gap-3 rounded-md border border-surface-border bg-surface-card p-3">
            <div className="mt-0.5">
              {answer.correct ? (
                <CheckCircle2 className="h-5 w-5 text-accent-live" />
              ) : (
                <XCircle className="h-5 w-5 text-accent-danger" />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-bold text-text-muted">#{index + 1}</span>
                <span className="text-xs font-semibold text-text-secondary">{answer.category}</span>
              </div>
              <p className="mt-1 truncate text-sm font-semibold">{answer.subject}</p>
              <p className="mt-1 text-xs text-text-muted">
                You picked {answer.guess} than {answer.threshold}%. Actual: {answer.actualPct}%.
              </p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
