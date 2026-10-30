'use strict';
// #10090 / #11674: code that runs INSIDE the held product page.
// Each function is serialized into the page; none may close over Node state.

// Installed before navigation. Subclasses the native EventSource with the
// product's own constructor arguments unchanged and attaches passive listeners
// only: no second subscription, no URL rewrite, no handler that swallows a
// frame. Raw `data` is forwarded before anything parses it.
function installPassiveEventSourceHook(cfg) {
  const send = window[cfg.binding];
  const Native = window.EventSource;
  if (typeof send !== 'function' || typeof Native !== 'function') return;
  // `acks` holds [page_seq, performance.now()] for each binding call that has
  // resolved since the last send; they ride the next record (or the stop
  // return), never a record of their own. The collector stamps its receipt
  // between this record's send_mono and its ack, so each callback is one
  // ordering exchange. A full ack buffer is counted, never silently trimmed.
  const q = {outstanding: 0, high_water: 0, dropped: 0, emit_failures: 0, page_seq: 0, acks: [], acks_dropped: 0,
    time_origin: performance.timeOrigin};
  window.__passiveRecorderQueue = q;
  function emit(rec) {
    rec.page_seq = ++q.page_seq;
    if (q.outstanding >= cfg.maxQueue) { q.dropped++; return; }
    q.outstanding++;
    if (q.outstanding > q.high_water) q.high_water = q.outstanding;
    rec.queue_dropped = q.dropped;
    rec.time_origin = q.time_origin;
    if (q.acks.length) rec.acks = q.acks.splice(0);
    if (q.acks_dropped) rec.acks_dropped = q.acks_dropped;
    const seq = rec.page_seq;
    rec.send_mono = performance.now();
    try {
      Promise.resolve(send(rec)).then(() => {
        const at = performance.now();
        q.outstanding--;
        if (q.acks.length < cfg.maxAcks) q.acks.push([seq, at]); else q.acks_dropped++;
      }, () => { q.outstanding--; q.emit_failures++; });
    } catch { q.outstanding--; q.emit_failures++; }
  }
  window.__passiveRecorderEmit = emit;
  let instances = 0;
  const live = new Set();
  class PassiveEventSource extends Native {
    constructor(...args) {
      super(...args);
      const instance = ++instances;
      // URLs of the other EventSources still open at construction; the recorder
      // decides which one is the case stream (the page may hold others).
      const concurrentUrls = [...live].filter(es => es.readyState !== Native.CLOSED).map(es => es.url);
      live.add(this);
      Object.defineProperty(this, '__passiveInstance', {value: instance});
      emit({kind: 'es-construct', instance, url: this.url, arg_count: args.length,
        with_credentials: this.withCredentials, concurrent_urls: concurrentUrls, mono: performance.now(), wall: Date.now()});
      for (const type of cfg.streamEvents) {
        this.addEventListener(type, e => {
          const rec = {kind: 'es-event', instance, type, mono: performance.now(), wall: Date.now(), url: this.url,
            ready_state: this.readyState, last_event_id: typeof e.lastEventId === 'string' ? e.lastEventId : null};
          if (typeof e.data === 'string') {
            if (e.data.length > cfg.maxDataChars) { rec.data_oversize_chars = e.data.length; rec.data_prefix = e.data.slice(0, 256); }
            else rec.data = e.data;
          }
          emit(rec);
        });
      }
    }
    close() {
      emit({kind: 'es-close', instance: this.__passiveInstance, mono: performance.now(), ready_state_before: this.readyState});
      live.delete(this);
      return super.close();
    }
  }
  window.EventSource = PassiveEventSource;
  window.addEventListener('pagehide', () => emit({kind: 'page-lifecycle', type: 'pagehide', mono: performance.now(), wall: Date.now()}));
  document.addEventListener('visibilitychange', () => emit({kind: 'page-lifecycle', type: 'visibility', state: document.visibilityState, mono: performance.now(), wall: Date.now()}));
}

// 100 ms sampler. `readDisplayIdentity10090` is the pinned display_sample.cjs,
// installed unchanged on window before this runs. Full chart geometry rides
// every sample; a path's `d` is sent whole whenever it changes and by hash
// otherwise. Nothing here joins or infers identity.
function startDisplaySampler(cfg) {
  if (window.__passiveSampler) throw new Error('sampler already running');
  const emit = window.__passiveRecorderEmit, read = window.__readDisplayIdentity10090;
  if (typeof emit !== 'function' || typeof read !== 'function') throw new Error('sampler prerequisites missing');
  const hash = s => { let h1 = 0x811c9dc5, h2 = 0x01000193; for (let i = 0; i < s.length; i++) { const c = s.charCodeAt(i); h1 = Math.imul(h1 ^ c, 16777619) >>> 0; h2 = Math.imul(h2 ^ c, 2246822519) >>> 0; } return h1.toString(16).padStart(8, '0') + h2.toString(16).padStart(8, '0'); };
  const lastD = new Map();
  let prev = performance.now(), n = 0;
  const rect = el => { if (!el) return null; const r = el.getBoundingClientRect(); return [r.x, r.y, r.width, r.height].map(v => Math.round(v * 100) / 100); };
  function sample() {
    const started = performance.now();
    try {
      const hero = document.querySelector('[data-testid="event-hero-probability"]');
      const card = document.querySelector('[data-testid="win-probability-card"]');
      const label = [...document.querySelectorAll('dt')].filter(x => x.textContent.trim() === 'Probability observed');
      const clock = label.length === 1 ? label[0].nextElementSibling : null;
      const svg = card ? card.querySelector('svg.recharts-surface') || card.querySelector('svg') : null;
      const paths = [...(card ? card.querySelectorAll('.recharts-line path') : [])].map((p, i) => {
        const d = p.getAttribute('d') || '';
        const h = hash(d);
        const out = {i, stroke: p.getAttribute('stroke'), d_hash: h, d_len: d.length};
        if (lastD.get(i) !== h) { out.d = d; lastD.set(i, h); }
        try { const b = p.getBBox(); out.bbox = [b.x, b.y, b.width, b.height].map(v => Math.round(v * 100) / 100); } catch { out.bbox = null; }
        return out;
      });
      const endpoints = [...(card ? card.querySelectorAll('[data-callout-at],[data-chart-endpoint-state]') : [])].map(el => {
        const attrs = {};
        for (const a of el.attributes) if (a.name.startsWith('data-')) attrs[a.name] = a.value;
        return {tag: el.tagName.toLowerCase(), attrs, rect: rect(el)};
      });
      // read_bracket: document time immediately around the pinned read(); `mono`
      // (taken before the DOM queries above) stays the sample's start.
      const r0 = performance.now();
      const displayIdentity = read();
      const r1 = performance.now();
      emit({kind: 'sample', n: ++n, mono: started, wall: Date.now(), gap_ms: started - prev,
        read_bracket: [r0, r1], display_identity: displayIdentity,
        hero: hero ? {probability: hero.getAttribute('data-probability'), text: hero.innerText, rect: rect(hero)} : null,
        observed: clock ? {iso: clock.querySelector('time')?.getAttribute('datetime') ?? null, text: clock.innerText, visible: !!clock.getClientRects().length} : null,
        observed_labels: label.length,
        chart: card ? {rect: rect(card), svg: svg ? {rect: rect(svg), view_box: svg.getAttribute('viewBox'), width: svg.getAttribute('width'), height: svg.getAttribute('height')} : null,
          ticks: [...card.querySelectorAll('.recharts-yAxis .recharts-cartesian-axis-tick-value')].map(t => ({text: t.textContent, y: t.getAttribute('y')})),
          x_ticks: [...card.querySelectorAll('.recharts-xAxis .recharts-cartesian-axis-tick-value')].map(t => ({text: t.textContent, x: t.getAttribute('x')})),
          paths, endpoints} : null,
        viewport: {w: innerWidth, h: innerHeight, scroll_y: scrollY}, visibility: document.visibilityState,
        read_ms: performance.now() - started});
    } catch (error) {
      emit({kind: 'sample-error', mono: started, error: String(error)});
    }
    prev = started;
  }
  window.__passiveSampler = setInterval(sample, cfg.intervalMs);
  sample();
  return {started: performance.now(), timeOrigin: performance.timeOrigin};
}

function stopDisplaySampler() {
  if (window.__passiveSampler) clearInterval(window.__passiveSampler);
  window.__passiveSampler = null;
  const q = window.__passiveRecorderQueue || null;
  return {stopped: performance.now(), queue: q && {...q, acks: q.acks.splice(0)}};
}

// One bounded sweep after the stop: acks that resolved after the stop return.
function drainRecorderAcks() {
  const q = window.__passiveRecorderQueue || null;
  return q ? {at: performance.now(), time_origin: performance.timeOrigin, acks: q.acks.splice(0), acks_dropped: q.acks_dropped,
    outstanding: q.outstanding, page_seq: q.page_seq} : null;
}

module.exports = {installPassiveEventSourceHook, startDisplaySampler, stopDisplaySampler, drainRecorderAcks};
