/** Bounded CUA DOM recorder. No navigation, network client, file writes or daemon. */
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

export async function captureObservation(tab, {
  eventId, durationMs = 180_000, now = () => performance.now(), wait = sleep,
} = {}) {
  if (!/^\d+$/.test(String(eventId)) || Number(eventId) <= 0
      || !Number.isFinite(durationMs) || durationMs <= 0 || durationMs > 180_000) {
    throw new TypeError('A positive eventId and durationMs in (0, 180000] are required');
  }
  const origin = now(), samples = [];
  while (now() - origin < durationMs) {
    const beginMs = now() - origin;
    try {
      const components = await tab.playwright.getByTestId('live-connection-status').evaluateAll(nodes => {
          const visible = node => {
            if (!node) return false;
            const r = node.getBoundingClientRect(), style = getComputedStyle(node);
            if (!(r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0
              && r.top < innerHeight && r.left < innerWidth
              && style.visibility !== 'hidden' && style.display !== 'none'
              && style.opacity !== '0' && !node.closest('[hidden]'))) return false;
            // A fullscreen modal can cover the still-mounted inline copy.
            const x = (Math.max(0, r.left) + Math.min(innerWidth, r.right)) / 2;
            const y = (Math.max(0, r.top) + Math.min(innerHeight, r.bottom)) / 2;
            const top = document.elementFromPoint(x, y);
            return top !== null && (top === node || node.contains(top));
          };
          return nodes.map(node => {
            const button = node.querySelector('button[aria-expanded]');
            const panelId = button?.getAttribute('aria-controls');
            return {
              eventId: node.getAttribute('data-observation-event-id'),
              observedAt: node.getAttribute('data-observation-at'),
              count: node.getAttribute('data-observation-count'),
              delivery: node.getAttribute('data-observation-delivery'),
              visible: visible(node),
              disclosureOpen: button?.getAttribute('aria-expanded') === 'true',
              disclosureVisible: panelId ? visible(document.getElementById(panelId)) : null,
            };
          });
        }, undefined, { timeoutMs: Math.max(1, Math.ceil(durationMs - (now() - origin))) });
      samples.push({ beginMs, endMs: now() - origin, components });
    } catch (error) {
      samples.push({ beginMs, endMs: now() - origin, error: String(error?.message ?? error) });
    }
    if (now() - origin >= durationMs) break;
    // One read in flight; skip missed polling slots instead of catching up.
    const next = Math.min(durationMs, (Math.floor((now() - origin) / 100) + 1) * 100);
    await wait(Math.max(0, next - (now() - origin)));
  }
  const endMs = now() - origin;
  const capture = { schema: 1, eventId: String(eventId), requestedDurationMs: durationMs,
    endMs, overrunMs: Math.max(0, endMs - durationMs), pollMs: 100, samples };
  return { ...capture, analysis: analyzeObservation(capture) };
}

// Preserve exact strings, compare milliseconds like the UI's high-water
// counter, not its printed second. Only explicit time zones qualify.
function timestamp(value) {
  if (typeof value !== 'string') return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})$/.exec(value);
  if (!m) return null;
  const [year, month, day, hour, minute, second] = m.slice(1, 7).map(Number);
  const utc = Date.UTC(year, month - 1, day, hour, minute, second), d = new Date(utc);
  if (d.getUTCFullYear() !== year || d.getUTCMonth() !== month - 1 || d.getUTCDate() !== day
      || hour > 23 || minute > 59 || second > 59) return null;
  const zone = m[8], zh = zone === 'Z' ? 0 : Number(zone.slice(1, 3));
  const zm = zone === 'Z' ? 0 : Number(zone.slice(4, 6));
  if (zh > 23 || zm > 59) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** Main metric is the whole-window maximum no-forward-observation interval.
 * Bounds describe DOM read uncertainty; they are not input-to-user latency. */
export function analyzeObservation(capture, { maxReadMs = 500, maxGapMs = 500 } = {}) {
  const issues = [], advances = [], rollbacks = [], intervals = [], selected = [];
  const issue = (kind, index, detail) => issues.push({ kind, index, ...(detail === undefined ? {} : { detail }) });
  const end = capture.endMs;
  if (!Number.isFinite(end) || end < 0 || !Array.isArray(capture.samples)) {
    return { qualification: 'NO_RESULT', longest: null, issues: [{ kind: 'invalid-capture' }] };
  }
  let previousReadEnd = 0, prior = null, highwater = null, highwaterAt = null, reliable = 0;
  let boundary = null, last = null;
  for (const [i, sample] of capture.samples.entries()) {
    const { beginMs: begin, endMs: finish } = sample;
    if (!Number.isFinite(begin) || !Number.isFinite(finish) || begin < previousReadEnd
        || finish < begin || finish > end) { issue('invalid-read-timing', i); continue; }
    if (begin - previousReadEnd > maxGapMs) issue('recorder-gap', i, begin - previousReadEnd);
    previousReadEnd = finish;
    const slow = finish - begin > maxReadMs;
    if (slow) issue('slow-read', i, finish - begin);
    if (sample.error || !Array.isArray(sample.components)) { issue('read-failed', i, sample.error); continue; }
    const candidates = sample.components.filter(c => c.visible === true && String(c.eventId) === String(capture.eventId));
    if (candidates.length !== 1) {
      issue(candidates.length ? 'duplicate-visible-target' : 'no-visible-target', i,
        { componentCount: sample.components.length, visibleEventIds: sample.components.filter(c => c.visible).map(c => c.eventId) });
      continue;
    }
    const value = candidates[0], at = timestamp(value.observedAt);
    if (value.disclosureOpen !== true || value.disclosureVisible !== true) {
      issue('timestamp-disclosure-not-visible', i,
        { open: value.disclosureOpen ?? null, visible: value.disclosureVisible ?? null });
    }
    const count = /^\d+$/.test(String(value.count)) ? Number(value.count) : NaN;
    if (at === null || !Number.isSafeInteger(count) || count < 1
        || !['dnpl', 'committed', 'unknown'].includes(value.delivery)) { issue('invalid-observation', i); continue; }
    const current = { beginMs: begin, endMs: finish, ...value };
    selected.push(current);
    if (!slow) reliable++;
    if (prior) {
      const delta = count - Number(prior.count);
      if (delta < 0) issue('counter-reset', i);
      if (delta > 1) issue('missed-forward-updates', i, delta - 1);
      if (at > highwater && delta !== 1) issue('forward-counter-disagreement', i);
      if (at <= highwater && delta > 0) issue('unseen-forward-update', i);
    }
    if (highwater === null) {
      highwater = at; highwaterAt = value.observedAt;
      // The baseline was observed somewhere inside the first read.
      boundary = { lowerMs: 0, upperMs: finish, edge: 'left' };
    } else if (at > highwater) {
      const arrival = { lowerMs: prior.beginMs, upperMs: finish, observedAt: value.observedAt,
        count, delivery: value.delivery };
      intervals.push({ kind: boundary.edge === 'left' ? 'left-censored' : 'completed',
        lowerMs: Math.max(0, arrival.lowerMs - boundary.upperMs),
        upperMs: Math.max(0, arrival.upperMs - boundary.lowerMs) });
      advances.push(arrival); boundary = arrival; highwater = at; highwaterAt = value.observedAt;
    } else if (at < highwater) {
      rollbacks.push({ beginMs: begin, endMs: finish, observedAt: value.observedAt, highwaterAt });
    }
    prior = current; last = current;
  }
  if (end - previousReadEnd > maxGapMs) issue('recorder-trailing-gap', capture.samples.length, end - previousReadEnd);
  if (capture.outstandingRead) issue('outstanding-read-at-deadline', capture.samples.length);
  if (last && boundary) intervals.push({ kind: advances.length ? 'right-censored' : 'both-censored',
    lowerMs: Math.max(0, last.beginMs - boundary.upperMs),
    upperMs: Math.max(0, end - boundary.lowerMs) });
  const qualification = reliable < 2 || !last || last.beginMs <= selected[0].endMs ? 'NO_RESULT' : issues.length ? 'UNQUALIFIED' : 'QUALIFIED';
  const winner = intervals.reduce((a, b) => !a || b.lowerMs > a.lowerMs ? b : a, null);
  return { qualification, longest: qualification === 'NO_RESULT' || !winner ? null : {
    ...winner, upperMs: Math.max(...intervals.map(x => x.upperMs)),
    isWholeSampleQualified: qualification === 'QUALIFIED',
  }, issues, intervals, advances, rollbacks, samplesRead: capture.samples.length,
  validSamples: selected.length, highwaterAt, selected };
}
