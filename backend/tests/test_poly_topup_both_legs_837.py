"""#837 — both legs of a live Polymarket binary get their own book, and the
``No`` leg is never handed the ``Yes`` one.

WHY THIS FILE EXISTS.  ``topup_outcome_clob_tokens`` built its work set as
``addressable[cid] = (market_id, outcome_id)`` — a scalar value under a key that
is NOT unique across our rows.  Our outcome rows store a Polymarket condition id
with a ``_yes`` / ``_no`` suffix, so both legs of a two-way market map to one
key through ``condition_id_of``, and the second assignment overwrote the first.

Two consequences:

1. **HALF THE LEGS ARE NEVER ASKED ABOUT, AND NOT "NEXT RECYCLE".**  The caller
   orders by ``FuturesOutcome.id`` and the ``_no`` row is minted second, so the
   ``_no`` leg wins every collision and the ``_yes`` leg is never subscribed.
   Nor is it retried: once the survivor's token is stored, the stored-shrink
   drops the whole condition id from the ask, so the sibling is unreachable for
   good.

2. 🔴 **AND THE SURVIVING LEG CAN BE THE INVERTED ONE.**  ``token_for_outcome``
   asked ``yes_token_of`` first and let its answer win.  That function answers
   "which token is the YES side of this MARKET" — it cannot see which of our
   rows is asking.  So on a market whose Gamma ``outcomes`` are literally
   ``["Yes","No"]``, the surviving ``_no`` row is handed token index 0.  Not a
   stale leg: the Q489 *inversion*, ``p`` where the truth is ``1-p``.

⚠️ **LATENT, NOT LIVE, AND THIS FILE FIRST CLAIMED OTHERWISE.**  Measured on
production and Gamma 2026-09-17 09:2x-09:5xZ:

* 385 condition ids carry an outcome row on a ``status='live'`` event, **384 of
  them holding exactly two of our rows** — the collapsing shape is essentially
  the whole binary population.
* **All 385 of those markets already carry market-level ``clob_token_ids``**, so
  ``polymarket_ws`` excludes them from ``outcome_topup_targets`` and attributes
  both legs positionally through the Q489 zip.  This function never sees them.
* Of the **235** slate markets that DO lack market-level tokens — the population
  it is handed — exactly **38** condition ids are pairs, and **every one sits on
  a ``status='scheduled'`` event older than ``STALE_EVENT_HOURS``**, which #837's
  own filter drops before the ask is built.

So the reach is zero on both arms today, including for the two ``["Yes","No"]``
rows below: they are attributed correctly by the market-level zip and were never
wrong on a screen.  An earlier version of this docstring reported "158 of 769
legs filled -> 316" and called those two rows live inversions; **both claims are
withdrawn** — the first replays this function's attribution over rows it is
never handed, the second reads a latent branch as a live one.

🪤 **THE TRAP THAT PRODUCED THEM.**  Two metadata keys answer "does this leg have
a book": ``clob_token_ids`` (market level, stamped by ingest, consumed by the
Q489 zip) and ``clob_yes_token_by_outcome`` (per outcome, written here).
Counting coverage on the second alone reads **0** across the entire binary
population and says "live legs are starved", when they are served by the first.
Which key a population is keyed on decides whether this function can reach it.

**WHY IT IS STILL PINNED.**  The reachable path is live — 97 of those 235 slate
markets hold outcome-level tokens today — and the only thing keeping the pair
shape off it is that ingest currently stamps a market-level pair on every binary
it sees.  That is an upstream property, not an invariant this module may assume.

THE FIX is two lines of shape and one of order: the work set maps a condition id
to a LIST of our rows, every one of them is attributed, and
``token_for_outcome`` tries OUR OWN ROW'S NAME before falling back to
``yes_token_of``.  Nothing that is correct today moves — the name path only
fires on an exact, unique match against Gamma's own outcome list, and where it
fires the old order either agreed with it or was the inversion above.

Specimens are verbatim from that read, Gamma answers included, so the fixture
cannot drift into a friendlier shape than the one production served.
"""

import pytest
from sqlalchemy.sql.dml import Update

import app.tasks.polymarket_token_topup as topup_mod
from app.tasks.polymarket_token_topup import (
    OUTCOME_TOKEN_METADATA_KEY,
    token_for_outcome,
    topup_outcome_clob_tokens,
)

pytestmark = pytest.mark.asyncio


# ── SPECIMEN A: the ordinary pair ────────────────────────────────────────────
# Production 2026-09-17 09:2xZ. Event 15313731, market 61241839, both rows live.
# Gamma: "M15 Monastir: Samuel Vincent Ruggeri vs Daniel Domingos",
# outcomes the contenders themselves, outcomePrices ["0.895","0.105"].
PAIR_CONDITION = "0x053846787086f17e892647b6fcddfe81780fc11d7f05a8607e7f8eb3b5114e75"
PAIR_MARKET_ID = 61241839
PAIR_YES_OUTCOME_ID = 230449323
PAIR_YES_NAME = "Samuel Vincent Ruggeri"
PAIR_NO_OUTCOME_ID = 230449324
PAIR_NO_NAME = "Daniel Domingos"
PAIR_GAMMA_OUTCOMES = ["Samuel Vincent Ruggeri", "Daniel Domingos"]
PAIR_TOKEN_0 = (
    "67020722636652289524494152093222023225386529899143943619819210677936936056529"
)
PAIR_TOKEN_1 = (
    "80614858358297311731201539126885547765652131264582639706757301485275192155095"
)

# ── SPECIMEN B: the inversion ────────────────────────────────────────────────
# Production 2026-09-17 09:2xZ. Event live, market 61263632, both rows live.
# Gamma: "M25 Zlatibor, Main Draw: Completed Match: Marko Knezevic vs Drazen
# Petrovic", outcomes ["Yes","No"], outcomePrices ["0.9995","0.0005"].
INVERT_CONDITION = "0xd7a5b002d2205d962522d47b82630b84c18d7b50122ad6b9632dbeec2f533487"
INVERT_MARKET_ID = 61263632
INVERT_YES_OUTCOME_ID = 230547838
INVERT_NO_OUTCOME_ID = 230547839
INVERT_GAMMA_OUTCOMES = ["Yes", "No"]
INVERT_YES_TOKEN = (
    "103954422285662835757809467285124379986523141220864038720685738004177956463713"
)
INVERT_NO_TOKEN = (
    "84400071260534812843891346994320229832194833393636810144306466629406668619597"
)

assert INVERT_YES_OUTCOME_ID < INVERT_NO_OUTCOME_ID, (
    "the caller orders by FuturesOutcome.id and the collision was won by "
    "whichever row came LAST; if these ever sort the other way the inversion "
    "specimen stops reproducing the defect it was drawn for"
)
assert PAIR_YES_OUTCOME_ID < PAIR_NO_OUTCOME_ID, (
    "same ordering fact, for the pair specimen"
)


class _FakeMarket:
    def __init__(self, condition_id, clob_token_ids, outcomes):
        self.condition_id = condition_id
        self.clob_token_ids = list(clob_token_ids)
        self.outcomes = list(outcomes)


class _FakeService:
    def __init__(self, markets):
        self._markets = markets
        self.asked: list[list[str]] = []
        self.closed = False

    async def get_markets_by_conditions(self, condition_ids, **_kw):
        self.asked.append(list(condition_ids))
        wanted = set(condition_ids)
        return [m for m in self._markets if m.condition_id in wanted]

    async def close(self):
        self.closed = True


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _Session:
    """Answers the two SELECTs this function makes, in the order it makes them.

    Stored metadata first — four columns wide since #837, ``(market_id,
    metadata, commence_time, status)`` — then the outcome-name read. Both are
    Selects, so a stub that answered them alike would hand market metadata to
    the name parser and every name lookup would come back empty, which on this
    module's fail-open shape reads as a green pass on the degraded path.
    """

    def __init__(self, stored_rows=(), name_rows=()):
        self.updates: list = []
        self._queue = [
            ("stored", [tuple(r) + (None,) * (4 - len(tuple(r))) for r in stored_rows]),
            ("names", list(name_rows)),
        ]

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            self.updates.append(stmt)
            return _Rows([])
        _kind, rows = self._queue.pop(0) if self._queue else ("names", [])
        return _Rows(rows)


@pytest.fixture(autouse=True)
def _pinned_window(monkeypatch):
    """Hold the resuming window at the front.

    Nothing in this file is about where the window starts; a live Redis would
    make these pass or fail on what an earlier run left in the key.
    """

    async def _front():
        return None

    async def _discard(_cursor):
        return None

    monkeypatch.setattr(topup_mod, "load_topup_cursor", _front)
    monkeypatch.setattr(topup_mod, "save_topup_cursor", _discard)


def _pair_targets():
    """Exactly the caller's shape and ORDER: ``order_by(FuturesOutcome.id)``."""
    return [
        (PAIR_MARKET_ID, PAIR_YES_OUTCOME_ID, f"{PAIR_CONDITION}_yes"),
        (PAIR_MARKET_ID, PAIR_NO_OUTCOME_ID, f"{PAIR_CONDITION}_no"),
    ]


def _pair_names():
    return [
        (PAIR_YES_OUTCOME_ID, PAIR_YES_NAME),
        (PAIR_NO_OUTCOME_ID, PAIR_NO_NAME),
    ]


def _invert_targets():
    return [
        (INVERT_MARKET_ID, INVERT_YES_OUTCOME_ID, f"{INVERT_CONDITION}_yes"),
        (INVERT_MARKET_ID, INVERT_NO_OUTCOME_ID, f"{INVERT_CONDITION}_no"),
    ]


def _invert_names():
    return [(INVERT_YES_OUTCOME_ID, "Yes"), (INVERT_NO_OUTCOME_ID, "No")]


class TestBothLegsOfOneConditionIdAreReached:
    async def test_both_rows_get_their_own_token(self):
        """THE DEFECT ITSELF — 384 of 385 live condition ids were shaped like this.

        One Gamma answer carries both books. Before this fix the scalar work set
        kept only the ``_no`` row and the ``_yes`` row was never subscribed at
        all, so a reader watching this match saw Domingos tick live and Ruggeri
        frozen on the 120 s poll.
        """
        service = _FakeService(
            [
                _FakeMarket(
                    PAIR_CONDITION,
                    [PAIR_TOKEN_0, PAIR_TOKEN_1],
                    PAIR_GAMMA_OUTCOMES,
                )
            ]
        )
        session = _Session(name_rows=_pair_names())

        filled = await topup_outcome_clob_tokens(
            session, _pair_targets(), service=service
        )

        assert filled[PAIR_YES_OUTCOME_ID] == (PAIR_MARKET_ID, PAIR_TOKEN_0)
        assert filled[PAIR_NO_OUTCOME_ID] == (PAIR_MARKET_ID, PAIR_TOKEN_1)

    async def test_one_condition_id_is_asked_once_for_two_legs(self):
        """The second leg costs no extra request, which is why the cap did not move.

        Gamma is billed one query parameter per condition id, so the sibling is
        answered by a response the pass was already paying for. If this ever
        starts asking twice, the ask has been re-billed in the wrong unit.
        """
        service = _FakeService(
            [
                _FakeMarket(
                    PAIR_CONDITION,
                    [PAIR_TOKEN_0, PAIR_TOKEN_1],
                    PAIR_GAMMA_OUTCOMES,
                )
            ]
        )
        session = _Session(name_rows=_pair_names())

        await topup_outcome_clob_tokens(session, _pair_targets(), service=service)

        assert service.asked == [[PAIR_CONDITION]]

    async def test_both_legs_are_written_under_one_market(self):
        """Persisted, not merely returned — a restart must not re-ask for them."""
        service = _FakeService(
            [
                _FakeMarket(
                    PAIR_CONDITION,
                    [PAIR_TOKEN_0, PAIR_TOKEN_1],
                    PAIR_GAMMA_OUTCOMES,
                )
            ]
        )
        session = _Session(name_rows=_pair_names())

        await topup_outcome_clob_tokens(session, _pair_targets(), service=service)

        assert len(session.updates) == 1, (
            "both legs live on one FuturesMarket row, so one nested merge "
            "carries them; two writes would mean the second overwrote the first"
        )

    async def test_the_sibling_is_still_asked_once_its_twin_is_stored(self):
        """PERMANENCE, which is what made this a coverage cap and not a lag.

        The stored-shrink used to drop a whole condition id as soon as ONE of
        its rows was known, so the sibling was never reachable again. Pass two,
        with the ``_no`` leg banked from pass one.
        """
        service = _FakeService(
            [
                _FakeMarket(
                    PAIR_CONDITION,
                    [PAIR_TOKEN_0, PAIR_TOKEN_1],
                    PAIR_GAMMA_OUTCOMES,
                )
            ]
        )
        session = _Session(
            stored_rows=[
                (
                    PAIR_MARKET_ID,
                    {
                        OUTCOME_TOKEN_METADATA_KEY: {
                            str(PAIR_NO_OUTCOME_ID): PAIR_TOKEN_1
                        }
                    },
                )
            ],
            name_rows=_pair_names(),
        )

        filled = await topup_outcome_clob_tokens(
            session, _pair_targets(), service=service
        )

        assert service.asked == [[PAIR_CONDITION]], (
            "the unstored sibling keeps its condition id in the ask"
        )
        assert filled[PAIR_YES_OUTCOME_ID] == (PAIR_MARKET_ID, PAIR_TOKEN_0)
        assert filled[PAIR_NO_OUTCOME_ID] == (PAIR_MARKET_ID, PAIR_TOKEN_1), (
            "and the stored twin stays subscribed: the return value IS the "
            "socket's subscription list"
        )

    async def test_a_fully_stored_pair_asks_gamma_nothing(self):
        """The shrink still shrinks. Per row, so it needs BOTH before it fires."""
        service = _FakeService([])
        session = _Session(
            stored_rows=[
                (
                    PAIR_MARKET_ID,
                    {
                        OUTCOME_TOKEN_METADATA_KEY: {
                            str(PAIR_YES_OUTCOME_ID): PAIR_TOKEN_0,
                            str(PAIR_NO_OUTCOME_ID): PAIR_TOKEN_1,
                        }
                    },
                )
            ],
            name_rows=_pair_names(),
        )

        filled = await topup_outcome_clob_tokens(
            session, _pair_targets(), service=service
        )

        assert service.asked == []
        assert filled[PAIR_YES_OUTCOME_ID] == (PAIR_MARKET_ID, PAIR_TOKEN_0)
        assert filled[PAIR_NO_OUTCOME_ID] == (PAIR_MARKET_ID, PAIR_TOKEN_1)


class TestTheNoLegIsNeverGivenTheYesBook:
    async def test_the_no_row_is_subscribed_to_the_no_book(self):
        """🔴 THE INVERSION, on a real row that carries its shape.

        Gamma ``outcomes ["Yes","No"]``, ``outcomePrices ["0.9995","0.0005"]``.
        The old order hands our ``No`` row token index 0: a leg that would read
        99.95% where its own truth is 0.05%.

        This row is NOT inverted on production — its market carries
        market-level ``clob_token_ids``, so the socket attributes it through the
        Q489 zip and this function is never asked. It is the specimen because it
        is the loudest real instance of the shape, not because it was wrong on a
        screen; the module docstring carries the reach measurement.
        """
        service = _FakeService(
            [
                _FakeMarket(
                    INVERT_CONDITION,
                    [INVERT_YES_TOKEN, INVERT_NO_TOKEN],
                    INVERT_GAMMA_OUTCOMES,
                )
            ]
        )
        session = _Session(name_rows=_invert_names())

        filled = await topup_outcome_clob_tokens(
            session, _invert_targets(), service=service
        )

        assert filled[INVERT_NO_OUTCOME_ID] == (INVERT_MARKET_ID, INVERT_NO_TOKEN)

    async def test_the_yes_row_still_takes_the_yes_book(self):
        """The control for the assertion above: the fix must not swap the pair."""
        service = _FakeService(
            [
                _FakeMarket(
                    INVERT_CONDITION,
                    [INVERT_YES_TOKEN, INVERT_NO_TOKEN],
                    INVERT_GAMMA_OUTCOMES,
                )
            ]
        )
        session = _Session(name_rows=_invert_names())

        filled = await topup_outcome_clob_tokens(
            session, _invert_targets(), service=service
        )

        assert filled[INVERT_YES_OUTCOME_ID] == (INVERT_MARKET_ID, INVERT_YES_TOKEN)

    async def test_two_legs_of_one_binary_never_share_a_token(self):
        """The shape-level statement, independent of which token is which.

        Two rows on one asset id is the bug wearing either orientation: both
        would render the same number for opposite questions.
        """
        service = _FakeService(
            [
                _FakeMarket(
                    INVERT_CONDITION,
                    [INVERT_YES_TOKEN, INVERT_NO_TOKEN],
                    INVERT_GAMMA_OUTCOMES,
                )
            ]
        )
        session = _Session(name_rows=_invert_names())

        filled = await topup_outcome_clob_tokens(
            session, _invert_targets(), service=service
        )

        tokens = [token for _mid, token in filled.values()]
        assert len(set(tokens)) == len(tokens) == 2


class TestWhatMustNotChange:
    async def test_a_field_outcome_named_for_a_contender_still_takes_the_yes_token(
        self,
    ):
        """Q500's three-way soccer case, which is the reason the Yes path exists.

        Our row is named for the team; Gamma's outcomes are ``["Yes","No"]``, so
        the name matches nothing and the fallback answers exactly as before.
        """
        market = _FakeMarket("0xfa91ccd0", ["yes-tok", "no-tok"], ["Yes", "No"])

        assert token_for_outcome(market, "Wolfsberger AC") == "yes-tok"

    async def test_a_head_to_head_still_matches_our_own_name(self):
        """#6617's case, unchanged: no "Yes" anywhere, attribution is by name."""
        market = _FakeMarket(
            "0xc72411a3",
            ["tigers-tok", "jays-tok"],
            ["Detroit Tigers", "Toronto Blue Jays"],
        )

        assert token_for_outcome(market, "Toronto Blue Jays") == "jays-tok"
        assert token_for_outcome(market, "Detroit Tigers") == "tigers-tok"

    async def test_an_unreadable_name_falls_back_rather_than_guessing(self):
        """A name we could not read leaves the row on the Yes path, as before."""
        market = _FakeMarket("0xfa91ccd0", ["yes-tok", "no-tok"], ["Yes", "No"])

        assert token_for_outcome(market, None) == "yes-tok"
        assert token_for_outcome(market, "   ") == "yes-tok"

    async def test_a_name_matching_twice_refuses_rather_than_taking_the_first(self):
        """Position is never the tiebreak. No Yes to fall back to, so: nothing."""
        market = _FakeMarket("0xdupe", ["a", "b"], ["Draw", "Draw"])

        assert token_for_outcome(market, "Draw") is None

    async def test_a_market_with_no_tokens_yields_nothing(self):
        market = _FakeMarket("0xempty", [], ["Yes", "No"])

        assert token_for_outcome(market, "No") is None

    async def test_a_name_that_only_prefixes_gammas_is_refused(self):
        """EQUALITY, NOT PREFIX — and this is a live cohort, not a hypothetical.

        34 of the 385 measured live condition ids are totals markets where our
        rows are named ``Over`` / ``Under`` and Gamma's carry the line:
        ``["Over 2.5","Under 2.5"]``. ``Over`` prefixes exactly one of those, so
        a matcher relaxed to ``startswith`` would fill 68 more legs — and would
        attribute whatever line Gamma is quoting to a row we never checked the
        line of. Our own row does not record which total it was minted for, so
        the agreement is unverifiable from here and the refusal stands until
        something measures it. Reaching this cohort is #837's next question, not
        a matcher relaxation.
        """
        market = _FakeMarket("0x0aed5803", ["over-tok", "under-tok"], ["Over 2.5", "Under 2.5"])

        assert token_for_outcome(market, "Over") is None
        assert token_for_outcome(market, "Under") is None

    async def test_an_exact_match_on_a_lined_name_is_still_taken(self):
        """The control for the refusal above: equality is not being weakened."""
        market = _FakeMarket("0x0aed5803", ["over-tok", "under-tok"], ["Over 2.5", "Under 2.5"])

        assert token_for_outcome(market, "Under 2.5") == "under-tok"

    async def test_a_stale_event_drops_both_of_its_legs(self):
        """The #837 age filter is per row now; it must still drop the whole pair.

        Dropping one leg of a dead game and keeping the other would be the
        corpse-in-the-ask defect back at half strength.
        """
        from datetime import datetime, timedelta, timezone

        long_dead = datetime.now(timezone.utc) - timedelta(days=30)
        service = _FakeService(
            [
                _FakeMarket(
                    PAIR_CONDITION,
                    [PAIR_TOKEN_0, PAIR_TOKEN_1],
                    PAIR_GAMMA_OUTCOMES,
                )
            ]
        )
        session = _Session(
            stored_rows=[(PAIR_MARKET_ID, None, long_dead, "scheduled")],
            name_rows=_pair_names(),
        )

        filled = await topup_outcome_clob_tokens(
            session, _pair_targets(), service=service
        )

        assert service.asked == []
        assert filled == {}

    async def test_the_cap_is_still_counted_in_condition_ids(self):
        """``max_outcomes`` bounds the REQUEST, and the request is per condition id.

        A cap re-counted in legs would halve the ask for no reason — the sibling
        rides a response already being paid for. One condition id, cap of one,
        two legs out.
        """
        service = _FakeService(
            [
                _FakeMarket(
                    PAIR_CONDITION,
                    [PAIR_TOKEN_0, PAIR_TOKEN_1],
                    PAIR_GAMMA_OUTCOMES,
                )
            ]
        )
        session = _Session(name_rows=_pair_names())

        filled = await topup_outcome_clob_tokens(
            session, _pair_targets(), service=service, max_outcomes=1
        )

        assert len(filled) == 2
