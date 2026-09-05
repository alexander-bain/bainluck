"""Which Kalshi series the supplementary rescue fetches — DISCOVERED, not listed.

`kalshi_api._SPORTS_SERIES_TICKERS` is a hand list. Every incident recorded in
its comments has the same shape: a series the venue carried and the list did not
name, so we held none of it — golf before #163, combat before #173, tennis
singles before Q426. The list grew by one incident each time, which is a
membership rule that can only ever be as complete as the last outage.

Measured at the venue 2026-09-04 (`/series?category=Sports&tags=Tennis`, then a
`status=open&with_nested_markets=false` walk of the whole listing — 72 pages,
17s, cursor exhausted):

* Kalshi lists **140** tennis series; **39** of them carry open events, holding
  **418** open events between them.
* The hand list names **4** (`KXATPMATCH`, `KXWTAMATCH`, `KXATPNATSTAGE`,
  `KXWTANATSTAGE`).
* Our `futures_markets` held **64** open tennis rows across 24 series, and the
  only four series whose newest row was from that day were exactly those four.
  Everything else was stale (newest 2026-08-28) or absent.
* `KXATPDOUBLES` (32 open events) and `KXWTADOUBLES` (22) were **0 open rows**,
  newest row 2026-08-29 — five days cold — while the venue carried today's US
  Open doubles draw. `KXHONEYDEUCE` (the US Open's Honey Deuce prop, 7 markets)
  was absent outright.

So the hand list is not a safety net over a scan that mostly works; for tennis
the hand list IS the coverage. The container principle (#2927) applies to
series exactly as it applies to events: **membership is discovered, never
listed by hand.**

This module is the selection half, kept pure so the policy is a unit test
rather than a live fetch. The service supplies two measurements — what the
venue lists for a tag, and how many OPEN events each series actually holds —
and this function decides what the rescue fetches and, for everything it
declines, says why.

Why a census bounds it. `Sports` alone is 3,648 series and 1,263 of them carry
open events; a rescue loop that fetched one page each would need ~380s and the
whole fetch budget is 240s. Selecting on live open-event counts turns an
unbounded catalog into today's ~30 tennis series, and the counts also say how
many pages each one needs, so nothing pages into empty space.

The two refusals are deliberate and both are the #995 monster-payload lesson
rather than timidity:

``heavy_payload_shape``
    The ticker carries a `_HEAVY_TOKENS` word (GAME/SPREAD/TOTAL/1H/2H/WINNER/
    SERIES). Those are the series whose nested-markets pages froze the poll.
    The guaranteed floor handles the ones we know by fetching them stripped and
    backfilling markets per event, on a 45s reserve that is already fully
    subscribed by tonight's NBA/MLB slate. Discovery must not push new load into
    that reserve, so it declines them here — visibly, with a count — instead of
    silently crowding a promise #2214 had to be built to keep. Today that
    declines `KXATPSETWINNER` (48 open) and seven siblings; they are props on
    matches the selected series bring in, and they are the natural next widening
    once the backfill's headroom is measured.

``too_many_open_events``
    A series big enough that one beat could not drain it anyway. Fetching its
    first page every beat is how a series gets *partially* ingested forever,
    which reads healthier than a gap and is worse.

The receipt is bounded on purpose. Detail is recorded for every series that has
open events and was still declined — those are the ones we could have taken and
did not, and they are the only ones a reader can act on. Series with zero open
events are counted and sampled rather than listed in full: 101 of the 140
tennis series are dormant, and a telemetry blob that names them all every beat
buries the eight that matter.
"""

from __future__ import annotations

import math
from typing import Iterable, Mapping, NamedTuple, Optional, Sequence, Union

#: How many dormant series to name in the receipt before switching to a count.
_DORMANT_SAMPLE = 8

#: The tag a flat (untagged) ticker list is filed under. One tag means the
#: per-tag machinery below collapses to exactly the single-tag behaviour that
#: shipped for tennis: whole cap to that tag, plain open-count-descending order.
_UNTAGGED = "_"


def _fair_shares(wants: Mapping[str, int], cap: int) -> dict[str, int]:
    """Split ``cap`` slots across tags so a big tag cannot evict a small one.

    This function is the whole of lane1b/040 and it exists because the naive
    widening is wrong in a way only a measurement shows. Measured at the venue
    2026-09-05: tennis carries 27 selectable series, Football carries 256
    uncarried live series of which 200+ are selectable. Ranked together on one
    global cap of 40 by open-event count, **tennis drops from 27 series to 3** —
    `KXWTADOUBLES`, `KXITFDOUBLES` and `KXHONEYDEUCE` among the 24 evicted, i.e.
    exactly the US Open doubles coverage that shipped four beats ago. Raising the
    cap does not fix it: at 80 tennis still loses 17, because Football's long
    tail out-ranks tennis's small futures on raw open-event count forever.

    That is one cap over two populations of very different size, which caps the
    smaller one out of existence. So the cap is split rather than shared:

    * every tag with something to select starts on an equal share;
    * a tag that wants fewer slots than its share **releases the remainder**,
      which is re-offered to the tags still short (water-filling, repeated until
      nothing more can be given away);
    * a tag never receives more than it wants, so no slot is reserved for a
      dormant tag — an out-of-season tag costs the others nothing, which is the
      same promise ``has_discovered`` makes to the guaranteed floor.

    With today's numbers and ``max_series=60``: two tags, 30 each; tennis wants
    27 so releases 3; Football takes 33. Tennis keeps **every** series it selects
    today and Football adds 33 — which is the ship, without un-shipping the last
    one.

    Deterministic: shares depend only on ``wants`` and ``cap``, and the leftover
    from integer division is handed out in sorted tag order.
    """
    live = {t: n for t, n in wants.items() if n > 0}
    if not live or cap <= 0:
        return {t: 0 for t in wants}

    shares = {t: 0 for t in wants}
    remaining = int(cap)
    open_tags = set(live)

    while remaining > 0 and open_tags:
        share, extra = divmod(remaining, len(open_tags))
        if share == 0:
            # Fewer slots left than tags still short: hand them out one apiece in
            # sorted tag order rather than dropping them on the floor.
            for tag in sorted(open_tags)[:remaining]:
                shares[tag] += 1
                remaining -= 1
            break
        granted = 0
        for i, tag in enumerate(sorted(open_tags)):
            allot = share + (1 if i < extra else 0)
            take = min(allot, live[tag] - shares[tag])
            shares[tag] += take
            granted += take
        remaining -= granted
        open_tags = {t for t in open_tags if shares[t] < live[t]}
        if granted == 0:
            # Everyone is full; the cap simply exceeds total demand.
            break

    return shares


class StageDeadlines(NamedTuple):
    """Where each stage of the fetch must stop so the next one has a floor."""

    main_scan: Optional[float]
    guaranteed: Optional[float]
    discovered: Optional[float]


def fetch_stage_deadlines(
    deadline: Optional[float],
    has_discovered: bool,
    rescue_reserve_s: float,
    discovery_reserve_s: float,
    backfill_reserve_s: float,
) -> StageDeadlines:
    """Carve the fetch budget so a later stage cannot be starved by an earlier one.

    This arithmetic is the whole of #999 and #2214, and it is a function rather
    than four expressions inline because both of those bugs were the same
    off-by-one-stage mistake and neither was visible in a test. The failure has
    a signature: the last stage's first deadline check fires immediately, it
    does zero work every beat, deterministically, and the fetch reports itself
    healthy. #999 was the golf rescue getting nothing; #2214 was the market
    backfill getting nothing; discovery is the third stage to need the carve and
    the first to get it before shipping rather than after an outage.

    Stages run main scan → guaranteed floor → discovered → market backfill, and
    each returned deadline is where that stage stops, leaving the remainder to
    those after it. The main scan pays for all of them because its cursor is
    resumable: the seconds it gives up are deferred to the next beat, not lost.

    ``has_discovered`` collapses the discovery reserve to zero when nothing was
    selected. A tag with no live series must cost the guaranteed floor nothing —
    otherwise adding a quiet tag silently shortens the rescue.

    ``deadline`` of None means unbounded (tests, and callers with no budget);
    every stage then gets None and no stage stops early.
    """
    if deadline is None:
        return StageDeadlines(None, None, None)
    disc = discovery_reserve_s if has_discovered else 0.0
    return StageDeadlines(
        main_scan=deadline - rescue_reserve_s - disc - backfill_reserve_s,
        guaranteed=deadline - disc - backfill_reserve_s,
        discovered=deadline - backfill_reserve_s,
    )


def select_discovered_series(
    discovered: Union[Iterable[str], Mapping[str, Iterable[str]]],
    open_counts: Mapping[str, int],
    guaranteed: Iterable[str],
    heavy_tokens: Sequence[str],
    max_series: int,
    max_open_events: int,
    page_limit: int,
    max_pages: int,
) -> tuple[list[tuple[str, int]], dict]:
    """Choose the discovered series the rescue should fetch this beat.

    Args:
        discovered: series tickers the venue lists for the tags we asked about.
            Either a flat iterable (one anonymous tag — the tennis-only shape,
            behaviour unchanged) or a ``{tag: tickers}`` mapping, which is what
            turns the cap from shared into split (see ``_fair_shares``). A ticker
            listed under two tags belongs to the first tag that claims it, in the
            mapping's own order, so the split is deterministic.
        open_counts: series ticker → count of OPEN events, from the census walk.
            A series absent from this mapping has no open events.
        guaranteed: the hand-listed floor. Already fetched, so selecting one
            again would spend the discovery reserve on work already done.
        heavy_tokens: substrings that mark a monster-nested-payload series.
        max_series: hard cap on how many series one beat may add, across all tags.
        max_open_events: refuse a series holding more open events than this.
        page_limit: events per page the caller will request.
        max_pages: hard per-series page ceiling.

    Returns:
        ``(selected, receipt)``. ``selected`` is a list of
        ``(series_ticker, pages)``. Within a tag it is open-event count
        descending then ticker ascending; across tags the tags are INTERLEAVED
        round-robin, so a truncated beat loses the tail of every tag rather than
        the whole of one. That is gotcha #41 at tag scale — "ask what the
        ordering starts on" — and with one tag it collapses to the plain
        descending order that shipped. ``pages`` is derived from the census
        count, never a uniform guess.

    Pure and total: an unparseable or duplicated ticker is skipped, not raised.
    A fetch must never fail on a bookkeeping concern.
    """
    _guaranteed = {str(g).upper() for g in guaranteed if g}
    _tokens = tuple(t.upper() for t in heavy_tokens)

    if isinstance(discovered, Mapping):
        by_tag = {str(k): list(v or []) for k, v in discovered.items()}
    else:
        by_tag = {_UNTAGGED: list(discovered or [])}

    counts: dict[str, int] = {}
    tag_of: dict[str, str] = {}
    dormant: list[str] = []
    skipped: dict[str, int] = {}
    detail: dict[str, str] = {}

    def _skip(ticker: str, reason: str, *, with_detail: bool = True) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1
        if with_detail:
            detail[ticker] = reason

    seen: set[str] = set()
    for tag, tickers in by_tag.items():
        for raw in tickers:
            ticker = str(raw or "").strip().upper()
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)

            n_open = int(open_counts.get(ticker) or 0)
            if n_open <= 0:
                # Counted, not named: dormant series are the bulk of any catalog
                # and naming them all would bury the refusals a reader can act on.
                dormant.append(ticker)
                _skip(ticker, "no_open_events", with_detail=False)
                continue
            if ticker in _guaranteed:
                _skip(ticker, "already_guaranteed")
                continue
            if any(tok in ticker for tok in _tokens):
                _skip(ticker, "heavy_payload_shape")
                continue
            if n_open > max_open_events:
                _skip(ticker, "too_many_open_events")
                continue
            counts[ticker] = n_open
            tag_of[ticker] = tag

    # Rank within each tag, then give each tag a share of the cap it cannot be
    # squeezed out of by a bigger neighbour.
    ranked_by_tag: dict[str, list[tuple[str, int]]] = {t: [] for t in by_tag}
    for ticker, n_open in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        ranked_by_tag[tag_of[ticker]].append((ticker, n_open))

    shares = _fair_shares({t: len(r) for t, r in ranked_by_tag.items()}, max_series)

    taken: dict[str, list[tuple[str, int]]] = {}
    for tag, ranked in ranked_by_tag.items():
        keep = shares.get(tag, 0)
        taken[tag] = ranked[:keep]
        for ticker, _ in ranked[keep:]:
            # Not a failure — the cap is what keeps one busy tag from eating the
            # whole reserve. Named so a beat that hits it is visible.
            _skip(ticker, "over_budget")

    # Interleave: tag A's biggest, tag B's biggest, tag A's second… A deadline
    # that cuts the loop short then costs every tag its smallest series, not one
    # tag its entire draw.
    order = sorted(taken)
    selected: list[tuple[str, int]] = []
    for rank in range(max((len(v) for v in taken.values()), default=0)):
        for tag in order:
            if rank < len(taken[tag]):
                ticker, n_open = taken[tag][rank]
                pages = max(
                    1, min(max_pages, math.ceil(n_open / max(1, page_limit)))
                )
                selected.append((ticker, pages))

    receipt = {
        "discovered": len(seen),
        "with_open_events": len(seen) - len(dormant),
        "selected": [t for t, _ in selected],
        "selected_count": len(selected),
        "selected_open_events": sum(counts[t] for t, _ in selected),
        # Which tag each slot went to. The split is the policy, so a reader who
        # sees tennis at 27 and Football at 33 can tell a healthy share from a
        # tag that has quietly been squeezed to nothing.
        "selected_per_tag": {
            t: len(v) for t, v in sorted(taken.items()) if t != _UNTAGGED
        },
        # CERT-953: what the census said EACH selected series holds. The fetch
        # needs it per series to say "KXATPDOUBLES was supposed to bring 32 and
        # brought 0" rather than reporting one aggregate in which a dead series
        # is invisible behind a live sibling.
        "selected_expected": {t: counts[t] for t, _ in selected},
        "skipped": skipped,
        "skipped_detail": detail,
        "dormant_sample": sorted(dormant)[:_DORMANT_SAMPLE],
    }
    return selected, receipt


#: Hard caps on the persisted copy of a discovery receipt. The live receipt is
#: bounded by policy (see the module docstring); these bound it by arithmetic,
#: because the scan report keeps 48 of them in a shared 100MB Redis and a
#: catalog that grows must not turn telemetry into a memory problem.
_PERSIST_MAX_LIST = 24
_PERSIST_MAX_DETAIL = 24

#: The receipt keys worth keeping across beats, in reading order. `source` and
#: `events_added` are the two the reader is actually here for — everything else
#: explains a number that surprised them.
_PERSIST_SCALARS = (
    "source",
    "events_added",
    "series_fetched",
    "discovered",
    "with_open_events",
    "selected_count",
    "selected_open_events",
    "fetch_truncated_after",
    "not_cached",
    "error",
)


def summarize_discovery_receipt(receipt: Optional[Mapping]) -> dict:
    """The part of a discovery receipt worth persisting on every beat.

    The receipt as measured carries two nested sub-receipts (the catalog read
    and the census walk) that answer "why is this number what it is" for the
    beat that produced it. Across 48 ring entries they are noise, so this keeps
    the counters and drops the sub-receipts — with one exception: `census` is
    reduced to `exhausted`, because a census that did not exhaust is the one
    condition under which a *small* `selected_count` is expected rather than
    alarming, and a reader who cannot see it will misread the beat.

    Never raises. A receipt is telemetry, and telemetry that can fail the report
    it rides on is worse than no telemetry (the whole reason this function
    exists is that the receipt was silently dropped instead).
    """
    if not receipt:
        return {"source": "absent"}
    try:
        out: dict = {}
        for key in _PERSIST_SCALARS:
            if key in receipt:
                out[key] = receipt[key]
        out.setdefault("source", "unknown")

        selected = receipt.get("selected")
        if isinstance(selected, (list, tuple)):
            out["selected"] = [str(s) for s in selected[:_PERSIST_MAX_LIST]]
            if len(selected) > _PERSIST_MAX_LIST:
                out["selected_truncated"] = len(selected) - _PERSIST_MAX_LIST

        skipped = receipt.get("skipped")
        if isinstance(skipped, Mapping):
            out["skipped"] = {str(k): int(v) for k, v in skipped.items()}

        # The tag split. Tiny (one int per tag) and the only field that can show
        # a tag being squeezed out, which is the failure `_fair_shares` exists to
        # prevent — so it survives every cap here.
        per_tag = receipt.get("selected_per_tag")
        if isinstance(per_tag, Mapping) and per_tag:
            out["selected_per_tag"] = {str(k): int(v) for k, v in per_tag.items()}

        detail = receipt.get("skipped_detail")
        if isinstance(detail, Mapping):
            items = sorted(detail.items())[:_PERSIST_MAX_DETAIL]
            out["skipped_detail"] = {str(k): str(v) for k, v in items}
            if len(detail) > _PERSIST_MAX_DETAIL:
                out["skipped_detail_truncated"] = len(detail) - _PERSIST_MAX_DETAIL

        census = receipt.get("census")
        if isinstance(census, Mapping) and "exhausted" in census:
            out["census_exhausted"] = bool(census["exhausted"])

        # CERT-953: the per-series results, which are the only fields that can
        # answer "did THIS draw arrive". Bounded like everything else here, but
        # ordered so the ones a reader must not lose survive the cap: anything
        # that returned nothing or errored sorts first.
        results = receipt.get("series_results")
        if isinstance(results, Mapping):
            def _rank(item):
                ticker, res = item
                if not isinstance(res, Mapping):
                    return (2, ticker)
                bad = bool(res.get("error")) or int(res.get("returned") or 0) <= 0
                return (0 if bad else 1, ticker)

            kept = sorted(results.items(), key=_rank)[:_PERSIST_MAX_DETAIL]
            out["series_results"] = {
                str(t): {
                    k: v for k, v in dict(r).items()
                    if k in ("expected", "returned", "unique_added",
                             "truncated", "parse_failed", "error")
                }
                for t, r in kept
                if isinstance(r, Mapping)
            }
            if len(results) > _PERSIST_MAX_DETAIL:
                out["series_results_truncated"] = len(results) - _PERSIST_MAX_DETAIL

        return out
    except Exception:  # noqa: BLE001 — see docstring
        return {"source": "unsummarizable"}


#: Receipt `source` values that mean the discovery stage actually resolved a
#: series list this beat, so `events_added == 0` is a result and not a no-op.
_DISCOVERY_RAN_SOURCES = frozenset({"live", "cache"})


def discovery_dead_series(receipt: Optional[Mapping]) -> list[str]:
    """Selected series the venue returned NOTHING for — named, one by one.

    This is the gotcha #53 reading for this stage, and it has to be per series.
    The aggregate `events_added` cannot carry it, in both directions (CERT-953):

    * **It hides a real outage.** `events_added` sums every selected series, so
      a dead `KXATPDOUBLES` returning zero is invisible behind a live
      `KXWTADOUBLES` that added events. The alarm would stay quiet through
      exactly the half-outage it exists to catch — the men's draw vanishing off
      the site while the women's draw keeps it looking healthy.
    * **It invents one that is not there.** `events_added` counts only events
      the main and supplementary scans had not already mapped. A perfectly
      healthy doubles fetch whose events the main scan already held contributes
      zero UNIQUE additions, and an aggregate alarm would fire on a beat where
      nothing whatsoever is wrong.

    So the question is asked of the venue's own answer for each series:
    `returned` — how many events came back for this ticker, counted before the
    dedup — plus an outright fetch error. Neither depends on a sibling, and
    neither depends on what we already held.

    Deliberately NOT dead:

    * a series the reserve never reached (`truncated` with nothing returned).
      `fetch_truncated_after` already says that precisely, and alarming on it
      would turn a budget signal into a coverage alarm.
    * a beat that selected nothing at all. The `skipped` counters explain it,
      and firing every night the tournament is dark is how an alarm gets
      ignored on the night it matters.
    * a stage that never ran (`not_wired`, `disabled`, `failed`) — those name
      their own failure in `source`.

    Returns the sorted tickers so the caller can print them; empty means clean.
    """
    if not receipt:
        return []
    try:
        if str(receipt.get("source") or "") not in _DISCOVERY_RAN_SOURCES:
            return []
        results = receipt.get("series_results")
        if not isinstance(results, Mapping):
            return []
        dead = []
        for ticker, res in results.items():
            if not isinstance(res, Mapping):
                continue
            if res.get("error"):
                dead.append(str(ticker))
                continue
            if int(res.get("returned") or 0) > 0:
                continue
            # Zero returned. Only an alarm if we actually got to ask.
            if res.get("truncated") or res.get("parse_failed"):
                continue
            if int(res.get("expected") or 0) <= 0:
                continue
            dead.append(str(ticker))
        return sorted(dead)
    except Exception:  # noqa: BLE001 — telemetry never raises
        return []
