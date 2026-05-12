"use client";

import { useState } from "react";
import Link from "next/link";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";

export default function AboutPage() {
  usePageTracking({ pageType: "about", pageTitle: "About Bain Luck" });
  useScrollDepth({ pageType: "about" });
  useEngagementTime({ pageType: "about" });

  const [techOpen, setTechOpen] = useState(false);

  return (
    <div className="max-w-3xl mx-auto space-y-10">
      {/* Hero */}
      <div className="text-center space-y-5 pb-8 border-b border-surface-border">
        <div className="text-6xl">🍀</div>
        <h1 className="text-title-1 text-text-primary">Bain Luck</h1>
        <p className="text-xl text-text-secondary max-w-2xl mx-auto leading-relaxed">
          The most engaging way to explore what the world thinks will happen.
        </p>
        <div className="bg-surface-deep rounded-xl p-5 border border-surface-border max-w-sm mx-auto">
          <div className="flex items-center justify-center gap-8">
            <div className="text-center">
              <div className="text-4xl font-black text-text-primary font-mono tracking-tight">60%</div>
              <div className="text-xs text-text-muted mt-1">Celtics</div>
            </div>
            <div className="text-lg text-text-muted font-light">vs</div>
            <div className="text-center">
              <div className="text-4xl font-black text-text-secondary font-mono tracking-tight">40%</div>
              <div className="text-xs text-text-muted mt-1">76ers</div>
            </div>
          </div>
          <p className="text-xs text-text-muted text-center mt-3">
            Not &ldquo;-150 / +130&rdquo; &mdash; just probabilities.
          </p>
        </div>
      </div>

      {/* What You Can Explore */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-text-primary">What You Can Explore</h2>
        <p className="text-text-secondary">
          We aggregate prediction markets and betting odds across every category &mdash; not just sports.
        </p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[
            { emoji: "🏀", label: "Sports", desc: "NBA, NFL, MLB, NHL, Soccer, Golf, MMA" },
            { emoji: "📈", label: "Prediction Markets", desc: "Kalshi + Polymarket, unified" },
            { emoji: "🌦️", label: "Weather", desc: "Rainfall, temperature, tornado bets" },
            { emoji: "💰", label: "Economics", desc: "Fed rates, GDP, inflation markets" },
            { emoji: "🗳️", label: "Politics", desc: "Elections, policy, geopolitics" },
            { emoji: "🎬", label: "Entertainment", desc: "Awards, box office, culture" },
          ].map((c) => (
            <div key={c.label} className="p-4 bg-surface-card rounded-xl border border-surface-border">
              <div className="text-2xl mb-1.5">{c.emoji}</div>
              <div className="font-semibold text-text-primary text-sm">{c.label}</div>
              <div className="text-xs text-text-secondary mt-0.5">{c.desc}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Calibration CTA */}
      <section>
        <Link href="/calibration" className="block bg-surface-card rounded-xl p-6 border border-surface-border hover:border-accent-brand transition-colors group">
          <div className="flex items-start gap-4">
            <div className="text-3xl">📊</div>
            <div className="flex-1">
              <h2 className="text-title-3 text-text-primary group-hover:text-accent-brand transition-colors">Do Prediction Markets Predict Anything?</h2>
              <p className="text-sm text-text-secondary mt-1">
                We analyzed 474,000+ resolved outcomes across Kalshi, Polymarket, and sportsbooks.
                When markets say something has a 30% chance, does it really happen 30% of the time?
              </p>
              <span className="inline-flex items-center gap-1 text-sm font-semibold text-accent-brand mt-3">
                View calibration report
                <svg className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" /></svg>
              </span>
            </div>
          </div>
        </Link>
      </section>

      {/* How It Works */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-text-primary">How It Works</h2>
        <div className="bg-surface-card rounded-xl p-6 border border-surface-border shadow-card space-y-4">
          <p className="text-text-secondary leading-relaxed">
            We ingest data from <strong className="text-text-primary">8 sources</strong> &mdash;
            20+ sportsbooks via The Odds API, prediction markets (Kalshi, Polymarket),
            ESPN, MLB Stats API, DataGolf, and proprietary stat models &mdash; then blend
            them into a single probability using weighted multi-source aggregation.
          </p>
          <p className="text-text-secondary leading-relaxed">
            You see what <em>the market as a whole</em> thinks will happen, not just one
            bookmaker&apos;s opinion. Source attribution is always visible &mdash; tap any
            probability to see where it comes from.
          </p>
          <div className="bg-surface-deep rounded-lg p-4 border border-surface-border text-sm text-text-muted">
            <div className="flex items-center justify-between mb-2">
              <span>Betting Odds (20+ books)</span>
              <span className="font-mono">61%</span>
            </div>
            <div className="flex items-center justify-between mb-2">
              <span>ESPN Win Probability</span>
              <span className="font-mono">58%</span>
            </div>
            <div className="flex items-center justify-between mb-2">
              <span>Kalshi</span>
              <span className="font-mono">63%</span>
            </div>
            <div className="flex items-center justify-between border-t border-surface-border pt-2 mt-2">
              <span className="font-semibold text-text-primary">Bain Luck Aggregate</span>
              <span className="font-mono font-bold text-text-primary">60%</span>
            </div>
          </div>
        </div>
      </section>

      {/* Discover Feed */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-text-primary">The Discover Feed</h2>
        <div className="bg-surface-card rounded-xl p-6 border border-surface-border shadow-card space-y-4">
          <p className="text-text-secondary leading-relaxed">
            Browse interesting predictions across every category. Each card shows a probability &mdash;
            guess <strong className="text-text-primary">Higher or Lower</strong>, then see
            where you stack up against the market.
          </p>
          <div className="flex flex-wrap gap-3">
            {["Daily Challenges", "Prediction Streaks", "Category Filters", "Shareable Results"].map((f) => (
              <span key={f} className="px-3 py-1.5 bg-surface-deep rounded-full text-xs font-medium text-text-secondary border border-surface-border">
                {f}
              </span>
            ))}
          </div>
          <Link href="/discover" className="text-sm font-medium text-accent-brand hover:underline">
            Try the Discover feed →
          </Link>
        </div>
      </section>

      {/* By the Numbers */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-text-primary">By the Numbers</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { value: "8", label: "Data Sources" },
            { value: "130K+", label: "Markets Tracked" },
            { value: "20+", label: "Sportsbooks" },
            { value: "~32s", label: "Live Updates" },
          ].map((s) => (
            <div key={s.label} className="bg-surface-card rounded-xl p-4 border border-surface-border text-center">
              <div className="text-2xl font-black text-text-primary font-mono">{s.value}</div>
              <div className="text-xs text-text-muted mt-1">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Under the Hood */}
      <section className="space-y-4">
        <button
          onClick={() => setTechOpen(!techOpen)}
          className="flex items-center gap-2 text-title-2 text-text-primary hover:text-accent-brand transition-colors"
        >
          <span className={`transition-transform ${techOpen ? "rotate-90" : ""}`}>▸</span>
          Under the Hood
        </button>
        {techOpen && (
          <div className="space-y-4">
            <p className="text-sm text-text-muted">
              Built end-to-end as a solo project &mdash; FastAPI/Postgres backend, Next.js web, SwiftUI iOS/macOS.
            </p>
            <div className="grid gap-4 sm:grid-cols-1">
              {/* Semantic Matching */}
              <div className="bg-surface-card rounded-xl p-5 border border-surface-border space-y-3">
                <h3 className="font-semibold text-text-primary text-sm">Semantic Matching</h3>
                <p className="text-xs text-text-secondary leading-relaxed">
                  The core technical challenge: Kalshi lists &ldquo;Will Aaron Judge hit 1+ HR Tuesday?&rdquo;
                  while Polymarket has &ldquo;Yankees vs Red Sox: Judge HR yes/no&rdquo; &mdash; same bet,
                  completely different formats. A 4-layer matching system (event existence → market
                  linking → futures surfacing → market completeness) with independent audits at each
                  layer. Uses GPT-4o-mini for classification, ticker prefix heuristics, and structured
                  matching (sport + time window + team identity). Matching accuracy is treated as a
                  measurable, hill-climbable surface &mdash; not vibes.
                </p>
              </div>
              {/* Multi-Source Aggregation */}
              <div className="bg-surface-card rounded-xl p-5 border border-surface-border space-y-3">
                <h3 className="font-semibold text-text-primary text-sm">Multi-Source Aggregation</h3>
                <p className="text-xs text-text-secondary leading-relaxed">
                  Weighted blending across 8 sources (betting 3.0, ESPN 1.5, stat model 1.0,
                  Kalshi/Polymarket 0.8). Resilience-by-design: when The Odds API exhausted its
                  5M-request monthly quota in March 2026, the system continued operating on ESPN,
                  Kalshi, and Polymarket alone without going dark.
                </p>
              </div>
              {/* Production Engineering */}
              <div className="bg-surface-card rounded-xl p-5 border border-surface-border space-y-3">
                <h3 className="font-semibold text-text-primary text-sm">Production Engineering</h3>
                <p className="text-xs text-text-secondary leading-relaxed">
                  3,350+ tests. Celery dual workers (realtime + background) with per-market
                  commit to avoid deadlocks. Redis circuit breaker enforces quota budgets
                  (Normal → LIVE_ONLY → FULL_STOP). Auto-deploy from GitHub to Heroku + Vercel.
                  Audit-driven development: every data-quality bug gets a check added; audits
                  run before and after each fix.
                </p>
              </div>
            </div>
            <div className="bg-surface-deep rounded-lg p-4 border border-surface-border">
              <p className="text-xs text-text-muted leading-relaxed">
                <strong className="text-text-secondary">Tech stack:</strong> FastAPI (Python 3.11+),
                PostgreSQL, Celery + Redis, Next.js 14, SwiftUI (iOS + macOS), Alembic migrations.
                Hosted on Heroku (backend) + Vercel (frontend).
              </p>
            </div>
          </div>
        )}
      </section>

      {/* Philosophy */}
      <section className="space-y-4">
        <h2 className="text-title-2 text-text-primary">Philosophy</h2>
        <div className="bg-surface-card rounded-xl p-6 border border-surface-border shadow-card">
          <ul className="space-y-3 text-text-secondary text-sm">
            <li className="flex gap-3">
              <span className="text-emerald-500 flex-shrink-0">✓</span>
              <span><strong className="text-text-primary">Probability-first</strong> — Every number is a probability, not a moneyline</span>
            </li>
            <li className="flex gap-3">
              <span className="text-emerald-500 flex-shrink-0">✓</span>
              <span><strong className="text-text-primary">Fans first</strong> — Built for people who want context, not betting advice</span>
            </li>
            <li className="flex gap-3">
              <span className="text-emerald-500 flex-shrink-0">✓</span>
              <span><strong className="text-text-primary">Source transparency</strong> — See where every probability comes from</span>
            </li>
            <li className="flex gap-3">
              <span className="text-emerald-500 flex-shrink-0">✓</span>
              <span><strong className="text-text-primary">Cross-source</strong> — Aggregate across all markets, not just one</span>
            </li>
            <li className="flex gap-3">
              <span className="text-emerald-500 flex-shrink-0">✓</span>
              <span><strong className="text-text-primary">No gambling</strong> — Informational only, always</span>
            </li>
          </ul>
        </div>
      </section>

      {/* Disclaimer */}
      <section>
        <div className="bg-slate-50 rounded-xl p-6 border border-slate-200 text-sm text-text-secondary">
          <p className="font-semibold text-text-primary mb-2">Disclaimer</p>
          <p className="leading-relaxed">
            Bain Luck is for informational and entertainment purposes only.
            We do not encourage or facilitate gambling. Win probabilities are
            derived from publicly available betting market data and prediction
            market prices and do not constitute betting advice. Past performance
            does not guarantee future results.
          </p>
        </div>
      </section>

      {/* CTA */}
      <div className="text-center pt-2 pb-8">
        <Link
          href="/discover"
          className="inline-flex items-center gap-2 bg-text-primary text-surface-deep px-6 py-3 rounded-full font-semibold hover:bg-text-primary/90 transition-colors"
        >
          🍀 Start Exploring
        </Link>
      </div>
    </div>
  );
}
