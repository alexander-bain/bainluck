"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { fetchOscarsData } from "@/lib/api";
import type { OscarsResponse, OscarsCategory } from "@/lib/types";
import { MAJOR_CATEGORIES, PERSON_CATEGORIES, CATEGORY_EMOJI } from "@/lib/oscarsData";
import {
  searchMovie, searchPerson, getTrailers, posterUrl, headshotUrl,
} from "@/lib/tmdb";

// ============================================================================
// Types
// ============================================================================

interface NomineeImage {
  url: string;
  type: "poster" | "headshot";
  tmdbId: number;
}

interface NomineeTrailer {
  youtubeKey: string;
}

// ============================================================================
// Main Page
// ============================================================================

export default function OscarsPage() {
  const [data, setData] = useState<OscarsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [images, setImages] = useState<Record<string, NomineeImage>>({});
  const [trailers, setTrailers] = useState<Record<string, NomineeTrailer>>({});

  // Phase 1: Fetch odds data
  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const result = await fetchOscarsData();
        setData(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load Oscars data");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // Phase 2: Progressive TMDB enrichment
  useEffect(() => {
    if (!data) return;

    async function enrichImages() {
      const searches: Promise<void>[] = [];

      for (const cat of data!.categories) {
        const isPerson = PERSON_CATEGORIES.has(cat.key);
        // Enrich top nominees for major categories, top 3 for craft
        const topN = MAJOR_CATEGORIES.has(cat.key) ? cat.nominees.length : 3;

        for (const nominee of cat.nominees.slice(0, topN)) {
          const cacheKey = `${cat.key}_${nominee.name}`;

          if (isPerson) {
            searches.push(
              searchPerson(nominee.name).then((result) => {
                if (result?.profile_path) {
                  setImages((prev) => ({
                    ...prev,
                    [cacheKey]: {
                      url: headshotUrl(result.profile_path)!,
                      type: "headshot",
                      tmdbId: result.id,
                    },
                  }));
                }
              })
            );
          } else {
            // Extract movie name (strip " - Director" etc.)
            const movieName = nominee.name.split(/\s+[-–]\s+/)[0].trim();
            searches.push(
              searchMovie(movieName, 2025).then(async (result) => {
                if (!result) {
                  // Retry without year constraint
                  const retry = await searchMovie(movieName);
                  if (retry?.poster_path) {
                    setImages((prev) => ({
                      ...prev,
                      [cacheKey]: {
                        url: posterUrl(retry.poster_path)!,
                        type: "poster",
                        tmdbId: retry.id,
                      },
                    }));
                  }
                  return;
                }
                if (result.poster_path) {
                  setImages((prev) => ({
                    ...prev,
                    [cacheKey]: {
                      url: posterUrl(result.poster_path)!,
                      type: "poster",
                      tmdbId: result.id,
                    },
                  }));
                }
                // Fetch trailers for Best Picture nominees
                if (cat.key === "best_picture") {
                  const vids = await getTrailers(result.id);
                  if (vids.length > 0) {
                    setTrailers((prev) => ({
                      ...prev,
                      [cacheKey]: { youtubeKey: vids[0].key },
                    }));
                  }
                }
              })
            );
          }
        }
      }

      await Promise.allSettled(searches);
    }

    enrichImages();
  }, [data]);

  // Derived data
  const bestPicture = data?.categories.find((c) => c.key === "best_picture");
  const majorCategories = data?.categories.filter(
    (c) => c.is_major && c.key !== "best_picture"
  ) || [];
  const craftCategories = data?.categories.filter((c) => !c.is_major) || [];

  return (
    <div className="min-h-screen">
      {/* Hero */}
      <div className="relative overflow-hidden bg-gradient-to-b from-[#1a1408] via-surface-deep to-surface-deep">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_rgba(212,175,55,0.08)_0%,_transparent_70%)]" />
        <div className="relative max-w-4xl mx-auto px-4 pt-8 pb-6 text-center">
          <Link
            href="/"
            className="text-sm text-text-secondary hover:text-text-primary transition-colors mb-4 inline-block"
          >
            &larr; Back to feed
          </Link>
          <div className="text-4xl mb-3">&#x1F3C6;</div>
          <h1 className="text-3xl sm:text-4xl font-bold text-[#D4AF37] tracking-tight">
            98th Academy Awards
          </h1>
          <p className="text-text-secondary mt-2 text-lg">March 2, 2026</p>

          {/* Countdown */}
          <Countdown targetDate="2026-03-02T20:00:00-05:00" />

          <p className="text-xs text-text-muted mt-4">
            Odds from Polymarket &amp; Kalshi
          </p>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-4xl mx-auto px-4 py-6 space-y-10">
        {loading && (
          <div className="text-center py-16 text-text-secondary">
            Loading Oscars data...
          </div>
        )}

        {error && (
          <div className="text-center py-16 text-red-400">{error}</div>
        )}

        {data && !loading && data.categories.length === 0 && (
          <div className="text-center py-16">
            <p className="text-lg text-text-secondary">
              No Oscar markets found yet.
            </p>
            <p className="text-sm text-text-muted mt-1">
              Markets typically appear on Polymarket and Kalshi a few weeks before the ceremony.
            </p>
          </div>
        )}

        {/* Best Picture Spotlight */}
        {bestPicture && (
          <BestPictureSection
            category={bestPicture}
            images={images}
            trailers={trailers}
          />
        )}

        {/* Major Awards */}
        {majorCategories.length > 0 && (
          <section>
            <h2 className="text-title-2 text-text-primary mb-4">
              Major Awards
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {majorCategories.map((cat) => (
                <MajorCategoryCard
                  key={cat.key}
                  category={cat}
                  images={images}
                />
              ))}
            </div>
          </section>
        )}

        {/* Craft Awards */}
        {craftCategories.length > 0 && (
          <section>
            <h2 className="text-title-2 text-text-primary mb-4">
              Craft Awards
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {craftCategories.map((cat) => (
                <CraftCategoryCard key={cat.key} category={cat} />
              ))}
            </div>
          </section>
        )}

        {/* Trivia / Beyond the Awards */}
        {data && data.trivia.length > 0 && (
          <section>
            <h2 className="text-title-2 text-text-primary mb-4">
              Beyond the Awards
            </h2>
            <div className="space-y-3">
              {data.trivia.map((market) => (
                <div
                  key={market.id}
                  className="bg-surface-card rounded-xl border border-surface-border p-4"
                >
                  <h3 className="text-body-strong text-text-primary mb-3">
                    {market.name}
                  </h3>
                  <div className="space-y-2">
                    {market.top_outcomes.map((outcome, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between gap-3"
                      >
                        <span className="text-sm text-text-secondary truncate">
                          {outcome.name}
                        </span>
                        <span className="text-sm font-mono font-bold text-text-primary flex-shrink-0">
                          {outcome.probability
                            ? `${Math.round(outcome.probability * 100)}%`
                            : "-"}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Footer attribution */}
        {data && data.categories.length > 0 && (
          <div className="text-center text-xs text-text-muted pt-4 pb-8">
            Odds powered by Polymarket &amp; Kalshi &middot; Not betting advice
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Countdown Timer
// ============================================================================

function Countdown({ targetDate }: { targetDate: string }) {
  const [timeLeft, setTimeLeft] = useState<{
    days: number;
    hours: number;
    minutes: number;
  } | null>(null);

  useEffect(() => {
    const target = new Date(targetDate).getTime();

    function update() {
      const now = Date.now();
      const diff = target - now;
      if (diff <= 0) {
        setTimeLeft(null);
        return;
      }
      setTimeLeft({
        days: Math.floor(diff / (1000 * 60 * 60 * 24)),
        hours: Math.floor((diff / (1000 * 60 * 60)) % 24),
        minutes: Math.floor((diff / (1000 * 60)) % 60),
      });
    }

    update();
    const interval = setInterval(update, 60_000);
    return () => clearInterval(interval);
  }, [targetDate]);

  if (!timeLeft) return null;

  return (
    <div className="flex items-center justify-center gap-4 mt-4">
      {[
        { value: timeLeft.days, label: "days" },
        { value: timeLeft.hours, label: "hrs" },
        { value: timeLeft.minutes, label: "min" },
      ].map(({ value, label }) => (
        <div key={label} className="text-center">
          <div className="text-2xl sm:text-3xl font-mono font-bold text-[#D4AF37]">
            {String(value).padStart(2, "0")}
          </div>
          <div className="text-xs text-text-muted uppercase tracking-wider">
            {label}
          </div>
        </div>
      ))}
    </div>
  );
}

// ============================================================================
// Best Picture Spotlight
// ============================================================================

function BestPictureSection({
  category,
  images,
  trailers,
}: {
  category: OscarsCategory;
  images: Record<string, NomineeImage>;
  trailers: Record<string, NomineeTrailer>;
}) {
  return (
    <section>
      <div className="flex items-center gap-2 mb-4">
        <h2 className="text-title-2 text-[#D4AF37]">Best Picture</h2>
        {category.market_ids[0] && (
          <Link
            href={`/futures/${category.market_ids[0]}`}
            className="text-xs text-text-muted hover:text-text-secondary transition-colors ml-auto"
          >
            Full market &rarr;
          </Link>
        )}
      </div>

      {/* Poster row — horizontal scroll on mobile */}
      <div className="flex gap-3 overflow-x-auto pb-2 -mx-4 px-4 md:mx-0 md:px-0 md:flex-wrap md:justify-center">
        {category.nominees.map((nominee) => {
          const cacheKey = `best_picture_${nominee.name}`;
          const img = images[cacheKey];
          const trailer = trailers[cacheKey];
          const pct = Math.round(nominee.probability * 100);

          return (
            <div
              key={nominee.name}
              className="flex-shrink-0 w-[120px] md:w-[140px] group"
            >
              {/* Poster */}
              <div className="relative aspect-[2/3] rounded-lg overflow-hidden bg-surface-elevated border border-surface-border group-hover:border-[#D4AF37]/50 transition-colors">
                {img ? (
                  <Image
                    src={img.url}
                    alt={nominee.name}
                    fill
                    className="object-cover transition-opacity duration-500"
                    sizes="140px"
                    unoptimized
                  />
                ) : (
                  <div className="absolute inset-0 flex items-center justify-center text-text-muted">
                    <span className="text-3xl">&#x1F3AC;</span>
                  </div>
                )}

                {/* Rank badge */}
                {nominee.rank <= 3 && (
                  <div className="absolute top-1.5 left-1.5 bg-black/70 backdrop-blur-sm text-[#D4AF37] text-xs font-bold px-1.5 py-0.5 rounded">
                    #{nominee.rank}
                  </div>
                )}

                {/* Trailer button */}
                {trailer && (
                  <a
                    href={`https://www.youtube.com/watch?v=${trailer.youtubeKey}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="absolute bottom-1.5 right-1.5 bg-black/70 backdrop-blur-sm text-white text-xs px-2 py-1 rounded hover:bg-black/90 transition-colors"
                    onClick={(e) => e.stopPropagation()}
                  >
                    &#x25B6; Trailer
                  </a>
                )}
              </div>

              {/* Probability */}
              <div className="mt-2 text-center">
                <div className="text-prob-md font-mono text-text-primary">
                  {pct}%
                </div>
                <div className="text-xs text-text-secondary mt-0.5 line-clamp-2 leading-tight">
                  {nominee.name}
                </div>
                <MovementBadge movement={nominee.movement_24h} />
                <SourceDots sources={nominee.sources} />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// ============================================================================
// Major Category Card
// ============================================================================

function MajorCategoryCard({
  category,
  images,
}: {
  category: OscarsCategory;
  images: Record<string, NomineeImage>;
}) {
  const emoji = CATEGORY_EMOJI[category.key] || "";

  return (
    <Link href={`/futures/${category.market_ids[0]}`}>
      <div className="bg-surface-card rounded-xl border border-surface-border border-l-4 border-l-[#D4AF37] p-4 hover:shadow-card-hover transition-shadow cursor-pointer h-full">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-lg">{emoji}</span>
          <h3 className="text-body-strong text-text-primary">{category.name}</h3>
          <span className="text-xs text-text-muted ml-auto">
            #{category.ceremony_order}
          </span>
        </div>

        <div className="space-y-2.5">
          {category.nominees.slice(0, 5).map((nominee) => {
            const cacheKey = `${category.key}_${nominee.name}`;
            const img = images[cacheKey];
            const pct = Math.round(nominee.probability * 100);
            const isLeader = nominee.rank === 1;

            return (
              <div key={nominee.name} className="flex items-center gap-3">
                {/* Headshot / initial */}
                <div className="w-8 h-8 rounded-full overflow-hidden bg-surface-elevated flex-shrink-0 flex items-center justify-center">
                  {img ? (
                    <Image
                      src={img.url}
                      alt={nominee.name}
                      width={32}
                      height={32}
                      className="object-cover w-full h-full"
                      unoptimized
                    />
                  ) : (
                    <span className="text-xs text-text-muted font-bold">
                      {nominee.name.charAt(0)}
                    </span>
                  )}
                </div>

                {/* Name + bar */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2 mb-0.5">
                    <span
                      className={`text-sm truncate ${
                        isLeader
                          ? "text-text-primary font-semibold"
                          : "text-text-secondary"
                      }`}
                    >
                      {nominee.name}
                    </span>
                    <span className="text-sm font-mono font-bold text-text-primary flex-shrink-0">
                      {pct}%
                    </span>
                  </div>
                  {/* Probability bar */}
                  <div className="h-1 bg-surface-elevated rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${Math.min(pct, 100)}%`,
                        backgroundColor: isLeader ? "#D4AF37" : "#475569",
                      }}
                    />
                  </div>
                </div>

                <MovementBadge movement={nominee.movement_24h} />
              </div>
            );
          })}
        </div>

        {/* Source badges */}
        {category.nominees[0] && (
          <div className="mt-3 pt-2 border-t border-surface-border">
            <SourceDots sources={category.nominees[0].sources} />
          </div>
        )}
      </div>
    </Link>
  );
}

// ============================================================================
// Craft Category Card (compact, all expanded)
// ============================================================================

function CraftCategoryCard({ category }: { category: OscarsCategory }) {
  const emoji = CATEGORY_EMOJI[category.key] || "";

  return (
    <Link href={`/futures/${category.market_ids[0]}`}>
      <div className="bg-surface-card rounded-xl border border-surface-border p-3 hover:shadow-card-hover transition-shadow cursor-pointer h-full">
        <div className="flex items-center gap-2 mb-2">
          <span>{emoji}</span>
          <h3 className="text-caption-strong text-text-primary">
            {category.name}
          </h3>
          <span className="text-micro text-text-muted ml-auto">
            #{category.ceremony_order}
          </span>
        </div>

        <div className="space-y-1.5">
          {category.nominees.slice(0, 5).map((nominee) => {
            const pct = Math.round(nominee.probability * 100);
            const isLeader = nominee.rank === 1;

            return (
              <div key={nominee.name} className="flex items-center gap-2">
                <span
                  className={`text-xs truncate flex-1 ${
                    isLeader ? "text-text-primary font-medium" : "text-text-secondary"
                  }`}
                >
                  {nominee.name}
                </span>

                {/* Mini bar */}
                <div className="w-16 h-1 bg-surface-elevated rounded-full overflow-hidden flex-shrink-0">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${Math.min(pct, 100)}%`,
                      backgroundColor: isLeader ? "#D4AF37" : "#475569",
                    }}
                  />
                </div>

                <span className="text-xs font-mono font-bold text-text-primary w-8 text-right flex-shrink-0">
                  {pct}%
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </Link>
  );
}

// ============================================================================
// Shared Components
// ============================================================================

function MovementBadge({ movement }: { movement: number | null }) {
  if (!movement || Math.abs(movement) < 0.005) return null;

  const isUp = movement > 0;
  const pct = Math.abs(Math.round(movement * 100));

  return (
    <span
      className={`text-micro font-mono ${
        isUp ? "text-green-500" : "text-red-400"
      }`}
    >
      {isUp ? "+" : "-"}{pct}%
    </span>
  );
}

function SourceDots({ sources }: { sources: Record<string, number> }) {
  const sourceNames = Object.keys(sources);
  if (sourceNames.length === 0) return null;

  return (
    <div className="flex items-center gap-1.5 mt-1">
      {sourceNames.map((src) => (
        <span
          key={src}
          className="text-micro-xs text-text-muted uppercase"
          title={`${src}: ${Math.round(sources[src] * 100)}%`}
        >
          {src === "polymarket" ? "PM" : src === "kalshi" ? "KL" : src.toUpperCase().slice(0, 2)}
        </span>
      ))}
    </div>
  );
}
