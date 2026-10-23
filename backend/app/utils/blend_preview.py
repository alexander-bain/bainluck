"""#10090 — a provisional blend published BEFORE its event stamp commits.

DNPL is the ordinary delivery path for both supported streaming sources.
Every positive event identity may enter the existing eligibility checks; no
operator event list or source activation flag is required. New events are
covered without restarting a worker. The ledger's source/status/revision,
freshness, capacity and owner fences still decide whether a frame may publish.
An ineligible observation retains the committed delivery path.

Why it exists. A held event page only moves when the WS lane's
``UPDATE events SET win_probability_sources = …`` commits. When another
transaction holds that row, every attempt waits out its lock budget, requeues,
and the page shows nothing new until a stamp finally lands. The reading itself
— estimator, orientation, eligibility, weights — was already computed before
the UPDATE. This module lets that reading be shown while persistence keeps
retrying, without pretending it was stored.

The contract (``preview`` frames, never ``probability`` frames):

* A preview frame has NO ``rev``. It is never given a committed revision, so
  it goes out as a plain PUBLISH: never retained, never replayed to a new
  stream, never ordered with committed frames by rev.
* It carries its own identity: ``epoch`` (this process's fence claim, below)
  and ``seq`` (strictly increasing within the epoch).
* ``base_rev`` is the committed ``win_probability_sources_rev`` the preview's
  bag was composed on. A reader shows a preview only while it holds no newer
  committed revision; a newer commit always wins, whoever wrote it.
* ``pending`` names the uncommitted source values folded in. The composed bag
  is the newest committed bag this process knows, with every pending source
  merged by `aggregation.stamp_source_reading` and the aggregate from
  `compute_aggregate_probability`, the same call the committed frame uses.
  That merge is unconditional; the SQL stamp is not (#8910,
  `observation_admits_clause`). So every composition first drops any pending
  source whose reading `reading_regresses_stored_observation` against the
  base it is composed on — the row this arm read, or a sibling's RETURNING —
  so no value the database would refuse as stale is shown while a lock keeps
  the UPDATE from evaluating that clause.
* ``revoke`` frames withdraw a preview: the stamp was refused (a later stored
  observation), the reading disappeared or returned to the stored value, this
  source left the event's group read or was withdrawn, the event left a quote
  status, or the value stayed uncommitted past
  ``LIVE_BLEND_PREVIEW_MAX_UNCOMMITTED_S``. A reader that sees one falls back
  to its committed value.
* The uncommitted limit bounds one value across retries. Expiry leaves a
  per-source marker of the expired value, and the SAME value is not proposed
  again until a commit, a refusal or a different value ends that chain. The
  marker lives in the bounded per-event state (at most one per source), so
  eviction is the only thing that forgets it. It is NOT a cap on how long
  uncommitted values in total may stay on screen during one long hold.

Display authority across processes (the fence). Production runs each venue's
WS arm in its own process (``WS_VENUE_PROCESSES=1``), and a release overlaps
an old worker with its replacement. So exactly ONE source previews, and its
process must own the display before it may publish a blend:

* claim — one atomic script INCRs a global epoch counter and SETs the
  source's owner key to the result (`FENCE_CLAIM_SCRIPT`). A replacement's
  claim therefore supersedes the old worker at Redis, whatever order their
  frames would otherwise arrive in;
* offer — every batch goes through `FENCE_PUBLISH_SCRIPT`, which PUBLISHes a
  blend only while the owner key still holds this process's epoch. A
  superseded process's blends are dropped at Redis and counted as fenced.
  Revokes pass: they only take a provisional value off the page;
* a missing owner key fails closed (no blend is published) — it is never
  re-claimed from inside a running process;
* readers keep a monotonic epoch floor and refuse anything older
  (``frontend/lib/blendPreview.ts``), so an earlier epoch never regains the
  display, not even on a reader that missed the claim.

Cross-writer scope, stated plainly. The other venue's arm and every other
writer (the poll, the matcher, withdrawals) do not preview; their commits
reach the reader as newer committed revisions, which retire any preview
composed on an older base, and the preview arm's next attempt recomposes on
the freshly read row. No pending state is shared between processes.

Two previewing sources (TSP-1, the default shared-ledger path). Both venue processes
write their pending value into ONE per-event ledger inside one Redis hash
(`LEDGER_SCRIPT`), and a frame is composed from the whole ledger and published
only while that exact read-set still stands. The contract, in the order the
script enforces it:

* authority — the hash's ``epoch`` field is the only generation source; a
  missing hash after first use, a malformed field or an exhausted counter
  refuses every operation (previews stop; nothing is re-initialized from
  zero). Readers keep their existing ``(epoch, seq)`` rules: a frame's
  ``epoch`` is the event's ledger generation, its ``seq`` the ledger sequence.
  A write whose event generation is not above the shared counter (any claim
  since — a ledger owner, or the single-source fence after a mode switch —
  may have raised a held reader's floor that high) takes a new generation
  above it, keeping every pending entry and the sequence;
* propose — fenced on the source's owner; ``continue`` needs this owner's
  chain and a newer local sequence and keeps its Redis-clock deadline;
  ``open`` never renews an existing chain; a terminal tombstone refuses any
  proposal read at or below its revision;
* settle — deletes only an entry this owner wrote, through the local sequence
  the stamp carried; a strictly advancing landed commit may renew that owner's
  still-live newer chain. Reproposals, repeated receipts and expired chains
  cannot renew. Progress lives inside the pending payload and retires with it;
  a newer committed base is adopted as the event's floor,
  so a sibling never composes on an older committed bag;
* terminal — a revision-checked tombstone plus one ordered revoke;
* bounded lifecycle — every new-chain admission carries the retirement barrier
  captured BEFORE its authoritative DB graph read. Retirement first commits a
  terminal-only increment of that event's database revision, then atomically
  increments the Redis barrier before deleting event fields. Any fresh future
  context is above the discarded floor; an older prepared context has an old
  barrier and cannot open or recreate a tombstone. The database increment is
  lifecycle ordering only: source values and observation timestamps do not
  change. Active continuations retain their original deadlines. Mixed-version
  owners cannot retire. At 512 events the caller may reread bounded ids and
  retire authoritatively finished rows or idle future-scheduled residents.
  A fresh SHARE/SKIP LOCKED read preserves live, suspended and started or
  undated scheduled rows. Distant starts go first; valid proposals survive.
  The status lock covers an acknowledged reclaim, not an uncertain Redis
  command completing after cancellation. A missing barrier fails closed;
* publish — generation, sequence, tombstone and EVERY contributor's owner and
  original deadline are rechecked at the send; the reader's ``ttl_ms`` is
  computed there, last. Revokes keep the generation and ``through_seq`` they
  were allocated with.

Limits kept explicit: the readers' expiry is still receipt-relative
(``now + ttl_ms``), so delivery delay shifts it. Folded pages accept ledger
frames only when every contributor is elected from the same origin event.
Split-origin folded composition remains unsupported.
"""

from __future__ import annotations

import itertools
import json
import logging
import math
import os
import time
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

SOURCE_ENV = "LIVE_BLEND_PREVIEW_SOURCE"
EVENT_IDS_ENV = "LIVE_BLEND_PREVIEW_EVENT_IDS"
MAX_UNCOMMITTED_ENV = "LIVE_BLEND_PREVIEW_MAX_UNCOMMITTED_S"
#: The arms that may preview (`LiveBlendRefresher.source`).
PREVIEW_SOURCES = frozenset({"kalshi", "polymarket"})
#: How long one uncommitted value may stay on a reader's screen. A concrete
#: product decision, not a measurement; the canary keeps the lab's number.
DEFAULT_MAX_UNCOMMITTED_S = 60.0
#: Latest-per-event state is bounded; the oldest event is revoked past this.
DEFAULT_MAX_EVENTS = 512
#: Statuses a quote stream serves (`routes/event_stream.QUOTE_STATUSES`).
PREVIEW_STATUSES = frozenset({"live", "scheduled", "suspended"})

#: The fence (module doc). One counter for every source, so epochs only rise.
FENCE_EPOCH_KEY = "live:blend_preview:epoch"
FENCE_OWNER_KEY_PREFIX = "live:blend_preview:owner:"
FENCE_CLAIM_SCRIPT = (
    "local epoch = redis.call('INCR', KEYS[1]) "
    "redis.call('SET', KEYS[2], epoch) "
    "return epoch"
)
#: ARGV = epoch, then (kind, channel, payload) per frame, in publication order.
#: Returns {published, fenced, owner-or-empty}.
FENCE_PUBLISH_SCRIPT = (
    "local owner = redis.call('GET', KEYS[1]) "
    "local published, fenced = 0, 0 "
    "for i = 2, #ARGV, 3 do "
    "if ARGV[i] == 'revoke' or owner == ARGV[1] then "
    "redis.call('PUBLISH', ARGV[i + 1], ARGV[i + 2]) published = published + 1 "
    "else fenced = fenced + 1 end "
    "end "
    "return {published, fenced, owner or ''}"
)


#: TSP-1 (module doc): the sources that preview through the shared ledger.
LEDGER_SOURCES_ENV = "LIVE_BLEND_PREVIEW_SOURCES"
LEDGER_KEY = "live:blend_preview:ledger"
#: Set at first initialization: a missing ledger after it is LOST, not new.
LEDGER_MARKER_KEY = "live:blend_preview:ledger:initialized"
#: Replaced by the script with the reader's ttl at the final send.
LEDGER_TTL_TOKEN = '"@@TTL@@"'
LEDGER_MAX_EVENTS = DEFAULT_MAX_EVENTS
#: Lists bigger than this are not stored as a committed floor (it is skipped).
LEDGER_MAX_BASE_BYTES = 262144
#: Refusals that mean the ledger's display authority or admission failed —
#: not supersession (`stale`, `terminal`) or expiry. Each is logged in the
#: fixed `LEDGER_ALARM_FORMAT` so the operator can stop on the first one
#: (#11388 admission review, item 4); the counters alone are never logged.
LEDGER_ALARM_STATUSES = frozenset({"fenced", "lost", "malformed", "exhausted", "full", "no_base"})
#: The operator's matcher keys on this shape; change it only with that matcher.
#: phase = claim, propose, settle, terminal or publish. One line per (status,
#: phase, source) per batch; `count` includes refusals held back since that
#: key's previous line, and `event_id` is the first of them (`-` for a claim).
LEDGER_ALARM_FORMAT = "blend_preview ledger ALARM status=%s phase=%s source=%s count=%d event_id=%s"
#: A persisting refusal repeats its line at most this often per key.
LEDGER_ALARM_INTERVAL_S = 10.0
# KEYS: ledger hash, init marker, shared epoch counter, then the single-source
# owner keys (read only at first initialization). ARGV[1] is the operation.
# Canonical integers: Wee-Bey's reviewed helper (PR #11376 SOURCE-REVIEW).
# Every check precedes the first write; the sequence moves first among the
# writes, so a fault after it still fails every older read-set at PUBLISH.
LEDGER_SCRIPT = r"""
local L, MARK, SHARED = KEYS[1], KEYS[2], KEYS[3]
local op = ARGV[1]
if op == 'revoke' then
  redis.call('PUBLISH', ARGV[2], ARGV[3])
  return {'published'}
end
local MAX = 9007199254740991
local function decimal(n) return string.format('%.0f', n) end
local function uint(s)
  if type(s) ~= 'string' and type(s) ~= 'number' then return nil end
  if type(s) == 'string' then
    if s ~= '0' and not string.match(s, '^[1-9][0-9]*$') then return nil end
    if #s > 16 or (#s == 16 and s > '9007199254740991') then return nil end
  end
  local n = tonumber(s)
  if not n or n < 0 or n > MAX or n % 1 ~= 0 then return nil end
  if type(s) == 'string' and decimal(n) ~= s then return nil end
  return n
end
local BAD = {}
local function field(f)
  local v = redis.call('HGET', L, f)
  if not v then return nil end
  local n = uint(v)
  if n == nil then return BAD end
  return n
end
local function meta(f)
  local v = redis.call('HGET', L, f)
  if not v then return nil end
  local o, c, l, x = string.match(v, '^(%d+) (%d+) (%d+) (%d+)$')
  o, c, l, x = uint(o), uint(c), uint(l), uint(x)
  if not (o and c and l and x) then return BAD end
  return {owner = o, chain = c, lseq = l, expires = x}
end
-- Progress belongs to the existing pending payload, so every old/new delete
-- or replacement also discards it. Never cjson-encode observation numbers:
-- preserve their exact JSON bytes and append one privately-owned final field.
local function progress(raw)
  if not raw then return nil end
  local prefix, o, c, q, r = string.match(raw,
    '^(.*),"_commit_progress":"(%d+) (%d+) (%d+) (%d+)"}$')
  o, c, q, r = uint(o), uint(c), uint(q), uint(r)
  if not (prefix and o and c and q and r) then return nil end
  return {prefix = prefix, owner = o, chain = c, through = q, rev = r}
end
local function progressed(prefix, owner, chain, through, rev)
  return prefix .. ',"_commit_progress":"' .. decimal(owner) .. ' ' .. decimal(chain)
    .. ' ' .. decimal(through) .. ' ' .. decimal(rev) .. '"}'
end
local function shared_floor()
  local v = redis.call('GET', SHARED)
  if not v then return 0 end
  local n = uint(v)
  if n == nil then return BAD end
  return n
end
local function now_ms()
  local t = redis.call('TIME')
  return tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
end
local src = ARGV[2]
local epoch = field('epoch')
if op == 'claim' then
  local shared = shared_floor()
  local retired = field('retired')
  if epoch == BAD or shared == BAD or retired == BAD then return {'malformed'} end
  if retired == nil and (redis.call('HEXISTS', L, 'read_owner:kalshi') == 1
      or redis.call('HEXISTS', L, 'read_owner:polymarket') == 1) then return {'lost_admission'} end
  if epoch == nil then
    if redis.call('EXISTS', MARK) == 1 then return {'lost'} end
    if redis.call('EXISTS', SHARED) == 0 then
      for i = 4, #KEYS do
        if redis.call('EXISTS', KEYS[i]) == 1 then return {'lost'} end
      end
    end
    epoch = 0
  end
  local n = math.max(epoch, shared)
  if n >= MAX then return {'exhausted'} end
  n = n + 1
  redis.call('HSET', L, 'epoch', decimal(n), 'owner:' .. src, decimal(n),
    'read_owner:' .. src, decimal(n))
  if field('retired') == nil then redis.call('HSET', L, 'retired', '0') end
  redis.call('SET', MARK, '1')
  redis.call('SET', SHARED, decimal(n))
  return {'ok', decimal(n)}
end
if epoch == nil then return {'lost'} end
local claim = uint(ARGV[3])
if epoch == BAD or claim == nil then return {'malformed'} end
local sources, owners = {}, {}
for s in string.gmatch(ARGV[5], '%S+') do
  sources[#sources + 1] = s
  local o = field('owner:' .. s)
  if o == BAD then return {'malformed'} end
  owners[s] = o
end
if owners[src] ~= claim then return {'fenced'} end
-- This barrier is bounded, monotonic authority, not an event tombstone cache.
-- Only sources that implement read-before-admit may participate in retirement.
local barrier = field('retired')
if barrier == nil or barrier == BAD then return {'lost_admission'} end
local compatible = true
for _, s in ipairs(sources) do
  if owners[s] == nil or field('read_owner:' .. s) ~= owners[s] then compatible = false end
end
local now = now_ms()
local function stale(s, m) return m.owner ~= owners[s] or m.expires <= now end
if op == 'read_ticket' or op == 'capacity_ticket' then
  local out = {'ok', decimal(barrier)}
  local count = field('nevents')
  if count == BAD then return {'malformed'} end
  local candidates, idle = {}, {}
  if (ARGV[6] == '1' or op == 'capacity_ticket') and (count or 0) >= 512 and compatible then
    -- At capacity only: at most 512 event ids, never base/payload values.
    -- The caller rereads their authoritative DB status before retiring any.
    for _, f in ipairs(redis.call('HKEYS', L)) do
      local id = string.match(f, '^e:(%d+):gen$')
      if id then
        if op == 'read_ticket' then out[#out + 1] = id end
        candidates[#candidates + 1] = id
        local empty = redis.call('HEXISTS', L, 'e:' .. id .. ':term') == 0
        for _, s in ipairs(sources) do
          local m = meta('e:' .. id .. ':m:' .. s)
          if m == BAD or (m ~= nil and not stale(s, m)) then empty = false end
        end
        if empty then idle[#idle + 1] = id end
      end
    end
  end
  if op == 'capacity_ticket' then
    return {'ok', decimal(barrier), cjson.encode(candidates), cjson.encode(idle)}
  end
  return out
end
local P = 'e:' .. ARGV[4] .. ':'
local st = {gen = field(P .. 'gen'), seq = field(P .. 'seq'), term = field(P .. 'term'),
  live = field(P .. 'live'), base_rev = field(P .. 'base_rev'), metas = {}}
for _, k in ipairs({'gen', 'seq', 'term', 'live', 'base_rev'}) do
  if st[k] == BAD then return {'malformed'} end
end
if (st.gen == nil) ~= (st.seq == nil) then return {'malformed'} end
for _, s in ipairs(sources) do
  local m = meta(P .. 'm:' .. s)
  if m == BAD then return {'malformed'} end
  st.metas[s] = m
end
local function readset(status, gen, seq, extra)
  local out = {status, decimal(gen), decimal(seq), decimal(now),
    redis.call('HGET', L, P .. 'base_rev') or '', redis.call('HGET', L, P .. 'base') or '', extra}
  for _, s in ipairs(sources) do
    local m = meta(P .. 'm:' .. s)
    if m and m ~= BAD then
      out[#out + 1] = s
      out[#out + 1] = decimal(m.owner)
      out[#out + 1] = decimal(m.expires)
      out[#out + 1] = redis.call('HGET', L, P .. 'p:' .. s) or ''
    end
  end
  return out
end
local function admit(max_ev)
  -- The event's generation for this write. A shared counter above it means a
  -- claim has been allocated since (a ledger owner, or the single-source fence
  -- after a mode switch): a held reader's floor may be that high, so the write
  -- takes a new generation above it. The sequence keeps rising across it.
  local shared = shared_floor()
  if shared == BAD then return nil, 'malformed' end
  if st.gen ~= nil and shared <= st.gen then return st.gen, st.seq end
  if st.gen == nil then
    local count = field('nevents')
    if count == BAD then return nil, 'malformed' end
    if (count or 0) >= max_ev then return nil, 'full' end
  end
  local n = math.max(epoch, shared)
  if n >= MAX then return nil, 'exhausted' end
  return n + 1, st.seq or 0
end
local function advance(gen, seq)
  if st.gen == nil then redis.call('HINCRBY', L, 'nevents', 1) end
  if gen ~= st.gen then
    redis.call('HSET', L, P .. 'gen', decimal(gen), P .. 'seq', decimal(seq), 'epoch', decimal(gen))
    redis.call('SET', SHARED, decimal(gen))
  else
    redis.call('HSET', L, P .. 'seq', decimal(seq))
  end
end
if op == 'propose' then
  local mode = ARGV[6]
  local chain, lseq, ctx = uint(ARGV[7]), uint(ARGV[8]), uint(ARGV[9])
  local max_ms, max_ev = uint(ARGV[10]), uint(ARGV[11])
  local brev = nil
  if ARGV[13] ~= '' then brev = uint(ARGV[13]); if brev == nil then return {'malformed'} end end
  if not (chain and lseq and ctx and max_ms and max_ev) or ARGV[12] == ''
      or (mode ~= 'open' and mode ~= 'continue') then return {'malformed'} end
  if mode == 'open' and uint(ARGV[15]) ~= barrier then return {'read_required'} end
  if st.gen == nil and mode == 'continue' then return {'missing_chain'} end
  if st.term ~= nil and ctx <= st.term then return {'terminal'} end
  local mine = st.metas[src]
  local expires, expired = nil, false
  if mode == 'continue' then
    if mine == nil or mine.owner ~= claim or mine.chain ~= chain then return {'missing_chain'} end
    if lseq <= mine.lseq then return {'old_local'} end
    expires = mine.expires
    expired = expires <= now
  else
    if mine ~= nil and mine.owner == claim then
      if mine.chain == chain then return {'chain_exists'} end
      if lseq <= mine.lseq then return {'old_local'} end
    end
    expires = now + max_ms
    if expires > MAX then return {'malformed'} end
  end
  local payload = ARGV[12]
  if string.sub(payload, -1) ~= '}' then return {'malformed'} end
  local prior_progress = progress(redis.call('HGET', L, P .. 'p:' .. src))
  if mode == 'open' then
    if chain == 0 then return {'malformed'} end
    payload = progressed(string.sub(payload, 1, -2), claim, chain, chain - 1, ctx)
  elseif prior_progress ~= nil and prior_progress.owner == claim
      and prior_progress.chain == chain then
    payload = progressed(string.sub(payload, 1, -2), claim, chain,
      prior_progress.through, prior_progress.rev)
  end
  local adopt = brev ~= nil and ARGV[14] ~= '' and (st.base_rev == nil or brev > st.base_rev)
  if not adopt and st.base_rev == nil and not expired then return {'no_base'} end
  local gen, seq = admit(max_ev)
  if gen == nil then return {seq} end
  if seq >= MAX then return {'exhausted'} end
  seq = seq + 1
  advance(gen, seq)
  -- @@FAULT:propose
  if adopt then redis.call('HSET', L, P .. 'base_rev', decimal(brev), P .. 'base', ARGV[14]) end
  if expired then
    redis.call('HDEL', L, P .. 'm:' .. src, P .. 'p:' .. src)
  else
    if st.term ~= nil then redis.call('HDEL', L, P .. 'term') end
    if st.live == nil or ctx > st.live then redis.call('HSET', L, P .. 'live', decimal(ctx)) end
    redis.call('HSET', L, P .. 'm:' .. src,
      decimal(claim) .. ' ' .. decimal(chain) .. ' ' .. decimal(lseq) .. ' ' .. decimal(expires),
      P .. 'p:' .. src, payload)
  end
  for _, s in ipairs(sources) do
    local m = st.metas[s]
    if s ~= src and m ~= nil and stale(s, m) then
      redis.call('HDEL', L, P .. 'm:' .. s, P .. 'p:' .. s)
    end
  end
  return readset(expired and 'expired' or 'ok', gen, seq, '')
end
if op == 'settle' then
  local through, brev = nil, nil
  if ARGV[7] ~= '' then through = uint(ARGV[7]); if through == nil then return {'malformed'} end end
  if ARGV[8] ~= '' then brev = uint(ARGV[8]); if brev == nil then return {'malformed'} end end
  if st.gen == nil then return {'none'} end
  local mine = st.metas[src]
  local remove = ARGV[6] == 'settle' and mine ~= nil and mine.owner == claim
    and (through == nil or mine.lseq <= through)
  local mode, chain, max_ms = ARGV[6], nil, nil
  if mode == 'commit' or mode == 'expire' then
    chain = uint(ARGV[10])
    if chain == nil then return {'malformed'} end
  end
  if mode == 'expire' then
    -- An expiry prepared before an accepted renewal cannot withdraw it.
    remove = mine ~= nil and mine.owner == claim and mine.chain == chain
      and through ~= nil and mine.lseq <= through and mine.expires <= now
  end
  local renew, record_progress, progress_value, renewed_expires = false, false, nil, nil
  if mode == 'commit' then
    max_ms = uint(ARGV[11])
    if max_ms == nil or max_ms == 0 or now + max_ms > MAX then return {'malformed'} end
    progress_value = progress(redis.call('HGET', L, P .. 'p:' .. src))
    local own_commit = mine ~= nil and mine.owner == claim and mine.chain == chain
      and not stale(src, mine) and through ~= nil and through >= chain and through < mine.lseq
      and brev ~= nil and ARGV[9] ~= '' and progress_value ~= nil
      and progress_value.owner == claim and progress_value.chain == chain
    renew = own_commit and through > progress_value.through and brev > progress_value.rev
    record_progress = own_commit and (through > progress_value.through or brev > progress_value.rev)
    if renew then renewed_expires = math.max(mine.expires, now + max_ms) end
  end
  local adopt = brev ~= nil and ARGV[9] ~= '' and (st.base_rev == nil or brev > st.base_rev)
  local gone, remaining = {}, 0
  for _, s in ipairs(sources) do
    local m = st.metas[s]
    if m ~= nil and not (remove and s == src) then
      if stale(s, m) then gone[#gone + 1] = s else remaining = remaining + 1 end
    end
  end
  if not remove and not record_progress and #gone == 0 and not (adopt and remaining > 0) then
    if adopt then redis.call('HSET', L, P .. 'base_rev', decimal(brev), P .. 'base', ARGV[9]) end
    if mode == 'expire' then return readset('current', st.gen, st.seq, '') end
    return {'unchanged'}
  end
  local gen, seq = admit(MAX)
  if gen == nil then return {seq} end
  if seq >= MAX then return {'exhausted'} end
  seq = seq + 1
  advance(gen, seq)
  -- @@FAULT:settle
  if adopt then redis.call('HSET', L, P .. 'base_rev', decimal(brev), P .. 'base', ARGV[9]) end
  if renew then
    redis.call('HSET', L, P .. 'm:' .. src,
      decimal(claim) .. ' ' .. decimal(chain) .. ' ' .. decimal(mine.lseq) .. ' ' .. decimal(renewed_expires),
      P .. 'p:' .. src, progressed(progress_value.prefix, claim, chain, through, brev))
  elseif record_progress then
    -- Consume each dimension even when only the other was replayed. A later
    -- crossed pair cannot reuse either receipt to buy another lifetime.
    redis.call('HSET', L, P .. 'p:' .. src, progressed(progress_value.prefix, claim, chain,
      math.max(through, progress_value.through), math.max(brev, progress_value.rev)))
  end
  if remove then redis.call('HDEL', L, P .. 'm:' .. src, P .. 'p:' .. src) end
  for _, s in ipairs(gone) do redis.call('HDEL', L, P .. 'm:' .. s, P .. 'p:' .. s) end
  return readset('ok', gen, seq, remove and '1' or '0')
end
if op == 'terminal' then
  if compatible and uint(ARGV[8]) ~= barrier then return {'read_required'} end
  local ctx, max_ev = uint(ARGV[6]), uint(ARGV[7])
  if not (ctx and max_ev) then return {'malformed'} end
  if st.term ~= nil and st.term >= ctx then return {'unchanged'} end
  if st.live ~= nil and ctx < st.live then return {'stale_terminal'} end
  local gen, seq = admit(max_ev)
  if gen == nil then return {seq} end
  if seq >= MAX then return {'exhausted'} end
  seq = seq + 1
  advance(gen, seq)
  -- @@FAULT:terminal
  redis.call('HSET', L, P .. 'term', decimal(ctx))
  for _, s in ipairs(sources) do redis.call('HDEL', L, P .. 'm:' .. s, P .. 'p:' .. s) end
  return {'ok', decimal(gen), decimal(seq)}
end
-- Eligible rows may release idle residency without becoming terminal.
if op == 'retire_idle' then
  local ctx, ticket = uint(ARGV[6]), uint(ARGV[7])
  if not ctx or not ticket then return {'malformed'} end
  if not compatible then return {'legacy_owner'} end
  if ticket ~= barrier then return {'read_required'} end
  if st.gen == nil then return {'none'} end
  -- Terminal rows retain their durable revision-advance path.
  if st.term ~= nil then return {'terminal'} end
  if st.live ~= nil and ctx < st.live then return {'stale_terminal'} end
  if st.base_rev ~= nil and ctx < st.base_rev then return {'stale_terminal'} end
  -- Dead metadata follows the existing owner/deadline pruning rule.
  -- A live renewal/proposal wins atomically and refuses this reclamation.
  for _, s in ipairs(sources) do
    if st.metas[s] ~= nil and not stale(s, st.metas[s]) then return {'pending'} end
  end
  if barrier >= MAX then return {'exhausted'} end
  local count = field('nevents')
  if count == BAD or count == nil or count < 1 then return {'malformed'} end
  local gen, seq = admit(MAX)
  if gen == nil then return {seq} end
  if seq >= MAX then return {'exhausted'} end
  seq = seq + 1
  redis.call('HSET', L, 'retired', decimal(barrier + 1))
  advance(gen, seq)
  -- If a subsequent write faults, sequence already invalidates old readsets.
  redis.call('HDEL', L, P .. 'gen', P .. 'seq', P .. 'live',
    P .. 'base_rev', P .. 'base')
  for _, s in ipairs(sources) do
    redis.call('HDEL', L, P .. 'm:' .. s, P .. 'p:' .. s)
  end
  redis.call('HINCRBY', L, 'nevents', -1)
  return {'ok', decimal(gen), decimal(seq)}
end
if op == 'retire' or op == 'retire_missing' then
  local ctx, ticket, durable
  if op == 'retire_missing' then
    -- The caller proved absence in a fresh DB statement AFTER this ticket.
    -- No durable row remains to increment. The global barrier invalidates
    -- every prepared open from before deletion, including other producers.
    ticket = uint(ARGV[6])
    ctx = math.max(st.live or 0, st.term or 0, st.base_rev or 0)
    if not ticket then return {'malformed'} end
  else
    ctx, ticket, durable = uint(ARGV[6]), uint(ARGV[7]), uint(ARGV[8])
    if not ctx or not ticket or not durable or durable ~= ctx + 1 then return {'malformed'} end
  end
  if not compatible then return {'legacy_owner'} end
  if ticket ~= barrier then return {'read_required'} end
  if st.live ~= nil and ctx < st.live then return {'stale_terminal'} end
  if st.term ~= nil and ctx < st.term then return {'stale_terminal'} end
  if st.base_rev ~= nil and ctx < st.base_rev then return {'stale_terminal'} end
  if barrier >= MAX then return {'exhausted'} end
  local count = field('nevents')
  if count == BAD or (st.gen ~= nil and (count == nil or count < 1)) then
    return {'malformed'}
  end
  local gen, seq = nil, nil
  if st.gen ~= nil then
    gen, seq = admit(MAX)
    if gen == nil then return {seq} end
    if seq >= MAX then return {'exhausted'} end
    seq = seq + 1
  end
  -- Invalidate every old open BEFORE removing its last event-local guard.
  -- Active continuations are unchanged; absent chains cannot continue.
  redis.call('HSET', L, 'retired', decimal(barrier + 1))
  if gen == nil then return {'none'} end
  advance(gen, seq)
  redis.call('HSET', L, P .. 'term', decimal(ctx))
  -- @@FAULT:retire
  redis.call('HDEL', L, P .. 'gen', P .. 'seq', P .. 'term', P .. 'live',
    P .. 'base_rev', P .. 'base')
  for _, s in ipairs(sources) do
    redis.call('HDEL', L, P .. 'm:' .. s, P .. 'p:' .. s)
  end
  redis.call('HINCRBY', L, 'nevents', -1)
  return {'ok', decimal(gen), decimal(seq)}
end
if op == 'publish' then
  local gen, seq = uint(ARGV[6]), uint(ARGV[7])
  if not (gen and seq) or #ARGV < 12 or (#ARGV - 9) % 3 ~= 0 then return {'malformed'} end
  if st.gen ~= gen or st.seq ~= seq then return {'stale'} end
  if st.term ~= nil then return {'terminal'} end
  local least = nil
  for i = 10, #ARGV, 3 do
    local s, o, x = ARGV[i], uint(ARGV[i + 1]), uint(ARGV[i + 2])
    local m = st.metas[s]
    if m == nil or o == nil or x == nil or m.owner ~= o or owners[s] ~= o
        or m.expires ~= x or x <= now then return {'contributor'} end
    if least == nil or x < least then least = x end
  end
  local token = '"@@TTL@@"'
  local a, b = string.find(ARGV[9], token, 1, true)
  if not a or string.find(ARGV[9], token, b + 1, true) then return {'malformed'} end
  local ttl = least - now
  redis.call('PUBLISH', ARGV[8], string.sub(ARGV[9], 1, a - 1) .. decimal(ttl) .. string.sub(ARGV[9], b + 1))
  return {'published', decimal(ttl)}
end
return {'malformed'}
"""


def fence_owner_key(source: str) -> str:
    return FENCE_OWNER_KEY_PREFIX + source


def ledger_keys() -> tuple:
    return (LEDGER_KEY, LEDGER_MARKER_KEY, FENCE_EPOCH_KEY,
            *(fence_owner_key(name) for name in sorted(PREVIEW_SOURCES)))


class PreviewEventScope:
    """Stateless admission to preview validation, not a set of enrolled events.

    Membership only establishes a valid event identity. The existing graph,
    source, freshness and ledger checks still establish publication eligibility.
    Deliberately not iterable: callers must supply a finite batch to select.
    """

    def __contains__(self, event_id: object) -> bool:
        return type(event_id) is int and 0 < event_id <= 9007199254740991

    def isdisjoint(self, event_ids) -> bool:
        return not any(event_id in self for event_id in event_ids)


_ALL_PREVIEW_EVENTS = PreviewEventScope()


def ledger_sources() -> frozenset:
    """Both streaming sources share one fenced ledger in ordinary operation."""
    return PREVIEW_SOURCES


def preview_source() -> Optional[str]:
    """There is no single-source activation mode in ordinary delivery."""
    return None


def preview_events_for(source: str) -> PreviewEventScope | frozenset:
    """Admit supported sources to validation for every arriving event."""
    return _ALL_PREVIEW_EVENTS if source in PREVIEW_SOURCES else frozenset()


def preview_route_events() -> PreviewEventScope:
    """All event streams may forward eligible, client-compatible previews."""
    return _ALL_PREVIEW_EVENTS


def _max_uncommitted_s() -> float:
    try:
        value = float(os.environ.get(MAX_UNCOMMITTED_ENV, DEFAULT_MAX_UNCOMMITTED_S))
    except ValueError:
        return DEFAULT_MAX_UNCOMMITTED_S
    return value if value > 0 else DEFAULT_MAX_UNCOMMITTED_S


def _revision(value: Any) -> Optional[int]:
    return value if type(value) is int and value >= 0 else None


def _basis_observation_time(basis: Any) -> Optional[datetime]:
    """Date a complete contributing reading, never a persistence retry.

    The minimum is the existing oldest_observation_time contract. Reject an
    incomplete vector in full; filtering bad legs would overstate freshness.
    """
    if not isinstance(basis, dict) or not basis:
        return None
    if any(type(value) not in (int, float) or not math.isfinite(value)
           for value in basis.values()):
        return None
    try:
        return datetime.fromtimestamp(min(basis.values()), timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


@dataclass
class _Pending:
    value: float
    eligibility: Any
    observed_basis: Optional[dict]
    stamped_at: datetime
    seq: int
    #: Monotonic start of this source's uncommitted chain (kept across
    #: re-proposals until a commit, refusal or expiry ends the chain).
    since: float


@dataclass
class _EventState:
    status: Optional[str] = None
    espn_win_prob_home: Any = None
    opening_home_probability: Any = None
    base_sources: Optional[dict] = None
    base_rev: Optional[int] = None
    pending: dict = field(default_factory=dict)
    #: source -> the value whose uncommitted chain expired. Not proposed again
    #: until a commit, a refusal or a different value ends the chain.
    expired: dict = field(default_factory=dict)
    #: Ledger-only sequence of an expired reading. A delayed older commit
    #: cannot clear that newer reading's same-value tombstone. Event-bounded.
    expired_through: dict = field(default_factory=dict)
    #: Highest seq this process published for the event (blend or revoke).
    last_seq: int = 0
    #: Highest ``through_seq`` of a revoke this process has sent for the event.
    revoked_through: int = 0


class PreviewRegistry:
    """Bounded latest-per-event pending state for one process (one fence epoch)."""

    def __init__(
        self,
        *,
        max_events: int = DEFAULT_MAX_EVENTS,
        max_uncommitted_s: Optional[float] = None,
        clock: Callable[[], float] = time.monotonic,
        epoch: Optional[int] = None,
    ) -> None:
        #: This process's fence claim; None until `_publish_previews` claims.
        self.epoch = epoch
        self.claim_lock: Any = None
        self.max_events = max_events
        self.max_uncommitted_s = (
            _max_uncommitted_s() if max_uncommitted_s is None else max_uncommitted_s
        )
        self._clock = clock
        self._seq = itertools.count(1)
        self._events: "OrderedDict[int, _EventState]" = OrderedDict()

    # ── state ────────────────────────────────────────────────────────────
    def _state(self, event_id: int) -> _EventState:
        state = self._events.get(event_id)
        if state is None:
            state = self._events[event_id] = _EventState()
        self._events.move_to_end(event_id)
        return state

    def _context(self, state: _EventState, event: Any) -> None:
        state.status = getattr(event, "status", None)
        state.espn_win_prob_home = getattr(event, "espn_win_prob_home", None)
        state.opening_home_probability = getattr(event, "opening_home_probability", None)

    def _adopt_base(self, state: _EventState, sources: Any, rev: Any) -> None:
        rev = _revision(rev)
        if rev is None or not isinstance(sources, dict):
            return
        if state.base_rev is None or rev > state.base_rev:
            state.base_rev = rev
            state.base_sources = dict(sources)

    def has_pending(self, event_id: int, source: Optional[str] = None) -> bool:
        state = self._events.get(event_id)
        if state is None:
            return False
        return bool(state.pending) if source is None else source in state.pending

    def pending_seq(self, event_id: int, source: str) -> Optional[int]:
        state = self._events.get(event_id)
        entry = state.pending.get(source) if state is not None else None
        return None if entry is None else entry.seq

    # ── composition ──────────────────────────────────────────────────────
    def _drop_regressed(self, state: _EventState) -> list[str]:
        """Drop each pending source the SQL stamp would refuse as stale (#8910).

        The base may be the row this arm read or a sibling's RETURNING; either
        can carry a later observation of the same rows (the poll or the
        matcher committed one), and under a row lock the UPDATE never gets to
        refuse it.
        """
        from app.utils.aggregation import reading_regresses_stored_observation

        stale = [name for name, entry in state.pending.items()
                 if reading_regresses_stored_observation(
                     state.base_sources, name, entry.observed_basis)]
        for name in stale:
            del state.pending[name]
        return stale

    def _compose(self, event_id: int, state: _EventState, source: str) -> Optional[dict]:
        # Every composition is guarded here; callers that need to say WHY a
        # preview went away drop first themselves (a second pass finds none).
        self._drop_regressed(state)
        if (state.base_rev is None or state.status not in PREVIEW_STATUSES
                or not state.pending):
            return None

        def ttl_ms():
            now = self._clock()
            oldest = min(entry.since for entry in state.pending.values())
            return max(0, int((self.max_uncommitted_s - (now - oldest)) * 1000))

        def next_seq():
            seq = next(self._seq)
            state.last_seq = seq
            return seq

        return _composed_frame(event_id, state, source, epoch=self.epoch,
                               ttl_ms=ttl_ms, next_seq=next_seq)

    # ── claims (one per process here; one per source in the ledger) ────────
    ledger = False

    def unclaimed(self, source: str) -> bool:
        return self.epoch is None

    def claim_of(self, source: str) -> Optional[int]:
        return self.epoch

    def withdrawn(self, frame: dict) -> bool:
        """A queued blend that a revoke this process already sent withdrew.

        Frames are composed before the publication lock and sent in lock
        order, so a batch that waited can hold a blend older than a revoke
        another batch sent meanwhile. A reader holding nothing keeps no
        memory of the withdrawn sequence, so that blend would show again.
        """
        state = self._events.get(frame["event_id"])
        preview = frame["preview"]
        return (state is not None and preview["kind"] == "blend"
                and preview["seq"] <= state.revoked_through)

    def sending(self, frame: dict) -> None:
        """Record a revoke before its send; an unknown outcome still withdrew."""
        state = self._events.get(frame["event_id"])
        preview = frame["preview"]
        if state is not None and preview["kind"] == "revoke":
            state.revoked_through = max(state.revoked_through, preview["through_seq"])

    def _revoke_frame(self, event_id: int, state: _EventState, reason: str) -> Optional[dict]:
        if state.last_seq == 0:
            return None  # nothing was ever published for this event
        through = state.last_seq
        seq = next(self._seq)
        state.last_seq = seq
        return {
            "event_id": int(event_id),
            "p": None,
            "status": state.status,
            "provisional": True,
            "preview": {
                "kind": "revoke",
                "epoch": self.epoch,
                "seq": seq,
                "through_seq": through,
                "reason": reason,
            },
        }

    def _after_drop(self, event_id: int, state: _EventState, reason: str,
                    source: str) -> list[dict]:
        """A pending source left: recompose the rest, or revoke the event."""
        if self._drop_regressed(state) and not state.pending:
            reason = "stale"
        if state.pending:
            frame = self._compose(event_id, state, source)
            if frame is not None:
                return [frame]
            state.pending.clear()
        frame = self._revoke_frame(event_id, state, reason)
        return [] if frame is None else [frame]

    def _terminal(self, event_id: int, state: _EventState, row_rev: Any,
                  source: str) -> list[dict]:
        state.pending.clear()
        state.expired.clear()
        frame = self._revoke_frame(event_id, state, "terminal")
        return [] if frame is None else [frame]

    def _admit(self, event_id: int, state: _EventState, source: str, value: float, *,
               eligibility: Any, observed_basis: Optional[dict],
               stamped_at: Optional[datetime], row_sources: Any, row_rev: Any) -> list[dict]:
        prior = state.pending.get(source)
        now = self._clock()
        state.pending[source] = _Pending(
            value=value, eligibility=eligibility,
            observed_basis=dict(observed_basis) if observed_basis else None,
            stamped_at=stamped_at or datetime.now(timezone.utc),
            seq=0, since=prior.since if prior is not None else now,
        )
        stale = self._drop_regressed(state)
        frame = self._compose(event_id, state, source)
        if frame is None:
            if stale:
                # Nothing left that the database would keep: whatever this
                # event showed may not stay up on a refused value.
                state.pending.clear()
                revoke = self._revoke_frame(event_id, state, "stale")
                return [] if revoke is None else [revoke]
            state.pending.pop(source, None)
            return []
        entry = state.pending.get(source)
        if entry is not None:
            entry.seq = frame["preview"]["seq"]
        return [frame, *self._evict()]

    # ── writer API ───────────────────────────────────────────────────────
    def propose(
        self, event_id: int, source: str, *, value: float, event: Any,
        row_sources: Any, row_rev: Any, eligibility: Any = None,
        observed_basis: Optional[dict] = None, stamped_at: Optional[datetime] = None,
        observation_only: bool = False,
    ) -> list[dict]:
        """A reading passed every check and is about to be persisted.

        Returns the frames to publish now: one preview, or a revoke when the
        event left a quote status / cannot be ordered against a revision.
        """
        state = self._state(event_id)
        self._context(state, event)
        self._adopt_base(state, row_sources, row_rev)
        if state.status not in PREVIEW_STATUSES:
            return self._terminal(event_id, state, row_rev, source)
        value = float(value)
        if observation_only:
            from app.utils.aggregation import parse_source_entry, stamp_source_reading
            from app.utils.probability_eligibility import is_refused

            observed = _basis_observation_time(observed_basis)
            stored_value, stored_at = parse_source_entry((state.base_sources or {}).get(source))
            entry = stamp_source_reading(
                state.base_sources or {}, source, value, eligibility=eligibility,
                observed_basis=observed_basis,
            )[source]
            if (observed is None or stored_at is None or stored_value is None
                    or round(stored_value, 4) != value or is_refused(entry)):
                return self.refused(event_id, source, "unobserved")
            prior = state.pending.get(source)
            if observed <= stored_at:
                # The periodic row clock can precede a newer accepted quote.
                # It supplies no new observation, not a source withdrawal. In
                # particular, do not clear an expired same-value chain here.
                if prior is None:
                    return []
                previous = prior.observed_basis
                previous_at = _basis_observation_time(previous)
                if (prior.value == value and previous_at is not None
                        and previous_at > stored_at
                        and set(previous) == set(observed_basis)
                        and all(observed_basis[key] <= seen for key, seen in previous.items())):
                    expired = self.expire()
                    if self._drop_regressed(state):
                        expired.extend(self._after_drop(event_id, state, "stale", source))
                    return expired
                return self.refused(event_id, source, "unobserved")
            if prior is not None:
                previous = prior.observed_basis
                previous_at = _basis_observation_time(previous)
                # A duplicate/frozen leg or regressed sibling may not fabricate
                # a newer whole reading. The existing display keeps its original
                # deadline; a fresh proof never reopens an expired value below.
                if (previous_at is None or set(previous) != set(observed_basis)
                        or any(observed_basis[key] < seen for key, seen in previous.items())
                        or observed <= previous_at):
                    if self._drop_regressed(state):
                        return self._after_drop(event_id, state, "stale", source)
                    return []
        if source in state.expired:
            if state.expired[source] == value:
                # The same value outlived the limit and is still uncommitted:
                # a retry may not open it a fresh lifetime.
                return []
            del state.expired[source]  # a different value: a new chain
        return self._admit(event_id, state, source, value, eligibility=eligibility,
                           observed_basis=observed_basis, stamped_at=stamped_at,
                           row_sources=row_sources, row_rev=row_rev)

    def committed(
        self, event_id: int, source: str, *, seq: Optional[int], sources: Any,
        rev: Any, event: Any = None,
    ) -> list[dict]:
        """This source's stamp COMMITTED (``sources``/``rev`` from RETURNING).

        The pending value the attempt previewed is retired; any other source
        still pending is recomposed on the new committed base so the reader's
        newer revision does not drop it.
        """
        state = self._events.get(event_id)
        if state is None:
            return []
        if event is not None:
            self._context(state, event)
        self._adopt_base(state, sources, rev)
        # This source's newest reading is now stored. A pending value from this
        # attempt (or an earlier one) is retired; only a later proposal of the
        # same source — one this commit does not carry — stays pending.
        state.expired.pop(source, None)
        entry = state.pending.get(source)
        if entry is not None and (seq is None or entry.seq <= seq):
            del state.pending[source]
        if not state.pending:
            return []
        # A sibling still pending is recomposed on the RETURNING base, which
        # may hold a later observation of its rows: `_after_drop` refuses it.
        return self._after_drop(event_id, state, "unorderable", source)

    def refused(self, event_id: int, source: str, reason: str) -> list[dict]:
        """This source's pending value no longer stands (see module doc)."""
        state = self._events.get(event_id)
        if state is None:
            return []
        state.expired.pop(source, None)
        if source not in state.pending:
            return []
        del state.pending[source]
        return self._after_drop(event_id, state, reason, source)

    def expire(self) -> list[dict]:
        """Revoke every source whose value stayed uncommitted too long."""
        now = self._clock()
        frames: list[dict] = []
        for event_id, state in list(self._events.items()):
            stale = [name for name, entry in state.pending.items()
                     if now - entry.since >= self.max_uncommitted_s]
            if not stale:
                continue
            for name in stale:
                state.expired[name] = state.pending.pop(name).value
            frames.extend(self._after_drop(event_id, state, "expired", stale[0]))
        return frames

    def _evict(self) -> list[dict]:
        frames: list[dict] = []
        while len(self._events) > self.max_events:
            event_id, state = self._events.popitem(last=False)
            if state.pending:
                state.pending.clear()
                frame = self._revoke_frame(event_id, state, "evicted")
                if frame is not None:
                    frames.append(frame)
        return frames


def _composed_frame(event_id: int, state: _EventState, source: str, *, epoch: Any,
                    ttl_ms: Callable[[], Any], next_seq: Callable[[], int]) -> Optional[dict]:
    """The preview frame for ``state``'s pending values, or None (no aggregate).

    ``ttl_ms`` and ``next_seq`` are called only once the aggregate exists, in
    that order: the single-source registry spends a sequence only on a frame.
    """
    from app.utils.aggregation import compute_aggregate_probability, stamp_source_reading

    bag = dict(state.base_sources or {})
    for name, entry in state.pending.items():
        bag = stamp_source_reading(
            bag, name, entry.value, now=entry.stamped_at,
            eligibility=entry.eligibility, observed_basis=entry.observed_basis,
        )
    shim = SimpleNamespace(
        win_probability_sources=bag,
        status=state.status,
        espn_win_prob_home=state.espn_win_prob_home,
        opening_home_probability=state.opening_home_probability,
    )
    probability = compute_aggregate_probability(shim, state.status)
    if probability is None:
        return None
    ttl = ttl_ms()
    seq = next_seq()
    mover = state.pending.get(source) or next(iter(state.pending.values()))
    # A separate clock-only view preserves the probability/weighting bag
    # exactly. Pending stamps above are attempt times, not observations.
    # Committed siblings retain the clocks of this exact base revision.
    from app.utils.aggregation import newest_source_reading_time

    clock_bag = dict(bag)
    for name, entry in state.pending.items():
        observed = _basis_observation_time(entry.observed_basis)
        clock_bag[name] = {
            **bag[name],
            "updated_at": observed.isoformat() if observed is not None else None,
        }
    display_time = newest_source_reading_time(
        SimpleNamespace(win_probability_sources=clock_bag, status=state.status),
        state.status, require_complete=True,
    )
    # Folded readers need the exact policy inputs, not this row's scalar
    # aggregate. Round-trip a strict JSON copy so retained frame metadata
    # cannot alias the registry's committed base. Invalid legacy metadata
    # leaves singleton behavior intact and gives folded readers no claim.
    pending_entries = None
    try:
        pending_entries = json.loads(json.dumps(
            {name: bag[name] for name in sorted(state.pending)},
            allow_nan=False,
        ))
    except (TypeError, ValueError):
        pass
    return {
        "event_id": int(event_id),
        "p": float(probability),
        "status": state.status,
        "source": source,
        "source_value": float(mover.value),
        "observed_at": mover.stamped_at.isoformat(),  # legacy attempt clock
        # Additive contract: readers must not fall back to observed_at.
        "display_observed_at": display_time.isoformat() if display_time else None,
        "provisional": True,
        "preview": {
            "kind": "blend",
            "epoch": epoch,
            "seq": seq,
            "base_rev": state.base_rev,
            "ttl_ms": ttl,
            "pending": {name: float(e.value) for name, e in sorted(state.pending.items())},
            "pending_entries_version": 1,
            "pending_entries": pending_entries,
        },
    }


class _StoredEligibility:
    """An eligibility record carried through the ledger as its stored entry."""

    def __init__(self, entry: dict) -> None:
        self._entry = entry

    def to_entry(self) -> dict:
        return json.loads(json.dumps(self._entry))


def _ledger_text(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


class LedgerRegistry(PreviewRegistry):
    """TSP-1: this process's half of the shared per-event ledger (module doc).

    Local state keeps only this process's own chains — value, observation
    basis, local sequence, chain id, and the expired-value marker — for the
    existing gating. Every writer call returns ledger OPERATIONS, never frames;
    `execute`/`prepare` run them against Redis under the caller's connection,
    compose from the read-set each returns and publish through the CAS.
    """

    ledger = True

    def __init__(self, *, sources: frozenset, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.sources = tuple(sorted(PREVIEW_SOURCES))
        self.ledger_sources = frozenset(sources)
        self.claims: dict[str, int] = {}
        self._chains: dict[tuple[int, str], int] = {}
        self._dropped: list[tuple[str, int]] = []
        #: (status, phase, source) -> (refusals not yet logged, first event id).
        self._alarm_owed: dict[tuple[str, str, str], tuple[int, Optional[int]]] = {}
        self._alarm_last: dict[tuple[str, str, str], float] = {}
        self._alarm_batch_open = False

    def unclaimed(self, source: str) -> bool:
        return source not in self.claims

    def claim_of(self, source: str) -> Optional[int]:
        return self.claims.get(source)

    async def read_ticket(self, call, source: str, *, include_candidates: bool = False) -> tuple[Optional[int], list[int]]:
        """Capture before the caller's fresh READ COMMITTED statement.

        Never call this around an already prepared/cached graph. A refused
        ticket does not prevent committed delivery or active continuations.
        """
        claim = self.claims.get(source)
        if claim is None:
            return None, []
        reply = await self._eval(call, "read_ticket", source, claim, "", " ".join(self.sources),
                                 int(include_candidates))
        if reply[0] != "ok":
            return None, []
        return int(reply[1]), [int(eid) for eid in reply[2:]]

    async def capacity_ticket(self, call, source: str) -> tuple[Optional[int], list[int], set[int]]:
        """One bounded resident/idle hint, before the maintenance DB statement.

        The idle hint never authorizes deletion: retire_idle checks it again.
        Ordinary admission keeps read_ticket's unchanged lightweight response.
        """
        claim = self.claims.get(source)
        if claim is None:
            return None, [], set()
        reply = await self._eval(call, "capacity_ticket", source, claim, "", " ".join(self.sources))
        if reply[0] != "ok":
            return None, [], set()
        return int(reply[1]), [int(eid) for eid in json.loads(reply[2])], {
            int(eid) for eid in json.loads(reply[3])}

    def retire_idle(self, event_id: int, source: str, rev: int, ticket: int) -> dict:
        """Locked fresh future-scheduled DB proof for a resident with no valid pending metadata."""
        return {"ledger_op": "retire_idle", "event_id": int(event_id), "source": source,
                "ctx_rev": rev, "read_ticket": ticket}

    def propose(self, event_id: int, source: str, **kwargs: Any) -> list[dict]:
        ticket = getattr(kwargs["event"], "preview_read_ticket", None)
        state = self._events.get(event_id)
        # No fresh ticket: do not start a local chain we could never admit.
        if ticket is None and (state is None or source not in state.pending):
            return []
        ops = super().propose(event_id, source, **kwargs)
        # Terminal/refused observations also allocate context before returning.
        # Keep those paths bounded and settle any displaced pending chains.
        ops.extend(self._evict())
        for op in ops:
            if op.get("ledger_op") in ("propose", "terminal"):
                op["read_ticket"] = ticket
        return ops

    def retire_read(self, event_id: int, source: str, rev: int, ticket: int, *,
                    committed_rev: int) -> dict:
        """After terminal-only DB revision advance COMMITTED (rev -> rev+1).

        The next authoritative reader must therefore read above the deleted
        floor even if status later reopens without changing the source bag.
        Ticket precedes the proof transaction, never wraps old cached state.
        """
        return {"ledger_op": "retire", "event_id": int(event_id), "source": source,
                "ctx_rev": rev, "read_ticket": ticket, "committed_rev": committed_rev}

    def retire_missing(self, event_id: int, source: str, ticket: int) -> dict:
        """Only after a fresh authoritative DB statement proved row absence."""
        return {"ledger_op": "retire_missing", "event_id": int(event_id),
                "source": source, "read_ticket": ticket}

    # ── local bookkeeping → operations ──────────────────────────────────
    @staticmethod
    def _base(sources: Any, rev: Any, state: _EventState) -> tuple:
        rev = _revision(rev)
        if rev is None or not isinstance(sources, dict):
            return None, None
        try:
            text = json.dumps({
                "sources": sources, "status": state.status,
                # SQL Numeric columns arrive as Decimal, unlike JSONB source
                # values. Encode these scalars numerically, never as strings.
                "espn_win_prob_home": (float(state.espn_win_prob_home)
                                      if isinstance(state.espn_win_prob_home, Decimal)
                                      else state.espn_win_prob_home),
                "opening_home_probability": (float(state.opening_home_probability)
                                             if isinstance(state.opening_home_probability, Decimal)
                                             else state.opening_home_probability),
            }, allow_nan=False, sort_keys=True)
        except (TypeError, ValueError):
            return None, None
        return (rev, text) if len(text) <= LEDGER_MAX_BASE_BYTES else (None, None)

    def _settle_op(self, event_id: int, source: str, through: Optional[int], reason: str,
                   base: tuple = (None, None)) -> dict:
        return {"ledger_op": "settle", "mode": "settle", "event_id": int(event_id),
                "source": source, "through": through, "reason": reason,
                "base_rev": base[0], "base": base[1]}

    def _forget(self, event_id: int, source: str) -> Optional[_Pending]:
        state = self._events.get(event_id)
        self._chains.pop((event_id, source), None)
        return None if state is None else state.pending.pop(source, None)

    def _drop_regressed(self, state: _EventState) -> list[str]:
        from app.utils.aggregation import reading_regresses_stored_observation

        stale = [name for name, entry in state.pending.items()
                 if reading_regresses_stored_observation(
                     state.base_sources, name, entry.observed_basis)]
        for name in stale:
            self._dropped.append((name, state.pending.pop(name).seq))
        return stale

    def _after_drop(self, event_id: int, state: _EventState, reason: str,
                    source: str) -> list[dict]:
        dropped, self._dropped = self._dropped, []
        ops = []
        for name, seq in dropped:
            self._chains.pop((event_id, name), None)
            ops.append(self._settle_op(event_id, name, seq, "stale"))
        return ops

    def _terminal(self, event_id: int, state: _EventState, row_rev: Any,
                  source: str) -> list[dict]:
        for name in list(state.pending):
            self._forget(event_id, name)
        state.expired.clear()
        state.expired_through.clear()
        rev = _revision(row_rev)
        if rev is None:
            return []
        return [{"ledger_op": "terminal", "event_id": int(event_id),
                 "source": source, "ctx_rev": rev}]

    def _admit(self, event_id: int, state: _EventState, source: str, value: float, *,
               eligibility: Any, observed_basis: Optional[dict],
               stamped_at: Optional[datetime], row_sources: Any, row_rev: Any) -> list[dict]:
        from app.utils.aggregation import reading_regresses_stored_observation

        prior = state.pending.get(source)
        if reading_regresses_stored_observation(state.base_sources, source, observed_basis):
            # The SQL stamp would refuse it against this arm's own row (#8910).
            if prior is None:
                return []
            self._forget(event_id, source)
            return [self._settle_op(event_id, source, prior.seq, "stale")]
        rev, base = self._base(row_sources, row_rev, state)
        ctx_rev = _revision(row_rev)
        stamped_at = stamped_at or datetime.now(timezone.utc)
        try:
            payload = json.dumps({
                "value": value, "stamped_at": stamped_at.isoformat(),
                "eligibility": eligibility.to_entry() if eligibility is not None else None,
                "observed_basis": dict(observed_basis) if observed_basis else None,
            }, allow_nan=False)
        except (TypeError, ValueError, AttributeError):
            payload = None
        if ctx_rev is None or payload is None:
            return []
        local_seq = next(self._seq)
        chain = self._chains.get((event_id, source)) if prior is not None else None
        mode = "continue" if chain is not None else "open"
        if chain is None:
            chain = local_seq
        self._chains[(event_id, source)] = chain
        state.expired_through.pop(source, None)
        state.pending[source] = _Pending(
            value=value, eligibility=eligibility,
            observed_basis=dict(observed_basis) if observed_basis else None,
            stamped_at=stamped_at, seq=local_seq,
            since=prior.since if prior is not None else self._clock(),
        )
        return [{"ledger_op": "propose", "event_id": int(event_id), "source": source,
                 "mode": mode, "chain": chain, "local_seq": local_seq, "ctx_rev": ctx_rev,
                 "value": value, "payload": payload, "base_rev": rev, "base": base},
                *self._evict()]

    def committed(
        self, event_id: int, source: str, *, seq: Optional[int], sources: Any,
        rev: Any, event: Any = None,
    ) -> list[dict]:
        """Retire this process's entry through ``seq`` and advance the floor.

        Sent even with nothing pending here: the commit is the event's newer
        committed base, which a sibling's pending value must compose on.
        """
        # Commit-only events need a base for sibling composition, not retained
        # local state. In particular, Redis admission failure must not turn
        # successful database writes into an unbounded event catalog.
        state = (self._state(event_id) if event_id in self._events else _EventState())
        if event is not None:
            self._context(state, event)
        self._adopt_base(state, sources, rev)
        expired_through = state.expired_through.get(source)
        if (expired_through is None or seq is None
                or (_revision(seq) is not None and seq >= expired_through)):
            state.expired.pop(source, None)
            state.expired_through.pop(source, None)
        entry = state.pending.get(source)
        if entry is not None and (seq is None or entry.seq <= seq):
            self._forget(event_id, source)
        op = self._settle_op(event_id, source, seq, "unorderable",
                             self._base(sources, rev, state))
        chain = self._chains.get((event_id, source))
        if (entry is not None and chain is not None and _revision(seq) is not None
                and chain <= seq < entry.seq):
            op.update(mode="commit", chain=chain, owner=self.claims.get(source))
        return [op]

    def refused(self, event_id: int, source: str, reason: str) -> list[dict]:
        state = self._events.get(event_id)
        if state is None:
            return []
        state.expired.pop(source, None)
        state.expired_through.pop(source, None)
        entry = state.pending.get(source)
        if entry is None:
            return []
        self._forget(event_id, source)
        return [self._settle_op(event_id, source, entry.seq, reason)]

    def expire(self) -> list[dict]:
        now = self._clock()
        ops: list[dict] = []
        for event_id, state in list(self._events.items()):
            for name, entry in list(state.pending.items()):
                if now - entry.since >= self.max_uncommitted_s:
                    # Redis is authoritative: a landed-commit renewal may
                    # have succeeded even if its reply was lost/cancelled.
                    op = self._settle_op(event_id, name, entry.seq, "expired")
                    op.update(mode="expire", chain=self._chains[(event_id, name)],
                              owner=self.claims.get(name), value=entry.value)
                    ops.append(op)
        return ops

    def _evict(self) -> list[dict]:
        ops: list[dict] = []
        while len(self._events) > self.max_events:
            event_id, state = self._events.popitem(last=False)
            for name, entry in state.pending.items():
                self._chains.pop((event_id, name), None)
                ops.append(self._settle_op(event_id, name, entry.seq, "evicted"))
        return ops

    def _local_expired(self, op: dict) -> None:
        """Redis judged this chain over: never re-open the same value (R4)."""
        state = self._events.get(op["event_id"])
        entry = None if state is None else state.pending.get(op["source"])
        if entry is not None and entry.seq == op["local_seq"]:
            self._forget(op["event_id"], op["source"])
            state.expired[op["source"]] = op["value"]
            state.expired_through[op["source"]] = op["local_seq"]

    # ── Redis execution ─────────────────────────────────────────────────
    async def _eval(self, call, *argv: Any) -> list:
        keys = ledger_keys()
        reply = await call("EVAL", LEDGER_SCRIPT, len(keys), *keys,
                           *("" if a is None else str(a) for a in argv))
        return [_ledger_text(item) for item in reply]

    async def claim(self, call, source: str) -> int:
        reply = await self._eval(call, "claim", source)
        if reply[0] != "ok":
            self._alarm(reply[0], "claim", source, None)
            raise RuntimeError(f"ledger claim refused: {reply[0]}")
        self.claims[source] = int(reply[1])
        return self.claims[source]

    def _compose_readset(self, event_id: int, source: str, reply: list,
                         reason: str) -> tuple[Optional[dict], list[str]]:
        """(frame, excluded) for one read-set; a revoke when nothing composes."""
        from app.utils.aggregation import reading_regresses_stored_observation

        gen, seq = int(reply[1]), int(reply[2])
        try:
            base = json.loads(reply[5]) if reply[5] else None
        except ValueError:
            base = None
        state = _EventState()
        owners: dict[str, tuple[int, int]] = {}
        if isinstance(base, dict) and isinstance(base.get("sources"), dict) and reply[4]:
            state.base_rev = int(reply[4])
            state.base_sources = base["sources"]
            state.status = base.get("status")
            state.espn_win_prob_home = base.get("espn_win_prob_home")
            state.opening_home_probability = base.get("opening_home_probability")
        for i in range(7, len(reply) - 3, 4):
            name, owner, expires, raw = reply[i:i + 4]
            try:
                data = json.loads(raw)
                state.pending[name] = _Pending(
                    value=float(data["value"]),
                    eligibility=(_StoredEligibility(data["eligibility"])
                                 if data.get("eligibility") is not None else None),
                    observed_basis=data.get("observed_basis"),
                    stamped_at=datetime.fromisoformat(data["stamped_at"]),
                    seq=0, since=0.0,
                )
            except (ValueError, KeyError, TypeError):
                continue  # an unreadable entry is never shown
            owners[name] = (int(owner), int(expires))
        # #8910 against the CHOSEN base only: excluded from this frame, never
        # deleted from the ledger (that is its own writer's settle).
        excluded = [name for name, entry in state.pending.items()
                    if reading_regresses_stored_observation(
                        state.base_sources, name, entry.observed_basis)]
        for name in excluded:
            del state.pending[name]
        frame = None
        if (state.pending and state.base_rev is not None
                and state.status in PREVIEW_STATUSES):
            frame = _composed_frame(event_id, state, source, epoch=gen,
                                    ttl_ms=lambda: LEDGER_TTL_TOKEN.strip('"'),
                                    next_seq=lambda: seq)
        if frame is not None:
            # All entries share this event's generation/sequence and the
            # final-send contributor checks below. Folded readers may project
            # them only when every source is elected from this same event.
            frame["preview"]["pending_entries_version"] = 2
            frame["preview"]["pending_entries_authority"] = "event-ledger-v1"
            frame["_ledger"] = {"gen": gen, "seq": seq, "contributors": [
                (name, *owners[name]) for name in sorted(state.pending)]}
            return frame, excluded
        if seq <= 1:
            return None, excluded  # nothing of this generation was ever sent
        return {
            "event_id": int(event_id), "p": None, "status": state.status,
            "provisional": True,
            "preview": {"kind": "revoke", "epoch": gen, "seq": seq,
                        "through_seq": seq - 1, "reason": reason},
            "_ledger": {"gen": gen, "seq": seq},
        }, excluded

    async def _mutate(self, op: dict, call, stats: dict) -> list[dict]:
        source, event_id = op["source"], op["event_id"]
        kind = op["ledger_op"]
        claim = self.claims.get(source)
        if claim is None:
            self._refusal(stats, "fenced", kind, source, event_id)
            return []
        common = (source, op.get("owner", claim), event_id, " ".join(self.sources))
        started = self._clock()
        if kind == "propose":
            reply = await self._eval(
                call, "propose", *common, op["mode"], op["chain"], op["local_seq"],
                op["ctx_rev"], int(self.max_uncommitted_s * 1000), LEDGER_MAX_EVENTS,
                op["payload"], op["base_rev"], op["base"], op.get("read_ticket"),
            )
        elif kind == "settle":
            reply = await self._eval(call, "settle", *common, op["mode"], op["through"],
                                     op["base_rev"], op["base"], op.get("chain"),
                                     int(self.max_uncommitted_s * 1000))
        elif kind == "retire_idle":
            reply = await self._eval(call, "retire_idle", *common, op["ctx_rev"], op["read_ticket"])
        elif kind == "retire_missing":
            reply = await self._eval(call, "retire_missing", *common, op["read_ticket"])
        elif kind == "retire":
            reply = await self._eval(call, "retire", *common, op["ctx_rev"], op["read_ticket"],
                                     op["committed_rev"])
        else:
            reply = await self._eval(call, "terminal", *common, op["ctx_rev"],
                                     LEDGER_MAX_EVENTS, op.get("read_ticket"))
        status = reply[0]
        if (status in ("ok", "current") and op.get("chain") is not None
                and self._chains.get((event_id, source)) == op["chain"]):
            state = self._events.get(event_id)
            entry = None if state is None else state.pending.get(source)
            own = next((reply[i:i + 4] for i in range(7, len(reply) - 3, 4)
                        if reply[i] == source and int(reply[i + 1]) == claim), None)
            if entry is not None and own is not None:
                # The pre-EVAL monotonic time is conservative under slow/lost
                # replies; only Redis acknowledgement can advance this hint.
                entry.since = max(entry.since, started +
                    (int(own[2]) - int(reply[3])) / 1000 - self.max_uncommitted_s)
            elif (entry is not None and op.get("mode") == "expire"
                  and entry.seq <= op["through"]):
                state.expired[source] = entry.value
                state.expired_through[source] = entry.seq
                self._forget(event_id, source)
        if status == "current":
            return []
        if kind in ("terminal", "retire", "retire_missing", "retire_idle"):
            if status != "ok":
                self._refusal(stats, status, kind, source, event_id)
                return []
            gen, seq = int(reply[1]), int(reply[2])
            if seq <= 1:
                return []
            return [{"event_id": int(event_id), "p": None, "status": None,
                     "provisional": True,
                     "preview": {"kind": "revoke", "epoch": gen, "seq": seq,
                                 "through_seq": seq - 1, "reason": "idle" if kind == "retire_idle" else "terminal"},
                     "_ledger": {"gen": gen, "seq": seq}}]
        if kind == "propose" and status in ("read_required", "full"):
            state = self._events.get(event_id)
            entry = None if state is None else state.pending.get(source)
            if entry is not None and entry.seq == op["local_seq"]:
                self._forget(event_id, source)
        if kind == "propose" and status in ("expired", "missing_chain"):
            self._local_expired(op)
        if kind == "propose" and status == "terminal":
            self._forget(event_id, source)
        if status not in ("ok", "expired"):
            if status not in ("unchanged", "none"):
                self._refusal(stats, status, kind, source, event_id)
            return []
        frame, excluded = self._compose_readset(
            event_id, source, reply, "expired" if status == "expired" else op.get("reason", "stale"))
        if kind == "propose" and status == "ok" and source in excluded:
            # The chosen committed base already supersedes this value.
            self._forget(event_id, source)
            return await self._mutate(
                self._settle_op(event_id, source, op["local_seq"], "stale"), call, stats)
        return [] if frame is None else [frame]

    def _refusal(self, stats: dict, status: str, phase: str, source: str,
                 event_id: int) -> None:
        key = "fenced" if status == "fenced" else "ledger_refused"
        stats[key] = stats.get(key, 0) + 1
        self._alarm(status, phase, source, event_id)

    def _alarm(self, status: str, phase: str, source: str,
               event_id: Optional[int]) -> None:
        if status not in LEDGER_ALARM_STATUSES:
            return
        key = (status, phase, source)
        count, first = self._alarm_owed.get(key, (0, event_id))
        self._alarm_owed[key] = (count + 1, first)
        if not self._alarm_batch_open:
            self._flush_alarms()

    def _flush_alarms(self) -> None:
        now = self._clock()
        for key, (count, first) in list(self._alarm_owed.items()):
            last = self._alarm_last.get(key)
            if last is not None and now - last < LEDGER_ALARM_INTERVAL_S:
                continue
            del self._alarm_owed[key]
            self._alarm_last[key] = now
            logger.warning(LEDGER_ALARM_FORMAT, *key, count, "-" if first is None else first)

    @contextmanager
    def _alarm_batch(self):
        """One batch's alarms log when it ends — also when a timeout cuts it."""
        if self._alarm_batch_open:
            yield
            return
        self._alarm_batch_open = True
        try:
            yield
        finally:
            self._alarm_batch_open = False
            self._flush_alarms()

    async def _publish(self, frame: dict, call, channel, stats: dict, retries: int = 2) -> None:
        meta = frame.pop("_ledger")
        payload = json.dumps(frame)
        kind = frame["preview"]["kind"]
        if kind == "revoke":
            # Permissive, with the generation and through_seq it was allocated.
            await self._eval(call, "revoke", channel(frame["event_id"]), payload)
            stats["revoked"] = stats.get("revoked", 0) + 1
            return
        source = frame["source"]
        claim = self.claims.get(source)
        if claim is None or payload.count(LEDGER_TTL_TOKEN) != 1:
            self._refusal(stats, "fenced" if claim is None else "malformed", "publish",
                          source, frame["event_id"])
            return
        argv = [source, claim, frame["event_id"], " ".join(self.sources),
                meta["gen"], meta["seq"], channel(frame["event_id"]), payload]
        for name, owner, expires in meta["contributors"]:
            argv.extend((name, owner, expires))
        reply = await self._eval(call, "publish", *argv)
        status = reply[0]
        if status == "published":
            stats["published"] = stats.get("published", 0) + 1
        elif status == "contributor" and retries > 0:
            # A contributor lost its owner or deadline after this read-set:
            # recompose from a fresh one, never send the old composition.
            stats["ledger_recomposed"] = stats.get("ledger_recomposed", 0) + 1
            sync = {"ledger_op": "settle", "mode": "sync", "event_id": frame["event_id"],
                    "source": source, "through": None, "reason": "expired",
                    "base_rev": None, "base": None}
            for fresh in await self._mutate(sync, call, stats):
                await self._publish(fresh, call, channel, stats, retries - 1)
        elif status in ("stale", "terminal"):
            # A newer ledger write (its own frame carries every entry) or a
            # tombstone superseded this read-set.
            stats["ledger_superseded"] = stats.get("ledger_superseded", 0) + 1
        else:
            self._refusal(stats, status, "publish", source, frame["event_id"])

    async def prepare(self, items: list, call, stats: dict) -> list[dict]:
        """Run every operation; return composed frames, unpublished, in order."""
        frames: list[dict] = []
        with self._alarm_batch():
            for item in items:
                if "ledger_op" in item:
                    frames.extend(await self._mutate(item, call, stats))
                elif "_ledger" in item:
                    frames.append(item)
        return frames

    async def execute(self, items: list, call, channel, stats: dict) -> None:
        """Each operation's frames are published before the next operation runs."""
        with self._alarm_batch():
            for item in items:
                for frame in await self.prepare([item], call, stats):
                    await self._publish(frame, call, channel, stats)


_REGISTRY: Optional[PreviewRegistry] = None


def registry() -> PreviewRegistry:
    """The process's one registry: both source arms must share it."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = LedgerRegistry(sources=ledger_sources())
    return _REGISTRY


def reset_registry_for_tests() -> None:
    global _REGISTRY
    _REGISTRY = None


def is_preview_frame(frame: Any) -> bool:
    preview = frame.get("preview") if isinstance(frame, dict) else None
    return (isinstance(preview, dict) and preview.get("kind") in ("blend", "revoke")
            and "rev" not in frame)
