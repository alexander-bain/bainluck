"use client";

import Link from "next/link";

/**
 * Pulse Explainer Page
 *
 * Explains OddsTracker's proprietary excitement metric in accessible language
 * with visual examples for each excitement level.
 */
export default function PulseExplainerPage() {
  return (
    <div className="max-w-3xl mx-auto space-y-8">
      {/* Hero Section */}
      <div className="text-center space-y-4 pb-6 border-b border-mist">
        <div className="text-6xl">💓</div>
        <h1 className="text-title-1 text-graphite">What is Pulse?</h1>
        <p className="text-lg text-slate max-w-xl mx-auto">
          Pulse is OddsTracker&apos;s excitement score that tells you how thrilling
          a game is—at a glance. Think of it as a game&apos;s heartbeat.
        </p>
      </div>

      {/* How It Works */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-graphite flex items-center gap-2">
          <span>📊</span> How Pulse Works
        </h2>
        <div className="bg-white rounded-xl p-6 border border-mist shadow-sm space-y-4">
          <p className="text-slate leading-relaxed">
            During a game, betting odds constantly shift based on what&apos;s happening
            on the field. When one team scores, their odds of winning go up.
            When momentum swings, the odds swing too.
          </p>
          <p className="text-slate leading-relaxed">
            <strong className="text-graphite">Pulse measures these swings.</strong>{" "}
            A game where the lead changes hands multiple times and the outcome
            stays uncertain until the final whistle will have a high Pulse score.
            A blowout where one team dominates from start to finish? Low Pulse.
          </p>
          <div className="bg-snow rounded-lg p-4 border border-mist">
            <p className="text-sm text-slate italic">
              &ldquo;Pulse answers the question: If I only have time to watch one game,
              which one should I pick?&rdquo;
            </p>
          </div>
        </div>
      </section>

      {/* The Scale */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-graphite flex items-center gap-2">
          <span>📈</span> The Pulse Scale (1-100)
        </h2>

        <div className="space-y-3">
          {/* Racing */}
          <div className="bg-white rounded-xl overflow-hidden border border-mist shadow-sm">
            <div className="flex items-stretch">
              <div className="w-2 bg-red-500" />
              <div className="flex-1 p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">🫀</span>
                    <span className="font-bold text-graphite text-lg">Racing</span>
                    <span className="text-sm text-slate">(81-100)</span>
                  </div>
                  <span className="bg-red-100 text-red-700 px-3 py-1 rounded-full text-sm font-semibold">
                    Must-Watch
                  </span>
                </div>
                <p className="text-slate text-sm leading-relaxed">
                  Edge-of-your-seat excitement. Multiple lead changes, dramatic comebacks,
                  or a nail-biter that goes down to the wire. These games are unforgettable.
                </p>
                <div className="mt-3 p-3 bg-red-50 rounded-lg">
                  <p className="text-xs text-red-800">
                    <strong>Example:</strong> A basketball game where both teams trade
                    3-pointers in the final minutes, with the lead changing 5 times
                    in the last 2 minutes.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Strong */}
          <div className="bg-white rounded-xl overflow-hidden border border-mist shadow-sm">
            <div className="flex items-stretch">
              <div className="w-2 bg-orange-500" />
              <div className="flex-1 p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">💓</span>
                    <span className="font-bold text-graphite text-lg">Strong</span>
                    <span className="text-sm text-slate">(61-80)</span>
                  </div>
                  <span className="bg-orange-100 text-orange-700 px-3 py-1 rounded-full text-sm font-semibold">
                    Exciting
                  </span>
                </div>
                <p className="text-slate text-sm leading-relaxed">
                  Genuinely exciting with real moments of drama. The outcome wasn&apos;t
                  certain, and there were stretches where anything could happen.
                </p>
                <div className="mt-3 p-3 bg-orange-50 rounded-lg">
                  <p className="text-xs text-orange-800">
                    <strong>Example:</strong> A football game where the underdog
                    takes an early lead, the favorite storms back, but the final
                    drive stalls at the 10-yard line.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Steady */}
          <div className="bg-white rounded-xl overflow-hidden border border-mist shadow-sm">
            <div className="flex items-stretch">
              <div className="w-2 bg-amber-500" />
              <div className="flex-1 p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">💗</span>
                    <span className="font-bold text-graphite text-lg">Steady</span>
                    <span className="text-sm text-slate">(41-60)</span>
                  </div>
                  <span className="bg-amber-100 text-amber-700 px-3 py-1 rounded-full text-sm font-semibold">
                    Competitive
                  </span>
                </div>
                <p className="text-slate text-sm leading-relaxed">
                  A competitive game with some tension, but the favorite generally
                  controlled the pace. Worth watching if you&apos;re a fan of either team.
                </p>
                <div className="mt-3 p-3 bg-amber-50 rounded-lg">
                  <p className="text-xs text-amber-800">
                    <strong>Example:</strong> A baseball game where the better team
                    leads most of the way, but the opponent makes it interesting
                    with a late rally that falls short.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Weak */}
          <div className="bg-white rounded-xl overflow-hidden border border-mist shadow-sm">
            <div className="flex items-stretch">
              <div className="w-2 bg-slate-400" />
              <div className="flex-1 p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">🩺</span>
                    <span className="font-bold text-graphite text-lg">Weak</span>
                    <span className="text-sm text-slate">(21-40)</span>
                  </div>
                  <span className="bg-slate-100 text-slate-600 px-3 py-1 rounded-full text-sm font-semibold">
                    One-sided
                  </span>
                </div>
                <p className="text-slate text-sm leading-relaxed">
                  The outcome was rarely in doubt. One team dominated most of the
                  game with few exciting moments.
                </p>
                <div className="mt-3 p-3 bg-slate-50 rounded-lg">
                  <p className="text-xs text-slate-600">
                    <strong>Example:</strong> A hockey game where the home team
                    scores twice in the first period and cruises to victory,
                    never trailing.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Flatline */}
          <div className="bg-white rounded-xl overflow-hidden border border-mist shadow-sm">
            <div className="flex items-stretch">
              <div className="w-2 bg-slate-300" />
              <div className="flex-1 p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">📉</span>
                    <span className="font-bold text-graphite text-lg">Flatline</span>
                    <span className="text-sm text-slate">(1-20)</span>
                  </div>
                  <span className="bg-slate-100 text-slate-500 px-3 py-1 rounded-full text-sm font-semibold">
                    Skip It
                  </span>
                </div>
                <p className="text-slate text-sm leading-relaxed">
                  A blowout or completely uneventful game. The result was never in
                  question, and watching highlights would give you the full experience.
                </p>
                <div className="mt-3 p-3 bg-slate-50 rounded-lg">
                  <p className="text-xs text-slate-600">
                    <strong>Example:</strong> A basketball game where the favorite
                    leads by 20+ points from the second quarter onwards and the
                    starters rest the entire fourth quarter.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Components Breakdown */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-graphite flex items-center gap-2">
          <span>🔬</span> What Goes Into Pulse
        </h2>
        <div className="bg-white rounded-xl p-6 border border-mist shadow-sm">
          <p className="text-slate mb-4">
            Pulse combines several factors to measure excitement:
          </p>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="p-4 bg-snow rounded-lg border border-mist">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xl">💓</span>
                <span className="font-semibold text-graphite">Heart Rate</span>
              </div>
              <p className="text-sm text-slate">
                How frequently the odds change. More changes = more action happening.
              </p>
            </div>

            <div className="p-4 bg-snow rounded-lg border border-mist">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xl">📊</span>
                <span className="font-semibold text-graphite">Amplitude</span>
              </div>
              <p className="text-sm text-slate">
                How big the swings are. Large probability swings mean dramatic moments.
              </p>
            </div>

            <div className="p-4 bg-snow rounded-lg border border-mist">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xl">⚡</span>
                <span className="font-semibold text-graphite">Vitals</span>
              </div>
              <p className="text-sm text-slate">
                How close the game is overall. Tight games are more exciting than blowouts.
              </p>
            </div>

            <div className="p-4 bg-snow rounded-lg border border-mist">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xl">🔄</span>
                <span className="font-semibold text-graphite">Lead Changes</span>
              </div>
              <p className="text-sm text-slate">
                How many times the favorite flipped. Each flip adds to the drama.
              </p>
            </div>
          </div>

          <div className="mt-4 p-4 bg-amber-50 rounded-lg border border-amber-200">
            <p className="text-sm text-amber-800">
              <strong>Late-game bonus:</strong> Swings in the final moments of a game
              count extra. A last-second comeback is more exciting than an early lead change!
            </p>
          </div>
        </div>
      </section>

      {/* Live vs Completed */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-graphite flex items-center gap-2">
          <span>🔴</span> Live vs Final Pulse
        </h2>
        <div className="bg-white rounded-xl p-6 border border-mist shadow-sm space-y-4">
          <div className="flex gap-4">
            <div className="flex-1 p-4 bg-emerald-50 rounded-lg border border-emerald-200">
              <div className="font-semibold text-emerald-700 mb-2">
                🟢 During Live Games
              </div>
              <p className="text-sm text-emerald-800">
                Pulse updates every 30 seconds as new odds come in. Watch it climb
                during exciting moments!
              </p>
            </div>
            <div className="flex-1 p-4 bg-slate-50 rounded-lg border border-slate-200">
              <div className="font-semibold text-slate-700 mb-2">
                ✅ After Final
              </div>
              <p className="text-sm text-slate-600">
                The final Pulse score reflects the entire game. Use it to find
                the best highlights to rewatch.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-graphite flex items-center gap-2">
          <span>❓</span> Common Questions
        </h2>
        <div className="space-y-3">
          <details className="bg-white rounded-xl border border-mist shadow-sm group">
            <summary className="p-4 cursor-pointer font-semibold text-graphite flex items-center justify-between">
              Does a high Pulse mean the underdog won?
              <span className="text-slate group-open:rotate-180 transition-transform">▼</span>
            </summary>
            <div className="px-4 pb-4 text-slate text-sm">
              Not necessarily! Pulse measures excitement, not upsets. A game can have
              high Pulse even if the favorite wins—as long as it was a close, dramatic contest.
            </div>
          </details>

          <details className="bg-white rounded-xl border border-mist shadow-sm group">
            <summary className="p-4 cursor-pointer font-semibold text-graphite flex items-center justify-between">
              Why doesn&apos;t every game have a Pulse score?
              <span className="text-slate group-open:rotate-180 transition-transform">▼</span>
            </summary>
            <div className="px-4 pb-4 text-slate text-sm">
              We need enough odds data throughout the game to calculate Pulse accurately.
              Games that just started or have limited betting activity won&apos;t have a score yet.
            </div>
          </details>

          <details className="bg-white rounded-xl border border-mist shadow-sm group">
            <summary className="p-4 cursor-pointer font-semibold text-graphite flex items-center justify-between">
              Is Pulse the same across all sports?
              <span className="text-slate group-open:rotate-180 transition-transform">▼</span>
            </summary>
            <div className="px-4 pb-4 text-slate text-sm">
              Yes! Pulse is calibrated to work across sports. A Pulse of 80 in basketball
              represents similar excitement to a Pulse of 80 in football or hockey.
            </div>
          </details>
        </div>
      </section>

      {/* Hall of Fame Link */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-graphite flex items-center gap-2">
          <span>🏆</span> Pulse Hall of Fame
        </h2>
        <div className="bg-white rounded-xl p-6 border border-mist shadow-sm">
          <p className="text-slate mb-4">
            Curious which games had the highest (and lowest) Pulse scores ever?
            Check out our all-time rankings to discover legendary thrillers and
            forgettable blowouts.
          </p>
          <Link
            href="/pulse/hall-of-fame"
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
          className="inline-flex items-center gap-2 bg-graphite text-white px-6 py-3 rounded-full font-semibold hover:bg-graphite/90 transition-colors"
        >
          <span>🎯</span>
          Find Exciting Games Now
        </Link>
      </div>
    </div>
  );
}
