#!/usr/bin/env python3
"""#10769 successor gate: the acceptance amendment Alex approved 2026-10-25 03:18Z.

WHAT THIS FILE IS, AND WHAT IT IS NOT
-------------------------------------
`gate_futures_open_trgm_index.py` (the ORIGINAL gate), its baseline
`lat-p088-futures-open-trgm-red.json` and both 10/12 RED records are IMMUTABLE.
This file does not edit, re-grade or replace any of them. It imports the original
read-only (constants, the db-query round trip, the original semantics rule) so the
two can never drift, and it adds only what the amendment adopted
(`artifacts/release-root-10769-acceptance-decision-20261025T025855Z/DECISION.md`,
terms 1-6). Every clause below names its OLD text and its NEW text; `CRITERIA` is
the machine copy and every output record carries it.

Building this harness admits no measurement. The same independent reviewer
(lane1b) accepts the reading rule first; a read is a separate admission.

THE THREE TRACKS
----------------
`--track se`  /search futures name arm, all 8 original terms.
`--track ta`  typeahead futures ILIKE arm (the ship's surface), the same 8 terms.
`--track c4`  the typeahead READER, 8 single team words, `?debug_timing=1`.

`se` and `ta` time and plan a SQL arm through `/api/admin/db-query`. That is a
CUSTOM plan of literal SQL, run on the arm alone. The reader sends the same arm
as part of a larger asyncpg PREPARED statement, which Postgres may run with a
generic plan (#11552). So an arm read describes the custom-plan arm only. It is
never reader evidence and never feeds `c4`. Only `c4` reads the reader.

CLAUSE BY CLAUSE (old -> new)
-----------------------------
SHAPE (DECISION term 2). Old: a SUBJECT (its recorded before read
`ix_futures_name_trgm`) must read `ix_futures_name_trgm_open` AND not read
`ix_futures_name_trgm`; a bystander passes. New: unchanged, except a subject that
does not read the new index may still pass when ALL of these hold:
  (a) the same-instant no-trigram control (`no_trgm`: `name || '' ILIKE`) reads no
      trigram index on `futures_markets`, judged against the live catalog;
  (b) the ordinary plan does not read `ix_futures_name_trgm`;
  (c) the ordinary plan is open-only: at least one `WHERE status = 'open'` partial
      on `futures_markets` and no Seq Scan of it. (c) is this file's reading of the
      decision's "permits another valid open-only plan". It is flagged for the
      reviewer as an interpretation, not as adopted text.
  That pass is labelled PASS_EXCEPTION and carries "no claim that the new index
  helped this term". A RETAINED SHAPE failure whose plan read the forbidden index
  stays OWED: a later read that happens to choose another plan does not show the
  plan cannot flip back. Term 2 defines no clearing and the original graded each
  run fresh, so this too is this file's reading, flagged. Bystanders keep the
  original pass. D1 (failing a bystander
  that reads the whole-table index) was NOT adopted and is not applied.
  Because `no_trgm` disables every trigram path on `name` by construction, (a)
  discriminates only two things: the rewrite was complete, and no index the
  catalog cannot classify appears. That is said here so (a) is not over-read.
  /search grades BOTH the original SQL (G0) and the route-faithful arm; a term
  passes only if both pass. Typeahead has no recorded before, so subject status
  cannot be read from one; every typeahead term is graded as a subject, the
  stricter of the two choices.

/search BUDGET (term 3). Old: median over subjects of ratio_after/ratio_before
<= 0.5. New: WITHDRAWN. Recorded verbatim: "/search speedup attributable to
ix_futures_name_trgm_open: NOT PROVEN". This file computes no collapse and no
median, so no number exists to be misread as credit. Typeahead's speed is proven,
or not, by `c4` alone and never counts as a /search result.

/search NO-REGRESSION (term 4). Old = new: per term, on the ORIGINAL SQL,
ratio_after <= 1.5 x ratio_before (outcome-arm controlled, the 10/08 baseline).
The original SQL is proven unchanged before any read: the 24 G0 statements must
hash to `G0_SQL_SHA16`, the values compiled at the baseline's own commit
(`3908c039e5`), at the 10/12 RED run (`89031000dc`) and at `2f18107550`. A
mismatch exits 2: changed SQL is never compared with the old baseline. The
original SEQUENCE is kept too: all 8 terms' timed rounds run back to back, in
TERMS order, before any SHAPE, faithful or semantics read (`run_se` pass 1). One fix in
the fail-closed direction: a term with no before ratio is NOT_EVALUABLE (the
original passed it). Every retained failure is listed and stays OWED: no harness
observation clears it, because the amendment defines no clearing observation and
this file does not invent one. So `--track se` cannot exit 0 while any retained
failure is OWED. That is the decision's term 4, not a harness defect.

SEMANTICS (term 1, unchanged-answer protection). Old: the full /search arm's
ordered ids, usable vs `no_partial` vs `no_trgm`, same instant. Kept exactly (the
original function is called). Added on the faithful /search arm and on the
typeahead arm: the same three variants, compared as `count(*)` + md5 of the
id-ordered set, server-side, so db-query's row cap cannot truncate the comparison.
No other rewrite is used. In particular `status BETWEEN 'open' AND 'open'` is not
here: it only existed to attribute a speedup, attribution was not adopted, and
its correctness depends on collation and server version that this file could not
prove.

C4 (term 5, reader speed). Original: the typeahead `futures_query` stage on single
team words drops versus 2026-10-08's 0.17-0.89 s. The retained before is that
RANGE only, plus `futures_outcome_arm` 0.24-1.17 s from the same reads
(`lat-p088-futures-open-trgm-index-spec.md`). Its words were not recorded and no
per-word value survives. The proposed reading rule adds no number that is not in
that record:
  * per word, one cold read (`debug_timing` bypasses the cache both ways), no
    re-read;
  * DROP: `futures_query` < 170 ms, the before's FASTEST value;
  * LOAD MATCH: the same request's `futures_outcome_arm` >= 240 ms, the before's
    fastest. The index cannot serve that arm (the issue says so), so a faster
    control means a quieter database, and a drop under it is not credited;
  * C4 PAID iff every one of the 8 words DROPs under a matched load. A shed or
    timed-out stage, a non-200 or a missing word is NOT_EVALUABLE, never a pass.
It cannot establish that the 10/08 words were these words, that the reader code
path is unchanged since 10/08, or which plan the reader's prepared statement
used. The reviewer accepts or rejects this rule; no other is adopted.

VERDICTS. PASS / PASS_EXCEPTION / FAIL / NOT_EVALUABLE (input missing or
unclassifiable, never a pass) / OWED / WITHDRAWN. Exit 0 = every graded clause
on the track passed and nothing is OWED. Exit 1 = a result that is not that.
Anything else is the harness failing to run, not a verdict (gotcha #54).

USAGE
-----
    python3 backend/scripts/gate_10769_successor.py --criteria
    python3 backend/scripts/gate_10769_successor.py --track se --dry-run
    source ~/.claude/.env && python3 backend/scripts/gate_10769_successor.py \\
        --track ta --out ~/bainluck/artifacts/<dir>/lat-10769-successor-ta-<UTC>.json

`--dry-run` compiles every statement, checks the original-SQL hashes and the
retained-record hashes, refuses (exit 2) if either same-instant rewrite cannot be
built on any statement, prints the request count and exits. It makes no request.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
REPO = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
sys.path.insert(0, HERE)

from sqlalchemy import and_, or_, select  # noqa: E402

import explain_search_arm as ESA  # noqa: E402
import gate_futures_open_trgm_index as G  # noqa: E402  (the ORIGINAL, read-only)

from app.models.models import FuturesMarket  # noqa: E402
from app.routes import events as E  # noqa: E402
from app.utils.agent_origin import tagged  # noqa: E402

API = G.API
RELATION = "futures_markets"

#: Imported, never restated: the successor grades the same terms against the same
#: indexes with the same regression factor and rewrites as the original.
TERMS = G.TERMS
EXPECTED_INDEX = G.EXPECTED_INDEX
FORBIDDEN_INDEX = G.FORBIDDEN_INDEX
PER_TERM_REGRESSION_FACTOR = G.PER_TERM_REGRESSION_FACTOR
ROUNDS = G.DEFAULT_ROUNDS
VARIANTS = G.SEMANTICS_VARIANTS

PASS = "PASS"
PASS_EXCEPTION = "PASS_EXCEPTION"
FAIL = "FAIL"
NOT_EVALUABLE = "NOT_EVALUABLE"
OWED = "OWED"
WITHDRAWN = "WITHDRAWN"
SUPERSEDED_RULE = "SUPERSEDED_RULE"
UNMATCHED = "UNMATCHED"
PAID = "PAID"
NOT_PAID = "NOT_PAID"
_PASSING = (PASS, PASS_EXCEPTION)

SE_BUDGET_STATEMENT = (
    "/search speedup attributable to ix_futures_name_trgm_open: NOT PROVEN "
    "(BUDGET withdrawn for /search by the 2026-10-25 amendment, term 3)"
)
NO_CREDIT_NOTE = "no claim that ix_futures_name_trgm_open helped this term"

#: sha256[:16] of each original statement, ISO timestamps normalised to `'<ts>'`.
#: Identical at 3908c039e5 (the commit that recorded the 10/08 baseline),
#: 89031000dc (the 10/12 01:15Z RED run) and 2f18107550 (receipt:
#: artifacts/release-1.0.4-pickup-20261011/latency-10769/gate-sql-identity-20261025).
G0_SQL_SHA16 = {
    "best picture|all": "195ba8d08ee9fddb",
    "best picture|name": "839a260f9717f16f",
    "best picture|outcome": "ec4ad80088680e2c",
    "champion|all": "b2a2a2306815c5fc",
    "champion|name": "8beeb776e7f8e2fd",
    "champion|outcome": "29a1755821c23501",
    "election|all": "420bb3f60c0e340b",
    "election|name": "eb3ae4b7433a39d4",
    "election|outcome": "422cec69d4a23e38",
    "presidential election|all": "ab906c70a14f0a92",
    "presidential election|name": "27462df264743176",
    "presidential election|outcome": "b6d2d70bd307d24a",
    "super bowl|all": "452a467cc62e03e6",
    "super bowl|name": "ddf614ce789dd01c",
    "super bowl|outcome": "e20018a5c9773e48",
    "winner|all": "6510c77042fde219",
    "winner|name": "1d6026425638efb6",
    "winner|outcome": "8a275b46a26c2ef1",
    "world cup|all": "e213a14362e1deed",
    "world cup|name": "0d4035a02367d8fd",
    "world cup|outcome": "58203c5b28cb84fb",
    "world series|all": "9bc2a5a554204f95",
    "world series|name": "a206cbbfec74acc8",
    "world series|outcome": "f5e9c201f4dea523",
}

AUDIT_DIR = G.AUDIT_DIR

#: Byte-identical copies of the two 10/12 RED records (originals untracked under
#: ~/bainluck/artifacts/release-1.0.4-pickup-20261011/latency-10769/).
RETAINED_READS = {
    "20261012T0005Z": (
        os.path.join(AUDIT_DIR, "lat-10769-retained-gate-after-20261012T0005Z.json"),
        "46802f4e70efc320d9f44ac48bc2f6d39ea20027b620fb29e674898b6ad71fff",
    ),
    "20261012T0115Z": (
        os.path.join(AUDIT_DIR, "lat-10769-retained-gate-after-same-instant-20261012T0115Z.json"),
        "ffbd38d2a3e4a1acaf7b3dcb1c3c1242b480e458cc006018b0954c834cb7ab57",
    ),
}

#: The retained single-word set (`1866-open-trgm-single-word-before.jsonl`). The
#: 10/08 reader before did not record its words, so this is the closest set, not
#: a proven match.
C4_WORDS = ("ranger", "steeler", "falcon", "eagle", "dodger", "yankee", "celtic", "packer")
#: The retained reader before: production 2026-10-08 18:1xZ, range endpoints only.
C4_BEFORE_MS = {"futures_query": (170, 890), "futures_outcome_arm": (240, 1170)}
C4_BEFORE_SOURCE = "docs/audits/latency/lat-p088-futures-open-trgm-index-spec.md (2026-10-08 18:1xZ)"
C4_TIMEOUT_S = 10

CRITERIA = {
    "C3.SHAPE": {
        "old": "subject (before read ix_futures_name_trgm): EXPECTED in plan AND FORBIDDEN not in plan; bystander passes",
        "new": "old rule, OR for a subject: no_trgm control reads no trigram index AND FORBIDDEN not in plan AND "
               "plan is open-only [open-only = this file's reading, flagged]; labelled PASS_EXCEPTION, "
               f"{NO_CREDIT_NOTE}; /search graded on G0 AND the faithful arm; typeahead terms all graded as subjects; "
               "a retained SHAPE failure whose plan read FORBIDDEN stays OWED and no later read clears it "
               "[this file's reading, flagged: term 2 defines no clearing and the original graded each run fresh]",
        "source": "DECISION.md term 2",
    },
    "C3.BUDGET(/search)": {
        "old": "median over subjects of ratio_after/ratio_before <= 0.5",
        "new": f"WITHDRAWN. {SE_BUDGET_STATEMENT}",
        "source": "DECISION.md term 3",
    },
    "C3.NO-REGRESSION(/search)": {
        "old": "per term ratio_after <= 1.5 x ratio_before, original SQL, 10/08 baseline",
        "new": "unchanged; original SQL proven by hash; original sequence (all 8 terms' timed rounds back to back, "
               "in TERMS order, before any other read); no before ratio = NOT_EVALUABLE; every retained failure OWED "
               "(no clearing observation is defined)",
        "source": "DECISION.md term 4",
    },
    "C3.SEMANTICS": {
        "old": "/search full arm ordered ids: usable == no_partial == no_trgm, same instant",
        "new": "unchanged, plus the same three variants on the faithful /search arm and the typeahead arm "
               "(count + md5 of the id-ordered set)",
        "source": "DECISION.md term 1",
    },
    "C4": {
        "old": "typeahead futures_query on single team words drops versus 0.17-0.89 s",
        "new": "PROPOSED, needs reviewer acceptance: every word futures_query < 170 ms with the same request's "
               "futures_outcome_arm >= 240 ms; shed/timeout/missing = NOT_EVALUABLE",
        "source": "DECISION.md term 5 (reading rule owed to the same reviewer)",
    },
    "C1/C2": {
        "old": "C1 catalog VALID; C2 ranger plan uses the index with far fewer blocks",
        "new": "earned credit retained, not re-graded; C1 validity is read as a PRECONDITION of each track",
        "source": "DECISION.md term 5",
    },
}


class VariantUnavailable(Exception):
    """A same-instant control that cannot be built honestly for this SQL."""


# --------------------------------------------------------------------------
# Term chains and arm builders: the route's own helpers, in the route's order.
# --------------------------------------------------------------------------

def typeahead_terms(q: str):
    """`typeahead_search`'s chain: parse_intent -> subject -> club short forms ->
    split -> strip scaffolding -> expand -> synonyms. Typeahead takes the subject
    of ANY intent; /search does not (see `search_terms`)."""
    intent = E.parse_intent(q)
    identity = intent.subject if intent else q
    identity = E.expand_club_short_forms(identity)
    terms = E._strip_search_scaffolding(identity.strip().split())
    if not terms:
        raise ValueError(f"{q!r} leaves no search terms")
    return terms, E._apply_search_synonyms(E.expand_search_terms(terms))


def search_terms(q: str):
    """`search_events`' chain: the subject only for `_IDENTITY_SUBSTITUTED_KINDS`."""
    intent = E.parse_intent(q)
    identity = (
        intent.subject
        if intent is not None and intent.kind in E._IDENTITY_SUBSTITUTED_KINDS
        else q
    )
    identity = E.expand_club_short_forms(identity)
    terms = E._strip_search_scaffolding(identity.strip().split())
    if not terms:
        raise ValueError(f"{q!r} leaves no search terms")
    return terms, E._apply_search_synonyms(E.expand_search_terms(terms))


def open_now(now: datetime) -> tuple:
    """Both routes' pushed-down open filter, including #4914's game-played
    anti-join, which the original G0 SQL omits."""
    return (
        FuturesMarket.status == E._FUTURES_OPEN_STATUS_SQL,
        or_(
            FuturesMarket.resolution_date.is_(None),
            FuturesMarket.resolution_date >= now,
        ),
        E._futures_game_already_played(),
    )


def typeahead_ilike_member(q: str, now: datetime):
    """The typeahead pool's futures-name ILIKE arm, as the UNION member it sends."""
    terms, expanded = typeahead_terms(q)
    if len(terms) > 1:
        flt = and_(*[E._build_round_word_ilike(FuturesMarket.name, t, x) for t, x in expanded])
    else:
        term, exp = expanded[0]
        flt = E._build_round_word_ilike(FuturesMarket.name, term, exp)
    return select(FuturesMarket.id).where(flt, *open_now(now))


def search_name_member(q: str, now: datetime):
    """The /search futures-name arm, as the UNION member it sends (faithful)."""
    terms, expanded = search_terms(q)
    if len(terms) > 1:
        flt = and_(*E._futures_multi_term_name_conditions(expanded))
    else:
        term, exp = expanded[0]
        flt = E._futures_name_match_term(term, exp)
    return select(FuturesMarket.id).where(flt, *open_now(now))


compile_sql = ESA.compile_sql
_TS = re.compile(r"'\d{4}-\d\d-\d\d[ T][\d:.+]+'")


def normalise(sql: str) -> str:
    return _TS.sub("'<ts>'", sql)


def g0_identity() -> dict[str, str]:
    """{term|arm: problem} for every original statement whose hash moved."""
    bad = {}
    for term in TERMS:
        for arm in ("name", "outcome", "all"):
            key = f"{term}|{arm}"
            got = hashlib.sha256(normalise(G._sql_for(term, arm)).encode()).hexdigest()[:16]
            if got != G0_SQL_SHA16.get(key):
                bad[key] = f"{got} != pinned {G0_SQL_SHA16.get(key)}"
    return bad


# --------------------------------------------------------------------------
# Same-instant controls.
# --------------------------------------------------------------------------

#: Operators a trigram index on `futures_markets.name` can serve. If one survives
#: the `no_trgm` rewrite, the control is not a no-trigram control.
_NAME_TRGM_OPERATOR = re.compile(
    r"futures_markets\.name\s+(?:NOT\s+)?(?:I?LIKE|~~\*?|!?~\*?|%>?|<<?%|SIMILAR)", re.I
)


def rewrite(sql: str, variant: str) -> str:
    """`sql` with the original gate's `variant` rewrite, refusing an incomplete one."""
    old, new = VARIANTS[variant]
    if old not in sql:
        raise VariantUnavailable(f"{variant}: anchor {old!r} absent")
    out = sql.replace(old, new)
    if variant == "no_trgm" and _NAME_TRGM_OPERATOR.search(out):
        raise VariantUnavailable(
            "no_trgm: a trigram-servable operator on futures_markets.name survives the rewrite"
        )
    if old in out:
        raise VariantUnavailable(f"{variant}: anchor survives the rewrite")
    return out


def set_digest_sql(member_sql: str) -> str:
    """count + md5 of the id-ordered set, computed server-side (no row cap)."""
    return (
        "SELECT count(*), md5(coalesce(string_agg(s.id::text, ',' ORDER BY s.id), '')) "
        f"FROM ({member_sql}) AS s"
    )


# --------------------------------------------------------------------------
# Plans: relation-scoped access fingerprint, skeleton, anti-join.
# --------------------------------------------------------------------------

def _root(plan):
    if isinstance(plan, dict) and "plan" in plan and "Node Type" not in plan:
        plan = plan["plan"]
    if isinstance(plan, list):
        plan = plan[0] if plan else {}
    if isinstance(plan, dict) and "Plan" in plan:
        plan = plan["Plan"]
    return plan if isinstance(plan, dict) else {}


def access_fingerprint(plan, relation: str = RELATION) -> list[dict]:
    """Every scan of `relation`: Seq/Index/Index Only/Bitmap Heap (one entry per
    Bitmap Index Scan beneath it, through BitmapAnd/BitmapOr) and any other node
    naming the relation. A bitmap child that is not an index scan is recorded with
    index None, which the classifier refuses. Scans of other relations (the
    anti-join's `events`) are excluded; the original `_bitmap_index_scans` saw
    neither btree Index Scans nor relation scope."""
    out: list[dict] = []

    def bitmap_leaves(node) -> list:
        leaves = []
        for child in node.get("Plans") or []:
            kind = child.get("Node Type")
            if kind == "Bitmap Index Scan":
                leaves.append(child.get("Index Name"))
            elif kind in ("BitmapAnd", "BitmapOr"):
                leaves.extend(bitmap_leaves(child))
            else:
                leaves.append(None)
        return leaves

    def walk(node) -> None:
        if not isinstance(node, dict):
            return
        kind = node.get("Node Type")
        if node.get("Relation Name") == relation:
            alias = node.get("Alias")
            if kind == "Bitmap Heap Scan":
                for index in bitmap_leaves(node) or [None]:
                    out.append({"node": kind, "index": index, "alias": alias})
            else:
                out.append({"node": kind, "index": node.get("Index Name"), "alias": alias})
        for child in node.get("Plans") or []:
            walk(child)

    walk(_root(plan))
    return out


#: The aliases Postgres gives `futures_markets` when the SQL does not alias it
#: (`futures_markets`, `futures_markets_1`, ...). #4914's anti-join scans the
#: table again under its OWN alias (`grp_sibling`), by group id, never by name;
#: that scan is recorded but is not the access SHAPE grades.
_ARM_ALIAS = re.compile(rf"^{RELATION}(_\d+)?$")


def graded_access(fp: list[dict]) -> list[dict]:
    """The accesses that can serve the arm's name predicate (alias absent counts)."""
    return [e for e in fp if e["alias"] is None or _ARM_ALIAS.match(e["alias"])]


def plan_skeleton(plan) -> list:
    """Node type, join type, relation, index and parent relationship, nested."""
    def sk(node):
        return [
            node.get("Node Type"), node.get("Join Type"), node.get("Relation Name"),
            node.get("Index Name"), node.get("Parent Relationship"),
            [sk(c) for c in node.get("Plans") or []],
        ]
    return sk(_root(plan))


def anti_join_methods(plan) -> list[str]:
    """How the plan executes a NOT EXISTS: anti-join nodes, or SubPlans."""
    found: list[str] = []

    def walk(node) -> None:
        if not isinstance(node, dict):
            return
        if (node.get("Join Type") or "").endswith("Anti"):
            found.append(f"{node.get('Node Type')} ({node['Join Type']})")
        elif node.get("Parent Relationship") == "SubPlan":
            found.append(f"SubPlan {node.get('Subplan Name')}")
        for child in node.get("Plans") or []:
            walk(child)

    walk(_root(plan))
    return found


def classify_catalog(rows) -> dict[str, dict]:
    """`pg_indexes` (indexname, indexdef) for futures_markets -> per-index class.

    trigram   : `gin_trgm_ops`/`gist_trgm_ops` in the definition.
    open_only : the partial predicate is EXACTLY `status = 'open'`. A partial with
                any other predicate is not counted as open-only (under-credit,
                never over-credit).
    """
    classes = {}
    for name, indexdef in rows:
        predicate = indexdef.split(" WHERE ", 1)[1] if " WHERE " in indexdef else ""
        classes[name] = {
            "trigram": "gin_trgm_ops" in indexdef or "gist_trgm_ops" in indexdef,
            "open_only": predicate.strip() == "((status)::text = 'open'::text)",
        }
    return classes


def _unclassified(fp: list[dict], classes: dict) -> list:
    return sorted(
        {repr(e["index"]) for e in fp if e["node"] != "Seq Scan" and e["index"] not in classes}
    )


def _indexes(fp: list[dict]) -> set[str]:
    return {e["index"] for e in fp if e["index"]}


# --------------------------------------------------------------------------
# Verdicts.
# --------------------------------------------------------------------------

def shape_verdict(a_fp, t_fp, classes: dict, was_subject: bool, t_problem: str | None = None):
    """(verdict, reason) for one term on one surface. `a_fp`/`t_fp` are the
    union over rounds of the ordinary and `no_trgm` plans; `t_fp` None means the
    control could not be read, with `t_problem` saying why."""
    if not was_subject:
        return PASS, "bystander: original rule (D1 not adopted)"
    a_idx = _indexes(a_fp)
    if FORBIDDEN_INDEX in a_idx:
        return FAIL, f"plan reads {FORBIDDEN_INDEX} (fails the original and the amended rule)"
    unknown = _unclassified(a_fp, classes)
    if unknown:
        return NOT_EVALUABLE, f"plan reads index(es) absent from the catalog snapshot: {unknown}"
    if EXPECTED_INDEX in a_idx:
        return PASS, f"original rule: reads {EXPECTED_INDEX}, not {FORBIDDEN_INDEX}"
    if t_fp is None:
        return NOT_EVALUABLE, f"original rule unmet and the no_trgm control is unavailable: {t_problem}"
    t_unknown = _unclassified(t_fp, classes)
    if t_unknown:
        return NOT_EVALUABLE, f"no_trgm control reads unclassified index(es): {t_unknown}"
    t_trigram = sorted(i for i in _indexes(t_fp) if classes[i]["trigram"])
    if t_trigram:
        return FAIL, f"no_trgm control still reads trigram index(es) {t_trigram}; original rule unmet"
    open_only = any(classes[i]["open_only"] for i in a_idx) and not any(
        e["node"] == "Seq Scan" for e in a_fp
    )
    if not open_only:
        return FAIL, "exception needs an open-only plan (an open partial, no Seq Scan); original rule unmet"
    return PASS_EXCEPTION, f"amended rule; {NO_CREDIT_NOTE}"


def combine(*verdicts: str) -> str:
    """Conjunction: FAIL beats NOT_EVALUABLE beats any pass."""
    if FAIL in verdicts:
        return FAIL
    if NOT_EVALUABLE in verdicts or not verdicts:
        return NOT_EVALUABLE
    return PASS_EXCEPTION if PASS_EXCEPTION in verdicts else PASS


def no_regression_verdict(ratio: float, before_ratio) -> str:
    """The original per-term rule; an absent before is NOT_EVALUABLE, not a pass."""
    if not before_ratio:
        return NOT_EVALUABLE
    return PASS if ratio <= before_ratio * PER_TERM_REGRESSION_FACTOR else FAIL


def load_retained(verify: bool = True) -> dict[str, dict]:
    records = {}
    for read, (path, sha) in RETAINED_READS.items():
        with open(path, "rb") as fh:
            blob = fh.read()
        if verify and hashlib.sha256(blob).hexdigest() != sha:
            raise ValueError(f"retained record {path} is not byte-identical to the 10/12 RED")
        records[read] = json.loads(blob)
    return records


def retained_failures(records: dict[str, dict]) -> list[dict]:
    """Every failure in the retained RED records, with its status under the
    amendment. NO-REGRESSION: OWED (term 4). SHAPE: OWED if the plan read the
    forbidden index (fails the amended rule too); otherwise the old EXPECTED
    requirement was all it failed, and a NEW read is needed under the amended
    rule (no same-instant no_trgm control was taken in these reads). SEMANTICS:
    a record without same-instant ids used the superseded cross-instant rule."""
    out = []
    for read in sorted(records):
        rec = records[read]
        for term, t in rec["terms"].items():
            idx = set(t["name_arm_indexes"])
            chosen = EXPECTED_INDEX in idx
            if not t["regression_ok"]:
                out.append({
                    "read": read, "term": term, "clause": "NO-REGRESSION", "chosen_plan": chosen,
                    "plan": sorted(idx), "status": OWED,
                    "why": "term 4: no harness observation clears a retained failure",
                })
            if not t["shape_ok"]:
                forbidden = FORBIDDEN_INDEX in idx
                out.append({
                    "read": read, "term": term, "clause": "SHAPE", "chosen_plan": chosen,
                    "plan": sorted(idx), "status": OWED if forbidden else SUPERSEDED_RULE,
                    "why": (
                        f"read {FORBIDDEN_INDEX}: fails the amended rule too" if forbidden
                        else "failed only the old EXPECTED requirement; the amended rule needs a new read"
                    ),
                })
        if not rec["semantics_ok"]:
            same_instant = "same_instant_ids" in rec
            out.append({
                "read": read, "term": None, "clause": "SEMANTICS", "chosen_plan": None, "plan": None,
                "status": OWED if same_instant else SUPERSEDED_RULE,
                "why": "same-instant rule failed" if same_instant
                else "cross-instant rule, superseded before the 01:15Z read",
            })
    return out


def owed(failures: list[dict]) -> list[dict]:
    return [f for f in failures if f["status"] == OWED]


def c4_word_verdict(rec: dict) -> tuple[str, str]:
    """One reader read. `rec` must come from `c4_read`: an arm timing from
    db-query has no `source == 'reader'` and is refused."""
    if rec.get("source") != "reader":
        return NOT_EVALUABLE, "not a reader read (arm timings are never reader evidence)"
    if rec.get("http_status") != 200:
        return NOT_EVALUABLE, f"http {rec.get('http_status')} {rec.get('error', '')}".strip()
    timing = rec.get("debug_timing") or {}
    shed = rec.get("debug_shed") or {}
    fq = timing.get("futures_query")
    oa = timing.get("futures_outcome_arm")
    if not isinstance(fq, (int, float)):
        return NOT_EVALUABLE, "no futures_query stage (timed out or absent)"
    if shed.get("outcome_arm_shed") or not isinstance(oa, (int, float)):
        return NOT_EVALUABLE, "no same-request futures_outcome_arm control (shed or absent)"
    fq_min = C4_BEFORE_MS["futures_query"][0]
    oa_min = C4_BEFORE_MS["futures_outcome_arm"][0]
    if not fq < fq_min:
        return FAIL, f"futures_query {fq} ms is not below the before's fastest {fq_min} ms"
    if not oa >= oa_min:
        return UNMATCHED, f"control {oa} ms is below the before's fastest {oa_min} ms (quieter database)"
    return PASS, f"futures_query {fq} < {fq_min} ms with control {oa} >= {oa_min} ms"


def c4_verdict(recs: list[dict]) -> tuple[str, dict]:
    per_word = {r.get("word"): c4_word_verdict(r) for r in recs}
    words = [r.get("word") for r in recs]
    if sorted(words) != sorted(C4_WORDS):
        return NOT_PAID, {"_set": (NOT_EVALUABLE, f"words {words} != {list(C4_WORDS)}"), **per_word}
    if all(v == PASS for v, _ in per_word.values()):
        return PAID, per_word
    return NOT_PAID, per_word


def track_verdict(clauses: dict[str, str], owed_list: list) -> str:
    ok = all(v in _PASSING for v in clauses.values()) and not owed_list
    return "GREEN" if ok else "RED"


# --------------------------------------------------------------------------
# I/O. Nothing below runs under --dry-run or in tests.
# --------------------------------------------------------------------------

PROTECTED = {
    os.path.realpath(G.BASELINE),
    os.path.realpath(os.path.join(AUDIT_DIR, "lat-p088-futures-open-trgm-after.json")),
    os.path.realpath(os.path.join(AUDIT_DIR, "lat-p088-futures-open-trgm-gate-after.json")),
    *(os.path.realpath(p) for p, _ in RETAINED_READS.values()),
}


def check_out_path(path: str | None) -> str | None:
    """None if `path` may be written; otherwise the refusal reason."""
    if not path:
        return "--out is required (the successor never picks a default path)"
    real = os.path.realpath(os.path.expanduser(path))
    if real in PROTECTED:
        return f"{path} is an immutable original record"
    if not os.path.basename(real).startswith("lat-10769-successor-"):
        return "the output name must start with lat-10769-successor-"
    if os.path.exists(real):
        return f"{path} exists; a record is never overwritten"
    return None


def _analyze(sql: str) -> dict | str:
    """One EXPLAIN ANALYZE, or the STRING reason it could not be read. A plan the
    endpoint truncated (`plan: null`) is unread, never an empty fingerprint."""
    try:
        payload = G._post(sql, analyze=True, fatal=False)
    except G.DbQueryFailed as exc:
        return f"UNREAD:{exc.reason}"
    if payload.get("plan") is None or payload.get("truncated"):
        return f"UNREAD:plan_{payload.get('truncation_reason') or 'absent'}"
    return payload


def _plan_summary(payload: dict) -> dict:
    blob = json.dumps(payload.get("plan"))
    timing = {
        key: float(m.group(1))
        for key in ("Execution Time", "Planning Time")
        if (m := re.search(rf'"{key}":\s*([0-9.]+)', blob))
    }
    return {
        "exec_ms": timing.get("Execution Time"),
        "planning_ms": timing.get("Planning Time"),
        "access": access_fingerprint(payload),
        "skeleton": plan_skeleton(payload),
        "anti_join": anti_join_methods(payload),
    }


def _digest(sql: str) -> list | str:
    try:
        payload = G._post(set_digest_sql(sql), analyze=False, fatal=False)
    except G.DbQueryFailed as exc:
        return f"UNREAD:{exc.reason}"
    rows = payload.get("rows") or []
    return [int(rows[0][0]), rows[0][1]] if rows else "UNREAD:no_row"


def _arm_reads(sql: str, rounds: int, faithful: bool) -> dict:
    """Ordinary + no_trgm plans, interleaved per round, plus the set digests."""
    try:
        t_sql = rewrite(sql, "no_trgm")
        t_problem = None
    except VariantUnavailable as exc:
        t_sql, t_problem = None, str(exc)
    a_reads, t_reads = [], []
    for _ in range(rounds):
        a = _analyze(sql)
        a_reads.append(a if isinstance(a, str) else _plan_summary(a))
        if t_sql:
            t = _analyze(t_sql)
            t_reads.append(t if isinstance(t, str) else _plan_summary(t))
    digests = {"usable": _digest(sql)}
    for variant in VARIANTS:
        try:
            digests[variant] = _digest(rewrite(sql, variant))
        except VariantUnavailable as exc:
            digests[variant] = f"UNAVAILABLE:{exc}"
    return {"a": a_reads, "t": t_reads, "t_problem": t_problem, "digests": digests,
            "faithful_required": faithful}


def _union_fp(reads: list) -> list | None:
    if not reads or any(isinstance(r, str) for r in reads):
        return None
    seen, out = set(), []
    for r in reads:
        for e in graded_access(r["access"]):
            key = (e["node"], e["index"], e["alias"])
            if key not in seen:
                seen.add(key)
                out.append(e)
    return out


def arm_shape(reads: dict, classes: dict, was_subject: bool) -> tuple[str, str]:
    a_fp = _union_fp(reads["a"])
    if a_fp is None:
        return NOT_EVALUABLE, f"ordinary plan unread: {[r for r in reads['a'] if isinstance(r, str)]}"
    if reads["faithful_required"] and not all(r["anti_join"] for r in reads["a"]):
        return NOT_EVALUABLE, "a faithful read whose plan has no anti-join/SubPlan for #4914"
    t_fp = _union_fp(reads["t"])
    problem = reads["t_problem"] or (None if t_fp is not None else "no_trgm plan unread")
    return shape_verdict(a_fp, t_fp, classes, was_subject, problem)


def _catalog() -> tuple[dict, list]:
    payload = G._post(
        "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' "
        "AND tablename = 'futures_markets' ORDER BY indexname",
        analyze=False,
    )
    rows = [(r[0], r[1]) for r in payload.get("rows") or []]
    if not rows:
        print("ERROR: empty catalog snapshot -- cannot classify any index", file=sys.stderr)
        sys.exit(2)
    validity = G._post(
        "SELECT c.relname, i.indisvalid, i.indisready FROM pg_index i "
        f"JOIN pg_class c ON c.oid = i.indexrelid WHERE c.relname = '{EXPECTED_INDEX}'",
        analyze=False,
    ).get("rows") or []
    return classify_catalog(rows), validity


def c4_read(word: str) -> dict:
    url = f"{API}/api/events/typeahead?" + urllib.parse.urlencode({"q": word, "debug_timing": 1})
    rec: dict = {"source": "reader", "word": word, "read_at": datetime.now(timezone.utc).isoformat()}
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=tagged(API, {})), timeout=C4_TIMEOUT_S
        ) as response:
            body = json.loads(response.read())
            rec["http_status"] = response.status
    except urllib.error.HTTPError as exc:
        rec["http_status"], rec["error"] = exc.code, exc.read().decode(errors="replace")[:200]
        return rec
    except (urllib.error.URLError, TimeoutError) as exc:
        rec["http_status"], rec["error"] = None, str(exc)[:200]
        return rec
    for key in ("debug_timing", "debug_shed", "debug_plan"):
        rec[key] = body.get(key)
    return rec


def run_se(rounds: int, classes: dict, record: dict) -> dict[str, str]:
    """Two passes, in the original gate's sequence. Pass 1 is NO-REGRESSION's
    timing: all 8 terms back to back, in TERMS order, name/outcome interleaved per
    round, exactly as the original `main()` times them, with no other statement
    between one term's rounds and the next. Only then pass 2: the SHAPE controls,
    the faithful arm and the semantics reads (~21 statements per term, some with
    an index disabled), which would otherwise land between terms the 10/08
    before timed consecutively."""
    with open(G.BASELINE) as fh:
        baseline = json.load(fh)
    clauses: dict[str, str] = {}
    timed: dict[str, dict] = {}
    # Pass 1 -- NO-REGRESSION: the original procedure, byte for byte (fatal posts).
    for term in TERMS:
        name_sql, ctrl_sql = G._sql_for(term, "name"), G._sql_for(term, "outcome")
        name_ms, ctrl_ms, g0_a = [], [], []
        for _ in range(rounds):
            p_name = G._post(name_sql, analyze=True)
            name_ms.append(G._exec_ms(p_name))
            g0_a.append(_plan_summary(p_name))
            ctrl_ms.append(G._exec_ms(G._post(ctrl_sql, analyze=True)))
        timed[term] = {"name_sql": name_sql, "name_ms": name_ms, "ctrl_ms": ctrl_ms, "g0_a": g0_a}
    record["sequence"] = "pass 1: timed rounds, all terms in TERMS order; pass 2: SHAPE/faithful/semantics"
    # Pass 2 -- SHAPE on G0 and on the faithful arm, then the semantics reads.
    g0_ids = {}
    faithful_digests = {}
    for term in TERMS:
        base = (baseline.get("terms") or {}).get(term) or {}
        was_subject = FORBIDDEN_INDEX in (base.get("name_arm_indexes") or [])
        t1 = timed[term]
        name_ms, ctrl_ms = t1["name_ms"], t1["ctrl_ms"]
        c_med = statistics.median(ctrl_ms)
        ratio = statistics.median(name_ms) / c_med if c_med else float("inf")
        noreg = no_regression_verdict(ratio, base.get("ratio"))
        try:
            g0_t_sql, g0_t_problem = rewrite(t1["name_sql"], "no_trgm"), None
        except VariantUnavailable as exc:
            g0_t_sql, g0_t_problem = None, str(exc)
        g0_t = []
        for _ in range(rounds if g0_t_sql else 0):
            t = _analyze(g0_t_sql)
            g0_t.append(t if isinstance(t, str) else _plan_summary(t))
        g0_reads = {"a": t1["g0_a"], "t": g0_t, "t_problem": g0_t_problem, "faithful_required": False}
        shape_g0 = arm_shape(g0_reads, classes, was_subject)
        member = compile_sql(search_name_member(term, datetime.now(timezone.utc)))
        faithful = _arm_reads(member, rounds, faithful=True)
        shape_f = arm_shape(faithful, classes, was_subject)
        shape = combine(shape_g0[0], shape_f[0])
        g0_ids[term] = G.same_instant_ids(term)
        faithful_digests[term] = faithful["digests"]
        record["terms"][term] = {
            "was_subject": was_subject, "name_ms": name_ms, "ctrl_ms": ctrl_ms,
            "ratio": ratio, "before_ratio": base.get("ratio"), "no_regression": noreg,
            "shape": shape, "shape_g0": shape_g0, "shape_faithful": shape_f,
            "g0_reads": g0_reads, "faithful_reads": faithful,
        }
        clauses[f"SHAPE:{term}"] = shape
        clauses[f"NO-REGRESSION:{term}"] = noreg
        print(f"  {term:<22} shape={shape:<14} noregr={noreg:<13} ratio={ratio:.3f} "
              f"before={base.get('ratio')}")
    sem_g0 = G.semantics_verdict(g0_ids, baseline.get("ids") or {})
    sem_f = G.semantics_verdict(faithful_digests, {})
    record["same_instant_ids_g0"] = g0_ids
    record["semantics_g0"], record["semantics_faithful"] = sem_g0, sem_f
    clauses["SEMANTICS:g0"] = PASS if sem_g0[0] else FAIL
    clauses["SEMANTICS:faithful"] = PASS if sem_f[0] else FAIL
    record["budget"] = {"verdict": WITHDRAWN, "statement": SE_BUDGET_STATEMENT}
    return clauses


def run_ta(rounds: int, classes: dict, record: dict) -> dict[str, str]:
    clauses: dict[str, str] = {}
    digests = {}
    for term in TERMS:
        member = compile_sql(typeahead_ilike_member(term, datetime.now(timezone.utc)))
        reads = _arm_reads(member, rounds, faithful=True)
        shape = arm_shape(reads, classes, was_subject=True)
        digests[term] = reads["digests"]
        record["terms"][term] = {"shape": shape, "reads": reads, "was_subject": True,
                                 "subject_basis": "no typeahead before exists; graded as a subject"}
        clauses[f"SHAPE:{term}"] = shape[0]
        print(f"  {term:<22} shape={shape[0]:<14} {shape[1]}")
    sem = G.semantics_verdict(digests, {})
    record["semantics"] = sem
    clauses["SEMANTICS"] = PASS if sem[0] else FAIL
    record["not_graded_here"] = (
        "typeahead NO-REGRESSION/BUDGET: no faithful typeahead-arm before exists and making one needs DDL; "
        "typeahead speed is C4 (--track c4)"
    )
    return clauses


def rewrite_problems(members: dict[str, str]) -> dict[str, str]:
    """{member|variant: reason} for every rewrite that cannot be built. During a
    read an unbuildable variant is excluded like an unread one; before a read it
    is refused, so route drift stops the read instead of thinning it."""
    bad = {}
    for key, sql in members.items():
        for variant in VARIANTS:
            try:
                rewrite(sql, variant)
            except VariantUnavailable as exc:
                bad[f"{key}|{variant}"] = str(exc)
    return bad


def dry_run(track: str) -> int:
    print(f"gate_10769_successor --track {track} --dry-run (no request is made)")
    if track == "se":
        bad = g0_identity()
        print(f"  original SQL identity: {'OK 24/24' if not bad else bad}")
        if bad:
            return 2
    load_retained()
    print("  retained RED records: byte-identical (2/2)")
    now = datetime.now(timezone.utc)
    if track == "se":
        members = {f"faithful|{t}": compile_sql(search_name_member(t, now)) for t in TERMS}
        members.update({f"g0|{t}": G._sql_for(t, "name") for t in TERMS})
        n = len(TERMS) * (5 * ROUNDS + 6) + 2
    elif track == "ta":
        members = {f"ta|{t}": compile_sql(typeahead_ilike_member(t, now)) for t in TERMS}
        n = len(TERMS) * (2 * ROUNDS + 3) + 2
    else:
        members = {}
        n = len(C4_WORDS)
    unbuildable = rewrite_problems(members)
    if unbuildable:
        print(f"  ERROR: a same-instant control cannot be built (route drift?): {unbuildable}")
        return 2
    if members:
        print(f"  both rewrites build on all {len(members)} statements")
    print(f"  statements compiled; a read would make {n} requests")
    print(f"  owed retained failures: {len(owed(retained_failures(load_retained())))}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="#10769 successor gate (approved 2026-10-25 amendment)")
    ap.add_argument("--track", choices=("se", "ta", "c4"))
    ap.add_argument("--rounds", type=int, default=ROUNDS)
    ap.add_argument("--out")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--criteria", action="store_true", help="print old/new criteria and exit")
    args = ap.parse_args()

    if args.criteria:
        print(json.dumps(CRITERIA, indent=2))
        return 0
    if not args.track:
        ap.error("--track is required")
    if args.dry_run:
        return dry_run(args.track)
    refusal = check_out_path(args.out)
    if refusal:
        print(f"ERROR: {refusal}", file=sys.stderr)
        return 2
    if args.rounds != ROUNDS and args.track == "se":
        print(f"ERROR: /search NO-REGRESSION is the original procedure (rounds={ROUNDS})", file=sys.stderr)
        return 2

    failures = retained_failures(load_retained())
    record: dict = {
        "track": args.track, "rounds": args.rounds, "criteria": CRITERIA,
        "started_at": datetime.now(timezone.utc).isoformat(), "terms": {},
        "retained_failures": failures,
        "arm_plan_mode": "custom plan of literal SQL via db-query; NOT the reader's prepared statement",
    }
    if args.track == "c4":
        recs = [c4_read(word) for word in C4_WORDS]
        verdict, per_word = c4_verdict(recs)
        record.update({"reads": recs, "per_word": per_word, "c4": verdict,
                       "before": C4_BEFORE_MS, "before_source": C4_BEFORE_SOURCE})
        record["verdict"] = "GREEN" if verdict == PAID else "RED"
        for word, (v, why) in per_word.items():
            print(f"  {word:<10} {v:<14} {why}")
    else:
        bad = g0_identity() if args.track == "se" else {}
        if bad:
            print(f"ERROR: original SQL changed, refusing to compare it with the baseline: {bad}",
                  file=sys.stderr)
            return 2
        classes, validity = _catalog()
        record["catalog"], record["c1_precondition"] = classes, validity
        if not (validity and validity[0][1] and validity[0][2]):
            record["verdict"] = "RED"
            record["note"] = f"C1 precondition failed: {EXPECTED_INDEX} not valid+ready ({validity})"
        else:
            run = run_se if args.track == "se" else run_ta
            clauses = run(args.rounds, classes, record)
            owed_list = owed(failures) if args.track == "se" else []
            record["clauses"], record["owed"] = clauses, owed_list
            record["verdict"] = track_verdict(clauses, owed_list)
            if owed_list:
                print(f"  OWED retained failures: {len(owed_list)} (term 4) -- this track cannot be GREEN")
    out = os.path.realpath(os.path.expanduser(args.out))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "x") as fh:
        json.dump(record, fh, indent=2, default=str)
    print(f"VERDICT: {record['verdict']}   (written to {out})")
    return 0 if record["verdict"] == "GREEN" else 1


if __name__ == "__main__":
    sys.exit(main())
