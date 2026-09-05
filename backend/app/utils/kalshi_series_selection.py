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
from typing import Iterable, Mapping, NamedTuple, Optional, Sequence

#: How many dormant series to name in the receipt before switching to a count.
_DORMANT_SAMPLE = 8


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
    discovered: Iterable[str],
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
        open_counts: series ticker → count of OPEN events, from the census walk.
            A series absent from this mapping has no open events.
        guaranteed: the hand-listed floor. Already fetched, so selecting one
            again would spend the discovery reserve on work already done.
        heavy_tokens: substrings that mark a monster-nested-payload series.
        max_series: hard cap on how many series one beat may add.
        max_open_events: refuse a series holding more open events than this.
        page_limit: events per page the caller will request.
        max_pages: hard per-series page ceiling.

    Returns:
        ``(selected, receipt)``. ``selected`` is a list of
        ``(series_ticker, pages)`` ordered by open-event count descending then
        ticker ascending — deterministic, so a guard test can assert on it and
        so the biggest gap is closed first if the deadline truncates the loop.
        ``pages`` is derived from the census count, never a uniform guess.

    Pure and total: an unparseable or duplicated ticker is skipped, not raised.
    A fetch must never fail on a bookkeeping concern.
    """
    _guaranteed = {str(g).upper() for g in guaranteed if g}
    _tokens = tuple(t.upper() for t in heavy_tokens)

    counts: dict[str, int] = {}
    dormant: list[str] = []
    skipped: dict[str, int] = {}
    detail: dict[str, str] = {}

    def _skip(ticker: str, reason: str, *, with_detail: bool = True) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1
        if with_detail:
            detail[ticker] = reason

    seen: set[str] = set()
    for raw in discovered:
        ticker = str(raw or "").strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)

        n_open = int(open_counts.get(ticker) or 0)
        if n_open <= 0:
            # Counted, not named: dormant series are the bulk of any catalog and
            # naming them all would bury the refusals a reader can act on.
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

    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))

    selected: list[tuple[str, int]] = []
    for ticker, n_open in ranked:
        if len(selected) >= max_series:
            # Not a failure — the cap is what keeps one busy tag from eating the
            # whole reserve. Named so a beat that hits it is visible.
            _skip(ticker, "over_budget")
            continue
        pages = max(1, min(max_pages, math.ceil(n_open / max(1, page_limit))))
        selected.append((ticker, pages))

    receipt = {
        "discovered": len(seen),
        "with_open_events": len(seen) - len(dormant),
        "selected": [t for t, _ in selected],
        "selected_count": len(selected),
        "selected_open_events": sum(counts[t] for t, _ in selected),
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

        detail = receipt.get("skipped_detail")
        if isinstance(detail, Mapping):
            items = sorted(detail.items())[:_PERSIST_MAX_DETAIL]
            out["skipped_detail"] = {str(k): str(v) for k, v in items}
            if len(detail) > _PERSIST_MAX_DETAIL:
                out["skipped_detail_truncated"] = len(detail) - _PERSIST_MAX_DETAIL

        census = receipt.get("census")
        if isinstance(census, Mapping) and "exhausted" in census:
            out["census_exhausted"] = bool(census["exhausted"])

        return out
    except Exception:  # noqa: BLE001 — see docstring
        return {"source": "unsummarizable"}


#: Receipt `source` values that mean the discovery stage actually resolved a
#: series list this beat, so `events_added == 0` is a result and not a no-op.
_DISCOVERY_RAN_SOURCES = frozenset({"live", "cache"})


def discovery_is_silent_zero(receipt: Optional[Mapping]) -> bool:
    """True when discovery ran, selected series, and still added nothing.

    This is the gotcha #53 shape for this stage: `events_added: 0` from a beat
    that resolved a live list and picked series off it is a response, not an
    absence, and it is exactly what a poisoned cache, a spent reserve or a
    venue that quietly stopped listing the draw all look like. It is the one
    reading that must be loud, because every other failure mode here already
    names itself in `source`.

    A beat that selected nothing is NOT this: `selected_count == 0` is already
    explained by the `skipped` counters, and calling it silent would fire the
    alarm every night the tournament is dark.
    """
    if not receipt:
        return False
    try:
        if str(receipt.get("source") or "") not in _DISCOVERY_RAN_SOURCES:
            return False
        if int(receipt.get("selected_count") or 0) <= 0:
            return False
        return int(receipt.get("events_added") or 0) <= 0
    except Exception:  # noqa: BLE001 — telemetry never raises
        return False
