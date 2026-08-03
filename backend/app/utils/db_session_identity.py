"""Query-visible identity for the sessions our scheduled work opens (Queue 300B).

Two orphaned calibration backends have been sitting on the production database
since 2026-08-02 (#1479). Everything we know about them we inferred: they are
old, they are running something whose shape matches the futures population CTE,
and they hold an xmin that autovacuum cannot get past. What we could NOT
establish from the database itself is *whose they are* — the rows carry an empty
``application_name``, so C127's containment contract reports
``OWNER_IDENTITY_AMBIGUOUS`` and refuses to act, which is the correct refusal and
also a dead end.

The evidence we were reduced to — client address and age — is exactly the
evidence C127 forbids as authority. ``client_addr`` is a dyno IP that is reused
and rotated; age is ``AGE_ONLY_AUTHORITY``, the rule that exists because "it has
been running a long time" is indistinguishable between a wedged orphan and a
legitimately slow current beat. So this module makes the backend say who it is.

What a tag has to carry, derived from what the contract asks of a row:

* **which task** — so ``fingerprint``-style allowlisting has a name to check
  against rather than a query-text guess.
* **which build/deploy generation** — so ``generation_relation`` can be
  ``predeploy`` vs ``current`` without asking how old the session is. This is
  the field that would have resolved the current incident on sight.
* **which run, and whose** — so ``current_beat`` is a fact, not an inference, and
  so a ledger row and a ``pg_stat_activity`` row can be joined afterwards.

Three properties are non-negotiable and every one of them is tested:

* **Bounded.** PostgreSQL truncates ``application_name`` at 63 bytes and does it
  silently. A tag that gets truncated loses its tail — which is where the owner
  lives — so the format is sized to fit in the worst case, not the typical one.
* **Redacted.** The raw owner is ``hostname:pid``; the hostname is infrastructure
  detail that ends up in error reports and log aggregators. The tag carries a
  hash of it and the ledger keeps the plaintext, which is the half that is
  already access-controlled.
* **Semantically inert.** The tag reaches Postgres as a bind parameter to
  ``set_config``, never as interpolated SQL, and the character set is restricted
  on top of that. A tag can make a query identifiable; it must never be able to
  make it do something else.

This module is pure — no database, no clock, no environment beyond an explicitly
passed mapping — so the classification rules can be graded against static
fixture rows the way C127 grades its corpus. The applier lives in
``app.tasks.base``; keeping it over there is also what keeps a pooled *web*
session from ever acquiring one of these tags.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional

#: PostgreSQL's ``application_name`` is a ``NameData``: 64 bytes including the
#: terminator, so 63 usable, and anything longer is truncated WITHOUT error.
APPLICATION_NAME_MAX = 63

#: Schema marker. Versioned because a future field change must be detectable by
#: an operator reading an old backend's tag, not guessed at.
TAG_SCHEMA = "bl1"

_SEP = "/"

# Field widths, budgeted so the worst case lands EXACTLY on the ceiling:
#   3 + 1 + 29 + 1 + 10 + 1 + 9 + 1 + 8 = 63
#
# The task gets the lion's share because it is the field a human reads first and
# the field C127 allowlists against. ``precompute_calibration_main`` is 27
# characters and MUST survive intact — an earlier cut at 24 silently shortened it
# to ``precompute_calibration_m``, which is the exact class of quiet truncation
# this whole module exists to avoid. 10 hex characters of build id and 9 base36
# digits of generation (good past the year 5000) are what pay for it.
_TASK_MAX = 29
_BUILD_MAX = 10
_RUN_MAX = 9
_OWNER_MAX = 8

UNKNOWN_TASK = "unknown"
UNKNOWN_BUILD = "nobuild"
UNKNOWN_RUN = "norun"
UNKNOWN_OWNER = "noowner"

#: Everything outside this becomes ``_``. Deliberately narrower than "what
#: Postgres accepts": no quotes, no semicolons, no whitespace, no backslashes,
#: nothing that could matter to a log parser, an error formatter, or a shell
#: someone later pipes ``pg_stat_activity`` output into.
_UNSAFE = re.compile(r"[^a-z0-9_.-]")

# Generation relations, in C127's own vocabulary.
CURRENT = "current"
SUPERSEDED = "superseded"
PREDEPLOY = "predeploy"

# What a row turns out to be.
KIND_CURRENT_BEAT = "current_beat"
KIND_SUPERSEDED_RUN = "superseded_run"
KIND_PREDEPLOY_RUN = "predeploy_run"
#: Ours by tag, but the generation evidence does not place it. Not an error —
#: the honest answer when a build id is missing on either side.
KIND_UNCLASSIFIED = "unclassified_run"
KIND_FOREIGN = "foreign"


def _slug(value: Any, *, max_len: int, fallback: str) -> str:
    """One tag field: lowercased, restricted, bounded, never empty."""
    text = "" if value is None else str(value).strip().lower()
    text = _UNSAFE.sub("_", text)
    text = text.strip("_")
    if not text:
        return fallback
    return text[:max_len]


def _short_owner(owner: Any) -> str:
    """A stable, non-reversible 8-hex handle for ``hostname:pid``.

    Hashed rather than truncated: ``web.1:12345`` and ``web.10:12345`` share a
    prefix, and two orphans that look like the same owner is worse than no owner
    at all. The plaintext goes in the ledger, which is not world-readable.
    """
    if owner is None or str(owner).strip() == "":
        return UNKNOWN_OWNER
    digest = hashlib.sha256(str(owner).encode("utf-8", "replace")).hexdigest()
    return digest[:_OWNER_MAX]


def _short_run(generation: Any) -> str:
    """Base36 of the epoch-ms generation — 8 chars where decimal needs 13.

    The generation only has to be comparable and joinable, not human-readable;
    trading 5 characters of width for that is what leaves room for a legible
    task name inside the 63-byte ceiling.
    """
    try:
        value = int(generation)
    except (TypeError, ValueError):
        return UNKNOWN_RUN
    if value <= 0:
        return UNKNOWN_RUN
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while value:
        value, rem = divmod(value, 36)
        out = digits[rem] + out
    return out[-_RUN_MAX:]


def current_build_id(env: Optional[Mapping[str, str]] = None) -> str:
    """This deploy's identity, from whatever the platform actually sets.

    Heroku populates ``HEROKU_SLUG_COMMIT`` / ``HEROKU_RELEASE_VERSION`` with
    dyno metadata enabled — ``app.main`` already reports the former to Sentry, so
    it is present in production rather than aspirational.

    When nothing is set this returns :data:`UNKNOWN_BUILD` and, per
    :func:`classify_activity_row`, generation authority becomes *unknown* instead
    of silently defaulting to "predeploy". Inventing a generation relation is how
    a live beat gets classified as an orphan and cancelled.
    """
    if env is None:
        import os

        env = os.environ
    for key in ("HEROKU_RELEASE_VERSION", "HEROKU_SLUG_COMMIT", "GIT_COMMIT"):
        value = env.get(key)
        if value:
            return _slug(value, max_len=_BUILD_MAX, fallback=UNKNOWN_BUILD)
    return UNKNOWN_BUILD


@dataclass(frozen=True)
class SessionTag:
    """A parsed ``application_name`` this codebase wrote."""

    task: str
    build: str
    run: str
    owner: str

    @property
    def build_known(self) -> bool:
        return self.build != UNKNOWN_BUILD

    @property
    def run_known(self) -> bool:
        return self.run != UNKNOWN_RUN


def build_session_tag(
    *,
    task: Any,
    build: Any = None,
    run_generation: Any = None,
    owner: Any = None,
) -> str:
    """The ``application_name`` one scheduled session should announce itself as.

    Total width is bounded by construction (see the field maxima above), so this
    never relies on Postgres's silent truncation to keep it legal.
    """
    tag = _SEP.join(
        (
            TAG_SCHEMA,
            _slug(task, max_len=_TASK_MAX, fallback=UNKNOWN_TASK),
            _slug(build, max_len=_BUILD_MAX, fallback=UNKNOWN_BUILD),
            _short_run(run_generation),
            _short_owner(owner),
        )
    )
    # Belt and braces. If a future field widens past the budget the truncation
    # should be ours and visible in a test, not Postgres's and invisible.
    return tag[:APPLICATION_NAME_MAX]


def parse_session_tag(application_name: Any) -> Optional[SessionTag]:
    """Read a tag back off a ``pg_stat_activity`` row, or ``None``.

    ``None`` covers every "not ours" case — empty, a psql session, a connection
    pooler's own label, a tag from a schema we do not know. None of those are
    errors; they are simply rows this codebase cannot speak for.
    """
    if not isinstance(application_name, str):
        return None
    parts = application_name.strip().split(_SEP)
    if len(parts) != 5 or parts[0] != TAG_SCHEMA:
        return None
    _, task, build, run, owner = parts
    if not task or not build or not run or not owner:
        return None
    return SessionTag(task=task, build=build, run=run, owner=owner)


@dataclass(frozen=True)
class ActivityIdentity:
    """What a single ``pg_stat_activity`` row can be said to be.

    ``generation_relation`` is ``None`` when the evidence does not support one.
    That is a real answer and the caller must treat it as a refusal to classify —
    C127 raises ``GENERATION_AUTHORITY_UNKNOWN`` on exactly that, and the whole
    point of this module is to stop guessing at this particular field.
    """

    kind: str
    task: Optional[str] = None
    owner: Optional[str] = None
    generation_relation: Optional[str] = None
    current_beat: bool = False

    @property
    def is_ours(self) -> bool:
        return self.kind != KIND_FOREIGN


def classify_activity_row(
    row: Mapping[str, Any],
    *,
    current_build: Optional[str] = None,
    current_run: Optional[Any] = None,
    current_owner: Optional[str] = None,
) -> ActivityIdentity:
    """Classify one row from ``application_name`` alone.

    Explicitly NOT from ``client_addr`` (a recycled dyno IP) and NOT from
    ``age``/``backend_start`` (``AGE_ONLY_AUTHORITY``). Those two are the only
    evidence the current orphan incident left us, and the reason it is stuck.

    Where the evidence runs out, this fails toward ``current`` — the class that
    C127 forbids touching. An unprovable row must be the untouchable one; the
    cost of that mistake is a missed cleanup, while the reverse is cancelling a
    live build.
    """
    tag = parse_session_tag(row.get("application_name"))
    if tag is None:
        return ActivityIdentity(kind=KIND_FOREIGN)

    expected_build = (
        _slug(current_build, max_len=_BUILD_MAX, fallback=UNKNOWN_BUILD)
        if current_build is not None
        else UNKNOWN_BUILD
    )

    # Either side unable to name its build means there is no generation
    # authority to have. Reporting ``None`` is what makes C127 refuse, which is
    # the outcome we want: a row we cannot place is a row we do not touch.
    if not tag.build_known or expected_build == UNKNOWN_BUILD:
        return ActivityIdentity(
            kind=KIND_UNCLASSIFIED,
            task=tag.task,
            owner=tag.owner,
            generation_relation=None,
            current_beat=False,
        )

    if tag.build != expected_build:
        # Started under a different slug than the one running now. This is the
        # fact the current incident needed and did not have.
        return ActivityIdentity(
            kind=KIND_PREDEPLOY_RUN,
            task=tag.task,
            owner=tag.owner,
            generation_relation=PREDEPLOY,
            current_beat=False,
        )

    # Same build. Superseded only if we can PROVE a different run owns "now".
    expected_run = _short_run(current_run) if current_run is not None else UNKNOWN_RUN
    expected_owner = (
        _short_owner(current_owner) if current_owner is not None else UNKNOWN_OWNER
    )
    if expected_run == UNKNOWN_RUN or expected_owner == UNKNOWN_OWNER:
        return ActivityIdentity(
            kind=KIND_CURRENT_BEAT,
            task=tag.task,
            owner=tag.owner,
            generation_relation=CURRENT,
            current_beat=True,
        )

    if tag.run == expected_run and tag.owner == expected_owner:
        return ActivityIdentity(
            kind=KIND_CURRENT_BEAT,
            task=tag.task,
            owner=tag.owner,
            generation_relation=CURRENT,
            current_beat=True,
        )

    return ActivityIdentity(
        kind=KIND_SUPERSEDED_RUN,
        task=tag.task,
        owner=tag.owner,
        generation_relation=SUPERSEDED,
        current_beat=False,
    )
