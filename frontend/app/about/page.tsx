"use client";

import Link from "next/link";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";

/**
 * About Page
 *
 * Explains what Bain Luck is and its mission.
 */
export default function AboutPage() {
  usePageTracking({ pageType: 'about', pageTitle: 'About Bain Luck' });
  useScrollDepth({ pageType: 'about' });
  useEngagementTime({ pageType: 'about' });

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      {/* Hero Section */}
      <div className="text-center space-y-4 pb-6 border-b border-surface-border">
        <div className="text-6xl">🍀</div>
        <h1 className="text-title-1 text-text-primary">About Bain Luck</h1>
        <p className="text-lg text-text-secondary max-w-xl mx-auto">
          Making sports betting odds actually understandable.
        </p>
      </div>

      {/* The Problem */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-text-primary flex items-center gap-2">
          <span>🤔</span> The Problem
        </h2>
        <div className="bg-surface-card rounded-xl p-6 border border-surface-border shadow-card space-y-4">
          <p className="text-text-secondary leading-relaxed">
            You&apos;re watching a game and someone asks, &ldquo;What are the odds?&rdquo; You check
            a sportsbook and see: <span className="font-mono bg-slate/10 px-2 py-0.5 rounded">-150 / +130</span>
          </p>
          <p className="text-text-secondary leading-relaxed">
            What does that even mean? Is the favorite likely to win? By how much?
            Should you be excited about this matchup?
          </p>
          <p className="text-text-secondary leading-relaxed">
            Betting odds are designed for gamblers, not fans. They&apos;re confusing,
            inconsistent across regions (American vs. Decimal vs. Fractional),
            and don&apos;t tell you what you actually want to know.
          </p>
        </div>
      </section>

      {/* Our Solution */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-text-primary flex items-center gap-2">
          <span>💡</span> Our Solution
        </h2>
        <div className="bg-surface-card rounded-xl p-6 border border-surface-border shadow-card space-y-4">
          <p className="text-text-secondary leading-relaxed">
            Bain Luck converts those cryptic numbers into simple{" "}
            <strong className="text-text-primary">win probabilities</strong>.
            Instead of &ldquo;-150 / +130&rdquo;, you see:
          </p>

          <div className="bg-surface-deep rounded-lg p-4 border border-surface-border">
            <div className="flex items-center justify-center gap-8">
              <div className="text-center">
                <div className="text-3xl font-bold text-text-primary font-mono">60%</div>
                <div className="text-sm text-text-secondary">Team A</div>
              </div>
              <div className="text-2xl text-text-secondary">vs</div>
              <div className="text-center">
                <div className="text-3xl font-bold text-text-secondary font-mono">40%</div>
                <div className="text-sm text-text-secondary">Team B</div>
              </div>
            </div>
          </div>

          <p className="text-text-secondary leading-relaxed">
            Now you instantly know Team A is favored, but it&apos;s not a lock—Team B
            has a real shot. That&apos;s useful information, presented clearly.
          </p>
        </div>
      </section>

      {/* What We Track */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-text-primary flex items-center gap-2">
          <span>📊</span> What We Track
        </h2>
        <div className="bg-surface-card rounded-xl p-6 border border-surface-border shadow-card">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="p-4 bg-surface-deep rounded-lg border border-surface-border">
              <div className="text-2xl mb-2">🏈</div>
              <div className="font-semibold text-text-primary">NFL</div>
              <div className="text-sm text-text-secondary">Pro football</div>
            </div>
            <div className="p-4 bg-surface-deep rounded-lg border border-surface-border">
              <div className="text-2xl mb-2">🏀</div>
              <div className="font-semibold text-text-primary">NBA</div>
              <div className="text-sm text-text-secondary">Pro basketball</div>
            </div>
            <div className="p-4 bg-surface-deep rounded-lg border border-surface-border">
              <div className="text-2xl mb-2">⚾</div>
              <div className="font-semibold text-text-primary">MLB</div>
              <div className="text-sm text-text-secondary">Pro baseball</div>
            </div>
            <div className="p-4 bg-surface-deep rounded-lg border border-surface-border">
              <div className="text-2xl mb-2">🏒</div>
              <div className="font-semibold text-text-primary">NHL</div>
              <div className="text-sm text-text-secondary">Pro hockey</div>
            </div>
            <div className="p-4 bg-surface-deep rounded-lg border border-surface-border">
              <div className="text-2xl mb-2">🏈</div>
              <div className="font-semibold text-text-primary">NCAAF</div>
              <div className="text-sm text-text-secondary">College football</div>
            </div>
            <div className="p-4 bg-surface-deep rounded-lg border border-surface-border">
              <div className="text-2xl mb-2">🏀</div>
              <div className="font-semibold text-text-primary">NCAAB</div>
              <div className="text-sm text-text-secondary">College basketball</div>
            </div>
          </div>

          <p className="text-sm text-text-secondary mt-4 text-center">
            More sports coming soon!
          </p>
        </div>
      </section>

      {/* Pulse */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-text-primary flex items-center gap-2">
          <span>💓</span> Pulse: Our Excitement Metric
        </h2>
        <div className="bg-gradient-to-br from-red-50 to-orange-50 rounded-xl p-6 border border-orange-200 shadow-card space-y-4">
          <p className="text-text-secondary leading-relaxed">
            We don&apos;t just show you odds—we help you find the{" "}
            <strong className="text-text-primary">most exciting games</strong>.
          </p>
          <p className="text-text-secondary leading-relaxed">
            The <strong className="text-text-primary">Excitement Index</strong> is our
            score (1-100) that measures how thrilling a game is based on the total
            distance win probabilities travel during the game.
          </p>
          <Link
            href="/ei"
            className="inline-flex items-center gap-2 text-orange-700 hover:text-orange-800 font-semibold"
          >
            Learn how the Excitement Index works →
          </Link>
        </div>
      </section>

      {/* Data Sources */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-text-primary flex items-center gap-2">
          <span>🔄</span> Real-Time Data
        </h2>
        <div className="bg-surface-card rounded-xl p-6 border border-surface-border shadow-card space-y-4">
          <p className="text-text-secondary leading-relaxed">
            We aggregate odds from multiple sportsbooks to give you the{" "}
            <strong className="text-text-primary">consensus probability</strong>—what
            the market as a whole thinks will happen, not just one bookmaker&apos;s opinion.
          </p>
          <p className="text-text-secondary leading-relaxed">
            For live games, we update every 30 seconds so you always see the
            current state of play reflected in the probabilities.
          </p>
        </div>
      </section>

      {/* Philosophy */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-text-primary flex items-center gap-2">
          <span>🧭</span> Our Philosophy
        </h2>
        <div className="bg-surface-card rounded-xl p-6 border border-surface-border shadow-card">
          <ul className="space-y-3 text-text-secondary">
            <li className="flex gap-3">
              <span className="text-emerald-500">✓</span>
              <span><strong className="text-text-primary">Clarity over complexity</strong> — Information should be instantly understandable</span>
            </li>
            <li className="flex gap-3">
              <span className="text-emerald-500">✓</span>
              <span><strong className="text-text-primary">Fans first</strong> — Built for people who love sports, not just bettors</span>
            </li>
            <li className="flex gap-3">
              <span className="text-emerald-500">✓</span>
              <span><strong className="text-text-primary">Transparency</strong> — Show the data, not just conclusions</span>
            </li>
            <li className="flex gap-3">
              <span className="text-emerald-500">✓</span>
              <span><strong className="text-text-primary">No gambling advice</strong> — We&apos;re informational only</span>
            </li>
          </ul>
        </div>
      </section>

      {/* Disclaimer */}
      <section className="space-y-4">
        <div className="bg-slate-50 rounded-xl p-6 border border-slate-200 text-sm text-text-secondary">
          <p className="font-semibold text-text-primary mb-2">Disclaimer</p>
          <p className="leading-relaxed">
            Bain Luck is for informational and entertainment purposes only.
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
          className="inline-flex items-center gap-2 bg-text-primary text-surface-deep px-6 py-3 rounded-full font-semibold hover:bg-text-primary/90 transition-colors"
        >
          <span>🍀</span>
          Start Exploring
        </Link>
      </div>
    </div>
  );
}
