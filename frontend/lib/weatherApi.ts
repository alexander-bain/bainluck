import { HERO_FEATURED, CITIES, NYC_RAIN, MONTHLY_RAIN, HURRICANE, EARTHQUAKE, TORNADOES, CLIMATE, WILDCARDS } from "@/components/weather/data";

export function fetchWeatherFeatured() { return Promise.resolve(HERO_FEATURED); }
export function fetchCities() { return Promise.resolve(CITIES); }
export function fetchNycRain() { return Promise.resolve(NYC_RAIN); }
export function fetchMonthlyRain() { return Promise.resolve(MONTHLY_RAIN); }
export function fetchHurricane() { return Promise.resolve(HURRICANE); }
export function fetchEarthquake() { return Promise.resolve(EARTHQUAKE); }
export function fetchTornadoes() { return Promise.resolve(TORNADOES); }
export function fetchClimate() { return Promise.resolve(CLIMATE); }
export function fetchWildCards() { return Promise.resolve(WILDCARDS); }
