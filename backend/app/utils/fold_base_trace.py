"""#10090: optional log-only receipt of a traced fold's committed base, per vector.

Purpose. A folded preview (`folded_blend_preview_v2.FoldedPreviewSession`)
composes each origin's pending entries over the fold's committed BASE
(`FoldedPreviewBase`: the elected sources, their owners and the hero context at
one exact revision vector). The fold frame names that vector
(``base_fold_revision``) and its origins, but not the base itself, so the
composed target cannot be recomputed from the frame. This receipt writes, in
the web process's log, the base each traced fold composed on:

  FOLD_BASE             once per CHANGE of base for that event (revision
                        vector, owners, bag hash, context) per process, not
                        once per distinct base: two streams alternating bases
                        A,B,A,B write four lines. Fields: ``revision``,
                        ``members``, ``owners`` (source -> origin event),
                        ``election`` (the preview sources' owners), the hero
                        ``context`` (status, scores, completed_at, ESPN and
                        opening inputs, commence_time), ``sport``, the complete
                        source bag (per probability source: value, stamp,
                        weight, refusal, observed basis; ``bag_hash`` over the
                        whole bag) and ``committed`` (the base alone composed by
                        the fold's own `compose`: p, p_away, display clock).
                        ``fold_session`` is the stream whose update wrote the
                        line; ``repeat_uses`` counts the further updates (from
                        any stream, the writer included) that composed on the
                        event's PREVIOUS base after its line, so a base still in
                        use at STOP has its repeats uncounted.
  FOLD_BASE_UNAVAILABLE a traced fold whose base became unavailable (eviction,
                        recovery, a cold hub): once per transition.
  START / ARMED / STOP  as `nonvenue_trace.BoundedLogTrace`.

The adapter joins a fold frame to its base by (event, ``base_fold_revision``).
A base is the hub's warm detached capture (`folded_live_quote`), never a new
read: this receipt adds no read, subscription, Redis or database call.

Enable only with FOLD_TRACE_EVENTS (1-4 fold/display event ids) and an absolute
FOLD_TRACE_EXPIRES_AT no more than 600 s away; FOLD_TRACE_MAX_LINES (128,
4..256) and optional FOLD_TRACE_ARM_AT as the nonvenue trace. Per web process:
each dyno has its own budget and ``run``. Disarmed: `fold_base_trace()` returns
None after one environment read, and the route's hook is a ``None`` check.
Every method swallows its own failure. Activation is owner-controlled.
"""

from __future__ import annotations

import os

from app.utils.nonvenue_trace import (
    MAX_PENDING,
    BoundedLogTrace,
    _clean,
    _hash,
    _number,
    _text,
    bag_fields,
)

_UNSET = object()
_TRACE = _UNSET


def fold_base_trace():
    """This process's fold-base trace, built on first use, or None."""
    global _TRACE
    if _TRACE is _UNSET:
        try:
            _TRACE = FoldBaseTrace.from_env(os.environ)
        except Exception:
            _TRACE = None
        if _TRACE is not None:
            from app.utils.clock_bridge import attach

            attach(_TRACE, "fold")
    return _TRACE


def reset_for_tests(trace=None):
    global _TRACE
    _TRACE = _UNSET if trace is None else trace


_CONTEXT = ("status", "home_score", "away_score", "completed_at", "espn_win_prob_home",
            "opening_home_probability", "opening_away_probability", "commence_time")


class FoldBaseTrace(BoundedLogTrace):
    PREFIX = "FOLD_TRACE"
    LOG = "fold-base-trace"
    SCHEMA = "fold-base-trace/1"

    def __init__(self, events, expiry, limit, run, wall, mono, emit):
        super().__init__(events, expiry, limit, run, wall, mono, emit)
        self.last = {}  # event -> (signature, repeat uses since its line)
        self.n_bases = 0

    def _counters(self):
        return dict(bases=self.n_bases)

    def _discard(self):
        self.last.clear()

    def base(self, event_id, base, *, fold_session=None):
        """One fold update's base, before the session composes on it."""
        try:
            if event_id not in self.events or not self.active():
                return
            if base is None:
                signature = None
            else:
                context = {key: base.context.get(key) for key in _CONTEXT}
                signature = (tuple(sorted(base.revision.items())),
                             tuple(sorted(base.owners.items())),
                             _hash(base.sources), _hash(context))
            last, repeats = self.last.get(event_id, (_UNSET, 0))
            if last == signature:
                self.last[event_id] = (last, repeats + (0 if signature is None else 1))
                return
            if event_id not in self.last and len(self.last) >= MAX_PENDING:
                self._stop("PENDING_OVERFLOW")
                return
            self.last[event_id] = (signature, 0)
            if signature is None:
                if last is not _UNSET:
                    self._record("FOLD_BASE_UNAVAILABLE", event=event_id,
                                 fold_session=_text(fold_session))
                return
            self.n_bases += 1
            self._record("FOLD_BASE", **self._fields(event_id, base, context),
                         fold_session=_text(fold_session), repeat_uses=repeats)
        except Exception:
            pass  # evidence must never cost a frame

    @staticmethod
    def _fields(event_id, base, context):
        from app.utils.blend_preview import PREVIEW_SOURCES

        fields = dict(
            event=event_id,
            base_event=base.event_id,
            revision={str(k): v for k, v in sorted(base.revision.items())},
            members=sorted(base.revision),
            owners={str(k): v for k, v in sorted(base.owners.items())},
            election={name: owner for name, owner in sorted(base.owners.items())
                      if name in PREVIEW_SOURCES},
            context={key: _clean(_iso(value)) for key, value in context.items()},
            sport=_text(base.sport),
            # The fold's hero is `compose` below, never the row aggregate.
            **bag_fields(base.sources, context.get("status"),
                         context.get("espn_win_prob_home"),
                         context.get("opening_home_probability"), recompute=False),
        )
        try:
            committed = base.compose({}, {})
        except Exception:
            committed = "COMPOSE_ERROR"
        fields["committed"] = (
            None if committed is None
            else committed if isinstance(committed, str)
            else dict(p=_number(committed.get("p")), p_away=_number(committed.get("p_away")),
                      display_observed_at=_text(committed.get("display_observed_at")))
        )
        return fields


def _iso(value):
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else value
