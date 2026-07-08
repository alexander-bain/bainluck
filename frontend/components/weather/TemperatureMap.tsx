"use client";

import { useState } from "react";
import useSWR from "swr";
import type { CityData } from "./data";
import MapCanvas from "./MapCanvas";
import DistributionPanel from "./DistributionPanel";
import { SectionHeader } from "./RainForecast";
import { fetchCities } from "@/lib/weatherApi";

function TemperatureMapSkeleton() {
  return (
    <section className="pt-10 px-4 md:px-6">
      <div className="max-w-[1280px] mx-auto">
        <SectionHeader
          kicker="Global temperature map"
          title="Tomorrow's high, as a probability distribution."
          meta="Polymarket & Kalshi"
        />
        <div className="grid grid-cols-1 lg:grid-cols-[1.55fr_1fr] gap-3.5 items-stretch">
          {/* Map skeleton */}
          <div className="bg-surface-card border border-surface-border rounded-2xl overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-surface-border">
              <div className="h-2 w-40 bg-gray-200 rounded animate-pulse" />
              <div className="h-3 w-28 bg-gray-200 rounded animate-pulse" />
            </div>
            <div className="animate-pulse bg-gray-100" style={{ aspectRatio: "1.8 / 1", minHeight: 420 }} />
            <div className="flex items-center justify-between px-4 py-2.5 border-t border-surface-border">
              <div className="h-3 w-48 bg-gray-200 rounded animate-pulse" />
              <div className="h-3 w-20 bg-gray-200 rounded animate-pulse" />
            </div>
          </div>
          {/* Distribution panel skeleton */}
          <div className="bg-surface-card border border-surface-border rounded-2xl p-5" style={{ minHeight: 460 }}>
            <div className="h-3 w-16 bg-gray-200 rounded animate-pulse mb-2" />
            <div className="h-6 w-32 bg-gray-200 rounded animate-pulse mb-4" />
            <div className="h-3 w-48 bg-gray-200 rounded animate-pulse mb-5" />
            <div className="h-16 w-24 bg-gray-200 rounded animate-pulse mb-3" />
            <div className="h-4 w-20 bg-gray-200 rounded animate-pulse mb-4" />
            <div className="flex-1 flex items-end gap-1 mt-6" style={{ height: 140 }}>
              {Array.from({ length: 11 }).map((_, i) => (
                <div
                  key={i}
                  className="flex-1 bg-gray-200 rounded-t animate-pulse"
                  style={{ height: `${15 + Math.sin(i * 0.8) * 50 + 40}%` }}
                />
              ))}
            </div>
            <div className="flex gap-1 mt-1">
              {Array.from({ length: 11 }).map((_, i) => (
                <div key={i} className="flex-1 h-2 bg-gray-200 rounded animate-pulse" />
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export default function TemperatureMap() {
  const [selected, setSelected] = useState("nyc");
  const [hover, setHover] = useState<string | null>(null);
  const [citySearch, setCitySearch] = useState("");

  const { data: liveCities, error } = useSWR("weather-cities", fetchCities, { refreshInterval: 3600000 });
  const allCities = (liveCities as CityData[])?.length ? (liveCities as CityData[]) : null;

  if (error && !allCities) {
    return (
      <section className="pt-10 px-4 md:px-6">
        <div className="max-w-[1280px] mx-auto">
          <SectionHeader
            kicker="Global temperature map"
            title="Tomorrow's high, as a probability distribution."
            meta="Polymarket & Kalshi"
          />
          <div className="bg-surface-card border border-surface-border rounded-2xl py-16 text-center">
            <p className="text-text-secondary text-sm">Failed to load temperature data</p>
          </div>
        </div>
      </section>
    );
  }

  // Loaded but EMPTY (200 with no fresh daily city markets — a #995 freeze
  // symptom) must show an honest empty state, NOT an infinite skeleton. Only
  // `undefined` means still-loading; `[]` means loaded-and-empty. The data gap
  // is upstream (Lane 1) — this is resilience only.
  if (liveCities !== undefined && !allCities) {
    return (
      <section className="pt-10 px-4 md:px-6">
        <div className="max-w-[1280px] mx-auto">
          <SectionHeader
            kicker="Global temperature map"
            title="Tomorrow's high, as a probability distribution."
            meta="Polymarket & Kalshi"
          />
          <div className="bg-surface-card border border-surface-border rounded-2xl py-16 text-center">
            <p className="text-text-secondary text-sm">No live temperature markets right now</p>
            <p className="text-text-muted text-xs mt-1.5">Daily city markets appear here when they reopen.</p>
          </div>
        </div>
      </section>
    );
  }

  if (!allCities) return <TemperatureMapSkeleton />;

  const cities = citySearch.trim()
    ? allCities.filter(c => c.name.toLowerCase().includes(citySearch.trim().toLowerCase()))
    : allCities;

  const city = cities.find(c => c.id === selected) ?? cities[0];

  return (
    <section className="pt-10 px-4 md:px-6">
      <div className="max-w-[1280px] mx-auto">
        <SectionHeader
          kicker="Global temperature map"
          title={`${allCities.length} cities. Tomorrow's high, as a probability distribution.`}
          meta={`Polymarket & Kalshi · ${allCities.length * 8} markets`}
        />
        <div className="mb-3">
          <input
            type="text"
            value={citySearch}
            onChange={e => setCitySearch(e.target.value)}
            placeholder="Search cities..."
            className="w-full max-w-xs px-3 py-2 text-sm border border-surface-border rounded-lg bg-surface-card text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent-brand/30 focus:border-accent-brand"
          />
          {citySearch.trim() && (
            <span className="ml-2 text-xs text-text-muted">
              {cities.length} of {allCities.length} cities
            </span>
          )}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-[1.55fr_1fr] gap-3.5 items-stretch">
          <MapCanvas
            cities={cities}
            selected={selected}
            hover={hover}
            onHover={setHover}
            onSelect={setSelected}
          />
          <DistributionPanel city={city} />
        </div>
      </div>
    </section>
  );
}
