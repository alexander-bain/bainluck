"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Link from "next/link";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { fetchCalibration } from "@/lib/api";

/* ── Intersection Observer hook for scroll-triggered animations ── */
function useScrollReveal(threshold = 0.15) {
  const ref = useRef<HTMLDivElement>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
          observer.unobserve(el);
        }
      },
      { threshold }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [threshold]);

  return { ref, isVisible };
}

/* ── Animated section wrapper ── */
function RevealSection({
  children,
  className = "",
  delay = 0,
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
}) {
  const { ref, isVisible } = useScrollReveal(0.1);
  return (
    <div
      ref={ref}
      className={`transition-all duration-700 ease-out ${
        isVisible
          ? "opacity-100 translate-y-0"
          : "opacity-0 translate-y-6"
      } ${className}`}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </div>
  );
}

/* ── Animated counter for "By the Numbers" ── */
function AnimatedNumber({ value, suffix = "" }: { value: string; suffix?: string }) {
  const { ref, isVisible } = useScrollReveal(0.3);
  const [displayed, setDisplayed] = useState("0");
  const numericPart = value.replace(/[^0-9.]/g, "");
  const prefix = value.replace(/[0-9.,]+.*/, "");

  useEffect(() => {
    if (!isVisible) return;
    const target = parseFloat(numericPart);
    if (isNaN(target)) {
      setDisplayed(value);
      return;
    }
    const duration = 1200;
    const steps = 40;
    const increment = target / steps;
    let current = 0;
    let step = 0;
    const timer = setInterval(() => {
      step++;
      current = Math.min(current + increment, target);
      if (target >= 1000) {
        setDisplayed(
          prefix + Math.round(current).toLocaleString() + suffix
        );
      } else if (target >= 10) {
        setDisplayed(prefix + Math.round(current).toString() + suffix);
      } else {
        setDisplayed(prefix + current.toFixed(1) + suffix);
      }
      if (step >= steps) {
        setDisplayed(value);
        clearInterval(timer);
      }
    }, duration / steps);
    return () => clearInterval(timer);
  }, [isVisible, value, numericPart, prefix, suffix]);

  return <span ref={ref}>{displayed}</span>;
}

export default function AboutPage() {
  usePageTracking({ pageType: "about", pageTitle: "About Bain Luck" });
  useScrollDepth({ pageType: "about" });
  useEngagementTime({ pageType: "about" });

  const [techOpen, setTechOpen] = useState(false);
  const [caseStudyOpen, setCaseStudyOpen] = useState(true);

  // Fetch real stats from calibration API
  const [stats, setStats] = useState({
    sources: "8",
    markets: "130K+",
    outcomes: "474K+",
    liveUpdate: "~32s",
  });

  const loadStats = useCallback(async () => {
    try {
      const data = await fetchCalibration();
      if (data.total_outcomes > 0) {
        const mkt =
          data.total_markets >= 1000
            ? `${Math.round(data.total_markets / 1000)}K+`
            : `${data.total_markets}`;
        const out =
          data.total_outcomes >= 1000
            ? `${Math.round(data.total_outcomes / 1000)}K+`
            : `${data.total_outcomes}`;
        setStats((prev) => ({ ...prev, markets: mkt, outcomes: out }));
      }
    } catch {
      // keep defaults
    }
  }, []);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  const categories = [
    { emoji: "\u{1F3C0}", label: "Sports", desc: "NBA, NFL, MLB, NHL, Soccer, Golf, MMA" },
    { emoji: "\u{1F4C8}", label: "Prediction Markets", desc: "Kalshi + Polymarket, unified" },
    { emoji: "\u{1F326}\u{FE0F}", label: "Weather", desc: "Rainfall, temperature, tornado bets" },
    { emoji: "\u{1F4B0}", label: "Economics", desc: "Fed rates, GDP, inflation markets" },
    { emoji: "\u{1F5F3}\u{FE0F}", label: "Politics", desc: "Elections, policy, geopolitics" },
    { emoji: "\u{1F3AC}", label: "Entertainment", desc: "Awards, box office, culture" },
  ];

  return (
    <div className="max-w-3xl mx-auto space-y-12 px-4 sm:px-6">
      {/* ── Hero ── */}
      <RevealSection>
        <div className="text-center space-y-6 pb-10 border-b border-surface-border">
          <div className="text-6xl sm:text-7xl">🍀</div>
          <h1 className="text-display text-text-primary">Bain Luck</h1>
          <p className="text-body text-text-secondary max-w-xl mx-auto leading-relaxed">
            The most engaging way to explore what the world thinks will happen.
          </p>
          <div className="bg-surface-deep rounded-2xl p-6 border border-surface-border max-w-sm mx-auto shadow-card">
            <div className="flex items-center justify-center gap-8">
              <div className="text-center">
                <div className="text-prob-xl font-black text-text-primary font-mono tracking-tight">
                  60%
                </div>
                <div className="text-micro text-text-muted mt-1.5">Celtics</div>
              </div>
              <div className="text-title-3 text-text-muted font-light">vs</div>
              <div className="text-center">
                <div className="text-prob-xl font-black text-text-secondary font-mono tracking-tight">
                  40%
                </div>
                <div className="text-micro text-text-muted mt-1.5">76ers</div>
              </div>
            </div>
            <p className="text-micro text-text-muted text-center mt-4">
              Not &ldquo;-150 / +130&rdquo; &mdash; just probabilities.
            </p>
          </div>
        </div>
      </RevealSection>

      {/* ── Case Studies (lead with the hook) ── */}
      <RevealSection>
        <section className="space-y-4">
          <button
            onClick={() => setCaseStudyOpen(!caseStudyOpen)}
            className="flex items-center gap-2 text-title-2 text-text-primary hover:text-accent-brand transition-colors duration-200 group"
          >
            <span
              className={`transition-transform duration-200 text-text-muted group-hover:text-accent-brand ${
                caseStudyOpen ? "rotate-90" : ""
              }`}
            >
              ▸
            </span>
            Why Probability Matters
          </button>
          <div
            className={`grid transition-all duration-500 ease-out ${
              caseStudyOpen
                ? "grid-rows-[1fr] opacity-100"
                : "grid-rows-[0fr] opacity-0"
            }`}
          >
            <div className="overflow-hidden">
              <div className="space-y-5 pt-1">
                {/* Story 1: Alcaraz */}
                <div className="bg-surface-card rounded-xl p-6 border border-surface-border shadow-card space-y-3">
                  <p className="text-micro tracking-wider text-accent-brand uppercase font-semibold">
                    Case Study
                  </p>
                  <h3 className="text-body-strong text-text-primary">
                    Winning big, then barely surviving
                  </h3>
                  <p className="text-caption text-text-secondary leading-relaxed">
                    2026 Australian Open semifinal. Carlos Alcaraz entered as the
                    underdog at roughly{" "}
                    <strong className="text-text-primary">
                      20% win probability
                    </strong>
                    . He won the first two sets and surged past 85%. Then an
                    adductor injury struck. His probability crashed through volatile
                    swings across sets 3 and 4 as Zverev fought back to level the
                    match. In the decisive fifth set, Alcaraz broke back and won
                    7-5. The final scoreline &mdash; 3 sets to 2 &mdash; looks
                    close. The probability chart on Kalshi ($27M volume) shows the
                    real drama: wild swings from underdog to dominant to desperate
                    to champion.
                  </p>
                  <p className="text-micro text-text-muted">
                    Score: Alcaraz 6-4, 7-6, 6-7, 6-7, 7-5. Source: Kalshi market
                    kxatpmatch-26jan29alczve.
                  </p>
                </div>

                {/* Story 2: Masters */}
                <div className="bg-surface-card rounded-xl p-6 border border-surface-border shadow-card space-y-3">
                  <p className="text-micro tracking-wider text-accent-brand uppercase font-semibold">
                    Case Study
                  </p>
                  <h3 className="text-body-strong text-text-primary">
                    The leaderboard hides the real favorites
                  </h3>
                  <p className="text-caption text-text-secondary leading-relaxed">
                    2025 Masters, end of Round 1. Rory McIlroy sat T1 on the
                    leaderboard. But the prediction market didn&apos;t just agree
                    with the leaderboard &mdash; it saw{" "}
                    <em>how much</em> more likely McIlroy was to win than the other
                    co-leaders. McIlroy held{" "}
                    <strong className="text-text-primary">
                      24.4% win probability
                    </strong>
                    , while co-leader Sam Burns had just 8.6%. Meanwhile, Scottie
                    Scheffler sat T6 &mdash; a shot back &mdash; but the market
                    gave him 19.0%, more than double most players above him.
                    McIlroy went on to win. The leaderboard showed positions;
                    probability showed conviction.
                  </p>
                  <p className="text-micro text-text-muted">
                    Source: DataGolf win probability model + Kalshi futures.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>
      </RevealSection>

      {/* ── What You Can Explore ── */}
      <RevealSection>
        <section className="space-y-5">
          <h2 className="text-title-1 text-text-primary">What You Can Explore</h2>
          <p className="text-body text-text-secondary">
            We aggregate prediction markets and betting odds across every
            category &mdash; not just sports.
          </p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {categories.map((c, i) => (
              <RevealSection key={c.label} delay={i * 80}>
                <div className="p-4 bg-surface-card rounded-xl border border-surface-border shadow-card hover:shadow-card-hover hover:-translate-y-0.5 transition-all duration-300">
                  <div className="text-2xl mb-2">{c.emoji}</div>
                  <div className="text-caption-strong text-text-primary">
                    {c.label}
                  </div>
                  <div className="text-micro text-text-secondary mt-1">
                    {c.desc}
                  </div>
                </div>
              </RevealSection>
            ))}
          </div>
        </section>
      </RevealSection>

      {/* ── Calibration CTA ── */}
      <RevealSection>
        <section>
          <Link
            href="/calibration"
            className="block bg-surface-card rounded-2xl p-6 sm:p-8 border border-surface-border shadow-card hover:shadow-card-hover hover:-translate-y-0.5 transition-all duration-300 group"
          >
            <div className="flex items-start gap-4 sm:gap-5">
              <div className="text-3xl sm:text-4xl flex-shrink-0">📊</div>
              <div className="flex-1 min-w-0">
                <h2 className="text-title-2 text-text-primary group-hover:text-accent-brand transition-colors">
                  Do Prediction Markets Predict Anything?
                </h2>
                <p className="text-caption text-text-secondary mt-2 leading-relaxed">
                  We analyzed {stats.outcomes} resolved outcomes across Kalshi,
                  Polymarket, and sportsbooks. When markets say something has a
                  30% chance, does it really happen 30% of the time?
                </p>
                <span className="inline-flex items-center gap-1.5 text-caption-strong text-accent-brand mt-4">
                  View calibration report
                  <svg
                    className="w-4 h-4 group-hover:translate-x-1 transition-transform duration-200"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={2}
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3"
                    />
                  </svg>
                </span>
              </div>
            </div>
          </Link>
        </section>
      </RevealSection>

      {/* ── How It Works ── */}
      <RevealSection>
        <section className="space-y-5">
          <h2 className="text-title-1 text-text-primary">How It Works</h2>
          <div className="bg-surface-card rounded-2xl p-6 sm:p-8 border border-surface-border shadow-card space-y-5">
            <p className="text-body text-text-secondary leading-relaxed">
              We ingest data from{" "}
              <strong className="text-text-primary">8 sources</strong> &mdash;
              20+ sportsbooks via The Odds API, prediction markets (Kalshi,
              Polymarket), ESPN, MLB Stats API, DataGolf, and proprietary stat
              models &mdash; then blend them into a single probability using
              weighted multi-source aggregation.
            </p>
            <p className="text-body text-text-secondary leading-relaxed">
              You see what <em>the market as a whole</em> thinks will happen, not
              just one bookmaker&apos;s opinion. Source attribution is always
              visible &mdash; tap any probability to see where it comes from.
            </p>
            <div className="bg-surface-deep rounded-xl p-5 border border-surface-border">
              {[
                { label: "Betting Odds (20+ books)", value: "61%" },
                { label: "ESPN Win Probability", value: "58%" },
                { label: "Kalshi", value: "63%" },
              ].map((row) => (
                <div
                  key={row.label}
                  className="flex items-center justify-between py-2.5 text-caption text-text-muted"
                >
                  <span>{row.label}</span>
                  <span className="font-mono font-medium">{row.value}</span>
                </div>
              ))}
              <div className="flex items-center justify-between border-t border-surface-border pt-3 mt-1">
                <span className="text-caption-strong text-text-primary">
                  Bain Luck Aggregate
                </span>
                <span className="font-mono font-bold text-body text-text-primary">
                  60%
                </span>
              </div>
            </div>
          </div>
        </section>
      </RevealSection>

      {/* ── Discover Feed ── */}
      <RevealSection>
        <section className="space-y-5">
          <h2 className="text-title-1 text-text-primary">The Discover Feed</h2>
          <div className="bg-surface-card rounded-2xl p-6 sm:p-8 border border-surface-border shadow-card space-y-5">
            <p className="text-body text-text-secondary leading-relaxed">
              Browse interesting predictions across every category. Each card
              shows a probability &mdash; guess{" "}
              <strong className="text-text-primary">Higher or Lower</strong>,
              then see where you stack up against the market.
            </p>
            <div className="flex flex-wrap gap-2.5">
              {[
                "Daily Challenges",
                "Prediction Streaks",
                "Category Filters",
                "Shareable Results",
              ].map((f) => (
                <span
                  key={f}
                  className="px-3.5 py-1.5 bg-surface-deep rounded-full text-micro text-text-secondary border border-surface-border hover:border-accent-brand hover:text-accent-brand transition-colors duration-200 cursor-default"
                >
                  {f}
                </span>
              ))}
            </div>
            <Link
              href="/discover"
              className="inline-flex items-center gap-1.5 text-caption-strong text-accent-brand hover:underline group"
            >
              Try the Discover feed
              <svg
                className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform duration-200"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2.5}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3"
                />
              </svg>
            </Link>
          </div>
        </section>
      </RevealSection>

      {/* ── By the Numbers ── */}
      <RevealSection>
        <section className="space-y-5">
          <h2 className="text-title-1 text-text-primary">By the Numbers</h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { value: stats.sources, label: "Data Sources" },
              { value: stats.markets, label: "Markets Tracked" },
              { value: "20+", label: "Sportsbooks" },
              { value: stats.liveUpdate, label: "Live Updates" },
            ].map((s, i) => (
              <RevealSection key={s.label} delay={i * 100}>
                <div className="bg-surface-card rounded-xl p-5 border border-surface-border shadow-card hover:shadow-card-hover transition-shadow duration-300 text-center">
                  <div className="text-title-1 font-black text-text-primary font-mono">
                    <AnimatedNumber value={s.value} />
                  </div>
                  <div className="text-micro text-text-muted mt-1.5">
                    {s.label}
                  </div>
                </div>
              </RevealSection>
            ))}
          </div>
        </section>
      </RevealSection>

      {/* ── Under the Hood ── */}
      <RevealSection>
        <section className="space-y-4">
          <button
            onClick={() => setTechOpen(!techOpen)}
            className="flex items-center gap-2 text-title-2 text-text-primary hover:text-accent-brand transition-colors duration-200 group"
          >
            <span
              className={`transition-transform duration-200 text-text-muted group-hover:text-accent-brand ${
                techOpen ? "rotate-90" : ""
              }`}
            >
              ▸
            </span>
            Under the Hood
          </button>
          <div
            className={`grid transition-all duration-500 ease-out ${
              techOpen
                ? "grid-rows-[1fr] opacity-100"
                : "grid-rows-[0fr] opacity-0"
            }`}
          >
            <div className="overflow-hidden">
              <div className="space-y-4 pt-1">
                <p className="text-caption text-text-muted">
                  Built end-to-end as a solo project &mdash; FastAPI/Postgres
                  backend, Next.js web, SwiftUI iOS/macOS.
                </p>
                <div className="grid gap-4 sm:grid-cols-1">
                  {[
                    {
                      title: "Semantic Matching",
                      body: `The core technical challenge: Kalshi lists “Will Aaron Judge hit 1+ HR Tuesday?” while Polymarket has “Yankees vs Red Sox: Judge HR yes/no” — same bet, completely different formats. A 4-layer matching system (event existence → market linking → futures surfacing → market completeness) with independent audits at each layer. Uses GPT-4o-mini for classification, ticker prefix heuristics, and structured matching (sport + time window + team identity). Matching accuracy is treated as a measurable, hill-climbable surface — not vibes.`,
                    },
                    {
                      title: "Multi-Source Aggregation",
                      body: `Weighted blending across 8 sources (betting 3.0, ESPN 1.5, stat model 1.0, Kalshi/Polymarket 0.8). Resilience-by-design: when The Odds API exhausted its 5M-request monthly quota in March 2026, the system continued operating on ESPN, Kalshi, and Polymarket alone without going dark.`,
                    },
                    {
                      title: "Production Engineering",
                      body: `3,500+ tests. Celery dual workers (realtime + background) with per-market commit to avoid deadlocks. Redis circuit breaker enforces quota budgets (Normal → LIVE_ONLY → FULL_STOP). Auto-deploy from GitHub to Heroku + Vercel. Audit-driven development: every data-quality bug gets a check added; audits run before and after each fix.`,
                    },
                  ].map((card) => (
                    <div
                      key={card.title}
                      className="bg-surface-card rounded-xl p-5 border border-surface-border shadow-card hover:shadow-card-hover transition-shadow duration-300 space-y-3"
                    >
                      <h3 className="text-caption-strong text-text-primary">
                        {card.title}
                      </h3>
                      <p className="text-micro text-text-secondary leading-relaxed">
                        {card.body}
                      </p>
                    </div>
                  ))}
                </div>
                <div className="bg-surface-deep rounded-xl p-5 border border-surface-border">
                  <p className="text-micro text-text-muted leading-relaxed">
                    <strong className="text-text-secondary">Tech stack:</strong>{" "}
                    FastAPI (Python 3.11+), PostgreSQL, Celery + Redis, Next.js 14,
                    SwiftUI (iOS + macOS), Alembic migrations. Hosted on Heroku
                    (backend) + Vercel (frontend).
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>
      </RevealSection>

      {/* ── Philosophy ── */}
      <RevealSection>
        <section className="space-y-5">
          <h2 className="text-title-1 text-text-primary">Philosophy</h2>
          <div className="bg-surface-card rounded-2xl p-6 sm:p-8 border border-surface-border shadow-card">
            <ul className="space-y-4">
              {[
                {
                  title: "Probability-first",
                  desc: "Every number is a probability, not a moneyline",
                },
                {
                  title: "Fans first",
                  desc: "Built for people who want context, not betting advice",
                },
                {
                  title: "Source transparency",
                  desc: "See where every probability comes from",
                },
                {
                  title: "Cross-source",
                  desc: "Aggregate across all markets, not just one",
                },
                {
                  title: "Insight-first",
                  desc: "Understand probability without placing a bet",
                },
              ].map((item) => (
                <li key={item.title} className="flex gap-3 items-start">
                  <span className="text-accent-brand flex-shrink-0 mt-0.5">
                    <svg
                      className="w-5 h-5"
                      fill="none"
                      viewBox="0 0 24 24"
                      strokeWidth={2.5}
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="m4.5 12.75 6 6 9-13.5"
                      />
                    </svg>
                  </span>
                  <span className="text-caption text-text-secondary">
                    <strong className="text-text-primary">{item.title}</strong>{" "}
                    &mdash; {item.desc}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </section>
      </RevealSection>

      {/* ── Disclaimer ── */}
      <RevealSection>
        <section>
          <div className="bg-surface-deep rounded-2xl p-6 sm:p-8 border border-surface-border">
            <p className="text-caption-strong text-text-primary mb-2">
              Disclaimer
            </p>
            <p className="text-caption text-text-secondary leading-relaxed">
              Bain Luck is for informational and entertainment purposes only. We
              do not encourage or facilitate gambling. Win probabilities are
              derived from publicly available betting market data and prediction
              market prices and do not constitute betting advice. Past
              performance does not guarantee future results.
            </p>
          </div>
        </section>
      </RevealSection>

      {/* ── CTA ── */}
      <RevealSection>
        <div className="text-center pt-2 pb-10">
          <Link
            href="/discover"
            className="inline-flex items-center gap-2.5 bg-text-primary text-surface-deep px-8 py-3.5 rounded-full text-body-strong hover:bg-text-primary/90 hover:shadow-glow hover:scale-[1.02] transition-all duration-300"
          >
            🍀 Start Exploring
          </Link>
        </div>
      </RevealSection>
    </div>
  );
}
