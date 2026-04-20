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

  const { data: liveCities } = useSWR("weather-cities", fetchCities, { refreshInterval: 3600000 });
  const cities: CityData[] = (liveCities as CityData[])?.length ? (liveCities as CityData[]) : CITIES;

  const city = cities.find(c => c.id === selected) ?? cities[0];

  return (
    <section className="pt-10 px-4 md:px-6">
      <div className="max-w-[1280px] mx-auto">
        <SectionHeader
          kicker="Global temperature map"
          title={`${cities.length} cities. Tomorrow's high, as a probability distribution.`}
          meta={`Polymarket & Kalshi · ${cities.length * 8} markets`}
        />
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
