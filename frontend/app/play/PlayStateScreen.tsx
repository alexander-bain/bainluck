"use client";

// L2-194 / L2-195 — the honest non-play screens shared by both game modes.
// Replaces the old "Loading questions… forever" and "you rated them all" states
// that lied when a feed request had failed or a page carried no usable cards.
// Every screen has an accessible role/label and exactly one primary action:
//   • error       → Try again        (retry the SAME offset)
//   • scan_paused → Continue         (keep scanning — server still has pages)
//   • caught_up   → Check for more   (freshness refresh from page zero)
// Only caught_up means true server exhaustion; scan_paused never claims it.

interface PlayStateScreenProps {
  variant: "loading" | "error" | "scan_paused" | "caught_up";
  bestStreakLabel?: string; // optional line under the headline (Higher/Lower streak)
  onRetry: () => void; // error → Try again (same offset)
  onRefresh?: () => void; // caught_up → Check for more (refresh from zero)
  onContinue?: () => void; // scan_paused → Continue (next scan page)
  onExit: () => void;
}

const CARD_ACTION =
  "w-full rounded-2xl bg-accent-brand px-6 py-3 text-white font-black text-lg active:scale-95 transition-transform";
const CARD_SECONDARY =
  "w-full rounded-2xl border-2 border-surface-border bg-surface-card px-6 py-3 text-text-primary font-bold text-lg active:scale-95 transition-transform";
const WRAP =
  "flex flex-col items-center justify-center min-h-[70vh] text-center px-6 gap-4";

export default function PlayStateScreen({
  variant,
  bestStreakLabel,
  onRetry,
  onRefresh,
  onContinue,
  onExit,
}: PlayStateScreenProps) {
  if (variant === "loading") {
    return (
      <div className={WRAP} role="status" aria-live="polite">
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
      <div className={WRAP} role="alert" aria-live="assertive">
        <div className="text-6xl" aria-hidden>
          📡
        </div>
        <h2 className="text-2xl font-black text-text-primary">Couldn&apos;t load new cards</h2>
        <p className="text-text-secondary">Check your connection and try again.</p>
        <div className="mt-2 flex flex-col gap-3 w-full max-w-xs">
          <button onClick={onRetry} className={CARD_ACTION} style={{ minHeight: 48 }} aria-label="Try again">
            🔁 Try again
          </button>
          <button onClick={onExit} className={CARD_SECONDARY} style={{ minHeight: 48 }} aria-label="Back to menu">
            Back to menu
          </button>
        </div>
      </div>
    );
  }

  if (variant === "scan_paused") {
    // The server still reports more pages — we just haven't found a usable card
    // yet. Truthful copy + Continue, NOT a false "all caught up".
    return (
      <div className={WRAP} role="status" aria-live="polite">
        <div className="text-6xl" aria-hidden>
          🔎
        </div>
        <h2 className="text-2xl font-black text-text-primary">Still looking…</h2>
        <p className="text-text-secondary">
          {bestStreakLabel ? `${bestStreakLabel} · ` : ""}No new match yet — keep searching?
        </p>
        <div className="mt-2 flex flex-col gap-3 w-full max-w-xs">
          <button
            onClick={onContinue ?? onRetry}
            className={CARD_ACTION}
            style={{ minHeight: 48 }}
            aria-label="Keep looking for more cards"
          >
            🔎 Keep looking
          </button>
          <button onClick={onExit} className={CARD_SECONDARY} style={{ minHeight: 48 }} aria-label="Back to menu">
            Back to menu
          </button>
        </div>
      </div>
    );
  }

  // caught_up — genuine server exhaustion (has_more=false). "Check for more" is a
  // freshness refresh from page zero, so newly inserted first-page cards appear.
  return (
    <div className={WRAP} role="status" aria-live="polite">
      <div className="text-6xl" aria-hidden>
        🎉
      </div>
      <h2 className="text-2xl font-black text-text-primary">You&apos;re all caught up!</h2>
      <p className="text-text-secondary">
        {bestStreakLabel ? `${bestStreakLabel} · ` : ""}Come back later for more.
      </p>
      <div className="mt-2 flex flex-col gap-3 w-full max-w-xs">
        <button
          onClick={onRefresh ?? onRetry}
          className={CARD_ACTION}
          style={{ minHeight: 48 }}
          aria-label="Check for more cards"
        >
          🔁 Check for more
        </button>
        <button onClick={onExit} className={CARD_SECONDARY} style={{ minHeight: 48 }} aria-label="Back to menu">
          Back to menu
        </button>
      </div>
    </div>
  );
}
