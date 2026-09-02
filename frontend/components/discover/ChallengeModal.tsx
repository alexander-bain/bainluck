"use client";

// LAT-P206 — the direct module, not the `@/components/DiscoverCard` barrel.
// A barrel is imported whole, so reaching `GuessCard` through it would pull
// every Discover card type into this modal's chunk.
import { GuessCard } from "@/components/discover/GuessCard";
import { Button } from "@/components/ui/button";
import { getItemId } from "@/lib/discover/itemId";
import type { FeedItem } from "@/lib/types";

/**
 * LAT-P205 — the daily challenge, off the first load.
 *
 * This markup used to live inside `app/discover/page.tsx`, which is the eagerly
 * loaded entry chunk of `/`. It is only ever rendered behind `challengeOpen`,
 * i.e. after a reader taps "Start" on the challenge card — so every cold
 * visitor downloaded it before their first card and the overwhelming majority
 * never opened it. Its own module is what makes `next/dynamic` in the page a
 * real split point; declaring the deferral without moving the code would leave
 * the bytes exactly where they were (the LAT-P200 lesson, in reverse).
 *
 * Nothing about the component changed in the move. It is exported as a named
 * AND default export: the page reaches it through `dynamic()` (default), and
 * `__tests__/capture/emptyStatesRenderTheirOwnBranch.test.tsx` renders the
 * no-cards branch directly (named), which is the anchor three certs asked for
 * and which a source-only reference would not satisfy.
 */
export function ChallengeModal({
  items,
  currentIndex,
  completed,
  onClose,
  onGuessCompleted,
  onNextQuestion,
}: {
  items: FeedItem[];
  currentIndex: number;
  completed: boolean;
  onClose: () => void;
  onGuessCompleted: () => void;
  onNextQuestion: () => void;
}) {
  const goal = Math.min(5, Math.max(items.length, 1));
  const progress = completed ? 1 : currentIndex / goal;
  const currentItem = items[currentIndex];
  const isLastQuestion = currentIndex >= goal - 1;

  return (
    <div className="fixed inset-0 z-50 bg-black/55 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="w-full max-w-md max-h-[92vh] overflow-y-auto rounded-2xl bg-surface-deep shadow-2xl border border-surface-border">
        <div className="sticky top-0 z-10 bg-surface-card/90 backdrop-blur border-b border-surface-border px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-black text-text-primary">Today’s Challenge</div>
              <div className="text-xs text-text-muted">
                {completed ? "Set complete" : `Question ${Math.min(currentIndex + 1, goal)} of ${goal}`}
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="grid place-items-center w-8 h-8 rounded-full text-text-muted hover:text-text-primary hover:bg-surface-elevated transition-colors"
              aria-label="Close challenge"
            >
              ×
            </button>
          </div>
          <div className="mt-3 h-2 rounded-full bg-surface-elevated overflow-hidden">
            <div
              className="h-full rounded-full bg-amber-500 transition-all duration-500"
              style={{ width: `${progress * 100}%` }}
            />
          </div>
        </div>

        <div className="p-4">
          {completed ? (
            <div className="rounded-2xl border border-green-400/40 bg-surface-card p-6 text-center shadow-md">
              <div className="text-4xl mb-3">🏆</div>
              <h2 className="text-xl font-black text-text-primary">Challenge complete</h2>
              <p className="mt-2 text-sm text-text-secondary">
                Your predictions are counted. Come back tomorrow for a fresh set.
              </p>
              <Button
                type="button"
                onClick={onClose}
                size="lg"
                className="mt-5 w-full rounded-xl"
              >
                Back to Discover
              </Button>
            </div>
          ) : currentItem ? (
            <GuessCard
              key={getItemId(currentItem)}
              item={currentItem}
              onGuessCompleted={onGuessCompleted}
              nextButtonLabel={isLastQuestion ? "Finish challenge" : "Next question"}
              onNextQuestion={onNextQuestion}
            />
          ) : (
            <div
              className="rounded-2xl border border-surface-border bg-surface-card p-6 text-center shadow-md"
              data-empty-state-name="challenge-no-cards"
            >
              <h2 className="text-lg font-black text-text-primary">No challenge cards right now</h2>
              {/* Ruling 142: say where the challenge gets its questions, not
                  when more will arrive. */}
              <p className="mt-2 text-sm text-text-secondary">
                The daily challenge draws its questions from the live feed.
              </p>
              <Button
                type="button"
                onClick={onClose}
                size="lg"
                className="mt-5 w-full rounded-xl"
              >
                Back to Discover
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default ChallengeModal;
