"use client";

import Link from "next/link";

/**
 * About Page
 *
 * Explains what OddsTracker is and its mission.
 */
export default function AboutPage() {
  return (
    <div className="max-w-3xl mx-auto space-y-8">
      {/* Hero Section */}
      <div className="text-center space-y-4 pb-6 border-b border-mist">
        <div className="text-6xl">🎯</div>
        <h1 className="text-title-1 text-graphite">About OddsTracker</h1>
        <p className="text-lg text-slate max-w-xl mx-auto">
          Making sports betting odds actually understandable.
        </p>
      </div>

      {/* The Problem */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-graphite flex items-center gap-2">
          <span>🤔</span> The Problem
        </h2>
        <div className="bg-white rounded-xl p-6 border border-mist shadow-sm space-y-4">
          <p className="text-slate leading-relaxed">
            You're watching a game and someone asks, "What are the odds?" You check
            a sportsbook and see: <span className="font-mono bg-slate/10 px-2 py-0.5 rounded">-150 / +130</span>
          </p>
          <p className="text-slate leading-relaxed">
            What does that even mean? Is the favorite likely to win? By how much?
            Should you be excited about this matchup?
          </p>
          <p className="text-slate leading-relaxed">
            Betting odds are designed for gamblers, not fans. They're confusing,
            inconsistent across regions (American vs. Decimal vs. Fractional),
            and don't tell you what you actually want to know.
          </p>
        </div>
      </section>

      {/* Our Solution */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-graphite flex items-center gap-2">
          <span>💡</span> Our Solution
        </h2>
        <div className="bg-white rounded-xl p-6 border border-mist shadow-sm space-y-4">
          <p className="text-slate leading-relaxed">
            OddsTracker converts those cryptic numbers into simple{" "}
            <strong className="text-graphite">win probabilities</strong>.
            Instead of "-150 / +130", you see:
          </p>

          <div className="bg-snow rounded-lg p-4 border border-mist">
            <div className="flex items-center justify-center gap-8">
              <div className="text-center">
                <div className="text-3xl font-bold text-graphite font-mono">60%</div>
                <div className="text-sm text-slate">Team A</div>
              </div>
              <div className="text-2xl text-slate">vs</div>
              <div className="text-center">
                <div className="text-3xl font-bold text-slate font-mono">40%</div>
                <div className="text-sm text-slate">Team B</div>
              </div>
            </div>
          </div>

          <p className="text-slate leading-relaxed">
            Now you instantly know Team A is favored, but it's not a lock—Team B
            has a real shot. That's useful information, presented clearly.
          </p>
        </div>
      </section>

      {/* What We Track */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-graphite flex items-center gap-2">
          <span>📊</span> What We Track
        </h2>
        <div className="bg-white rounded-xl p-6 border border-mist shadow-sm">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="p-4 bg-snow rounded-lg border border-mist">
              <div className="text-2xl mb-2">🏈</div>
              <div className="font-semibold text-graphite">NFL</div>
              <div className="text-sm text-slate">Pro football</div>
            </div>
            <div className="p-4 bg-snow rounded-lg border border-mist">
              <div className="text-2xl mb-2">🏀</div>
              <div className="font-semibold text-graphite">NBA</div>
              <div className="text-sm text-slate">Pro basketball</div>
            </div>
            <div className="p-4 bg-snow rounded-lg border border-mist">
              <div className="text-2xl mb-2">⚾</div>
              <div className="font-semibold text-graphite">MLB</div>
              <div className="text-sm text-slate">Pro baseball</div>
            </div>
            <div className="p-4 bg-snow rounded-lg border border-mist">
              <div className="text-2xl mb-2">🏒</div>
              <div className="font-semibold text-graphite">NHL</div>
              <div className="text-sm text-slate">Pro hockey</div>
            </div>
            <div className="p-4 bg-snow rounded-lg border border-mist">
              <div className="text-2xl mb-2">🏈</div>
              <div className="font-semibold text-graphite">NCAAF</div>
              <div className="text-sm text-slate">College football</div>
            </div>
            <div className="p-4 bg-snow rounded-lg border border-mist">
              <div className="text-2xl mb-2">🏀</div>
              <div className="font-semibold text-graphite">NCAAB</div>
              <div className="text-sm text-slate">College basketball</div>
            </div>
          </div>

          <p className="text-sm text-slate mt-4 text-center">
            More sports coming soon!
          </p>
        </div>
      </section>

      {/* Pulse */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-graphite flex items-center gap-2">
          <span>💓</span> Pulse: Our Excitement Metric
        </h2>
        <div className="bg-gradient-to-br from-red-50 to-orange-50 rounded-xl p-6 border border-orange-200 shadow-sm space-y-4">
          <p className="text-slate leading-relaxed">
            We don't just show you odds—we help you find the{" "}
            <strong className="text-graphite">most exciting games</strong>.
          </p>
          <p className="text-slate leading-relaxed">
            <strong className="text-graphite">Pulse</strong> is our proprietary
            score (1-100) that measures how thrilling a game is based on
            probability swings, lead changes, and dramatic moments.
          </p>
          <Link
            href="/pulse"
            className="inline-flex items-center gap-2 text-orange-700 hover:text-orange-800 font-semibold"
          >
            Learn how Pulse works →
          </Link>
        </div>
      </section>

      {/* Data Sources */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-graphite flex items-center gap-2">
          <span>🔄</span> Real-Time Data
        </h2>
        <div className="bg-white rounded-xl p-6 border border-mist shadow-sm space-y-4">
          <p className="text-slate leading-relaxed">
            We aggregate odds from multiple sportsbooks to give you the{" "}
            <strong className="text-graphite">consensus probability</strong>—what
            the market as a whole thinks will happen, not just one bookmaker's opinion.
          </p>
          <p className="text-slate leading-relaxed">
            For live games, we update every 30 seconds so you always see the
            current state of play reflected in the probabilities.
          </p>
        </div>
      </section>

      {/* Philosophy */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-graphite flex items-center gap-2">
          <span>🧭</span> Our Philosophy
        </h2>
        <div className="bg-white rounded-xl p-6 border border-mist shadow-sm">
          <ul className="space-y-3 text-slate">
            <li className="flex gap-3">
              <span className="text-emerald-500">✓</span>
              <span><strong className="text-graphite">Clarity over complexity</strong> — Information should be instantly understandable</span>
            </li>
            <li className="flex gap-3">
              <span className="text-emerald-500">✓</span>
              <span><strong className="text-graphite">Fans first</strong> — Built for people who love sports, not just bettors</span>
            </li>
            <li className="flex gap-3">
              <span className="text-emerald-500">✓</span>
              <span><strong className="text-graphite">Transparency</strong> — Show the data, not just conclusions</span>
            </li>
            <li className="flex gap-3">
              <span className="text-emerald-500">✓</span>
              <span><strong className="text-graphite">No gambling advice</strong> — We're informational only</span>
            </li>
          </ul>
        </div>
      </section>

      {/* Disclaimer */}
      <section className="space-y-4">
        <div className="bg-slate-50 rounded-xl p-6 border border-slate-200 text-sm text-slate">
          <p className="font-semibold text-graphite mb-2">Disclaimer</p>
          <p className="leading-relaxed">
            OddsTracker is for informational and entertainment purposes only.
            We do not encourage or facilitate gambling. Win probabilities are
            derived from publicly available betting market data and do not
            constitute betting advice. Past performance does not guarantee
            future results. Please gamble responsibly if you choose to do so.
          </p>
        </div>
      </section>

      {/* CTA */}
      <div className="text-center pt-4 pb-8">
        <Link
          href="/"
          className="inline-flex items-center gap-2 bg-graphite text-white px-6 py-3 rounded-full font-semibold hover:bg-graphite/90 transition-colors"
        >
          <span>🎯</span>
          Start Exploring
        </Link>
      </div>
    </div>
  );
}
