"use client";

import { useState } from "react";
import { CITIES } from "./data";
import MapCanvas from "./MapCanvas";
import DistributionPanel from "./DistributionPanel";
import { SectionHeader } from "./RainForecast";

export default function TemperatureMap() {
  const [selected, setSelected] = useState("nyc");
  const [hover, setHover] = useState<string | null>(null);
  const city = CITIES.find(c => c.id === selected) ?? CITIES[0];

  return (
    <section className="pt-10 px-4 md:px-6">
      <div className="max-w-[1280px] mx-auto">
        <SectionHeader
          kicker="Global temperature map"
          title="50 cities. Tomorrow's high, as a probability distribution."
          meta="Polymarket & Kalshi · 420 markets"
        />
        <div className="grid grid-cols-1 lg:grid-cols-[1.55fr_1fr] gap-3.5 items-stretch">
          <MapCanvas
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
