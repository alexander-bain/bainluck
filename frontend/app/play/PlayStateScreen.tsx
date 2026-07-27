"use client";

// L2-194 — the honest non-play screens shared by both game modes. Replaces the
// old "Loading questions... forever" and "you rated them all" states that lied
// when the feed request had actually failed or a page simply carried no usable
// cards. Every screen has an accessible role/label and a working action.

interface PlayStateScreenProps {
  variant: "loading" | "error" | "caught_up";
  bestStreakLabel?: string; // optional line under the headline (Higher/Lower streak)
  onRetry: () => void;
  onExit: () => void;
}

export default function PlayStateScreen({
  variant,
  bestStreakLabel,
  onRetry,
  onExit,
}: PlayStateScreenProps) {
  if (variant === "loading") {
    return (
      <div
        className="flex flex-col items-center justify-center min-h-[70vh] text-center px-6 gap-4"
        role="status"
        aria-live="polite"
      >
        <div className="text-6xl" aria-hidden>
          🎯
        </div>
        <h2 className="text-2xl font-black text-text-primary">Loading questions…</h2>
        {bestStreakLabel && <p className="text-text-secondary">{bestStreakLabel}</p>}
        <button
          onClick={onExit}
          className="mt-2 rounded-2xl bg-accent-brand px-6 py-3 text-white font-bold text-lg active:scale-95 transition-transform"
          style={{ minHeight: 48 }}
          aria-label="Back to menu"
        >
          Back to menu
        </button>
      </div>
    );
  }

  if (variant === "error") {
    return (
      <div
        className="flex flex-col items-center justify-center min-h-[70vh] text-center px-6 gap-4"
        role="alert"
        aria-live="assertive"
      >
        <div className="text-6xl" aria-hidden>
          📡
        </div>
        <h2 className="text-2xl font-black text-text-primary">Couldn&apos;t load new cards</h2>
        <p className="text-text-secondary">Check your connection and try again.</p>
        <div className="mt-2 flex flex-col gap-3 w-full max-w-xs">
          <button
            onClick={onRetry}
            className="w-full rounded-2xl bg-accent-brand px-6 py-3 text-white font-black text-lg active:scale-95 transition-transform"
            style={{ minHeight: 48 }}
            aria-label="Try again"
          >
            🔁 Try again
          </button>
          <button
            onClick={onExit}
            className="w-full rounded-2xl border-2 border-surface-border bg-surface-card px-6 py-3 text-text-primary font-bold text-lg active:scale-95 transition-transform"
            style={{ minHeight: 48 }}
            aria-label="Back to menu"
          >
            Back to menu
          </button>
        </div>
      </div>
    );
  }

  // caught_up
  return (
    <div
      className="flex flex-col items-center justify-center min-h-[70vh] text-center px-6 gap-4"
      role="status"
      aria-live="polite"
    >
      <div className="text-6xl" aria-hidden>
        🎉
      </div>
      <h2 className="text-2xl font-black text-text-primary">You&apos;re all caught up!</h2>
      <p className="text-text-secondary">
        {bestStreakLabel ? `${bestStreakLabel} · ` : ""}Come back later for more.
      </p>
      <div className="mt-2 flex flex-col gap-3 w-full max-w-xs">
        <button
          onClick={onRetry}
          className="w-full rounded-2xl bg-accent-brand px-6 py-3 text-white font-black text-lg active:scale-95 transition-transform"
          style={{ minHeight: 48 }}
          aria-label="Check for more cards"
        >
          🔁 Check for more
        </button>
        <button
          onClick={onExit}
          className="w-full rounded-2xl border-2 border-surface-border bg-surface-card px-6 py-3 text-text-primary font-bold text-lg active:scale-95 transition-transform"
          style={{ minHeight: 48 }}
          aria-label="Back to menu"
        >
          Back to menu
        </button>
      </div>
    </div>
  );
}
