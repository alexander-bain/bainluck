"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  Check,
  Copy,
  Loader2,
  Share2,
  Trophy,
  X,
} from "lucide-react";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { useAnalyticsContext } from "@/components/Analytics";
import { Button } from "@/components/ui/button";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
const SESSION_KEY = "bainluck_session_id";

type Guess = "higher" | "lower";

interface ChallengeResponse {
  challenge_code: string;
  market_name: string;
  market_id: number;
  creator_guess: Guess;
  threshold: number;
  friend_guess: Guess | null;
  current_probability: number | null;
  creator_correct: boolean | null;
  friend_correct: boolean | null;
  resolved_at: string | null;
  created_at: string | null;
}

interface AcceptResponse {
  status: string;
  challenge_code: string;
  friend_guess: Guess;
  actual_probability: number | null;
  creator_correct: boolean | null;
  friend_correct: boolean | null;
}

interface ChallengePageProps {
  params: { id: string };
}

function getSessionId(): string {
  if (typeof window === "undefined") return "";

  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

function formatProbability(probability: number | null): string {
  if (probability === null || Number.isNaN(probability)) return "--";
  return `${Math.round(probability * 100)}%`;
}

function formatDate(value: string | null): string {
  if (!value) return "Pending";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function guessLabel(guess: Guess): string {
  return guess === "higher" ? "Higher" : "Lower";
}

function resultLabel(correct: boolean | null): string {
  if (correct === null) return "Pending";
  return correct ? "Correct" : "Missed";
}

export default function ChallengePage({ params }: ChallengePageProps) {
  const challengeCode = decodeURIComponent(params.id);

  usePageTracking({
    pageType: "friend_challenge",
    pageTitle: "Friend Challenge",
    additionalParams: { challenge_code: challengeCode },
    deps: [challengeCode],
  });
  useScrollDepth({ pageType: "friend_challenge" });
  useEngagementTime({ pageType: "friend_challenge" });
  const { track } = useAnalyticsContext();

  const [challenge, setChallenge] = useState<ChallengeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedGuess, setSelectedGuess] = useState<Guess | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [copied, setCopied] = useState(false);
  const [submitMessage, setSubmitMessage] = useState<string | null>(null);

  const shareUrl = useMemo(() => {
    if (typeof window === "undefined") return `https://bainluck.com/challenge/${challengeCode}`;
    return window.location.href;
  }, [challengeCode]);

  const isAccepted = challenge?.friend_guess !== null && challenge?.friend_guess !== undefined;
  const isResolved = challenge?.creator_correct !== null || challenge?.friend_correct !== null || Boolean(challenge?.resolved_at);
  const currentProbability = formatProbability(challenge?.current_probability ?? null);
  const progressValue = challenge ? (isAccepted ? 100 : 50) : 0;

  const loadChallenge = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_URL}/api/challenges/${encodeURIComponent(challengeCode)}`, {
        headers: { "x-session-id": getSessionId() },
      });

      if (res.status === 404) {
        setChallenge(null);
        setError("Challenge not found");
        return;
      }

      if (!res.ok) {
        setChallenge(null);
        setError("Challenge unavailable");
        return;
      }

      const data = (await res.json()) as ChallengeResponse;
      setChallenge(data);
      setSelectedGuess(data.friend_guess);
    } catch {
      setChallenge(null);
      setError("Could not load challenge");
    } finally {
      setLoading(false);
    }
  }, [challengeCode]);

  useEffect(() => {
    loadChallenge();
  }, [loadChallenge]);

  useEffect(() => {
    if (!challenge) return;
    track("friend_challenge_view", {
      challenge_code: challenge.challenge_code,
      market_id: challenge.market_id,
      accepted: Boolean(challenge.friend_guess),
    });
  }, [challenge, track]);

  async function acceptChallenge() {
    if (!selectedGuess || !challenge || submitting || isAccepted) return;

    setSubmitting(true);
    setSubmitMessage(null);
    try {
      const res = await fetch(`${API_URL}/api/challenges/${encodeURIComponent(challenge.challenge_code)}/accept`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-session-id": getSessionId(),
        },
        body: JSON.stringify({ guess: selectedGuess }),
      });

      if (res.status === 409) {
        setSubmitMessage("This challenge has already been accepted.");
        await loadChallenge();
        return;
      }

      if (!res.ok) {
        setSubmitMessage("Could not submit your pick.");
        return;
      }

      const data = (await res.json()) as AcceptResponse;
      setChallenge((prev) =>
        prev
          ? {
              ...prev,
              friend_guess: data.friend_guess,
              current_probability: data.actual_probability ?? prev.current_probability,
              creator_correct: data.creator_correct,
              friend_correct: data.friend_correct,
            }
          : prev
      );
      track("friend_challenge_accept", {
        challenge_code: challenge.challenge_code,
        market_id: challenge.market_id,
        guess: selectedGuess,
      });
    } catch {
      setSubmitMessage("Could not submit your pick.");
    } finally {
      setSubmitting(false);
    }
  }

  async function shareChallenge() {
    const title = challenge ? `${challenge.market_name} challenge` : "Bain Luck challenge";
    const text = challenge
      ? `Higher or lower than ${challenge.threshold}%?`
      : "Take this Bain Luck challenge.";

    try {
      if (navigator.share) {
        await navigator.share({ title, text, url: shareUrl });
      } else if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(shareUrl);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1600);
      }
      track("friend_challenge_share", {
        challenge_code: challengeCode,
        method: navigator.share ? "native" : "clipboard",
      });
    } catch {}
  }

  if (loading) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center bg-surface-deep">
        <Loader2 className="h-7 w-7 animate-spin text-text-muted" aria-label="Loading challenge" />
      </div>
    );
  }

  if (error || !challenge) {
    return (
      <div className="min-h-[70vh] bg-surface-deep">
        <div className="mx-auto max-w-2xl px-4 py-12">
          <Link href="/discover" className="inline-flex items-center gap-2 text-sm font-semibold text-text-secondary hover:text-text-primary">
            <ArrowLeft className="h-4 w-4" />
            Discover
          </Link>
          <section className="mt-8 rounded-lg border border-surface-border bg-surface-card p-6 text-center shadow-sm">
            <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-lg bg-surface-elevated text-text-muted">
              <X className="h-5 w-5" />
            </div>
            <h1 className="mt-4 text-2xl font-black tracking-tight text-text-primary">{error}</h1>
            <p className="mt-2 text-sm text-text-secondary">
              This link may be expired, mistyped, or no longer available.
            </p>
            <Link
              href="/discover"
              className="mt-6 inline-flex items-center justify-center rounded-lg bg-accent-brand px-4 py-2 text-sm font-bold text-white hover:bg-accent-live"
            >
              Open Discover
            </Link>
          </section>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-[70vh] bg-surface-deep">
      <div className="mx-auto max-w-3xl px-4 py-5 md:py-8">
        <div className="mb-5 flex items-center justify-between gap-3">
          <Link href="/discover" className="inline-flex items-center gap-2 text-sm font-semibold text-text-secondary hover:text-text-primary">
            <ArrowLeft className="h-4 w-4" />
            Discover
          </Link>
          <button
            type="button"
            onClick={shareChallenge}
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-surface-border bg-surface-card px-3 text-sm font-bold text-text-primary hover:bg-surface-elevated"
          >
            {copied ? <Check className="h-4 w-4 text-accent-live" /> : <Share2 className="h-4 w-4" />}
            {copied ? "Copied" : "Share"}
          </button>
        </div>

        <main className="space-y-4">
          <section className="rounded-lg border border-surface-border bg-surface-card p-5 shadow-sm md:p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs font-bold uppercase tracking-wide text-text-muted">Friend challenge</p>
                <h1 className="mt-2 max-w-2xl text-2xl font-black tracking-tight text-text-primary md:text-3xl">
                  {challenge.market_name}
                </h1>
              </div>
              <div className="rounded-lg bg-surface-elevated px-3 py-2 text-right">
                <div className="text-xs font-semibold text-text-muted">Current</div>
                <div className="font-mono text-2xl font-black tabular-nums text-text-primary">{currentProbability}</div>
              </div>
            </div>

            <div className="mt-5">
              <div className="mb-2 flex items-center justify-between text-xs font-semibold text-text-muted">
                <span>Question 1 of 1</span>
                <span>{isAccepted ? "Accepted" : "Awaiting your pick"}</span>
              </div>
              <div className="h-2 overflow-hidden rounded-lg bg-surface-elevated">
                <div className="h-full rounded-lg bg-accent-brand transition-all" style={{ width: `${progressValue}%` }} />
              </div>
            </div>

            <div className="mt-6 rounded-lg border border-surface-border bg-surface-elevated p-4">
              <p className="text-sm font-semibold text-text-secondary">Will the final probability be higher or lower than</p>
              <div className="mt-1 font-mono text-5xl font-black tabular-nums text-text-primary">{challenge.threshold}%</div>
            </div>
          </section>

          <section className="grid gap-4 md:grid-cols-[1.1fr_0.9fr]">
            <div className="rounded-lg border border-surface-border bg-surface-card p-5 shadow-sm">
              <h2 className="text-base font-black tracking-tight text-text-primary">Your Pick</h2>
              <div className="mt-4 grid grid-cols-2 gap-3">
                <GuessButton
                  guess="higher"
                  selected={selectedGuess === "higher"}
                  disabled={isAccepted}
                  onClick={() => setSelectedGuess("higher")}
                />
                <GuessButton
                  guess="lower"
                  selected={selectedGuess === "lower"}
                  disabled={isAccepted}
                  onClick={() => setSelectedGuess("lower")}
                />
              </div>

              {!isAccepted ? (
                <Button
                  type="button"
                  onClick={acceptChallenge}
                  disabled={!selectedGuess || submitting}
                  size="lg"
                  className="mt-4 w-full"
                >
                  {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
                  Lock Pick
                </Button>
              ) : (
                <div className="mt-4 rounded-lg border border-accent-live/30 bg-accent-live/10 p-3 text-sm font-semibold text-text-primary">
                  Your pick is locked: {guessLabel(challenge.friend_guess!)}
                </div>
              )}

              {submitMessage && <p className="mt-3 text-sm font-semibold text-accent-danger">{submitMessage}</p>}
            </div>

            <div className="rounded-lg border border-surface-border bg-surface-card p-5 shadow-sm">
              <h2 className="text-base font-black tracking-tight text-text-primary">Participants</h2>
              <div className="mt-4 space-y-3">
                <ParticipantRow
                  label="Challenger"
                  guess={challenge.creator_guess}
                  result={challenge.creator_correct}
                />
                <ParticipantRow
                  label="Friend"
                  guess={challenge.friend_guess}
                  result={challenge.friend_correct}
                />
              </div>
            </div>
          </section>

          <section className="rounded-lg border border-surface-border bg-surface-card p-5 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-black tracking-tight text-text-primary">Result</h2>
                <p className="mt-1 text-sm text-text-secondary">
                  {isResolved ? "Scored from the latest available probability." : "Result appears after the challenge is accepted."}
                </p>
              </div>
              <div className="flex items-center gap-2 rounded-lg bg-surface-elevated px-3 py-2 text-sm font-semibold text-text-secondary">
                <Trophy className="h-4 w-4 text-accent-warning" />
                {isResolved ? "Scored" : "Pending"}
              </div>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <Metric label="Threshold" value={`${challenge.threshold}%`} />
              <Metric label="Current" value={currentProbability} />
              <Metric label="Created" value={formatDate(challenge.created_at)} />
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}

function GuessButton({
  guess,
  selected,
  disabled,
  onClick,
}: {
  guess: Guess;
  selected: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  const Icon = guess === "higher" ? ArrowUp : ArrowDown;

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`flex h-24 flex-col items-center justify-center gap-2 rounded-lg border px-3 text-sm font-black transition ${
        selected
          ? "border-accent-brand bg-accent-brand/10 text-text-primary ring-2 ring-accent-brand/20"
          : "border-surface-border bg-surface-card text-text-secondary hover:bg-surface-elevated"
      } ${disabled ? "cursor-default opacity-80" : ""}`}
    >
      <Icon className={`h-6 w-6 ${guess === "higher" ? "text-accent-live" : "text-accent-danger"}`} />
      {guessLabel(guess)}
    </button>
  );
}

function ParticipantRow({
  label,
  guess,
  result,
}: {
  label: string;
  guess: Guess | null;
  result: boolean | null;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-surface-border bg-surface-elevated p-3">
      <div>
        <div className="text-sm font-bold text-text-primary">{label}</div>
        <div className="text-xs font-semibold text-text-muted">{guess ? guessLabel(guess) : "Waiting"}</div>
      </div>
      <span
        className={`rounded-lg px-2.5 py-1 text-xs font-black ${
          result === null
            ? "bg-surface-card text-text-secondary"
            : result
              ? "bg-accent-live/15 text-accent-live"
              : "bg-accent-danger/10 text-accent-danger"
        }`}
      >
        {resultLabel(result)}
      </span>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface-elevated p-3">
      <div className="text-xs font-semibold text-text-muted">{label}</div>
      <div className="mt-1 truncate font-mono text-lg font-black tabular-nums text-text-primary">{value}</div>
    </div>
  );
}
