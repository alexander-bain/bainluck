"""Warm folded DNPL composition; no IO and no new probability policy."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import math
from types import SimpleNamespace

from app.utils.aggregation import newest_source_reading_time, reading_regresses_stored_observation
from app.utils.blend_preview import PREVIEW_SOURCES, PREVIEW_STATUSES, _basis_observation_time
from app.utils.draw_priced_winner import printable_away
from app.utils.hero_probability import resolve_hero
from app.utils.proven_duplicates import FoldedBlendView


def _revision(value):
    return type(value) is int and 0 <= value <= 9007199254740991


def valid_vector(vector):
    return (isinstance(vector, dict) and bool(vector)
            and all(isinstance(key, str) and key.isdecimal() and str(int(key)) == key
                    and int(key) > 0 and _revision(value) for key, value in vector.items()))


@dataclass(frozen=True)
class FoldedPreviewBase:
    event_id: int
    sources: dict
    owners: dict[str, int]
    revision: dict[str, int]
    context: dict
    sport: str | None

    @classmethod
    def capture(cls, event, sources, owners, revision, sport):
        if not valid_vector(revision) or str(event.id) not in revision:
            return None
        # All values are detached scalars/bags, never a session-owned ORM row.
        context = {key: getattr(event, key, None) for key in (
            "status", "home_score", "away_score", "completed_at",
            "espn_win_prob_home", "opening_home_probability",
            "opening_away_probability", "commence_time",
        )}
        return cls(event.id, deepcopy(sources), dict(owners), dict(revision), context, sport)

    def covers(self, members, floors):
        keys = {str(member) for member in members}
        return (keys == set(self.revision) and isinstance(floors, dict)
                and all(key in keys and _revision(value) and self.revision[key] >= value
                        for key, value in floors.items()))

    def project(self, frame, *, members, floors, elapsed_ms=0):
        """Replace only the already elected source owner's exact pending entry.

        The route supplies observed commit floors and elapsed time since receipt.
        No projection/retry creates a fresh sequence or extends its lifetime.
        """
        if not self.covers(members, floors) or not isinstance(frame, dict) or "rev" in frame:
            return None
        preview = frame.get("preview")
        origin = frame.get("event_id")
        source = frame.get("source")
        if (type(origin) is not int or origin <= 0 or source not in PREVIEW_SOURCES
                or self.owners.get(source) != origin or str(origin) not in self.revision
                or frame.get("status") != self.context["status"]
                or self.context["status"] not in PREVIEW_STATUSES
                or not isinstance(preview, dict) or preview.get("kind") != "blend"):
            return None
        if (not all(_revision(preview.get(k)) for k in ("epoch", "seq", "base_rev", "ttl_ms"))
                or preview["base_rev"] != self.revision[str(origin)]
                or type(elapsed_ms) not in (float, int) or not math.isfinite(elapsed_ms)
                or elapsed_ms < 0):
            return None
        ttl = preview["ttl_ms"] - math.ceil(elapsed_ms)
        if ttl <= 0:
            return None
        entries, pending = preview.get("pending_entries"), preview.get("pending")
        if (type(preview.get("pending_entries_version")) is not int
                or preview["pending_entries_version"] != 1
                or not isinstance(entries, dict) or set(entries) != {source}
                or not isinstance(pending, dict) or set(pending) != {source}):
            return None
        entry = entries[source]
        value = pending[source]
        if (not isinstance(entry, dict) or type(value) not in (int, float)
                or not math.isfinite(value) or not 0 <= value <= 1
                or entry.get("value") != value or entry.get("observed_value") != value
                or frame.get("source_value") != value):
            return None
        basis = entry.get("observed_basis")
        observed = _basis_observation_time(basis)
        if (observed is None or not isinstance(entry.get("updated_at"), str)
                or reading_regresses_stored_observation(self.sources, source, basis)):
            return None
        try:
            # Refuse malformed legacy metadata, without repairing the evidence.
            entry = json.loads(json.dumps(entry, allow_nan=False))
        except (TypeError, ValueError):
            return None
        sources = {**self.sources, source: entry}
        context = SimpleNamespace(**self.context)
        hero = resolve_hero(FoldedBlendView(context, sources))
        if hero is None or hero.source != "blend":
            return None
        clock_sources = {**sources, source: {**entry, "updated_at": observed.isoformat()}}
        clock = newest_source_reading_time(
            FoldedBlendView(context, clock_sources), require_complete=True,
        )
        result = {
            **frame, "event_id": self.event_id,
            "p": hero.home_probability,
            "p_away": printable_away(hero.away_probability, hero.home_probability, self.sport),
            "sport": self.sport,
            "display_observed_at": clock.isoformat() if clock else None,
            "preview": {
                **preview, "origin_event_id": origin, "folded_version": 1,
                "base_fold_revision": dict(self.revision), "ttl_ms": ttl,
            },
        }
        try:
            json.dumps(result, allow_nan=False)
        except (TypeError, ValueError):
            return None
        return result


class QuoteWithPreviewBase(dict):
    """The public quote serializes unchanged; raw policy inputs stay internal."""

    def __init__(self, quote, base):
        super().__init__(quote)
        self.preview_base = base
