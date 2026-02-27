"use client";

import Link from "next/link";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";

/**
 * Excitement Index Explainer Page
 *
 * Explains Bain Luck's excitement metric in accessible language
 * with visual examples for each excitement level.
 */
export default function EIExplainerPage() {
  usePageTracking({ pageType: 'pulse', pageTitle: 'What is the Excitement Index?' });
  useScrollDepth({ pageType: 'pulse' });
  useEngagementTime({ pageType: 'pulse' });

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      {/* Hero Section */}
      <div className="text-center space-y-4 pb-6 border-b border-surface-border">
        <div className="text-6xl">⚡</div>
        <h1 className="text-title-1 text-text-primary">What is the Excitement Index?</h1>
        <p className="text-lg text-text-secondary max-w-xl mx-auto">
          The Excitement Index (EI) tells you how thrilling a game is — at a glance.
          It measures the total distance win probabilities travel during a game.
        </p>
      </div>

      {/* How It Works */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-text-primary flex items-center gap-2">
          <span>📊</span> How the Excitement Index Works
        </h2>
        <div className="bg-surface-card rounded-xl p-6 border border-surface-border shadow-card space-y-4">
          <p className="text-text-secondary leading-relaxed">
            During a game, betting odds constantly shift based on what&apos;s happening
            on the field. When one team scores, their odds of winning go up.
            When momentum swings, the odds swing too.
          </p>
          <p className="text-text-secondary leading-relaxed">
            <strong className="text-text-primary">The Excitement Index measures the total amount of these swings.</strong>{" "}
            A game where the lead changes hands multiple times and the outcome
            stays uncertain until the final whistle will have a high EI score.
            A blowout where one team dominates from start to finish? Low EI.
          </p>
          <div className="bg-surface-deep rounded-lg p-4 border border-surface-border">
            <p className="text-sm text-text-secondary italic">
              &ldquo;The Excitement Index answers the question: If I only have time to watch one game,
              which one should I pick?&rdquo;
            </p>
          </div>
        </div>
      </section>

      {/* The Scale */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-text-primary flex items-center gap-2">
          <span>📈</span> The EI Scale (1-100)
        </h2>

        <div className="space-y-3">
          {[
            { emoji: "🔥", name: "Incredible", range: "81-100", tag: "Must-Watch", tagColor: "bg-red-500/15 text-red-400", barColor: "bg-red-500/150", example: "A basketball game where both teams trade 3-pointers in the final minutes, with the lead changing 5 times in the last 2 minutes.", exBg: "bg-red-500/15", exText: "text-red-800" },
            { emoji: "⚡", name: "Exciting", range: "61-80", tag: "Great Game", tagColor: "bg-orange-100 text-orange-700", barColor: "bg-orange-500", example: "A football game where the underdog takes an early lead, the favorite storms back, but the final drive stalls at the 10-yard line.", exBg: "bg-orange-50", exText: "text-orange-800" },
            { emoji: "💪", name: "Competitive", range: "41-60", tag: "Solid", tagColor: "bg-amber-100 text-amber-700", barColor: "bg-amber-500", example: "A baseball game where the better team leads most of the way, but the opponent makes it interesting with a late rally that falls short.", exBg: "bg-amber-50", exText: "text-amber-800" },
            { emoji: "😐", name: "Quiet", range: "21-40", tag: "One-sided", tagColor: "bg-surface-elevated text-text-secondary-600", barColor: "bg-slate-400", example: "A hockey game where the home team scores twice in the first period and cruises to victory, never trailing.", exBg: "bg-slate-50", exText: "text-text-secondary-600" },
            { emoji: "💤", name: "Flat", range: "1-20", tag: "Skip It", tagColor: "bg-surface-elevated text-text-secondary-500", barColor: "bg-slate-300", example: "A basketball game where the favorite leads by 20+ points from the second quarter onwards and the starters rest the entire fourth quarter.", exBg: "bg-slate-50", exText: "text-text-secondary-600" },
          ].map((level) => (
            <div key={level.name} className="bg-surface-card rounded-xl overflow-hidden border border-surface-border shadow-card">
              <div className="flex items-stretch">
                <div className={`w-2 ${level.barColor}`} />
                <div className="flex-1 p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-2xl">{level.emoji}</span>
                      <span className="font-bold text-text-primary text-lg">{level.name}</span>
                      <span className="text-sm text-text-secondary">({level.range})</span>
                    </div>
                    <span className={`${level.tagColor} px-3 py-1 rounded-full text-sm font-semibold`}>
                      {level.tag}
                    </span>
                  </div>
                  <div className={`mt-3 p-3 ${level.exBg} rounded-lg`}>
                    <p className={`text-xs ${level.exText}`}>
                      <strong>Example:</strong> {level.example}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* What Goes Into EI */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-text-primary flex items-center gap-2">
          <span>🔬</span> What Goes Into the Excitement Index
        </h2>
        <div className="bg-surface-card rounded-xl p-6 border border-surface-border shadow-card">
          <p className="text-text-secondary mb-4">
            The EI is based on the cumulative distance win probabilities travel during
            a game, normalized by game length:
          </p>

          <div className="grid gap-4 sm:grid-cols-2">
            {[
              { emoji: "📏", name: "Probability Travel", desc: "The total distance probabilities moved. More travel = more action." },
              { emoji: "🔄", name: "Lead Changes", desc: "How many times the favorite flipped. Each flip adds to the drama." },
              { emoji: "🦾", name: "Comeback Factor", desc: "The winner's lowest probability during the game. A winner who was down to 10% is more exciting than one who led the whole way." },
              { emoji: "⏱️", name: "Time Normalization", desc: "Overtime games are adjusted so extra time doesn't artificially inflate the score." },
            ].map((item) => (
              <div key={item.name} className="p-4 bg-surface-deep rounded-lg border border-surface-border">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xl">{item.emoji}</span>
                  <span className="font-semibold text-text-primary">{item.name}</span>
                </div>
                <p className="text-sm text-text-secondary">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Live vs Completed */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-text-primary flex items-center gap-2">
          <span>🔴</span> Live vs Final
        </h2>
        <div className="bg-surface-card rounded-xl p-6 border border-surface-border shadow-card space-y-4">
          <div className="flex gap-4">
            <div className="flex-1 p-4 bg-emerald-50 rounded-lg border border-emerald-200">
              <div className="font-semibold text-emerald-400 mb-2">🟢 During Live Games</div>
              <p className="text-sm text-emerald-800">
                EI updates every 30 seconds as new odds come in. Watch it climb during exciting moments!
              </p>
            </div>
            <div className="flex-1 p-4 bg-slate-50 rounded-lg border border-slate-200">
              <div className="font-semibold text-text-secondary-700 mb-2">✅ After Final</div>
              <p className="text-sm text-text-secondary-600">
                The final EI score reflects the entire game. Use it to find the best highlights to rewatch.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-text-primary flex items-center gap-2">
          <span>❓</span> Common Questions
        </h2>
        <div className="space-y-3">
          {[
            { q: "Does a high EI mean the underdog won?", a: "Not necessarily! EI measures excitement, not upsets. A game can have high EI even if the favorite wins — as long as it was a close, dramatic contest." },
            { q: "Why doesn't every game have an EI score?", a: "We need enough odds data throughout the game to calculate EI accurately. Games that just started or have limited betting activity won't have a score yet." },
            { q: "Is EI the same across all sports?", a: "Yes! EI is calibrated using percentiles so a score of 80 represents similar excitement across sports — whether it's basketball, football, or hockey." },
          ].map((faq) => (
            <details key={faq.q} className="bg-surface-card rounded-xl border border-surface-border shadow-card group">
              <summary className="p-4 cursor-pointer font-semibold text-text-primary flex items-center justify-between">
                {faq.q}
                <span className="text-text-secondary group-open:rotate-180 transition-transform">▼</span>
              </summary>
              <div className="px-4 pb-4 text-text-secondary text-sm">{faq.a}</div>
            </details>
          ))}
        </div>
      </section>

      {/* Hall of Fame Link */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-text-primary flex items-center gap-2">
          <span>🏆</span> Hall of Fame
        </h2>
        <div className="bg-surface-card rounded-xl p-6 border border-surface-border shadow-card">
          <p className="text-text-secondary mb-4">
            Curious which games had the highest (and lowest) Excitement Index scores ever?
            Check out our all-time rankings.
          </p>
          <Link
            href="/ei/hall-of-fame"
            className="inline-flex items-center gap-2 bg-amber-100 text-amber-800 px-4 py-2 rounded-full font-semibold hover:bg-amber-200 transition-colors"
          >
            <span>🏆</span>
            View Hall of Fame
          </Link>
        </div>
      </section>

      {/* CTA */}
      <div className="text-center pt-4 pb-8">
        <Link
          href="/"
          className="inline-flex items-center gap-2 bg-text-primary text-surface-deep px-6 py-3 rounded-full font-semibold hover:bg-text-primary/90 transition-colors"
        >
          <span>🍀</span>
          Find Exciting Games Now
        </Link>
      </div>
    </div>
  );
}
