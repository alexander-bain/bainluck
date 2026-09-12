"""CAL-P1127 (#2644): a championship future stops saying it resolves in 2029.

THE DEFECT. Kalshi publishes four timestamps per market. For a tier-1 championship
future the venue sends the SAME legal backstop as both ``close_time`` and
``expiration_time``, and carries its real estimate in a third field,
``expected_expiration_time``, which until this ship was read by zero lines of our
code. So the card for the 2027 Super Bowl said it resolves 2029-02-13, and a US
Open market said it resolves at the end of September.

EVERY FIXTURE BELOW IS A REAL VENUE PAYLOAD, re-read from
``api.elections.kalshi.com/trade-api/v2/events/{ticker}?with_nested_markets=true``
on 2026-09-12 by the session that wrote this file — not inherited from a prior
report and not invented::

    event          legs   max close     max expiration   max expected
    KXWTA-26USO     31    2026-09-27    2026-09-27       2026-09-13
    KXSB-27         32    2029-02-13    2029-02-13       2027-02-14

Both are the pad shape (``close == expiration``) and in both the estimate is
EARLIER, which is the case #2644 is about.

WHY THE RULE IS GATED AND NOT A PREFERENCE. ``expected_expiration_time`` is a
prediction. On the settled cohort it scores 34/49 against ``close_time``'s 39/49
(CAL-P989, ``kalshi_resolution_window``'s docstring), so it must never displace a
REAL close. It is used only where ``close_time`` is itself a pad, and only via
``min()`` — on 13 measured markets the estimate is LATER than what we store, and a
blanket preference would push those the wrong way. Those two gates are what make
#1818's 39/49 untouched structurally rather than merely on a sample, and they are
what these tests are mostly about: the negative space, not the win.

CLOCK DISCIPLINE (gotcha #44). ``derive_resolution_window`` takes no clock and
every assertion here is on a returned datetime, never on "is it in the past". No
test in this file can flip with the wall clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.utils.kalshi_resolution_window import derive_resolution_window


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@dataclass
class Leg:
    """Mirrors ``KalshiMarket``'s three window fields."""

    close_time: Optional[datetime] = None
    expiration_time: Optional[datetime] = None
    expected_expiration_time: Optional[datetime] = None


@dataclass
class LegacyLeg:
    """A leg from before #2644 — no ``expected_expiration_time`` attribute AT ALL.

    Not the same thing as ``Leg(expected_expiration_time=None)``: this object does
    not carry the attribute, which is what an older caller or an older fake looks
    like. The derivation reads the field through ``getattr`` precisely so this
    cannot raise.
    """

    close_time: Optional[datetime] = None
    expiration_time: Optional[datetime] = None


# --- Real venue payloads, re-read 2026-09-12 -------------------------------

#: KXSB-27, Pro Football Champion 2027. 32 legs; the card said "2029".
SUPER_BOWL_27 = [
    Leg(
        _ts("2029-02-13T23:30:00Z"),
        _ts("2029-02-13T23:30:00Z"),
        _ts("2027-02-14T23:30:00Z"),
    ),
    Leg(
        _ts("2029-02-13T23:30:00Z"),
        _ts("2029-02-13T23:30:00Z"),
        _ts("2027-02-14T23:30:00Z"),
    ),
]

#: KXATP-26USO, US Open MEN'S singles winner. 48 legs. THE SHIP'S NAMED CARD:
#: production stores ``resolution_date = 2026-09-28 02:00`` — a fortnight after
#: the final — while the venue's estimate is 2026-09-14T05:00Z, the night the
#: men's final is played. This is the card that said "resolves within a month"
#: on the morning of the final.
US_OPEN_ATP = [
    Leg(
        _ts("2026-09-28T02:00:00Z"),
        _ts("2026-09-28T02:00:00Z"),
        _ts("2026-09-14T05:00:00Z"),
    ),
    Leg(
        _ts("2026-09-28T02:00:00Z"),
        _ts("2026-09-28T02:00:00Z"),
        _ts("2026-09-14T05:00:00Z"),
    ),
]

#: KXWTA-26USO, US Open women's singles. 31 legs; the card said end of September
#: for a tournament whose final is 2026-09-12/13.
US_OPEN_WTA = [
    Leg(
        _ts("2026-09-27T02:00:00Z"),
        _ts("2026-09-27T02:00:00Z"),
        _ts("2026-09-13T05:00:00Z"),
    ),
    Leg(
        _ts("2026-09-27T02:00:00Z"),
        _ts("2026-09-27T02:00:00Z"),
        _ts("2026-09-13T05:00:00Z"),
    ),
]

#: The #2660/#1818 shape: a REAL close well before the 14-day backstop. The
#: estimate exists but must be ignored, because close_time is a trading fact.
#: The estimate here sits just AFTER the close, which is what the venue actually
#: does on this shape (see the census in ``TestThePadGateIsAnInvariantNotAnObservation``).
SETTLED_PROP_WITH_ESTIMATE = [
    Leg(
        _ts("2026-09-01T22:54:02Z"),
        _ts("2026-09-15T16:40:00Z"),
        _ts("2026-09-02T00:00:00Z"),
    ),
]

#: SYNTHETIC, AND DELIBERATELY SO — labelled because every other fixture in this
#: file is a real venue payload and a reader must be able to tell them apart.
#: A real close (close < expiration) whose estimate is EARLIER than the close.
#: Census of 3,000 live venue markets (2026-09-12, statuses settled/closed/open):
#: 557 carry a real close and **0 of the 557** have an earlier estimate. So this
#: shape does not occur today. See the test class for why it is still pinned.
SYNTHETIC_REAL_CLOSE_WITH_EARLIER_ESTIMATE = [
    Leg(
        _ts("2026-09-01T22:54:02Z"),
        _ts("2026-09-15T16:40:00Z"),
        _ts("2026-08-30T00:00:00Z"),
    ),
]


class TestTheDefectIsFixed:
    """The two cards a reader complained about."""

    def test_super_bowl_27_stops_resolving_in_2029(self):
        w = derive_resolution_window(SUPER_BOWL_27)
        assert w.resolution_date == _ts("2027-02-14T23:30:00Z")
        assert w.resolution_date.year == 2027, "the whole point of #2644"
        assert w.used_expected_expiration is True

    def test_the_us_open_mens_final_card_stops_saying_a_fortnight_away(self):
        """The ship, on the exact card it was named for.

        Production stores 2026-09-28 for ``KXATP-26USO``. The men's final is
        played the night of 2026-09-13/14, and the venue says so.
        """
        w = derive_resolution_window(US_OPEN_ATP)
        assert w.resolution_date == _ts("2026-09-14T05:00:00Z")
        assert w.used_expected_expiration is True

    def test_us_open_womens_stops_resolving_at_the_end_of_september(self):
        w = derive_resolution_window(US_OPEN_WTA)
        assert w.resolution_date == _ts("2026-09-13T05:00:00Z")
        assert w.used_expected_expiration is True

    def test_the_backstop_column_is_preserved_unchanged(self):
        """No data loss: ``expiration_time`` still reproduces the old value.

        CAL-P061's 421/421 provenance reproduction depends on this, and #2644
        must not be the thing that breaks it.
        """
        assert (
            derive_resolution_window(SUPER_BOWL_27).expiration_time
            == _ts("2029-02-13T23:30:00Z")
        )
        assert (
            derive_resolution_window(US_OPEN_WTA).expiration_time
            == _ts("2026-09-27T02:00:00Z")
        )


class TestTheGatesThatProtect1818:
    """The negative space. These are the tests that matter most."""

    def test_a_real_close_is_never_displaced_by_the_estimate(self):
        """close < expiration means close_time is a trading fact. Hands off.

        This is the structural reason #1818's 39/49 cannot regress: the rule
        cannot even see a market whose close is real.
        """
        w = derive_resolution_window(SETTLED_PROP_WITH_ESTIMATE)
        assert w.resolution_date == _ts("2026-09-01T22:54:02Z")
        assert w.used_expected_expiration is False

    def test_an_estimate_that_is_later_never_moves_the_date_forward(self):
        """The 13-market hazard. ``min()`` is what covers it.

        A blanket preference for the estimate would push these later, into a
        future the venue has already contradicted.
        """
        legs = [
            Leg(
                _ts("2026-09-27T02:00:00Z"),
                _ts("2026-09-27T02:00:00Z"),
                _ts("2026-11-01T00:00:00Z"),
            )
        ]
        w = derive_resolution_window(legs)
        assert w.resolution_date == _ts("2026-09-27T02:00:00Z")
        assert w.used_expected_expiration is False

    def test_an_estimate_equal_to_the_pad_changes_nothing(self):
        """Strict ``<``. Equal dates are the same answer, so nothing "fired"."""
        legs = [
            Leg(
                _ts("2029-02-13T23:30:00Z"),
                _ts("2029-02-13T23:30:00Z"),
                _ts("2029-02-13T23:30:00Z"),
            )
        ]
        w = derive_resolution_window(legs)
        assert w.resolution_date == _ts("2029-02-13T23:30:00Z")
        assert w.used_expected_expiration is False

    def test_an_absent_estimate_is_no_opinion(self):
        """Gotcha #53: absence is not a value, and is not zero."""
        legs = [Leg(_ts("2029-02-13T23:30:00Z"), _ts("2029-02-13T23:30:00Z"), None)]
        w = derive_resolution_window(legs)
        assert w.resolution_date == _ts("2029-02-13T23:30:00Z")
        assert w.used_expected_expiration is False

    def test_a_leg_predating_the_field_does_not_raise(self):
        """``LegacyLeg`` has no such attribute. The ``getattr`` read is why."""
        legs = [LegacyLeg(_ts("2029-02-13T23:30:00Z"), _ts("2029-02-13T23:30:00Z"))]
        w = derive_resolution_window(legs)
        assert w.resolution_date == _ts("2029-02-13T23:30:00Z")
        assert w.used_expected_expiration is False

    def test_the_no_close_time_fallback_still_wins(self):
        """An event with no close at all falls back to the backstop, as before.

        #2644 must not quietly take over the fallback path — that path has its
        own flag and its own consumers.
        """
        legs = [Leg(None, _ts("2029-02-13T23:30:00Z"), _ts("2027-02-14T23:30:00Z"))]
        w = derive_resolution_window(legs)
        assert w.resolution_date == _ts("2029-02-13T23:30:00Z")
        assert w.used_expiration_fallback is True
        assert w.used_expected_expiration is False


class TestThePadGateIsAnInvariantNotAnObservation:
    """The ``close_max == expiration_max`` gate, and an honest note about it.

    MEASURED (2026-09-12, live venue, 1,000 markets each at status
    settled/closed/open — every one carrying all three timestamps)::

        status     real close (close<exp)   ...of which estimate < close
        settled            254                        0
        closed             303                        0
        open                 0                        -
        ------------------------------------------------------------
        total              557                        0

    So **no market with a real close currently carries an earlier estimate**, and
    deleting the pad gate changes nothing on today's data — a mutation of that
    gate survives against every venue-shaped fixture in this file. That is
    recorded rather than hidden.

    The gate is kept anyway, and pinned here with an openly synthetic fixture,
    because it is what makes #1818's protection STRUCTURAL. Without it the ship
    rests on "the venue never sends an earlier estimate on a real-close market" —
    an assumption about a third party's open-set payload that nothing on our side
    enforces and no alarm would catch. With it, a market whose close is a trading
    fact cannot move, whatever the venue starts sending.

    The same census sizes the ship: **992 of 1,000 open markets** are the pad
    shape with an earlier estimate, which is the population #2644 is about.
    """

    def test_a_real_close_survives_even_when_the_estimate_is_earlier(self):
        w = derive_resolution_window(SYNTHETIC_REAL_CLOSE_WITH_EARLIER_ESTIMATE)
        assert w.resolution_date == _ts("2026-09-01T22:54:02Z"), (
            "close_time is a trading fact and outranks the venue's guess. "
            "If this fails, the pad gate has been removed and #1818's 39/49 "
            "is no longer structurally protected."
        )
        assert w.used_expected_expiration is False


class TestAggregationAcrossLegs:
    def test_the_estimate_is_maxed_across_legs_like_the_others(self):
        """An event resolves when its LAST leg does — same aggregation as the rest."""
        legs = [
            Leg(
                _ts("2029-02-13T23:30:00Z"),
                _ts("2029-02-13T23:30:00Z"),
                _ts("2027-02-14T23:30:00Z"),
            ),
            Leg(
                _ts("2029-02-13T23:30:00Z"),
                _ts("2029-02-13T23:30:00Z"),
                _ts("2027-03-01T23:30:00Z"),
            ),
        ]
        w = derive_resolution_window(legs)
        assert w.resolution_date == _ts("2027-03-01T23:30:00Z")

    def test_a_partial_estimate_uses_the_legs_that_have_one(self):
        """A missing estimate on one leg is an absent field, not a veto."""
        legs = [
            Leg(_ts("2029-02-13T23:30:00Z"), _ts("2029-02-13T23:30:00Z"), None),
            Leg(
                _ts("2029-02-13T23:30:00Z"),
                _ts("2029-02-13T23:30:00Z"),
                _ts("2027-02-14T23:30:00Z"),
            ),
        ]
        w = derive_resolution_window(legs)
        assert w.resolution_date == _ts("2027-02-14T23:30:00Z")
        assert w.used_expected_expiration is True


class TestTheFieldTravelsFromTheVenuePayload:
    """A rule nothing feeds is inert. These guard the two hops that feed it."""

    def test_kalshi_market_parses_the_field(self):
        from app.services.kalshi_api import KalshiAPIService

        parsed = KalshiAPIService()._parse_market(
            {
                "ticker": "KXSB-27-KC",
                "event_ticker": "KXSB-27",
                "title": "Chiefs",
                "status": "active",
                "close_time": "2029-02-13T23:30:00Z",
                "expiration_time": "2029-02-13T23:30:00Z",
                "expected_expiration_time": "2027-02-14T23:30:00Z",
            }
        )
        assert parsed is not None
        assert parsed.expected_expiration_time == _ts("2027-02-14T23:30:00Z")

    def test_kalshi_market_tolerates_the_field_being_absent(self):
        from app.services.kalshi_api import KalshiAPIService

        parsed = KalshiAPIService()._parse_market(
            {
                "ticker": "KXSB-27-KC",
                "event_ticker": "KXSB-27",
                "title": "Chiefs",
                "status": "active",
                "close_time": "2029-02-13T23:30:00Z",
                "expiration_time": "2029-02-13T23:30:00Z",
            }
        )
        assert parsed is not None
        assert parsed.expected_expiration_time is None

    def test_a_parsed_market_drives_the_rule_end_to_end(self):
        """The real model, not a fake, through the real derivation."""
        from app.services.kalshi_api import KalshiAPIService

        svc = KalshiAPIService()
        markets = [
            svc._parse_market(
                {
                    "ticker": f"KXSB-27-{team}",
                    "event_ticker": "KXSB-27",
                    "title": team,
                    "status": "active",
                    "close_time": "2029-02-13T23:30:00Z",
                    "expiration_time": "2029-02-13T23:30:00Z",
                    "expected_expiration_time": "2027-02-14T23:30:00Z",
                }
            )
            for team in ("KC", "SF")
        ]
        w = derive_resolution_window(markets)
        assert w.resolution_date == _ts("2027-02-14T23:30:00Z")
        assert w.used_expected_expiration is True

    def test_the_sweeps_leg_carries_the_field(self):
        """The SECOND writer of ``resolution_date``.

        The poller is the first. If this leg type had not learned the field, the
        sweep would keep stamping the pad on every row it reaches (a NULL
        ``resolution_date``, or one the poller has not re-polled), and the two
        writers of one column would be applying different rules.
        """
        from app.tasks.kalshi_resolution_sweep import _Leg

        legs = [
            _Leg(
                _ts("2029-02-13T23:30:00Z"),
                _ts("2029-02-13T23:30:00Z"),
                _ts("2027-02-14T23:30:00Z"),
            )
        ]
        w = derive_resolution_window(legs)
        assert w.resolution_date == _ts("2027-02-14T23:30:00Z")
        assert w.used_expected_expiration is True

    def test_the_sweeps_leg_still_defaults_the_field(self):
        """Every other ``_Leg(...)`` construction site stays valid."""
        from app.tasks.kalshi_resolution_sweep import _Leg

        leg = _Leg(_ts("2029-02-13T23:30:00Z"), _ts("2029-02-13T23:30:00Z"))
        assert leg.expected_expiration_time is None


class TestTheRuleStillHasAWriterOnTheAppThatRunsIt:
    """CAL-P1134. Who CALLS the rule, and which Heroku app runs them.

    Everything above proves the derivation is right. Neither this file nor any
    other asserted the thing that decides whether the ship is LIVE: that some
    task which carries the rule actually runs, on the app the reader's rows are
    written by. Notice 48 is the whole reason — since the 2026-09-11 heavy split,
    ``bainluck-heavy`` does not follow master, so a writer on the ``heavy`` queue
    can sit months behind while every test here stays green.

    THE WRITER MAP, measured 2026-09-12 17:5xZ by AST-scanning ``app/`` (below)
    and reading ``HEAVY_TASKS`` / the beat literals::

        call site                      entry task                       queue      app     fires #2644?
        kalshi.py `_poll_kalshi_markets`
                                       poll_kalshi_markets              heavy      heavy   code is STALE
        kalshi.py `_create_settled_market`
                                       backfill_settled_gap_creation    background main    no (see below)
        kalshi_resolution_sweep.py `handle` (in `run_backfill`)
                                       settle_kalshi_recent_finals      realtime   main    no (see below)
                                       "                                background main    YES, 04:20Z daily

    Two of those three main-app arms carry the rule but are BARRED FROM FIRING IT
    STRUCTURALLY, which is why they are not a substitute for the sweep:
    ``settle_kalshi_recent_finals``' cohort is recently-final game legs, whose
    ``close_time`` is a genuine close, so the pad gate (``close == expiration``)
    is false by construction; and ``backfill_settled_gap_creation`` inserts
    ``status="resolved"`` rows for markets that already settled, whose close has
    likewise collapsed to the settlement instant.

    So ``sweep_kalshi_resolution_window`` is the ONLY arm that can move a
    pad-shaped row on the main app. That is a single point of failure worth one
    assertion: move it onto ``heavy`` and #2644 goes inert on production, silently,
    with this file green.
    """

    #: Every call site of the rule in ``app/``, as ``(module, enclosing function)``.
    #: A set, not a count, so a new writer names itself in the failure.
    KNOWN_CALL_SITES = {
        ("app/tasks/kalshi.py", "_poll_kalshi_markets"),
        ("app/tasks/kalshi.py", "_create_settled_market"),
        ("app/tasks/kalshi_resolution_sweep.py", "handle"),
    }

    @staticmethod
    def _call_sites():
        """AST-scan ``app/`` for CALLS of the rule — not mentions of its name.

        Deliberately not a text grep: the imports, this docstring and the module's
        own prose all spell the identifier, so a substring scan would stay true
        after the last real call site was deleted (the vacuous-guard shape).
        """
        import ast
        import pathlib

        import app as _app

        root = pathlib.Path(_app.__file__).resolve().parent
        sites = set()
        for path in sorted(root.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text())
            except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
                continue
            rel = f"app/{path.relative_to(root).as_posix()}"
            stack: list[str] = []

            class _V(ast.NodeVisitor):
                def visit_FunctionDef(self, node):
                    stack.append(node.name)
                    self.generic_visit(node)
                    stack.pop()

                visit_AsyncFunctionDef = visit_FunctionDef

                def visit_Call(self, node):
                    func = node.func
                    name = (
                        func.id
                        if isinstance(func, ast.Name)
                        else getattr(func, "attr", None)
                    )
                    if name == "derive_resolution_window":
                        sites.add((rel, stack[-1] if stack else "<module>"))
                    self.generic_visit(node)

            _V().visit(tree)
        return sites

    def test_every_writer_of_the_rule_is_accounted_for(self):
        """A new caller must state which app runs it, in the map above.

        This is not tidiness. The reach of #2644 is not a property of the
        derivation — it is a property of the set of tasks that call it and the
        queues those run on. A fourth call site added without a thought about
        routing is how the ship quietly becomes partial.
        """
        found = self._call_sites()
        assert found == self.KNOWN_CALL_SITES, (
            "the set of callers of `derive_resolution_window` changed.\n"
            f"  added:   {sorted(found - self.KNOWN_CALL_SITES)}\n"
            f"  removed: {sorted(self.KNOWN_CALL_SITES - found)}\n"
            "Update KNOWN_CALL_SITES *and* the writer map in this class's "
            "docstring, naming the entry task, its queue and its Heroku app. "
            "A caller on the `heavy` queue does not ship until a "
            "`bainluck-heavy` release carries it (notice 48)."
        )

    def test_the_only_arm_that_can_fire_the_rule_stays_off_the_heavy_queue(self):
        """``sweep_kalshi_resolution_window`` must keep running on the main app.

        Two assertions because there are two independent ways to move it, and
        each is a real edit someone could make:

        1. adding it to ``HEAVY_TASKS`` — the routing loop then rewrites its beat
           entry's queue regardless of the literal, so the source would still
           read ``background``;
        2. hand-editing the beat literal to ``heavy``.
        """
        from app.tasks import HEAVY_TASKS, celery_app

        assert "app.tasks.sweep_kalshi_resolution_window" not in HEAVY_TASKS, (
            "the 04:20Z resolution sweep moved onto the `heavy` queue. It is the "
            "only writer that can fire #2644's pad rule on the main app, and "
            "`bainluck-heavy` does not follow master (notice 48) — this makes the "
            "ship inert on production with every other test in this file green."
        )

        entry = celery_app.conf.beat_schedule["sweep-kalshi-resolution-window"]
        assert entry["options"]["queue"] != "heavy", (
            "the sweep's beat entry now pins the `heavy` queue. See above: this "
            "takes #2644 off the app that serves the reader's rows."
        )
