const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) throw new Error(`Weather API error: ${res.status}`);
  return res.json();
}

export function fetchWeatherFeatured() {
  return fetchJson("/api/weather/featured");
}

export function fetchCities() {
  return fetchJson("/api/weather/cities");
}

export function fetchRain() {
  return fetchJson<{ daily: unknown[]; monthly: unknown[] }>("/api/weather/rain");
}

export function fetchNaturalEvents() {
  return fetchJson<{ hurricane: unknown[]; earthquake: unknown[]; tornadoes: unknown[] }>("/api/weather/events");
}

export function fetchClimate() {
  return fetchJson("/api/weather/climate");
}

export function fetchWildCards() {
  return fetchJson("/api/weather/wildcards");
}
