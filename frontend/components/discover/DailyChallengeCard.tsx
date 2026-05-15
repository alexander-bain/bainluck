"use client";

const DAILY_GOAL = 5;

interface DailyChallengeCardProps {
  guessesToday: number;
  onStart?: () => void;
}

export function DailyChallengeCard({ guessesToday, onStart }: DailyChallengeCardProps) {
  const completed = guessesToday >= DAILY_GOAL;
  const progress = Math.min(guessesToday / DAILY_GOAL, 1);
  const remaining = Math.max(DAILY_GOAL - guessesToday, 0);

  return (
    <div className={`rounded-2xl overflow-hidden border ${completed ? "border-green-400/50" : "border-amber-400/40"} bg-surface-card shadow-md`}>
      <div className="px-4 py-3 flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <span className="grid place-items-center w-10 h-10 rounded-xl bg-amber-500/10 text-xl">{completed ? "🏆" : "🎯"}</span>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-bold">
              {completed ? "Daily Challenge Complete" : "Today's Challenge"}
            </div>
            <div className="text-xs text-text-muted">
              {completed
                ? "Come back tomorrow for a new set"
                : `${remaining} ${remaining === 1 ? "prediction" : "predictions"} left to finish today's set`}
            </div>
          </div>
        </div>
        <div className="flex-1">
          <div className="h-2 rounded-full bg-surface-elevated overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${completed ? "bg-green-500" : "bg-amber-500"}`}
              style={{ width: `${progress * 100}%` }}
            />
          </div>
          <div className="mt-1 text-[10px] font-semibold text-text-muted text-right">{guessesToday}/{DAILY_GOAL}</div>
        </div>
        {!completed && (
          <button
            type="button"
            onClick={onStart}
            className="shrink-0 rounded-xl bg-amber-500 px-4 py-2 text-sm font-bold text-white hover:bg-amber-600 transition-colors"
          >
            Play next
          </button>
        )}
      </div>
    </div>
  );
}
