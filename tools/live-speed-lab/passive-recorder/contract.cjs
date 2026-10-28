'use strict';
// #10090 / #11674: offline validation of the case manifest and the owner grant.
// Pure: reads only the named files, opens no socket. Every number is supplied by
// the manifest or grant; nothing here has a default. A refusal lists every
// failed clause so one read names them all.
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const MANIFEST_SCHEMA = 'bainluck.passive-case-manifest/1';
const GRANT_SCHEMA = 'bainluck.passive-case-grant/1';
// The case's finite edges are fixed by the predeclared #10090 case, not tunable.
const SCORING = {start_offset_ms: 0, end_offset_ms: 180000};
const ACQUISITION = {start_offset_ms: -5000, end_offset_ms: 185000};
const EARLIEST_SETUP_OFFSET_MS = -600000;
const STREAM_PROTOCOL = 'authority-v3';
const READOUT_ACTIVATIONS = ['click-live-connection-status', 'none'];
const KNOWN_STREAM_EVENTS = ['open', 'error', 'probability', 'folded_probability', 'preview', 'preview_open_v3',
  'preview_v3', 'reconcile', 'resync', 'fold_preview_floor', 'reconnect', 'heartbeat', 'closed'];
const LIMIT_FIELDS = ['max_request_attempts', 'max_eventsource_constructions', 'max_stream_attempts',
  'max_active_streams', 'max_response_bytes', 'max_stream_bytes', 'max_request_bytes', 'max_record_bytes',
  'max_saved_bytes', 'reserved_stop_bytes', 'max_queue_records', 'max_detail_requests',
  'received_overshoot_bytes'];
// The transport proxy reads at most one socket chunk before it can refuse it.
// libuv reads into 64 KiB buffers, so that is the received-side overshoot bound
// a grant must authorize. Forwarded overshoot is zero.
const RECEIVED_OVERSHOOT_BOUND_BYTES = 65536;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const LOOPBACK = new Set(['127.0.0.1', 'localhost', '[::1]', '::1']);

function sha256(buf) { return crypto.createHash('sha256').update(buf).digest('hex'); }
function sha256File(file) { return sha256(fs.readFileSync(file)); }

// JSON.parse keeps the last of two equal keys silently. A contract file or a
// stream frame with a duplicated key is ambiguous, so it is refused instead.
function parseStrictJson(text) {
  let i = 0;
  const duplicates = [];
  const fail = msg => { throw new SyntaxError(`${msg} at ${i}`); };
  const ws = () => { while (i < text.length && ' \t\n\r'.includes(text[i])) i++; };
  function str() {
    const start = i;
    i++;
    while (i < text.length && text[i] !== '"') i += text[i] === '\\' ? 2 : 1;
    if (text[i] !== '"') fail('unterminated string');
    i++;
    return JSON.parse(text.slice(start, i));
  }
  function value(where) {
    ws();
    const c = text[i];
    if (c === '{') {
      i++;
      const out = {};
      const seen = new Set();
      ws();
      if (text[i] === '}') { i++; return out; }
      for (;;) {
        ws();
        if (text[i] !== '"') fail('expected key');
        const key = str();
        if (seen.has(key)) duplicates.push(`${where}.${key}`);
        seen.add(key);
        ws();
        if (text[i] !== ':') fail('expected colon');
        i++;
        out[key] = value(`${where}.${key}`);
        ws();
        if (text[i] === ',') { i++; continue; }
        if (text[i] === '}') { i++; return out; }
        fail('expected , or }');
      }
    }
    if (c === '[') {
      i++;
      const out = [];
      ws();
      if (text[i] === ']') { i++; return out; }
      for (;;) {
        out.push(value(`${where}[${out.length}]`));
        ws();
        if (text[i] === ',') { i++; continue; }
        if (text[i] === ']') { i++; return out; }
        fail('expected , or ]');
      }
    }
    if (c === '"') return str();
    const m = /^(?:-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null)/.exec(text.slice(i));
    if (!m) fail('unexpected token');
    i += m[0].length;
    return JSON.parse(m[0]);
  }
  const out = value('$');
  ws();
  if (i !== text.length) fail('trailing data');
  return {value: out, duplicates};
}

const isObj = v => v !== null && typeof v === 'object' && !Array.isArray(v);
const posInt = v => Number.isSafeInteger(v) && v > 0;
const nonEmpty = v => typeof v === 'string' && v.length > 0;
const isoMs = v => (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,3})?Z$/.test(v)) ? Date.parse(v) : NaN;

function exactKeys(obj, keys, where, refuse) {
  if (!isObj(obj)) { refuse(`${where}: object required`); return false; }
  const have = Object.keys(obj).sort(), want = [...keys].sort();
  const missing = want.filter(k => !have.includes(k)), extra = have.filter(k => !want.includes(k));
  if (missing.length) refuse(`${where}: missing ${missing.join(',')}`);
  if (extra.length) refuse(`${where}: unknown ${extra.join(',')}`);
  return !missing.length;
}

function pinnedFile(ref, where, refuse, baseDir) {
  if (!exactKeys(ref, ['path', 'sha256'], where, refuse)) return null;
  if (!nonEmpty(ref.path) || !path.isAbsolute(ref.path)) { refuse(`${where}.path: absolute path required`); return null; }
  if (!SHA256.test(ref.sha256 || '')) { refuse(`${where}.sha256: lowercase sha256 required`); return null; }
  let actual;
  try { actual = sha256File(ref.path); } catch (e) { refuse(`${where}: unreadable (${e.code || e.message})`); return null; }
  if (actual !== ref.sha256) { refuse(`${where}: sha256 drift (have ${actual})`); return null; }
  return actual;
}

function originOf(url, where, refuse) {
  try {
    const u = new URL(url);
    if (!['http:', 'https:'].includes(u.protocol)) { refuse(`${where}: http(s) required`); return null; }
    if (u.username || u.password || u.hash) { refuse(`${where}: credentials/fragment not allowed`); return null; }
    return u;
  } catch { refuse(`${where}: not a URL`); return null; }
}

function loadPinned(file, expectedSha, label, refuse) {
  if (!nonEmpty(file)) { refuse(`${label}: path required`); return null; }
  if (!SHA256.test(expectedSha || '')) { refuse(`${label}: --${label}-sha256 must be a lowercase sha256`); return null; }
  let bytes;
  try { bytes = fs.readFileSync(file); } catch (e) { refuse(`${label}: unreadable (${e.code || e.message})`); return null; }
  const actual = sha256(bytes);
  if (actual !== expectedSha) { refuse(`${label}: sha256 drift (have ${actual}, pinned ${expectedSha})`); return null; }
  try {
    const {value, duplicates} = parseStrictJson(bytes.toString('utf8'));
    if (duplicates.length) { refuse(`${label}: duplicate keys ${duplicates.join(',')}`); return null; }
    return {value, sha256: actual, bytes: bytes.length};
  } catch (e) { refuse(`${label}: invalid JSON (${e.message})`); return null; }
}

function validateManifest(m, refuse) {
  if (!exactKeys(m, ['schema', 'case_id', 'policy', 'selection', 'event', 'owner_receipts', 'entry', 'trace',
    'clock', 'page', 'cleanup'], 'manifest', refuse)) return;
  if (m.schema !== MANIFEST_SCHEMA) refuse(`manifest.schema: ${MANIFEST_SCHEMA} required`);
  if (!nonEmpty(m.case_id)) refuse('manifest.case_id: required');
  pinnedFile(m.policy, 'manifest.policy', refuse);

  const s = m.selection;
  if (exactKeys(s, ['selected_at', 'max_age_s', 'selected_by', 'inventory'], 'manifest.selection', refuse)) {
    if (!Number.isFinite(isoMs(s.selected_at))) refuse('manifest.selection.selected_at: UTC ISO-8601 Z required');
    if (!posInt(s.max_age_s)) refuse('manifest.selection.max_age_s: positive integer required');
    if (!nonEmpty(s.selected_by)) refuse('manifest.selection.selected_by: required');
    const inv = s.inventory;
    if (exactKeys(inv, ['evidence', 'order', 'rejections', 'replacement_rule'], 'manifest.selection.inventory', refuse)) {
      pinnedFile(inv.evidence, 'manifest.selection.inventory.evidence', refuse);
      if (!Array.isArray(inv.order) || !inv.order.length) refuse('manifest.selection.inventory.order: non-empty list required');
      if (!Array.isArray(inv.rejections)) refuse('manifest.selection.inventory.rejections: list required');
      if (!nonEmpty(inv.replacement_rule)) refuse('manifest.selection.inventory.replacement_rule: required (the recorder never replaces)');
    }
  }

  const e = m.event;
  if (exactKeys(e, ['canonical_event_id', 'members', 'contributing_sources'], 'manifest.event', refuse)) {
    if (!posInt(e.canonical_event_id)) refuse('manifest.event.canonical_event_id: positive integer required');
    const mem = e.members;
    if (!Array.isArray(mem) || !mem.length || mem.length > 32 || !mem.every(posInt) || mem.some((v, i) => i && v <= mem[i - 1])) {
      refuse('manifest.event.members: 1..32 strictly increasing positive integers required');
    } else if (!mem.includes(e.canonical_event_id)) refuse('manifest.event.members: must include canonical_event_id');
    if (!Array.isArray(e.contributing_sources) || !e.contributing_sources.length) refuse('manifest.event.contributing_sources: non-empty list required');
    else e.contributing_sources.forEach((c, i) => {
      if (exactKeys(c, ['source', 'contract', 'orientation'], `manifest.event.contributing_sources[${i}]`, refuse)) {
        if (![c.source, c.contract, c.orientation].every(nonEmpty)) refuse(`manifest.event.contributing_sources[${i}]: non-empty strings required`);
      }
    });
  }

  const o = m.owner_receipts;
  if (exactKeys(o, ['backend', 'worker', 'frontend', 'authority', 'preview_activation'], 'manifest.owner_receipts', refuse)) {
    for (const k of ['backend', 'worker', 'frontend']) {
      if (exactKeys(o[k], ['source_sha', 'release_receipt'], `manifest.owner_receipts.${k}`, refuse)) {
        if (!/^[0-9a-f]{40}$/.test(o[k].source_sha || '')) refuse(`manifest.owner_receipts.${k}.source_sha: 40-hex sha required`);
        pinnedFile(o[k].release_receipt, `manifest.owner_receipts.${k}.release_receipt`, refuse);
      }
    }
    if (exactKeys(o.authority, ['incarnation', 'namespace'], 'manifest.owner_receipts.authority', refuse)) {
      if (typeof o.authority.incarnation !== 'string' || !/^[1-9]\d*$/.test(o.authority.incarnation)) refuse('manifest.owner_receipts.authority.incarnation: decimal string required');
      if (!UUID.test(o.authority.namespace || '')) refuse('manifest.owner_receipts.authority.namespace: lowercase uuid required');
    }
    pinnedFile(o.preview_activation, 'manifest.owner_receipts.preview_activation', refuse);
  }

  const en = m.entry;
  if (exactKeys(en, ['page_url', 'api_origin', 'readout_activation', 'expected_stream_url', 'expected_stream_events'], 'manifest.entry', refuse)) {
    const page = originOf(en.page_url, 'manifest.entry.page_url', refuse);
    const api = originOf(en.api_origin, 'manifest.entry.api_origin', refuse);
    if (api && (api.pathname !== '/' || api.search || en.api_origin !== api.origin)) refuse('manifest.entry.api_origin: bare origin required');
    if (page && e && posInt(e.canonical_event_id) && page.pathname !== `/events/${e.canonical_event_id}`) refuse('manifest.entry.page_url: must be the product event route /events/{canonical_event_id}');
    if (page && page.search) refuse('manifest.entry.page_url: no query (the product entry is the plain event route)');
    if (api && e && posInt(e.canonical_event_id)) {
      const want = `${api.origin}/api/events/${e.canonical_event_id}/stream?preview_protocol=${STREAM_PROTOCOL}`;
      if (en.expected_stream_url !== want) refuse(`manifest.entry.expected_stream_url: must equal ${want}`);
    }
    if (!READOUT_ACTIVATIONS.includes(en.readout_activation)) refuse(`manifest.entry.readout_activation: one of ${READOUT_ACTIVATIONS.join('|')}`);
    const ev = en.expected_stream_events;
    if (!Array.isArray(ev) || !ev.length || !ev.every(t => KNOWN_STREAM_EVENTS.includes(t)) || new Set(ev).size !== ev.length) refuse(`manifest.entry.expected_stream_events: unique subset of ${KNOWN_STREAM_EVENTS.join(',')}`);
  }

  if (m.trace !== null && exactKeys(m.trace, ['owner', 'run_id', 'binding'], 'manifest.trace', refuse)) {
    if (!nonEmpty(m.trace.owner) || !nonEmpty(m.trace.run_id)) refuse('manifest.trace: owner and run_id required');
    pinnedFile(m.trace.binding, 'manifest.trace.binding', refuse);
  }

  const c = m.clock;
  if (exactKeys(c, ['t0_utc', 'scoring', 'acquisition', 'setup'], 'manifest.clock', refuse)) {
    if (!Number.isFinite(isoMs(c.t0_utc))) refuse('manifest.clock.t0_utc: UTC ISO-8601 Z required');
    for (const [k, want] of [['scoring', SCORING], ['acquisition', ACQUISITION]]) {
      if (exactKeys(c[k], ['start_offset_ms', 'end_offset_ms'], `manifest.clock.${k}`, refuse)
          && (c[k].start_offset_ms !== want.start_offset_ms || c[k].end_offset_ms !== want.end_offset_ms)) {
        refuse(`manifest.clock.${k}: must be the predeclared ${want.start_offset_ms}..${want.end_offset_ms} ms`);
      }
    }
    if (exactKeys(c.setup, ['earliest_offset_ms', 'cutoff_offset_ms'], 'manifest.clock.setup', refuse)) {
      const {earliest_offset_ms: a, cutoff_offset_ms: b} = c.setup;
      if (!Number.isSafeInteger(a) || !Number.isSafeInteger(b) || a < EARLIEST_SETUP_OFFSET_MS || b > ACQUISITION.start_offset_ms || a >= b) {
        refuse(`manifest.clock.setup: ${EARLIEST_SETUP_OFFSET_MS} <= earliest < cutoff <= ${ACQUISITION.start_offset_ms}`);
      }
    }
  }

  const p = m.page;
  if (exactKeys(p, ['viewport', 'held_pages', 'require_document_visible', 'require_in_viewport'], 'manifest.page', refuse)) {
    if (!exactKeys(p.viewport, ['width', 'height'], 'manifest.page.viewport', refuse) || !posInt(p.viewport.width) || !posInt(p.viewport.height)) refuse('manifest.page.viewport: positive integers required');
    if (p.held_pages !== 1) refuse('manifest.page.held_pages: exactly 1');
    if (p.require_document_visible !== true) refuse('manifest.page.require_document_visible: true required');
    if (typeof p.require_in_viewport !== 'boolean') refuse('manifest.page.require_in_viewport: boolean required');
  }
  if (exactKeys(m.cleanup, ['custody'], 'manifest.cleanup', refuse) && !nonEmpty(m.cleanup.custody)) refuse('manifest.cleanup.custody: required');
}

function validateGrant(g, m, manifestSha, refuse) {
  if (!exactKeys(g, ['schema', 'grant_id', 'issued_by', 'issued_at', 'expires_at', 'case_id', 'manifest_sha256',
    'allowed_origins', 'allowed_routes', 'limits', 'detail_requests'], 'grant', refuse)) return;
  if (g.schema !== GRANT_SCHEMA) refuse(`grant.schema: ${GRANT_SCHEMA} required`);
  if (!nonEmpty(g.grant_id) || !nonEmpty(g.issued_by)) refuse('grant: grant_id and issued_by required');
  if (g.manifest_sha256 !== manifestSha) refuse('grant.manifest_sha256: does not bind this manifest');
  if (isObj(m) && g.case_id !== m.case_id) refuse('grant.case_id: does not match manifest.case_id');
  const issued = isoMs(g.issued_at), expires = isoMs(g.expires_at);
  if (!Number.isFinite(issued) || !Number.isFinite(expires) || expires <= issued) refuse('grant: issued_at < expires_at (UTC ISO-8601 Z) required');
  if (!Array.isArray(g.allowed_origins) || !g.allowed_origins.length) refuse('grant.allowed_origins: non-empty list required');
  else g.allowed_origins.forEach((o, i) => {
    const u = originOf(o, `grant.allowed_origins[${i}]`, refuse);
    if (u && u.origin !== o) refuse(`grant.allowed_origins[${i}]: bare origin required`);
  });
  if (!Array.isArray(g.allowed_routes) || !g.allowed_routes.length) refuse('grant.allowed_routes: non-empty list required');
  else g.allowed_routes.forEach((r, i) => {
    if (!exactKeys(r, ['origin', 'methods', 'path_prefix', 'resource_types'], `grant.allowed_routes[${i}]`, refuse)) return;
    if (!g.allowed_origins.includes(r.origin)) refuse(`grant.allowed_routes[${i}].origin: not in allowed_origins`);
    if (!Array.isArray(r.methods) || !r.methods.length || !r.methods.every(x => ['GET', 'HEAD', 'OPTIONS', 'POST'].includes(x))) refuse(`grant.allowed_routes[${i}].methods: GET/HEAD/OPTIONS/POST list required`);
    if (!nonEmpty(r.path_prefix) || !r.path_prefix.startsWith('/')) refuse(`grant.allowed_routes[${i}].path_prefix: absolute path prefix required`);
    if (!Array.isArray(r.resource_types) || !r.resource_types.length || !r.resource_types.every(nonEmpty)) refuse(`grant.allowed_routes[${i}].resource_types: non-empty list required`);
  });
  const L = g.limits;
  if (exactKeys(L, LIMIT_FIELDS, 'grant.limits', refuse)) {
    for (const k of LIMIT_FIELDS) {
      if (k === 'max_detail_requests' ? !(Number.isSafeInteger(L[k]) && L[k] >= 0 && L[k] <= 2) : !posInt(L[k])) {
        refuse(`grant.limits.${k}: ${k === 'max_detail_requests' ? 'integer 0..2' : 'finite positive integer'} required`);
      }
    }
    if (posInt(L.reserved_stop_bytes) && posInt(L.max_saved_bytes) && L.reserved_stop_bytes >= L.max_saved_bytes) refuse('grant.limits.reserved_stop_bytes: must be below max_saved_bytes');
    if (posInt(L.max_record_bytes) && posInt(L.reserved_stop_bytes) && L.max_record_bytes > L.max_saved_bytes - L.reserved_stop_bytes) refuse('grant.limits.max_record_bytes: must fit below the STOP reserve');
    if (posInt(L.max_stream_bytes) && posInt(L.max_response_bytes) && L.max_stream_bytes > L.max_response_bytes) refuse('grant.limits.max_stream_bytes: must not exceed max_response_bytes');
    if (posInt(L.max_active_streams) && L.max_active_streams !== 1) refuse('grant.limits.max_active_streams: exactly 1 (one held case-stream subscription)');
    if (posInt(L.received_overshoot_bytes) && L.received_overshoot_bytes < RECEIVED_OVERSHOOT_BOUND_BYTES) refuse(`grant.limits.received_overshoot_bytes: must authorize the transport's ${RECEIVED_OVERSHOOT_BOUND_BYTES}-byte received-chunk bound`);
  }
  if (!Array.isArray(g.detail_requests)) refuse('grant.detail_requests: list required');
  else {
    if (isObj(L) && g.detail_requests.length !== L.max_detail_requests) refuse('grant.detail_requests: count must equal limits.max_detail_requests');
    g.detail_requests.forEach((d, i) => {
      if (!exactKeys(d, ['method', 'url', 'at_offset_ms'], `grant.detail_requests[${i}]`, refuse)) return;
      if (d.method !== 'GET') refuse(`grant.detail_requests[${i}].method: GET only`);
      const u = originOf(d.url, `grant.detail_requests[${i}].url`, refuse);
      if (u && Array.isArray(g.allowed_origins) && !g.allowed_origins.includes(u.origin)) refuse(`grant.detail_requests[${i}].url: origin not granted`);
      if (!Number.isSafeInteger(d.at_offset_ms) || d.at_offset_ms < ACQUISITION.start_offset_ms || d.at_offset_ms > ACQUISITION.end_offset_ms) refuse(`grant.detail_requests[${i}].at_offset_ms: inside the acquisition window`);
    });
  }
  // The manifest's own entry must be reachable under the grant, or the case cannot run.
  if (isObj(m) && isObj(m.entry) && Array.isArray(g.allowed_origins)) {
    for (const [k, url] of [['page_url', m.entry.page_url], ['expected_stream_url', m.entry.expected_stream_url]]) {
      try { if (!g.allowed_origins.includes(new URL(url).origin)) refuse(`grant.allowed_origins: does not cover manifest.entry.${k}`); } catch { /* reported by manifest */ }
    }
  }
}

function isLoopbackUrl(url) {
  try { return LOOPBACK.has(new URL(url).hostname); } catch { return false; }
}

/**
 * Validate a manifest+grant pair. `scope` is 'local' or 'production', with no
 * default. `now` is the collector wall clock in ms. Returns {ok, refusals, ...}.
 */
function validateBundle({manifest, manifestSha256, grant, grantSha256, scope, now}) {
  const refusals = [];
  const refuse = msg => refusals.push(msg);
  if (!['local', 'production'].includes(scope)) refuse('--scope: local or production required (no default)');
  if (!Number.isFinite(now)) refuse('collector wall clock unavailable');
  const M = loadPinned(manifest, manifestSha256, 'manifest', refuse);
  const G = loadPinned(grant, grantSha256, 'grant', refuse);
  if (M) validateManifest(M.value, refuse);
  if (G) validateGrant(G.value, M && M.value, M && M.sha256, refuse);
  let window = null;
  if (M && isObj(M.value.clock) && Number.isFinite(isoMs(M.value.clock.t0_utc)) && isObj(M.value.clock.setup)) {
    const t0 = isoMs(M.value.clock.t0_utc), su = M.value.clock.setup;
    window = {t0_wall_ms: t0, setup_earliest_wall_ms: t0 + su.earliest_offset_ms, setup_cutoff_wall_ms: t0 + su.cutoff_offset_ms,
      acquisition_start_wall_ms: t0 + ACQUISITION.start_offset_ms, acquisition_end_wall_ms: t0 + ACQUISITION.end_offset_ms,
      scoring_start_wall_ms: t0 + SCORING.start_offset_ms, scoring_end_wall_ms: t0 + SCORING.end_offset_ms};
    if (Number.isFinite(now)) {
      // No rolling start: a late recorder refuses rather than recording a shifted case.
      if (now > window.setup_cutoff_wall_ms) refuse('late start: collector wall is past the setup cutoff; no rolling start and no later case');
      if (now < window.setup_earliest_wall_ms + EARLIEST_SETUP_OFFSET_MS) refuse('early start: more than 10 minutes before setup earliest');
      const sel = M.value.selection;
      if (isObj(sel) && Number.isFinite(isoMs(sel.selected_at)) && posInt(sel.max_age_s)) {
        if (isoMs(sel.selected_at) > now) refuse('manifest.selection.selected_at: in the future');
        if (isoMs(sel.selected_at) + sel.max_age_s * 1000 < window.acquisition_end_wall_ms) refuse('manifest.selection: selection is not current through the acquisition end');
      }
    }
    if (G && isObj(G.value) && Number.isFinite(isoMs(G.value.expires_at))) {
      if (isoMs(G.value.expires_at) < window.acquisition_end_wall_ms) refuse('grant.expires_at: expires before the acquisition end');
      if (Number.isFinite(now) && isoMs(G.value.issued_at) > now) refuse('grant.issued_at: in the future');
    }
  }
  if (scope === 'local' && M && G) {
    // Local scope never touches a production host, even if a fixture names one.
    const urls = [];
    if (isObj(M.value.entry)) urls.push(M.value.entry.page_url, M.value.entry.api_origin, M.value.entry.expected_stream_url);
    if (Array.isArray(G.value.allowed_origins)) urls.push(...G.value.allowed_origins);
    if (Array.isArray(G.value.detail_requests)) urls.push(...G.value.detail_requests.map(d => d && d.url));
    for (const u of urls) if (typeof u === 'string' && !isLoopbackUrl(u)) refuse(`local scope: non-loopback origin refused (${(() => { try { return new URL(u).host; } catch { return u; } })()})`);
  }
  return {ok: refusals.length === 0, refusals, manifest: M && M.value, grant: G && G.value,
    manifestSha256: M && M.sha256, grantSha256: G && G.sha256, window, scope};
}

module.exports = {
  MANIFEST_SCHEMA, GRANT_SCHEMA, SCORING, ACQUISITION, STREAM_PROTOCOL, KNOWN_STREAM_EVENTS, LIMIT_FIELDS,
  RECEIVED_OVERSHOOT_BOUND_BYTES, LOOPBACK, sha256, sha256File, parseStrictJson, validateBundle, isLoopbackUrl, isoMs,
};
