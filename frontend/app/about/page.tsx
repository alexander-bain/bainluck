"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Link from "next/link";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { fetchCalibration } from "@/lib/api";
import {
  STORY_ONE_LINER,
  STORY_ANTI_THESIS,
  STORY_BLEND,
  STORY_THESIS,
  STORY_HUMAN_LINE,
  CASE_STUDIES,
} from "@/lib/story-content";
import CaseStudyCard from "@/components/story/CaseStudyCard";

/* ── Intersection Observer hook for scroll-triggered reveals ── */
function useScrollReveal(threshold = 0.1) {
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
        isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-6"
      } ${className}`}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </div>
  );
}

export default function AboutPage() {
  usePageTracking({ pageType: "about", pageTitle: "About Bain Luck" });
  useScrollDepth({ pageType: "about" });
  useEngagementTime({ pageType: "about" });

  // Live calibration figure so the public proof line stays honest.
  const [proof, setProof] = useState<{ points: string | null; outcomes: string | null }>({
    points: null,
    outcomes: null,
  });

  const loadProof = useCallback(async () => {
    try {
      const data = await fetchCalibration();
      const worst = (data.by_source || [])
        .map((s) => s.ece)
        .filter((e): e is number => typeof e === "number");
      const headline = data.mce_closing_line;
      const pts =
        typeof headline === "number"
          ? headline.toFixed(1)
          : worst.length
          ? Math.max(...worst).toFixed(1)
          : null;
      const out =
        data.total_outcomes && data.total_outcomes >= 1000
          ? `${(data.total_outcomes / 1_000_000).toFixed(1)}M`
          : data.total_outcomes
          ? `${data.total_outcomes}`
          : null;
      setProof({ points: pts, outcomes: out });
    } catch {
      // keep the editorial fallback copy
    }
  }, []);

  useEffect(() => {
    loadProof();
  }, [loadProof]);

  const categories = [
    { emoji: "\u{1F3C0}", label: "Sports", desc: "NBA, NFL, MLB, NHL, Soccer, Golf, MMA" },
    { emoji: "\u{1F4C8}", label: "Prediction Markets", desc: "Kalshi + Polymarket, unified" },
    { emoji: "\u{1F326}\u{FE0F}", label: "Weather", desc: "Rain, temperature, storms" },
    { emoji: "\u{1F4B0}", label: "Economics", desc: "Fed rates, GDP, inflation" },
    { emoji: "\u{1F5F3}\u{FE0F}", label: "Politics", desc: "Elections, policy, geopolitics" },
    { emoji: "\u{1F3AC}", label: "Entertainment", desc: "Awards, box office, culture" },
  ];

  return (
    <div className="max-w-3xl mx-auto space-y-14 px-4 sm:px-6">
      {/* ── 1. THE ONE-LINER ── */}
      <RevealSection>
        <div className="text-center space-y-6 pt-2 pb-10 border-b border-surface-border">
          <div className="text-6xl sm:text-7xl">🍀</div>
          <h1 className="text-display text-text-primary">Bain Luck</h1>
          <p className="text-body text-text-secondary max-w-xl mx-auto leading-relaxed">
            {STORY_ONE_LINER}
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
            {/* This American-odds string STAYS. Alex ruling 2026-07-31.
                It is the counter-example, not a price we are quoting — the
                60/40 above only means something against the thing it replaces,
                and this is the product's founding line. The no-price-format
                rule bans odds used as a SELLING POINT (and L2-221 removed the
                dollar-volume social proof under the same ruling); it does not
                ban naming what we refuse to show. Do not "clean this up". */}
            <p className="text-micro text-text-muted text-center mt-4">
              Not &ldquo;-150 / +130&rdquo; &mdash; just probabilities.
            </p>
          </div>
        </div>
      </RevealSection>

      {/* ── 2. THE ANTI-THESIS ── */}
      <RevealSection>
        <section className="space-y-4">
          <h2 className="text-title-1 text-text-primary">{STORY_ANTI_THESIS.heading}</h2>
          <div className="space-y-3">
            {STORY_ANTI_THESIS.lines.map((line, i) => (
              <p
                key={i}
                className={`text-body leading-relaxed ${
                  i === STORY_ANTI_THESIS.lines.length - 1
                    ? "text-text-primary font-medium"
                    : "text-text-secondary"
                }`}
              >
                {line}
              </p>
            ))}
          </div>
        </section>
      </RevealSection>

      {/* ── 3. THE BLEND (+ public calibration proof) ── */}
      <RevealSection>
        <section className="space-y-5">
          <h2 className="text-title-1 text-text-primary">{STORY_BLEND.heading}</h2>
          <p className="text-body text-text-secondary leading-relaxed">{STORY_BLEND.body}</p>

          {/* the blend, made visual */}
          <div className="bg-surface-card rounded-2xl p-6 border border-surface-border shadow-card">
            <div className="bg-surface-deep rounded-xl p-5 border border-surface-border">
              {[
                { label: "Betting Odds (20+ books)", value: "61%" },
                { label: "ESPN Win Probability", value: "58%" },
                { label: "Kalshi", value: "63%" },
                { label: "Polymarket", value: "59%" },
              ].map((row) => (
                <div
                  key={row.label}
                  className="flex items-center justify-between py-2 text-caption text-text-muted"
                >
                  <span>{row.label}</span>
                  <span className="font-mono font-medium">{row.value}</span>
                </div>
              ))}
              <div className="flex items-center justify-between border-t border-surface-border pt-3 mt-1">
                <span className="text-caption-strong text-text-primary">Bain Luck Aggregate</span>
                <span className="font-mono font-bold text-body text-accent-brand">60%</span>
              </div>
            </div>
          </div>

          {/* public calibration proof */}
          <Link
            href="/calibration"
            className="block bg-surface-card rounded-2xl p-6 border border-surface-border shadow-card hover:shadow-card-hover hover:-translate-y-0.5 transition-all duration-300 group"
          >
            <div className="flex items-start gap-4">
              <div className="text-3xl flex-shrink-0">📊</div>
              <div className="flex-1 min-w-0">
                <p className="text-body text-text-secondary leading-relaxed">
                  <span className="text-text-primary font-medium">
                    {STORY_BLEND.proofLead}
                  </span>{" "}
                  {proof.points && proof.outcomes ? (
                    <>
                      across {proof.outcomes} resolved outcomes, our numbers land within{" "}
                      <span className="text-text-primary font-semibold">
                        {proof.points} points
                      </span>{" "}
                      of what actually happened.
                    </>
                  ) : (
                    STORY_BLEND.proofBody
                  )}
                </p>
                <span className="inline-flex items-center gap-1.5 text-caption-strong text-accent-brand mt-3">
                  {STORY_BLEND.proofCta}
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

      {/* ── 4. THE STORY THESIS + 2 CASE STUDIES ── */}
      <RevealSection>
        <section className="space-y-5">
          <h2 className="text-title-1 text-text-primary">{STORY_THESIS.heading}</h2>
          <p className="text-body text-text-secondary leading-relaxed">{STORY_THESIS.body}</p>
          <div className="space-y-5">
            {CASE_STUDIES.map((study, i) => (
              <RevealSection key={study.id} delay={i * 80}>
                <CaseStudyCard study={study} />
              </RevealSection>
            ))}
          </div>
        </section>
      </RevealSection>

      {/* ── What you can explore ── */}
      <RevealSection>
        <section className="space-y-5">
          <h2 className="text-title-1 text-text-primary">Every category, not just sports</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {categories.map((c, i) => (
              <RevealSection key={c.label} delay={i * 60}>
                <div className="p-4 bg-surface-card rounded-xl border border-surface-border shadow-card hover:shadow-card-hover hover:-translate-y-0.5 transition-all duration-300 h-full">
                  <div className="text-2xl mb-2">{c.emoji}</div>
                  <div className="text-caption-strong text-text-primary">{c.label}</div>
                  <div className="text-micro text-text-secondary mt-1">{c.desc}</div>
                </div>
              </RevealSection>
            ))}
          </div>
        </section>
      </RevealSection>

      {/* ── 5. WHO BUILDS IT ── */}
      <RevealSection>
        <section>
          <div className="bg-surface-deep rounded-2xl p-6 sm:p-8 border border-surface-border text-center">
            <p className="text-body text-text-secondary leading-relaxed max-w-xl mx-auto">
              {STORY_HUMAN_LINE}
            </p>
          </div>
        </section>
      </RevealSection>

      {/* ── Disclaimer + support (compact) ── */}
      <RevealSection>
        <section className="space-y-4">
          <div className="bg-surface-card rounded-2xl p-6 border border-surface-border">
            <p className="text-caption-strong text-text-primary mb-2">The fine print</p>
            <p className="text-caption text-text-secondary leading-relaxed">
              Bain Luck is for information and entertainment only. We don&rsquo;t encourage or
              facilitate gambling. Probabilities are derived from publicly available market data and
              are not betting advice.
            </p>
            <p className="text-caption text-text-muted mt-4">
              Questions or bugs?{" "}
              <a
                href="mailto:bugs@bainluck.com"
                className="text-accent-brand hover:underline font-medium"
              >
                bugs@bainluck.com
              </a>{" "}
              &middot;{" "}
              <Link href="/privacy" className="text-accent-brand hover:underline">
                Privacy Policy
              </Link>
            </p>
          </div>
        </section>
      </RevealSection>

      {/* ── CTA ── */}
      <RevealSection>
        <div className="text-center pt-2 pb-12">
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
