export function probabilityMovement(value: number | null | undefined, baseline: number | null | undefined): string {
  if (value == null || baseline == null || !Number.isFinite(value) || !Number.isFinite(baseline) || value < 0 || value > 1 || baseline < 0 || baseline > 1) return 'Comparison unavailable';
  if (value === baseline) return 'At the pre-match baseline';
  const points = Math.abs(value - baseline) * 100;
  const amount = points < .01 ? 'less than 0.01' : new Intl.NumberFormat('en-US', {maximumFractionDigits: 2}).format(points);
  return `${value > baseline ? 'Up' : 'Down'} ${amount} points from pre-match`;
}
