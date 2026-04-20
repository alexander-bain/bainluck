export type Source = "kalshi" | "polymarket";

export type FeaturedMarket = {
  q: string;
  prob: number;
  src: Source;
  tag: string;
  closes: string;
};

export type CityData = {
  id: string;
  name: string;
  x: number;
  y: number;
  region: "Americas" | "Europe" | "Asia" | "Africa" | "Oceania";
  srcs: Source[];
  high: {
    unit: "C" | "F";
    mode: number;
    dist: Array<{ label: string; prob: number }>;
  };
  kalshiHigh?: {
    unit: "C" | "F";
    mode: number;
    dist: Array<{ label: string; prob: number }>;
  };
  low?: {
    unit: "C" | "F";
    mode: number;
    dist: Array<{ label: string; prob: number }>;
  };
  rainToday?: number;
};

export type RainDay = {
  day: string;
  date: string;
  prob: number;
  icon: string;
};

export type MonthlyRain = {
  city: string;
  prob: number;
  src: Source;
};

export type EventMarket = {
  q: string;
  prob: number;
  src: Source;
  closes: string;
};

export type ClimateMarket = {
  q: string;
  prob: number;
  src: Source;
  scale: "2026" | "2030" | "2050";
};

export type WildCard = {
  q: string;
  prob: number;
  src: Source;
  tag: string;
};

export const SOURCES = {
  kalshi: { key: "kalshi" as const, label: "Kalshi", color: "#22C55E", bg: "#ECFDF5", fg: "#047857" },
  polymarket: { key: "polymarket" as const, label: "Polymarket", color: "#3B82F6", bg: "#EFF6FF", fg: "#1D4ED8" },
};

export const HERO_FEATURED: FeaturedMarket[] = [
  { q: "Will it rain in NYC tomorrow?", prob: 72, src: "kalshi", tag: "Daily rain", closes: "Tue, Apr 21" },
  { q: "Will 2026 be the hottest year ever?", prob: 38, src: "kalshi", tag: "Climate", closes: "Thu, Dec 31" },
  { q: "Cat 4 hurricane hits the US before 2027?", prob: 36, src: "polymarket", tag: "Hurricane", closes: "Thu, Dec 31" },
  { q: "Will any month of 2026 be hottest on record?", prob: 78, src: "polymarket", tag: "Climate", closes: "Thu, Dec 31" },
  { q: "Megaquake before June 30?", prob: 18, src: "polymarket", tag: "Seismic", closes: "Tue, Jun 30" },
];

export const CITIES: CityData[] = [
  { id: "nyc", name: "New York", x: 30.8, y: 41, region: "Americas", srcs: ["polymarket", "kalshi"],
    high: { unit: "F", mode: 50.5, dist: [
      { label: "<45°F", prob: 4 }, { label: "45-46", prob: 8 }, { label: "47-48", prob: 14 }, { label: "49-50", prob: 22 },
      { label: "50-51", prob: 33 }, { label: "52-53", prob: 10 }, { label: "54-55", prob: 5 }, { label: "56-57", prob: 2 },
      { label: "58-59", prob: 1 }, { label: "60-61", prob: 1 }, { label: "62°F+", prob: 0 },
    ] },
    kalshiHigh: { unit: "F", mode: 51.5, dist: [
      { label: "49° or below", prob: 25 }, { label: "50-51°", prob: 42 }, { label: "52-53°", prob: 20 }, { label: "54-55°", prob: 8 }, { label: "56-57°", prob: 4 }, { label: "58°+", prob: 1 },
    ] },
    low: { unit: "F", mode: 38, dist: [
      { label: "<34°F", prob: 9 }, { label: "34-36", prob: 14 }, { label: "37-39", prob: 36 }, { label: "40-42", prob: 28 }, { label: "43-45", prob: 10 }, { label: "46°F+", prob: 3 },
    ] },
    rainToday: 72,
  },
  { id: "la", name: "Los Angeles", x: 18.8, y: 45.4, region: "Americas", srcs: ["polymarket", "kalshi"],
    high: { unit: "F", mode: 68.5, dist: [
      { label: "<62°F", prob: 2 }, { label: "62-63", prob: 4 }, { label: "64-65", prob: 8 }, { label: "66-67", prob: 20 },
      { label: "68-69", prob: 37 }, { label: "70-71", prob: 18 }, { label: "72-73", prob: 7 }, { label: "74-75", prob: 3 },
      { label: "76-77", prob: 1 }, { label: "78-79", prob: 0 }, { label: "80°F+", prob: 0 },
    ] },
    kalshiHigh: { unit: "F", mode: 66.5, dist: [
      { label: "62° or below", prob: 4 }, { label: "63-64°", prob: 10 }, { label: "65-66°", prob: 22 }, { label: "67-68°", prob: 38 }, { label: "69-70°", prob: 18 }, { label: "71°+", prob: 8 },
    ] },
  },
  { id: "mia", name: "Miami", x: 31.2, y: 51, region: "Americas", srcs: ["polymarket", "kalshi"],
    high: { unit: "F", mode: 82.5, dist: [
      { label: "<76°F", prob: 1 }, { label: "76-77", prob: 2 }, { label: "78-79", prob: 7 }, { label: "80-81", prob: 18 },
      { label: "82-83", prob: 42 }, { label: "84-85", prob: 18 }, { label: "86-87", prob: 8 }, { label: "88-89", prob: 3 },
      { label: "90-91", prob: 1 }, { label: "92-93", prob: 0 }, { label: "94°F+", prob: 0 },
    ] },
    kalshiHigh: { unit: "F", mode: 82, dist: [
      { label: "78° or below", prob: 5 }, { label: "79-80°", prob: 14 }, { label: "81-82°", prob: 40 }, { label: "83-84°", prob: 25 }, { label: "85-86°", prob: 12 }, { label: "87°+", prob: 4 },
    ] },
  },
  { id: "chi", name: "Chicago", x: 26, y: 38, region: "Americas", srcs: ["polymarket", "kalshi"],
    high: { unit: "F", mode: 58.5, dist: [
      { label: "<52°F", prob: 3 }, { label: "52-53", prob: 8 }, { label: "54-55", prob: 14 }, { label: "56-57", prob: 22 },
      { label: "58-59", prob: 28 }, { label: "60-61", prob: 14 }, { label: "62-63", prob: 6 }, { label: "64-65", prob: 3 },
      { label: "66-67", prob: 1 }, { label: "68-69", prob: 1 }, { label: "70°F+", prob: 0 },
    ] },
    kalshiHigh: { unit: "F", mode: 59, dist: [
      { label: "54° or below", prob: 8 }, { label: "55-57°", prob: 18 }, { label: "58-59°", prob: 35 }, { label: "60-61°", prob: 22 }, { label: "62-63°", prob: 12 }, { label: "64°+", prob: 5 },
    ] },
  },
  { id: "sfo", name: "San Francisco", x: 16.5, y: 42, region: "Americas", srcs: ["polymarket", "kalshi"],
    high: { unit: "F", mode: 63.5, dist: [
      { label: "<58°F", prob: 4 }, { label: "58-59", prob: 9 }, { label: "60-61", prob: 15 }, { label: "62-63", prob: 29 },
      { label: "64-65", prob: 24 }, { label: "66-67", prob: 12 }, { label: "68-69", prob: 5 }, { label: "70-71", prob: 1 },
      { label: "72-73", prob: 1 }, { label: "74-75", prob: 0 }, { label: "76°F+", prob: 0 },
    ] },
    kalshiHigh: { unit: "F", mode: 63.5, dist: [
      { label: "58° or below", prob: 6 }, { label: "59-61°", prob: 20 }, { label: "62-63°", prob: 38 }, { label: "64-65°", prob: 22 }, { label: "66-67°", prob: 10 }, { label: "68°+", prob: 4 },
    ] },
  },
  { id: "dal", name: "Dallas", x: 24.5, y: 47, region: "Americas", srcs: ["polymarket", "kalshi"],
    high: { unit: "F", mode: 78.5, dist: [
      { label: "<72°F", prob: 2 }, { label: "72-73", prob: 5 }, { label: "74-75", prob: 10 }, { label: "76-77", prob: 18 },
      { label: "78-79", prob: 30 }, { label: "80-81", prob: 18 }, { label: "82-83", prob: 10 }, { label: "84-85", prob: 5 },
      { label: "86-87", prob: 1 }, { label: "88-89", prob: 1 }, { label: "90°F+", prob: 0 },
    ] },
    kalshiHigh: { unit: "F", mode: 79.5, dist: [
      { label: "74° or below", prob: 5 }, { label: "75-77°", prob: 15 }, { label: "78-79°", prob: 35 }, { label: "80-81°", prob: 25 }, { label: "82-83°", prob: 14 }, { label: "84°+", prob: 6 },
    ] },
  },
  { id: "tor", name: "Toronto", x: 29, y: 37, region: "Americas", srcs: ["polymarket"],
    high: { unit: "C", mode: 11, dist: [
      { label: "<7°C", prob: 4 }, { label: "7-8", prob: 10 }, { label: "9-10", prob: 24 }, { label: "11", prob: 30 },
      { label: "12-13", prob: 18 }, { label: "14-15", prob: 8 }, { label: "16-17", prob: 3 }, { label: "18-19", prob: 2 },
      { label: "20-21", prob: 1 }, { label: "22-23", prob: 0 }, { label: "24°C+", prob: 0 },
    ] },
  },
  { id: "mex", name: "Mexico City", x: 22.6, y: 53, region: "Americas", srcs: ["polymarket"],
    high: { unit: "C", mode: 26, dist: [
      { label: "<21°C", prob: 1 }, { label: "21-22", prob: 3 }, { label: "23-24", prob: 11 }, { label: "25", prob: 22 },
      { label: "26", prob: 34 }, { label: "27", prob: 18 }, { label: "28-29", prob: 7 }, { label: "30-31", prob: 3 },
      { label: "32-33", prob: 1 }, { label: "34-35", prob: 0 }, { label: "36°C+", prob: 0 },
    ] },
  },
  { id: "sao", name: "São Paulo", x: 35, y: 67, region: "Americas", srcs: ["polymarket"],
    high: { unit: "C", mode: 25, dist: [
      { label: "<20°C", prob: 2 }, { label: "20-21", prob: 6 }, { label: "22-23", prob: 15 }, { label: "24", prob: 25 },
      { label: "25", prob: 30 }, { label: "26", prob: 14 }, { label: "27-28", prob: 5 }, { label: "29-30", prob: 2 },
      { label: "31-32", prob: 1 }, { label: "33-34", prob: 0 }, { label: "35°C+", prob: 0 },
    ] },
  },
  { id: "bue", name: "Buenos Aires", x: 33, y: 74, region: "Americas", srcs: ["polymarket"],
    high: { unit: "C", mode: 20, dist: [
      { label: "<15°C", prob: 3 }, { label: "15-16", prob: 8 }, { label: "17-18", prob: 18 }, { label: "19", prob: 27 },
      { label: "20", prob: 25 }, { label: "21-22", prob: 12 }, { label: "23-24", prob: 4 }, { label: "25-26", prob: 2 },
      { label: "27-28", prob: 1 }, { label: "29-30", prob: 0 }, { label: "31°C+", prob: 0 },
    ] },
  },
  { id: "lon", name: "London", x: 49, y: 33, region: "Europe", srcs: ["polymarket"],
    high: { unit: "C", mode: 13, dist: [
      { label: "<9°C", prob: 2 }, { label: "9-10", prob: 5 }, { label: "11", prob: 14 }, { label: "12", prob: 22 },
      { label: "13", prob: 46 }, { label: "14", prob: 7 }, { label: "15-16", prob: 3 }, { label: "17-18", prob: 1 },
      { label: "19-20", prob: 0 }, { label: "21-22", prob: 0 }, { label: "23°C+", prob: 0 },
    ] },
  },
  { id: "par", name: "Paris", x: 50, y: 34, region: "Europe", srcs: ["polymarket"],
    high: { unit: "C", mode: 15, dist: [
      { label: "<11°C", prob: 3 }, { label: "11-12", prob: 9 }, { label: "13-14", prob: 22 }, { label: "15", prob: 34 },
      { label: "16", prob: 18 }, { label: "17-18", prob: 10 }, { label: "19-20", prob: 3 }, { label: "21-22", prob: 1 },
      { label: "23-24", prob: 0 }, { label: "25-26", prob: 0 }, { label: "27°C+", prob: 0 },
    ] },
  },
  { id: "mad", name: "Madrid", x: 48, y: 38, region: "Europe", srcs: ["polymarket"],
    high: { unit: "C", mode: 20, dist: [
      { label: "<15°C", prob: 2 }, { label: "15-16", prob: 6 }, { label: "17-18", prob: 16 }, { label: "19", prob: 25 },
      { label: "20", prob: 28 }, { label: "21-22", prob: 14 }, { label: "23-24", prob: 6 }, { label: "25-26", prob: 2 },
      { label: "27-28", prob: 1 }, { label: "29-30", prob: 0 }, { label: "31°C+", prob: 0 },
    ] },
  },
  { id: "ber", name: "Munich", x: 52, y: 33, region: "Europe", srcs: ["polymarket"],
    high: { unit: "C", mode: 14, dist: [
      { label: "<9°C", prob: 3 }, { label: "9-10", prob: 9 }, { label: "11-12", prob: 19 }, { label: "13", prob: 23 },
      { label: "14", prob: 26 }, { label: "15-16", prob: 12 }, { label: "17-18", prob: 5 }, { label: "19-20", prob: 2 },
      { label: "21-22", prob: 1 }, { label: "23-24", prob: 0 }, { label: "25°C+", prob: 0 },
    ] },
  },
  { id: "mos", name: "Moscow", x: 57, y: 28, region: "Europe", srcs: ["polymarket"],
    high: { unit: "C", mode: 9, dist: [
      { label: "<4°C", prob: 4 }, { label: "4-5", prob: 10 }, { label: "6-7", prob: 20 }, { label: "8", prob: 26 },
      { label: "9", prob: 24 }, { label: "10-11", prob: 11 }, { label: "12-13", prob: 3 }, { label: "14-15", prob: 1 },
      { label: "16-17", prob: 1 }, { label: "18-19", prob: 0 }, { label: "20°C+", prob: 0 },
    ] },
  },
  { id: "ist", name: "Istanbul", x: 55, y: 39, region: "Europe", srcs: ["polymarket"],
    high: { unit: "C", mode: 17, dist: [
      { label: "<12°C", prob: 2 }, { label: "12-13", prob: 7 }, { label: "14-15", prob: 18 }, { label: "16", prob: 26 },
      { label: "17", prob: 28 }, { label: "18", prob: 12 }, { label: "19-20", prob: 5 }, { label: "21-22", prob: 1 },
      { label: "23-24", prob: 1 }, { label: "25-26", prob: 0 }, { label: "27°C+", prob: 0 },
    ] },
  },
  { id: "tok", name: "Tokyo", x: 83, y: 39, region: "Asia", srcs: ["polymarket"],
    high: { unit: "C", mode: 23, dist: [
      { label: "<18°C", prob: 2 }, { label: "18-19", prob: 6 }, { label: "20-21", prob: 16 }, { label: "22", prob: 25 },
      { label: "23", prob: 40 }, { label: "24", prob: 7 }, { label: "25-26", prob: 3 }, { label: "27-28", prob: 1 },
      { label: "29-30", prob: 0 }, { label: "31-32", prob: 0 }, { label: "33°C+", prob: 0 },
    ] },
  },
  { id: "seo", name: "Seoul", x: 81, y: 38, region: "Asia", srcs: ["polymarket"],
    high: { unit: "C", mode: 19, dist: [
      { label: "<14°C", prob: 3 }, { label: "14-15", prob: 9 }, { label: "16-17", prob: 20 }, { label: "18", prob: 23 },
      { label: "19", prob: 26 }, { label: "20", prob: 11 }, { label: "21-22", prob: 5 }, { label: "23-24", prob: 2 },
      { label: "25-26", prob: 1 }, { label: "27-28", prob: 0 }, { label: "29°C+", prob: 0 },
    ] },
  },
  { id: "bei", name: "Beijing", x: 78, y: 37, region: "Asia", srcs: ["polymarket"],
    high: { unit: "C", mode: 22, dist: [
      { label: "<16°C", prob: 3 }, { label: "16-17", prob: 8 }, { label: "18-19", prob: 18 }, { label: "20-21", prob: 24 },
      { label: "22", prob: 28 }, { label: "23-24", prob: 12 }, { label: "25-26", prob: 5 }, { label: "27-28", prob: 1 },
      { label: "29-30", prob: 1 }, { label: "31-32", prob: 0 }, { label: "33°C+", prob: 0 },
    ] },
  },
  { id: "sha", name: "Shanghai", x: 80, y: 42, region: "Asia", srcs: ["polymarket"],
    high: { unit: "C", mode: 22, dist: [
      { label: "<17°C", prob: 2 }, { label: "17-18", prob: 7 }, { label: "19-20", prob: 19 }, { label: "21", prob: 25 },
      { label: "22", prob: 30 }, { label: "23", prob: 10 }, { label: "24-25", prob: 4 }, { label: "26-27", prob: 2 },
      { label: "28-29", prob: 1 }, { label: "30-31", prob: 0 }, { label: "32°C+", prob: 0 },
    ] },
  },
  { id: "hkg", name: "Hong Kong", x: 79, y: 49, region: "Asia", srcs: ["polymarket"],
    high: { unit: "C", mode: 27, dist: [
      { label: "<22°C", prob: 1 }, { label: "22-23", prob: 4 }, { label: "24-25", prob: 12 }, { label: "26", prob: 22 },
      { label: "27", prob: 35 }, { label: "28", prob: 16 }, { label: "29-30", prob: 7 }, { label: "31-32", prob: 2 },
      { label: "33-34", prob: 1 }, { label: "35-36", prob: 0 }, { label: "37°C+", prob: 0 },
    ] },
  },
  { id: "sng", name: "Singapore", x: 77, y: 58, region: "Asia", srcs: ["polymarket"],
    high: { unit: "C", mode: 32, dist: [
      { label: "<27°C", prob: 1 }, { label: "27-28", prob: 3 }, { label: "29-30", prob: 12 }, { label: "31", prob: 28 },
      { label: "32", prob: 33 }, { label: "33", prob: 15 }, { label: "34-35", prob: 5 }, { label: "36-37", prob: 2 },
      { label: "38-39", prob: 1 }, { label: "40-41", prob: 0 }, { label: "42°C+", prob: 0 },
    ] },
  },
  { id: "knw", name: "Lucknow", x: 71, y: 48, region: "Asia", srcs: ["polymarket"],
    high: { unit: "C", mode: 41, dist: [
      { label: "<35°C", prob: 2 }, { label: "35-36", prob: 5 }, { label: "37-38", prob: 13 }, { label: "39-40", prob: 24 },
      { label: "41", prob: 36 }, { label: "42", prob: 12 }, { label: "43-44", prob: 5 }, { label: "45-46", prob: 2 },
      { label: "47-48", prob: 1 }, { label: "49-50", prob: 0 }, { label: "51°C+", prob: 0 },
    ] },
  },
  { id: "man", name: "Manila", x: 83, y: 54, region: "Asia", srcs: ["polymarket"],
    high: { unit: "C", mode: 34, dist: [
      { label: "<29°C", prob: 2 }, { label: "29-30", prob: 6 }, { label: "31-32", prob: 16 }, { label: "33", prob: 24 },
      { label: "34", prob: 32 }, { label: "35", prob: 12 }, { label: "36-37", prob: 5 }, { label: "38-39", prob: 2 },
      { label: "40-41", prob: 1 }, { label: "42-43", prob: 0 }, { label: "44°C+", prob: 0 },
    ] },
  },
  { id: "jak", name: "Jakarta", x: 79, y: 60, region: "Asia", srcs: ["polymarket"],
    high: { unit: "C", mode: 33, dist: [
      { label: "<28°C", prob: 1 }, { label: "28-29", prob: 5 }, { label: "30-31", prob: 14 }, { label: "32", prob: 22 },
      { label: "33", prob: 34 }, { label: "34", prob: 14 }, { label: "35-36", prob: 6 }, { label: "37-38", prob: 2 },
      { label: "39-40", prob: 1 }, { label: "41-42", prob: 1 }, { label: "43°C+", prob: 0 },
    ] },
  },
  { id: "krc", name: "Karachi", x: 69, y: 49, region: "Asia", srcs: ["polymarket"],
    high: { unit: "C", mode: 36, dist: [
      { label: "<30°C", prob: 2 }, { label: "30-31", prob: 5 }, { label: "32-33", prob: 14 }, { label: "34-35", prob: 22 },
      { label: "36", prob: 30 }, { label: "37", prob: 16 }, { label: "38-39", prob: 7 }, { label: "40-41", prob: 2 },
      { label: "42-43", prob: 1 }, { label: "44-45", prob: 1 }, { label: "46°C+", prob: 0 },
    ] },
  },
  { id: "cpt", name: "Cape Town", x: 52, y: 71, region: "Africa", srcs: ["polymarket"],
    high: { unit: "C", mode: 20, dist: [
      { label: "<15°C", prob: 3 }, { label: "15-16", prob: 9 }, { label: "17-18", prob: 20 }, { label: "19", prob: 26 },
      { label: "20", prob: 24 }, { label: "21-22", prob: 11 }, { label: "23-24", prob: 4 }, { label: "25-26", prob: 2 },
      { label: "27-28", prob: 1 }, { label: "29-30", prob: 0 }, { label: "31°C+", prob: 0 },
    ] },
  },
  { id: "lag", name: "Lagos", x: 50, y: 57, region: "Africa", srcs: ["polymarket"],
    high: { unit: "C", mode: 32, dist: [
      { label: "<27°C", prob: 1 }, { label: "27-28", prob: 4 }, { label: "29-30", prob: 14 }, { label: "31", prob: 23 },
      { label: "32", prob: 32 }, { label: "33", prob: 15 }, { label: "34-35", prob: 7 }, { label: "36-37", prob: 3 },
      { label: "38-39", prob: 1 }, { label: "40-41", prob: 0 }, { label: "42°C+", prob: 0 },
    ] },
  },
  { id: "wlg", name: "Wellington", x: 92.5, y: 76, region: "Oceania", srcs: ["polymarket"],
    high: { unit: "C", mode: 14, dist: [
      { label: "<10°C", prob: 3 }, { label: "10-11", prob: 9 }, { label: "12-13", prob: 22 }, { label: "14", prob: 28 },
      { label: "15", prob: 20 }, { label: "16-17", prob: 11 }, { label: "18-19", prob: 4 }, { label: "20-21", prob: 2 },
      { label: "22-23", prob: 1 }, { label: "24-25", prob: 0 }, { label: "26°C+", prob: 0 },
    ] },
  },
  // Kalshi-only US cities (6 outcome buckets for high + low)
  { id: "bos", name: "Boston", x: 32, y: 38, region: "Americas", srcs: ["kalshi"],
    high: { unit: "F", mode: 71.5, dist: [
      { label: "<65°F", prob: 5 }, { label: "65-67", prob: 12 }, { label: "68-70", prob: 22 }, { label: "71-73", prob: 35 }, { label: "74-76", prob: 18 }, { label: "77°F+", prob: 8 },
    ] },
  },
  { id: "atl", name: "Atlanta", x: 28, y: 47, region: "Americas", srcs: ["polymarket", "kalshi"],
    high: { unit: "F", mode: 74.5, dist: [
      { label: "<68°F", prob: 3 }, { label: "68-70", prob: 8 }, { label: "71-73", prob: 18 }, { label: "74-76", prob: 42 }, { label: "77-79", prob: 20 }, { label: "80-81", prob: 6 },
      { label: "82-83", prob: 2 }, { label: "84-85", prob: 1 }, { label: "86-87", prob: 0 }, { label: "88-89", prob: 0 }, { label: "90°F+", prob: 0 },
    ] },
    kalshiHigh: { unit: "F", mode: 75, dist: [
      { label: "70° or below", prob: 4 }, { label: "71-73°", prob: 16 }, { label: "74-75°", prob: 38 }, { label: "76-77°", prob: 24 }, { label: "78-79°", prob: 12 }, { label: "80°+", prob: 6 },
    ] },
  },
  { id: "hou", name: "Houston", x: 24, y: 51, region: "Americas", srcs: ["polymarket", "kalshi"],
    high: { unit: "F", mode: 81, dist: [
      { label: "<74°F", prob: 2 }, { label: "74-75", prob: 5 }, { label: "76-77", prob: 10 }, { label: "78-79", prob: 16 },
      { label: "80-81", prob: 34 }, { label: "82-83", prob: 19 }, { label: "84-85", prob: 9 }, { label: "86-87", prob: 3 },
      { label: "88-89", prob: 1 }, { label: "90-91", prob: 1 }, { label: "92°F+", prob: 0 },
    ] },
    kalshiHigh: { unit: "F", mode: 81, dist: [
      { label: "76° or below", prob: 5 }, { label: "77-79°", prob: 14 }, { label: "80-81°", prob: 38 }, { label: "82-83°", prob: 26 }, { label: "84-85°", prob: 12 }, { label: "86°+", prob: 5 },
    ] },
  },
  { id: "den", name: "Denver", x: 21, y: 42, region: "Americas", srcs: ["polymarket", "kalshi"],
    high: { unit: "F", mode: 73.5, dist: [
      { label: "<66°F", prob: 4 }, { label: "66-68", prob: 10 }, { label: "69-71", prob: 20 }, { label: "72-74", prob: 32 }, { label: "75-77", prob: 22 }, { label: "78°F+", prob: 12 },
    ] },
    kalshiHigh: { unit: "F", mode: 73.5, dist: [
      { label: "68° or below", prob: 8 }, { label: "69-71°", prob: 18 }, { label: "72-73°", prob: 34 }, { label: "74-75°", prob: 22 }, { label: "76-77°", prob: 12 }, { label: "78°+", prob: 6 },
    ] },
  },
  { id: "sea", name: "Seattle", x: 17, y: 34, region: "Americas", srcs: ["polymarket", "kalshi"],
    high: { unit: "F", mode: 62, dist: [
      { label: "<56°F", prob: 5 }, { label: "56-58", prob: 12 }, { label: "59-61", prob: 25 }, { label: "62-64", prob: 35 }, { label: "65-67", prob: 16 }, { label: "68°F+", prob: 7 },
    ] },
    kalshiHigh: { unit: "F", mode: 62, dist: [
      { label: "56° or below", prob: 8 }, { label: "57-59°", prob: 18 }, { label: "60-62°", prob: 36 }, { label: "63-65°", prob: 24 }, { label: "66-67°", prob: 10 }, { label: "68°+", prob: 4 },
    ] },
  },
  { id: "phx", name: "Phoenix", x: 19.5, y: 47, region: "Americas", srcs: ["kalshi"],
    high: { unit: "F", mode: 80.5, dist: [
      { label: "<74°F", prob: 3 }, { label: "74-76", prob: 8 }, { label: "77-79", prob: 18 }, { label: "80-82", prob: 38 }, { label: "83-85", prob: 22 }, { label: "86°F+", prob: 11 },
    ] },
  },
  { id: "min", name: "Minneapolis", x: 24, y: 36, region: "Americas", srcs: ["kalshi"],
    high: { unit: "F", mode: 72.5, dist: [
      { label: "<66°F", prob: 5 }, { label: "66-68", prob: 12 }, { label: "69-71", prob: 22 }, { label: "72-74", prob: 32 }, { label: "75-77", prob: 20 }, { label: "78°F+", prob: 9 },
    ] },
  },
  { id: "phi", name: "Philadelphia", x: 31, y: 40, region: "Americas", srcs: ["kalshi"],
    high: { unit: "F", mode: 80.5, dist: [
      { label: "<74°F", prob: 3 }, { label: "74-76", prob: 8 }, { label: "77-79", prob: 18 }, { label: "80-82", prob: 38 }, { label: "83-85", prob: 22 }, { label: "86°F+", prob: 11 },
    ] },
  },
  { id: "lv", name: "Las Vegas", x: 19, y: 45, region: "Americas", srcs: ["kalshi"],
    high: { unit: "F", mode: 70.5, dist: [
      { label: "<64°F", prob: 4 }, { label: "64-66", prob: 10 }, { label: "67-69", prob: 22 }, { label: "70-72", prob: 35 }, { label: "73-75", prob: 20 }, { label: "76°F+", prob: 9 },
    ] },
  },
  { id: "okc", name: "Oklahoma City", x: 23.5, y: 45, region: "Americas", srcs: ["kalshi"],
    high: { unit: "F", mode: 85.5, dist: [
      { label: "<78°F", prob: 3 }, { label: "78-80", prob: 8 }, { label: "81-83", prob: 18 }, { label: "84-86", prob: 38 }, { label: "87-89", prob: 22 }, { label: "90°F+", prob: 11 },
    ] },
  },
  { id: "sat", name: "San Antonio", x: 23, y: 50, region: "Americas", srcs: ["kalshi"],
    high: { unit: "F", mode: 89, dist: [
      { label: "<82°F", prob: 3 }, { label: "82-84", prob: 8 }, { label: "85-87", prob: 18 }, { label: "88-90", prob: 38 }, { label: "91-93", prob: 22 }, { label: "94°F+", prob: 11 },
    ] },
  },
  { id: "nol", name: "New Orleans", x: 26, y: 50, region: "Americas", srcs: ["kalshi"],
    high: { unit: "F", mode: 81.5, dist: [
      { label: "<76°F", prob: 3 }, { label: "76-78", prob: 8 }, { label: "79-81", prob: 22 }, { label: "82-84", prob: 38 }, { label: "85-87", prob: 20 }, { label: "88°F+", prob: 9 },
    ] },
  },
  { id: "wdc", name: "Washington DC", x: 30.5, y: 42, region: "Americas", srcs: ["kalshi"],
    high: { unit: "F", mode: 84, dist: [
      { label: "<78°F", prob: 3 }, { label: "78-80", prob: 9 }, { label: "81-83", prob: 22 }, { label: "84-86", prob: 36 }, { label: "87-89", prob: 20 }, { label: "90°F+", prob: 10 },
    ] },
  },
  { id: "aus", name: "Austin", x: 23.5, y: 49, region: "Americas", srcs: ["polymarket", "kalshi"],
    high: { unit: "F", mode: 88.5, dist: [
      { label: "<82°F", prob: 2 }, { label: "82-84", prob: 6 }, { label: "85-87", prob: 16 }, { label: "88-90", prob: 40 }, { label: "91-93", prob: 24 }, { label: "94°F+", prob: 12 },
    ] },
    kalshiHigh: { unit: "F", mode: 88.5, dist: [
      { label: "82° or below", prob: 4 }, { label: "83-85°", prob: 12 }, { label: "86-88°", prob: 34 }, { label: "89-91°", prob: 32 }, { label: "92-93°", prob: 12 }, { label: "94°+", prob: 6 },
    ] },
  },
  // Additional Polymarket global cities
  { id: "ams", name: "Amsterdam", x: 50.5, y: 31, region: "Europe", srcs: ["polymarket"],
    high: { unit: "C", mode: 12, dist: [
      { label: "<8°C", prob: 3 }, { label: "8-9", prob: 9 }, { label: "10-11", prob: 22 }, { label: "12", prob: 45 },
      { label: "13", prob: 12 }, { label: "14-15", prob: 6 }, { label: "16-17", prob: 2 }, { label: "18-19", prob: 1 },
      { label: "20-21", prob: 0 }, { label: "22-23", prob: 0 }, { label: "24°C+", prob: 0 },
    ] },
  },
  { id: "hel", name: "Helsinki", x: 54, y: 26, region: "Europe", srcs: ["polymarket"],
    high: { unit: "C", mode: 13, dist: [
      { label: "<8°C", prob: 4 }, { label: "8-9", prob: 10 }, { label: "10-11", prob: 20 }, { label: "12", prob: 22 },
      { label: "13", prob: 26 }, { label: "14-15", prob: 12 }, { label: "16-17", prob: 4 }, { label: "18-19", prob: 1 },
      { label: "20-21", prob: 1 }, { label: "22-23", prob: 0 }, { label: "24°C+", prob: 0 },
    ] },
  },
  { id: "tlv", name: "Tel Aviv", x: 57, y: 44, region: "Asia", srcs: ["polymarket"],
    high: { unit: "C", mode: 22, dist: [
      { label: "<17°C", prob: 2 }, { label: "17-18", prob: 6 }, { label: "19-20", prob: 16 }, { label: "21", prob: 24 },
      { label: "22", prob: 30 }, { label: "23", prob: 14 }, { label: "24-25", prob: 5 }, { label: "26-27", prob: 2 },
      { label: "28-29", prob: 1 }, { label: "30-31", prob: 0 }, { label: "32°C+", prob: 0 },
    ] },
  },
  { id: "jed", name: "Jeddah", x: 59, y: 51, region: "Asia", srcs: ["polymarket"],
    high: { unit: "C", mode: 34, dist: [
      { label: "<29°C", prob: 2 }, { label: "29-30", prob: 6 }, { label: "31-32", prob: 16 }, { label: "33", prob: 24 },
      { label: "34", prob: 31 }, { label: "35", prob: 13 }, { label: "36-37", prob: 5 }, { label: "38-39", prob: 2 },
      { label: "40-41", prob: 1 }, { label: "42-43", prob: 0 }, { label: "44°C+", prob: 0 },
    ] },
  },
  { id: "bus", name: "Busan", x: 82, y: 40, region: "Asia", srcs: ["polymarket"],
    high: { unit: "C", mode: 22, dist: [
      { label: "<17°C", prob: 3 }, { label: "17-18", prob: 8 }, { label: "19-20", prob: 19 }, { label: "21", prob: 24 },
      { label: "22", prob: 28 }, { label: "23", prob: 11 }, { label: "24-25", prob: 5 }, { label: "26-27", prob: 1 },
      { label: "28-29", prob: 1 }, { label: "30-31", prob: 0 }, { label: "32°C+", prob: 0 },
    ] },
  },
  { id: "szn", name: "Shenzhen", x: 79, y: 51, region: "Asia", srcs: ["polymarket"],
    high: { unit: "C", mode: 29, dist: [
      { label: "<24°C", prob: 2 }, { label: "24-25", prob: 5 }, { label: "26-27", prob: 14 }, { label: "28", prob: 22 },
      { label: "29", prob: 33 }, { label: "30", prob: 14 }, { label: "31-32", prob: 6 }, { label: "33-34", prob: 3 },
      { label: "35-36", prob: 1 }, { label: "37-38", prob: 0 }, { label: "39°C+", prob: 0 },
    ] },
  },
  { id: "kul", name: "Kuala Lumpur", x: 77, y: 56, region: "Asia", srcs: ["polymarket"],
    high: { unit: "C", mode: 32, dist: [
      { label: "<27°C", prob: 1 }, { label: "27-28", prob: 4 }, { label: "29-30", prob: 12 }, { label: "31", prob: 25 },
      { label: "32", prob: 33 }, { label: "33", prob: 15 }, { label: "34-35", prob: 6 }, { label: "36-37", prob: 3 },
      { label: "38-39", prob: 1 }, { label: "40-41", prob: 0 }, { label: "42°C+", prob: 0 },
    ] },
  },
  { id: "mil", name: "Milan", x: 51, y: 36, region: "Europe", srcs: ["polymarket"],
    high: { unit: "C", mode: 21, dist: [
      { label: "<16°C", prob: 3 }, { label: "16-17", prob: 7 }, { label: "18-19", prob: 18 }, { label: "20", prob: 25 },
      { label: "21", prob: 28 }, { label: "22", prob: 12 }, { label: "23-24", prob: 4 }, { label: "25-26", prob: 2 },
      { label: "27-28", prob: 1 }, { label: "29-30", prob: 0 }, { label: "31°C+", prob: 0 },
    ] },
  },
  { id: "pnm", name: "Panama City", x: 26.5, y: 55, region: "Americas", srcs: ["polymarket"],
    high: { unit: "C", mode: 31, dist: [
      { label: "<26°C", prob: 1 }, { label: "26-27", prob: 3 }, { label: "28-29", prob: 10 }, { label: "30", prob: 22 },
      { label: "31", prob: 36 }, { label: "32", prob: 18 }, { label: "33-34", prob: 7 }, { label: "35-36", prob: 2 },
      { label: "37-38", prob: 1 }, { label: "39-40", prob: 0 }, { label: "41°C+", prob: 0 },
    ] },
  },
  { id: "ank", name: "Ankara", x: 56, y: 41, region: "Europe", srcs: ["polymarket"],
    high: { unit: "C", mode: 13, dist: [
      { label: "<8°C", prob: 3 }, { label: "8-9", prob: 8 }, { label: "10-11", prob: 18 }, { label: "12", prob: 24 },
      { label: "13", prob: 28 }, { label: "14-15", prob: 12 }, { label: "16-17", prob: 4 }, { label: "18-19", prob: 2 },
      { label: "20-21", prob: 1 }, { label: "22-23", prob: 0 }, { label: "24°C+", prob: 0 },
    ] },
  },
  { id: "wrw", name: "Warsaw", x: 53, y: 30, region: "Europe", srcs: ["polymarket"],
    high: { unit: "C", mode: 14, dist: [
      { label: "<9°C", prob: 3 }, { label: "9-10", prob: 8 }, { label: "11-12", prob: 18 }, { label: "13", prob: 24 },
      { label: "14", prob: 28 }, { label: "15-16", prob: 12 }, { label: "17-18", prob: 4 }, { label: "19-20", prob: 2 },
      { label: "21-22", prob: 1 }, { label: "23-24", prob: 0 }, { label: "25°C+", prob: 0 },
    ] },
  },
];

export const NYC_RAIN: RainDay[] = [
  { day: "Mon", date: "Apr 20", prob: 72, icon: "🌧️" },
  { day: "Tue", date: "Apr 21", prob: 66, icon: "🌧️" },
  { day: "Wed", date: "Apr 22", prob: 34, icon: "⛅" },
  { day: "Thu", date: "Apr 23", prob: 100, icon: "☔" },
  { day: "Fri", date: "Apr 24", prob: 35, icon: "⛅" },
  { day: "Sat", date: "Apr 25", prob: 100, icon: "☔" },
  { day: "Sun", date: "Apr 26", prob: 74, icon: "🌧️" },
];

export const MONTHLY_RAIN: MonthlyRain[] = [
  { city: "NYC", prob: 92, src: "kalshi" },
  { city: "Seattle", prob: 85, src: "kalshi" },
  { city: "Miami", prob: 74, src: "kalshi" },
  { city: "Houston", prob: 62, src: "kalshi" },
  { city: "Chicago", prob: 58, src: "kalshi" },
  { city: "Austin", prob: 51, src: "kalshi" },
  { city: "San Francisco", prob: 42, src: "kalshi" },
  { city: "Dallas", prob: 38, src: "kalshi" },
  { city: "Denver", prob: 34, src: "kalshi" },
  { city: "Los Angeles", prob: 10, src: "kalshi" },
];

export const HURRICANE: EventMarket[] = [
  { q: "Hurricane forms by May 31", prob: 21, src: "polymarket", closes: "Sat, May 31" },
  { q: "Hurricane makes US landfall by May 31", prob: 8, src: "polymarket", closes: "Sat, May 31" },
  { q: "Any Cat 4 lands in US before 2027", prob: 36, src: "polymarket", closes: "Thu, Dec 31" },
  { q: "Any Cat 5 lands in US before 2027", prob: 15, src: "polymarket", closes: "Thu, Dec 31" },
  { q: ">10 tropical storms in 2026", prob: 78, src: "kalshi", closes: "Thu, Dec 31" },
  { q: ">4 Atlantic hurricanes in 2026", prob: 82, src: "kalshi", closes: "Thu, Dec 31" },
  { q: ">0 major Atlantic hurricanes 2026", prob: 80, src: "kalshi", closes: "Thu, Dec 31" },
];

export const EARTHQUAKE: EventMarket[] = [
  { q: "Megaquake before June 30", prob: 18, src: "polymarket", closes: "Tue, Jun 30" },
  { q: "Another 7.0+ earthquake by Apr 30", prob: 37, src: "polymarket", closes: "Thu, Apr 30" },
  { q: "9.0+ earthquake before 2027", prob: 10, src: "polymarket", closes: "Thu, Dec 31" },
  { q: "8.0 earthquake in California before 2027", prob: 8, src: "kalshi", closes: "Thu, Dec 31" },
  { q: "8.0 earthquake in California before 2028", prob: 13, src: "kalshi", closes: "Fri, Dec 31" },
  { q: "8.0 earthquake in Japan before 2030", prob: 50, src: "kalshi", closes: "2029-12-31" },
  { q: "Zero 6.5+ quakes this week", prob: 48, src: "polymarket", closes: "Sun, Apr 26" },
];

export const TORNADOES: EventMarket[] = [
  { q: ">170 tornadoes in April", prob: 32, src: "polymarket", closes: "Thu, Apr 30" },
  { q: "1250+ US tornadoes in 2026", prob: 60, src: "polymarket", closes: "Thu, Dec 31" },
];

export const CLIMATE: ClimateMarket[] = [
  { q: "Any month of 2026 is hottest on record", prob: 78, src: "polymarket", scale: "2026" },
  { q: "2026 is the hottest year ever", prob: 38, src: "kalshi", scale: "2026" },
  { q: "CO₂ concentration above 440 ppm before 2030", prob: 88, src: "kalshi", scale: "2030" },
  { q: "World passes 2°C over pre-industrial by 2050", prob: 78, src: "kalshi", scale: "2050" },
  { q: "US meets climate goals by 2030", prob: 16, src: "kalshi", scale: "2030" },
  { q: "EU meets 2030 climate goals", prob: 44, src: "kalshi", scale: "2030" },
  { q: "India meets its 2030 climate goals", prob: 66, src: "kalshi", scale: "2030" },
  { q: "EV market share above 10% in 2030", prob: 87, src: "kalshi", scale: "2030" },
];

export const WILDCARDS: WildCard[] = [
  { q: "Supervolcano erupts before 2050", prob: 21, src: "kalshi", tag: "Once-in-civilization" },
  { q: "Arctic sea ice <4M km² this summer", prob: 43, src: "polymarket", tag: "Ice record" },
  { q: "Major solar storm before April 30", prob: 3, src: "polymarket", tag: "Space weather" },
  { q: "Zero major space weather events this week", prob: 38, src: "polymarket", tag: "Space weather" },
  { q: "Zero VEI≥4 volcano eruptions in 2026", prob: 55, src: "polymarket", tag: "Volcanic" },
];

export function probColor(p: number): string {
  if (p >= 65) return "#22C55E";
  if (p >= 35) return "#F59E0B";
  return "#EF4444";
}

export function probLabel(p: number): string {
  if (p >= 65) return "Likely";
  if (p >= 35) return "Toss-up";
  return "Unlikely";
}

export function tempColorC(tempC: number): string {
  const stops = [
    { t: -10, c: [37, 99, 235] },
    { t: 5, c: [56, 189, 248] },
    { t: 15, c: [148, 163, 184] },
    { t: 22, c: [245, 158, 11] },
    { t: 32, c: [239, 68, 68] },
    { t: 45, c: [159, 18, 57] },
  ];
  const t = Math.max(stops[0].t, Math.min(stops[stops.length - 1].t, tempC));
  for (let i = 0; i < stops.length - 1; i++) {
    const a = stops[i], b = stops[i + 1];
    if (t >= a.t && t <= b.t) {
      const f = (t - a.t) / (b.t - a.t);
      const c = [0, 1, 2].map(k => Math.round(a.c[k] + (b.c[k] - a.c[k]) * f));
      return `rgb(${c[0]},${c[1]},${c[2]})`;
    }
  }
  return "#94A3B8";
}

export function toC(city: CityData): number {
  return city.high.unit === "C" ? city.high.mode : ((city.high.mode - 32) * 5) / 9;
}

export function sparkFrom(seed: number, end: number, n = 14): number[] {
  let s = seed;
  const rng = () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
  const start = Math.max(2, Math.min(98, end + (rng() * 30 - 15)));
  const pts: number[] = [];
  let cur = start;
  for (let i = 0; i < n - 1; i++) {
    const target = start + ((end - start) * i) / (n - 1);
    cur = cur * 0.55 + target * 0.45 + (rng() * 8 - 4);
    pts.push(Math.max(2, Math.min(98, cur)));
  }
  pts.push(end);
  return pts;
}
