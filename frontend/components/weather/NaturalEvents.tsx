"use client";

import { EARTHQUAKE, TORNADOES } from "./data";
import { SectionHeader } from "./RainForecast";
import HurricaneTracker from "./HurricaneTracker";
import EventList from "./EventList";

export default function NaturalEvents() {
  return (
    <section className="pt-14 px-4 md:px-6">
      <div className="max-w-[1280px] mx-auto">
        <SectionHeader
          kicker="Natural events"
          title="Bigger picture. Rarer events."
          meta="Hurricanes · Earthquakes · Tornadoes"
        />
        <div className="grid grid-cols-1 md:grid-cols-[1.4fr_1fr] lg:grid-cols-[1.4fr_1fr_1fr] gap-3.5">
          <HurricaneTracker />
          <EventList
            title="Seismic activity"
            sub="Earthquake threshold markets — the dramatic 'what if'."
            icon="⊙"
            items={EARTHQUAKE}
            accent="#7C3AED"
          />
          <EventList
            title="Tornadoes"
            sub="Season-long count markets."
            icon="⟳"
            items={TORNADOES}
            accent="#F59E0B"
          />
        </div>
      </div>
    </section>
  );
}
