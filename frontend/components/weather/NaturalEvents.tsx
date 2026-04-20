"use client";

import useSWR from "swr";
import { EARTHQUAKE, TORNADOES, HURRICANE } from "./data";
import type { EventMarket } from "./data";
import { SectionHeader } from "./RainForecast";
import HurricaneTracker from "./HurricaneTracker";
import EventList from "./EventList";
import { fetchNaturalEvents } from "@/lib/weatherApi";

export default function NaturalEvents() {
  const { data: liveEvents } = useSWR("weather-events", fetchNaturalEvents, { refreshInterval: 3600000 });
  const events = liveEvents as { hurricane: EventMarket[]; earthquake: EventMarket[]; tornadoes: EventMarket[] } | undefined;

  const earthquake = events?.earthquake?.length ? events.earthquake : EARTHQUAKE;
  const tornadoes = events?.tornadoes?.length ? events.tornadoes : TORNADOES;
  const hurricane = events?.hurricane?.length ? events.hurricane : HURRICANE;

  return (
    <section className="pt-14 px-4 md:px-6">
      <div className="max-w-[1280px] mx-auto">
        <SectionHeader
          kicker="Natural events"
          title="Bigger picture. Rarer events."
          meta="Hurricanes · Earthquakes · Tornadoes"
        />
        <div className="grid grid-cols-1 md:grid-cols-[1.4fr_1fr] lg:grid-cols-[1.4fr_1fr_1fr] gap-3.5">
          <HurricaneTracker items={hurricane} />
          <EventList
            title="Seismic activity"
            sub="Earthquake threshold markets."
            icon="⊙"
            items={earthquake}
            accent="#7C3AED"
          />
          <EventList
            title="Tornadoes"
            sub="Season-long count markets."
            icon="⟳"
            items={tornadoes}
            accent="#F59E0B"
          />
        </div>
      </div>
    </section>
  );
}
