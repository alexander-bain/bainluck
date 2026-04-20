"use client";

import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import WeatherHero from "@/components/weather/WeatherHero";
import TemperatureMap from "@/components/weather/TemperatureMap";
import RainForecast from "@/components/weather/RainForecast";
import NaturalEvents from "@/components/weather/NaturalEvents";
import ClimateDashboard from "@/components/weather/ClimateDashboard";
import WildCards from "@/components/weather/WildCards";
import { SectionHeader } from "@/components/weather/RainForecast";

export default function WeatherPage() {
  usePageTracking({ pageType: "weather", pageTitle: "Weather Probabilities" });
  useScrollDepth({ pageType: "weather" });
  useEngagementTime({ pageType: "weather" });

  return (
    <div className="-mx-3 md:-mx-6 -mt-4">
      <WeatherHero />
      <TemperatureMap />
      <NaturalEvents />
      <section className="pt-14 px-4 md:px-6">
        <div className="max-w-[1280px] mx-auto">
          <SectionHeader
            kicker="Climate dashboard"
            title="Slow-moving markets. Long-horizon odds."
            meta="2026 · 2030 · 2050"
          />
          <ClimateDashboard />
        </div>
      </section>

      <section className="pt-14 px-4 md:px-6">
        <div className="max-w-[1280px] mx-auto">
          <SectionHeader
            kicker="Wild cards"
            title="Rare events. Shareable numbers."
          />
          <WildCards />
        </div>
      </section>

      <RainForecast />

      {/* Footer */}
      <footer className="mt-[72px] border-t border-surface-border bg-white">
        <div className="max-w-[1280px] mx-auto px-4 md:px-6 py-7 flex items-center justify-between flex-wrap gap-3 text-xs text-text-muted">
          <span>Data from Kalshi &amp; Polymarket prediction markets · Not weather forecasts. Not financial advice.</span>
          <span className="font-mono">bainluck.com/weather · 521 active · updated 2m ago</span>
        </div>
      </footer>
    </div>
  );
}
