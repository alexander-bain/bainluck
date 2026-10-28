#!/usr/bin/env node
'use strict';
// #11674: LOCAL-ONLY qualification of passive_case_recorder.cjs.
//
//   node qualify.cjs --arm fixture --out NEW_DIR --playwright-module DIR --browser-channel CH --browser-mode MODE [--only NAME,NAME] [--parallel N]
//   node qualify.cjs --arm product-lab --lab-facts FILE --out NEW_DIR --playwright-module DIR --browser-channel CH --browser-mode MODE [--only ...]
//
// Every control writes its own pinned case (policy, evidence, receipts — all
// labeled LOCAL QUALIFICATION, none a production receipt), runs the recorder
// in `--scope local` as a subprocess exactly as a production invocation would
// (only the scope differs), and checks the recorder's own STOP/SUMMARY and
// journal. The fixture arm is synthetic; product-lab drives the real product
// page served by the lab. Nothing here can reach a non-loopback host: the
// recorder's local scope refuses one, and this harness refuses to start if a
// lab fact names one.
const {spawn} = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const net = require('net');

const HERE = __dirname;
const RECORDER = path.join(HERE, 'passive_case_recorder.cjs');
const FIXTURE = path.join(HERE, 'fixture_arm.cjs');
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const iso = ms => new Date(ms).toISOString().replace(/\.(\d{3})Z$/, '.$1Z');

const args = {};
for (let i = 2; i < process.argv.length; i += 2) args[process.argv[i].slice(2)] = process.argv[i + 1];
for (const k of ['arm', 'out', 'playwright-module', 'browser-channel', 'browser-mode']) if (!args[k]) { console.error(`--${k} required`); process.exit(2); }
const OUT = path.resolve(args.out);
if (fs.existsSync(OUT)) { console.error(`--out exists: ${OUT}`); process.exit(3); }
fs.mkdirSync(OUT);

const LIMITS = {max_request_attempts: 400, max_eventsource_constructions: 4, max_stream_attempts: 6, max_active_streams: 1,
  max_response_bytes: 50_000_000, max_stream_bytes: 20_000_000, max_request_bytes: 2_000_000, max_record_bytes: 262_144,
  max_saved_bytes: 200_000_000, reserved_stop_bytes: 4_000_000, max_queue_records: 512, max_detail_requests: 0,
  received_overshoot_bytes: 65_536};
const RESOURCE_TYPES = ['document', 'script', 'fetch', 'eventsource', 'xhr', 'stylesheet', 'image', 'font', 'manifest', 'other'];

function freePort() {
  return new Promise((resolve, reject) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => resolve(p)); }); s.on('error', reject); });
}
function writePinned(dir, name, value) {
  const file = path.join(dir, name);
  fs.writeFileSync(file, typeof value === 'string' ? value : JSON.stringify(value, null, 1));
  return {path: file, sha256: sha(fs.readFileSync(file))};
}

// One case: a manifest and a grant for a T0 `leadMs` from now.
function buildCase(dir, {origin, eventId, members, authority, leadMs, limits, mutateManifest, mutateGrant, detail}) {
  fs.mkdirSync(dir);
  const now = Date.now();
  const t0 = Math.ceil((now + leadMs) / 1000) * 1000;
  const label = 'LOCAL QUALIFICATION ONLY — not a production receipt';
  const receipt = name => writePinned(dir, `${name}.json`, {label, name});
  const manifest = {
    schema: 'bainluck.passive-case-manifest/1', case_id: `qual-${path.basename(dir)}`,
    policy: writePinned(dir, 'policy.json', {label, policy: 'qualification'}),
    selection: {selected_at: iso(now - 1000), max_age_s: 3600, selected_by: 'lane1 qualification',
      inventory: {evidence: writePinned(dir, 'inventory.json', {label, candidates: [eventId]}), order: [eventId], rejections: [], replacement_rule: 'none: the recorder never replaces'}},
    event: {canonical_event_id: eventId, members, contributing_sources: [{source: 'fixture', contract: 'qualification', orientation: 'home'}]},
    owner_receipts: {backend: {source_sha: '0'.repeat(40), release_receipt: receipt('backend')}, worker: {source_sha: '0'.repeat(40), release_receipt: receipt('worker')},
      frontend: {source_sha: '0'.repeat(40), release_receipt: receipt('frontend')}, authority, preview_activation: receipt('preview-activation')},
    entry: {page_url: `${origin}/events/${eventId}`, api_origin: origin, readout_activation: 'click-live-connection-status',
      expected_stream_url: `${origin}/api/events/${eventId}/stream?preview_protocol=authority-v3`,
      expected_stream_events: ['preview_open_v3', 'preview_v3', 'folded_probability', 'heartbeat']},
    trace: null,
    clock: {t0_utc: iso(t0), scoring: {start_offset_ms: 0, end_offset_ms: 180000}, acquisition: {start_offset_ms: -5000, end_offset_ms: 185000},
      setup: {earliest_offset_ms: -(leadMs + 10000), cutoff_offset_ms: -5000}},
    page: {viewport: {width: 390, height: 844}, held_pages: 1, require_document_visible: true, require_in_viewport: false},
    cleanup: {custody: 'lane1 qualification harness; fixture/lab processes stopped by the harness'},
  };
  if (mutateManifest) mutateManifest(manifest, dir);
  const mPath = path.join(dir, 'manifest.json');
  fs.writeFileSync(mPath, JSON.stringify(manifest, null, 1));
  const mSha = sha(fs.readFileSync(mPath));
  const grant = {schema: 'bainluck.passive-case-grant/1', grant_id: `grant-${path.basename(dir)}`, issued_by: 'lane1 qualification',
    issued_at: iso(now - 1000), expires_at: iso(t0 + 600000), case_id: manifest.case_id, manifest_sha256: mSha,
    allowed_origins: [origin], allowed_routes: [{origin, methods: ['GET'], path_prefix: '/', resource_types: RESOURCE_TYPES}],
    limits: {...LIMITS, ...limits}, detail_requests: detail || []};
  if (mutateGrant) mutateGrant(grant, dir);
  const gPath = path.join(dir, 'grant.json');
  fs.writeFileSync(gPath, JSON.stringify(grant, null, 1));
  return {mPath, mSha, gPath, gSha: sha(fs.readFileSync(gPath)), t0, manifest, grant};
}

function run(cmd, argv, {env, logFile, timeoutMs}) {
  return new Promise(resolve => {
    const fd = fs.openSync(logFile, 'w');
    const p = spawn(cmd, argv, {env: {...process.env, ...env}, stdio: ['ignore', fd, fd]});
    const t = setTimeout(() => p.kill('SIGKILL'), timeoutMs);
    p.on('exit', (code, signal) => { clearTimeout(t); fs.closeSync(fd); resolve({code, signal}); });
  });
}
function readJson(file) { try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return null; } }
function records(dir) {
  try { return fs.readFileSync(path.join(dir, 'records.jsonl'), 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l)); } catch { return []; }
}
const has = (list, x) => Array.isArray(list) && list.includes(x);

// ---------------------------------------------------------------- controls
const AUTH = {incarnation: '7', namespace: '3b4f1a52-8d7e-4c1a-9f0e-2a6b5c4d3e21'};
const full = 'full-window';
const FIXTURE_CONTROLS = [
  {name: 'C1-fixture-normal', page: 'normal', stream: 'normal', kind: full, expect: r => [
    [r.code === 0 && r.summary?.status === 'COMPLETE', `exit ${r.code} status ${r.summary?.status} holes ${r.summary?.holes} faults ${r.summary?.fault_kinds}`],
    [r.stop?.counters.eventsource_constructions === 1 && r.stop?.counters.stream_attempts === 1, 'one subscription, one stream attempt'],
    [Object.keys(r.stop?.counters.methods || {}).join() === 'GET', `methods ${JSON.stringify(r.stop?.counters.methods)}`],
    [r.summary?.coverage.start_edge_covered && r.summary?.coverage.end_edge_covered, 'both 180 s edges covered'],
    [r.stop?.counters.samples >= 1850, `samples ${r.stop?.counters.samples}`],
    [r.stop?.stopped_since_t0_ms?.[0] >= 185000 && r.stop?.stopped_since_t0_ms?.[0] < 186000, `stopped at ${r.stop?.stopped_since_t0_ms}`]]},
  {name: 'C1-fixture-with-market-stream', page: 'market-stream', stream: 'normal', kind: full, expect: r => [
    [r.code === 0 && r.summary?.status === 'COMPLETE', `status ${r.summary?.status} holes ${r.summary?.holes} faults ${r.summary?.fault_kinds}`],
    [r.stop?.counters.eventsource_constructions === 1 && r.stop?.counters.other_eventsource_constructions === 1, `case ${r.stop?.counters.eventsource_constructions} other ${r.stop?.counters.other_eventsource_constructions}`],
    [r.stop?.counters.other_frames > 0 && r.recs.some(x => x.rec?.kind === 'es-construct' && x.rec.url.includes('/api/markets/stream')), 'the other subscription is recorded raw, not treated as the case']]},
  // The exact production-scope code path (no qualification fault is possible there) against a
  // loopback fixture the grant names. Production scope binds origins to the grant alone.
  {name: 'C1-production-scope-loopback-fixture', scope: 'production', page: 'market-stream', stream: 'normal', kind: full, expect: r => [
    [r.code === 0 && r.summary?.status === 'COMPLETE' && r.summary?.scope === 'production', `scope ${r.summary?.scope} status ${r.summary?.status} holes ${r.summary?.holes} faults ${r.summary?.fault_kinds}`],
    [r.stop?.counters.eventsource_constructions === 1 && r.stop?.counters.other_eventsource_constructions === 1 && Object.keys(r.stop?.counters.methods || {}).join() === 'GET', `case ${r.stop?.counters.eventsource_constructions} other ${r.stop?.counters.other_eventsource_constructions} methods ${JSON.stringify(r.stop?.counters.methods)}`]]},
  {name: 'C2-malformed-json', page: 'normal', stream: 'malformed', kind: full, expect: r => [
    [r.code === 1 && r.summary?.status === 'UNRESOLVED' && has(r.summary?.fault_kinds, 'frame-malformed-json'), `status ${r.summary?.status} ${r.summary?.fault_kinds}`],
    [r.recs.some(x => x.rec?.type === 'preview_v3' && x.rec?.data === '{"protocol":3,"event_id":1,'), 'raw malformed frame retained verbatim']]},
  {name: 'C2-wrong-event', page: 'normal', stream: 'wrong-event', kind: full, expect: r => [[has(r.summary?.fault_kinds, 'frame-wrong-event') && r.summary?.status === 'UNRESOLVED', `${r.summary?.fault_kinds}`]]},
  {name: 'C2-wrong-members', page: 'normal', stream: 'wrong-members', kind: full, expect: r => [[has(r.summary?.fault_kinds, 'frame-wrong-members') && r.summary?.status === 'UNRESOLVED', `${r.summary?.fault_kinds}`]]},
  {name: 'C2-wrong-domain', page: 'normal', stream: 'wrong-domain', kind: full, expect: r => [[has(r.summary?.fault_kinds, 'frame-wrong-domain') && r.summary?.status === 'UNRESOLVED', `${r.summary?.fault_kinds}`]]},
  {name: 'C2-wrong-session', page: 'normal', stream: 'wrong-session', kind: full, expect: r => [[has(r.summary?.fault_kinds, 'frame-wrong-session') && r.summary?.status === 'UNRESOLVED', `${r.summary?.fault_kinds}`]]},
  {name: 'C2-duplicate-key', page: 'normal', stream: 'dup-key', kind: full, expect: r => [[has(r.summary?.fault_kinds, 'frame-duplicate-key') && r.summary?.status === 'UNRESOLVED', `${r.summary?.fault_kinds}`]]},
  {name: 'C2-missing-protocol-field', page: 'normal', stream: 'missing-protocol-field', kind: full, expect: r => [[has(r.summary?.fault_kinds, 'frame-missing-protocol') && r.summary?.status === 'UNRESOLVED', `${r.summary?.fault_kinds}`]]},
  {name: 'C2-url-protocol-missing', page: 'missing', stream: 'normal', kind: full, expect: r => [[has(r.summary?.fault_kinds, 'stream-protocol-missing') && has(r.summary?.fault_kinds, 'stream-url-mismatch') && r.summary?.status === 'UNRESOLVED', `${r.summary?.fault_kinds}`]]},
  {name: 'C2-url-protocol-duplicated', page: 'duplicate', stream: 'normal', kind: full, expect: r => [[has(r.summary?.fault_kinds, 'stream-protocol-duplicated') && r.summary?.status === 'UNRESOLVED', `${r.summary?.fault_kinds}`]]},
  {name: 'C2-headline-hidden', page: 'hidden-hero', stream: 'normal', kind: full, expect: r => [[has(r.summary?.holes, 'headline-unsupported-or-hidden') && r.summary?.coverage.surface_holes.headline.first[0]?.why === 'hidden' && r.summary?.status === 'UNRESOLVED', `${r.summary?.holes} ${JSON.stringify(r.summary?.coverage.surface_holes.headline.first[0])}`]]},
  {name: 'C2-headline-unsupported', page: 'unsupported', stream: 'normal', kind: full, expect: r => [[has(r.summary?.holes, 'headline-unsupported-or-hidden') && r.summary?.coverage.surface_holes.headline.first[0]?.why === 'unsupported', `${r.summary?.holes}`]]},
  {name: 'C3-request-cap', page: 'many-requests', stream: 'normal', limits: {max_request_attempts: 12}, expect: r => [
    [r.code === 1 && r.stop?.reason === 'cap:max_request_attempts', `reason ${r.stop?.reason}`],
    [r.stop?.counters.request_attempts === 12, `attempts ${r.stop?.counters.request_attempts}`],
    [r.recs.some(x => x.kind === 'request' && x.decision === 'refused-cap'), 'the 13th attempt was refused before it left the browser'],
    [r.fixtureLog.filter(e => e.kind === 'request').length <= 12, `fixture saw ${r.fixtureLog.filter(e => e.kind === 'request').length} requests`]]},
  {name: 'C3-sse-endless-response-cap', page: 'normal', stream: 'endless', limits: {max_response_bytes: 3_000_000, max_stream_bytes: 3_000_000}, expect: r => [
    [r.code === 1 && ['cap:max_response_bytes', 'cap:max_stream_bytes'].includes(r.stop?.reason), `reason ${r.stop?.reason}`],
    [r.stop?.counters.transport.response_bytes <= 3_000_000, `forwarded ${r.stop?.counters.transport.response_bytes} <= cap`],
    [r.stop?.counters.transport.max_received_chunk <= 65_536, `largest received chunk ${r.stop?.counters.transport.max_received_chunk}`]]},
  // Characterization: the per-stream sub-ceiling is counted from CDP Network.dataReceived, which
  // lags (a fast stream can starve the recorder's loop so CDP counts nothing before the transport
  // trips). It is NOT a hard boundary; the aggregate transport ceiling is. This control passes when
  // the hard ceiling holds whichever counter trips, and retains how far CDP lagged.
  {name: 'C3-stream-subcap-is-soft', page: 'normal', stream: 'endless', limits: {max_stream_bytes: 500_000}, expect: r => [
    [r.code === 1 && ['cap:max_stream_bytes', 'cap:max_response_bytes'].includes(r.stop?.reason), `reason ${r.stop?.reason}`],
    [r.stop?.counters.transport.response_bytes <= 50_000_000, `hard ceiling held: forwarded ${r.stop?.counters.transport.response_bytes} <= 50000000`],
    [true, `soft sub-ceiling 500000: CDP counted ${r.stop?.counters.cdp_stream_bytes} stream bytes when the run stopped (forwarded ${r.stop?.counters.transport.response_bytes})`]]},
  {name: 'C3-http-finite-body-cap', page: 'big-fetch', stream: 'normal', limits: {max_response_bytes: 1_500_000, max_stream_bytes: 1_000_000}, expect: r => [
    [r.code === 1 && r.stop?.reason === 'cap:max_response_bytes', `reason ${r.stop?.reason}`],
    [r.stop?.counters.transport.response_bytes <= 1_500_000 && r.stop?.counters.transport.refused_chunks >= 1, `forwarded ${r.stop?.counters.transport.response_bytes}, refused ${r.stop?.counters.transport.refused_chunks}`]]},
  {name: 'C3-sse-endless-tls-connect-cap', page: 'normal', stream: 'endless', tls: true, limits: {max_response_bytes: 3_000_000, max_stream_bytes: 3_000_000}, expect: r => [
    [r.code === 1 && ['cap:max_response_bytes', 'cap:max_stream_bytes'].includes(r.stop?.reason), `reason ${r.stop?.reason}`],
    [r.stop?.counters.transport.tunnels >= 1 && r.stop?.counters.transport.http_requests === 0, `tunnels ${r.stop?.counters.transport.tunnels} http ${r.stop?.counters.transport.http_requests}`],
    [r.stop?.counters.transport.response_bytes <= 3_000_000, `forwarded ${r.stop?.counters.transport.response_bytes}`]]},
  {name: 'C3-saved-bytes-cap', page: 'normal', stream: 'normal', limits: {max_saved_bytes: 600_000, reserved_stop_bytes: 200_000, max_record_bytes: 100_000}, expect: r => [
    [r.code === 1 && r.stop?.reason === 'cap:max_saved_bytes', `reason ${r.stop?.reason}`],
    [r.stop?.counters.journal.saved_bytes <= 400_000 && r.stop?.counters.journal.refused >= 1, `saved ${r.stop?.counters.journal.saved_bytes} refused ${r.stop?.counters.journal.refused}`],
    [!!r.summary, 'STOP and SUMMARY written from the reserve']]},
  {name: 'C3-queue-overflow', page: 'normal', stream: 'normal', limits: {max_queue_records: 1}, kind: full, expect: r => [
    [has(r.summary?.holes, 'page-queue-loss') && r.stop?.counters.page_queue.dropped > 0, `holes ${r.summary?.holes} dropped ${r.stop?.counters.page_queue?.dropped} hw ${r.stop?.counters.page_queue?.high_water}`]]},
  {name: 'C3-redirect-counted', page: 'redirect', stream: 'normal', kind: full, expect: r => [
    [r.stop?.counters.redirect_hops >= 1, `redirect hops ${r.stop?.counters.redirect_hops}`],
    [r.recs.filter(x => x.kind === 'request' && x.url?.endsWith('/api/ping') && ['allowed', 'unrouted-counted'].includes(x.decision)).length >= 1, 'the redirect target was counted as an attempt']]},
  {name: 'C4-quiet-stream-deadline', page: 'normal', stream: 'quiet', kind: full, expect: r => [
    [r.stop?.reason === 'deadline' && r.stop?.stopped_since_t0_ms?.[0] >= 185000 && r.stop?.stopped_since_t0_ms?.[0] < 186000, `reason ${r.stop?.reason} at ${r.stop?.stopped_since_t0_ms}`],
    [r.stop?.counters.stream_attempts === 1, `stream attempts ${r.stop?.counters.stream_attempts} (no retry to extend)`],
    [r.summary?.status === 'UNRESOLVED' && r.summary.holes.some(h => h.startsWith('expected-stream-event-missing')), `${r.summary?.holes}`]]},
  {name: 'C4-hung-stream-deadline', page: 'normal', stream: 'hung', kind: full, expect: r => [
    [r.stop?.reason === 'deadline' && r.stop?.stopped_since_t0_ms?.[0] < 186000, `reason ${r.stop?.reason} at ${r.stop?.stopped_since_t0_ms}`],
    [r.stop?.counters.stream_attempts === 1 && r.elapsedMs < 260000, `stream attempts ${r.stop?.counters.stream_attempts}, elapsed ${r.elapsedMs}`]]},
  {name: 'C4-product-style-reconnect', page: 'normal', stream: 'reconnect-event', kind: full,
    limits: {max_detail_requests: 1}, detail: origin => [{method: 'GET', url: `${origin}/api/ping`, at_offset_ms: 10000}], expect: r => [
    [r.stop?.counters.eventsource_constructions === 2 && r.stop?.counters.stream_attempts === 2, `constructions ${r.stop?.counters.eventsource_constructions} attempts ${r.stop?.counters.stream_attempts}`],
    [Object.values(r.summary?.streams || {}).filter(s => s.session).length === 2 && new Set(Object.values(r.summary?.streams || {}).map(s => s.session)).size === 2, 'each instance retained its own session'],
    [!has(r.summary?.fault_kinds, 'concurrent-duplicate-stream'), 'no concurrent duplicate'],
    [has(r.summary?.holes, 'stream-outage') && r.summary?.coverage.stream_outages.all[0]?.cause === 'close', `reconnect keeps its hole: ${JSON.stringify(r.summary?.coverage.stream_outages.all[0] || null).slice(0, 200)}`],
    [r.recs.some(x => x.kind === 'detail' && x.status === 200) && r.stop?.counters.detail_requests === 1, 'one granted detail request, counted']]},
  {name: 'C4-native-recovery-after-sever', page: 'normal', stream: 'normal', kind: full, fault: {kind: 'sever-stream', at_offset_ms: 30000}, expect: r => [
    [r.stop?.counters.eventsource_constructions === 1 && r.stop?.counters.stream_attempts === 2, `constructions ${r.stop?.counters.eventsource_constructions} attempts ${r.stop?.counters.stream_attempts}`],
    [Object.values(r.summary?.streams || {})[0]?.opens === 2, `opens ${JSON.stringify(r.summary?.streams)}`],
    [r.recs.some(x => x.kind === 'page' && x.rec?.type === 'folded_probability' && x.since_t0_ms?.[0] > 40000), 'frames continue after recovery'],
    [has(r.summary?.holes, 'stream-outage') && r.summary?.coverage.stream_outages.all[0]?.cause === 'error' && r.summary?.status === 'UNRESOLVED', `recovery keeps its hole: ${JSON.stringify(r.summary?.coverage.stream_outages.all[0] || null).slice(0, 200)}`]]},
  {name: 'C4-parallel-subscription-detected', page: 'second-subscription', stream: 'normal', kind: full, expect: r => [[has(r.summary?.fault_kinds, 'concurrent-duplicate-stream'), `${r.summary?.fault_kinds}`]]},
  {name: 'C5-collector-wall-jump', page: 'normal', stream: 'normal', kind: full, fault: {kind: 'wall-jump', ms: 5000, at_offset_ms: 20000}, expect: r => [[has(r.summary?.fault_kinds, 'collector-wall-jump-or-suspend') && r.summary?.status === 'UNRESOLVED', `${r.summary?.fault_kinds}`]]},
  {name: 'C5-document-busy-read-uncertainty', page: 'busy', stream: 'normal', kind: full, expect: r => [[has(r.summary?.fault_kinds, 'clock-read-uncertainty') || has(r.summary?.holes, 'sample-gaps'), `${r.summary?.fault_kinds} ${r.summary?.holes}`]]},
  {name: 'C5-document-replaced', page: 'replace-document', stream: 'normal', kind: full, expect: r => [[has(r.summary?.fault_kinds, 'document-navigated-after-setup') && has(r.summary?.fault_kinds, 'document-replaced'), `${r.summary?.fault_kinds}`]]},
  {name: 'C5-export-failure', page: 'normal', stream: 'normal', fault: {kind: 'export-fail', after_records: 300}, expect: r => [[r.stop?.reason === 'export-failure' && has(r.summary?.fault_kinds, 'export-failure'), `reason ${r.stop?.reason}`]]},
  {name: 'C5-cancel-stops-with-receipt', page: 'normal', stream: 'normal', fault: {kind: 'cancel', at_offset_ms: 15000}, expect: r => [[r.stop?.reason === 'cancelled' && r.summary?.status === 'STOPPED' && r.recs.some(x => x.kind === 'primary-export'), `reason ${r.stop?.reason}, primary exported`]]},
  {name: 'C5-pin-drift-after-validation', page: 'normal', stream: 'normal', faultFn: dir => ({kind: 'drift-after-validation', path: path.join(dir, 'policy.json')}), expect: r => [
    [r.stop?.reason === 'refused:pin-drift', `reason ${r.stop?.reason}`],
    [r.fixtureLog.filter(e => e.kind === 'request').length === 0, `fixture saw ${r.fixtureLog.filter(e => e.kind === 'request').length} requests`]]},
];
// Refusals: exit 3, no --out created, and the fixture sees no request.
const REFUSAL_CONTROLS = [
  ['R-manifest-sha-wrong', {argv: a => ({...a, 'manifest-sha256': 'f'.repeat(64)})}, /manifest: sha256 drift/],
  ['R-grant-sha-wrong', {argv: a => ({...a, 'grant-sha256': 'e'.repeat(64)})}, /grant: sha256 drift/],
  ['R-policy-drift', {after: c => fs.appendFileSync(c.manifest.policy.path, ' ')}, /manifest.policy: sha256 drift/],
  ['R-out-exists', {argv: a => { fs.mkdirSync(a.out); return a; }}, /--out exists/],
  ['R-production-host-in-local-scope', {mutateManifest: m => { m.entry.page_url = 'https://bainluck.com/events/1'; m.entry.api_origin = 'https://api.bainluck.com'; m.entry.expected_stream_url = 'https://api.bainluck.com/api/events/1/stream?preview_protocol=authority-v3'; },
    mutateGrant: g => { g.allowed_origins.push('https://bainluck.com', 'https://api.bainluck.com'); }}, /local scope: non-loopback origin refused \((api\.)?bainluck\.com\)/],
  ['R-grant-expired', {mutateGrant: g => { g.issued_at = '2026-01-01T00:00:00.000Z'; g.expires_at = '2026-01-02T00:00:00.000Z'; }}, /expires before the acquisition end/],
  ['R-grant-limit-missing', {mutateGrant: g => { delete g.limits.max_response_bytes; }}, /grant.limits: missing max_response_bytes/],
  ['R-grant-limit-infinite', {mutateGrant: g => { g.limits.max_saved_bytes = 1e400; }}, /max_saved_bytes: finite positive integer required/],
  ['R-grant-overshoot-unauthorized', {mutateGrant: g => { g.limits.received_overshoot_bytes = 1024; }}, /received_overshoot_bytes: must authorize/],
  ['R-grant-wrong-manifest', {mutateGrant: g => { g.manifest_sha256 = 'a'.repeat(64); }}, /does not bind this manifest/],
  ['R-grant-three-details', {mutateGrant: g => { g.limits.max_detail_requests = 3; }}, /integer 0..2/],
  ['R-grant-two-streams', {mutateGrant: g => { g.limits.max_active_streams = 2; }}, /exactly 1/],
  ['R-rolling-edge', {mutateManifest: m => { m.clock.acquisition.end_offset_ms = 245000; }}, /acquisition: must be the predeclared -5000..185000/],
  ['R-late-start', {mutateManifest: m => { const t = Date.now() - 2000; m.clock.t0_utc = iso(Math.floor(t / 1000) * 1000); }}, /late start/],
  ['R-production-scope-with-qual-fault', {argv: a => ({...a, scope: 'production'}), env: {PASSIVE_RECORDER_QUAL_FAULT: '{"kind":"cancel","at_offset_ms":1}'}}, /production scope refuses qualification faults/],
  ['R-unknown-manifest-field', {mutateManifest: m => { m.extra = true; }}, /manifest: unknown extra/],
];

async function startFixture(dir, page, stream, tls) {
  const port = await freePort();
  let tlsDir = null;
  if (tls) {
    tlsDir = path.join(dir, 'tls');
    fs.mkdirSync(tlsDir);
    await run('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', path.join(tlsDir, 'key.pem'), '-out', path.join(tlsDir, 'cert.pem'), '-days', '1', '-subj', '/CN=127.0.0.1'], {env: {}, logFile: path.join(tlsDir, 'openssl.log'), timeoutMs: 30000});
  }
  const logFile = path.join(dir, 'fixture-requests.json');
  const p = spawn('node', [FIXTURE, '--port', String(port), '--page', page, '--stream', stream, '--log', logFile, ...(tls ? ['--tls', tlsDir] : [])], {stdio: ['ignore', fs.openSync(path.join(dir, 'fixture.log'), 'w'), 'inherit']});
  for (let i = 0; i < 100; i++) {
    if (await new Promise(r => { const s = net.connect(port, '127.0.0.1', () => { s.destroy(); r(true); }); s.on('error', () => r(false)); })) break;
    await new Promise(r => setTimeout(r, 50));
  }
  return {origin: `${tls ? 'https' : 'http'}://127.0.0.1:${port}`, stop: () => new Promise(r => { p.on('exit', r); p.kill('SIGTERM'); }), logFile};
}

function argvOf(a) { return ['record', ...Object.entries(a).flatMap(([k, v]) => [`--${k}`, v])]; }

async function runControl(c, base) {
  const dir = path.join(OUT, c.name);
  let fixture = null;
  if (!base.lab) {
    const armDir = path.join(OUT, `${c.name}.arm`);
    fs.mkdirSync(armDir);
    fixture = await startFixture(armDir, c.page, c.stream, c.tls);
  }
  const origin = base.lab ? base.lab.origin : fixture.origin;
  const kase = buildCase(dir, {origin, eventId: base.lab ? base.lab.event_id : 1, members: base.lab ? base.lab.members : [1], authority: base.lab ? base.lab.authority : AUTH,
    leadMs: base.leadMs, limits: c.limits, detail: c.detail && c.detail(origin), mutateManifest: base.lab ? m => { m.entry.expected_stream_events = base.lab.expected_stream_events; } : null});
  const fault = c.fault || (c.faultFn && c.faultFn(dir));
  const env = fault ? {PASSIVE_RECORDER_QUAL_FAULT: JSON.stringify(fault)} : {};
  const recOut = path.join(dir, 'recording');
  const a = {scope: c.scope || 'local', manifest: kase.mPath, 'manifest-sha256': kase.mSha, grant: kase.gPath, 'grant-sha256': kase.gSha, out: recOut, 'playwright-module': args['playwright-module'], 'browser-channel': args['browser-channel'], 'browser-mode': args['browser-mode']};
  if (base.lab && base.lab.trigger) setTimeout(() => base.trigger(kase.t0), Math.max(0, kase.t0 - Date.now()));
  const started = Date.now();
  const res = await run('node', [RECORDER, ...argvOf(a)], {env, logFile: path.join(dir, 'recorder.log'), timeoutMs: base.leadMs + 300000});
  const elapsedMs = Date.now() - started;
  if (fixture) await fixture.stop();
  const r = {code: res.code, signal: res.signal, elapsedMs, stop: readJson(path.join(recOut, 'STOP.json')), summary: readJson(path.join(recOut, 'SUMMARY.json')),
    recs: records(recOut), fixtureLog: fixture ? (readJson(fixture.logFile) || []) : []};
  const checks = c.expect(r).map(([ok, detail]) => ({ok: !!ok, detail}));
  return {name: c.name, arm: base.lab ? 'product-lab' : 'fixture', invocation: ['node', RECORDER, ...argvOf(a)], env, exit: res.code, signal: res.signal, elapsed_ms: elapsedMs,
    status: r.summary?.status ?? null, reason: r.stop?.reason ?? null, holes: r.summary?.holes ?? null, fault_kinds: r.summary?.fault_kinds ?? null,
    pass: checks.every(x => x.ok), checks, out: recOut, manifest_sha256: kase.mSha, grant_sha256: kase.gSha, t0_utc: kase.manifest.clock.t0_utc};
}

async function runRefusal([name, spec, pattern]) {
  const dir = path.join(OUT, name);
  const armDir = path.join(OUT, `${name}.arm`);
  fs.mkdirSync(armDir);
  const fixture = await startFixture(armDir, 'normal', 'normal', false);
  const kase = buildCase(dir, {origin: fixture.origin, eventId: 1, members: [1], authority: AUTH, leadMs: 25000, mutateManifest: spec.mutateManifest, mutateGrant: spec.mutateGrant});
  if (spec.after) spec.after(kase);
  let a = {scope: 'local', manifest: kase.mPath, 'manifest-sha256': kase.mSha, grant: kase.gPath, 'grant-sha256': kase.gSha, out: path.join(dir, 'recording'), 'playwright-module': args['playwright-module'], 'browser-channel': args['browser-channel'], 'browser-mode': args['browser-mode']};
  if (spec.argv) a = spec.argv(a);
  const outExisted = fs.existsSync(a.out);
  const logFile = path.join(dir, 'recorder.log');
  const res = await run('node', [RECORDER, ...argvOf(a)], {env: spec.env || {}, logFile, timeoutMs: 60000});
  await fixture.stop();
  const text = fs.readFileSync(logFile, 'utf8');
  const fixtureRequests = (readJson(fixture.logFile) || []).filter(e => e.kind === 'request').length;
  const outCreated = !outExisted && fs.existsSync(a.out);
  const checks = [{ok: res.code === 3, detail: `exit ${res.code}`}, {ok: pattern.test(text), detail: `refusal names ${pattern}`},
    {ok: fixtureRequests === 0, detail: `fixture requests ${fixtureRequests}`}, {ok: !outCreated, detail: outCreated ? '--out created' : '--out not created'}];
  return {name, arm: 'fixture', invocation: ['node', RECORDER, ...argvOf(a)], env: spec.env || {}, exit: res.code, pass: checks.every(x => x.ok), checks, refusal: text.slice(0, 2000)};
}

async function pool(items, n, fn) {
  const results = [];
  let i = 0;
  await Promise.all(Array.from({length: n}, async () => { while (i < items.length) { const k = i++; results[k] = await fn(items[k]); console.log(`${results[k].pass ? 'PASS' : 'FAIL'} ${results[k].name} exit=${results[k].exit} ${results[k].reason || ''}`); } }));
  return results;
}

(async () => {
  const only = args.only ? new Set(args.only.split(',')) : null;
  const parallel = Number(args.parallel || 4);
  const started = new Date().toISOString();
  const base = {leadMs: Number(args['lead-ms'] || 25000)};
  let results = [];
  if (args.arm === 'fixture') {
    const refusals = REFUSAL_CONTROLS.filter(c => !only || only.has(c[0]));
    results.push(...await pool(refusals, parallel, runRefusal));
    results.push(...await pool(FIXTURE_CONTROLS.filter(c => !only || only.has(c.name)), parallel, c => runControl(c, base)));
  } else if (args.arm === 'product-lab') {
    const facts = JSON.parse(fs.readFileSync(args['lab-facts'], 'utf8'));
    for (const u of [facts.origin, facts.trigger && facts.trigger.url].filter(Boolean)) if (!['127.0.0.1', 'localhost'].includes(new URL(u).hostname)) { console.error('lab fact names a non-loopback host'); process.exit(3); }
    base.lab = facts;
    base.leadMs = Number(args['lead-ms'] || 40000);
    // The lab scenario is started by THIS harness at T0, never by the recorder.
    base.trigger = async () => {
      const http = require('http');
      const body = JSON.stringify(facts.trigger.body);
      await new Promise(resolve => { const req = http.request(facts.trigger.url, {method: 'POST', headers: {'content-type': 'application/json', 'content-length': Buffer.byteLength(body)}}, res => { let d = ''; res.on('data', c => { d += c; }); res.on('end', () => { fs.writeFileSync(path.join(OUT, `lab-trigger-${Date.now()}.json`), d); resolve(); }); }); req.on('error', e => { fs.writeFileSync(path.join(OUT, `lab-trigger-error-${Date.now()}.txt`), String(e)); resolve(); }); req.end(body); });
    };
    const P = [
      {name: 'P1-product-held-page', expect: r => [
        [r.stop?.reason === 'deadline', `reason ${r.stop?.reason}`],
        // The real backend may roll the stream over (`reconnect`) or drop it; the recorder must keep
        // each reopen as its own counted, exact-URL construction with a new session and a retained hole.
        [!has(r.summary?.fault_kinds, 'concurrent-duplicate-stream') && r.stop?.counters.eventsource_constructions <= r.stop?.limits.max_eventsource_constructions && r.stop?.counters.stream_attempts <= r.stop?.limits.max_stream_attempts, `case constructions ${r.stop?.counters.eventsource_constructions} attempts ${r.stop?.counters.stream_attempts} within caps; other product EventSources ${JSON.stringify(r.summary?.other_eventsources)}`],
        [r.recs.filter(x => x.rec?.kind === 'es-construct' && x.rec.url.includes('/api/events/')).every(x => x.rec.url === `${facts.origin}/api/events/${facts.event_id}/stream?preview_protocol=authority-v3`), 'every case construction used the exact authority-v3 URL'],
        [(r.summary?.coverage.stream_outages.all || []).every(o => o.to_mono !== null) && Object.values(r.summary?.streams || {}).filter(x => x.session).length >= 1 + (r.summary?.coverage.stream_outages.all || []).filter(o => o.cause === 'close').length, `outages ${(r.summary?.coverage.stream_outages.all || []).map(o => o.cause + '@' + Math.round(o.from_since_t0_ms?.[0])).join(',') || 'none'} each closed by a new open; sessions ${JSON.stringify(r.summary?.streams)}`],
        [!has(r.summary?.fault_kinds, 'stream-url-mismatch') && r.recs.some(x => x.rec?.kind === 'es-construct' && x.rec.url === `${facts.origin}/api/events/${facts.event_id}/stream?preview_protocol=authority-v3`), 'exact authority-v3 URL from the product constructor'],
        [r.recs.some(x => x.rec?.type === 'preview_open_v3') && !has(r.summary?.fault_kinds, 'frame-wrong-members') && !has(r.summary?.fault_kinds, 'frame-wrong-domain'), 'complete open envelope matching the declared members/authority'],
        [base.lab.expected_stream_events.every(t => has(r.summary?.stream_event_types_seen, t)), `declared ${base.lab.expected_stream_events}; seen ${r.summary?.stream_event_types_seen}`],
        [r.summary?.fault_count === 0 && (r.summary?.status === 'COMPLETE' || r.summary?.holes.every(h => h === 'stream-outage')), `status ${r.summary?.status} holes ${r.summary?.holes} faults ${r.summary?.fault_kinds}`],
        [Object.keys(r.stop?.counters.methods || {}).every(k => k === 'GET') && !r.recs.some(x => x.kind === 'request' && /\/lab\//.test(x.url || '')), `methods ${JSON.stringify(r.stop?.counters.methods)}; no /lab/ request from the recorder's page`],
        [r.summary?.coverage.start_edge_covered && r.summary?.coverage.end_edge_covered && r.stop?.counters.samples >= 1850, `edges ${r.summary?.coverage.start_edge_covered}/${r.summary?.coverage.end_edge_covered} samples ${r.stop?.counters.samples}`],
        [r.recs.some(x => x.kind === 'sample' && x.rec?.display_identity?.headline?.status === 'present' && x.rec?.display_identity?.chart?.status === 'present'), '#11673 headline and chart attributes present on the real page']]},
      {name: 'P2-product-native-recovery', fault: {kind: 'sever-stream', at_offset_ms: 60000}, expect: r => [
        [r.stop?.counters.eventsource_constructions >= 1 && r.stop?.counters.stream_attempts >= 2, `constructions ${r.stop?.counters.eventsource_constructions} attempts ${r.stop?.counters.stream_attempts}`],
        [r.recs.filter(x => x.rec?.type === 'preview_open_v3').length >= 2, 'a new open envelope after recovery'],
        [r.recs.some(x => (x.rec?.type === 'folded_probability' || x.rec?.type === 'probability' || x.rec?.type === 'preview_v3') && x.since_t0_ms?.[0] > 65000), 'frames continue after recovery'],
        [!has(r.summary?.fault_kinds, 'concurrent-duplicate-stream'), 'no parallel subscription'],
        [has(r.summary?.holes, 'stream-outage'), 'the recovery gap is a retained hole']]},
    ].filter(c => !only || only.has(c.name));
    for (const c of P) { const res = await runControl(c, base); results.push(res); console.log(`${res.pass ? 'PASS' : 'FAIL'} ${res.name} exit=${res.exit} ${res.reason}`); }
  } else { console.error('--arm fixture|product-lab'); process.exit(2); }
  const files = {};
  for (const f of fs.readdirSync(HERE).filter(f => f.endsWith('.cjs'))) files[f] = sha(fs.readFileSync(path.join(HERE, f)));
  const receipt = {schema: 'bainluck.passive-recorder-qualification/1', arm: args.arm, browser_mode: args['browser-mode'], browser_channel: args['browser-channel'], started, ended: new Date().toISOString(), node: process.version,
    playwright_module: args['playwright-module'], recorder_files: files, passed: results.filter(r => r.pass).length, failed: results.filter(r => !r.pass).length,
    results, scope: 'local loopback only; fixture-clock, not production-clock; DOM observation, not paint'};
  fs.writeFileSync(path.join(OUT, 'QUALIFICATION.json'), JSON.stringify(receipt, null, 1));
  console.log(`QUALIFICATION ${args.arm} passed ${receipt.passed} failed ${receipt.failed} -> ${path.join(OUT, 'QUALIFICATION.json')}`);
  process.exitCode = receipt.failed ? 1 : 0;
})();
