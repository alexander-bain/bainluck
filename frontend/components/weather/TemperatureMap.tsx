"use client";

import { useState } from "react";
import useSWR from "swr";
import { CITIES } from "./data";
import type { CityData } from "./data";
import MapCanvas from "./MapCanvas";
import DistributionPanel from "./DistributionPanel";
import { SectionHeader } from "./RainForecast";
import { fetchCities } from "@/lib/weatherApi";

export default function TemperatureMap() {
  const [selected, setSelected] = useState("nyc");
  const [hover, setHover] = useState<string | null>(null);
  const [citySearch, setCitySearch] = useState("");

  const { data: liveCities } = useSWR("weather-cities", fetchCities, { refreshInterval: 3600000 });
  const allCities: CityData[] = (liveCities as CityData[])?.length ? (liveCities as CityData[]) : CITIES;

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
