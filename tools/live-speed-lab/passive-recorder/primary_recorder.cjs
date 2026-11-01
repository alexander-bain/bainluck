'use strict';
// #11674: copied byte-for-byte from the staged observe.cjs (sha256 f8b5543f…, lines 53-146).
// The verbatim span is pinned by test_recorder_units.cjs; do not edit it.
// Browser-local primary record. Callback time is a DOM observation, never paint time.
function installVisibleObservationRecorder(options = {}) {
 const slot = '__visibleObservationRecorder11434';
 if (window[slot]) throw new Error('primary recorder already installed');
 const selector = '[data-testid="live-connection-status"]';
 const maxEntries = options.maxEntries ?? 50000, maxBytes = options.maxBytes ?? 8 * 1024 * 1024;
 if (!Number.isInteger(maxEntries) || maxEntries < 2 || !Number.isInteger(maxBytes) || maxBytes < 128) throw new Error('invalid primary limits');
 const captureId = options.captureId;
 if (typeof captureId !== 'string' || !captureId) throw new Error('primary capture identity required');
 const entries = [], faults = [], ancestors = [];
 let root = null, timeNode = null, rootGeneration = 0, timeGeneration = 0, ancestorGeneration = 0;
 let seq = 0, bytes = 0, dropped = 0, stopped = false, previousKey = null, previousTimestamp = null;
 const installed = {mono: performance.now(), wall: Date.now(), timeOrigin: performance.timeOrigin};
 const fault = message => { if (!faults.includes(message)) faults.push(message); };
 function append(value) {
  const row = {seq: ++seq, ...value};
  const size = new TextEncoder().encode(JSON.stringify(row)).length;
  if (entries.length >= maxEntries || bytes + size > maxBytes) { dropped++; fault('primary-buffer-overflow'); return; }
  entries.push(row); bytes += size;
 }
 function state() {
  const roots = [...document.querySelectorAll(selector)];
  const labels = root ? [...root.querySelectorAll('dt')].filter(n => n.textContent.trim() === 'Probability observed') : [];
  const clock = labels.length === 1 ? labels[0].nextElementSibling : null;
  const times = clock ? [...clock.querySelectorAll('time')] : [];
  const current = times.length === 1 ? times[0] : null;
  if (current !== timeNode) { timeNode = current; timeGeneration++; }
  const iso = current?.getAttribute('datetime') ?? null;
  const displayedText = current?.textContent?.trim() ?? null;
  const timestamp = iso === null ? null : Date.parse(iso);
  let visible = !!current?.isConnected && !!current.getClientRects().length;
  if (visible) for (let n = current; n; n = n.parentElement) {
   const style = getComputedStyle(n);
   if (n.hidden || n.getAttribute('aria-hidden') === 'true' || style.display === 'none' || style.visibility !== 'visible' || Number(style.opacity) === 0) { visible = false; break; }
  }
  const rect = current?.getBoundingClientRect();
  const inViewport = !!rect && rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.right > 0 && rect.top < innerHeight && rect.left < innerWidth;
  const status = roots.length > 1 || labels.length > 1 || times.length > 1 ? 'ambiguous' : !root ? 'missing-root' : !clock ? 'missing-clock' : !current || !iso || !displayedText ? 'blank' : !Number.isFinite(timestamp) ? 'invalid-timestamp' : 'timestamp';
  return {iso, displayedText, ancestorGeneration, timestamp: Number.isFinite(timestamp) ? timestamp : null, status, visible, inViewport, documentVisibility: document.visibilityState, rootGeneration, timeGeneration};
 }
 function capture(reason, force = false) {
  if (stopped) return;
  try {
   const value = state(), key = JSON.stringify(value);
   if (!force && key === previousKey) return;
   const backwards = value.timestamp !== null && previousTimestamp !== null && value.timestamp < previousTimestamp;
   if (value.timestamp !== null) previousTimestamp = value.timestamp;
   previousKey = key;
   append({reason, mono: performance.now(), wall: Date.now(), ...value, backwards});
  } catch (error) { fault('primary-capture-error:' + String(error)); }
 }
 const local = new MutationObserver(() => capture('readout-mutation'));
 const ancestry = new MutationObserver(() => capture('ancestor-visibility'));
 function bind(reason) {
  const next = document.querySelector(selector);
  if (next !== root) {
   local.disconnect(); root = next; rootGeneration++; timeNode = null;
   if (root) local.observe(root, {subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['datetime', 'hidden', 'style', 'class', 'aria-hidden']});
  }
  const lineage = [];
  for (let n = root?.parentElement; n; n = n.parentElement) lineage.push(n);
  if (lineage.length !== ancestors.length || lineage.some((n,i) => n !== ancestors[i])) {
   ancestry.disconnect(); ancestors.splice(0, ancestors.length, ...lineage); ancestorGeneration++;
   for (const n of ancestors) ancestry.observe(n, {attributes: true, attributeFilter: ['hidden', 'style', 'class', 'aria-hidden']});
  }
  capture(reason);
 }
 // Discovery watches only DOM structure. Chart style/path animation is not observed.
 const discovery = new MutationObserver(records => {
  const relevant = records.some(r => [...r.addedNodes, ...r.removedNodes].some(n => n.nodeType === 1 && (n === root || n.contains(root) || n.matches(selector) || n.querySelector(selector))));
  if (relevant || (root && !root.isConnected)) bind('readout-remount');
 });
 const visibility = () => capture('document-visibility');
 const geometry = () => capture('viewport-change');
 const pagehide = () => { fault('page-hidden-before-export'); capture('pagehide', true); };
 document.addEventListener('visibilitychange', visibility);
 window.addEventListener('resize', geometry, {passive: true});
 window.addEventListener('scroll', geometry, {passive: true, capture: true});
 window.addEventListener('pagehide', pagehide);
 bind('initial');
 discovery.observe(document.documentElement, {childList: true, subtree: true});
 window[slot] = {
  captureId,
  finish() {
   if (stopped) throw new Error('primary export already finalized');
   bind('before-final'); capture('final', true); stopped = true;
   local.disconnect(); ancestry.disconnect(); discovery.disconnect();
   document.removeEventListener('visibilitychange', visibility);
   window.removeEventListener('resize', geometry); window.removeEventListener('scroll', geometry, true); window.removeEventListener('pagehide', pagehide);
   return {schema: 'visible-observation-transitions/1', captureId, installed, exported: {mono: performance.now(), wall: Date.now()}, captureComplete: faults.length === 0 && dropped === 0, faults, dropped, attemptedEntries: seq, retainedBytes: bytes, limits: {maxEntries, maxBytes}, entries, semantics: 'DOM readout observed in MutationObserver callbacks; no physical-paint claim; same-task mutations can coalesce; diagnostic ACKs are independent'};
  }
 };
 return {captureId, installed};
}

module.exports = {installVisibleObservationRecorder};
