"""#10090 A1 adapter controls on synthetic arm directories (no lab, browser or network).

Each control builds a miniature sealed tape and two arms whose records follow
the lab's A1 recorders field for field, then breaks one thing.
"""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import a1_adapter  # noqa: E402
import compare  # noqa: E402

S, T0, L0 = 1_800_000_000_000.0, 1000.0, 1_800_000_000.0
READ, AWAY, X, X2, BH, BA, PH, PA, Y, Y2 = 100, 101, 110, 111, 200, 201, 300, 301, 310, 311


def ticker(t, p, seq):
    return json.dumps({"msg": {"market_ticker": t, "price_dollars": f"{p:.4f}", "yes_ask_dollars": f"{p+.005:.4f}",
                               "yes_bid_dollars": f"{p-.005:.4f}"}, "seq": seq, "sid": 1, "type": "ticker"},
                      separators=(",", ":"), sort_keys=True)


def make_tape():
    markets = [
        {"event_id": 1, "id": 10, "role": "headline", "retained": True, "external_id": "KXATPDOUBLES-LAB",
         "outcomes": [{"id": READ, "external_id": "KXATPDOUBLES-LAB-H", "leg": "home"},
                      {"id": AWAY, "external_id": "KXATPDOUBLES-LAB-A", "leg": "away"}]},
        {"event_id": 1, "id": 11, "role": "board", "external_id": "KXA1LABPROP1-LAB",
         "outcomes": [{"id": X, "external_id": "KXA1LABPROP1-LAB-O1"}, {"id": X2, "external_id": "KXA1LABPROP1-LAB-O2"}]},
        {"event_id": 2, "id": 20, "role": "headline", "external_id": "KXATPDOUBLES-LABB",
         "outcomes": [{"id": BH, "external_id": "KXATPDOUBLES-LABB-H", "leg": "home"},
                      {"id": BA, "external_id": "KXATPDOUBLES-LABB-A", "leg": "away"}]},
        {"event_id": 3, "id": 30, "role": "headline", "external_id": "KXATPDOUBLES-LABP",
         "outcomes": [{"id": PH, "external_id": "KXATPDOUBLES-LABP-H", "leg": "home"},
                      {"id": PA, "external_id": "KXATPDOUBLES-LABP-A", "leg": "away"}]},
        {"event_id": 3, "id": 31, "role": "board", "external_id": "KXA1LABPROP1-LABP",
         "outcomes": [{"id": Y, "external_id": "KXA1LABPROP1-LABP-O1"}, {"id": Y2, "external_id": "KXA1LABPROP1-LABP-O2"}]},
    ]
    ext = {o["id"]: o["external_id"] for m in markets for o in m["outcomes"]}
    frames, seq = [], [0]

    def add(at, role, oid, p, cycle=None):
        seq[0] += 1
        frames.append({"at_ms": at, "role": role, "cycle": cycle, "outcome_id": oid, "market_id": 0,
                       "ticker": ext[oid], "home_value": f"{p:.4f}", "raw": ticker(ext[oid], p, seq[0])})

    def head(at, role, home, away, p, cycle=None):
        add(at, role, home, p, cycle)
        add(at, role, away, round(1 - p, 4), cycle)
    head(0, "A-headline", READ, AWAY, .30)
    add(0, "A-board", X, .10); add(0, "A-board", X2, .11)
    head(0, "B-headline", BH, BA, .59)
    head(0, "P-headline", PH, PA, .45)
    add(0, "P-board", Y, .20); add(0, "P-board", Y2, .21)
    head(10000, "P-headline", PH, PA, .46, 1)
    add(10000, "P-board", Y, .201, 1); add(10000, "P-board", Y2, .211, 1)
    head(10800, "B-headline", BH, BA, .60, 1)
    add(11000, "A-board", X, .101, 1); add(11000, "A-board", X2, .111, 1)
    head(11000, "A-headline", READ, AWAY, .31, 1)
    add(14500, "A-board", X, .102, 1); add(14500, "A-board", X2, .112, 1)
    head(14500, "A-headline", READ, AWAY, .32, 1)
    head(15200, "A-headline", READ, AWAY, .33, 1)
    holds = [{"outcome_id": Y, "value": "0.2010", "hold_s": 3.5, "label": "cycle-1-owner-nonlive-phase", "cycle": 1, "role": "P-board"},
             {"outcome_id": BH, "value": "0.6000", "hold_s": 0.4, "label": "cycle-1-beside-pacer", "cycle": 1, "role": "B-headline"},
             {"outcome_id": X, "value": "0.1010", "hold_s": 1.2, "label": "cycle-1-board-unfinished-beside", "cycle": 1, "role": "A-board"}]
    return {"schema": "a1-kalshi-tape/1", "sample_duration_s": 60, "fixture": {"markets": markets},
            "frames": frames, "holds": holds, "markers": [{"at_ms": 9500, "label": "parity-snapshot"}],
            "roles": {"X": X, "Y": Y, "A_read_leg_candidates": [READ]}, "cycle_ms": [10000], "deciding_cycles": 1}


def mono(t_ms):
    return T0 + t_ms/1000.0


def wall(t_ms):
    return (S + t_ms)/1000.0


def iso(seconds):
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()


MARKET = {READ: 10, AWAY: 10, X: 11, X2: 11, BH: 20, BA: 20, PH: 30, PA: 30, Y: 31, Y2: 31}
EVENT_OF = {READ: 1, AWAY: 1, X: 1, X2: 1, BH: 2, BA: 2, PH: 3, PA: 3, Y: 3, Y2: 3}
# lab/FIXTURE-INPUT.json's retained Kalshi bag, as seeded (lab r2 `origin='seed'`): no observed_basis.
SEED_BAG = {"value": 0.465, "display_name": "Kalshi", "type": "market", "color": "#22c55e",
            "updated_at": "2026-10-21T16:05:39.623092+00:00", "evidence_status": "verified",
            "verified_scope": "full_event_winner", "contract_version": "live_blend.admissible_as_blend_speaker@5031"}


def phase(t0, t1, values, *, beside, rows=None):
    """One price phase as the lab r2 recorder writes it: RETURNING rows with their
    own value, then the OUTER commit witnessed 0.5 ms after the iterator returned."""
    return {"start_mono": mono(t0), "end_mono": mono(t1), "beside": beside, "status": "returned",
            "outer": "committed", "committed_mono": mono(t1) + .0005,
            "outcomes": {str(k): [v, v-.005, v+.005] for k, v in values.items()},
            "rows": [{"id": k, "market_id": MARKET[k], "last_updated": L0 + t0/1000.0 + .0001, "last_updated_iso": "",
                      "database_clock": "", "value": values[k], "quote_moved": True}
                     for k in (rows if rows is not None else values)]}


def publication(p):
    """The post-commit MARKET publication of one committed phase: one change per
    market naming each returned row's basis; every PUBLISH acknowledged."""
    changes = {}
    for r in p["rows"]:
        change = changes.setdefault(r["market_id"], {"market_id": r["market_id"], "source": "kalshi",
                                                     "outcome_observed_at": {}, "terminal": False, "invalidation": True})
        change["outcome_observed_at"][str(r["id"])] = iso(r["last_updated"])
    for change in changes.values():
        change["outcome_ids"] = sorted(map(int, change["outcome_observed_at"]))
    return {"mono": p["committed_mono"] + .0002, "end_mono": p["committed_mono"] + .0004, "source": "kalshi",
            "changes": list(changes.values()), "sent": len(changes)}


def make_arm(root, name, tape, *, shown_31, commit_32=True, control_delay_ms=10):
    path = Path(root)/name
    path.mkdir()
    raw = json.dumps(tape, sort_keys=True)
    (path/"A1-TAPE.json").write_text(raw)
    tape_sha = hashlib.sha256(raw.encode()).hexdigest()
    sent, marks, seq = [], [], 0
    for i, f in enumerate(tape["frames"]):
        sm = mono(f["at_ms"]) + .0005
        sent.append({"i": i, "at_ms": f["at_ms"], "sha256": hashlib.sha256(f["raw"].encode()).hexdigest(),
                     "sent_count": 1, "errors": [], "sent_mono": sm, "jitter_ms": .5, "scheduled_mono": mono(f["at_ms"])})
        seq += 1
        p = float(json.loads(f["raw"])["msg"]["price_dollars"])
        marks.append({"seq": seq, "event_id": EVENT_OF[f["outcome_id"]], "outcome_id": f["outcome_id"],
                      "probability": p, "kind": "ticker", "recv_wall": (S + f["at_ms"] + 1.5)/1000.0,
                      "recv_mono": sm + .001, "venue_ts_ms": None, "event_ordinal": 0, "source": "kalshi"})
    # [0..4] keep the deciding layout; later entries are warmup and the owner's board tail.
    phases = [phase(50, 60, {READ: .30, AWAY: .70}, beside=False),
              phase(10100, 13700, {PH: .46, PA: .54, Y: .201, Y2: .211}, beside=False),
              phase(10810, 11220, {BH: .60, BA: .40}, beside=True),
              phase(11230, 11240, {READ: .31, AWAY: .69}, beside=True),
              phase(11240, 12450, {X: .101, X2: .111}, beside=True),
              phase(60, 70, {X: .10, X2: .11, Y: .20, Y2: .21}, beside=False),
              phase(70, 80, {BH: .59, BA: .41, PH: .45, PA: .55}, beside=False),
              phase(14620, 14630, {X: .102, X2: .112}, beside=False)]
    if commit_32:
        phases.append(phase(14600, 14610, {READ: .32, AWAY: .68}, beside=False))
    phases.append(phase(15300, 15310, {READ: .33, AWAY: .67}, beside=False))
    publications = [publication(p) for p in phases]

    def basis_of(oid, value):
        return next(r["last_updated"] for p in phases for r in p["rows"] if r["id"] == oid and r["value"] == value)
    bag_log = [{"event_id": 1, "rev": 1, "kalshi": SEED_BAG, "logged_at": iso(wall(-5000)), "origin": "seed"}]
    shows = [(0, 1), (300, 2, .30), (shown_31, 3, .31)]
    if commit_32:
        shows.append((14800, 4, .32))
    shows.append((15500, 5, .33))
    for item in shows[1:]:
        bag_log.append({"event_id": 1, "rev": item[1], "logged_at": iso(wall(item[0] - 20)), "origin": "update",
                        "kalshi": json.dumps({"observed_basis": {str(READ): basis_of(READ, item[2])}})})
    # B/P: each committed home-leg row is stamped `control_delay_ms` after its commit,
    # and the refresher's post-commit resolve names that event's rev as stamped.
    resolved = []
    for event, oid, commits in ((2, BH, [(80, .59), (11220, .60)]), (3, PH, [(80, .45), (13700, .46)])):
        bag_log.append({"event_id": event, "rev": 1, "kalshi": None, "logged_at": iso(wall(-5000)), "origin": "seed"})
        for rev, (at, value) in enumerate(commits, start=2):
            stamped = at + control_delay_ms
            bag_log.append({"event_id": event, "rev": rev, "logged_at": iso(wall(stamped)), "origin": "update",
                            "kalshi": {"value": value, "observed_basis": {str(oid): basis_of(oid, value)}}})
            resolved.append({"mono": mono(stamped + 2), "due": [event], "staged": {str(event): None},
                             "dispositions": {str(event): ["stamped", str(value), "", "None", str(rev), "live"]}})
    rows = []
    for t in range(0, 60001, 100):
        rev = max(r for at, r, *_ in shows if at <= t)
        state = f"fold:1={rev}"
        ident = {"headline": {"status": "present", "count": 1, "visible": True,
                              "attributes": {"data-display-state": state, "data-display-basis": "committed"}},
                 "chart": {"status": "present", "count": 1, "visible": True,
                           "attributes": {"data-chart-endpoint-state": state, "data-chart-endpoint-basis": "push"}}}
        rows.append({"kind": "dom", "wall": S + t, "mono": t, "hero": "0.5", "displayIdentity": ident})
    (path/"reader.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    cls = {o["external_id"]: {"outcome_id": o["id"], "market_id": m["id"], "event_id": m["event_id"],
                              "role": m["role"], "market_external_id": m["external_id"],
                              "feeds_win_prob_blend": m["role"] == "headline",
                              "headline_aux": m["role"] == "board", "non_speaking": False}
           for m in tape["fixture"]["markets"] for o in m["outcomes"]}
    parity = {"outcomes": {str(o["id"]): {"event_id": m["event_id"], "value": .5, "age_s": 1.0}
                           for m in tape["fixture"]["markets"] for o in m["outcomes"]},
              "events": {str(e): {"status": "live", "commence_age_s": 3600.0, "rev": 2, "kalshi_value": .3,
                                  "kalshi_entry_age_s": 1.0} for e in (1, 2, 3)}, "snapshots": []}
    a1 = {"marks": marks, "phases": phases, "asks": [], "resolved": resolved, "sent": sent, "parity": parity,
          "holds": [{"label": h["label"], "held_s": h["hold_s"]} for h in tape["holds"]], "bag_log": bag_log,
          "plans": [{"mono": mono(11225), "beside": True, "phases": [[READ, AWAY], [X, X2]]}],
          "market_publications": publications}
    receipt = {"errors": [], "runs": [{"kind": a1_adapter.MODE, "status": "inputs-complete", "sample_start_ms": S,
                                        "a1_t0_mono": T0, "a1_tape_sha256": tape_sha}],
               "consumer_epochs": [{"source": "kalshi", "started": T0 - 5}], "a1": a1}
    files = {"backend-receipt.json": receipt,
             "SOURCE.json": {"scenario": a1_adapter.MODE, "backend_ref": name * 40,
                             "frontend_build_source_sha": "f" * 40, "build_id": "BUILD"},
             "CONFIG.json": {"requested": {"fixture": "a1", "preview_sources": ["kalshi", "polymarket"]},
                             "effective": {"a1": {"tape_sha256": tape_sha, "speed_switch_env": {},
                                                  "preview_from_commit_possible": False, "classification": cls}}},
             "RUN.json": {"status": "READER_COMPLETE"}, "SOURCE-AFTER.json": {"unchanged": True},
             "CLEANUP.json": {"stopped": True, "cleanup_errors": []},
             "OBSERVATION-SCORE.json": {"status": "OBSERVED_CALLBACK_INTERVALS", "faults": [],
                                        "clock_mapping": {"edge_uncertainty_ms": 1}, "longest_wait": {"ms": 1}},
             "sample-boundaries.json": {"start_ms": S, "end_ms": S + 60000}}
    for fname, value in files.items():
        (path/fname).write_text(json.dumps(value))
    return path, tape_sha


class A1AdapterControls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.tape = make_tape()

    def tearDown(self):
        self.tmp.cleanup()

    def pair(self, *, base_kw=None, cand_kw=None, tape_c=None):
        b, sha = make_arm(self.root, "b", self.tape, **({"shown_31": 12600} | (base_kw or {})))
        c, _ = make_arm(self.root, "c", tape_c or self.tape, **({"shown_31": 11400} | (cand_kw or {})))
        spec = {"mode": a1_adapter.MODE, "baseline": str(b), "candidate": str(c), "baseline_sha": "b" * 40,
                "candidate_sha": "c" * 40, "tape": str(b/"A1-TAPE.json"), "tape_sha256": sha,
                "min_exercised_cycles": 1}
        return b, c, spec

    def edit(self, path, name, fn):
        value = json.loads((path/name).read_text())
        fn(value)
        (path/name).write_text(json.dumps(value))

    def consume(self, spec, out="out"):
        return a1_adapter.a1_consume(spec, self.root/out, stable_backend_clock=True)

    def invalid(self, spec, needle):
        with self.assertRaises(ValueError) as caught:
            self.consume(spec, "bad")
        self.assertIn(needle, str(caught.exception))
        self.assertEqual(json.loads((self.root/"bad"/"INVALID.json").read_text())["decision"], "experiment_invalid")

    def test_supported_gain_on_the_deciding_input_through_compare_consume(self):
        _, _, spec = self.pair()
        result = compare.consume(spec, self.root/"out", stable_backend_clock=True)
        self.assertEqual(result["decision"], "improvement_supported")
        b, c = result["baseline"], result["candidate"]
        self.assertEqual(b["mechanism"]["exercised"], 1)
        delay = {arm: next(u for u in r["score"]["surfaces"]["headline"]["updates"] if u["id"] == "A:1")["delay_ms"]
                 for arm, r in (("b", b), ("c", c))}
        self.assertGreater(delay["b"][0], 1000)
        self.assertLess(delay["c"][1], 500)
        self.assertEqual(b["trace"]["coverage"]["eligible_states_scored"], 4)

    def test_timing_requires_the_explicit_clock_assumption(self):
        _, _, spec = self.pair()
        with self.assertRaises(ValueError) as caught:
            a1_adapter.a1_consume(spec, self.root/"t", stable_backend_clock=False)
        self.assertIn("timing_unknown", str(caught.exception))

    # ── admission-case substitution ────────────────────────────────────────
    def test_the_admission_fixture_or_scenario_is_refused(self):
        b, _, spec = self.pair()
        self.edit(b, "CONFIG.json", lambda v: v["requested"].update(fixture="singleton"))
        self.invalid(spec, "not the A1 fixture")

    def test_the_admission_spec_never_routes_into_a1_and_a1_never_into_admission(self):
        _, _, spec = self.pair()
        with self.assertRaises(ValueError):
            a1_adapter.a1_consume(dict(spec, mode="controlled-admission"), self.root/"m", stable_backend_clock=True)
        # run_existing with the A1 mode refuses on its own pins before reserving output.
        out = self.root/"never"
        with self.assertRaises((ValueError, KeyError, FileNotFoundError)):
            compare.run_existing(dict(spec, hypothesis="h", baseline_release_evidence="r", helper="/nonexistent",
                                      helper_sha256="x", lab_files={}), out, stable_backend_clock=True)
        self.assertFalse(out.exists())

    def test_an_arm_that_ran_another_tape_is_refused(self):
        b, _, spec = self.pair()
        self.edit(b, "backend-receipt.json", lambda v: v["runs"][0].update(a1_tape_sha256="0" * 64))
        self.invalid(spec, "sealed tape")

    # ── cohort / board identity ─────────────────────────────────────────────
    def test_a_display_whose_basis_is_a_board_commit_is_a_hole_not_coverage(self):
        b, _, spec = self.pair()
        receipt = json.loads((b/"backend-receipt.json").read_text())
        board_basis = next(r["last_updated"] for p in receipt["a1"]["phases"] for r in p["rows"] if r["id"] == X)
        self.edit(b, "backend-receipt.json", lambda v: v["a1"]["bag_log"][3].update(
            kalshi={"observed_basis": {str(READ): board_basis}}))
        self.invalid(spec, "identity coverage incomplete")

    def test_a_frame_basis_naming_a_board_outcome_is_refused(self):
        b, _, spec = self.pair()
        self.edit(b, "backend-receipt.json", lambda v: v["a1"]["bag_log"].append(
            {"event_id": 1, "rev": 9, "kalshi": {"observed_basis": {str(X): L0}}, "origin": "update"}))
        self.invalid(spec, "not exactly the declared read leg")

    def test_a_board_the_arm_would_read_or_drop_from_the_cohort_is_refused(self):
        b, _, spec = self.pair()
        self.edit(b, "CONFIG.json", lambda v: v["effective"]["a1"]["classification"]["KXA1LABPROP1-LAB-O1"].update(
            non_speaking=True))
        self.invalid(spec, "in-cohort headline-aux")

    def test_board_marks_never_become_headline_obligations(self):
        _, _, spec = self.pair()
        result = self.consume(spec)
        ids = [o["id"] for o in result["baseline"]["trace"]["eligible"]]
        self.assertEqual(ids, ["A:0", "A:1", "A:2", "A:3"])  # read-leg inputs only; 6 board inputs owe nothing

    # ── independent epoch rebasing / starting parity ───────────────────────
    def test_rebased_offsets_are_refused(self):
        _, c, spec = self.pair()
        self.edit(c, "backend-receipt.json", lambda v: [e.update(at_ms=e["at_ms"] + 7) for e in v["a1"]["sent"]])
        self.invalid(spec, "sealed offset")

    def test_different_tape_bytes_between_arms_are_refused(self):
        tape_c = copy.deepcopy(self.tape)
        tape_c["frames"][0]["raw"] = tape_c["frames"][0]["raw"].replace('"seq":1', '"seq":99')
        b, c, spec = self.pair(tape_c=tape_c)
        self.invalid(spec, "sealed tape")

    def test_unequal_starting_ages_are_refused(self):
        _, c, spec = self.pair()
        self.edit(c, "backend-receipt.json", lambda v: v["a1"]["parity"]["events"]["1"].update(kalshi_entry_age_s=4.0))
        self.invalid(spec, "kalshi_entry_age_s differs")

    def test_unequal_settings_are_refused(self):
        _, c, spec = self.pair()
        self.edit(c, "CONFIG.json", lambda v: v["effective"]["a1"].update(
            speed_switch_env={"SPEED_SWITCH_TODAY_PREVIEW_FROM_COMMIT": "1"}))
        self.invalid(spec, "relevant settings differ")

    # ── missing context / cleanup / mechanism ──────────────────────────────
    def test_unclean_cleanup_is_refused(self):
        b, _, spec = self.pair()
        self.edit(b, "CLEANUP.json", lambda v: v.update(stopped=False))
        self.invalid(spec, "cleanup incomplete")

    def test_missing_starting_context_is_refused(self):
        b, _, spec = self.pair()
        self.edit(b, "backend-receipt.json", lambda v: v["a1"].pop("parity"))
        self.invalid(spec, "missing A1 context")

    def test_an_unexercised_board_contention_is_invalid_never_no_improvement(self):
        _, c, spec = self.pair()
        # The board committed by the owner, not beside: the deciding mechanism did not occur.
        self.edit(c, "backend-receipt.json", lambda v: v["a1"]["phases"][4].update(beside=False))
        self.invalid(spec, "mechanism unexercised in cycles [1]")

    def test_a_board_that_finished_before_the_headline_did_not_exercise_it(self):
        _, c, spec = self.pair()
        self.edit(c, "backend-receipt.json", lambda v: v["a1"]["phases"][4].update(end_mono=mono(11235)))
        self.invalid(spec, "mechanism unexercised")

    # ── identity, not percent equality; explicit supersession ──────────────
    def test_an_equal_percentage_under_an_older_identity_does_not_cover(self):
        b, _, spec = self.pair()
        rows = [json.loads(line) for line in (b/"reader.jsonl").read_text().splitlines()]
        for r in rows:
            if 11300 <= r["wall"] - S < 12600:
                r["hero"] = "0.31"  # the new number, still under rev 2's identity
        (b/"reader.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        result = self.consume(spec)
        upd = next(u for u in result["baseline"]["score"]["surfaces"]["headline"]["updates"] if u["id"] == "A:1")
        self.assertGreater(upd["delay_ms"][0], 1000)

    def test_an_input_superseded_before_commit_is_coalesced_not_missing(self):
        _, _, spec = self.pair(base_kw={"commit_32": False}, cand_kw={"commit_32": False})
        result = self.consume(spec)
        head = result["candidate"]["score"]["surfaces"]["headline"]
        self.assertEqual(head["coalesced"], ["A:2"])
        self.assertEqual(head["unresolved_at_end"], [])

    def test_an_unbracketed_or_unresolvable_display_row_is_invalid(self):
        b, _, spec = self.pair()
        self.edit(b, "backend-receipt.json", lambda v: v["a1"]["bag_log"].pop(2))  # rev 2's bag missing
        self.invalid(spec, "identity coverage incomplete")

    # ── Measurement 0906Z (1): board correctness gates the verdict ─────────
    def test_every_board_input_is_committed_and_published_by_identity(self):
        _, _, spec = self.pair()
        result = self.consume(spec)
        self.assertEqual(result["decision"], "improvement_supported")
        board = result["candidate"]["board_publication"]
        self.assertEqual((board["outcomes"], board["inputs"], board["committed_and_published"], board["coalesced"]),
                         (4, 10, 10, 0))
        self.assertEqual((board["failures"], board["dom"]), ([], "not_measured"))

    def test_no_market_publication_is_invalid(self):
        _, c, spec = self.pair()
        self.edit(c, "backend-receipt.json", lambda v: v["a1"].update(market_publications=[]))
        self.invalid(spec, "but unpublished")

    def test_a_failed_publication_is_invalid(self):
        _, c, spec = self.pair()
        self.edit(c, "backend-receipt.json", lambda v: v["a1"]["market_publications"][4].update(sent=0))
        self.invalid(spec, "but publication_failed")

    def test_a_partial_publication_is_invalid(self):
        _, c, spec = self.pair()  # phase 5 publishes two board markets; one acknowledged
        self.edit(c, "backend-receipt.json", lambda v: v["a1"]["market_publications"][5].update(sent=1))
        self.invalid(spec, "but publication_failed")

    def test_a_publication_naming_the_market_without_the_row_basis_is_invalid(self):
        _, c, spec = self.pair()

        def change(v):
            stamps = v["a1"]["market_publications"][4]["changes"][0]["outcome_observed_at"]
            stamps[str(X2)] = iso(datetime.fromisoformat(stamps[str(X2)]).timestamp() + 1)
        self.edit(c, "backend-receipt.json", change)
        self.invalid(spec, f"board {X2}:1 committed in phase 4 but unpublished")

    def test_a_publication_before_its_commit_does_not_count(self):
        _, c, spec = self.pair()
        self.edit(c, "backend-receipt.json", lambda v: v["a1"]["market_publications"][4].update(mono=mono(11000)))
        self.invalid(spec, "but unpublished")

    def test_a_missing_unheld_board_row_is_invalid(self):
        _, c, spec = self.pair()  # Measurement counterexample 3, faithful identities

        def change(v):
            for p in v["a1"]["phases"]:
                p["rows"] = [r for r in p["rows"] if r["id"] != X2]
        self.edit(c, "backend-receipt.json", change)
        self.invalid(spec, f"board {X2}:2 unresolved")

    def test_a_returned_phase_that_rolled_back_commits_nothing(self):
        _, c, spec = self.pair()
        self.edit(c, "backend-receipt.json", lambda v: v["a1"]["phases"][7].update(
            outer="rolled_back", committed_mono=None, rolled_back_mono=mono(14631)))
        self.invalid(spec, f"board {X}:2 unresolved")

    def test_a_board_input_superseded_before_commit_is_coalesced_explicitly(self):
        _, c, spec = self.pair()
        self.edit(c, "backend-receipt.json", lambda v: v["a1"]["phases"][5].update(
            rows=[r for r in v["a1"]["phases"][5]["rows"] if r["id"] not in (X, X2)]))
        result = self.consume(spec)
        self.assertEqual(result["decision"], "improvement_supported")
        by = {x["id"]: x for x in result["candidate"]["board_publication"]["by_input"]}
        self.assertEqual((by[f"{X}:0"]["disposition"], by[f"{X}:0"]["via"]), ("coalesced", f"{X}:1"))

    # ── Measurement 0906Z (2): B/P controls gate completeness and regression ──
    def test_each_B_and_P_input_resolves_to_its_own_committed_stamp(self):
        _, _, spec = self.pair()
        result = self.consume(spec)
        controls = result["candidate"]["controls"]
        self.assertEqual(sorted(controls), ["2", "3"])
        for event, leg in (("2", BH), ("3", PH)):
            control = controls[event]
            self.assertEqual((control["leg"], control["final_debt"], control["failures"]), (leg, 0, []))
            self.assertEqual([(u["id"], u["via"], u["disposition"]) for u in control["updates"]],
                             [(f"{event}:0", f"{event}:0", "stamped"), (f"{event}:1", f"{event}:1", "stamped")])
        delay = controls["2"]["updates"][1]["delay_ms"]  # 10800 receipt -> 11220 commit + 10 ms stamp
        self.assertTrue(400 < delay[0] <= delay[1] < 440, delay)
        self.assertEqual(result["control_regressions"], [])

    def test_a_B_and_P_regression_prevents_a_supported_gain(self):
        # Measurement counterexample 4 with faithful identities: same deciding
        # mechanism and headline gain, B/P committed stamps 100 ms -> 5000 ms.
        _, _, spec = self.pair(base_kw={"control_delay_ms": 100}, cand_kw={"control_delay_ms": 5000})
        result = self.consume(spec)
        self.assertEqual(result["decision"], "no_improvement_or_regression")
        self.assertEqual(len(result["control_regressions"]), 4)
        self.assertIn("control event 2 worst_ms", result["control_regressions"][0])

    def test_unresolved_B_debt_is_invalid(self):
        _, c, spec = self.pair()  # event 2's last stamp never committed
        self.edit(c, "backend-receipt.json", lambda v: v["a1"].update(bag_log=[
            e for e in v["a1"]["bag_log"] if not (e["event_id"] == 2 and e["rev"] == 3)]))
        self.invalid(spec, "control event 2 incomplete (1): 2:1 unresolved at end")

    def test_a_stamp_without_its_post_commit_witness_is_invalid(self):
        _, c, spec = self.pair()
        self.edit(c, "backend-receipt.json", lambda v: v["a1"].update(resolved=[
            r for r in v["a1"]["resolved"] if r["dispositions"].get("3", [None, None, None, None, None])[4] != "3"]))
        self.invalid(spec, "3:1: rev 3 has no post-commit stamped witness")

    def test_a_later_staged_seq_is_not_a_read_basis(self):
        _, c, spec = self.pair()  # the r1 correspondence: stamped + staged seq >= input seq, no rev

        def change(v):
            v["a1"]["resolved"] = [
                {"mono": m["recv_mono"] + .1, "due": [e], "dispositions": {str(e): ["stamped"]},
                 "staged": {str(e): m["seq"] + 1}}
                for m in v["a1"]["marks"] for e, oid in ((2, BH), (3, PH)) if m["outcome_id"] == oid]
        self.edit(c, "backend-receipt.json", change)
        self.invalid(spec, "has no post-commit stamped witness")

    def test_a_stamp_basis_that_is_not_a_committed_row_is_invalid(self):
        _, c, spec = self.pair()

        def change(v):
            entry = next(e for e in v["a1"]["bag_log"] if e["event_id"] == 2 and e["rev"] == 3)
            entry["kalshi"]["observed_basis"][str(BH)] += 5
        self.edit(c, "backend-receipt.json", change)
        self.invalid(spec, "rev 3 basis")

    # ── Measurement 0906Z (3): the real seed is the bounded initial state ──
    def test_the_real_seed_is_the_bounded_initial_state(self):
        _, _, spec = self.pair()
        result = self.consume(spec)
        head = result["candidate"]["trace"]["coverage"]["surface"]["headline"]
        self.assertEqual((head["initial_display"], head["initial_revision"], head["unbracketed"]), ("initial", 1, 0))
        first = next(u for u in result["candidate"]["score"]["surfaces"]["headline"]["updates"] if u["id"] == "A:0")
        self.assertEqual(first["disposition"], "displayed")  # bracketed by the seed rows before it

    def test_an_unknown_initial_revision_is_invalid(self):
        _, c, spec = self.pair()  # a basis-less revision that is not the seed stays unknown
        self.edit(c, "backend-receipt.json", lambda v: v["a1"]["bag_log"][0].update(origin="update", rev=1))
        self.invalid(spec, "no single seeded committed revision")

    def test_a_basis_less_revision_other_than_the_seed_is_a_hole(self):
        _, c, spec = self.pair()
        self.edit(c, "backend-receipt.json", lambda v: v["a1"]["bag_log"][1].update(kalshi=SEED_BAG))
        self.invalid(spec, "identity coverage incomplete")

    def test_an_invented_older_seed_basis_is_not_an_initial_state(self):
        _, c, spec = self.pair()  # the r1 miniature's invented basis
        self.edit(c, "backend-receipt.json", lambda v: v["a1"]["bag_log"][0].update(
            kalshi={"observed_basis": {str(READ): L0 - 100}}))
        self.invalid(spec, "identity coverage incomplete")

    # ── Measurement 0906Z (4): sealed membership, one RETURNING row ────────
    def test_read_leg_marks_naming_another_event_are_invalid(self):
        _, c, spec = self.pair()  # Measurement counterexample 6
        self.edit(c, "backend-receipt.json", lambda v: [m.update(event_id=2) for m in v["a1"]["marks"]
                                                        if m["outcome_id"] == READ])
        self.invalid(spec, f"names event 2 for outcome {READ} of sealed event 1")

    def test_a_board_mark_naming_another_event_is_invalid(self):
        _, c, spec = self.pair()
        self.edit(c, "backend-receipt.json", lambda v: next(m for m in v["a1"]["marks"]
                                                            if m["outcome_id"] == Y).update(event_id=1))
        self.invalid(spec, f"for outcome {Y} of sealed event 3")

    def test_a_duplicate_read_leg_RETURNING_row_is_ambiguous(self):
        _, c, spec = self.pair()  # Measurement counterexample 5

        def change(v):
            rows = v["a1"]["phases"][3]["rows"]
            rows.append(copy.deepcopy(next(r for r in rows if r["id"] == READ)))
        self.edit(c, "backend-receipt.json", change)
        self.invalid(spec, "identity coverage incomplete")

    def test_a_classification_naming_another_event_is_invalid(self):
        b, _, spec = self.pair()
        self.edit(b, "CONFIG.json", lambda v: v["effective"]["a1"]["classification"]["KXATPDOUBLES-LAB-H"].update(
            event_id=2))
        self.invalid(spec, "differs from the sealed fixture on ['event_id']")

    def test_a_RETURNING_row_under_another_market_is_invalid(self):
        _, c, spec = self.pair()
        self.edit(c, "backend-receipt.json", lambda v: v["a1"]["phases"][4]["rows"][0].update(market_id=31))
        self.invalid(spec, "outside the sealed membership")

    def test_a_RETURNING_value_unlike_its_phase_input_is_invalid(self):
        _, c, spec = self.pair()
        self.edit(c, "backend-receipt.json", lambda v: v["a1"]["phases"][3]["rows"][0].update(value=.99))
        self.invalid(spec, "not the input it carried")

    def test_an_r1_receipt_is_refused_as_not_r2(self):
        for i, (strip, needle) in enumerate((
                (lambda v: [p.pop("outer") for p in v["a1"]["phases"]], "phase commit witness absent"),
                (lambda v: [p.pop("sent") for p in v["a1"]["market_publications"]], "publication result absent"),
                (lambda v: [e.pop("origin") for e in v["a1"]["bag_log"]], "seed/update origin"))):
            self.root = Path(self.tmp.name)/f"r1-shape-{i}"
            self.root.mkdir()
            _, c, spec = self.pair()
            self.edit(c, "backend-receipt.json", strip)
            self.invalid(spec, needle)


class A1RunPins(unittest.TestCase):
    """`run` verifies every pin and refuses BEFORE reserving output or starting an arm."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        lab = root/"lab"
        lab.mkdir()
        for name in a1_adapter.LAB_FILES | {"warm_helper.py"}:
            (lab/name).write_text(name)
        scorer = root/"score_transitions.py"
        scorer.write_text("scorer")
        prepared = {}
        for arm, build in (("baseline", "B1"), ("candidate", "B1")):
            d = root/arm
            (d/"source").mkdir(parents=True)
            (d/"source"/"f.txt").write_text(arm)
            manifest = {"sha": arm[0] * 40, "build_id": build, "frontend_build_source_sha": "b" * 40,
                        "files": {"f.txt": hashlib.sha256(arm.encode()).hexdigest()}}
            (d/"PREPARED.json").write_text(json.dumps(manifest))
            prepared[arm] = d
        digest = a1_adapter.digest
        self.spec = {"mode": a1_adapter.MODE, "hypothesis": "h", "baseline_release_evidence": "r",
                     "helper": str(lab/"warm_helper.py"), "helper_sha256": digest(lab/"warm_helper.py"),
                     "lab_files": {n: digest(lab/n) for n in a1_adapter.LAB_FILES},
                     "tape": str(lab/"A1-TAPE.json"), "tape_sha256": digest(lab/"A1-TAPE.json"),
                     "baseline_sha": "b" * 40, "candidate_sha": "c" * 40,
                     "baseline_prepared": str(prepared["baseline"]), "candidate_prepared": str(prepared["candidate"]),
                     "transition_scorer": str(scorer), "transition_scorer_sha256": digest(scorer)}
        self.out = root/"out"

    def tearDown(self):
        self.tmp.cleanup()

    def refused(self, spec, needle, clock=True):
        with self.assertRaises(ValueError) as caught:
            compare.run_existing(spec, self.out, stable_backend_clock=clock)
        self.assertIn(needle, str(caught.exception))
        self.assertFalse(self.out.exists(), "output reserved before a refusal")

    def test_pins_pass_and_only_the_clock_opt_in_stops_it(self):
        self.refused(self.spec, "timing_unknown", clock=False)

    def test_two_frontend_builds_are_refused(self):
        manifest = json.loads(Path(self.spec["candidate_prepared"], "PREPARED.json").read_text())
        manifest["build_id"] = "B2"
        Path(self.spec["candidate_prepared"], "PREPARED.json").write_text(json.dumps(manifest))
        self.refused(self.spec, "one pinned frontend build")

    def test_lab_or_tape_drift_is_refused(self):
        Path(self.spec["tape"]).write_text("another tape")
        self.refused(self.spec, "drift: A1-TAPE.json")

    def test_a_spec_without_the_tape_pin_is_refused(self):
        spec = dict(self.spec, lab_files={k: v for k, v in self.spec["lab_files"].items() if k != "A1-TAPE.json"})
        self.refused(spec, "sealed tape")


if __name__ == "__main__":
    unittest.main()
