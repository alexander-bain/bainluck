#!/usr/bin/env python3
"""The Phase-0 READY sweep, with the never-merge containment check COMPUTED.

Ruling 109: **a READY token is VOID while its branch contains a never-merge
ancestor.** This script is the enforcement half of that ruling, and it exists
because the alternative — a list of never-merge heads that a human consults —
is a list a human forgets. INT-092 retired the two never-merge heads it could
see and the real constraint ran through a third one that was still advertising
``status: ready_for_integration``, so four further ready branches silently
carried an edit to a migration production had already run.

What it answers, per token:

* is the branch's head where the token says it is (**MOVED-HEAD** = withdrawn),
* is the branch already on master (**SPENT** = flip it to merged; the INT-034
  failure, where 15 of 15 ready entries were already-merged work),
* does the branch share any commit with the never-merge closure (**VOID**,
  ruling 109) — see :func:`never_merge_closure` for why this is a set
  intersection and not an ancestry test,
* otherwise **LIVE-READY**.

Three deliberate refusals, all gotcha #53 — an absent comparison is not evidence
of health:

* a token whose head cannot be resolved is **UNRESOLVED**, never clean;
* a run where the never-merge set is empty prints ``containment: NOT RUN`` and
  says so in the verdict, rather than reporting every branch as uncontained;
* a token with no ``status:`` field is **MALFORMED** and is REPORTED, never
  silently read as not-ready (**ruling 115**). It is still resolved against git,
  so a malformed token over unmerged work is flagged as the emergency it is, and
  the header states coverage as a ratio so a half-blind sweep cannot print a
  confident list of only what it could see;
* a token whose ``status:`` is outside :data:`STATUS_VOCABULARY` is
  **UNKNOWN-STATUS** and is reported the same way (**ruling 118**). Same defect
  as ruling 115, one layer along: ``status in READY_VALUES`` treated an
  unrecognised value and a missing one identically, so fourteen hand-written
  statuses were being dropped by the same ``continue``. Human prose belongs in
  ``note:``, which is parsed and printed. ``--strict`` reds on ALL of these,
  not only the ones over live work — see :func:`main` for why the asymmetry
  with MALFORMED is deliberate.

Usage::

    python3 scripts/sweep_ready_tokens.py
    python3 scripts/sweep_ready_tokens.py --json
    python3 scripts/sweep_ready_tokens.py --strict     # exit 1 if a VOID token still reads ready
    python3 scripts/sweep_ready_tokens.py --never-merge <sha> [--never-merge <sha> ...]

Exit codes: ``0`` swept, ``1`` ``--strict`` and a void-but-ready token exists,
``2`` the handoff directory does not exist.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

DEFAULT_HANDOFF_DIR = ".claude/handoff"

#: Values of a token's ``status:`` field that mean "merge me". `ready` is here
#: because `READY-lane1-380.md` used it while carrying three real branches with
#: three open PRs — a one-word deviation that hid live work from a literal-bytes
#: grep for the long form. Accept both, and REPORT the short one rather than
#: silently normalising it, so the token gets fixed.
READY_VALUES = {"ready_for_integration", "ready"}

#: **Ruling 118 — the status field is a CLOSED VOCABULARY.**
#:
#: Every value a ``status:`` line is allowed to take. Anything else is
#: ``UNKNOWN-STATUS`` and is REPORTED, never silently read as "not ready".
#:
#: Why a closed set and not a free string: the sweep's ready test is
#: ``status in READY_VALUES``, so *every* unrecognised value already behaved
#: identically to a missing one — dropped by the ``continue`` below, absent from
#: every verdict group, invisible to every grep. That is ruling 115's defect
#: exactly, one layer along: ruling 115 closed the case where a token says
#: NOTHING, and left open the case where a token says something no reader
#: understands. Measured on the day this was banked, 14 of 194 tokens sat in the
#: second case, wearing 11 distinct hand-written values::
#:
#:     '⛔ STILL VISIBLE, NOT MERGE-ELIGIBLE — no ready_for_integration token.'
#:     'BOUNCED by INT-087 — merged as 72b7ed7a, REVERTED as e61ef179.'
#:     'merged + DDL HALF NOW DISCHARGED — INT-075, 2026-08-17. All three ...'
#:     'superseded-by-READY-lane1-1991'   'BLOCKED_codex_C-SEN-1'   ...
#:
#: The third is the one that settles the argument: it *starts* with the word
#: ``merged`` and is not equal to it, so a literal-bytes grep for
#: ``status: merged`` — which is how a human audits 194 files — skips it. The
#: prose is not the problem; the prose being in the MACHINE FIELD is. Human
#: sentences belong in ``note:``, which this script parses and prints beside the
#: verdict precisely so nobody has to smuggle them into ``status:`` again.
#:
#: Kept deliberately small. A value earns a place here only if a reader must
#: BRANCH on it; everything else is a defined value plus a ``note:``.
STATUS_VOCABULARY = {
    # merge offers
    "ready_for_integration",  # the long form, the one to write
    "ready",                  # short form — accepted, and REPORTED so it gets fixed
    # terminal
    "merged",
    "partially_merged",       # some branches of a multi-branch token landed. Real and distinct:
                              # collapsing it to `merged` asserts something false about the rest.
    "bounced",                # merged and then REVERTED. Ancestry survives a revert and content
                              # does not, so this can never be folded into `merged` (cal-43/#2076).
    "void",                   # ruling 109
    "superseded",             # a later token replaces it — name the successor in `note:`
    "withdrawn",              # the lane pulled it back
    # not terminal, not an offer
    "blocked",                # say WHY in `note:`, not in the status
    "held",
    "never_merge",            # containment head — both spellings, the field is `never_merge:`
    "never-merge",
    # ruling 118, and the reason it is a VOCABULARY entry rather than a code exemption:
    # a token can be deliberately visible while carrying no merge claim at all. Before this
    # existed, the only way to express it was to omit `status:` — which ruling 115 correctly
    # calls silence. `excused` is how that intent is SAID.
    "excused",
}

#: Tokens whose absent ``status:`` is a DOCUMENTED deliberate choice, excused by
#: name until the owning lane writes ``status: excused``.
#:
#: This is an allowlist of exactly one, and it is spelled out rather than
#: inferred, because "the sweep decided this omission looked intentional" is the
#: guess ruling 115 forbids. The reason string is printed in the report, so the
#: excusal argues for itself in front of the next reader instead of being a
#: silent skip.
DELIBERATE_OMISSIONS = {
    "READY-calibration-52.md": (
        "deliberate, documented at PROGRAM-CALIBRATION-QUEUE.md:2294 — visible, not "
        "merge-eligible. Owed: the lane writes `status: excused` and this entry is deleted."
    ),
}

#: Verdicts, most-blocking first. Order matters: a branch that is BOTH spent and
#: void is reported void, because the void is the fact that needs acting on.
#: Ruling 115. First in the order below because a token that cannot be READ is a
#: prior question to any verdict about the branch it names.
MALFORMED = "MALFORMED"
#: Ruling 118. Ranked immediately after MALFORMED and for the same reason: a
#: status nobody can interpret is a prior question to any verdict about the
#: branch, and it fails in the identical direction — invisibly, as "not ready".
UNKNOWN_STATUS = "UNKNOWN-STATUS"
#: Ruling 118. A token that says, in the vocabulary, that it is deliberately not
#: an offer. Distinct from MALFORMED (which is silence) and from HELD.
EXCUSED = "EXCUSED"
VOID = "VOID"
UNRESOLVED = "UNRESOLVED"
MOVED_HEAD = "MOVED-HEAD"
SPENT = "SPENT"
LIVE_READY = "LIVE-READY"
HELD = "HELD"

#: Underlying verdicts that make a MALFORMED token an EMERGENCY rather than
#: bookkeeping: the branch RESOLVED and is not on base, so there are real commits
#: nobody is looking at.
#:
#: ``UNRESOLVED`` is deliberately NOT in this set. A token whose branch cannot be
#: resolved might name a live branch or a deleted one, and calling that "real
#: work" would assert a fact from an absence — the exact error ruling 115 is
#: about, committed by ruling 115's own enforcement. It gets its own honest
#: label instead, and does not red ``--strict``, because adding a ``status:``
#: field would not fix it: the ``branch:`` field is broken too.
MALFORMED_OVER_LIVE_WORK = {LIVE_READY, MOVED_HEAD}


def normalize_status(status):
    """Pure. The single spelling rule for a status value. ``None`` stays ``None``.

    Case and surrounding whitespace are not meaning: ``SUPERSEDED`` and
    ``superseded`` were both in the directory on the day ruling 118 was banked,
    and treating them as two values would have made the vocabulary argue with
    itself. Nothing else is normalised — in particular a trailing clause is NOT
    stripped down to its first word, because ``merged + DDL HALF NOW
    DISCHARGED`` must come back UNKNOWN rather than quietly becoming ``merged``.
    Silently repairing the token is how the prose survives.
    """
    if status is None:
        return None
    return str(status).strip().lower()


class UnknownStatus(Exception):
    """Ruling 118: the token stated a status outside the closed vocabulary.

    Deliberately NOT a subclass of :class:`MalformedToken`. They are different
    facts with different fixes — silence needs a field added, an unknown value
    needs a word changed or moved to ``note:`` — and an ``except MalformedToken``
    somewhere would otherwise swallow this the day it was introduced.
    """

    def __init__(self, value):
        self.value = value
        super().__init__(f"status {value!r} is outside the closed vocabulary (ruling 118)")


def _clean(value: str) -> str:
    """Strip the markdown a token field is usually dressed in.

    Real tokens write ``branch: **`program/calibration-74`**``, so a naive
    ``split(":", 1)[1].strip()`` yields a branch name git has never heard of.

    Underscores are deliberately NOT stripped, though ``_x_`` is also markdown
    italics: the underscore is load-bearing inside the values this field carries
    (``ready_for_integration``, ``never_merge``). Stripping it turned every ready
    token into ``readyforintegration`` and the sweep reported an EMPTY ready set —
    caught on the first run of the impure test, which is the whole of ruling 102.
    """
    value = value.split("#", 1)[0]
    return value.replace("*", "").replace("`", "").strip()


def parse_token(text: str) -> dict:
    """Pull ``status`` / ``branch`` / ``head`` / ``never_merge`` out of a token. Pure.

    Only the FIRST occurrence of each field counts. Tokens quote other tokens in
    their prose (a report will happily contain the string ``status: merged``
    inside a paragraph about a previous cycle), and the header is the claim.

    ``note`` is parsed for ruling 118: it is the field the prose is supposed to
    live in, so the sweep has to actually READ it and print it. A field the tool
    ignores is a field nobody fills in.
    """
    out = {"status": None, "branch": None, "head": None, "never_merge": False,
           "note": None}
    for line in text.splitlines():
        stripped = line.strip()
        for key in ("status", "branch", "head", "never_merge", "note"):
            if out.get(key) not in (None, False):
                continue
            prefix = key + ":"
            if not stripped.lower().startswith(prefix):
                continue
            value = _clean(stripped[len(prefix):])
            if key == "never_merge":
                out[key] = value.lower() in {"true", "yes", "1"}
            elif value:
                out[key] = value
    return out


class MalformedToken(Exception):
    """A token stated no status. There is no boolean answer to return."""


def is_ready(status) -> bool:
    """Pure. **Ruling 115: a missing ``status:`` is MALFORMED, not not-ready.**

    A token with no status field has not said "no" — it has said nothing, and
    returning ``False`` for both renders an absence in the same bytes as a
    decision. That silent ``False`` hid live work in five consecutive cycles:
    `READY-calibration-75.md` (invisible for a full cycle over gate-clean work,
    named in ruling 113's charter case), and then, in the cycle that banked this
    ruling, `READY-ux-99.md` and `READY-lane1-386.md` — the first of which had no
    PR either, so ruling 113's second source could not catch it and only a
    hand-written directive did.

    Inferring ready from the filename is still refused, for the reason it always
    was: it would make all 178 historical tokens in the directory live again.
    Absence cannot be resolved by guessing its direction. It is REPORTED.

    **Ruling 118** adds the second half of the same idea: a status the reader
    does not recognise has also not said "no". It raises :class:`UnknownStatus`
    rather than returning ``False``, because returning ``False`` renders
    ``BLOCKED_codex_C-SEN-1`` and ``merged`` in the same bytes — one is a lane
    waiting on a gate, the other is finished work, and the sweep was calling
    them the same thing.

    Raises:
        MalformedToken: ``status`` is None, empty, or whitespace only.
        UnknownStatus: ``status`` is outside :data:`STATUS_VOCABULARY`.
    """
    if status is None or not str(status).strip():
        raise MalformedToken("token carries no status: field")
    value = normalize_status(status)
    if value not in STATUS_VOCABULARY:
        raise UnknownStatus(str(status).strip())
    return value in READY_VALUES


def classify(token: dict, resolved_head, on_master: bool, shared) -> str:
    """Pure. `shared` = commits this branch has in common with the never-merge closure."""
    if token.get("never_merge"):
        return HELD
    if shared:
        return VOID
    if resolved_head is None:
        return UNRESOLVED
    if on_master:
        return SPENT
    token_head = token.get("head")
    if token_head and not resolved_head.startswith(token_head.lower()[:7]):
        return MOVED_HEAD
    return LIVE_READY


def _git(runner, repo, *args):
    """Return stdout, or None when git refuses. Never raises."""
    try:
        proc = runner(
            ["git", "-C", repo, *args],
            capture_output=True, text=True, check=False,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _is_ancestor(runner, repo, ancestor, descendant) -> bool:
    try:
        proc = runner(
            ["git", "-C", repo, "merge-base", "--is-ancestor", ancestor, descendant],
            capture_output=True, text=True, check=False,
        )
    except Exception:
        return False
    return proc.returncode == 0


def _commits_not_on_base(runner, repo, base, head):
    """``git rev-list base..head`` as a set. None when git refuses."""
    out = _git(runner, repo, "rev-list", f"{base}..{head}")
    if out is None:
        return None
    return {line.strip() for line in out.splitlines() if line.strip()}


def open_pull_requests(runner, repo, base):
    """Open PRs whose head is NOT already on ``base``, with their CI rollup.

    **Ruling 113: a merge offer is a branch with a green gate, not a file.** The
    token sweep above reads what lanes WROTE; this reads what they OFFERED. Two
    consecutive Integrator cycles missed live merge-eligible work because a PR
    is a real offer and no token described it — `#2049`/`#2050` sat behind a
    token the parser read as ``branch: None``, and `#2054`/`#2055` had no token
    at all while `#2055` gated 31 downstream applies.

    Returns ``(rows, error)``. **`error` is not optional decoration.** This is
    the one part of the sweep that makes a NETWORK call, and `gh` missing,
    unauthenticated, rate-limited or slow all produce an empty list that is
    indistinguishable from "no PRs are open" (gotcha #53). So the failure is
    returned as a REASON and rendered as ``NOT RUN``, never as an empty section.
    """
    fields = "number,title,headRefName,headRefOid,mergeable,mergeStateStatus,isDraft,statusCheckRollup"
    try:
        proc = runner(
            ["gh", "pr", "list", "--state", "open", "--limit", "100", "--json", fields],
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        return [], "gh not installed"
    except Exception as exc:  # noqa: BLE001 - the reason is the product here
        return [], f"gh could not run: {type(exc).__name__}"
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()
        return [], f"gh exited {proc.returncode}: {detail[0] if detail else 'no stderr'}"
    try:
        raw = json.loads(proc.stdout or "[]")
    except ValueError:
        return [], "gh returned output that is not JSON"

    rows = []
    for pr in raw:
        head = pr.get("headRefOid") or ""
        # Contained by CONTENT-bearing ancestry, same test the token sweep uses
        # for SPENT. A PR whose head is already on base is not an offer.
        if head and _is_ancestor(runner, repo, head, base):
            continue
        checks = pr.get("statusCheckRollup") or []
        concl = [c.get("conclusion") or c.get("state") or "" for c in checks]
        failed = [c for c in concl if c in ("FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED")]
        pending = [c for c in concl if c in ("", "PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED")]
        if not checks:
            ci = "NO CHECKS"
        elif failed:
            ci = f"RED ({len(failed)})"
        elif pending:
            ci = f"PENDING ({len(pending)})"
        else:
            ci = "GREEN"
        rows.append({
            "number": pr.get("number"),
            "branch": pr.get("headRefName"),
            "head": head[:8],
            "draft": bool(pr.get("isDraft")),
            "mergeable": pr.get("mergeable"),
            "merge_state": pr.get("mergeStateStatus"),
            "ci": ci,
            "title": (pr.get("title") or "")[:60],
        })
    rows.sort(key=lambda r: r["number"] or 0)
    return rows, None


def never_merge_closure(runner, repo, base, heads):
    """Every commit reachable from a never-merge head and NOT already on ``base``.

    **This is the containment primitive, and plain head-ancestry is the wrong
    one** — which this cycle proved by shipping the wrong one first.

    Testing ``is-ancestor(never_merge_head, candidate)`` asks whether the
    candidate is DOWNSTREAM of the retired head. It answered "no" for all five
    contaminated branches, because the poison is not the retired head — it is
    `02cd7ad8`, an ANCESTOR of never-merge `provenance-r5`, sitting upstream of
    four branches that never touched `provenance-r5` at all.

    Reversing the test is not the fix either: `origin/master` is an ancestor of
    `provenance-r5` too, so "is an ancestor of a never-merge head" marks the
    entire repository void.

    The set that is actually forbidden is the never-merge lineage MINUS what is
    already shipped: `base..head`. A candidate is contaminated when its own
    `base..head` intersects it. Master's commits fall out by construction, and
    a branch is contaminated by the specific commits it shares — which are named
    in the report, so the finding can be checked rather than believed.
    """
    closure = set()
    unreadable = []
    for entry in heads:
        commits = _commits_not_on_base(runner, repo, base, entry["head"])
        if commits is None:
            unreadable.append(entry)
            continue
        closure |= commits
    return closure, unreadable


def sweep(handoff_dir, repo, runner=subprocess.run, extra_never_merge=(),
          include_prs=True,
          base="origin/master"):
    """Read every READY token, resolve it against git, apply ruling 109."""
    names = sorted(
        n for n in os.listdir(handoff_dir)
        if n.startswith("READY-") and n.endswith(".md")
    )

    tokens = []
    for name in names:
        path = os.path.join(handoff_dir, name)
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError:
            continue
        parsed = parse_token(text)
        parsed["file"] = name
        tokens.append(parsed)

    # The never-merge SET first — the closure cannot be computed without it.
    never_merge = []
    for token in tokens:
        if not token.get("never_merge"):
            continue
        head = _git(runner, repo, "rev-parse", token["branch"]) if token.get("branch") else None
        head = head or token.get("head")
        if head:
            never_merge.append({"head": head, "source": token["file"]})
    for head in extra_never_merge:
        never_merge.append({"head": head, "source": "--never-merge"})

    closure, unreadable = never_merge_closure(runner, repo, base, never_merge)

    # Ruling 113: the second source. Never lets its own failure read as "none".
    pr_rows, pr_error = (([], "disabled") if not include_prs
                         else open_pull_requests(runner, repo, base))

    rows = []
    malformed_files = []
    unknown_status_files = []
    excused_files = []
    for token in tokens:
        # Ruling 115. A token that states no status is MALFORMED, and MALFORMED is
        # carried into the report — never dropped by the same `continue` that
        # discards a token honestly marked `merged`.
        # Ruling 118 adds the sibling case: a status OUTSIDE the closed vocabulary
        # is UNKNOWN-STATUS, and is carried into the report by the same route, for
        # the same reason — it was being dropped by that identical `continue`.
        malformed = unknown = excused = False
        try:
            ready = is_ready(token.get("status"))
        except MalformedToken:
            ready = False
            # Ruling 118: an omission the owning lane documented is EXCUSED by name,
            # not MALFORMED. Everything else is still silence.
            if token["file"] in DELIBERATE_OMISSIONS:
                excused = True
                excused_files.append(token["file"])
            else:
                malformed = True
                malformed_files.append(token["file"])
        except UnknownStatus:
            unknown, ready = True, False
            unknown_status_files.append(token["file"])
        else:
            # `excused` is a real vocabulary value, so a token that SAYS it lands
            # here rather than in the MalformedToken arm above.
            if normalize_status(token.get("status")) == "excused":
                excused = True
                excused_files.append(token["file"])
        if not (ready or malformed or unknown or excused or token.get("never_merge")):
            continue
        branch = token.get("branch")
        resolved = _git(runner, repo, "rev-parse", branch) if branch else None
        if resolved is None and token.get("head"):
            resolved = _git(runner, repo, "rev-parse", "--verify", token["head"] + "^{commit}")

        shared = []
        if resolved and closure and not token.get("never_merge"):
            own = _commits_not_on_base(runner, repo, base, resolved)
            if own:
                shared = sorted(own & closure)

        on_master = bool(resolved) and _is_ancestor(runner, repo, resolved, base)
        # Ruling 115 obligation 2: a malformed token is resolved against git like
        # any other and carries the verdict it WOULD have had, so "malformed over
        # spent work" (bookkeeping) is distinguishable at a glance from "malformed
        # over three unmerged commits" (a lane's work with nobody looking).
        underlying = classify(token, resolved, on_master, shared)
        # Ruling 118 inherits ruling 115's obligation 2 verbatim: an unreadable
        # token is still resolved against git and carries the verdict it WOULD
        # have had, so "unknown status over spent work" (bookkeeping) is
        # distinguishable at a glance from "unknown status over live commits".
        if malformed:
            verdict = MALFORMED
        elif unknown:
            verdict = UNKNOWN_STATUS
        elif excused:
            verdict = EXCUSED
        else:
            verdict = underlying
        # NOT named `unreadable`: that name belongs to the never-merge closure's
        # unreadable-heads list in this same function, and shadowing it made the
        # sweep raise on the return statement.
        status_unreadable = malformed or unknown
        rows.append({
            "file": token["file"],
            "branch": branch,
            "token_head": token.get("head"),
            "resolved_head": resolved,
            "status": token.get("status"),
            "status_is_short_form": normalize_status(token.get("status")) == "ready",
            "note": token.get("note"),
            "verdict": verdict,
            "underlying": underlying if (status_unreadable or excused) else None,
            "over_live_work": bool(status_unreadable and underlying in MALFORMED_OVER_LIVE_WORK),
            "excused_reason": DELIBERATE_OMISSIONS.get(token["file"]) if excused else None,
            "contains_never_merge": [c[:8] for c in shared],
        })

    return {
        "handoff_dir": handoff_dir,
        "base": base,
        "tokens_read": len(tokens),
        "never_merge_heads": [
            {"head": e["head"][:8], "source": e["source"]} for e in never_merge
        ],
        "closure_size": len(closure),
        "unreadable_never_merge_heads": [e["source"] for e in unreadable],
        # Obligation 4 of ruling 109: an unrun check is reported UNRUN, never clean.
        # A head we could not read makes the closure INCOMPLETE, so that is not
        # clean either — an under-read closure produces false LIVE-READY verdicts,
        # which is the exact failure the ruling was written about.
        "containment_ran": bool(never_merge) and not unreadable,
        "open_prs": pr_rows,
        "open_prs_error": pr_error,
        # Ruling 115 obligation 4: coverage as a RATIO. A sweep that prints only
        # what it could read can never disclose that it read half of it.
        "malformed_tokens": sorted(malformed_files),
        # Ruling 118 obligation: coverage counts a status the reader cannot
        # INTERPRET against the same ratio as one that is absent. Both are
        # tokens the sweep did not understand, and a ratio that quietly counted
        # `BLOCKED_codex_C-SEN-1` as "readable" would be the ratio lying about
        # exactly the thing it exists to disclose.
        "unknown_status_tokens": sorted(unknown_status_files),
        "excused_tokens": sorted(excused_files),
        "status_readable": len(tokens) - len(malformed_files) - len(unknown_status_files),
        "status_vocabulary": sorted(STATUS_VOCABULARY),
        "rows": rows,
    }


def render(result) -> str:
    lines = []
    lines.append(f"READY sweep — {result['handoff_dir']} — {result['tokens_read']} token files read")
    # Ruling 115 obligation 4 — coverage stated as a ratio, always, so a blind
    # sweep cannot print a confident list of only what it could see.
    readable = result.get("status_readable")
    malformed_files = result.get("malformed_tokens") or []
    unknown_files = result.get("unknown_status_tokens") or []
    if readable is not None:
        line = (f"status coverage: {readable} of {result['tokens_read']} tokens carry a "
                "readable status: field")
        if malformed_files:
            line += (f" — {len(malformed_files)} MALFORMED. A missing status is not a quiet "
                     "'no'; it is silence (ruling 115).")
        if unknown_files:
            line += (f" — {len(unknown_files)} UNKNOWN-STATUS, outside the closed vocabulary. "
                     "A status nobody can interpret fails in the same direction as a missing "
                     "one: silently, as 'not ready' (ruling 118).")
        lines.append(line)
    if result["containment_ran"]:
        heads = ", ".join(
            f"{e['head']} ({e['source']})" for e in result["never_merge_heads"]
        )
        lines.append(
            f"never-merge containment: RAN against {len(result['never_merge_heads'])} head(s) "
            f"— {heads}; closure = {result['closure_size']} commit(s) not on {result['base']}"
        )
    elif result["unreadable_never_merge_heads"]:
        lines.append(
            "never-merge containment: INCOMPLETE — could not read "
            f"{result['unreadable_never_merge_heads']}. The closure is under-read, so a "
            "LIVE-READY verdict below may be false (ruling 109 obligation 4, gotcha #53)."
        )
    else:
        lines.append(
            "never-merge containment: NOT RUN — no head carries never_merge: true. "
            "This is NOT a clean result (ruling 109 obligation 4, gotcha #53)."
        )
    lines.append("")
    order = [MALFORMED, UNKNOWN_STATUS, VOID, UNRESOLVED, MOVED_HEAD, SPENT, LIVE_READY,
             HELD, EXCUSED]
    for verdict in order:
        group = [r for r in result["rows"] if r["verdict"] == verdict]
        if not group:
            continue
        header = f"── {verdict} ({len(group)})"
        if verdict in (MALFORMED, UNKNOWN_STATUS):
            live = sum(1 for r in group if r.get("over_live_work"))
            unres = sum(1 for r in group if r.get("underlying") == UNRESOLVED)
            what = ("no status: field" if verdict == MALFORMED
                    else "status outside the closed vocabulary (ruling 118) — move the prose "
                         "to note: and use a defined value")
            header += (f" — {what}. {live} sit over UNMERGED work and are "
                       f"invisible to every sweep; {unres} more cannot be resolved at all "
                       f"({'ruling 115' if verdict == MALFORMED else 'ruling 118'})")
        elif verdict == EXCUSED:
            header += (" — deliberately not a merge offer, and SAYS so. Listed, never hidden: "
                       "an excusal that cannot be seen is indistinguishable from an oversight")
        lines.append(header)
        for row in group:
            head = (row["resolved_head"] or "unresolved")[:8]
            line = f"   {row['file']:<44} {str(row['branch']):<38} {head}"
            if verdict in (MALFORMED, UNKNOWN_STATUS, EXCUSED):
                line += f"  would be {row.get('underlying')}"
                if row.get("over_live_work"):
                    line += "   ⚠ REAL WORK, INVISIBLE"
                elif row.get("underlying") == UNRESOLVED:
                    line += "   ⚠ branch UNRESOLVED — cannot rule out live work"
            if verdict == UNKNOWN_STATUS:
                line += f"\n        status: {row.get('status')!r}"
            if row.get("excused_reason"):
                line += f"\n        excused: {row['excused_reason']}"
            if row["contains_never_merge"]:
                line += "  contains " + ",".join(row["contains_never_merge"])
            if row["status_is_short_form"]:
                line += "   [status: ready — short form, fix the token]"
            if row.get("note"):
                line += f"\n        note: {row['note']}"
            lines.append(line)
        lines.append("")
    # ---- ruling 113: the second source, and its NOT-RUN discipline ----
    err = result.get("open_prs_error")
    prs = result.get("open_prs") or []
    if err == "disabled":
        lines.append(
            "open PRs: NOT RUN — --no-prs was passed. This is NOT a clean result: a merge "
            "offer is a branch with a green gate, not a file (ruling 113)."
        )
    elif err:
        lines.append(
            f"open PRs: NOT RUN — {err}. This is NOT a clean result. An unreadable PR list "
            "and an empty PR list look identical (gotcha #53), so nothing below rules out a "
            "green, merge-eligible PR that no token describes (ruling 113)."
        )
    elif not prs:
        lines.append(
            f"open PRs: RAN against {result['base']} — none open whose head is not already "
            "upstream."
        )
    else:
        ready = [r for r in prs if r["ci"] == "GREEN" and not r["draft"]]
        lines.append(
            f"── OPEN PRs ({len(prs)}) — merge offers the token sweep cannot see (ruling 113); "
            f"{len(ready)} green and non-draft"
        )
        for r in prs:
            flag = "  [DRAFT]" if r["draft"] else ""
            lines.append(
                f"   #{str(r['number']):<6} {str(r['branch']):<38} {r['head']}  "
                f"{r['ci']:<12} {str(r['merge_state'] or '?'):<10}{flag}  {r['title']}"
            )
        lines.append("")
        lines.append(
            "   Ruling 034 still governs: a PR promotes a branch into the candidate set and "
            "does not decide readiness. Confirm by CONTENT before merging."
        )
    lines.append("")

    void_but_ready = [r for r in result["rows"] if r["verdict"] == VOID]
    if void_but_ready:
        lines.append(
            f"RULING 109: {len(void_but_ready)} token(s) are VOID — their branch contains a "
            "never-merge ancestor. Mark them void with the reason in the file. They re-earn "
            "ready only from a branch REBUILT without the ancestor."
        )
    blind = [r for r in result["rows"] if r["verdict"] == MALFORMED and r.get("over_live_work")]
    if blind:
        lines.append(
            f"RULING 115: {len(blind)} token(s) carry NO status: field over UNMERGED work — "
            "the sweep cannot see them, and neither can the next Integrator. Add "
            "`status: ready_for_integration` (or `merged`) to: "
            + ", ".join(r["file"] for r in blind)
        )
    unknown_rows = [r for r in result["rows"] if r["verdict"] == UNKNOWN_STATUS]
    if unknown_rows:
        hidden = [r for r in unknown_rows if r.get("over_live_work")]
        line = (
            f"RULING 118: {len(unknown_rows)} token(s) state a status outside the closed "
            "vocabulary, so every sweep has silently read them as 'not ready'. Replace the "
            "value with one of "
            + ", ".join(sorted(result.get("status_vocabulary") or STATUS_VOCABULARY))
            + " and move the sentence to a `note:` line: "
            + ", ".join(r["file"] for r in unknown_rows)
        )
        if hidden:
            # The whole argument for the ruling, stated with names in it. A count
            # persuades nobody; "this branch has commits and nobody is looking"
            # is the same fact and it gets fixed.
            line += (
                "\n            ⚠ " + str(len(hidden)) + " of those sit over UNMERGED work and "
                "were invisible to every prior sweep: "
                + ", ".join(f"{r['file']} ({r['branch']}, would be {r['underlying']})"
                            for r in hidden)
            )
        lines.append(line)
    return "\n".join(lines)


def main(argv=None, runner=subprocess.run, stdout=None) -> int:
    stdout = stdout if stdout is not None else sys.stdout
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--handoff-dir", default=DEFAULT_HANDOFF_DIR)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 if a VOID token still reads ready, a MALFORMED "
                             "token sits over unmerged work, or any token states a status "
                             "outside the closed vocabulary (rulings 109, 115, 118)")
    parser.add_argument("--no-prs", action="store_true",
                        help="skip the open-PR source; reported as NOT RUN, never as clean")
    parser.add_argument("--never-merge", action="append", default=[],
                        help="an additional never-merge head, repeatable")
    parser.add_argument("--base", default="origin/master",
                        help="what counts as already-shipped when computing the closure")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.handoff_dir):
        print(f"no such handoff dir: {args.handoff_dir}", file=stdout)
        return 2

    result = sweep(args.handoff_dir, args.repo, runner=runner,
                   extra_never_merge=tuple(args.never_merge), base=args.base,
                   include_prs=not args.no_prs)
    print(json.dumps(result, indent=2) if args.json else render(result), file=stdout)

    if args.strict:
        # Ruling 115 obligation 5: a defect that cannot red a gate is a defect that
        # gets written down for five cycles. INT-102 wrote the fix request into its
        # own queue file and the field was still absent one cycle later.
        if any(r["verdict"] == VOID for r in result["rows"]):
            return 1
        if any(r["verdict"] == MALFORMED and r.get("over_live_work") for r in result["rows"]):
            return 1
        # Ruling 118, and the same obligation applied to its own defect. An
        # out-of-vocabulary status is red on sight — NOT only when it sits over
        # live work, which is where it differs from MALFORMED above.
        #
        # The asymmetry is deliberate. A missing status can be an ancient merged
        # token nobody will ever touch again, so redding on all 13 of those would
        # make --strict permanently red and therefore ignored. An unknown status
        # is different in kind: someone TYPED it, this cycle or another, and the
        # fix is one word plus a `note:` line. The set is small, closed, and
        # drainable — which is the only honest reason to gate on all of it.
        if any(r["verdict"] == UNKNOWN_STATUS for r in result["rows"]):
            return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
