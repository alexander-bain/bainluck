/**
 * The labels a golf card's chaser strip prints — #9750.
 *
 * `/sports`, 390px, 2026-09-30: the LPGA LOTTE Championship card's strip read
 * "Kim 9.0%" beside "Kim 7.7%" — A Lim Kim and Hyo Joo Kim, printed as one
 * word each. The strip printed the last word of every name, and an LPGA field
 * routinely carries several Kims, Lees and Parks, so two columns could name two
 * golfers with the same string and nothing on the card could tell them apart.
 *
 * THE RULE. A chaser keeps the surname it has always printed. Only where two
 * chasers share a surname does each of them take the initial of their given
 * name ("A. Kim", "H. Kim"), and where the initials collide as well ("A Lim
 * Kim" / "Auston Kim") the full name is printed — the tile truncates, but a
 * truncated full name still starts on the part that differs.
 *
 * Compared case-blind; the labels keep the served spelling.
 */

function words(name: string): string[] {
  return name.trim().split(/\s+/).filter(Boolean);
}

function surname(name: string): string {
  const parts = words(name);
  return parts.length > 1 ? parts[parts.length - 1] : name.trim();
}

function initialled(name: string): string {
  const parts = words(name);
  if (parts.length < 2) return name.trim();
  return `${parts[0].charAt(0).toUpperCase()}. ${parts[parts.length - 1]}`;
}

function counts(labels: string[]): Map<string, number> {
  const seen = new Map<string, number>();
  for (const label of labels) {
    const key = label.toLowerCase();
    seen.set(key, (seen.get(key) ?? 0) + 1);
  }
  return seen;
}

export function golfChaserLabels(names: string[]): string[] {
  const surnames = names.map(surname);
  const surnameCounts = counts(surnames);
  const shared = (label: string, seen: Map<string, number>) =>
    (seen.get(label.toLowerCase()) ?? 0) > 1;

  const initials = names.map((name, i) =>
    shared(surnames[i], surnameCounts) ? initialled(name) : surnames[i],
  );
  const initialCounts = counts(initials);
  return names.map((name, i) =>
    shared(surnames[i], surnameCounts) && shared(initials[i], initialCounts)
      ? name.trim()
      : initials[i],
  );
}
