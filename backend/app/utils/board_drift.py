"""The six board-drift conditions, as pure functions (#1878).

Why this module is pure
-----------------------
``.claude/handoff/`` is gitignored, absent from the Heroku dyno, and absent
from an Actions checkout. Four of the six conditions (a, b, d, e) can ONLY be
computed where those files live, so the sentinel itself is a LOCAL rail
(``scripts/board_drift_sentinel.py``). That constraint was named in the spec
precisely so it would be decided at the start rather than discovered at gate
time — and the decision here is to split it: **all judgment lives in this
module, which takes already-parsed inputs and touches no filesystem, no
network and no database.** The rail reads; this decides.

That split is what makes the retro-test possible at all. The acceptance bar is
that the sentinel re-detects the 2026-08-11 drift it was created out of, and a
retro-test cannot be run against a function that insists on reading today's
directory.

The rule every condition obeys
------------------------------
**Compute the invariant; never consult a list.** Chain queue 344 was written
from an orphan list taken three days earlier, and by the time it ran the list
was wrong in both directions — it named 4 orphans and missed 3, one of which
self-declared ``consumed`` for code that had been REVERTED. A list of known
orphans cannot find an unknown one. Every function below derives its findings
from the directory contents and the board, and there is deliberately no
allowlist anywhere in this file for a finding to hide behind.

``checked: 0`` is ``unknown``, never ``pass``
---------------------------------------------
Gotcha #53, and #1147's ``chart_density`` reported a green empty pass for 21
days while two real fixes shipped against it. A condition that examined
nothing has not passed; it has not run. :func:`summarise` enforces this for
every condition rather than trusting each one to remember.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

#: Filename statuses that take a staged queue OUT of the orphan population.
#: These are read from the FILENAME, not from a status line inside the file —
#: see condition (e) for why that distinction is itself a finding.
_RESOLVED_SUFFIXES = ("promoted", "superseded", "consumed")

_STAGED_RE = re.compile(r"^QUEUE-STAGED-.*\.md$")

#: Ready-column staleness. N=14 per the spec, escalating at 30.
READY_STALE_DAYS = 14
READY_STALE_ESCALATE_DAYS = 30

#: HELD-table age thresholds, in lane1 windows.
HELD_AGE_WARN = 5
HELD_AGE_ESCALATE = 10


@dataclass(frozen=True)
class Finding:
    condition: str          # "a".."f"
    severity: str           # "P1" | "P2" | "P3"
    subject: str            # the file / row / issue the finding is ABOUT
    detail: str


@dataclass
class ConditionResult:
    """One condition's outcome, carrying its own denominator.

    ``checked`` is the number of things EXAMINED, not the number found. It is
    separate from ``findings`` because zero findings out of zero examined and
    zero findings out of forty examined are different claims, and only the
    second one is a pass.
    """

    condition: str
    checked: int
    findings: list[Finding] = field(default_factory=list)
    note: Optional[str] = None

    @property
    def verdict(self) -> str:
        if self.checked == 0:
            return "unknown"
        return "fail" if self.findings else "pass"


# ---------------------------------------------------------------------------
# (a) a staged queue file absent from CHAIN.md — P2
# ---------------------------------------------------------------------------

def staged_queue_is_resolved(filename: str) -> bool:
    """Resolved-ness is read from the FILENAME.

    The invariant keys on filenames, so this must too. Queue 316's disposition
    was recorded by editing the ``status:`` line INSIDE the file while the
    filename stayed ``QUEUE-STAGED-...md`` — CHAIN.md then asserted it was
    "flipped to consumed" and the orphan check kept reporting it, silently, for
    a day. Condition (e) exists to catch exactly that split; this function must
    not paper over it by peeking at the file's contents.

    Two properties, both learned from the live directory rather than assumed:

    * **The marker may be followed by a REASON, so it is not anchored to the
      end.** The first live run reported five false orphans because it required
      the stem to end with the marker, while the real convention attaches the
      why — ``…-US-OPEN-ALIAS.superseded-by-4c491eaf-and-1793.md``,
      ``…-RULING-024-COMBINED.consumed-then-REVERTED-90602414.md``. Those names
      are *more* informative than a bare suffix, and a check that understands
      only the terse form punishes the better convention.
    * **The marker is lowercase and introduced by a literal ``.``** — that is
      what separates a disposition from a topic. Matching loosely and
      case-insensitively made ``QUEUE-STAGED-CONSUMED-THINGS.md`` read as
      consumed: a queue *about* consumed things, silently disposed of by its
      own subject matter. Queue names carry their topic in UPPERCASE segments
      after hyphens; dispositions are lowercase after a dot. Every disposition
      in the live directory follows it.
    """
    stem = filename[:-3] if filename.endswith(".md") else filename
    return any(re.search(rf"\.{s}\b", stem) for s in _RESOLVED_SUFFIXES)


def condition_a_orphan_staged_queues(
    handoff_filenames: Iterable[str], chain_text: str
) -> ConditionResult:
    """A staged queue whose LITERAL FILENAME does not appear in CHAIN.md.

    Computed from the directory listing. If this function ever grows a
    parameter named ``known_orphans``, it has stopped being this check.
    """
    staged = [f for f in sorted(handoff_filenames) if _STAGED_RE.match(f)]
    unresolved = [f for f in staged if not staged_queue_is_resolved(f)]
    findings = [
        Finding("a", "P2", f,
                "staged queue file is not named anywhere in CHAIN.md, so no "
                "chain row owns it — it will not be executed and nothing will "
                "report it missing")
        for f in unresolved if f not in chain_text
    ]
    return ConditionResult("a", checked=len(unresolved), findings=findings)


# ---------------------------------------------------------------------------
# (b) promotes-after: pointing at a dead queue — P2
# ---------------------------------------------------------------------------

_PROMOTES_RE = re.compile(r"^promotes-after:\s*(\S+)", re.MULTILINE)

#: A queue id: `344`, `339T`, or an uppercase token like `CAL-P045`. Anything
#: else in a `promotes-after:` is prose, and prose is not a gate.
_QUEUE_ID_RE = re.compile(r"\d{1,4}[A-Za-z]?|[A-Z][A-Z0-9-]{2,}")


def condition_b_dead_promotes_after(
    queue_files: dict[str, str], dead_queue_ids: Iterable[str]
) -> ConditionResult:
    """A gate that can never fire reads as "blocked" forever.

    Which is indistinguishable from "not ready" — so nothing escalates, and the
    queue waits on an event that has already happened or can never happen.
    """
    dead = {str(d) for d in dead_queue_ids}
    checked, findings = 0, []
    for name, text in sorted(queue_files.items()):
        # A resolved file's gate is HISTORY, not a live block. The first run
        # reported 35 findings, almost all of them `*.promoted.md` files whose
        # gate had already fired — which is the check describing the chain
        # working correctly. A sentinel that reports normal operation at that
        # volume trains its reader to close it unread, and then it is worse
        # than absent.
        if staged_queue_is_resolved(name):
            continue
        m = _PROMOTES_RE.search(text or "")
        if not m:
            continue
        target = m.group(1).strip("`\"'")
        # `promotes-after: nothing (legacy file...)` is prose meaning NO gate,
        # not a gate on a queue called "nothing". Skipped BEFORE the denominator
        # so it does not count as an examined gate either — it isn't one. The
        # first live run read that line as a dead target and reported the file.
        if not _QUEUE_ID_RE.fullmatch(target):
            continue
        checked += 1
        if target in dead:
            findings.append(Finding(
                "b", "P2", name,
                f"promotes-after: {target}, which is done/superseded/orphaned — "
                "this gate can never fire, and a gate that cannot fire is "
                "indistinguishable from a queue that is merely not ready"))
    return ConditionResult("b", checked=checked, findings=findings)


# ---------------------------------------------------------------------------
# (c) a stale Ready-column item — P3, escalating P2 at 30 days
# ---------------------------------------------------------------------------

def condition_c_stale_ready_items(
    ready_items: Iterable[tuple[str, int]]
) -> ConditionResult:
    """``ready_items`` is ``(label, age_in_days)``, age already computed.

    Taking the age rather than a timestamp keeps the clock OUT of the judgment
    (gotcha #44): the caller resolves "now" once, and this function has no
    branch that can change colour with the wall clock.
    """
    items = list(ready_items)
    findings = []
    for label, age in items:
        if age > READY_STALE_ESCALATE_DAYS:
            findings.append(Finding(
                "c", "P2", label,
                f"in Ready for {age}d (> {READY_STALE_ESCALATE_DAYS}d) — a "
                "Ready item nobody pulls is a queue that has stopped being read"))
        elif age > READY_STALE_DAYS:
            findings.append(Finding(
                "c", "P3", label, f"in Ready for {age}d (> {READY_STALE_DAYS}d)"))
    return ConditionResult("c", checked=len(items), findings=findings)


# ---------------------------------------------------------------------------
# (d) a chain row naming a file that no longer contains that queue — P1
# ---------------------------------------------------------------------------

def condition_d_chain_row_file_mismatch(
    chain_rows: Iterable[tuple[str, str]], queue_files: dict[str, str]
) -> ConditionResult:
    """``chain_rows`` is ``(queue_id, filename)``.

    **P1, and the only P1 among the six.** This is the 333 substitution: a
    window can RUN THE WRONG QUEUE while believing it followed the chain,
    because it resolved the row to a filename and the filename's contents had
    moved on. Every other condition here delays work; this one silently
    redirects it.
    """
    rows = list(chain_rows)
    checked, findings = 0, []
    for queue_id, filename in rows:
        text = queue_files.get(filename)
        if text is None:
            findings.append(Finding(
                "d", "P1", f"{queue_id} -> {filename}",
                "chain row names a file that does not exist"))
            checked += 1
            continue
        checked += 1
        if not re.search(rf"(?:^|\D){re.escape(str(queue_id))}(?:\D|$)", text):
            findings.append(Finding(
                "d", "P1", f"{queue_id} -> {filename}",
                f"chain row claims queue {queue_id} but that file does not "
                "mention it — a window following the chain would execute "
                "whatever this file now contains, believing it obeyed"))
    return ConditionResult("d", checked=checked, findings=findings)


# ---------------------------------------------------------------------------
# (e) a disposition in prose but not in the artifact the check reads — P2
# ---------------------------------------------------------------------------

_DISPOSITION_WORD_RE = re.compile(
    r"\b(consumed|promoted|superseded|flipped|reconciled)\b", re.IGNORECASE)

#: How far from a filename a disposition word still counts as being ABOUT it.
_PROSE_WINDOW = 200


def condition_e_prose_only_disposition(
    chain_text: str, handoff_filenames: Iterable[str]
) -> ConditionResult:
    """CHAIN.md says a queue was dispositioned; the filename says otherwise.

    Queue 316's exact split. The prose was true about the ``status:`` line
    INSIDE the file and false about the filename, and since the invariant keys
    on filenames the chain read "reconciled" while the check read "orphan" — at
    the same moment, from the same directory, with nobody wrong on purpose.

    A disposition that lives only in prose is a disposition no automated reader
    can see, which makes it a claim rather than a state change.

    **Why this is a WINDOW around the filename rather than a single ordered
    pattern.** The first version required the filename to precede the
    disposition word, and missed the real CHAIN.md text on its first run — the
    prose there reads "Queue 316's file was flipped to `consumed` … See
    `QUEUE-STAGED-316-CAL-EXIT-EXAM.md` for the record", with the word FIRST.
    A check for prose cannot assume prose word order; it would have been a
    condition that passes because English is flexible.

    **This condition is (a)'s complement, not its duplicate.** (a) reports a
    staged file whose filename is absent from CHAIN.md. 316's filename was
    PRESENT — in a sentence claiming it was already dealt with — so (a) is
    silent on it, correctly. The mention that satisfies (a) is exactly the
    mention that hides the drift, which is why (e) was added.
    """
    present = {f for f in handoff_filenames if _STAGED_RE.match(f)}
    text = chain_text or ""
    checked, findings = 0, []
    for filename in sorted(present):
        if filename not in text:
            continue
        if staged_queue_is_resolved(filename):
            continue
        checked += 1
        for m in re.finditer(re.escape(filename), text):
            lo = max(0, m.start() - _PROSE_WINDOW)
            hi = min(len(text), m.end() + _PROSE_WINDOW)
            word = _DISPOSITION_WORD_RE.search(text[lo:hi])
            if word:
                findings.append(Finding(
                    "e", "P2", filename,
                    f"CHAIN.md describes this queue as '{word.group(1).lower()}', "
                    "but the file is still on disk under an unresolved "
                    "filename. The invariant keys on filenames, so the prose "
                    "and the check disagree — and only the prose is visible to "
                    "a human reading the chain"))
                break
    return ConditionResult("e", checked=checked, findings=findings)


# ---------------------------------------------------------------------------
# (f) an over-age HELD row — P2 at >= 5 windows, P1 at >= 10
# ---------------------------------------------------------------------------

def condition_f_over_age_held_rows(
    held_rows: Iterable[tuple[str, int]]
) -> ConditionResult:
    """``held_rows`` is ``(row_label, age_in_windows)``.

    The HELD table already has two human readers. That is the point: **both
    readers are humans reading a table, which is the mechanism the table exists
    because it failed.** A held item has a written reason, so every window that
    reads past it feels correct doing so, and the permission slip renews itself
    while only the age column grows.
    """
    rows = list(held_rows)
    findings = []
    for label, age in rows:
        if age >= HELD_AGE_ESCALATE:
            findings.append(Finding(
                "f", "P1", label,
                f"held {age} windows (>= {HELD_AGE_ESCALATE}) — at this age the "
                "row is not waiting on its stated gate, it is waiting on nobody"))
        elif age >= HELD_AGE_WARN:
            findings.append(Finding(
                "f", "P2", label,
                f"held {age} windows (>= {HELD_AGE_WARN}) — is this gate still "
                "the right gate?"))
    return ConditionResult("f", checked=len(rows), findings=findings)


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------

ALL_CONDITIONS = ("a", "b", "c", "d", "e", "f")


def summarise(results: Iterable[ConditionResult]) -> dict:
    """The verdict envelope, in the shape the Flow/Grid/Calibration sentinels use.

    Two rules are enforced HERE rather than per condition, because a rule each
    condition must remember is a rule some condition will forget:

    1. ``checked == 0`` is ``unknown``, never ``pass`` (gotcha #53).
    2. A condition that produced no result at all is ``unknown`` and PRESENT in
       the output — an absent key reads as "nothing to report" to every
       consumer, which is the same false green one level up.
    """
    by_condition = {r.condition: r for r in results}
    conditions, findings = {}, []
    for letter in ALL_CONDITIONS:
        r = by_condition.get(letter)
        if r is None:
            conditions[letter] = {
                "verdict": "unknown", "checked": 0, "findings": 0,
                "note": "condition did not run",
            }
            continue
        conditions[letter] = {
            "verdict": r.verdict,
            "checked": r.checked,
            "findings": len(r.findings),
            "note": r.note,
        }
        findings.extend(r.findings)

    verdicts = {c["verdict"] for c in conditions.values()}
    if "fail" in verdicts:
        overall = "fail"
    elif "unknown" in verdicts:
        overall = "unknown"
    else:
        overall = "pass"

    severities = {f.severity for f in findings}
    return {
        "verdict": overall,
        "conditions": conditions,
        "findings": [
            {"condition": f.condition, "severity": f.severity,
             "subject": f.subject, "detail": f.detail}
            for f in findings
        ],
        "finding_count": len(findings),
        "worst_severity": min(severities) if severities else None,
    }
