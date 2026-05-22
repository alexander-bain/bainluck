export function ratioText(value: number, total: number) {
  return `${value}/${total}`;
}

export function formatTargetName(name: string) {
  return name.replaceAll("_", " ");
}

export function percentText(value: number | null) {
  return value === null ? "none" : `${Math.round(value * 100)}%`;
}

export function rateText(value: number) {
  return `${Math.round(value * 100)}%`;
}

export function signedNumber(value: number, digits = 0) {
  const fixed = value.toFixed(digits);
  return value > 0 ? `+${fixed}` : fixed;
}

export function rankText(value: number | null) {
  return value === null ? "out" : `#${value}`;
}

export function itemHref(itemType: string, itemId: string | number | null | undefined) {
  if (itemId === null || itemId === undefined || itemId === "") return null;
  if (itemType === "futures") return `/futures/${itemId}`;
  if (itemType === "event") return `/events/${itemId}`;
  return null;
}
