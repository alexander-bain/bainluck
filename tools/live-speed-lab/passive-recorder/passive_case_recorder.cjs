#!/usr/bin/env node
'use strict';
// #10090 / #11674: passive held-page recorder for one predeclared case.
//
// One ordinary product page, warmed once before T0 through its normal entry.
// The page's own EventSource is observed passively (no second subscription);
// the #11673 headline/chart attributes are sampled every 100 ms with the
// pinned display_sample.cjs; the primary "Probability observed" recorder is
// the staged one, unchanged. Acquisition ends at the predeclared T0+185 s
// whatever happens. Request attempts are refused BEFORE an over-cap request
// leaves the browser; response bytes are refused at the transport boundary
// before an over-cap chunk reaches it; saved bytes stop before the STOP
// reserve. There is no default for any case, window, endpoint or limit.
const fs = require('fs');
const path = require('path');
const contract = require('./contract.cjs');
const {createTransport} = require('./transport.cjs');
const {createJournal, minimalForms} = require('./journal.cjs');
const {createClock} = require('./clock.cjs');
const hooks = require('./page_hooks.cjs');
const {installVisibleObservationRecorder} = require('./primary_recorder.cjs');
const {createChallengeDriver, inactiveSummary} = require('./challenge.cjs');

const RECORDER_VERSION = 'passive-case-recorder/2';
const DISPLAY_SAMPLE = path.resolve(__dirname, '../compare/display_sample.cjs');
const DISPLAY_SAMPLE_SHA256 = '587951bb9615190f21de1f5c9c25e3f27ad286a876d0a7ba69b47111446eb91d';
const SAMPLE_INTERVAL_MS = 100;
const SAMPLE_GAP_HOLE_MS = 300;
const CHECKPOINT_EVERY_MS = 15000;
const TEARDOWN_BUDGET_MS = 20000;
const RECORDER_FILES = ['passive_case_recorder.cjs', 'contract.cjs', 'transport.cjs', 'journal.cjs', 'clock.cjs',
  'page_hooks.cjs', 'primary_recorder.cjs', 'challenge.cjs', 'challenge_schema.json'];
// Page acks awaiting the next record; the in-page buffer refuses (and counts) beyond this.
const PAGE_ACK_PENDING_CAP = 512;
const QUAL_ENV = 'PASSIVE_RECORDER_QUAL_FAULT';

const HELP = `usage:
  passive_case_recorder.cjs validate --scope local|production --manifest PATH --manifest-sha256 HEX
                                     --grant PATH --grant-sha256 HEX
  passive_case_recorder.cjs record   --scope local|production --manifest PATH --manifest-sha256 HEX
                                     --grant PATH --grant-sha256 HEX --out NEW_DIRECTORY
                                     --playwright-module DIR --browser-channel chrome|chromium
                                     --browser-mode multi-process|single-process
                                     [--challenge-connection MODULE]   (local scope, only with grant.challenge)

validate  offline: hashes, schemas, case edges, grant limits and timing. Opens no socket.
record    one held page for the manifest's case, T0-5 s .. T0+185 s, then STOP.
          --scope local refuses every non-loopback origin even if the manifest or grant names one.
          --scope production refuses if ${QUAL_ENV} is set.
          --out must not exist; it is created, never reused.
          --browser-mode single-process adds Chrome's --single-process --disable-crashpad (the only
          mode that launches inside a sandboxed lane shell); multi-process is Chrome's ordinary layout.
          --browser-channel chrome is the installed Google Chrome; chromium is the Playwright module's own build.
          The grant's \`browser\` names the qualified channel, mode, Playwright package.json sha256 and browser
          version: a channel, mode or package it does not name refuses before launch; a version it does not
          name STOPs before navigation (refused:browser-version). All four are copied into SUMMARY.json.

Clock challenge (DARK): only a grant that names \`challenge\` turns it on, and only under --scope local with
--challenge-connection naming a module that exports connect(); production scope refuses such a grant.

Every option is required; none has a default. Exit: 0 complete case, 1 recorded but
STOPPED/UNRESOLVED (a result), 2 recorder failure, 3 refused before any network.`;

function parseArgs(argv) {
  const [command, ...rest] = argv;
  const opts = {};
  for (let i = 0; i < rest.length; i++) {
    const k = rest[i];
    if (!k.startsWith('--') || i + 1 >= rest.length || rest[i + 1].startsWith('--')) return {command, error: `bad option ${k}`};
    const key = k.slice(2);
    if (key in opts) return {command, error: `duplicate option ${k}`};
    opts[key] = rest[++i];
  }
  return {command, opts};
}

function selfPins() {
  const files = {};
  for (const f of RECORDER_FILES) files[f] = contract.sha256File(path.join(__dirname, f));
  const sampler = contract.sha256File(DISPLAY_SAMPLE);
  return {files, display_sample: {path: DISPLAY_SAMPLE, sha256: sampler, pinned: DISPLAY_SAMPLE_SHA256, ok: sampler === DISPLAY_SAMPLE_SHA256}};
}

// Every pinned file the case depends on, re-hashed immediately before navigation.
function pinnedRefs(m) {
  const refs = [m.policy, m.selection.inventory.evidence, m.owner_receipts.backend.release_receipt,
    m.owner_receipts.worker.release_receipt, m.owner_receipts.frontend.release_receipt, m.owner_receipts.preview_activation];
  if (m.trace) refs.push(m.trace.binding);
  return refs;
}

function refuse(reasons, extra = {}) {
  process.stdout.write(JSON.stringify({status: 'REFUSED', network: 'none', reasons, ...extra}, null, 1) + '\n');
  process.exitCode = 3;
}

function streamQuery(url) {
  try { const u = new URL(url); return {path: u.pathname, protocol_values: u.searchParams.getAll('preview_protocol'), keys: [...u.searchParams.keys()]}; } catch { return null; }
}

async function record(opts) {
  const required = ['scope', 'manifest', 'manifest-sha256', 'grant', 'grant-sha256', 'out', 'playwright-module', 'browser-channel', 'browser-mode'];
  const missing = required.filter(k => !opts[k]);
  const unknown = Object.keys(opts).filter(k => !required.includes(k) && k !== 'challenge-connection');
  if (missing.length || unknown.length) return refuse([...missing.map(k => `--${k} required`), ...unknown.map(k => `--${k} unknown`)]);
  const scope = opts.scope;
  let qualFault = null;
  if (scope === 'production' && process.env[QUAL_ENV]) return refuse([`${QUAL_ENV} is set; production scope refuses qualification faults`]);
  if (scope === 'local' && process.env[QUAL_ENV]) {
    try { qualFault = JSON.parse(process.env[QUAL_ENV]); } catch { return refuse([`${QUAL_ENV}: invalid JSON`]); }
  }
  const {BROWSER_MODES} = contract;
  if (!Object.hasOwn(BROWSER_MODES, opts['browser-mode'])) return refuse(['--browser-mode: multi-process or single-process']);
  if (!contract.BROWSER_CHANNELS.includes(opts['browser-channel'])) return refuse(['--browser-channel: chrome or chromium']);
  const pins = selfPins();
  if (!pins.display_sample.ok) return refuse([`display_sample.cjs drift (have ${pins.display_sample.sha256})`]);
  const v = contract.validateBundle({manifest: opts.manifest, manifestSha256: opts['manifest-sha256'], grant: opts.grant,
    grantSha256: opts['grant-sha256'], scope, now: Date.now()});
  if (!v.ok) return refuse(v.refusals);
  // The challenge is on only when the grant names it AND a local test connection is injected.
  const challengeCfg = 'challenge' in v.grant ? v.grant.challenge : null;
  let challengeModule = null;
  if (challengeCfg && !opts['challenge-connection']) return refuse(['--challenge-connection required: grant.challenge is present']);
  if (!challengeCfg && opts['challenge-connection']) return refuse(['--challenge-connection given but the grant names no challenge']);
  if (challengeCfg && scope !== 'local') return refuse(['grant.challenge: no challenge transport is admitted for production scope']);
  if (challengeCfg) {
    try {
      const file = require.resolve(path.resolve(opts['challenge-connection']));
      challengeModule = {path: file, sha256: contract.sha256File(file), connect: require(file).connect};
      if (typeof challengeModule.connect !== 'function') throw new Error('module exports no connect()');
    } catch (e) { return refuse([`--challenge-connection unusable: ${e.message}`]); }
  }
  const out = path.resolve(opts.out);
  if (fs.existsSync(out)) return refuse([`--out exists: ${out} (never reused)`]);
  if (!fs.existsSync(path.dirname(out))) return refuse([`--out parent missing: ${path.dirname(out)}`]);
  let playwright, pwPackage;
  try {
    const pkgPath = path.join(path.resolve(opts['playwright-module']), 'package.json');
    pwPackage = {path: pkgPath, sha256: contract.sha256File(pkgPath), version: JSON.parse(fs.readFileSync(pkgPath, 'utf8')).version};
    playwright = require(path.resolve(opts['playwright-module']));
  } catch (e) { return refuse([`--playwright-module unusable: ${e.message}`]); }
  const gb = v.grant.browser;
  const notGranted = [];
  if (opts['browser-channel'] !== gb.browser_channel) notGranted.push(`grant.browser: --browser-channel ${opts['browser-channel']} is not the granted ${gb.browser_channel}`);
  if (opts['browser-mode'] !== gb.browser_mode) notGranted.push(`grant.browser: --browser-mode ${opts['browser-mode']} is not the granted ${gb.browser_mode}`);
  if (pwPackage.sha256 !== gb.playwright_package_sha256) notGranted.push(`grant.browser: Playwright package.json sha256 ${pwPackage.sha256} is not the granted ${gb.playwright_package_sha256}`);
  if (notGranted.length) return refuse(notGranted);
  fs.mkdirSync(out); // non-recursive; EEXIST here would mean a race, which throws
  // Qualification-only: change a pinned file after validation so the
  // pre-navigation re-hash must catch it (local scope only, see QUAL_ENV).
  if (qualFault && qualFault.kind === 'drift-after-validation') fs.appendFileSync(qualFault.path, ' ');

  const m = v.manifest, g = v.grant, L = g.limits, W = v.window;
  const canonical = m.event.canonical_event_id;
  const streamUrl = m.entry.expected_stream_url;
  // The case stream is the product EventSource on the event stream PATH; any
  // query difference on that path is a fault. Other product EventSources (the
  // page's market stream) are recorded raw and counted, never treated as the case.
  const streamOrigin = new URL(streamUrl).origin, streamPath = new URL(streamUrl).pathname;
  const isCaseStream = url => { try { const u = new URL(url); return u.origin === streamOrigin && u.pathname === streamPath; } catch { return false; } };
  const caseInstances = new Set();
  const allowedOrigins = new Set(g.allowed_origins);
  const allowOrigin = origin => allowedOrigins.has(origin) && (scope !== 'local' || contract.isLoopbackUrl(origin));
  const faults = [];
  const fault = (kind, detail = {}) => { faults.push({...detail, kind}); };
  const counters = {request_attempts: 0, refused_requests: 0, stream_attempts: 0, redirect_hops: 0, unrouted_requests: 0,
    eventsource_constructions: 0, eventsource_closes: 0, other_eventsource_constructions: 0, other_stream_attempts: 0, other_frames: 0, detail_requests: 0, cdp_stream_bytes: 0, cdp_response_bytes: 0,
    frames: 0, frame_parse_failures: 0, samples: 0, sample_errors: 0, max_sample_gap_ms: 0, teardown_refused: 0,
    methods: {}};
  let stopping = null;
  let finishPromise = null;
  const wallSkew = {ms: 0};
  const clock = createClock({t0WallMs: W.t0_wall_ms, wallSkewMs: () => wallSkew.ms});
  const sinceT0 = () => clock.sinceT0(clock.mono());
  let finish;
  const requestStop = (reason, detail) => { if (!stopping) { stopping = {reason, detail, since_t0_ms: sinceT0()}; } if (finish) finish(); };

  const journalFault = qualFault && qualFault.kind === 'export-fail' ? {beforeWrite: s => { if (s.records >= qualFault.after_records) throw Object.assign(new Error('injected export failure'), {code: 'EQUALFAULT'}); }} : null;
  const journal = createJournal({dir: out, limits: L, fault: journalFault,
    onExhausted: d => { fault(d.export_failure ? 'export-failure' : 'saved-budget-exhausted', d); requestStop(d.export_failure ? 'export-failure' : 'cap:max_saved_bytes', d); }});
  if (!journal.writeSidecar('BINDINGS.json', {recorder: RECORDER_VERSION, scope, browser_mode: opts['browser-mode'], browser_channel: opts['browser-channel'], granted_browser: gb, pins, playwright: pwPackage, node: process.version,
    manifest: {path: path.resolve(opts.manifest), sha256: v.manifestSha256}, grant: {path: path.resolve(opts.grant), sha256: v.grantSha256},
    case_id: m.case_id, grant_id: g.grant_id, window: W, clock_anchor: clock.anchor, qualification_fault: qualFault,
    challenge: challengeModule ? {connection_module: {path: challengeModule.path, sha256: challengeModule.sha256}, config: challengeCfg} : 'inactive',
    byte_boundary: {where: 'loopback proxy write to the browser socket', counted: 'encoded wire bytes (HTTP body as received incl. Content-Encoding; CONNECT = TLS records)',
      forwarded_overshoot_bytes: 0, received_overshoot_bound_bytes: contract.RECEIVED_OVERSHOOT_BOUND_BYTES, authorized_received_overshoot_bytes: L.received_overshoot_bytes,
      per_stream: 'not enforced (CDP, lagging): the case stream is charged to max_response_bytes; counters.cdp_stream_bytes is diagnostic only'},
    receipt_bracket: 'collector C recv is stamped at the first line of onPageRecord; the page stamps send_mono before the binding call and an ack when it resolves; acks ride the next record and the stop return',
    constants: {SAMPLE_INTERVAL_MS, SAMPLE_GAP_HOLE_MS, CHECKPOINT_EVERY_MS, TEARDOWN_BUDGET_MS, PAGE_ACK_PENDING_CAP, ...clock.constants}})) {
    fault('saved-budget-exhausted', {at: 'bindings'});
    stopping = {reason: 'cap:max_saved_bytes', since_t0_ms: sinceT0()};
  }

  // Qualification-only transport fault (local scope): sever the product stream once.
  let severed = false;
  const transportFault = qualFault && qualFault.kind === 'sever-stream' ? {onResponse: (target, sock) => {
    if (severed || target.href !== streamUrl) return;
    setTimeout(() => { if (!severed) { severed = true; journal.append('qualification-fault', {kind: 'sever-stream', since_t0_ms: sinceT0()}); sock.destroy(); } }, Math.max(0, qualFault.at_offset_ms - sinceT0()[1]));
  }} : null;
  const transport = createTransport({allowOrigin, limits: L, fault: transportFault,
    onTrip: t => { fault('transport-ceiling', t); requestStop(`cap:${t.kind}`, t); },
    onEvent: e => journal.append('transport', {...e, since_t0_ms: sinceT0()})});
  const proxyPort = await transport.listen();

  const hardKill = setTimeout(() => {
    try { journal.writeReserved('STOP.json', {status: 'STOPPED', reason: 'teardown-overrun'}, minimalForms({status: 'STOPPED', reason: 'teardown-overrun'}).stop); } catch { /* best effort */ }
    process.exit(2);
  }, Math.max(0, W.acquisition_end_wall_ms - clock.wall()) + TEARDOWN_BUDGET_MS * 3);

  let browser = null, context = null, page = null, cdp = null, browserVersion = null;
  const streamState = new Map(); // instance -> {session, opens}
  const seenTypes = new Set();
  const otherStreams = new Set();
  // A stream outage runs from an error (native retry) or a close (product
  // reopen) to the next open. Reconnection keeps its hole; it is never bridged.
  const outages = [];
  let outage = null;
  const requestIds = new Map();
  const routed = new WeakSet();
  const holes = [];
  const samples = []; // compact copies for coverage only
  let samplerStarted = false, primaryInstalled = false, primaryCaptureId = null, setupReadyAt = null;
  const timers = [];
  // Receipt brackets: which page records the collector received (page_seq ->
  // C recv), and which of them the page acked. A record received before the
  // stop request whose ack never arrives is a hole.
  const receipts = {recvBySeq: new Map(), acked: new Set(), acks_unknown: 0, acks_malformed: 0, acks_dropped: 0, last_time_origin: null,
    stop_sent_mono: null, final_from_stop: 0, final_from_drain: 0};
  const noteAcks = (acks, dropped) => {
    if (Number.isSafeInteger(dropped) && dropped > receipts.acks_dropped) receipts.acks_dropped = dropped;
    if (!Array.isArray(acks)) return 0;
    for (const a of acks) {
      if (!Array.isArray(a) || a.length !== 2 || !Number.isSafeInteger(a[0]) || !Number.isFinite(a[1])) { receipts.acks_malformed++; continue; }
      if (!receipts.recvBySeq.has(a[0])) receipts.acks_unknown++;
      receipts.acked.add(a[0]);
    }
    return acks.length;
  };
  const challenge = challengeCfg ? createChallengeDriver({cfg: challengeCfg, connect: challengeModule.connect, clock, journal,
    setTimer: (fn, ms) => { const t = setTimeout(fn, ms); timers.push(t); return t; }}) : null;

  function checkFrame(rec) {
    counters.frames++;
    seenTypes.add(rec.type);
    const q = streamQuery(rec.url);
    if (rec.url !== streamUrl) fault('stream-url-mismatch', {url: rec.url, expected: streamUrl, protocol_values: q && q.protocol_values});
    if (rec.data_oversize_chars) { fault('frame-oversize', {type: rec.type, chars: rec.data_oversize_chars}); return; }
    if (typeof rec.data !== 'string' || rec.type === 'error' || rec.type === 'heartbeat' || rec.type === 'reconnect' || rec.type === 'closed') return;
    if (rec.type === 'open' && rec.data === '') return;
    let parsed;
    try {
      parsed = contract.parseStrictJson(rec.data);
    } catch (e) { counters.frame_parse_failures++; fault('frame-malformed-json', {type: rec.type, error: e.message, page_seq: rec.page_seq}); return; }
    if (parsed.duplicates.length) fault('frame-duplicate-key', {type: rec.type, keys: parsed.duplicates, page_seq: rec.page_seq});
    const d = parsed.value;
    if (d && typeof d === 'object' && 'event_id' in d && d.event_id !== canonical) fault('frame-wrong-event', {type: rec.type, event_id: d.event_id, page_seq: rec.page_seq});
    if (rec.type === 'preview_open_v3' || rec.type === 'preview_v3') {
      if (!d || d.protocol === undefined) fault('frame-missing-protocol', {type: rec.type, page_seq: rec.page_seq});
      else if (d.protocol !== 3) fault('frame-wrong-protocol', {type: rec.type, protocol: d.protocol, page_seq: rec.page_seq});
      const a = d && d.authority;
      if (!a || a.incarnation !== m.owner_receipts.authority.incarnation || a.namespace !== m.owner_receipts.authority.namespace) fault('frame-wrong-domain', {type: rec.type, authority: a, page_seq: rec.page_seq});
      const st = streamState.get(rec.instance) || {};
      if (rec.type === 'preview_open_v3') {
        const members = Array.isArray(d && d.members) ? d.members : null;
        if (!members || members.length !== m.event.members.length || members.some((x, i) => x !== m.event.members[i])) fault('frame-wrong-members', {members, expected: m.event.members, page_seq: rec.page_seq});
        st.session = d && d.stream_session;
        st.opens = (st.opens || 0) + 1;
      } else if (!st.session || (d && d.stream_session) !== st.session) {
        fault('frame-wrong-session', {session: d && d.stream_session, open_session: st.session || null, page_seq: rec.page_seq});
      }
      streamState.set(rec.instance, st);
    }
  }

  function onPageRecord(rec) {
    // Collector receipt first, before validation or journal work.
    const recvMono = clock.mono(), recvWall = clock.wall();
    const recv = {mono: recvMono, wall: recvWall, since_t0_ms: clock.sinceT0(recvMono)};
    if (!rec || typeof rec !== 'object') { fault('page-record-invalid', {recv}); return; }
    const at = clock.docToT0(rec.mono);
    if (Number.isSafeInteger(rec.page_seq)) receipts.recvBySeq.set(rec.page_seq, recvMono);
    noteAcks(rec.acks, rec.acks_dropped);
    if (rec.time_origin !== undefined) {
      if (receipts.last_time_origin !== null && rec.time_origin !== receipts.last_time_origin) fault('document-replaced-record', {from: receipts.last_time_origin, to: rec.time_origin, page_seq: rec.page_seq});
      receipts.last_time_origin = rec.time_origin;
    }
    if (rec.kind === 'es-construct') {
      if (!isCaseStream(rec.url)) {
        counters.other_eventsource_constructions++;
        otherStreams.add(rec.url);
      } else {
        caseInstances.add(rec.instance);
        counters.eventsource_constructions++;
        const q = streamQuery(rec.url);
        if (rec.url !== streamUrl) fault('stream-url-mismatch', {url: rec.url, expected: streamUrl, protocol_values: q && q.protocol_values, at: 'construct'});
        if (q && q.protocol_values.length !== 1) fault(q.protocol_values.length ? 'stream-protocol-duplicated' : 'stream-protocol-missing', {url: rec.url});
        const dup = (rec.concurrent_urls || []).filter(isCaseStream);
        if (dup.length) fault('concurrent-duplicate-stream', {instance: rec.instance, concurrent_case_streams: dup.length});
        streamState.set(rec.instance, {});
        if (counters.eventsource_constructions > L.max_eventsource_constructions) requestStop('cap:max_eventsource_constructions', {constructions: counters.eventsource_constructions});
        if (outage) outage.reopened_by_instance = rec.instance;
      }
    } else if (rec.kind === 'es-close') {
      if (caseInstances.has(rec.instance)) {
        counters.eventsource_closes++;
        if (!outage) outage = {from_mono: rec.mono, instance: rec.instance, cause: 'close'};
      }
    } else if (rec.kind === 'es-event' && !caseInstances.has(rec.instance)) {
      counters.other_frames++;
    } else if (rec.kind === 'es-event') {
      if (rec.type === 'error' && !outage) outage = {from_mono: rec.mono, instance: rec.instance, cause: 'error', ready_state: rec.ready_state};
      if (rec.type === 'open' && outage) { outages.push({...outage, to_mono: rec.mono, open_instance: rec.instance}); outage = null; }
      checkFrame(rec);
    }
    else if (rec.kind === 'sample') {
      counters.samples++;
      counters.max_sample_gap_ms = Math.max(counters.max_sample_gap_ms, rec.n > 1 ? rec.gap_ms : 0);
      samples.push({mono: rec.mono, di: rec.display_identity});
    } else if (rec.kind === 'sample-error') counters.sample_errors++;
    if (rec.queue_dropped) counters.page_queue_dropped = rec.queue_dropped;
    journal.append(rec.kind === 'sample' ? 'sample' : 'page', {since_t0_ms: at, recv, rec},
      {since_t0_ms: at, recv, page_seq: rec.page_seq, send_mono: rec.send_mono, time_origin: rec.time_origin, acks: rec.acks});
  }

  function receiptBrackets() {
    const missing = [];
    let afterStop = 0;
    for (const [seq, m] of receipts.recvBySeq) {
      if (receipts.acked.has(seq)) continue;
      if (receipts.stop_sent_mono === null || m < receipts.stop_sent_mono) missing.push(seq); else afterStop++;
    }
    return {records_received: receipts.recvBySeq.size, acked: receipts.acked.size, missing_before_stop: missing.length,
      missing_first: missing.slice(0, 20), unacked_after_stop_request: afterStop, acks_dropped: receipts.acks_dropped,
      acks_unknown: receipts.acks_unknown, acks_malformed: receipts.acks_malformed, final_acks_from_stop: receipts.final_from_stop,
      final_acks_from_drain: receipts.final_from_drain, stop_sent_mono: receipts.stop_sent_mono};
  }

  async function detail(d, i) {
    if (stopping) return;
    if (counters.request_attempts >= L.max_request_attempts) { requestStop('cap:max_request_attempts', {at: 'detail'}); return; }
    counters.request_attempts++;
    counters.detail_requests++;
    const lib = d.url.startsWith('https:') ? require('https') : require('http');
    const started = sinceT0();
    await new Promise(resolve => {
      const req = lib.request(d.url, {method: 'GET', agent: false, headers: {'accept-encoding': 'identity'}}, res => {
        const chunks = [];
        let bytes = 0;
        const head = Buffer.byteLength(`HTTP/1.1 ${res.statusCode}\r\n` + res.rawHeaders.join(': ') + '\r\n\r\n');
        if (transport.counters.response_bytes + head > L.max_response_bytes) { transport.trip('max_response_bytes', {at: 'detail-head'}); req.destroy(); return resolve(); }
        transport.counters.response_bytes += head;
        res.on('data', c => {
          if (transport.counters.response_bytes + c.length > L.max_response_bytes) { transport.trip('max_response_bytes', {at: 'detail-body'}); req.destroy(); return; }
          transport.counters.response_bytes += c.length;
          bytes += c.length;
          chunks.push(c);
        });
        res.on('end', () => { journal.append('detail', {i, url: d.url, status: res.statusCode, bytes, started, ended: sinceT0(), body: Buffer.concat(chunks).toString('utf8')}); resolve(); });
        res.on('error', e => { journal.append('detail', {i, url: d.url, error: String(e)}); resolve(); });
      });
      req.on('error', e => { journal.append('detail', {i, url: d.url, error: String(e)}); resolve(); });
      req.end();
    });
  }

  function computeCoverage() {
    const mapped = samples.map(s => ({at: clock.docToT0(s.mono), di: s.di})).filter(s => s.at);
    const before = mapped.filter(s => s.at[1] <= contract.SCORING.start_offset_ms);
    const after = mapped.filter(s => s.at[0] >= contract.SCORING.end_offset_ms);
    const inWindow = mapped.filter(s => s.at[1] >= contract.SCORING.start_offset_ms && s.at[0] <= contract.SCORING.end_offset_ms);
    const gaps = [];
    for (let i = 1; i < mapped.length; i++) {
      const a = mapped[i - 1].at, b = mapped[i].at;
      if (b[1] < contract.SCORING.start_offset_ms || a[0] > contract.SCORING.end_offset_ms) continue;
      if (b[1] - a[0] > SAMPLE_GAP_HOLE_MS) gaps.push([a[0], b[1]]);
    }
    const surfaceHoles = {};
    for (const surface of ['headline', 'chart']) {
      const list = [];
      let open = null;
      for (const s of inWindow) {
        const x = s.di && s.di[surface];
        const bad = !x || x.status !== 'present' || !x.visible || (m.page.require_in_viewport && !x.inViewport) || (s.di && s.di.documentVisibility !== 'visible');
        const why = !x ? 'no-sample' : x.status !== 'present' ? x.status : !x.visible ? 'hidden' : (m.page.require_in_viewport && !x.inViewport) ? 'out-of-viewport' : 'document-hidden';
        if (bad && !open) open = {from: s.at[0], to: s.at[1], why, samples: 1};
        else if (bad) { open.to = s.at[1]; open.samples++; }
        else if (open) { list.push(open); open = null; }
      }
      if (open) list.push(open);
      surfaceHoles[surface] = {count: list.length, samples: list.reduce((n, h) => n + h.samples, 0), first: list.slice(0, 20)};
    }
    const streamOutages = [...outages, ...(outage ? [{...outage, to_mono: null}] : [])].map(o => ({...o,
      from_since_t0_ms: clock.docToT0(o.from_mono), to_since_t0_ms: o.to_mono === null ? null : clock.docToT0(o.to_mono)}));
    const inWindowOutages = streamOutages.filter(o => {
      const a = o.from_since_t0_ms, b = o.to_since_t0_ms;
      return a && a[0] <= contract.ACQUISITION.end_offset_ms && (b === null || !b || b[1] >= contract.ACQUISITION.start_offset_ms);
    });
    return {stream_outages: {count: inWindowOutages.length, all: streamOutages.slice(0, 50)}, mapped_samples: mapped.length, unmapped_samples: samples.length - mapped.length,
      start_edge_covered: before.length > 0, end_edge_covered: after.length > 0,
      sample_gaps_over_ms: {threshold: SAMPLE_GAP_HOLE_MS, count: gaps.length, first: gaps.slice(0, 20)},
      surface_holes: surfaceHoles};
  }

  finish = () => {
    if (finishPromise) return finishPromise;
    if (!stopping) stopping = {reason: 'unknown', since_t0_ms: sinceT0()};
    finishPromise = (async () => {
      for (const t of timers) clearTimeout(t);
      const steps = [];
      // A slow close after the window is custody, not an observation fault; it
      // counts toward status only if the browser then survives the kill.
      const teardownFaults = [];
      const bounded = async (label, fn, ms) => {
        let timer;
        try { await Promise.race([fn(), new Promise((_, rej) => { timer = setTimeout(() => rej(new Error('timeout')), ms); })]); steps.push({label, ok: true}); }
        catch (e) { steps.push({label, ok: false, error: String(e)}); (label === 'browser-close' || label === 'challenge-stop' ? teardownFaults : faults).push({kind: 'teardown-step-failed', label, error: String(e)}); }
        finally { clearTimeout(timer); }
      };
      // The challenge stops first: no request leaves after the stop.
      if (challenge) await bounded('challenge-stop', () => challenge.stop(stopping.reason), 2000);
      let queue = null;
      receipts.stop_sent_mono = clock.mono();
      if (page && samplerStarted) await bounded('stop-sampler', async () => { queue = (await page.evaluate(hooks.stopDisplaySampler)).queue; receipts.final_from_stop = noteAcks(queue && queue.acks, queue && queue.acks_dropped); }, 3000);
      if (page) await bounded('clock-end', () => clock.exchange(page, 'end'), 3000);
      let drained = null;
      if (page && samplerStarted) await bounded('drain-acks', async () => { drained = await page.evaluate(hooks.drainRecorderAcks); receipts.final_from_drain = noteAcks(drained && drained.acks, drained && drained.acks_dropped); }, 3000);
      if (page && primaryInstalled) {
        await bounded('primary-export', async () => {
          const data = await page.evaluate(id => { const r = window.__visibleObservationRecorder11434; if (!r || r.captureId !== id) throw new Error('primary recorder missing or replaced'); return r.finish(); }, primaryCaptureId);
          const {entries, ...head} = data;
          const seqOk = Array.isArray(entries) && entries.every((r, i) => r.seq === i + 1);
          for (const e of entries || []) journal.append('primary-transition', {since_t0_ms: clock.docToT0(e.mono), entry: e});
          journal.append('primary-export', {...head, entry_count: (entries || []).length, sequence_ok: seqOk});
          if (!head.captureComplete || !seqOk) fault('primary-export-incomplete', {faults: head.faults, dropped: head.dropped, sequence_ok: seqOk});
        }, 10000);
      } else fault('primary-not-installed');
      if (browser) await bounded('browser-close', () => browser.close(), 20000);
      // Custody: a browser that did not close in time is killed, and the kill is checked.
      const custody = {browser_closed: !steps.some(x => x.label === 'browser-close' && !x.ok), killed: [], remaining: []};
      if (browser && !custody.browser_closed) {
        const kids = () => require('child_process').execFileSync('ps', ['-Ao', 'pid=,ppid=,pgid=,command='], {encoding: 'utf8'})
          .split('\n').map(l => l.trim().split(/\s+/)).filter(r => r.length > 3 && Number(r[1]) === process.pid && /chrom/i.test(r.slice(3).join(' ')));
        for (const r of kids()) { try { process.kill(-Number(r[2]), 'SIGKILL'); } catch { try { process.kill(Number(r[0]), 'SIGKILL'); } catch { /* reported below */ } } custody.killed.push(Number(r[0])); }
        await new Promise(r => setTimeout(r, 500));
        custody.remaining = kids().map(r => Number(r[0]));
        if (custody.remaining.length) fault('browser-survived-teardown', {pids: custody.remaining});
      }
      await bounded('transport-close', () => transport.close(), 5000);
      clearTimeout(hardKill);
      const coverage = computeCoverage();
      const holesFound = [];
      if (!coverage.start_edge_covered) holesFound.push('start-edge-missing');
      if (!coverage.end_edge_covered) holesFound.push('end-edge-missing');
      if (coverage.sample_gaps_over_ms.count) holesFound.push('sample-gaps');
      if (coverage.stream_outages.count) holesFound.push('stream-outage');
      if (coverage.surface_holes.headline.count) holesFound.push('headline-unsupported-or-hidden');
      if (coverage.surface_holes.chart.count) holesFound.push('chart-unsupported-or-hidden');
      if (counters.eventsource_constructions === 0) holesFound.push('no-product-stream');
      for (const t of m.entry.expected_stream_events) if (!seenTypes.has(t)) holesFound.push(`expected-stream-event-missing:${t}`);
      if (queue && (queue.dropped || queue.emit_failures)) holesFound.push('page-queue-loss');
      if (!queue && samplerStarted) holesFound.push('page-queue-unread');
      if (journal.stats.oversize) holesFound.push('oversize-records');
      const brackets = receiptBrackets();
      if (brackets.missing_before_stop) holesFound.push('page-ack-missing');
      if (brackets.acks_dropped) holesFound.push('page-ack-dropped');
      if (brackets.acks_malformed) holesFound.push('page-ack-malformed');
      holes.push(...holesFound);
      const allFaults = [...faults, ...clock.faults];
      const challengeSummary = challenge ? challenge.summary() : inactiveSummary();
      const status = stopping.reason !== 'deadline' ? 'STOPPED' : (allFaults.length || holes.length) ? 'UNRESOLVED' : 'COMPLETE';
      const stop = {status, reason: stopping.reason, detail: stopping.detail || null, stopped_since_t0_ms: stopping.since_t0_ms,
        counters: {...counters, transport: transport.counters, journal: journal.stats, page_queue: queue, page_acks_drained: drained}, limits: L, steps,
        custody: typeof custody === 'undefined' ? null : custody, teardown_faults: teardownFaults};
      const summary = {schema: 'bainluck.passive-case-summary/1', recorder: RECORDER_VERSION, scope, case_id: m.case_id, grant_id: g.grant_id,
        status, reason: stopping.reason, coverage, receipt_brackets: brackets, holes, faults: allFaults.slice(0, 200), fault_count: allFaults.length,
        challenge_status: challengeSummary.status, challenge: challengeSummary,
        fault_kinds: [...new Set(allFaults.map(f => f.kind))].sort(),
        clock: {anchor: clock.anchor, exchanges: clock.exchanges, final_offset_ms: clock.offset},
        browser: {browser_channel: opts['browser-channel'], browser_mode: opts['browser-mode'], playwright_package_sha256: pwPackage.sha256,
          browser_version: browserVersion, granted: gb},
        setup_ready_since_t0_ms: setupReadyAt, streams: Object.fromEntries(streamState), other_eventsources: [...otherStreams], stream_event_types_seen: [...seenTypes].sort(),
        semantics: 'DOM observation, not physical paint. Collector/document mapping only; worker, Redis and DB clocks are not mapped by the page recorder. A page record\'s collector recv is an upper bound on its observation in C; a prior record\'s recv whose page ack precedes this sample\'s read is a lower bound; nothing converts document time to C by a constant. status covers the page case only; challenge_status is the clock challenge\'s own. Unexecuted checks are absent, not passed.'};
      const minimal = minimalForms({status, reason: stopping.reason, holes, fault_kinds: summary.fault_kinds});
      // A STOP or SUMMARY that could not be written is a recorder failure (exit 2), never a result.
      const unwritten = [['STOP.json', stop, minimal.stop], ['SUMMARY.json', summary, minimal.summary]].filter(([name, value, min]) => {
        try { return !journal.writeReserved(name, value, min).written; } catch { return true; }
      }).map(([name]) => name);
      journal.close();
      process.stdout.write(JSON.stringify({status, reason: stopping.reason, out, holes, fault_kinds: summary.fault_kinds,
        ...(unwritten.length ? {recorder_failure: 'reserve-unwritten', unwritten} : {})}) + '\n');
      process.exitCode = unwritten.length ? 2 : status === 'COMPLETE' ? 0 : 1;
    })();
    return finishPromise;
  };

  for (const sig of ['SIGINT', 'SIGTERM']) process.once(sig, () => requestStop('cancelled', {signal: sig}));
  // The watchdog never ends early: Node timers can fire a millisecond before
  // their delay, so it re-arms until the collector clock has reached T0+185 s.
  const watchdog = () => {
    const left = contract.ACQUISITION.end_offset_ms - sinceT0()[0];
    if (left > 0) { timers.push(setTimeout(watchdog, Math.ceil(left))); return; }
    requestStop('deadline');
  };
  watchdog();

  try {
    // Setup may not begin before the manifest's earliest setup edge.
    const wait = W.setup_earliest_wall_ms - clock.wall();
    if (wait > 0) await new Promise(r => timers.push(setTimeout(r, wait)));
    if (stopping) return finish();
    browser = await playwright.chromium.launch({headless: true, handleSIGINT: false, handleSIGTERM: false, handleSIGHUP: false, ...(opts['browser-channel'] === 'chrome' ? {channel: 'chrome'} : {}),
      proxy: {server: `http://127.0.0.1:${proxyPort}`, bypass: '<-loopback>'},
      args: ['--disable-background-networking', '--disable-component-update', '--no-pings', '--disable-domain-reliability', '--disable-sync', '--disable-features=MediaRouter,OptimizationHints', ...BROWSER_MODES[opts['browser-mode']]]});
    journal.append('browser-launch', {mode: opts['browser-mode'], extra_args: BROWSER_MODES[opts['browser-mode']]});
    browserVersion = browser.version();
    journal.append('browser', {version: browserVersion, granted_version: gb.browser_version, since_t0_ms: sinceT0()});
    // A browser build the grant does not name STOPs before any page exists.
    if (browserVersion !== gb.browser_version) {
      fault('browser-version-not-granted', {version: browserVersion, granted: gb.browser_version});
      requestStop('refused:browser-version', {version: browserVersion, granted: gb.browser_version});
      return finish();
    }
    context = await browser.newContext({viewport: m.page.viewport, serviceWorkers: 'block', ignoreHTTPSErrors: scope === 'local'});
    await context.route('**/*', async route => {
      const req = route.request();
      routed.add(req);
      const url = req.url(), method = req.method(), type = req.resourceType();
      let u = null;
      try { u = new URL(url); } catch { /* refused below */ }
      if (u && (u.protocol === 'data:' || u.protocol === 'blob:')) return route.continue();
      const rec = {method, url, type, since_t0_ms: sinceT0()};
      if (stopping) { counters.teardown_refused++; journal.append('request', {...rec, decision: 'refused-teardown'}); return route.abort('blockedbyclient').catch(() => {}); }
      const origin = u && u.origin;
      const grantRoute = u && g.allowed_routes.find(r => r.origin === origin && r.methods.includes(method) && u.pathname.startsWith(r.path_prefix) && (r.resource_types.includes(type) || r.resource_types.includes('*')));
      if (!u || !allowOrigin(origin) || !grantRoute) {
        counters.refused_requests++;
        journal.append('request', {...rec, decision: !u || !allowOrigin(origin) ? 'refused-origin' : 'refused-route'});
        return route.abort('blockedbyclient').catch(() => {});
      }
      if (counters.request_attempts >= L.max_request_attempts) {
        journal.append('request', {...rec, decision: 'refused-cap', cap: 'max_request_attempts'});
        requestStop('cap:max_request_attempts', {attempts: counters.request_attempts, url});
        return route.abort('blockedbyclient').catch(() => {});
      }
      const isStream = isCaseStream(url);
      if (!isStream && type === 'eventsource') counters.other_stream_attempts++;
      if (isStream && counters.stream_attempts >= L.max_stream_attempts) {
        journal.append('request', {...rec, decision: 'refused-cap', cap: 'max_stream_attempts'});
        requestStop('cap:max_stream_attempts', {stream_attempts: counters.stream_attempts});
        return route.abort('blockedbyclient').catch(() => {});
      }
      counters.request_attempts++;
      if (isStream) counters.stream_attempts++;
      counters.methods[method] = (counters.methods[method] || 0) + 1;
      journal.append('request', {...rec, decision: 'allowed', attempt: counters.request_attempts, stream: isStream});
      return route.continue().catch(e => journal.append('request', {...rec, decision: 'continue-failed', error: String(e)}));
    });
    page = await context.newPage();
    page.on('request', req => {
      if (req.redirectedFrom()) {
        counters.redirect_hops++;
        journal.append('redirect-hop', {url: req.url(), from: req.redirectedFrom().url(), routed: routed.has(req), since_t0_ms: sinceT0()});
      }
    });
    // A request the route layer never saw (e.g. a redirect hop) is still an
    // attempt. Checked once the request settles, when routing is certainly done.
    const settle = req => {
      if (routed.has(req) || /^(data|blob):/.test(req.url())) return;
      counters.unrouted_requests++;
      counters.request_attempts++;
      journal.append('request', {method: req.method(), url: req.url(), type: req.resourceType(), decision: 'unrouted-counted', attempt: counters.request_attempts, since_t0_ms: sinceT0()});
      if (counters.request_attempts > L.max_request_attempts) requestStop('cap:max_request_attempts', {at: 'unrouted', url: req.url()});
    };
    page.on('requestfinished', settle);
    page.on('requestfailed', settle);
    page.on('pageerror', e => journal.append('page-error', {message: String(e), since_t0_ms: sinceT0()}));
    page.on('crash', () => { fault('page-crashed'); requestStop('page-crashed'); });
    page.on('close', () => { if (!stopping) { fault('page-closed'); requestStop('page-closed'); } });
    page.on('framenavigated', f => {
      if (f !== page.mainFrame()) return;
      journal.append('navigation', {url: f.url(), since_t0_ms: sinceT0(), after_setup: setupReadyAt !== null});
      if (setupReadyAt !== null) fault('document-navigated-after-setup', {url: f.url()});
    });
    cdp = await context.newCDPSession(page);
    cdp.on('Network.requestWillBeSent', e => requestIds.set(e.requestId, {url: e.request.url, type: e.type}));
    cdp.on('Network.dataReceived', e => {
      const r = requestIds.get(e.requestId);
      const n = e.encodedDataLength || 0;
      counters.cdp_response_bytes += n;
      // Diagnostic only: CDP lags the wire, so this count never stops a run.
      if (r && r.url === streamUrl) counters.cdp_stream_bytes += n;
    });
    await cdp.send('Network.enable');
    await page.exposeFunction('__passiveRecord', onPageRecord);
    await page.addInitScript(hooks.installPassiveEventSourceHook, {binding: '__passiveRecord', maxQueue: L.max_queue_records, maxAcks: PAGE_ACK_PENDING_CAP,
      maxDataChars: L.max_record_bytes, streamEvents: [...new Set([...contract.KNOWN_STREAM_EVENTS, 'message'])]});

    // Drift refuses before network: every pin is re-read immediately before navigation.
    const drift = [];
    for (const ref of pinnedRefs(m)) if (contract.sha256File(ref.path) !== ref.sha256) drift.push(ref.path);
    if (contract.sha256File(opts.manifest) !== v.manifestSha256) drift.push('manifest');
    if (contract.sha256File(opts.grant) !== v.grantSha256) drift.push('grant');
    const again = selfPins();
    for (const f of RECORDER_FILES) if (again.files[f] !== pins.files[f]) drift.push(f);
    if (!again.display_sample.ok) drift.push('display_sample.cjs');
    if (drift.length) { fault('pin-drift-before-navigation', {drift}); requestStop('refused:pin-drift', {drift}); return finish(); }

    const cutoffMs = () => W.setup_cutoff_wall_ms - clock.wall();
    const beforeCutoff = async (label, fn) => {
      const left = cutoffMs();
      if (left <= 0 || stopping) throw Object.assign(new Error(`setup cutoff before ${label}`), {setup: true});
      try { return await fn(left); } catch (e) { if (e && e.name === 'TimeoutError') e.setup = true; throw e; }
    };
    journal.append('setup', {step: 'navigate', since_t0_ms: sinceT0()});
    await beforeCutoff('navigate', left => page.goto(m.entry.page_url, {waitUntil: 'domcontentloaded', timeout: left}));
    await clock.exchange(page, 'after-navigation');
    // Attached, not visible: a hidden or unsupported surface is a recorded hole, never a setup failure.
    await beforeCutoff('hero', left => page.locator('[data-testid="event-hero-probability"]').first().waitFor({state: 'attached', timeout: left}));
    if (m.entry.readout_activation === 'click-live-connection-status') {
      await beforeCutoff('readout', left => page.locator('[data-testid="live-connection-status"] button').first().click({timeout: left}));
    }
    await beforeCutoff('chart', left => page.locator('[data-testid="win-probability-card"]').first().waitFor({state: 'attached', timeout: left}));
    const samplerSrc = fs.readFileSync(DISPLAY_SAMPLE, 'utf8');
    if (contract.sha256(samplerSrc) !== DISPLAY_SAMPLE_SHA256) throw new Error('display_sample.cjs changed during setup');
    await page.evaluate(`(() => { const module = {exports: {}}; ${samplerSrc}\n; window.__readDisplayIdentity10090 = module.exports.readDisplayIdentity10090; })()`);
    primaryCaptureId = require('crypto').randomUUID();
    await page.evaluate(installVisibleObservationRecorder, {captureId: primaryCaptureId});
    primaryInstalled = true;
    const started = await page.evaluate(hooks.startDisplaySampler, {intervalMs: SAMPLE_INTERVAL_MS});
    samplerStarted = true;
    await clock.exchange(page, 'setup-ready');
    setupReadyAt = sinceT0();
    journal.append('setup', {step: 'ready', since_t0_ms: setupReadyAt, sampler: started, cutoff_left_ms: cutoffMs()});
    // Never awaited: a slow or failed connect is a challenge hole, never a setup failure.
    if (challenge) challenge.start().catch(e => fault('challenge-start-error', {error: String(e).slice(0, 300)}));
    if (cutoffMs() < 0) throw Object.assign(new Error('setup completed after the cutoff'), {setup: true});

    // Checkpoints at the acquisition start, T0, every 15 s, and T0+180 s.
    const marks = [contract.ACQUISITION.start_offset_ms, 0];
    for (let t = CHECKPOINT_EVERY_MS; t < contract.SCORING.end_offset_ms; t += CHECKPOINT_EVERY_MS) marks.push(t);
    marks.push(contract.SCORING.end_offset_ms);
    for (const t of marks) timers.push(setTimeout(() => { if (!stopping) clock.exchange(page, `T0${t >= 0 ? '+' : ''}${t}`); }, Math.max(0, t - sinceT0()[0])));
    g.detail_requests.forEach((d, i) => timers.push(setTimeout(() => detail(d, i), Math.max(0, d.at_offset_ms - sinceT0()[0]))));
    if (qualFault && qualFault.kind === 'wall-jump') timers.push(setTimeout(() => { wallSkew.ms = qualFault.ms; journal.append('qualification-fault', {kind: 'wall-jump', ms: qualFault.ms}); }, Math.max(0, qualFault.at_offset_ms - sinceT0()[0])));
    if (qualFault && qualFault.kind === 'cancel') timers.push(setTimeout(() => process.kill(process.pid, 'SIGTERM'), Math.max(0, qualFault.at_offset_ms - sinceT0()[0])));
    await new Promise(resolve => { const t = setInterval(() => { if (stopping) { clearInterval(t); resolve(); } }, 50); });
  } catch (e) {
    // An error raised because a STOP already closed the page is that STOP's consequence.
    if (stopping) fault('interrupted-by-stop', {stop: stopping.reason, error: String(e).slice(0, 500)});
    else {
      fault(e.setup ? 'setup-cutoff' : 'recorder-error', {error: String(e)});
      requestStop(e.setup ? 'setup-cutoff' : 'recorder-error', {error: String(e)});
    }
  }
  return finish();
}

function validate(opts) {
  const required = ['scope', 'manifest', 'manifest-sha256', 'grant', 'grant-sha256'];
  const missing = required.filter(k => !opts[k]);
  const unknown = Object.keys(opts).filter(k => !required.includes(k));
  if (missing.length || unknown.length) return refuse([...missing.map(k => `--${k} required`), ...unknown.map(k => `--${k} unknown`)]);
  const pins = selfPins();
  const v = contract.validateBundle({manifest: opts.manifest, manifestSha256: opts['manifest-sha256'], grant: opts.grant,
    grantSha256: opts['grant-sha256'], scope: opts.scope, now: Date.now()});
  const reasons = [...v.refusals, ...(pins.display_sample.ok ? [] : ['display_sample.cjs drift'])];
  if (reasons.length) return refuse(reasons, {pins});
  process.stdout.write(JSON.stringify({status: 'VALID', network: 'none', scope: opts.scope, case_id: v.manifest.case_id,
    grant_id: v.grant.grant_id, window: v.window, pins}, null, 1) + '\n');
}

if (require.main === module) {
  const {command, opts, error} = parseArgs(process.argv.slice(2));
  if (command === '--help' || command === 'help' || !command) { process.stdout.write(HELP + '\n'); process.exitCode = command ? 0 : 2; }
  else if (error) refuse([error]);
  else if (command === 'validate') validate(opts);
  else if (command === 'record') record(opts).catch(e => { process.stderr.write(String(e && e.stack || e) + '\n'); process.exitCode = 2; });
  else refuse([`unknown command ${command}`]);
}

module.exports = {parseArgs, RECORDER_FILES, DISPLAY_SAMPLE_SHA256};
