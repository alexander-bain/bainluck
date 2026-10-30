'use strict';
// #10090: a scripted, in-process stand-in for the Playwright surface the
// passive recorder uses, for the browser-free LIFECYCLE control only
// (lifecycle_control.cjs). The page's own code (page_hooks.cjs, the pinned
// sampler) runs unchanged in a vm "document" whose clock is the collector's
// performance.now() minus a fixed offset the recorder does not know. Every
// binding call is serialized at call time, delivered after d1 ms and resolved
// d2 ms after the collector handled it, as CDP orders them. Nothing here is a
// browser; a run proves lifecycle and record semantics, never paint or timing.
const vm = require('vm');
const {performance} = require('perf_hooks');

const S = JSON.parse(process.env.LIFECYCLE_FAKE_SCENARIO || '{}');
const OFF = S.doc_offset_ms;
const rand = (a, b) => a + Math.random() * (b - a);
const delay = spec => (Array.isArray(spec) ? rand(spec[0], spec[1]) : spec || 0);
const nowSinceT0 = () => Date.now() - S.t0_wall_ms; // scenario schedule only; never fed to the recorder
// Every timer the scripted page starts, so browser.close() ends them as a real browser would.
const live = new Set();
const track = (set, clear) => (fn, ms) => { const h = set(() => { if (set === setTimeout) live.delete(h); fn(); }, ms); h.__clear = clear; live.add(h); return h; };
const pSetTimeout = track(setTimeout, clearTimeout), pSetInterval = track(setInterval, clearInterval);
const pClear = h => { if (h) { live.delete(h); (h.__clear || clearTimeout)(h); } };
function closeAll() { for (const h of live) (h.__clear || clearTimeout)(h); live.clear(); }
// Binding calls are delivered to the collector in call order (CDP is ordered): a
// later call is never handled before an earlier one, whatever its delay.
let lastDelivery = 0;

function makeDocument(page, timeOrigin, off) {
  const doc = {timeOrigin, listeners: []};
  class FakeES {
    constructor(url) { this.url = url; this.withCredentials = false; this.readyState = 0; this.l = {}; }
    addEventListener(t, f) { (this.l[t] = this.l[t] || []).push(f); }
    close() { this.readyState = 2; }
  }
  FakeES.CLOSED = 2;
  const window = {EventSource: FakeES, addEventListener() {}};
  let seq = 0;
  window.__passiveRecordProxy = rec => {
    const clone = JSON.parse(JSON.stringify(rec));
    const mySeq = ++seq;
    return new Promise(resolve => {
      const at = Math.max(lastDelivery, performance.now() + delay(S.d1_ms));
      lastDelivery = at;
      pSetTimeout(() => {
        try { page.bindings.get('__passiveRecord')(clone); } catch { /* the collector's problem */ }
        const tail = S.never_resolve_after_ms !== undefined && nowSinceT0() >= S.never_resolve_after_ms;
        if (!tail) pSetTimeout(resolve, delay(S.d2_ms));
      }, at - performance.now());
      void mySeq;
    });
  };
  const document = {addEventListener() {}, visibilityState: 'visible', querySelector: () => null, querySelectorAll: () => []};
  const perf = {now: () => performance.now() - off, timeOrigin};
  const ctx = vm.createContext({window, document, performance: perf, Date, Promise, Math, Map, Set, String, Object, Error, JSON, Array,
    setInterval: pSetInterval, clearInterval: pClear, setTimeout: pSetTimeout, clearTimeout: pClear, innerWidth: 390, innerHeight: 844, scrollY: 0, getComputedStyle: () => ({})});
  doc.ctx = ctx;
  doc.window = window;
  return doc;
}

function identityAt(sinceT0) {
  const X = S.input_since_t0_ms;
  const head = sinceT0 >= X + S.headline_after_ms ? 'new' : 'old', chart = sinceT0 >= X + S.chart_after_ms ? 'new' : 'old';
  const s = (v, k) => ({status: 'present', count: 1, visible: true, inViewport: true, attributes: {[k]: v}});
  return {schema: 'display-identity-sample/1', documentVisibility: 'visible', headline: s(head, 'data-display-state'), chart: s(chart, 'data-chart-endpoint-state')};
}

function makePage(context) {
  const handlers = {};
  const page = {bindings: new Map(), init: [], doc: null, closed: false};
  const fire = (evt, ...a) => (handlers[evt] || []).forEach(f => f(...a));
  const frame = {url: () => S.page_url};
  const runInDoc = (src, arg) => vm.runInContext(`(${src})(${arg === undefined ? '' : JSON.stringify(arg)})`, page.doc.ctx);
  // Each document has its own clock: the first keeps the scenario offset, a
  // replacement restarts near zero with a new time origin, as a browser does.
  // The offsets go to a sidecar for the control's ground truth only.
  const offsets = {};
  function navigate(off) {
    const timeOrigin = Date.now() - (performance.now() - off);
    offsets[String(timeOrigin)] = off;
    if (S.offsets_file) require('fs').writeFileSync(S.offsets_file, JSON.stringify(offsets));
    page.doc = makeDocument(page, timeOrigin, off);
    page.doc.window[page.bindingName] = page.doc.window.__passiveRecordProxy;
    for (const [fn, arg] of page.init) runInDoc(fn.toString(), arg);
    fire('framenavigated', frame);
    // The product opens its event stream and the scripted server speaks.
    const es = vm.runInContext(`new window.EventSource(${JSON.stringify(S.stream_url)})`, page.doc.ctx);
    const send = (type, data) => (es.l[type] || []).forEach(f => f({data, lastEventId: ''}));
    const session = `s-${timeOrigin}`;
    pSetTimeout(() => {
      send('open', '');
      send('preview_open_v3', JSON.stringify({protocol: 3, authority: S.authority, members: S.members, stream_session: session, event_id: S.event_id}));
    }, 5);
    pSetInterval(() => { send('preview_v3', JSON.stringify({protocol: 3, authority: S.authority, stream_session: session, event_id: S.event_id})); }, 1000);
  }
  Object.assign(page, {
    on(evt, f) { (handlers[evt] = handlers[evt] || []).push(f); },
    mainFrame: () => frame,
    async exposeFunction(name, fn) { page.bindingName = name; page.bindings.set(name, fn); },
    async addInitScript(fn, arg) { page.init.push([fn, arg]); },
    async goto() {
      navigate(OFF);
      if (S.replace_document_at_ms !== undefined) {
        const wait = S.t0_wall_ms + S.replace_document_at_ms - Date.now();
        pSetTimeout(() => {
          // A new document: new time origin, same binding; the old document's sampler stops.
          const old = page.doc;
          vm.runInContext('clearInterval(window.__passiveSampler)', old.ctx);
          navigate(performance.now() - 0.5);
          page.doc.window.__readDisplayIdentity10090 = () => identityAt(nowSinceT0());
          vm.runInContext(`(${require('../page_hooks.cjs').startDisplaySampler})({intervalMs: 100})`, page.doc.ctx);
        }, Math.max(0, wait));
      }
    },
    locator: () => ({first: () => ({waitFor: async () => {}, click: async () => {}})}),
    async evaluate(fn, arg) {
      if (typeof fn === 'string') {
        vm.runInContext(fn, page.doc.ctx);
        // The pinned sampler is installed unchanged; the scripted DOM answers through it.
        page.doc.window.__readDisplayIdentity10090 = () => {
          const id = identityAt(nowSinceT0());
          if (S.stall && !page.stalled && nowSinceT0() >= S.stall.at_ms) { page.stalled = true; const end = Date.now() + S.stall.ms; while (Date.now() < end) { /* the collector loop is blocked */ } }
          return id;
        };
        return undefined;
      }
      if (fn.name === 'installVisibleObservationRecorder') {
        vm.runInContext(`window.__visibleObservationRecorder11434 = ${JSON.stringify({captureId: arg.captureId})}; window.__visibleObservationRecorder11434.finish = () => ({captureComplete: true, entries: [], faults: [], dropped: 0});`, page.doc.ctx);
        return undefined;
      }
      return JSON.parse(JSON.stringify(runInDoc(fn.toString(), arg) ?? null));
    },
  });
  return page;
}

module.exports = {chromium: {launch: async () => {
  const browser = {version: () => S.browser_version, close: async () => { closeAll(); }, async newContext() {
    return {async route() {}, async newPage() { return makePage(this); }, async newCDPSession() { return {on() {}, async send() {}}; }};
  }};
  return browser;
}}};
