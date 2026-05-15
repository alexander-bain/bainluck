"use client";

interface ResolutionCardProps {
  marketName: string;
  guess: string;
  threshold: number;
  actual: number;
  correct: boolean;
}

export function ResolutionCard({ marketName, guess, threshold, actual, correct }: ResolutionCardProps) {
  return (
    <div className="rounded-2xl overflow-hidden border-2 border-purple-400/30 bg-surface-card shadow-md">
      <div className="px-4 py-2 bg-purple-500/10 flex items-center gap-2">
        <span className="text-sm">📋</span>
        <span className="text-xs font-bold uppercase tracking-wider text-purple-700">Market Resolved</span>
      </div>
      <div className="p-4 text-center">
        <h3 className="font-bold text-sm mb-2">{marketName}</h3>
        <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-bold mb-2 ${
          correct ? "bg-green-500/15 text-green-700" : "bg-red-500/15 text-red-700"
        }`}>
          {correct ? "✓ You got it right!" : "✗ Better luck next time"}
        </div>
        <div className="text-xs text-text-muted">
          You guessed {guess} than {threshold}% — final result: {actual}%
        </div>
      </div>
    </div>
  );
}
