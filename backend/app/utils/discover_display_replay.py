"""#10290 (under #5105): capture one Discover build at the display-chain seam,
and replay it offline through the SAME chain.

What this is for. A policy comparison on Discover's mix is only worth reading
if its baseline arm reproduces the page that was actually served. The existing
replay (``scripts/replay_discover_ranking.py``) re-ranks a futures-only
snapshot capped at 300 and stops at the sort; the served page is a MIXED deck
(games, markets, tournaments, concepts, bundles, hubs) assembled by
``apply_discover_display_chain`` and four downstream stages. This module
freezes that seam and its downstream inputs, and refuses to call a replay
faithful until the whole pre-slice deck and the returned page match.

Two halves:

* :class:`DiscoverDisplayCapture` — a passive recorder ``get_feed`` feeds when
  an in-process caller puts one in the request's ASGI scope under
  :data:`DISCOVER_DISPLAY_CAPTURE_SCOPE_KEY`. No header or query parameter can
  reach the scope (the same arm as LAT-P001's pre-warm marker), so no HTTP
  request is ever captured, and ``debug=1`` is deliberately NOT the switch —
  it changes the build. The recorder never raises into the request: anything
  it cannot record turns into a refusal on the recorder itself.
* :func:`replay_capture` / :func:`verify_baseline` — offline: decode the frozen
  pool (a fresh copy per call), run the shared chain with the frozen clock and
  arguments, place the frozen collection cards with the shared pure helper,
  re-apply the frozen edition pin and venue-settlement deltas, publish with
  the route's own per-card and envelope helpers, and compare.

What a PASS proves, and what it does not (stated in every report):

1. Assembly from the captured scored pool through the supported downstream
   stages reproduces the served deck and page.
2. Upstream admission and scoring are NOT replayed — the pool is taken as
   scored.
3. The browser-painted order is NOT checked (clients may reorder).
4. Personalized, session, cached, Sports, filtered-browse, debug and
   reviewed-filter requests are NOT supported; they refuse at capture.
5. A synthetic or locally built capture proves the machinery, never a claim
   about production; ``provenance.origin`` says which it is.
"""

from __future__ import annotations

import copy
import datetime as _dt
import decimal
import hashlib
import json
import math
import os
import socket
import time
import uuid
from contextlib import contextmanager
from typing import Any, Callable, Iterable, Optional

SCHEMA_VERSION = "mixed_display_replay_v1"

#: The ASGI scope key an in-process caller sets to a
#: :class:`DiscoverDisplayCapture`. Never read from a header or a query.
DISCOVER_DISPLAY_CAPTURE_SCOPE_KEY = "bainluck_discover_display_capture"

#: Hard bound on a serialized capture. Exceeding it REFUSES the capture; the
#: pool is never truncated to fit.
DEFAULT_MAX_CAPTURE_BYTES = 64 * 1024 * 1024

#: Card kinds the seam pool may hold for a supported capture. Bundles are
#: built INSIDE the chain and collections after it, so neither may arrive in
#: the pool.
SUPPORTED_POOL_KINDS = frozenset({"event", "futures", "tournament", "concept"})

#: Kinds the deck may hold after the chain and collections.
SUPPORTED_DECK_KINDS = SUPPORTED_POOL_KINDS | {"bundle", "collection"}

#: The three keys ``_attach_feed_venue_settlement`` may write on a game card.
VENUE_FIELDS = ("venue_settled", "venue_settled_result", "venue_closed_no_winner")

#: The envelope field holding clock-derived cache metadata. Recorded verbatim,
#: never replayed: a cache build time is not the scoring clock.
CACHE_METADATA_FIELD = "cache"

#: Envelope fields the route adds from UPSTREAM facts (the futures stage's
#: outcome). Carried from the capture into the replayed envelope, and declared.
UPSTREAM_CARRIED_FIELDS = ("build_quality", "degraded_reason")

# Refusal / verdict codes.
UNSUPPORTED = "UNSUPPORTED"
INCOMPLETE = "INCOMPLETE"
INVALID = "INVALID"
MISMATCH = "MISMATCH"
OFFLINE_VIOLATION = "OFFLINE_VIOLATION"
PASS = "PASS"

_TAG = "__bl_t__"


class DisplayReplayError(Exception):
    """A capture or replay that cannot be trusted. ``code`` is one of the
    module's verdict codes; nothing downstream may compute a metric past one."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


# --------------------------------------------------------------------------- #
# Typed JSON codec
# --------------------------------------------------------------------------- #
#
# The pool holds datetimes, Decimals, sets and the odd tuple, and the chain
# compares some of them. A plain ``json.dumps(default=str)`` would turn a
# datetime into a string and the replay would compare strings where the build
# compared datetimes — a "faithful" replay of a different computation. So
# every non-JSON type is tagged and restored to the same type, and anything the
# codec does not know REFUSES rather than being stringified.


def encode_value(value: Any, path: str = "$") -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return {_TAG: "float", "v": repr(value)}
    if isinstance(value, dict):
        if _TAG in value:
            raise DisplayReplayError(
                UNSUPPORTED, f"{path}: a dict already carries the codec tag {_TAG!r}"
            )
        if all(isinstance(k, str) for k in value):
            return {k: encode_value(v, f"{path}.{k}") for k, v in value.items()}
        return {
            _TAG: "dict",
            "v": [
                [encode_value(k, f"{path}<key>"), encode_value(v, f"{path}[{k!r}]")]
                for k, v in value.items()
            ],
        }
    if isinstance(value, list):
        return [encode_value(v, f"{path}[{i}]") for i, v in enumerate(value)]
    if isinstance(value, tuple):
        return {
            _TAG: "tuple",
            "v": [encode_value(v, f"{path}[{i}]") for i, v in enumerate(value)],
        }
    if isinstance(value, (set, frozenset)):
        encoded = [encode_value(v, f"{path}{{}}") for v in value]
        encoded.sort(key=lambda e: json.dumps(e, sort_keys=True))
        return {_TAG: "frozenset" if isinstance(value, frozenset) else "set", "v": encoded}
    if isinstance(value, _dt.datetime):
        return {_TAG: "datetime", "v": value.isoformat()}
    if isinstance(value, _dt.date):
        return {_TAG: "date", "v": value.isoformat()}
    if isinstance(value, decimal.Decimal):
        return {_TAG: "decimal", "v": str(value)}
    raise DisplayReplayError(
        UNSUPPORTED, f"{path}: value of type {type(value).__name__} cannot be frozen"
    )


def decode_value(value: Any) -> Any:
    if isinstance(value, list):
        return [decode_value(v) for v in value]
    if not isinstance(value, dict):
        return value
    tag = value.get(_TAG)
    if tag is None:
        return {k: decode_value(v) for k, v in value.items()}
    raw = value.get("v")
    if tag == "float":
        return float(raw)
    if tag == "dict":
        return {decode_value(k): decode_value(v) for k, v in raw}
    if tag == "tuple":
        return tuple(decode_value(v) for v in raw)
    if tag == "set":
        return {decode_value(v) for v in raw}
    if tag == "frozenset":
        return frozenset(decode_value(v) for v in raw)
    if tag == "datetime":
        return _dt.datetime.fromisoformat(raw)
    if tag == "date":
        return _dt.date.fromisoformat(raw)
    if tag == "decimal":
        return decimal.Decimal(raw)
    raise DisplayReplayError(INVALID, f"unknown codec tag {tag!r}")


def canonical(value: Any) -> str:
    """One string per value, type-exact (``1``, ``1.0`` and ``True`` differ),
    key-order preserving. The comparison form for every parity check."""
    return json.dumps(encode_value(value), separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Identities
# --------------------------------------------------------------------------- #


def _member(item: Any) -> str:
    from app.utils.feed_cache import feed_edition_member

    return feed_edition_member(item)


def deck_identities(items: Iterable[Any]) -> list[str]:
    return [_member(item) for item in items]


def _check_identities(items: list, *, kinds: frozenset, where: str) -> list[str]:
    idents: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        kind = item.get("type") if isinstance(item, dict) else None
        if kind not in kinds:
            raise DisplayReplayError(
                UNSUPPORTED, f"{where}[{index}]: card kind {kind!r} is not supported"
            )
        ident = _member(item)
        if ident == "?":
            raise DisplayReplayError(
                INVALID, f"{where}[{index}]: {kind} card has no canonical identity"
            )
        if ident in seen:
            raise DisplayReplayError(
                INVALID, f"{where}[{index}]: duplicate identity {ident}"
            )
        seen.add(ident)
        idents.append(ident)
    return idents


def _code_sha() -> Optional[str]:
    for name in ("HEROKU_SLUG_COMMIT", "SOURCE_VERSION", "GIT_COMMIT"):
        value = os.environ.get(name)
        if value:
            return value
    return None


# --------------------------------------------------------------------------- #
# The recorder
# --------------------------------------------------------------------------- #


def display_capture_from_request(request: Any) -> Optional["DiscoverDisplayCapture"]:
    """The armed recorder for this request, or ``None`` (every HTTP request)."""
    scope = getattr(request, "scope", None)
    if not isinstance(scope, dict):
        return None
    capture = scope.get(DISCOVER_DISPLAY_CAPTURE_SCOPE_KEY)
    return capture if isinstance(capture, DiscoverDisplayCapture) else None


def _guarded(method: Callable) -> Callable:
    """Recorder hooks run inside ``/api/feed``: they never raise into it."""

    def wrapper(self: "DiscoverDisplayCapture", *args: Any, **kwargs: Any) -> Any:
        if self.status not in ("armed", "recording"):
            return None
        try:
            return method(self, *args, **kwargs)
        except DisplayReplayError as exc:
            self._refuse(exc.code, exc.detail)
        except Exception as exc:  # pragma: no cover - defensive
            self._refuse(INVALID, f"capture hook {method.__name__} failed: {exc!r}")
        return None

    wrapper.__name__ = method.__name__
    return wrapper


class DiscoverDisplayCapture:
    """Records one anonymous Discover build. Read :meth:`artifact` afterwards.

    ``status`` moves ``armed`` → ``recording`` → ``complete``, or to
    ``refused`` / ``abandoned`` with a reason. Only ``complete`` yields an
    artifact; a request served from any cache never reaches the seam and
    stays ``armed``, which :meth:`artifact` reports as INCOMPLETE.
    """

    def __init__(
        self,
        *,
        origin: str,
        max_bytes: int = DEFAULT_MAX_CAPTURE_BYTES,
        request_id: Optional[str] = None,
    ):
        if origin not in ("production", "local", "synthetic"):
            raise ValueError("origin must be production, local or synthetic")
        self.origin = origin
        self.max_bytes = max_bytes
        self.request_id = request_id
        self.build_id = uuid.uuid4().hex
        self.status = "armed"
        self.refusal: Optional[dict] = None
        self._doc: dict[str, Any] = {}
        self._result: Optional[dict] = None

    # -- state ------------------------------------------------------------- #

    def _refuse(self, code: str, detail: str) -> None:
        if self.status in ("refused", "abandoned"):
            return
        self.status = "refused"
        self.refusal = {"code": code, "detail": detail}
        self._doc = {}

    def abandon(self, reason: str) -> None:
        if self.status in ("armed", "recording"):
            self.status = "abandoned"
            self.refusal = {"code": INCOMPLETE, "detail": f"build abandoned: {reason}"}
            self._doc = {}

    # -- hooks (called by get_feed) ----------------------------------------- #

    @_guarded
    def record_chain_entry(
        self, items: list, *, chain_kwargs: dict, request_facts: dict
    ) -> None:
        from app.utils.personalization import PersonalizationContext

        self.status = "recording"
        facts = dict(request_facts)
        refusals = []
        if chain_kwargs.get("sports_mode"):
            refusals.append("Sports-mode builds (SPORTS FIRST CAPTURE UNSUPPORTED)")
        if (facts.get("mode") or "").lower() != "discover":
            refusals.append(f"mode={facts.get('mode')!r} is not the Discover build")
        for name in ("sport", "category", "tags"):
            if facts.get(name) is not None:
                refusals.append(f"{name} filter is a browse, not Discover")
        if not facts.get("include_events") or not facts.get("include_futures"):
            refusals.append("Discover carries both events and futures")
        if chain_kwargs.get("my_teams_only"):
            refusals.append("my_teams_only")
        if facts.get("debug") or facts.get("exclude_reviewed"):
            refusals.append("debug / reviewed-filter builds change the build")
        if chain_kwargs.get("reviewed_keys") is not None:
            refusals.append("reviewed-key filtering")
        if facts.get("principal_user") or facts.get("principal_session"):
            refusals.append("a user or session principal (personalized/session)")
        if chain_kwargs.get("ctx") != PersonalizationContext():
            refusals.append("an active personalization context")
        if refusals:
            raise DisplayReplayError(UNSUPPORTED, "; ".join(refusals))

        pool_ids = _check_identities(items, kinds=SUPPORTED_POOL_KINDS, where="pool")
        if len({id(item) for item in items}) != len(items):
            raise DisplayReplayError(UNSUPPORTED, "pool holds one card object twice")
        now = chain_kwargs.get("now")
        if not isinstance(now, _dt.datetime) or now.tzinfo is None:
            raise DisplayReplayError(INVALID, "the build passed no aware clock to the chain")

        config = facts.pop("discover_config", None)
        self._doc = {
            "schema_version": SCHEMA_VERSION,
            "support": {
                "surface": "discover_anonymous_build",
                "personalized": "unsupported",
                "session_principal": "unsupported",
                "cached_response": "unsupported",
                "sports": "unsupported",
                "filtered_browse": "unsupported",
                "debug_or_reviewed": "unsupported",
                "pinned_edition": "supported_frozen_manifest_and_clock",
                "collections": "supported_frozen_read",
                "venue_settlement": "supported_frozen_per_card_deltas",
            },
            "provenance": {
                "origin": self.origin,
                "code_sha": _code_sha(),
                "request_id": self.request_id,
                "build_id": self.build_id,
                "edition_policy_fingerprint": facts.get("edition_policy"),
                "policy_version": None,
                "policy_version_note": (
                    "no scoring/display policy version exists in the code; "
                    "code_sha + effective_config_digest are the policy identity"
                ),
                "effective_config": encode_value(config, "$.discover_config"),
                "effective_config_digest": _digest(config),
            },
            "clocks": {
                "scoring_now": now.isoformat(),
                "chain_entry_wall": time.time(),
                "source_and_feature_timestamps": "retained unchanged inside each card",
            },
            "effective_request": encode_value(facts, "$.request"),
            "effective_context": {
                "principal_mode": "anonymous",
                "personalization": "inactive (PersonalizationContext() equality)",
                "cold_start": "derived by the chain from the inactive context",
                "reviewed_keys": None,
            },
            "chain_kwargs": {
                "limit": chain_kwargs["limit"],
                "event_pct": chain_kwargs["event_pct"],
                "include_events": chain_kwargs["include_events"],
                "my_teams_only": chain_kwargs["my_teams_only"],
                "sports_mode": chain_kwargs["sports_mode"],
            },
            "scored_pool": {
                "count": len(items),
                "identities": pool_ids,
                "items": encode_value(items, "$.pool"),
            },
            "downstream": {
                "collections": {"active": bool(facts.get("collections_enabled"))},
                "edition": {"active": False},
                "venue_settlement": None,
            },
            "diagnostics": {"stage_identities": {}},
        }

    @_guarded
    def record_chain_exit(self, items: list, meta: dict) -> None:
        self._require_recording()
        ids = _check_identities(items, kinds=SUPPORTED_DECK_KINDS, where="chain_exit")
        diag = self._doc["diagnostics"]
        diag["stage_identities"]["chain_exit"] = ids
        diag["chain_meta"] = encode_value(meta, "$.chain_meta")

    @_guarded
    def record_collections(self, branch: str, collections: Optional[list]) -> None:
        from app.routes.feed import DISCOVER_COMPOSITION_WINDOW

        self._require_recording()
        frozen = None if collections is None else encode_value(collections, "$.collections")
        self._doc["downstream"]["collections"] = {
            "active": True,
            "branch": branch,
            "page_window": DISCOVER_COMPOSITION_WINDOW,
            "collections": frozen,
        }

    @_guarded
    def record_edition(
        self,
        *,
        manifest: Any,
        requested_policy: str,
        now: float,
        status: str,
        items: list,
    ) -> None:
        self._require_recording()
        self._doc["downstream"]["edition"] = {
            "active": True,
            "manifest": encode_value(manifest, "$.manifest"),
            "requested_policy": requested_policy,
            "now": now,
            "status": status,
        }
        self._doc["diagnostics"]["stage_identities"]["after_edition"] = deck_identities(
            items
        )

    def venue_fields_before(self, items: list) -> Optional[list]:
        if self.status != "recording":
            return None
        try:
            return [_venue_state(item) for item in items]
        except Exception as exc:  # pragma: no cover - defensive
            self._refuse(INVALID, f"venue snapshot failed: {exc!r}")
            return None

    @_guarded
    def record_venue_settlement(
        self, items: list, before: Optional[list], branch: Optional[str]
    ) -> None:
        self._require_recording()
        if before is None or len(before) != len(items):
            raise DisplayReplayError(INCOMPLETE, "venue-settlement snapshot missing")
        deltas = []
        for index, item in enumerate(items):
            after = _venue_state(item)
            if after == before[index]:
                continue
            changes = {}
            for key in VENUE_FIELDS:
                was, now = before[index].get(key, _ABSENT), after.get(key, _ABSENT)
                if was != now:
                    changes[key] = {"before": _absent_enc(was), "after": _absent_enc(now)}
            deltas.append(
                {
                    "position": index,
                    "identity": _member(item),
                    "changes": encode_value(changes, f"$.venue[{index}]"),
                }
            )
        self._doc["downstream"]["venue_settlement"] = {
            "branch": branch,
            "deltas": deltas,
        }

    @_guarded
    def record_response(self, payload: dict, feed_items: list, *, timings: list) -> None:
        self._require_recording()
        if self._doc["downstream"]["venue_settlement"] is None:
            raise DisplayReplayError(INCOMPLETE, "venue settlement was never recorded")
        deck_ids = _check_identities(
            feed_items, kinds=SUPPORTED_DECK_KINDS, where="served_deck"
        )
        self._doc["clocks"]["response_wall"] = time.time()
        self._doc["clocks"]["stage_timings_ms"] = encode_value(timings, "$.timings")
        self._doc["clocks"]["cache_metadata"] = encode_value(
            payload.get(CACHE_METADATA_FIELD), "$.cache"
        )
        self._doc["expected"] = {
            "full_deck_identities": deck_ids,
            "total": len(feed_items),
            "full_public_deck_digest": _digest(feed_items),
            "public_response": encode_value(payload, "$.response"),
        }
        doc = self._doc
        size = len(json.dumps(doc, separators=(",", ":"), allow_nan=False))
        if size > self.max_bytes:
            raise DisplayReplayError(
                INCOMPLETE,
                f"capture is {size} bytes, over the {self.max_bytes}-byte bound; "
                "refused rather than truncated",
            )
        doc["size_bytes"] = size
        self._result = doc
        self.status = "complete"

    # -- read --------------------------------------------------------------- #

    def _require_recording(self) -> None:
        if self.status != "recording":
            raise DisplayReplayError(INCOMPLETE, "hook fired before the chain entry")

    def artifact(self) -> dict:
        if self.status == "complete" and self._result is not None:
            return self._result
        if self.refusal is not None:
            raise DisplayReplayError(self.refusal["code"], self.refusal["detail"])
        raise DisplayReplayError(
            INCOMPLETE,
            "the request never reached a returned build (served from a cache tier, "
            "refused early, or raised)",
        )


class _Absent:
    def __repr__(self) -> str:  # pragma: no cover
        return "<absent>"


_ABSENT = _Absent()


def _absent_enc(value: Any) -> dict:
    return {"absent": True} if value is _ABSENT else {"value": value}


def _venue_state(item: Any) -> dict:
    data = item.get("data") if isinstance(item, dict) else None
    if not isinstance(data, dict):
        return {}
    return {key: copy.deepcopy(data[key]) for key in VENUE_FIELDS if key in data}


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

_REQUIRED_TOP = {
    "schema_version",
    "support",
    "provenance",
    "clocks",
    "effective_request",
    "effective_context",
    "chain_kwargs",
    "scored_pool",
    "downstream",
    "diagnostics",
    "expected",
    "size_bytes",
}


def load_capture(source: Any, *, max_bytes: int = DEFAULT_MAX_CAPTURE_BYTES) -> dict:
    """Strictly validate a capture (a dict, or a path to its JSON).

    Refuses an unknown schema, a missing or unknown top-level key, a pool whose
    identities disagree with its own cards, and any unsupported card kind or
    duplicate identity — before anything is replayed.
    """
    if isinstance(source, (str, os.PathLike)):
        size = os.path.getsize(source)
        if size > max_bytes:
            raise DisplayReplayError(
                INVALID, f"capture file is {size} bytes, over the {max_bytes}-byte bound"
            )
        with open(source, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    else:
        doc = source
    if not isinstance(doc, dict):
        raise DisplayReplayError(INVALID, "capture is not an object")
    if doc.get("schema_version") != SCHEMA_VERSION:
        raise DisplayReplayError(
            INVALID, f"schema_version {doc.get('schema_version')!r} != {SCHEMA_VERSION}"
        )
    keys = set(doc)
    if keys != _REQUIRED_TOP:
        raise DisplayReplayError(
            INVALID,
            f"missing keys {sorted(_REQUIRED_TOP - keys)}; unknown keys "
            f"{sorted(keys - _REQUIRED_TOP)}",
        )
    if doc["effective_context"].get("principal_mode") != "anonymous":
        raise DisplayReplayError(UNSUPPORTED, "only anonymous captures replay")
    if doc["chain_kwargs"].get("sports_mode") or doc["chain_kwargs"].get("my_teams_only"):
        raise DisplayReplayError(UNSUPPORTED, "Sports / My Stuff captures do not replay")
    pool = decode_value(doc["scored_pool"]["items"])
    ids = _check_identities(pool, kinds=SUPPORTED_POOL_KINDS, where="pool")
    if ids != doc["scored_pool"]["identities"] or len(pool) != doc["scored_pool"]["count"]:
        raise DisplayReplayError(INVALID, "pool identities disagree with the pool's cards")
    downstream = doc["downstream"]
    if downstream.get("venue_settlement") is None:
        raise DisplayReplayError(INCOMPLETE, "venue settlement input missing")
    collections = downstream.get("collections") or {}
    if collections.get("active") and "branch" not in collections:
        raise DisplayReplayError(INCOMPLETE, "collections were active but never recorded")
    expected = doc["expected"]
    if len(expected["full_deck_identities"]) != expected["total"]:
        raise DisplayReplayError(INVALID, "expected deck length disagrees with total")
    return doc


# --------------------------------------------------------------------------- #
# Offline guard
# --------------------------------------------------------------------------- #


@contextmanager
def offline():
    """Refuse every socket and every SQLAlchemy execute for the duration.

    A replay that hydrates anything — a price, a row, a publication read — is
    replaying today, not the capture. This turns that into an error.
    """

    def _refuse(*_a: Any, **_k: Any) -> Any:
        raise DisplayReplayError(OFFLINE_VIOLATION, "network or database access attempted")

    async def _refuse_async(*_a: Any, **_k: Any) -> Any:
        _refuse()

    patches: list[tuple[Any, str, Any]] = [
        (socket.socket, "connect", _refuse),
        (socket.socket, "connect_ex", _refuse),
        (socket, "create_connection", _refuse),
        (socket, "getaddrinfo", _refuse),
    ]
    try:
        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlalchemy.orm import Session

        patches += [
            (AsyncSession, "execute", _refuse_async),
            (AsyncSession, "scalar", _refuse_async),
            (AsyncSession, "scalars", _refuse_async),
            (Session, "execute", _refuse),
        ]
    except ImportError:  # pragma: no cover
        pass
    saved = [(owner, name, getattr(owner, name)) for owner, name, _ in patches]
    try:
        for owner, name, repl in patches:
            setattr(owner, name, repl)
        yield
    finally:
        for owner, name, original in saved:
            setattr(owner, name, original)


# --------------------------------------------------------------------------- #
# Replay
# --------------------------------------------------------------------------- #


def replay_capture(
    capture: dict, *, arm: Optional[Callable[[list], list]] = None
) -> dict:
    """Run one arm of a validated capture offline. Returns the replayed deck,
    page and diagnostics. ``arm`` (a candidate policy) receives a fresh decoded
    copy of the pool; the baseline arm is ``arm=None``.

    Never consults ``capture['expected']`` — that is the oracle, read only by
    :func:`verify_baseline`.
    """
    from app.routes import feed as feed_route
    from app.utils.feed_collections import COLLECTIONS_READ, insert_feed_collections
    from app.utils.feed_editions import EDITION_STATUS_PINNED, apply_pinned_edition
    from app.utils.personalization import PersonalizationContext

    kw = capture["chain_kwargs"]
    request = decode_value(capture["effective_request"])
    now = _dt.datetime.fromisoformat(capture["clocks"]["scoring_now"])
    pool = decode_value(capture["scored_pool"]["items"])
    if arm is not None:
        pool = arm(pool)
    stages: dict[str, list[str]] = {"pool": deck_identities(pool)}

    with offline():
        items, meta = feed_route.apply_discover_display_chain(
            pool,
            limit=kw["limit"],
            ctx=PersonalizationContext(),
            event_pct=kw["event_pct"],
            include_events=kw["include_events"],
            my_teams_only=kw["my_teams_only"],
            sports_mode=kw["sports_mode"],
            reviewed_keys=None,
            now=now,
        )
        stages["chain_exit"] = deck_identities(items)

        collections = capture["downstream"]["collections"]
        if collections.get("active") and collections.get("branch") == COLLECTIONS_READ:
            items = insert_feed_collections(
                items,
                decode_value(collections["collections"]),
                rank_key=feed_route._rank_key,
                page_window=collections["page_window"],
            )

        edition_status = None
        edition = capture["downstream"]["edition"]
        if edition.get("active"):
            pinned, edition_status = apply_pinned_edition(
                items,
                decode_value(edition["manifest"]),
                requested_policy=edition["requested_policy"],
                now=edition["now"],
            )
            if edition_status == EDITION_STATUS_PINNED and pinned is not None:
                items = pinned
        stages["pre_slice"] = deck_identities(items)

        total = len(items)
        offset, limit = request["offset"], request["limit"]
        paginated = items[offset : offset + limit]

        _apply_venue_deltas(items, capture["downstream"]["venue_settlement"])

        for item in items:
            feed_route._publish_feed_item(item)
        payload = feed_route._feed_page_payload(
            items,
            paginated,
            total=total,
            limit=limit,
            offset=offset,
            edition_status=edition_status,
        )
        # The route adds these only for a degraded build, from the futures
        # stage's outcome — an upstream fact, carried and declared as such.
        if request.get("build_quality") != "complete":
            for field in UPSTREAM_CARRIED_FIELDS:
                payload[field] = request.get(field)

    return {
        "deck": items,
        "deck_identities": deck_identities(items),
        "total": total,
        "public_response": payload,
        "chain_meta": meta,
        "stage_identities": stages,
    }


def _apply_venue_deltas(items: list, venue: dict) -> None:
    for delta in venue.get("deltas") or []:
        position = delta["position"]
        if position >= len(items) or _member(items[position]) != delta["identity"]:
            raise DisplayReplayError(
                MISMATCH,
                f"venue delta for {delta['identity']} expects position {position}, "
                "which the replayed deck does not hold",
            )
        data = items[position]["data"]
        for key, change in decode_value(delta["changes"]).items():
            before = change["before"]
            if before.get("absent"):
                if key in data:
                    raise DisplayReplayError(
                        MISMATCH, f"{delta['identity']}.{key} present before the delta"
                    )
            elif key not in data or canonical(data[key]) != canonical(before["value"]):
                raise DisplayReplayError(
                    MISMATCH, f"{delta['identity']}.{key} differs before the delta"
                )
            after = change["after"]
            if after.get("absent"):
                data.pop(key, None)
            else:
                data[key] = after["value"]


def _first_divergence(a: list, b: list) -> Optional[int]:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return None if len(a) == len(b) else min(len(a), len(b))


def _scope_statement(capture: dict) -> dict:
    return {
        "proves": (
            "assembly from the captured scored-pool seam through the display chain, "
            "collections, edition pin, venue settlement and publication reproduces "
            "the served deck and page"
        ),
        "not_replayed": [
            "upstream admission and scoring (the pool is taken as scored)",
            "browser-painted order",
            "cache metadata clocks (recorded verbatim under clocks.cache_metadata)",
        ],
        "unsupported": [
            k for k, v in capture["support"].items() if v == "unsupported"
        ],
        "origin": capture["provenance"]["origin"],
        "carried_not_replayed": list(UPSTREAM_CARRIED_FIELDS),
    }


def verify_baseline(source: Any) -> dict:
    """Load, replay the baseline arm, and compare to the capture's oracle.

    ``verdict`` is ``PASS`` only when the full pre-slice identity sequence, the
    total, the digest of the full public deck and the returned page (minus the
    cache clocks) all match exactly. Any refusal or mismatch is a non-PASS
    verdict with its reason, and carries no metrics.
    """
    try:
        capture = load_capture(source)
        replay = replay_capture(capture)
        return _compare(capture, replay)
    except DisplayReplayError as exc:
        return {"verdict": exc.code, "detail": exc.detail}


def _compare(capture: dict, replay: dict) -> dict:
    expected = capture["expected"]
    captured_chain_exit = capture["diagnostics"]["stage_identities"].get("chain_exit")
    report: dict[str, Any] = {
        "scope": _scope_statement(capture),
        "pool_count": capture["scored_pool"]["count"],
        "expected_total": expected["total"],
        "replayed_total": replay["total"],
        # Diagnosis only: where a mismatch first appears. The chain's own exit
        # is compared before the downstream stages so a divergence can be
        # pinned to the chain or to what follows it.
        "stage_counts": {
            "chain_exit": {
                "captured": len(captured_chain_exit or []),
                "replayed": len(replay["stage_identities"]["chain_exit"]),
            },
            "pre_slice": {"captured": expected["total"], "replayed": replay["total"]},
        },
        "chain_exit_matches": captured_chain_exit
        == replay["stage_identities"]["chain_exit"],
    }
    want, got = expected["full_deck_identities"], replay["deck_identities"]
    divergence = _first_divergence(want, got)
    if divergence is not None:
        report.update(
            verdict=MISMATCH,
            detail="full pre-slice identity sequence differs",
            first_divergence=divergence,
            expected_at=want[divergence] if divergence < len(want) else None,
            replayed_at=got[divergence] if divergence < len(got) else None,
        )
        return report
    if expected["total"] != replay["total"]:
        report.update(verdict=MISMATCH, detail="total differs")
        return report
    if expected["full_public_deck_digest"] != _digest(replay["deck"]):
        report.update(
            verdict=MISMATCH,
            detail="same identities, different public card content in the full deck",
            first_differing_identity=_first_content_divergence(capture, replay),
        )
        return report
    want_page = decode_value(expected["public_response"])
    want_page.pop(CACHE_METADATA_FIELD, None)
    if canonical(want_page) != canonical(replay["public_response"]):
        report.update(verdict=MISMATCH, detail="returned page or envelope differs")
        return report
    report.update(verdict=PASS, page_items=len(replay["public_response"]["items"]))
    return report


def _first_content_divergence(capture: dict, replay: dict) -> Optional[str]:
    page = decode_value(capture["expected"]["public_response"]).get("items") or []
    by_id = {_member(item): item for item in page}
    for item in replay["deck"]:
        ident = _member(item)
        if ident in by_id and canonical(by_id[ident]) != canonical(item):
            return ident
    return None


def write_capture(capture: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(capture, fh, separators=(",", ":"), allow_nan=False)
