"""#10305 D2 — the participant fill's pure verdict, receipt, and restore proof.

SYN = synthetic ESPN ids and team rows throughout. Nothing here claims anything
about the specimen (row 15322561 / ESPN 401918296): its real team ids, homeAway
and team inventory are unpaid specimen gates (plan §6).

The real-Postgres half — the write, its fences, concurrency, the rollback
contract through the real caller, restore and the re-fill discriminator — is
``tests/integration/test_espn_participant_fill_pg.py``.
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.espn_api import ESPNEvent, ESPNTeam  # noqa: E402
from app.utils import espn_helpers  # noqa: E402
from app.utils import espn_participant_fill as fill  # noqa: E402
from app.utils.espn_participant_fill import (  # noqa: E402
    CONFLICT,
    FILL,
    FILL_TAG_PREFIX,
    REFUSE,
    RESTORED_TAG_PREFIX,
    ReceiptInvalid,
    build_team_index,
    encode_fill_tag,
    maybe_fill_participants,
    parse_fill_tag,
    participant_fill_verdict,
)
from scripts import restore_espn_participant_fill as restore  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]

SPORT, OTHER_SPORT = 70, 71
EVENT_ID = 990561
ESPN_EVENT = "990401"
HOME_TID, AWAY_TID = "990001", "990002"  # SYN: home Valkyries, away Aces
HOME_PK, AWAY_PK = 501, 502


def _espn_team(tid, display, short):
    return ESPNTeam(
        espn_id=tid,
        name=short,
        abbreviation=None,
        display_name=display,
        short_name=short,
        nickname=None,
        primary_color=None,
        secondary_color=None,
        logo_url=None,
        logo_url_dark=None,
        record=None,
        location=display[: -len(short)].strip() or None,
    )


VALK = _espn_team(HOME_TID, "Golden State Valkyries", "Valkyries")
ACES = _espn_team(AWAY_TID, "Las Vegas Aces", "Aces")


def _ee(sides=((HOME_TID, "home"), (AWAY_TID, "away")), home=VALK, away=ACES, espn_id=ESPN_EVENT):
    return ESPNEvent(
        espn_id=espn_id,
        name="Las Vegas Aces at Golden State Valkyries",
        short_name=None,
        date=datetime(2031, 10, 4, 20, 0, tzinfo=timezone.utc),
        status="scheduled",
        status_detail=None,
        period=None,
        clock=None,
        home_team=home,
        away_team=away,
        home_score=None,
        away_score=None,
        venue=None,
        broadcasts=[],
        home_win_probability=None,
        competitor_sides=sides,
    )


def _event(**over):
    base = dict(
        id=EVENT_ID,
        espn_id=ESPN_EVENT,
        status="scheduled",
        sport_id=SPORT,
        home_team_name="TBD",
        away_team_name="TBD",
        home_team_id=None,
        away_team_id=None,
        home_team_normalized=None,
        away_team_normalized=None,
        home_team_alt_names=None,
        away_team_alt_names=None,
        event_tags=[],
    )
    base.update(over)
    return SimpleNamespace(**base)


def _team(pk, name, tid, sport=SPORT, alts=None):
    return SimpleNamespace(id=pk, name=name, sport_id=sport, espn_id=tid, alternate_names=alts)


def _index(*extra):
    return build_team_index(
        [
            _team(HOME_PK, "Golden State Valkyries", HOME_TID),
            _team(AWAY_PK, "Las Vegas Aces", AWAY_TID),
            *extra,
        ]
    )


def _receipt(**over):
    r = {
        "after": {"away_name": "Las Vegas Aces", "away_tid": AWAY_PK,
                  "home_name": "Golden State Valkyries", "home_tid": HOME_PK},
        "filled_at": "2031-10-03T14:50:00Z",
        "prior": {"away_name": "TBD", "away_norm": None, "home_name": "TBD", "home_norm": None},
    }
    for key, value in over.items():
        section, _, leaf = key.partition("__")
        if leaf:
            r[section][leaf] = value
        else:
            r[section] = value
    return r


def _tag(receipt=None, away=AWAY_TID, home=HOME_TID):
    return encode_fill_tag(ESPN_EVENT, away, home, receipt or _receipt())


def _verdict(event=None, ee=None, index=None):
    return participant_fill_verdict(event or _event(), ee or _ee(), _index() if index is None else index)


@pytest.fixture(autouse=True)
def _empty_denylist(monkeypatch):
    monkeypatch.setattr(fill, "RESTORED_FILL_EVENT_IDS", frozenset())


# ── Admit ────────────────────────────────────────────────────────────────────


def test_a1_admits_an_own_id_placeholder_row_onto_the_two_id_anchored_teams():
    v = _verdict()
    assert (v.action, v.reason) == (FILL, "fill")
    assert v.home_team.name == "Golden State Valkyries" and v.away_team.name == "Las Vegas Aces"
    assert (v.home_espn_tid, v.away_espn_tid) == (HOME_TID, AWAY_TID)
    assert v.summary_arm == "not_exercised"


def test_a2_follows_espns_literal_sides_when_the_payload_reverses_them():
    v = _verdict(ee=_ee(sides=((AWAY_TID, "home"), (HOME_TID, "away")), home=ACES, away=VALK))
    assert v.action == FILL
    assert v.home_team.name == "Las Vegas Aces" and v.away_team.name == "Golden State Valkyries"
    assert (v.home_espn_tid, v.away_espn_tid) == (AWAY_TID, HOME_TID)


# ── Refusals and routes ──────────────────────────────────────────────────────


@pytest.mark.parametrize("espn_id", [None, "", "990499"])
def test_r1_a_name_matched_row_is_not_attempted(espn_id):
    assert _verdict(event=_event(espn_id=espn_id)).reason == "not_id_anchored"


@pytest.mark.parametrize(
    "sides, reason",
    [
        ((), "no_side_evidence"),  # R2: the carrier default
        (((HOME_TID, "home"),), "side_count"),  # R3
        (((HOME_TID, "home"), (AWAY_TID, "away"), ("990003", "away")), "side_count"),  # R4
        (((HOME_TID, "home"), (AWAY_TID, None)), "side_invalid"),  # R5: the parser's else arm
        (((HOME_TID, "home"), (AWAY_TID, "home")), "side_duplicate"),  # R6
        (((HOME_TID, "home"), (AWAY_TID, "neutral")), "side_invalid"),  # R7
        (((HOME_TID, "home"), (HOME_TID, "away")), "side_duplicate_team"),  # R9
        (((HOME_TID, "home"), ("", "away")), "side_placeholder"),  # R10
    ],
)
def test_r2_to_r10_side_evidence_refusals(sides, reason):
    v = _verdict(ee=_ee(sides=sides))
    assert (v.action, v.reason) == (REFUSE, reason)


def test_r8_a_parsed_slot_that_disagrees_with_the_literal_side_routes_to_authority():
    v = _verdict(ee=_ee(home=ACES, away=VALK))
    assert (v.action, v.reason) == (CONFLICT, "payload_self_disagreement")


def test_r11_an_espn_competitor_named_tbd_refuses():
    tbd = _espn_team(AWAY_TID, "TBD", "TBD")
    assert _verdict(ee=_ee(away=tbd)).reason == "side_placeholder"


def test_a_missing_parsed_slot_refuses():
    assert _verdict(ee=_ee(home=None)).reason == "parsed_slot_missing"


def test_a_team_row_named_tbd_is_never_written():
    index = build_team_index([
        _team(HOME_PK, "TBD", HOME_TID, alts=["Golden State Valkyries"]),
        _team(AWAY_PK, "Las Vegas Aces", AWAY_TID),
    ])
    assert _verdict(index=index).reason == "team_name_placeholder"


def test_the_binding_invariant_is_consulted_as_defence_in_depth(monkeypatch):
    monkeypatch.setattr(fill, "binding_is_sound", lambda *a: False)
    assert _verdict().reason == "binding_unsound"


def test_two_ids_resolving_to_one_team_row_refuse():
    valk = _team(HOME_PK, "Golden State Valkyries", HOME_TID, alts=["Las Vegas Aces"])
    assert _verdict(index={HOME_TID: [valk], AWAY_TID: [valk]}).reason == "side_duplicate_team"


def test_r12_a_team_row_only_in_another_sport_refuses_and_mints_nothing():
    index = build_team_index([
        _team(HOME_PK, "Golden State Valkyries", HOME_TID),
        _team(AWAY_PK, "Las Vegas Aces", AWAY_TID, sport=OTHER_SPORT),
    ])
    assert _verdict(index=index).reason == "no_team_row"


def test_r13_two_rows_carrying_one_espn_id_in_the_sport_refuse():
    v = _verdict(index=_index(_team(503, "Las Vegas Aces", AWAY_TID)))
    assert v.reason == "ambiguous_team_row"


def test_r14_a_row_whose_identity_does_not_correspond_refuses():
    index = build_team_index([
        _team(HOME_PK, "Golden State Valkyries", HOME_TID),
        _team(AWAY_PK, "Seattle Storm", AWAY_TID),
    ])
    assert _verdict(index=index).reason == "identity_mismatch"


def test_r15_one_real_name_with_an_aligned_payload_is_a_plain_refusal(monkeypatch):
    monkeypatch.setattr(espn_helpers, "espn_orientation_verdict", lambda e, ee: "aligned")
    v = _verdict(event=_event(home_team_name="Golden State Valkyries"))
    assert (v.action, v.reason) == (REFUSE, "not_both_placeholder")


def test_r16_one_real_name_with_a_swapped_payload_routes_to_authority(monkeypatch):
    monkeypatch.setattr(espn_helpers, "espn_orientation_verdict", lambda e, ee: "swapped")
    v = _verdict(event=_event(home_team_name="Las Vegas Aces"))
    assert (v.action, v.reason) == (CONFLICT, "occupied_side_swapped")


def test_r16b_two_readable_names_espn_cannot_orient_route_to_authority():
    v = _verdict(event=_event(home_team_name="Seattle Storm", away_team_name="Dallas Wings"))
    assert (v.action, v.reason) == (CONFLICT, "occupied_side_unresolved")


def test_r17_an_occupied_fk_refuses_and_routes_when_it_names_the_other_side():
    assert _verdict(event=_event(home_team_id=777)).reason == "fk_occupied"
    v = _verdict(event=_event(home_team_id=AWAY_PK))
    assert (v.action, v.reason) == (CONFLICT, "fk_opposite_side")


@pytest.mark.parametrize(
    "over, reason",
    [
        (dict(home_team_normalized="Golden State Valkyries"), "stale_normalized"),  # R18
        (dict(away_team_alt_names=["Aces"]), "alt_names_present"),  # R19
        (dict(status="live"), "not_scheduled"),  # R22
    ],
)
def test_r18_r19_r22_row_state_refusals(over, reason):
    assert _verdict(event=_event(**over)).reason == reason


def test_r18_a_placeholder_normalized_value_is_not_stale():
    assert _verdict(event=_event(home_team_normalized="tbd", away_team_normalized=" TBA ")).action == FILL


@pytest.mark.parametrize(
    "prefix, plain",
    [(FILL_TAG_PREFIX, "prior_fill_present"), (RESTORED_TAG_PREFIX, "restored_fill_present")],
)
def test_r20_r21_r23_r24_a_prior_fill_or_marker_refuses_and_other_ids_route(prefix, plain):
    same = prefix + _tag()[len(FILL_TAG_PREFIX):]
    other = prefix + _tag(away="990009")[len(FILL_TAG_PREFIX):]
    assert _verdict(event=_event(event_tags=["x", same])).reason == plain  # R21 / R23
    v = _verdict(event=_event(event_tags=[other]))  # R20 / R24
    assert (v.action, v.reason) == (CONFLICT, f"{plain}_other_teams")


# ── R25: the code denylist is checked first ──────────────────────────────────


class _OnlyId:
    """A row that answers ``id`` and records every other read."""

    def __init__(self):
        self.reads = []

    def __getattr__(self, name):
        self.__dict__.setdefault("reads", []).append(name)
        return getattr(_event(), name)

    id = EVENT_ID


def test_r25a_a_listed_id_refuses_before_any_other_check(monkeypatch):
    monkeypatch.setattr(fill, "RESTORED_FILL_EVENT_IDS", frozenset({EVENT_ID}))
    row = _OnlyId()
    v = participant_fill_verdict(row, _ee(), _index())
    assert (v.action, v.reason) == (REFUSE, "restore_denylisted")
    assert row.reads == []


def test_r25b_another_listed_id_does_not_refuse_this_row(monkeypatch):
    monkeypatch.setattr(fill, "RESTORED_FILL_EVENT_IDS", frozenset({EVENT_ID + 1}))
    assert _verdict().action == FILL


def test_r25c_the_post_restore_tag_states_refuse_on_their_own():
    marker = RESTORED_TAG_PREFIX + _tag()[len(FILL_TAG_PREFIX):]
    assert _verdict(event=_event(event_tags=[marker])).reason == "restored_fill_present"
    assert _verdict(event=_event(event_tags=[_tag()])).reason == "prior_fill_present"


def _function_body(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    body = fn.body
    if isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
        body = body[1:]
    return body


def test_r25d_the_shipped_denylist_is_a_frozenset_of_int_checked_first(monkeypatch):
    monkeypatch.undo()  # read what ships, not the autouse fixture's patch
    shipped = fill.RESTORED_FILL_EVENT_IDS
    assert isinstance(shipped, frozenset)
    assert all(isinstance(i, int) and not isinstance(i, bool) for i in shipped)
    first = _function_body(BACKEND / "app/utils/espn_participant_fill.py", "participant_fill_verdict")[0]
    assert isinstance(first, ast.If)
    assert ast.unparse(first.test) == "event.id in RESTORED_FILL_EVENT_IDS"
    assert "restore_denylisted" in ast.unparse(first.body[0])


# ── The helper's pure path (no database) ─────────────────────────────────────


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _SpySession:
    def __init__(self):
        self.calls = []

    async def flush(self):
        self.calls.append("flush")

    async def execute(self, stmt, params=None):
        self.calls.append(("execute", params))
        return _Result([])

    def begin_nested(self):
        spy = self

        class _Nested:
            async def __aenter__(self):
                spy.calls.append("savepoint")

            async def __aexit__(self, *exc):
                return False

        return _Nested()

    async def refresh(self, *a, **k):
        self.calls.append("refresh")


async def test_a1_the_tag_written_is_oriented_and_a_complete_receipt(monkeypatch):
    monkeypatch.setattr(fill, "_utcnow", lambda: datetime(2031, 10, 3, 14, 50, 7, tzinfo=timezone.utc))
    session, stats = _SpySession(), {}
    event = _event(home_team_name=" TBA ", home_team_normalized="tbd")
    assert await maybe_fill_participants(session, event, _ee(), _index(), stats) is False
    assert stats["participant_fill"] == {"fence_lost": 1}  # the spy returns no row
    params = next(c[1] for c in session.calls if isinstance(c, tuple))
    (tag,) = json.loads(params["tag_array"])
    assert tag.startswith(f"{FILL_TAG_PREFIX}{ESPN_EVENT}:away={AWAY_TID}:home={HOME_TID}:r1=")
    r = parse_fill_tag(tag)
    assert (r.prior_home_name, r.prior_home_norm, r.prior_away_name) == (" TBA ", "tbd", "TBD")
    assert (r.after_home_tid, r.after_away_tid) == (HOME_PK, AWAY_PK)
    assert r.filled_at == "2031-10-03T14:50:07Z"
    assert session.calls[0] == "flush" and session.calls[1] == "savepoint"


async def test_a_refusal_issues_no_flush_and_no_statement():
    session, stats = _SpySession(), {}
    assert await maybe_fill_participants(session, _event(status="live"), _ee(), _index(), stats) is False
    assert session.calls == []
    assert stats["participant_fill"] == {"refused_not_scheduled": 1}


async def test_e3_a_verdict_exception_is_counted_and_touches_nothing():
    class _Boom:
        def __getattr__(self, name):
            raise RuntimeError("boom")

    session, stats = _SpySession(), {}
    index = {HOME_TID: [_Boom()], AWAY_TID: [_Boom()]}
    assert await maybe_fill_participants(session, _event(), _ee(), index, stats) is False
    assert stats["participant_fill"] == {"verdict_error": 1}
    assert session.calls == []


# ── E1 / E2: the receipt ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "prior",
    [
        {"away_name": "TBD", "away_norm": None, "home_name": "TBD", "home_norm": None},
        {"away_name": "To Be Announced", "away_norm": None, "home_name": " TBA ", "home_norm": "tbd"},
    ],
)
@pytest.mark.parametrize(
    "after_name", ["Golden State Valkyries", "Club: A%B \"quoted\"", "Atlético de São Paulo"]
)
def test_e1_the_receipt_round_trips_exact_bytes(prior, after_name):
    receipt = _receipt(prior=prior, after__home_name=after_name)
    r = parse_fill_tag(_tag(receipt))
    assert (r.prior_home_name, r.prior_away_name) == (prior["home_name"], prior["away_name"])
    assert (r.prior_home_norm, r.prior_away_norm) == (prior["home_norm"], prior["away_norm"])
    assert r.after_home_name == after_name
    assert (r.espn_event_id, r.away_espn_tid, r.home_espn_tid) == (ESPN_EVENT, AWAY_TID, HOME_TID)


def test_e2_a_non_string_tag_refuses():
    with pytest.raises(ReceiptInvalid) as exc:
        parse_fill_tag(None)
    assert exc.value.reason == "receipt_invalid:not_a_string"


def _pct(tag):
    return tag.rsplit(":r1=", 1)[1]


def _replace_pct(tag, pct):
    return tag.rsplit(":r1=", 1)[0] + ":r1=" + pct


def _raw(receipt):
    return quote(json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False), safe="")


@pytest.mark.parametrize(
    "mutate, reason",
    [
        (lambda t: t.rsplit(":r1=", 1)[0], "r1"),
        (lambda t: _tag(_receipt(filled_at="2031-10-03 14:50:00")), "filled_at"),
        (lambda t: _tag(_receipt(filled_at="2031-13-03T14:50:00Z")), "filled_at"),
        (lambda t: t[:-6], None),  # truncated: json or percent, never admitted
        (lambda t: _replace_pct(t, _pct(t) + "%zz"), "percent"),
        (lambda t: _replace_pct(t, "%7Bnot-json"), "json"),
        (lambda t: _replace_pct(t, _raw({k: v for k, v in _receipt().items() if k != "prior"})), "keys"),
        (lambda t: _replace_pct(t, _raw({**_receipt(), "extra": 1})), "keys"),
        (lambda t: _tag(_receipt(after__home_tid=str(HOME_PK))), "types"),
        (lambda t: _tag(_receipt(after__home_tid=True)), "types"),
        (lambda t: _tag(_receipt(prior__home_name="Seattle Storm")), "prior_name"),
        (lambda t: _tag(_receipt(prior__home_norm="Storm")), "prior_norm"),
        (lambda t: _tag(_receipt(after__home_name="TBD")), "after_name"),
        (lambda t: _tag(_receipt(after__away_tid=HOME_PK)), "after_tids"),
        (lambda t: _replace_pct(t, quote(json.dumps(_receipt()), safe="")), "non_canonical"),
        (lambda t: _replace_pct(t, re.sub(r"%[0-9A-F]{2}", lambda m: m.group(0).lower(), _pct(t))),
         "non_canonical"),
        (lambda t: t.replace(f"away={AWAY_TID}", f"away={HOME_TID}"), "same_ids"),
        (lambda t: t.replace(f"home={HOME_TID}", "home="), "home"),
        (lambda t: t.replace(f"{ESPN_EVENT}:", ":", 1), "espn_event_id"),
        (lambda t: RESTORED_TAG_PREFIX + t[len(FILL_TAG_PREFIX):], "prefix"),
        (lambda t: t.replace(f"away={AWAY_TID}", f"a={AWAY_TID}"), "away"),
        (lambda t: t.replace(":r1=", ":r2="), "r1"),
        (lambda t: _replace_pct(t, ""), "r1"),
        (lambda t: _replace_pct(t, _pct(t) + "%FF"), "percent"),  # not UTF-8
        (lambda t: _tag(_receipt(after={"away_name": "Las Vegas Aces", "away_tid": AWAY_PK,
                                         "home_name": "Golden State Valkyries"})), "keys"),
        (lambda t: _tag(_receipt(filled_at="2031-1-03T14:50:00Z")), "filled_at"),
    ],
)
def test_e2_every_incomplete_or_non_canonical_receipt_refuses(mutate, reason):
    with pytest.raises(ReceiptInvalid) as exc:
        parse_fill_tag(mutate(_tag()))
    assert exc.value.reason.startswith("receipt_invalid:")
    if reason is not None:
        assert exc.value.reason == f"receipt_invalid:{reason}"


# ── RP: the retirement / carrying proof ──────────────────────────────────────

LOCK = datetime(2031, 10, 3, 15, 0, 0, tzinfo=timezone.utc)
NEW_COMMIT, OLD_COMMIT, DENY_COMMIT = "b" * 40, "c" * 40, "a" * 40
NEW_VERSION, OLD_VERSION = 5500, 5499
ENV = {
    "HEROKU_APP_NAME": "bainluck",
    "HEROKU_RELEASE_VERSION": f"v{NEW_VERSION}"[1:],
    "HEROKU_SLUG_COMMIT": NEW_COMMIT,
    "HEROKU_RELEASE_CREATED_AT": (LOCK - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
}


def _ts(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _inst(dyno="worker-realtime.1", type_="worker-realtime", version=NEW_VERSION, commit=NEW_COMMIT,
          carries=True, state="up", exited_at=None, evidence=None):
    return {
        "dyno": dyno, "type": type_, "release_version": version, "release_commit": commit,
        "carries_id": carries, "state_at_capture": state,
        "exited_at": _ts(exited_at) if exited_at else None,
        "exit_evidence": evidence,
        "evidence_line": f"{dyno}: Process exited with status 0" if state == "exited" else None,
    }


def _old_exited(at=LOCK - timedelta(seconds=60), evidence="exit"):
    return _inst(version=OLD_VERSION, commit=OLD_COMMIT, carries=False, state="exited",
                 exited_at=at, evidence=evidence)


def _app(name, instances, formation, captured=LOCK - timedelta(seconds=30), window=600,
         version=NEW_VERSION, commit=NEW_COMMIT):
    return {
        "app": name, "window_start": _ts(captured - timedelta(seconds=window)),
        "captured_at": _ts(captured), "release_version": version, "release_commit": commit,
        "formation": {"worker-realtime": formation}, "instances": instances,
    }


def _proof(main_instances=None, heavy_instances=(), main_formation=1, heavy_formation=0, **main_kw):
    main = [_old_exited(), _inst()] if main_instances is None else main_instances
    return {
        "event_id": EVENT_ID,
        "denylist_commit": DENY_COMMIT,
        "apps": [
            _app("bainluck", main, main_formation, **main_kw),
            _app("bainluck-heavy", list(heavy_instances), heavy_formation),
        ],
    }


def _judge(proof, env=ENV, lock=LOCK):
    parsed = restore.parse_retirement_proof(proof, event_id=EVENT_ID)
    return restore.judge_retirement_proof(
        parsed, release_version=env.get("HEROKU_RELEASE_VERSION"),
        slug_commit=env.get("HEROKU_SLUG_COMMIT"), lock_now=lock,
    )


def test_rp1_a_valid_proof_is_admitted_and_reports_the_latest_exit():
    refusals, latest = _judge(_proof())
    assert refusals == []
    assert latest == LOCK - timedelta(seconds=60)


def _drop(d, key):
    return {k: v for k, v in d.items() if k != key}


@pytest.mark.parametrize(
    "build, reason",
    [
        (lambda: _drop(_proof(), "denylist_commit"), "top_keys"),
        (lambda: {**_proof(), "extra": 1}, "top_keys"),
        (lambda: {**_proof(), "event_id": str(EVENT_ID)}, "event_id"),
        (lambda: {**_proof(), "event_id": EVENT_ID + 1}, "event_id_mismatch"),
        (lambda: {**_proof(), "denylist_commit": "A" * 40}, "denylist_commit"),
        (lambda: {**_proof(), "apps": _proof()["apps"][:1]}, "apps"),
        (lambda: {**_proof(), "apps": [_proof()["apps"][0]] * 2}, "apps"),
        (lambda: _proof(main_instances=[{**_inst(), "exited_at": None, "extra": 1}]), "instance_keys"),
        (lambda: _proof(main_instances=[{**_inst(), "carries_id": "true"}]), "carries_id"),
        (lambda: _proof(main_instances=[{**_old_exited(), "exited_at": "2031-10-03T14:59:00"}]), "exited_at"),
        (lambda: _proof(main_instances=[{**_old_exited(), "exited_at": "2031-10-03T25:59:00Z"}]), "exited_at"),
        (lambda: _proof(main_instances=[{**_inst(), "release_commit": "abc"}]), "release_commit"),
        (lambda: _proof(main_instances=[{**_old_exited(), "exit_evidence": None}]), "exit_fields"),
        (lambda: _proof(main_instances=[{**_inst(), "exited_at": _ts(LOCK)}]), "exit_fields"),
        (lambda: _proof(main_instances=[{**_old_exited(), "exit_evidence": "crash"}]), "exit_evidence"),
        (lambda: _proof(main_instances=[_inst(dyno="worker-background.1", type_="worker-background")]),
         "out_of_scope_instance"),
        (lambda: _proof(main_instances=[{**_inst(), "dyno": ""}]), "dyno"),
        (lambda: _proof(main_instances=[{**_inst(), "type": None}]), "type"),
        (lambda: _proof(main_instances=[{**_inst(), "release_version": "5500"}]), "release_version"),
        (lambda: _proof(main_instances=[{**_inst(), "state_at_capture": "crashed"}]), "state_at_capture"),
        (lambda: _proof(main_instances=[{**_old_exited(), "evidence_line": ""}]), "evidence_line"),
        (lambda: _proof(main_instances=[{**_old_exited(), "exited_at": "2031-10-3T14:59:00Z"}]), "exited_at"),
        (lambda: {**_proof(), "apps": [_drop(_proof()["apps"][0], "formation"), _proof()["apps"][1]]},
         "app_keys"),
        (lambda: {**_proof(), "apps": [{**_proof()["apps"][0], "app": "bainluck-staging"}, _proof()["apps"][1]]},
         "apps"),
        (lambda: {**_proof(), "apps": [{**_proof()["apps"][0], "formation": {"worker-realtime": -1}},
                                       _proof()["apps"][1]]}, "formation"),
        (lambda: {**_proof(), "apps": [{**_proof()["apps"][0], "release_version": 5500.0},
                                       _proof()["apps"][1]]}, "release_version"),
        (lambda: {**_proof(), "apps": [{**_proof()["apps"][0], "instances": {}}, _proof()["apps"][1]]},
         "instances"),
        (lambda: {**_proof(), "apps": {"bainluck": 1}}, "apps"),
        (lambda: {**_proof(), "apps": [{**_proof()["apps"][0], "app": 5}, _proof()["apps"][1]]}, "apps"),
    ],
)
def test_rp2_every_malformed_proof_refuses_with_no_default(build, reason):
    with pytest.raises(restore.ProofRefusal) as exc:
        restore.parse_retirement_proof(build(), event_id=EVENT_ID)
    assert exc.value.reason == f"retirement_proof_invalid:{reason}"


def test_rp2_a_one_off_run_dyno_is_in_scope():
    one_off = _inst(dyno="run.4821", type_="run", version=OLD_VERSION, commit=OLD_COMMIT,
                    carries=False, state="exited", exited_at=LOCK - timedelta(seconds=90), evidence="exit")
    assert _judge(_proof(main_instances=[_old_exited(), one_off, _inst()]))[0] == []


@pytest.mark.parametrize(
    "evidence, seconds_before_lock, admitted",
    [
        ("exit", 10, True), ("exit", 11, True), ("exit", 9, False),
        ("sigterm", 40, True), ("sigterm", 41, True), ("sigterm", 39, False),
    ],
)
def test_rp3_sigterm_adds_exactly_30s_and_the_skew_margin_is_exactly_10s(
    evidence, seconds_before_lock, admitted
):
    old = _old_exited(at=LOCK - timedelta(seconds=seconds_before_lock), evidence=evidence)
    proof = _proof(main_instances=[old, _inst()], captured=LOCK - timedelta(seconds=5))
    refusals, latest = _judge(proof)
    assert (refusals == []) is admitted, refusals
    if not admitted:
        assert refusals == ["retirement_after_lock:worker-realtime.1"]
    bound = timedelta(seconds=30 if evidence == "sigterm" else 0)
    assert latest == LOCK - timedelta(seconds=seconds_before_lock) + bound


def test_rp_an_empty_main_formation_is_not_a_carrier():
    refusals, _ = _judge(_proof(main_instances=[_old_exited()], main_formation=0))
    assert refusals == ["replacement_absent:bainluck:worker-realtime"]


def test_rp_an_up_instance_that_does_not_carry_the_id_is_both_unretired_and_not_a_carrier():
    up_old = _inst(dyno="worker-realtime.2", version=OLD_VERSION, commit=OLD_COMMIT, carries=False)
    refusals, _ = _judge(_proof(main_instances=[_inst(), up_old], main_formation=2))
    assert refusals == ["replacement_not_carrying:worker-realtime.2", "retirement_unproven:worker-realtime.2"]


def test_restore_refuses_a_missing_row_and_an_already_restored_one(monkeypatch):
    monkeypatch.setattr(restore, "RESTORED_FILL_EVENT_IDS", frozenset({EVENT_ID}))
    assert restore.admit_row(None, event_id=EVENT_ID).refusals == ["row_absent"]
    marker = RESTORED_TAG_PREFIX + _tag()[len(FILL_TAG_PREFIX):]
    row = {
        "id": EVENT_ID, "espn_id": ESPN_EVENT, "status": "scheduled",
        "home_team_name": "TBD", "away_team_name": "TBD", "home_team_id": None, "away_team_id": None,
        "home_team_normalized": None, "away_team_normalized": None,
        "home_team_alt_names": None, "away_team_alt_names": None, "event_tags": [marker],
    }
    assert restore.admit_row(row, event_id=EVENT_ID).refusals == ["already_restored", "receipt_absent"]


def test_rp4_a_closed_window_with_no_non_carrying_instance_is_admitted():
    refusals, latest = _judge(_proof(main_instances=[_inst()]))
    assert refusals == [] and latest is None


async def test_rp5_release_age_and_the_proof_never_waive_each_other(tmp_path):
    good = tmp_path / "proof.json"
    good.write_text(json.dumps(_proof()))
    young = {**ENV, "HEROKU_RELEASE_CREATED_AT": _ts(LOCK - timedelta(seconds=30))}
    adm = restore._admit(None, event_id=EVENT_ID, env=young, lock_now=LOCK, proof_path=str(good))
    assert "release_too_young" in adm.refusals
    assert not [r for r in adm.refusals if r.startswith(("retirement", "replacement"))]
    old = {**ENV, "HEROKU_RELEASE_CREATED_AT": _ts(LOCK - timedelta(seconds=185))}
    adm = restore._admit(None, event_id=EVENT_ID, env=old, lock_now=LOCK, proof_path=None)
    assert "retirement_proof_absent" in adm.refusals
    assert "release_too_young" not in adm.refusals and "release_age_unknown" not in adm.refusals


@pytest.mark.parametrize("value", [None, "", "yesterday", "2031-10-03T14:59:00"])
def test_rp5_an_absent_or_unparseable_release_stamp_is_unknown_never_old(value):
    assert restore.release_age_refusal(value, LOCK) == "release_age_unknown"


# ── Static guards over files this change only reads ──────────────────────────


def _worker_queues(command: str):
    m = re.search(r"(?:--queues[= ]|-Q\s*)(\S+)", command)
    return None if m is None else set(m.group(1).split(","))


def test_g_procfile_the_fill_capable_process_types_are_exactly_the_realtime_consumers():
    consumers = set()
    for line in (BACKEND / "Procfile").read_text(encoding="utf-8").splitlines():
        if not line.strip() or ":" not in line:
            continue
        name, command = line.split(":", 1)
        if re.search(r"\bcelery\b.*\bworker\b", command):
            queues = _worker_queues(command)
            assert queues is not None, f"{name} names no queue list; re-derive the proof scope"
            if "realtime" in queues:
                consumers.add(name.strip())
    assert consumers == set(restore.FILL_CAPABLE_PROCESS_TYPES)


def _parents(tree):
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def test_g_caller_the_scheduled_pass_runs_inside_a_step_savepoint_whose_failure_is_counted():
    tree = ast.parse((BACKEND / "app/tasks/espn_sync.py").read_text(encoding="utf-8"))
    parents = _parents(tree)
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "sync_scheduled_events"
    ]
    assert len(calls) == 1
    node, saw_savepoint, handler_ok = calls[0], False, False
    while node in parents:
        node = parents[node]
        if isinstance(node, ast.AsyncWith) and any(
            ast.unparse(item.context_expr) == "_step_savepoint(session)" for item in node.items
        ):
            saw_savepoint = True
        if saw_savepoint and isinstance(node, ast.Try):
            handler_ok = any(
                'stats["errors"].append' in ast.unparse(h) or "stats['errors'].append" in ast.unparse(h)
                for h in node.handlers
            )
            break
    assert saw_savepoint and handler_ok


def test_the_seam_holds_no_catch_around_the_fill():
    tree = ast.parse((BACKEND / "app/utils/espn_helpers.py").read_text(encoding="utf-8"))
    parents = _parents(tree)
    (call,) = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "maybe_fill_participants"
    ]
    node = call
    while node in parents:
        node = parents[node]
        assert not isinstance(node, ast.Try), "a catch at the call site can hide what must propagate"
        if isinstance(node, ast.AsyncFunctionDef):
            assert node.name == "sync_scheduled_events"
            break
