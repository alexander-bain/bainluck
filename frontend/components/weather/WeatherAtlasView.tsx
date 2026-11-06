"use client";

import React, { useState } from "react";
import useSWR from "swr";
import {
  fetchWeatherFeatured,
  fetchRain,
  fetchCities,
  fetchNaturalEvents,
  fetchClimate,
  fetchWildCards,
} from "@/lib/weatherApi";
import {
  isoDayLabel,
  nycToday,
  weatherProbability,
  type CityData,
  type ClimateMarket,
  type EventMarket,
  type FeaturedMarket,
  type MonthlyRain as MonthlyRainType,
  type RainDay,
  type WildCard,
} from "./data";
import MapCanvas from "./MapCanvas";
import { temperatureMapHeader } from "./temperatureMapHeader";
import { rainCardHeading } from "@/lib/rainCardHeading";
import {
  BinaryRow,
  BucketDistribution,
  ThresholdLadderCard,
  type AtlasCategoryOutcome,
} from "@/components/atlas/CategoryAtlasComponents";

type SettleableRow = {
  status?: string | null;
  result?: "yes" | "no" | null;
  updated_at?: string | null;
  market_id?: number | null;
};

function toSettledFlags(row: SettleableRow): {
  isSettled: boolean;
  isWinner: boolean | null;
  settledResult: "won" | "lost" | "unavailable" | null;
} {
  const won = row.result === "yes";
  const lost = row.result === "no";
  const settledStatus =
    row.status === "settled" || row.status === "resolved";
  const settledWithoutResult = !won && !lost && settledStatus;
  return {
    isSettled: won || lost || settledStatus,
    isWinner: won ? true : lost ? false : null,
    settledResult: won
      ? "won"
      : lost
        ? "lost"
        : settledWithoutResult
          ? "unavailable"
          : null,
  };
}

export default function WeatherAtlasView() {
  const [selectedCityId, setSelectedCityId] = useState("nyc");
  const [hoverCityId, setHoverCityId] = useState<string | null>(null);
  const [citySearch, setCitySearch] = useState("");

  const { data: liveFeatured, error: featuredError } = useSWR(
    "weather-featured",
    fetchWeatherFeatured,
    { refreshInterval: 300000 }
  );
  const { data: liveRain, error: rainError } = useSWR(
    "weather-rain",
    fetchRain,
    { refreshInterval: 3600000 }
  );
  const { data: liveCities, error: citiesError } = useSWR(
    "weather-cities",
    fetchCities,
    { refreshInterval: 3600000 }
  );
  const { data: liveEvents, error: eventsError } = useSWR(
    "weather-events",
    fetchNaturalEvents,
    { refreshInterval: 3600000 }
  );
  const { data: liveClimate, error: climateError } = useSWR(
    "weather-climate",
    fetchClimate,
    { refreshInterval: 21600000 }
  );
  const { data: liveWildCards, error: wildCardsError } = useSWR(
    "weather-wildcards",
    fetchWildCards,
    { refreshInterval: 21600000 }
  );

  const featuredItems = (liveFeatured as (FeaturedMarket & SettleableRow)[])?.length
    ? (liveFeatured as (FeaturedMarket & SettleableRow)[])
    : null;
  const featured = featuredItems?.[0] ?? null;

  const rainPayload = liveRain as
    | { daily?: (RainDay & SettleableRow)[]; monthly?: (MonthlyRainType & SettleableRow)[] }
    | undefined;
  const dailyRain = rainPayload?.daily?.length ? rainPayload.daily : null;
  const monthlyRain = rainPayload?.monthly?.length ? rainPayload.monthly : null;
  const todayIso = nycToday();

  const allCities = (liveCities as CityData[])?.length ? (liveCities as CityData[]) : null;
  const cityHeader = allCities ? temperatureMapHeader(allCities, citySearch) : null;
  const filteredCities = cityHeader?.cities ?? [];
  const selectedCity =
    filteredCities.find((c) => c.id === selectedCityId) ?? filteredCities[0] ?? null;

  const eventsPayload = liveEvents as
    | {
        hurricane?: (EventMarket & SettleableRow)[];
        earthquake?: (EventMarket & SettleableRow)[];
        tornadoes?: (EventMarket & SettleableRow)[];
      }
    | undefined;

  const climateItems = (liveClimate as (ClimateMarket & SettleableRow)[])?.length
    ? (liveClimate as (ClimateMarket & SettleableRow)[])
    : null;

  const wildCardItems = (liveWildCards as (WildCard & SettleableRow)[])?.length
    ? (liveWildCards as (WildCard & SettleableRow)[])
    : null;

  const monthlyRungs: AtlasCategoryOutcome[] = (monthlyRain ?? []).map((m) => ({
    id: m.city,
    label: m.period ? `${m.city} (${m.period})` : m.city,
    probability: weatherProbability(m),
    renderedPercent: m.prob,
    observedAt: m.updated_at ?? null,
    ...toSettledFlags(m),
  }));

  const dailyRainRungs: AtlasCategoryOutcome[] = (dailyRain ?? []).map((d) => ({
    id: d.iso ?? d.date,
    label: d.iso === todayIso ? `Today (${d.date})` : `${d.day} (${d.date})`,
    probability: weatherProbability(d),
    renderedPercent: d.prob,
    observedAt: d.updated_at ?? null,
    ...toSettledFlags(d),
  }));

  const cityBuckets: AtlasCategoryOutcome[] = selectedCity
    ? selectedCity.high.dist.map((b) => ({
        id: `${selectedCity.id}-${b.label}`,
        label: b.label,
        probability: weatherProbability(b),
        renderedPercent: b.prob,
      }))
    : [];

  const toThresholdRungs = (
    rows: (EventMarket & SettleableRow)[] | undefined
  ): AtlasCategoryOutcome[] =>
    (rows ?? []).map((item, idx) => ({
      id: item.market_id ?? `${item.q}-${idx}`,
      label: item.leader ? `${item.q} — ${item.leader}` : item.q,
      probability: weatherProbability(item),
      renderedPercent: item.prob,
      observedAt: item.updated_at ?? null,
      ...toSettledFlags(item),
    }));

  return (
    <div
      data-testid="weather-atlas-view"
      className="max-w-[1120px] mx-auto px-4 md:px-6 py-6 space-y-12"
    >
      {/* Hero */}
      <section data-section="HERO" className="grid grid-cols-1 lg:grid-cols-[1.35fr_1fr] gap-6 items-start">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
            WEATHER · PROBABILITY FIRST
          </p>
          <h1 className="text-3xl md:text-4xl font-semibold text-text-primary tracking-tight mt-1.5">
            What is the chance it rains tomorrow?
          </h1>
          <p className="text-sm text-text-secondary mt-2 max-w-xl">
            Weather markets translated into plain probabilities. Rain, temperature,
            hurricanes, and long-horizon climate — one calibrated reading per market.
          </p>
        </div>

        <div className="bg-surface-card border border-surface-border rounded-xl p-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted mb-2">
            FEATURED MARKET
          </p>
          {featuredError && !featured ? (
            <p className="text-sm text-text-muted py-4">Failed to load featured markets</p>
          ) : featured ? (
            <BinaryRow
              meta={{
                marketId: featured.market_id ?? null,
                marketTitle: featured.leader
                  ? `${featured.q} — ${featured.leader}`
                  : featured.q,
                kicker: featured.tag,
                subtitle: featured.closes || null,
                source: featured.src,
              }}
              outcome={{
                id: featured.market_id ?? "featured",
                label: featured.leader ?? featured.q,
                probability: weatherProbability(featured),
                renderedPercent: featured.prob,
                ...toSettledFlags(featured),
              }}
            />
          ) : (
            <p className="text-sm text-text-muted py-4">No live featured markets right now</p>
          )}
        </div>
      </section>

      {/* Section 1: Precipitation */}
      <section data-section="RAIN" className="space-y-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
            PRECIPITATION
          </p>
          <h2 className="text-xl font-semibold text-text-primary mt-0.5">
            Rain &amp; rainfall
          </h2>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {rainError && !dailyRain ? (
            <div className="bg-surface-card border border-surface-border rounded-xl p-5 text-sm text-text-muted">
              Failed to load rain data
            </div>
          ) : dailyRain ? (
            <ThresholdLadderCard
              meta={{
                marketTitle: rainCardHeading(dailyRain.length),
                kicker: "DAILY RAIN",
                source: null,
              }}
              rungs={dailyRainRungs}
            />
          ) : (
            <div className="bg-surface-card border border-surface-border rounded-xl p-5">
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
                DAILY RAIN
              </p>
              <h3 className="text-base font-semibold text-text-primary mt-0.5">
                {rainCardHeading(0)}
              </h3>
              <p className="text-sm text-text-muted mt-3">
                No live rain markets right now
              </p>
            </div>
          )}

          {rainError && !monthlyRain ? (
            <div className="bg-surface-card border border-surface-border rounded-xl p-5 text-sm text-text-muted">
              Failed to load monthly data
            </div>
          ) : monthlyRain ? (
            <ThresholdLadderCard
              meta={{
                marketTitle: "Above 1 inch of rain",
                kicker: "MONTHLY RAINFALL",
                source: null,
              }}
              rungs={monthlyRungs}
            />
          ) : (
            <div className="bg-surface-card border border-surface-border rounded-xl p-5">
              <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
                MONTHLY RAINFALL
              </p>
              <h3 className="text-base font-semibold text-text-primary mt-0.5">
                Above 1 inch of rain
              </h3>
              <p className="text-sm text-text-muted mt-3">
                No live rainfall markets right now
              </p>
            </div>
          )}
        </div>
      </section>

      {/* Section 2: Global temperature map + BucketDistribution */}
      <section data-section="MAP" className="space-y-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
            GLOBAL TEMPERATURE MAP
          </p>
          <h2 className="text-xl font-semibold text-text-primary mt-0.5">
            {cityHeader?.title ?? "Daily high, as a probability distribution."}
          </h2>
          {cityHeader?.meta && (
            <p className="text-xs font-mono text-text-muted mt-0.5">{cityHeader.meta}</p>
          )}
        </div>

        {citiesError && !allCities ? (
          <div className="bg-surface-card border border-surface-border rounded-xl p-6 text-sm text-text-muted">
            Failed to load temperature data
          </div>
        ) : !allCities ? (
          <div className="bg-surface-card border border-surface-border rounded-xl p-6 text-sm text-text-muted">
            No live temperature markets right now
          </div>
        ) : (
          <>
            <div>
              <input
                type="text"
                value={citySearch}
                onChange={(e) => setCitySearch(e.target.value)}
                placeholder="Search cities..."
                className="w-full max-w-xs px-3 py-1.5 text-sm border border-surface-border rounded-lg bg-surface-card text-text-primary placeholder:text-text-muted focus:outline-none"
              />
              {cityHeader?.scope && (
                <span className="ml-2 text-xs text-text-muted">{cityHeader.scope}</span>
              )}
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-[1.45fr_1fr] gap-4 items-start">
              <MapCanvas
                cities={filteredCities}
                selected={selectedCityId}
                hover={hoverCityId}
                onHover={setHoverCityId}
                onSelect={setSelectedCityId}
              />
              {selectedCity && (
                <BucketDistribution
                  meta={{
                    marketId: selectedCity.marketId ?? null,
                    marketTitle: `${selectedCity.name} daily high`,
                    kicker: `${selectedCity.region.toUpperCase()} · °${selectedCity.high.unit}`,
                    resolutionDate: selectedCity.iso ?? null,
                    source: selectedCity.src ?? selectedCity.srcs?.[0] ?? null,
                    sourceCount: selectedCity.srcs?.length ?? 1,
                  }}
                  buckets={cityBuckets}
                  stationContextLabel={isoDayLabel(selectedCity.iso)}
                />
              )}
            </div>
          </>
        )}
      </section>

      {/* Section 3: Natural events */}
      <section data-section="NATURAL" className="space-y-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
            NATURAL EVENTS
          </p>
          <h2 className="text-xl font-semibold text-text-primary mt-0.5">
            Hurricanes, earthquakes &amp; tornadoes
          </h2>
        </div>

        {eventsError && !eventsPayload ? (
          <div className="bg-surface-card border border-surface-border rounded-xl p-6 text-sm text-text-muted">
            Failed to load natural events data
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <ThresholdLadderCard
              meta={{
                marketTitle: "Atlantic hurricane season",
                kicker: "HURRICANES",
              }}
              rungs={toThresholdRungs(eventsPayload?.hurricane)}
            />
            <ThresholdLadderCard
              meta={{
                marketTitle: "Earthquake thresholds",
                kicker: "SEISMIC ACTIVITY",
              }}
              rungs={toThresholdRungs(eventsPayload?.earthquake)}
            />
            <ThresholdLadderCard
              meta={{
                marketTitle: "Tornado count markets",
                kicker: "TORNADOES",
              }}
              rungs={toThresholdRungs(eventsPayload?.tornadoes)}
            />
          </div>
        )}
      </section>

      {/* Section 4: Climate dashboard */}
      <section data-section="CLIMATE" className="space-y-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
            CLIMATE DASHBOARD
          </p>
          <h2 className="text-xl font-semibold text-text-primary mt-0.5">
            Long-horizon climate probabilities
          </h2>
        </div>

        {climateError && !climateItems ? (
          <div className="bg-surface-card border border-surface-border rounded-xl p-6 text-sm text-text-muted">
            Failed to load climate data
          </div>
        ) : !climateItems ? (
          <div className="bg-surface-card border border-surface-border rounded-xl p-6 text-sm text-text-muted">
            No live climate markets right now
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {(
              [
                { scale: "2026", title: "2026", subtitle: "Next 12 months" },
                { scale: "2030", title: "2030", subtitle: "End of decade" },
                { scale: "2050", title: "2050", subtitle: "Mid-century" },
              ] as const
            ).map((col) => {
              const colItems = climateItems.filter((c) => c.scale === col.scale);
              return (
                <div
                  key={col.scale}
                  className="bg-surface-card border border-surface-border rounded-xl p-5 space-y-3"
                >
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
                      {col.subtitle}
                    </p>
                    <h3 className="text-lg font-semibold font-mono text-text-primary mt-0.5">
                      {col.title}
                    </h3>
                  </div>
                  {colItems.length === 0 ? (
                    <p className="text-sm text-text-muted">
                      No live markets for this horizon yet.
                    </p>
                  ) : (
                    <div className="space-y-2.5">
                      {colItems.map((item, idx) => (
                        <BinaryRow
                          key={item.market_id ?? `${col.scale}-${idx}`}
                          meta={{
                            marketId: item.market_id ?? null,
                            marketTitle: item.leader
                              ? `${item.q} — ${item.leader}`
                              : item.q,
                            source: item.src,
                          }}
                          outcome={{
                            id: item.market_id ?? `${col.scale}-${idx}`,
                            label: item.leader ?? item.q,
                            probability: weatherProbability(item),
                            renderedPercent: item.prob,
                            ...toSettledFlags(item),
                          }}
                        />
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Section 5: Wild cards */}
      <section data-section="WILD" className="space-y-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
            WILD CARDS
          </p>
          <h2 className="text-xl font-semibold text-text-primary mt-0.5">
            Rare events
          </h2>
        </div>

        {wildCardsError && !wildCardItems ? (
          <div className="bg-surface-card border border-surface-border rounded-xl p-6 text-sm text-text-muted">
            Failed to load wild cards
          </div>
        ) : !wildCardItems ? (
          <div className="bg-surface-card border border-surface-border rounded-xl p-6 text-sm text-text-muted">
            No live wild cards right now
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            {wildCardItems.map((card, idx) => (
              <BinaryRow
                key={card.market_id ?? idx}
                meta={{
                  marketId: card.market_id ?? null,
                  marketTitle: card.leader ? `${card.q} — ${card.leader}` : card.q,
                  kicker: card.tag,
                  source: card.src,
                }}
                outcome={{
                  id: card.market_id ?? idx,
                  label: card.leader ?? card.q,
                  probability: weatherProbability(card),
                  renderedPercent: card.prob,
                  ...toSettledFlags(card),
                }}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
