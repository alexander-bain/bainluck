"use client";

import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import ErrorBoundary from "@/components/ErrorBoundary";
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
    <ErrorBoundary fallback={<div className="p-8 text-center"><h2>Something went wrong</h2><button onClick={() => window.location.reload()} className="mt-2 text-sm text-accent-brand hover:underline">Reload page</button></div>}>
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
          <span>Prediction market data · Not weather forecasts. Not financial advice.</span>
          <span className="font-mono">bainluck.com/weather</span>
        </div>
      </footer>
    </div>
    </ErrorBoundary>
  );
}
