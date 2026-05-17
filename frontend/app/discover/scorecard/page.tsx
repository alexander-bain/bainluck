import type { Metadata } from "next";
import Link from "next/link";
import { ScorecardAnalytics } from "./ScorecardAnalytics";

interface ScorecardPageProps {
  searchParams: Promise<{
    accuracy?: string;
    total?: string;
    correct?: string;
    streak?: string;
    best?: string;
  }>;
}

export async function generateMetadata({ searchParams }: ScorecardPageProps): Promise<Metadata> {
  const params = await searchParams;
  const accuracy = params.accuracy || "0";
  const total = params.total || "0";
  const correct = params.correct || "0";
  const streak = params.streak || "0";
  const best = params.best || "0";

  const ogImageUrl = `https://bainluck.com/api/og/stats?accuracy=${accuracy}&total=${total}&correct=${correct}&streak=${streak}&best=${best}`;
  const description = `${accuracy}% accurate across ${total} predictions on Bain Luck!`;

  return {
    title: `${accuracy}% Prediction Accuracy | Bain Luck`,
    description,
    openGraph: {
      title: `${accuracy}% Prediction Accuracy | Bain Luck`,
      description,
      siteName: "Bain Luck",
      type: "website",
      images: [
        {
          url: ogImageUrl,
          width: 1200,
          height: 630,
          alt: `Prediction scorecard: ${accuracy}% accuracy`,
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: `${accuracy}% Prediction Accuracy | Bain Luck`,
      description,
      images: [ogImageUrl],
    },
  };
}

export default async function ScorecardPage({ searchParams }: ScorecardPageProps) {
  const params = await searchParams;
  const accuracy = parseInt(params.accuracy || "0") || 0;
  const total = parseInt(params.total || "0") || 0;
  const correct = parseInt(params.correct || "0") || 0;
  const streak = parseInt(params.streak || "0") || 0;
  const bestStreak = parseInt(params.best || "0") || 0;

  return (
    <div className="min-h-screen bg-surface-deep">
      <ScorecardAnalytics />
      <header className="sticky top-0 z-20 bg-surface-card/80 backdrop-blur-lg border-b border-surface-border">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center gap-3">
          <Link href="/discover" className="text-text-muted hover:text-text-primary">
            &larr;
          </Link>
          <h1 className="text-lg font-black tracking-tight">Prediction Scorecard</h1>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8 space-y-8">
        {/* Scorecard display */}
        <div className="text-center space-y-6">
          {/* Accuracy hero */}
          <div className="inline-flex flex-col items-center">
            <div className="w-40 h-40 rounded-full border-[6px] border-accent-brand flex flex-col items-center justify-center bg-surface-card shadow-lg">
              <div className="text-5xl font-black tabular-nums text-text-primary">{accuracy}%</div>
              <div className="text-sm font-semibold text-text-secondary">accuracy</div>
            </div>
          </div>

          {/* Stats grid */}
          <div className="grid grid-cols-3 gap-3 max-w-sm mx-auto">
            <div className="p-4 rounded-xl bg-surface-card border border-surface-border text-center">
              <div className="text-2xl font-black tabular-nums">{total}</div>
              <div className="text-xs text-text-muted mt-1">Predictions</div>
            </div>
            <div className="p-4 rounded-xl bg-surface-card border border-surface-border text-center">
              <div className="text-2xl font-black tabular-nums text-accent-brand">{correct}</div>
              <div className="text-xs text-text-muted mt-1">Correct</div>
            </div>
            <div className="p-4 rounded-xl bg-surface-card border border-surface-border text-center">
              <div className="text-2xl font-black tabular-nums">
                {streak > 0 ? streak : bestStreak}
              </div>
              <div className="text-xs text-text-muted mt-1">
                {streak > 0 ? "Active Streak" : "Best Streak"}
              </div>
            </div>
          </div>
        </div>

        {/* CTA */}
        <div className="text-center space-y-3">
          <p className="text-text-secondary text-sm">Think you can do better?</p>
          <Link
            href="/discover"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-full bg-accent-brand text-white font-bold text-sm hover:bg-accent-brand/90 transition-all"
          >
            Start Predicting
          </Link>
        </div>
      </main>
    </div>
  );
}
