/**
 * Pure pinned-id logic, split out of the pin hooks so the account-boundary
 * claims are testable without a DOM (UX-P017 / #1496).
 *
 * The claim that actually needs proving is a negative one — "no id originating
 * from account A is ever pushed to account B" — and a negative is only provable
 * where the decision is made. Inside a React effect it is not reachable by this
 * repo's `testEnvironment: 'node'` jest setup; here it is a table test.
 */

/** Parse a stored id list, tolerating absent, corrupt, or hand-edited values. */
export function parseIds(raw: string | null): number[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.every((id: unknown) => typeof id === "number")) {
      return parsed;
    }
    return [];
  } catch {
    return [];
  }
}

export function serializeIds(ids: number[]): string {
  return JSON.stringify(ids);
}

/**
 * What an account's pin set becomes when a device's ANONYMOUS pins are merged
 * into it on sign-in, and which of them must be pushed to the server.
 *
 * `migrateIds` must come from the anonymous bucket alone — never from another
 * account's cache. `pendingAnonymousMigration` in `principalStorage` is what
 * enforces that upstream; this function is deliberately dumb about provenance so
 * the two responsibilities stay separable and separately testable.
 *
 * Server ids come first and are never dropped: the server is authoritative for a
 * signed-in account, so `max` truncates the migrated tail rather than anything
 * the account already owns. An account that is already at the cap therefore
 * adopts nothing, which is also the safest behaviour if provenance were ever
 * wrong.
 */
export function mergeForMigration(
  serverIds: number[],
  migrateIds: number[],
  max: number
): { merged: number[]; toPush: number[] } {
  const alreadyOnServer = new Set(serverIds);
  const merged = [...serverIds];
  // Only ids that actually survive into the merged set get pushed, so the
  // server never receives an id the user cannot see.
  const toPush: number[] = [];

  for (const id of migrateIds) {
    if (merged.length >= max) break;
    if (alreadyOnServer.has(id)) continue;
    alreadyOnServer.add(id);
    merged.push(id);
    toPush.push(id);
  }

  return { merged, toPush };
}
