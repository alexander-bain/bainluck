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
6. ``provenance.capture_mode`` says HOW the build was obtained. The default
   is an ordinary anonymous request, which a warm cache tier serves without
   reaching the seam — so it refuses, and cached output is never promoted to a
   capture. The explicit operator mode (:data:`CAPTURE_MODE_WARM_RAIL`) arms
   the existing LAT-P001 pre-warm scope marker, so the route rebuilds exactly
   as the warm rail does. Its provenance declares that: an operator-triggered
   rebuild with the route's ordinary publication effects, NOT a public request
   that was served.
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

#: v2 (#10290 warm-capture): adds ``provenance.capture_mode`` +
#: ``provenance.operational``, ``clocks.armed_wall`` and
#: ``expected.returned_build_digest``. No v1 artifact was ever produced (the
#: sole production attempt refused before capture), so v1 is not read.
SCHEMA_VERSION = "mixed_display_replay_v2"

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

#: How a capture obtained its build. Closed set; the loader refuses any other.
CAPTURE_MODE_ORDINARY = "ordinary_anonymous_request"
CAPTURE_MODE_WARM_RAIL = "operator_warm_rail_rebuild"
CAPTURE_MODES = frozenset({CAPTURE_MODE_ORDINARY, CAPTURE_MODE_WARM_RAIL})

#: The operational declaration of an ordinary capture, required verbatim.
_ORDINARY_OPERATIONAL = {
    "kind": CAPTURE_MODE_ORDINARY,
    "cache_reads": (
        "ordinary: a request a cache tier serves never reaches the seam and "
        "refuses as INCOMPLETE"
    ),
}

#: The fixed half of an operator warm-rail capture's operational declaration,
#: required verbatim. The variable half (the age bound, publication
#: eligibility, the key write-back) is type- and consistency-checked.
_WARM_RAIL_DECLARED = {
    "kind": CAPTURE_MODE_WARM_RAIL,
    "trigger": (
        "operator-invoked in-process request carrying the existing LAT-P001 "
        "pre-warm scope marker (feed_cache.FEED_PREWARM_SCOPE_KEY); no header, "
        "query or HTTP request can set it"
    ),
    "claims": {
        "public_request_served": False,
        "upstream_admission_and_scoring_replayed": False,
    },
    "cache_reads": (
        "skipped by the route for this rebuild: response fresh, :stale and "
        "page-base tiers; shared input artifacts read only under the age bound"
    ),
    "publication_effects": [
        "response cache fresh + :stale entries under the resolved anonymous key, "
        "on the build's ordinary TTLs",
        "offset-independent page base (LAT-P141) when page-base publication is on",
        "edition manifest for this build's ordering (#5102)",
        "process-local last-good for the resolved key",
        "shared input artifacts rebuilt under the bound, republished on their "
        "namespace TTLs",
    ],
    "publication_completion": (
        "not observed: the route schedules publication in the background; "
        "a degraded build publishes nothing"
    ),
    "warm_rail_task_side_effects": (
        "not run: the warm-rail task's own report, refusal gates and "
        "served-market record are outside this capture"
    ),
}
_WARM_RAIL_VARIABLE_KEYS = {
    "shared_artifact_max_age_s",
    "publication_eligible",
    "resolved_cache_key_written_back",
}

# Refusal / verdict codes.
UNSUPPORTED = "UNSUPPORTED"
INCOMPLETE = "INCOMPLETE"
INVALID = "INVALID"
MISMATCH = "MISMATCH"
OFFLINE_VIOLATION = "OFFLINE_VIOLATION"
PASS = "PASS"

_TAG = "__bl_t__"

#: What a capture declares it supports. Written by the recorder and required
#: verbatim by the loader: a capture claiming any other support is refused.
_SUPPORT = {
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
}

#: The only principal context a capture may carry.
_ANONYMOUS_CONTEXT = {
    "principal_mode": "anonymous",
    "personalization": "inactive (PersonalizationContext() equality)",
    "cold_start": "derived by the chain from the inactive context",
    "reviewed_keys": None,
}


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


def capture_request(capture: "DiscoverDisplayCapture") -> Any:
    """An in-process, anonymous ``/api/feed`` request carrying ``capture``.

    The pre-warm's synthetic request: no headers (so no session or user
    principal), no query, never sent over a network. An ordinary capture
    carries NO pre-warm marker, so any cache tier may serve it (and the
    capture then refuses). Only an explicit operator warm-rail capture carries
    the existing ``FEED_PREWARM_SCOPE_KEY`` — the warm rail's own rebuild.
    """
    from starlette.requests import Request

    from app.utils.feed_cache import FEED_PREWARM_SCOPE_KEY

    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/api/feed",
        "headers": [],
        "query_string": b"",
        DISCOVER_DISPLAY_CAPTURE_SCOPE_KEY: capture,
    }
    if capture.mode == CAPTURE_MODE_WARM_RAIL:
        scope[FEED_PREWARM_SCOPE_KEY] = True
    request = Request(scope)
    capture._scope = request.scope
    return request


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

    ``mode`` defaults to the ordinary anonymous request. The operator
    warm-rail mode only works through :func:`capture_request`, which is the
    one place the pre-warm marker is set.
    """

    def __init__(
        self,
        *,
        origin: str,
        max_bytes: int = DEFAULT_MAX_CAPTURE_BYTES,
        request_id: Optional[str] = None,
        mode: str = CAPTURE_MODE_ORDINARY,
    ):
        if origin not in ("production", "local", "synthetic"):
            raise ValueError("origin must be production, local or synthetic")
        if mode not in CAPTURE_MODES:
            raise ValueError(f"mode must be one of {sorted(CAPTURE_MODES)}")
        self.origin = origin
        self.mode = mode
        self.armed_wall = time.time()
        self._scope: Optional[dict] = None
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
        operational = self._operational_at_entry()

        pool_ids = _check_identities(items, kinds=SUPPORTED_POOL_KINDS, where="pool")
        if len({id(item) for item in items}) != len(items):
            raise DisplayReplayError(UNSUPPORTED, "pool holds one card object twice")
        now = chain_kwargs.get("now")
        if not isinstance(now, _dt.datetime) or now.tzinfo is None:
            raise DisplayReplayError(INVALID, "the build passed no aware clock to the chain")

        config = facts.pop("discover_config", None)
        self._doc = {
            "schema_version": SCHEMA_VERSION,
            "support": dict(_SUPPORT),
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
                "capture_mode": self.mode,
                "operational": operational,
            },
            "clocks": {
                "armed_wall": self.armed_wall,
                "scoring_now": now.isoformat(),
                "chain_entry_wall": time.time(),
                "source_and_feature_timestamps": "retained unchanged inside each card",
            },
            "effective_request": encode_value(facts, "$.request"),
            "effective_context": dict(_ANONYMOUS_CONTEXT),
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

    def _operational_at_entry(self) -> dict:
        """The mode's declaration, read from the route's own state at the seam.

        The age bound is the ContextVar the route binds ONLY on its pre-warm
        branch, so its presence is the proof the marker was honoured — and its
        absence is required of an ordinary build, which would otherwise have
        been built under a narrower shared-input read than an ordinary request.
        """
        from app.utils import principal_independent_cache as _pic
        from app.utils.feed_cache import FEED_PREWARM_SCOPE_KEY

        bound = _pic.max_shared_age_s()
        marker = bool(self._scope and self._scope.get(FEED_PREWARM_SCOPE_KEY))
        if self.mode == CAPTURE_MODE_ORDINARY:
            if marker or bound is not None:
                raise DisplayReplayError(
                    UNSUPPORTED,
                    "an ordinary capture saw the pre-warm marker or a bound "
                    "shared-artifact age: not an ordinary anonymous build",
                )
            return dict(_ORDINARY_OPERATIONAL)
        if not marker:
            raise DisplayReplayError(
                INVALID, "operator warm-rail mode must be armed by capture_request"
            )
        if not _is_number(bound) or not math.isfinite(bound) or bound < 0:
            raise DisplayReplayError(
                INCOMPLETE,
                "operator warm-rail mode: the route bound no shared-artifact age, "
                "so the pre-warm marker was not honoured",
            )
        return {**copy.deepcopy(_WARM_RAIL_DECLARED), "shared_artifact_max_age_s": bound}

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
            "returned_build_digest": _digest(payload),
        }
        if self.mode == CAPTURE_MODE_WARM_RAIL:
            from app.utils.feed_cache import FEED_PREWARM_KEY_SCOPE_KEY

            request = decode_value(self._doc["effective_request"])
            keyed = request.get("cache_status") in _KEYED_CACHE_STATUSES
            operational = self._doc["provenance"]["operational"]
            operational["resolved_cache_key_written_back"] = bool(
                self._scope and FEED_PREWARM_KEY_SCOPE_KEY in self._scope
            )
            operational["publication_eligible"] = bool(
                keyed and request.get("build_quality") == "complete"
            )
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


# --------------------------------------------------------------------------- #
# Refusal disposition — what a non-capture can say about itself
# --------------------------------------------------------------------------- #
#
# A refused capture writes no artifact, so the only evidence of WHICH branch
# returned is what the route already stamps on the Response and the payload's
# cache block. Every value is read through a closed allowlist (anything else is
# reported as "unrecognized"), so the disposition can never carry credentials,
# the candidate pool or an arbitrary response body.

#: Every ``X-Feed-Cache`` value ``get_feed`` writes.
FEED_CACHE_DISPOSITIONS = frozenset(
    {
        "hit",
        "stale_hit",
        "shared_hit",
        "shared_stale_hit",
        "page_base_hit",
        "page_base_stale_hit",
        "last_good",
        "coalesced",
        "unavailable",
        "miss",
        "error",
        "disabled",
        "disabled_debug",
        "disabled_reviewed_filter",
    }
)
#: The dispositions that return a payload some earlier build produced.
CACHED_EARLY_RETURNS = frozenset(
    {
        "hit",
        "stale_hit",
        "shared_hit",
        "shared_stale_hit",
        "page_base_hit",
        "page_base_stale_hit",
        "last_good",
        "coalesced",
    }
)
FEED_SINGLEFLIGHT_STATES = frozenset(
    {"leader", "coalesced", "waiter_last_good", "waiter_unavailable", "none"}
)
#: Every ``cache.reason`` value ``get_feed`` writes.
FEED_CACHE_REASONS = frozenset(
    {
        "inert_principal",
        "input_age_ceiling",
        "leader_unavailable",
        "page_base",
        "redis_unavailable",
    }
)
_RECORDER_STATES = frozenset({"armed", "recording", "complete", "refused", "abandoned"})
_VERDICT_CODES = frozenset({UNSUPPORTED, INCOMPLETE, INVALID, MISMATCH, OFFLINE_VIOLATION})


def _allowlisted(value: Any, allowed: frozenset) -> Optional[str]:
    if value is None:
        return None
    return value if isinstance(value, str) and value in allowed else "unrecognized"


def refusal_disposition(
    capture: "DiscoverDisplayCapture", *, response_headers: Any, payload: Any
) -> dict:
    """A bounded, allowlisted account of why ``capture`` holds no artifact.

    ``response_headers`` is the retained Response's headers (case-insensitive
    ``.get``); ``payload`` is what ``get_feed`` returned. Only coarse states
    leave: header values, the payload's cache status/reason, and the
    recorder's own state and verdict code.
    """
    get = getattr(response_headers, "get", None)
    header = (lambda name: get(name)) if callable(get) else (lambda name: None)
    cache_block = payload.get(CACHE_METADATA_FIELD) if isinstance(payload, dict) else None
    if not isinstance(cache_block, dict):
        cache_block = {}
    x_cache = _allowlisted(header("x-feed-cache"), FEED_CACHE_DISPOSITIONS)
    status = _allowlisted(capture.status, _RECORDER_STATES)
    code = (capture.refusal or {}).get("code")
    if status == "armed":
        if x_cache in CACHED_EARLY_RETURNS:
            classification = "cache_tier_early_return"
        elif x_cache == "unavailable":
            classification = "unavailable_terminal"
        else:
            classification = "returned_before_seam"
    else:
        classification = {
            "recording": "seam_reached_no_returned_build",
            "refused": "recorder_refused",
            "abandoned": "build_abandoned",
            "complete": "complete",
        }.get(status, "unrecognized")
    return {
        "classification": classification,
        "capture_mode": _allowlisted(capture.mode, CAPTURE_MODES),
        "recorder_status": status,
        "refusal_code": _allowlisted(code, _VERDICT_CODES),
        "x_feed_cache": x_cache,
        "x_feed_singleflight": _allowlisted(
            header("x-feed-singleflight"), FEED_SINGLEFLIGHT_STATES
        ),
        "payload_cache_status": _allowlisted(
            cache_block.get("status"), FEED_CACHE_DISPOSITIONS
        ),
        "payload_cache_reason": _allowlisted(cache_block.get("reason"), FEED_CACHE_REASONS),
    }


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
    _exact_keys(doc, _REQUIRED_TOP, "capture")
    validate_replay_inputs(doc)
    expected = doc["expected"]
    _exact_keys(expected, _EXPECTED_KEYS, "expected")
    if not isinstance(expected["full_deck_identities"], list) or not _is_int(
        expected["total"]
    ):
        raise DisplayReplayError(INVALID, "expected deck identities / total malformed")
    if len(expected["full_deck_identities"]) != expected["total"]:
        raise DisplayReplayError(INVALID, "expected deck length disagrees with total")
    if expected["returned_build_digest"] != _digest(
        decode_value(expected["public_response"])
    ):
        raise DisplayReplayError(
            INVALID, "returned_build_digest disagrees with the returned build"
        )
    return doc


# The closed replay contract (#10290 review). Every input the replay reads —
# and every request/context fact that decides WHETHER the capture is a
# supported build — is checked against the values the recorder can write for a
# supported build. Anything else (an unknown branch, a browse filter, a missing
# input, two blocks that disagree) refuses with a typed verdict before a single
# stage runs. The replay itself dispatches only on these closed sets, so a
# capture cannot reach PASS by naming a branch the replay silently skips.

_EXPECTED_KEYS = {
    "full_deck_identities",
    "total",
    "full_public_deck_digest",
    "public_response",
    "returned_build_digest",
}
_REQUEST_KEYS = {
    "mode",
    "sport",
    "category",
    "tags",
    "include_events",
    "include_futures",
    "my_teams_only",
    "event_pct",
    "limit",
    "offset",
    "edition",
    "debug",
    "exclude_reviewed",
    "principal_user",
    "principal_session",
    "cache_status",
    "build_quality",
    "degraded_reason",
    "collections_enabled",
    "edition_policy",
}
_CHAIN_KWARG_KEYS = {"limit", "event_pct", "include_events", "my_teams_only", "sports_mode"}
_PROVENANCE_KEYS = {
    "origin",
    "code_sha",
    "request_id",
    "build_id",
    "edition_policy_fingerprint",
    "policy_version",
    "policy_version_note",
    "effective_config",
    "effective_config_digest",
    "capture_mode",
    "operational",
}
_CLOCK_KEYS = {
    "armed_wall",
    "scoring_now",
    "chain_entry_wall",
    "source_and_feature_timestamps",
    "response_wall",
    "stage_timings_ms",
    "cache_metadata",
}
_POOL_KEYS = {"count", "identities", "items"}
_DOWNSTREAM_KEYS = {"collections", "edition", "venue_settlement"}
_COLLECTIONS_ACTIVE_KEYS = {"active", "branch", "page_window", "collections"}
_EDITION_ACTIVE_KEYS = {"active", "manifest", "requested_policy", "now", "status"}
_VENUE_KEYS = {"branch", "deltas"}
_VENUE_DELTA_KEYS = {"position", "identity", "changes"}

#: Cache states a build that reached the seam can carry. The two
#: ``disabled_*`` states belong to debug / reviewed builds, refused at capture.
_REPLAYABLE_CACHE_STATUSES = frozenset({"disabled", "miss", "error"})
#: The states in which the route resolved a response-cache key — the only
#: states its pre-warm branch writes the key back and publication can run.
_KEYED_CACHE_STATUSES = frozenset({"miss", "error"})
_BUILD_QUALITIES = frozenset({"complete", "degraded"})
_DEGRADED_REASONS = frozenset(
    {"futures_skipped_budget", "futures_timeout", "futures_error"}
)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _exact_keys(block: Any, keys: set, where: str) -> None:
    if not isinstance(block, dict):
        raise DisplayReplayError(INVALID, f"{where} is not an object")
    have = set(block)
    if have != keys:
        raise DisplayReplayError(
            INVALID,
            f"{where}: missing keys {sorted(keys - have)}; unknown keys "
            f"{sorted(have - keys)}",
        )


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise DisplayReplayError(code, detail)


def validate_replay_inputs(capture: dict) -> None:
    """Refuse a capture the replay cannot reproduce faithfully.

    Reads everything except ``expected`` (the oracle), so :func:`replay_capture`
    runs it too without ever consulting the answer.
    """
    from app.routes.feed import (
        DISCOVER_COMPOSITION_WINDOW,
        VENUE_ATTACH_FAILED_OPEN,
        VENUE_ATTACH_NOTHING_ASKABLE,
        VENUE_ATTACH_READ,
    )
    from app.utils.feed_collections import (
        COLLECTIONS_NO_BUDGET,
        COLLECTIONS_NO_PAGE_GAMES,
        COLLECTIONS_READ,
        COLLECTIONS_READ_FAILED,
    )
    from app.utils.feed_editions import (
        EDITION_STATUS_EXPIRED,
        EDITION_STATUS_INVALIDATED,
        EDITION_STATUS_PINNED,
        EDITION_STATUS_SUPERSEDED,
        EDITION_STATUS_UNPINNED,
    )

    if not isinstance(capture, dict) or capture.get("schema_version") != SCHEMA_VERSION:
        raise DisplayReplayError(INVALID, f"not a {SCHEMA_VERSION} capture")
    for key in _REQUIRED_TOP - {"expected"}:
        _require(key in capture, INVALID, f"capture is missing {key!r}")

    _require(capture["support"] == _SUPPORT, UNSUPPORTED,
             "support declaration differs from the supported anonymous build")
    _require(capture["effective_context"] == _ANONYMOUS_CONTEXT, UNSUPPORTED,
             "only the anonymous, inactive-personalization context replays")

    provenance = capture["provenance"]
    _exact_keys(provenance, _PROVENANCE_KEYS, "provenance")
    _require(provenance["origin"] in ("production", "local", "synthetic"), INVALID,
             f"provenance.origin {provenance['origin']!r} is not a known origin")
    _require(
        _digest(decode_value(provenance["effective_config"]))
        == provenance["effective_config_digest"],
        INVALID,
        "effective_config disagrees with its digest",
    )

    clocks = capture["clocks"]
    _exact_keys(clocks, _CLOCK_KEYS, "clocks")
    _require(_is_number(clocks["armed_wall"]), INVALID, "clocks.armed_wall is not a number")
    try:
        scoring_now = _dt.datetime.fromisoformat(clocks["scoring_now"])
    except (TypeError, ValueError):
        raise DisplayReplayError(INVALID, "clocks.scoring_now is not an ISO datetime")
    _require(scoring_now.tzinfo is not None, INVALID, "clocks.scoring_now is naive")

    # -- the request: exactly the Discover build's facts ------------------- #
    request = decode_value(capture["effective_request"])
    _exact_keys(request, _REQUEST_KEYS, "effective_request")
    _require(isinstance(request["mode"], str) and request["mode"].lower() == "discover",
             UNSUPPORTED, f"mode={request['mode']!r} is not the Discover build")
    for name in ("sport", "category", "tags"):
        _require(request[name] is None, UNSUPPORTED,
                 f"{name} filter is a browse, not Discover")
    _require(request["include_events"] is True and request["include_futures"] is True,
             UNSUPPORTED, "Discover carries both events and futures")
    for name in ("my_teams_only", "debug", "exclude_reviewed",
                 "principal_user", "principal_session", "collections_enabled"):
        _require(isinstance(request[name], bool), INVALID, f"request.{name} is not a bool")
    for name in ("my_teams_only", "debug", "exclude_reviewed",
                 "principal_user", "principal_session"):
        _require(request[name] is False, UNSUPPORTED, f"request.{name} is set")
    _require(_is_int(request["limit"]) and request["limit"] >= 1, INVALID,
             "request.limit is not a positive int")
    _require(_is_int(request["offset"]) and request["offset"] >= 0, INVALID,
             "request.offset is not a non-negative int")
    _require(_is_number(request["event_pct"]), INVALID, "request.event_pct is not a number")
    _require(request["edition"] is None or isinstance(request["edition"], str), INVALID,
             "request.edition is not a token or null")
    _require(isinstance(request["edition_policy"], str), INVALID,
             "request.edition_policy is not a fingerprint")
    _require(provenance["edition_policy_fingerprint"] == request["edition_policy"],
             INVALID, "provenance and request disagree on the edition policy")
    _require(request["cache_status"] in _REPLAYABLE_CACHE_STATUSES, UNSUPPORTED,
             f"cache_status {request['cache_status']!r} is not a replayable build")
    _require(request["build_quality"] in _BUILD_QUALITIES, UNSUPPORTED,
             f"build_quality {request['build_quality']!r} is not known")
    if request["build_quality"] == "complete":
        _require(request["degraded_reason"] is None, INVALID,
                 "a complete build carries a degraded_reason")
    else:
        _require(request["degraded_reason"] in _DEGRADED_REASONS, UNSUPPORTED,
                 f"degraded_reason {request['degraded_reason']!r} is not known")

    _validate_operational(provenance, request)

    # -- chain arguments: agree with the request ---------------------------- #
    kw = capture["chain_kwargs"]
    _exact_keys(kw, _CHAIN_KWARG_KEYS, "chain_kwargs")
    _require(kw["sports_mode"] is False and kw["my_teams_only"] is False, UNSUPPORTED,
             "Sports / My Stuff captures do not replay")
    _require(kw["include_events"] is True, UNSUPPORTED, "Discover carries events")
    for name in ("limit", "event_pct", "my_teams_only", "include_events"):
        _require(canonical(kw[name]) == canonical(request[name]), INVALID,
                 f"chain_kwargs.{name} disagrees with the request")

    # -- the pool ----------------------------------------------------------- #
    scored = capture["scored_pool"]
    _exact_keys(scored, _POOL_KEYS, "scored_pool")
    _require(isinstance(scored["items"], list), INVALID, "scored_pool.items is not a list")
    pool = decode_value(scored["items"])
    ids = _check_identities(pool, kinds=SUPPORTED_POOL_KINDS, where="pool")
    if ids != scored["identities"] or len(pool) != scored["count"]:
        raise DisplayReplayError(INVALID, "pool identities disagree with the pool's cards")

    # -- downstream: closed branch sets, inputs present for the branch ------ #
    downstream = capture["downstream"]
    _exact_keys(downstream, _DOWNSTREAM_KEYS, "downstream")

    collections = downstream["collections"]
    _require(isinstance(collections, dict) and isinstance(collections.get("active"), bool),
             INVALID, "downstream.collections.active is not a bool")
    _require(collections["active"] is request["collections_enabled"], INVALID,
             "collections activity disagrees with request.collections_enabled")
    if collections["active"]:
        _require("branch" in collections, INCOMPLETE,
                 "collections were active but never recorded")
        _exact_keys(collections, _COLLECTIONS_ACTIVE_KEYS, "downstream.collections")
        branch = collections["branch"]
        _require(branch in (COLLECTIONS_READ, COLLECTIONS_READ_FAILED,
                            COLLECTIONS_NO_BUDGET, COLLECTIONS_NO_PAGE_GAMES),
                 UNSUPPORTED, f"collections branch {branch!r} is not supported")
        _require(collections["page_window"] == DISCOVER_COMPOSITION_WINDOW, UNSUPPORTED,
                 f"collections page_window {collections['page_window']!r} is not "
                 f"the route's {DISCOVER_COMPOSITION_WINDOW}")
        if branch == COLLECTIONS_READ:
            _require(isinstance(collections["collections"], list), INCOMPLETE,
                     "collections read branch has no frozen cards")
        else:
            _require(collections["collections"] is None, INVALID,
                     f"collections branch {branch!r} carries cards it never read")
    else:
        _exact_keys(collections, {"active"}, "downstream.collections")

    edition = downstream["edition"]
    _require(isinstance(edition, dict) and isinstance(edition.get("active"), bool),
             INVALID, "downstream.edition.active is not a bool")
    _require(edition["active"] is (request["edition"] is not None), INVALID,
             "edition activity disagrees with request.edition")
    if edition["active"]:
        _exact_keys(edition, _EDITION_ACTIVE_KEYS, "downstream.edition")
        _require(edition["status"] in (EDITION_STATUS_PINNED, EDITION_STATUS_UNPINNED,
                                       EDITION_STATUS_EXPIRED, EDITION_STATUS_SUPERSEDED,
                                       EDITION_STATUS_INVALIDATED),
                 UNSUPPORTED, f"edition status {edition['status']!r} is not supported")
        _require(edition["requested_policy"] == request["edition_policy"], INVALID,
                 "edition requested_policy disagrees with the request")
        _require(_is_number(edition["now"]), INVALID, "edition clock is not a number")
    else:
        _exact_keys(edition, {"active"}, "downstream.edition")

    venue = downstream["venue_settlement"]
    _require(venue is not None, INCOMPLETE, "venue settlement input missing")
    _exact_keys(venue, _VENUE_KEYS, "downstream.venue_settlement")
    _require(venue["branch"] in (VENUE_ATTACH_READ, VENUE_ATTACH_FAILED_OPEN,
                                 VENUE_ATTACH_NOTHING_ASKABLE),
             UNSUPPORTED, f"venue branch {venue['branch']!r} is not supported")
    _require(isinstance(venue["deltas"], list), INVALID, "venue deltas is not a list")
    if venue["branch"] != VENUE_ATTACH_READ:
        _require(venue["deltas"] == [], INVALID,
                 f"venue branch {venue['branch']!r} wrote no cards but carries deltas")
    for index, delta in enumerate(venue["deltas"]):
        _exact_keys(delta, _VENUE_DELTA_KEYS, f"venue.deltas[{index}]")
        _require(_is_int(delta["position"]) and delta["position"] >= 0, INVALID,
                 f"venue.deltas[{index}].position is not a non-negative int")
        changes = decode_value(delta["changes"])
        _require(isinstance(changes, dict) and changes and set(changes) <= set(VENUE_FIELDS),
                 UNSUPPORTED, f"venue.deltas[{index}] changes fields outside {VENUE_FIELDS}")
        for key, change in changes.items():
            _exact_keys(change, {"before", "after"}, f"venue.deltas[{index}].{key}")
            for side in ("before", "after"):
                _require(change[side] in ({"absent": True},) or (
                    isinstance(change[side], dict) and set(change[side]) == {"value"}),
                    INVALID, f"venue.deltas[{index}].{key}.{side} malformed")


def _validate_operational(provenance: dict, request: dict) -> None:
    """The capture mode is a closed set, and each mode's declaration is exact.

    A missing or unknown mode refuses; so does an operator declaration whose
    fixed text differs, whose variable facts are malformed, or whose facts
    disagree with the request the build recorded.
    """
    mode = provenance["capture_mode"]
    _require(mode in CAPTURE_MODES, UNSUPPORTED,
             f"provenance.capture_mode {mode!r} is not a known capture mode")
    operational = provenance["operational"]
    if mode == CAPTURE_MODE_ORDINARY:
        _require(operational == _ORDINARY_OPERATIONAL, INVALID,
                 "ordinary capture's operational declaration differs")
        return
    _exact_keys(operational, set(_WARM_RAIL_DECLARED) | _WARM_RAIL_VARIABLE_KEYS,
                "provenance.operational")
    for key, value in _WARM_RAIL_DECLARED.items():
        _require(operational[key] == value, INVALID,
                 f"operator warm-rail declaration {key!r} differs")
    bound = operational["shared_artifact_max_age_s"]
    _require(_is_number(bound) and math.isfinite(bound) and bound >= 0, INVALID,
             "shared_artifact_max_age_s is not a finite non-negative number")
    for key in ("publication_eligible", "resolved_cache_key_written_back"):
        _require(isinstance(operational[key], bool), INVALID,
                 f"provenance.operational.{key} is not a bool")
    keyed = request["cache_status"] in _KEYED_CACHE_STATUSES
    _require(operational["resolved_cache_key_written_back"] is keyed, INVALID,
             "the key write-back disagrees with request.cache_status")
    _require(
        operational["publication_eligible"]
        is (keyed and request["build_quality"] == "complete"),
        INVALID,
        "publication eligibility disagrees with the request's cache key / build quality",
    )


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

#: #10356 / #5105 — a candidate policy that changes ONE named stage of the
#: shared chain, for an offline arm. ``arm`` can only rewrite the pool; a policy
#: that lives inside the chain (which cards the first page selects) is reached
#: by rebinding that one stage for the duration of the replay, inside the same
#: offline fence, and restoring it afterwards. Never the production default:
#: ``routes/feed.py`` is unchanged and nothing outside a replay passes this.
#: ``cold_start_first_cards``: ``diversify_discover_first_page`` with
#: ``cold_start_window=COLD_START_WINDOW_FIRST_CARDS`` (see that constant).
STAGE_POLICY_COLD_START_FIRST_CARDS = "cold_start_first_cards"

#: #5105 D2 — the variety-promotion comparison. All three run the served
#: ``diversify_discover_first_page`` with its opt-in promotion hook
#: (``feed_market_quality.PromotionGate``) and return the per-seat trace:
#:
#: ``d2_baseline_trace``: an OBSERVER gate — every check is computed and
#: recorded, every promotion is allowed, so the deck is the served one (the
#: parity test asserts it byte for byte against the capture's oracle).
#: ``d2_arm_a``: a variety-only promotion must pass ``_is_clean_replacement_for``
#: at its destination slot (quality class, ladder, silence, and the type-agnostic
#: why-now inside ``FIRST_PAGE_WHY_NOW_WINDOW``) and the score bar its own
#: mechanism already applies (none for a cap-walk seat).
#: ``d2_arm_b``: A, plus ``lacks_a_why_now`` (the type-scoped clause-(d) check:
#: futures and bundles) at every first-page slot, plus a DEFINED bar — the
#: higher of the card's category hunger threshold and the required-archetype
#: bar, for whichever of the two applies to it. A card to which neither applies
#: has no defined bar and is NOT variety-promotable under B: it keeps ordinary
#: rank-earned seats only ("unbarred categories still earn ordinary ranked
#: seats"), and no threshold is invented for it.
#:
#: Ordinary rank-earned seats are never gated. Nothing outside this module
#: passes a gate; ``routes/feed.py`` is unchanged.
STAGE_POLICY_D2_BASELINE_TRACE = "d2_baseline_trace"
STAGE_POLICY_D2_ARM_A = "d2_arm_a"
STAGE_POLICY_D2_ARM_B = "d2_arm_b"
D2_POLICIES = (
    STAGE_POLICY_D2_BASELINE_TRACE,
    STAGE_POLICY_D2_ARM_A,
    STAGE_POLICY_D2_ARM_B,
)
STAGE_POLICIES = frozenset({STAGE_POLICY_COLD_START_FIRST_CARDS, *D2_POLICIES})


def d2_defined_bar(card: dict) -> Optional[int]:
    """Arm B's bar for ``card``: the higher of the existing bars that apply to it.

    The category hunger threshold when the card's category has one, and the
    required-archetype bar when its archetype is a required texture. ``None``
    for a card in neither — politics, geopolitics, an unlisted archetype: it is
    unbarred, keeps rank-earned access, and cannot be variety-promoted under B.
    No blanket threshold is introduced.
    """
    from app.utils.feed_market_quality import (
        _DISCOVER_REQUIRED_ARCHETYPES,
        DISCOVER_CATEGORY_HUNGER_THRESHOLDS,
        DISCOVER_REQUIRED_ARCHETYPE_MIN_SCORE,
        _discover_archetype_group,
        _discover_category_group,
    )

    bars = []
    category_bar = DISCOVER_CATEGORY_HUNGER_THRESHOLDS.get(_discover_category_group(card))
    if category_bar is not None:
        bars.append(category_bar)
    if _discover_archetype_group(card) in _DISCOVER_REQUIRED_ARCHETYPES:
        bars.append(DISCOVER_REQUIRED_ARCHETYPE_MIN_SCORE)
    return max(bars) if bars else None


def d2_promotion_gate(policy: str) -> Callable[..., tuple[bool, dict]]:
    """The ``PromotionGate`` for one D2 policy. Every check is computed for every
    arm and recorded, so the ledger shows what A and B would each have said
    about a baseline promotion; only ``policy`` decides what is allowed."""
    if policy not in D2_POLICIES:
        raise DisplayReplayError(UNSUPPORTED, f"unknown D2 policy {policy!r}")
    from app.utils import feed_market_quality as fmq

    def gate(card: dict, *, slot: int, mechanism: str, existing_bar: Any) -> tuple[bool, dict]:
        score = card.get("score", 0)
        window = fmq.FIRST_PAGE_WHY_NOW_WINDOW
        clean = fmq._is_clean_replacement_for(card, position=slot, why_now_window=window)
        bar = d2_defined_bar(card)
        checks = {
            "score_read_by_bars": score,
            "quality_class_ok": not fmq.is_first_page_quality_offender(card),
            "not_wholly_silent": not fmq.is_wholly_silent_card(card),
            "why_now_first_ten_ok": slot >= window or not fmq._is_reasonless(card),
            "clean_replacement": clean,
            "existing_bar": existing_bar,
            "existing_bar_ok": existing_bar is None or score >= existing_bar,
            "why_now_twenty_ok": not fmq.lacks_a_why_now(card),
            "defined_bar": bar,
            "defined_bar_ok": bar is not None and score >= bar,
        }
        checks["a_allowed"] = checks["clean_replacement"] and checks["existing_bar_ok"]
        checks["b_allowed"] = (
            checks["a_allowed"] and checks["why_now_twenty_ok"] and checks["defined_bar_ok"]
        )
        if policy == STAGE_POLICY_D2_ARM_A:
            return checks["a_allowed"], checks
        if policy == STAGE_POLICY_D2_ARM_B:
            return checks["b_allowed"], checks
        return True, checks

    return gate


@contextmanager
def _stage_policy(feed_route: Any, policy: Optional[str]):
    """Yields the D2 promotion trace (a list) for a D2 policy, else ``None``."""
    if policy is None:
        yield None
        return
    from functools import partial

    from app.utils.feed_market_quality import (
        COLD_START_WINDOW_FIRST_CARDS,
        diversify_discover_first_page,
    )

    trace: Optional[list] = None
    if policy == STAGE_POLICY_COLD_START_FIRST_CARDS:
        replacement = partial(
            diversify_discover_first_page,
            cold_start_window=COLD_START_WINDOW_FIRST_CARDS,
        )
    else:
        trace = []
        replacement = partial(
            diversify_discover_first_page,
            promotion_gate=d2_promotion_gate(policy),
            promotion_trace=trace,
        )
    original = feed_route.diversify_discover_first_page
    feed_route.diversify_discover_first_page = replacement
    try:
        yield trace
    finally:
        feed_route.diversify_discover_first_page = original


def _trace_card(card: Optional[dict]) -> Optional[dict]:
    if card is None:
        return None
    from app.utils.feed_market_quality import (
        _discover_archetype_group,
        _discover_category_group,
    )

    data = card.get("data") if isinstance(card.get("data"), dict) else {}
    return {
        "identity": _member(card),
        "type": card.get("type"),
        "title": data.get("name") or card.get("headline"),
        "score": card.get("score"),
        # Never the display score standing in for a missing ordering score.
        "ordering_score": card.get("_rank_score"),
        "quality_class": card.get("_quality_class"),
        "ladder_or_bucket": card.get("_quality_ladder_or_bucket"),
        "category_group": _discover_category_group(card),
        "archetype_group": _discover_archetype_group(card),
    }


def _serialize_promotion_trace(trace: list) -> list[dict]:
    out = []
    for entry in trace:
        row = {k: v for k, v in entry.items() if k not in ("card", "displaced", "deferred")}
        row["card"] = _trace_card(entry.get("card"))
        for key in ("displaced", "deferred"):
            if key in entry:
                row[key] = _trace_card(entry[key])
        out.append(row)
    return out



def replay_capture(
    capture: dict,
    *,
    arm: Optional[Callable[[list], list]] = None,
    stage_policy: Optional[str] = None,
    opening_seating: bool = False,
) -> dict:
    """Run one arm of a validated capture offline. Returns the replayed deck,
    page and diagnostics. ``arm`` (a candidate policy) receives a fresh decoded
    copy of the pool; the baseline arm is ``arm=None``. ``stage_policy`` (one
    of :data:`STAGE_POLICIES`) swaps one chain stage for a candidate rule; the
    baseline arm is ``stage_policy=None``.

    ``opening_seating`` (#5105, Alex's Option A) runs
    ``discover_opening_seating.seat_opening`` over the FINAL full deck — after
    collections, before pagination — at the capture's scoring clock. It
    composes with any ``stage_policy``. It refuses (``UNSUPPORTED``) a capture
    with an active edition, because reordering a pinned edition is exactly what
    the edition contract forbids and minting one under a new policy is release
    wiring this offline arm does not invent; it also refuses when the helper
    returns anything but applied/compliant (sparse supply, group membership,
    unknown kinds), so an unsupported shape is never counted as a pass. It
    raises ``MISMATCH`` if the stage changed, added or dropped any card.
    Default ``False``: the baseline arm is untouched.

    Never consults ``capture['expected']`` — that is the oracle, read only by
    :func:`verify_baseline`. Refuses (``validate_replay_inputs``) any capture
    outside the closed contract before running a stage, and runs the arm and
    every stage inside :func:`offline` — a candidate that hydrates is replaying
    today, exactly like a chain that does.
    """
    from app.routes import feed as feed_route
    from app.utils.feed_collections import COLLECTIONS_READ, insert_feed_collections
    from app.utils.feed_editions import EDITION_STATUS_PINNED, apply_pinned_edition
    from app.utils.personalization import PersonalizationContext

    if stage_policy is not None and stage_policy not in STAGE_POLICIES:
        raise DisplayReplayError(UNSUPPORTED, f"unknown stage_policy {stage_policy!r}")
    validate_replay_inputs(capture)
    if opening_seating and capture["downstream"]["edition"].get("active"):
        raise DisplayReplayError(
            UNSUPPORTED,
            "opening_seating does not replay an active-edition capture: a pinned "
            "edition is never reordered, and minting one under a new seating "
            "policy is release wiring this offline arm does not have",
        )
    kw = capture["chain_kwargs"]
    request = decode_value(capture["effective_request"])
    now = _dt.datetime.fromisoformat(capture["clocks"]["scoring_now"])

    with offline(), _stage_policy(feed_route, stage_policy) as promotion_trace:
        pool = decode_value(capture["scored_pool"]["items"])
        if arm is not None:
            pool = arm(pool)
        stages: dict[str, list[str]] = {"pool": deck_identities(pool)}

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
        pre_seating = items
        seating = None
        if opening_seating:
            stages["pre_seating"] = deck_identities(items)
            items, seating = _seat_opening(items, now)
        stages["pre_slice"] = deck_identities(items)
        # D2 only: read the internal fields BEFORE publication, which strips
        # ``_rank_score`` / ``_quality_*`` from the dicts in place.
        promotion_rows = card_facts = None
        if promotion_trace is not None:
            promotion_rows = _serialize_promotion_trace(promotion_trace)
            card_facts = {_member(item): _trace_card(item) for item in items}

        total = len(items)
        offset, limit = request["offset"], request["limit"]
        paginated = items[offset : offset + limit]

        # Deltas name the CAPTURED position; seating moves the same card objects,
        # so they are checked against the order the capture saw.
        _apply_venue_deltas(pre_seating, capture["downstream"]["venue_settlement"])

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
        "stage_policy": stage_policy,
        "promotion_trace": promotion_rows,
        "card_facts": card_facts,
        "opening_seating": seating,
    }


def _seat_opening(items: list, now: _dt.datetime) -> tuple[list, dict]:
    """The ``opening_seating`` stage, fenced: refuse what the helper refuses and
    prove — on the unpublished cards, private ranking fields included — that it
    moved cards without touching one."""
    from app.utils.discover_opening_seating import APPLIED, COMPLIANT, seat_opening

    def facts(card: dict) -> dict:
        return {
            "identity": _member(card),
            "type": card.get("type"),
            "score": card.get("score"),
            "_rank_score": card.get("_rank_score"),
        }

    before = {_member(card): (_digest(card), facts(card)) for card in items}
    outcome = seat_opening(items, now=now)
    if outcome.status not in (APPLIED, COMPLIANT):
        raise DisplayReplayError(
            UNSUPPORTED, f"opening seating {outcome.status}: {outcome.detail}"
        )
    after = {_member(card): (_digest(card), facts(card)) for card in outcome.items}
    if not len(items) == len(before) == len(after) == len(outcome.items) or set(
        after
    ) != set(before):
        raise DisplayReplayError(MISMATCH, "opening seating changed the deck's membership")
    changed = [ident for ident in before if before[ident] != after[ident]]
    if changed:
        raise DisplayReplayError(
            MISMATCH, f"opening seating changed card content: {changed[:5]}"
        )
    summary = outcome.summary()
    summary["card_facts"] = [after[_member(card)][1] for card in outcome.items]
    return outcome.items, summary


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
        "capture_mode": capture["provenance"]["capture_mode"],
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


# --------------------------------------------------------------------------- #
# Arm-vs-arm card comparison (#5105 root review of e4ed56d308)
# --------------------------------------------------------------------------- #
#
# A policy arm may move cards; it must not change one. The first comparison of
# two arms compared a hand-written PROJECTION of each card, which omitted
# tournament prices, bundle member prices, sources and timestamps, so "every
# shared card is identical" was never shown. This compares the WHOLE published
# card through the same codec as every parity check (type-exact, and anything
# it cannot freeze refuses rather than turning into a string), keyed by the
# edition identity, independent of deck order.


def _diff_encoded(before: Any, after: Any, path: str, out: list) -> None:
    def leaf(value: Any) -> str:
        return json.dumps(value, separators=(",", ":"), allow_nan=False)

    if isinstance(before, dict) and isinstance(after, dict):
        if _TAG in before or _TAG in after:
            if leaf(before) != leaf(after):
                out.append(
                    {
                        "path": path,
                        "before": {"value": before},
                        "after": {"value": after},
                    }
                )
            return
        for key in list(before) + [k for k in after if k not in before]:
            _diff_encoded(
                before.get(key, _ABSENT), after.get(key, _ABSENT), f"{path}.{key}", out
            )
        if [k for k in before if k in after] != [k for k in after if k in before]:
            out.append(
                {
                    "path": f"{path}<key order>",
                    "before": {"value": list(before)},
                    "after": {"value": list(after)},
                }
            )
        return
    if isinstance(before, list) and isinstance(after, list):
        for index in range(max(len(before), len(after))):
            _diff_encoded(
                before[index] if index < len(before) else _ABSENT,
                after[index] if index < len(after) else _ABSENT,
                f"{path}[{index}]",
                out,
            )
        return
    if before is _ABSENT or after is _ABSENT or leaf(before) != leaf(after):
        out.append(
            {"path": path, "before": _absent_enc(before), "after": _absent_enc(after)}
        )


def _is_permitted(path: str, permitted: frozenset) -> bool:
    return any(
        path == p or path.startswith(p + ".") or path.startswith(p + "[")
        for p in permitted
    )


def compare_decks_by_identity(
    before: list,
    after: list,
    *,
    require_same_inventory: bool = True,
    permitted_positional_paths: Iterable[str] = (),
) -> dict:
    """Compare two published decks card by card, by identity, ignoring order.

    Refuses (``INVALID``/``UNSUPPORTED``, the same rule as the capture's own
    decks) a deck holding a duplicate identity, a card with no identity or an
    unsupported kind — a duplicate is never allowed to collapse into one map
    entry. ``verdict`` is ``PASS`` only when no shared card differs anywhere in
    its encoded payload and, under ``require_same_inventory``, no card was added
    or removed.

    ``permitted_positional_paths`` names exact card paths (``"$.data.rank"``)
    that legitimately depend on position; their differences are reported under
    ``positional_changes`` and never hidden. Empty by default: nothing is
    permitted unless a caller names it.
    """
    permitted = frozenset(permitted_positional_paths)
    before_ids = _check_identities(before, kinds=SUPPORTED_DECK_KINDS, where="before")
    after_ids = _check_identities(after, kinds=SUPPORTED_DECK_KINDS, where="after")
    before_by = dict(zip(before_ids, before))
    after_by = dict(zip(after_ids, after))
    after_set = set(after_ids)
    added = [i for i in after_ids if i not in before_by]
    removed = [i for i in before_ids if i not in after_set]

    content: list[dict] = []
    positional: list[dict] = []
    shared = [i for i in before_ids if i in after_set]
    for ident in shared:
        a, b = before_by[ident], after_by[ident]
        changes: list[dict] = []
        _diff_encoded(encode_value(a, ident), encode_value(b, ident), "$", changes)
        if not changes and canonical(a) != canonical(b):  # pragma: no cover
            raise DisplayReplayError(
                INVALID,
                f"{ident}: canonical forms differ but no field difference found",
            )
        for change in changes:
            target = positional if _is_permitted(change["path"], permitted) else content
            target.append({"identity": ident, **change})

    inventory_ok = not (added or removed) or not require_same_inventory
    return {
        "verdict": PASS if inventory_ok and not content else MISMATCH,
        "compared": "full published card, encode_value codec, keyed by edition identity",
        "totals": {"before": len(before_ids), "after": len(after_ids)},
        "shared": len(shared),
        "require_same_inventory": require_same_inventory,
        "added": added,
        "removed": removed,
        "cards_with_content_changes": sorted({c["identity"] for c in content}),
        "content_changes": content,
        "permitted_positional_paths": sorted(permitted),
        "positional_changes": positional,
    }


def write_capture(capture: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(capture, fh, separators=(",", ":"), allow_nan=False)
