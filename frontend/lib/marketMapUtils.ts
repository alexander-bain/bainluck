export function posOnRail(value: number, min: number, max: number): number {
  return Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));
}

export function rgbaFromIntensity(intensity: number, rgb: string): string {
  const alpha = 0.10 + (intensity / 100) * 0.78;
  return `rgba(${rgb},${alpha.toFixed(2)})`;
}

export interface ParsedSpread {
  team: string;
  threshold: number;
  probability: number;
  source: string;
  isHome: boolean;
  margin: number;
}

export function parseSpreadOutcome(
  outcomeName: string,
  probability: number,
  source: string,
  homeTeam: string,
  awayTeam: string
): ParsedSpread | null {
  const lower = outcomeName.toLowerCase();
  const homeWords = homeTeam.toLowerCase().split(" ");
  const awayWords = awayTeam.toLowerCase().split(" ");
  const isHome = homeWords.some((w) => w.length >= 3 && lower.includes(w));
  const isAway = awayWords.some((w) => w.length >= 3 && lower.includes(w));
  if (!isHome && !isAway) return null;

  const matches = outcomeName.match(/(\d+\.?\d*)/g);
  if (!matches || matches.length === 0) return null;
  const threshold = parseFloat(matches[matches.length - 1]);

  const team = isHome ? homeTeam : awayTeam;
  const margin = isHome ? threshold : -threshold;

  return { team, threshold, probability, source, isHome, margin };
}

export function isFullGameSpread(marketName: string): boolean {
  const lower = (marketName || "").toLowerCase();
  return (
    !lower.includes("1h") &&
    !lower.includes("1st half") &&
    !lower.includes("first half") &&
    !lower.includes("2h") &&
    !lower.includes("2nd half") &&
    !lower.includes("second half") &&
    !lower.includes("first 5")
  );
}

export function isGameTotal(outcomeName: string): boolean {
  return !outcomeName.includes(":");
}

export function buildDensityFromSpreads(
  spreads: ParsedSpread[],
  rangeMin: number,
  rangeMax: number,
  segments: number = 14
): number[] {
  if (spreads.length === 0) return new Array(segments).fill(5);

  const density = new Array(segments).fill(0);
  const step = (rangeMax - rangeMin) / segments;

  for (const s of spreads) {
    const segIdx = Math.floor((s.margin - rangeMin) / step);
    const clampedIdx = Math.max(0, Math.min(segments - 1, segIdx));
    density[clampedIdx] += s.probability;
  }

  const peak = Math.max(...density, 0.01);
  return density.map((d) => Math.round((d / peak) * 96));
}

export function buildDensityFromThresholds(
  thresholds: Array<{ threshold: number; overProbability: number }>,
  rangeMin: number,
  rangeMax: number,
  segments: number = 12
): number[] {
  if (thresholds.length < 2) return new Array(segments).fill(8);

  const sorted = [...thresholds].sort((a, b) => a.threshold - b.threshold);

  const rawPdf: Array<{ mid: number; density: number }> = [];
  for (let i = 0; i < sorted.length - 1; i++) {
    const dt = sorted[i + 1].threshold - sorted[i].threshold;
    if (dt <= 0) continue;
    const dp = sorted[i].overProbability - sorted[i + 1].overProbability;
    rawPdf.push({
      mid: (sorted[i].threshold + sorted[i + 1].threshold) / 2,
      density: Math.max(0, dp / dt),
    });
  }

  if (rawPdf.length === 0) return new Array(segments).fill(8);

  const step = (rangeMax - rangeMin) / segments;
  const density = new Array(segments).fill(0);

  for (let i = 0; i < segments; i++) {
    const x = rangeMin + (i + 0.5) * step;
    let d = 0;

    if (rawPdf.length === 1) {
      d = rawPdf[0].density;
    } else if (x <= rawPdf[0].mid) {
      d = rawPdf[0].density * Math.max(0, 1 - (rawPdf[0].mid - x) / (step * 3));
    } else if (x >= rawPdf[rawPdf.length - 1].mid) {
      d = rawPdf[rawPdf.length - 1].density * Math.max(0, 1 - (x - rawPdf[rawPdf.length - 1].mid) / (step * 3));
    } else {
      for (let j = 0; j < rawPdf.length - 1; j++) {
        if (x >= rawPdf[j].mid && x <= rawPdf[j + 1].mid) {
          const t = (x - rawPdf[j].mid) / (rawPdf[j + 1].mid - rawPdf[j].mid);
          d = rawPdf[j].density * (1 - t) + rawPdf[j + 1].density * t;
          break;
        }
      }
    }
    density[i] = d;
  }

  // Smooth: simple 3-point moving average to reduce choppiness
  const smoothed = density.map((_, i) => {
    const prev = i > 0 ? density[i - 1] : density[i];
    const next = i < density.length - 1 ? density[i + 1] : density[i];
    return (prev + density[i] * 2 + next) / 4;
  });

  const peak = Math.max(...smoothed, 0.001);
  return smoothed.map((d) => Math.round((d / peak) * 96));
}

export function sportVocab(sportKey: string | undefined): {
  marginTitle: string;
  totalTitle: string;
  unit: string;
  unitSingular: string;
} {
  const key = (sportKey || "").toLowerCase();
  if (key.includes("baseball") || key.includes("mlb")) {
    return { marginTitle: "Run margin map", totalTitle: "Runs map", unit: "runs", unitSingular: "run" };
  }
  if (key.includes("hockey") || key.includes("nhl")) {
    return { marginTitle: "Goal margin map", totalTitle: "Goals map", unit: "goals", unitSingular: "goal" };
  }
  if (key.includes("soccer") || key.includes("mls") || key.includes("epl")) {
    return { marginTitle: "Goal margin map", totalTitle: "Goals map", unit: "goals", unitSingular: "goal" };
  }
  return { marginTitle: "Margin map", totalTitle: "Total map", unit: "points", unitSingular: "point" };
}
