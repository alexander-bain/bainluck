/**
 * WHAT `/health/ready`'s `last_polls` IS ALLOWED TO PAINT GREEN.
 *
 * `checks.last_polls` is a Record of source → ISO stamp on the happy path, but
 * the route falls back to the bare STRING `"unavailable"` when its Redis read
 * raises (`backend/app/routes/health.py`). The admin PREQ card typed the field
 * as a Record and handed it straight to `Object.entries`, which does not throw
 * on a string — it enumerates the characters. Measured: a Redis outage drew
 * ELEVEN rows labelled "0".."10", every one with a GREEN dot (each character is
 * truthy) and every one reading "NaNd ago".
 *
 * That is the failure the readiness route's own comment argues against one
 * screen upstream: a probe whose reading is wrong in the REASSURING direction
 * is worse than no probe, because the one that means something gets ignored
 * too. The outage is precisely when the operator is looking at this card.
 *
 * So the reading is made explicit, and the three cases are kept apart:
 *   - `stamps`      — a real map; the only case that may draw a dot at all.
 *   - `unavailable` — the field came back, we could not read it. Say so.
 *   - `absent`      — the field was never served. Not our story to tell.
 *
 * A non-string stamp inside an otherwise-good map is nulled rather than
 * dropped: the source is real and we have no time for it, which is exactly
 * what a grey dot means. Letting it through is how the same "NaNd ago" green
 * dot comes back for one row instead of eleven.
 */

export type LastPollStamps = Record<string, string | null>;

export type LastPollsReading =
  | { kind: "stamps"; stamps: LastPollStamps }
  | { kind: "unavailable" }
  | { kind: "absent" };

export function readLastPolls(value: unknown): LastPollsReading {
  if (value === undefined || value === null) return { kind: "absent" };

  // A string, a number, an array — anything that is not a plain object — is a
  // shape we cannot read as source→stamp, however happily it enumerates.
  if (typeof value !== "object" || Array.isArray(value)) {
    return { kind: "unavailable" };
  }

  const stamps: LastPollStamps = {};
  for (const [source, ts] of Object.entries(value as Record<string, unknown>)) {
    stamps[source] = typeof ts === "string" ? ts : null;
  }
  return { kind: "stamps", stamps };
}
