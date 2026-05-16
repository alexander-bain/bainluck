"use client";

import { useState, useEffect, useCallback } from "react";
import useSWR from "swr";
import { SOURCES, probColor, probLabel, sparkFrom } from "./data";
import type { FeaturedMarket } from "./data";
import { fetchWeatherFeatured } from "@/lib/weatherApi";
import Sparkline from "./Sparkline";
import { SourceBadge } from "./SourceBadge";
import ProbabilityNumber from "./ProbabilityNumber";

const fadeUpKeyframes = `
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(12px); }
  to   { opacity: 1; transform: translateY(0); }
}
`;

function HeroCardSkeleton() {
  return (
    <div
      className="relative bg-surface-card rounded-[18px] border border-surface-border overflow-hidden"
      style={{ padding: 28, minHeight: 260 }}
    >
      <div className="absolute top-0 left-0 right-0 h-1 bg-gray-200 animate-pulse" />
      <div className="h-3 w-24 bg-gray-200 rounded animate-pulse mb-4" />
      <div className="h-5 w-full bg-gray-200 rounded animate-pulse mb-2" />
      <div className="h-5 w-3/4 bg-gray-200 rounded animate-pulse mb-5" />
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="h-16 w-24 bg-gray-200 rounded animate-pulse" />
          <div className="flex items-center gap-2 mt-1.5">
            <div className="h-5 w-14 bg-gray-200 rounded-full animate-pulse" />
            <div className="h-5 w-16 bg-gray-200 rounded-full animate-pulse" />
          </div>
        </div>
        <div className="w-28 h-12 bg-gray-100 rounded animate-pulse" />
      </div>
      <div className="mt-4 pt-3 border-t border-dashed border-surface-border">
        <div className="h-3 w-28 bg-gray-200 rounded animate-pulse" />
      </div>
    </div>
  );
}

export default function WeatherHero() {
  const [idx, setIdx] = useState(0);
  const { data: liveItems } = useSWR("weather-featured", fetchWeatherFeatured, { refreshInterval: 300000 });
  const items = (liveItems as FeaturedMarket[])?.length ? (liveItems as FeaturedMarket[]) : null;
  const loading = !items;

  const advance = useCallback(() => {
    if (!items) return;
    setIdx((prev) => (prev + 1) % items.length);
  }, [items]);

  useEffect(() => {
    const id = setInterval(advance, 5500);
    return () => clearInterval(id);
  }, [advance]);

  const current = items?.[idx];
  const src = current ? SOURCES[current.src] : null;
  const spark = current ? sparkFrom(idx * 7 + 3, current.prob) : [];

  return (
    <section className="mb-10 px-4 md:px-6 pt-6">
      <style>{fadeUpKeyframes}</style>

      <div className="max-w-[1280px] mx-auto grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-7">
        {/* Left — headline */}
        <div className="flex flex-col justify-center">
          {/* Pill */}
          <div className="flex items-center gap-2 mb-5">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold tracking-wide bg-emerald-50 text-emerald-700">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
              </span>
              Weather markets · Live
            </span>
          </div>

          {/* Headline */}
          <h1
            className="text-text-primary mb-3 text-3xl md:text-4xl lg:text-[52px]"
            style={{ fontWeight: 600, letterSpacing: "-0.028em", lineHeight: 1.08 }}
          >
            What are the{" "}
            <span className="text-accent-brand">odds</span> it rains tomorrow?
          </h1>

          {/* Subtitle */}
          <p className="text-text-secondary text-lg max-w-md mb-6">
            Weather markets translated into plain probabilities. Rain, temperature, hurricanes, climate &mdash; updated live.
          </p>

          {/* Dots */}
          {!loading && (
            <div className="flex gap-2">
              {items.map((_, i) => (
                <button
                  key={i}
                  onClick={() => setIdx(i)}
                  aria-label={`Featured market ${i + 1}`}
                  className="transition-all duration-200"
                  style={{
                    width: i === idx ? 28 : 10,
                    height: 10,
                    borderRadius: 5,
                    backgroundColor: i === idx ? "#3B82F6" : "#D1D5DB",
                  }}
                />
              ))}
            </div>
          )}
        </div>

        {/* Right — featured card or skeleton */}
        {loading || !current || !src ? (
          <HeroCardSkeleton />
        ) : (
          <div
            key={idx}
            className="relative bg-surface-card rounded-[18px] border border-surface-border overflow-hidden"
            style={{
              padding: 28,
              minHeight: 260,
              animation: "fadeUp 0.4s ease-out both",
            }}
          >
            {/* Top colored bar */}
            <div
              className="absolute top-0 left-0 right-0"
              style={{ height: 4, backgroundColor: src.color }}
            />

            {/* Kicker */}
            <div className="flex items-center gap-2 mb-4">
              <span
                className="text-xs font-semibold uppercase tracking-wider"
                style={{ color: src.fg }}
              >
                Featured · {current.tag}
              </span>
            </div>

            {/* Question */}
            <p className="text-text-primary text-lg font-semibold leading-snug mb-5">
              {current.q}
            </p>

            {/* Probability + sparkline row */}
            <div className="flex items-end justify-between gap-4">
              <div>
                <ProbabilityNumber value={current.prob} size={64} />
                <div className="flex items-center gap-2 mt-1.5">
                  <span
                    className="text-xs font-semibold px-2 py-0.5 rounded-full"
                    style={{
                      color: probColor(current.prob),
                      backgroundColor: `${probColor(current.prob)}15`,
                    }}
                  >
                    {probLabel(current.prob)}
                  </span>
                  <SourceBadge src={current.src} />
                </div>
              </div>

              {/* Sparkline */}
              <div className="w-28 h-12 flex-shrink-0">
                <Sparkline data={spark} color={probColor(current.prob)} />
              </div>
            </div>

            {/* Resolution date */}
            <div className="mt-4 pt-3 border-t border-dashed border-surface-border">
              <span className="text-xs text-text-muted font-mono">
                Resolves {current.closes}
              </span>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
