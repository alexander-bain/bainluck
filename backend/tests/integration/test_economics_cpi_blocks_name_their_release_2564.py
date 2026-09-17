"""#2564: the /economics CPI card stops printing three decades as three blocks headed `Dec`.

Read off `GET /api/economics` at 2026-09-17 09:25:34Z and joined to
`futures_markets` by the `market_id` each block already carries:

    heading rendered        the market actually behind it              resolves
    Sep                     Argentina Monthly Inflation - September     2026-10-13
    Sep                     September Inflation US - Monthly            2026-10-15
    Dec                     US headline CPI inflation in December 2036  2037-02-01
    Dec                     US headline CPI inflation in December 2034  2035-02-01
    Dec                     US headline CPI inflation in December 2030  2031-02-01
    South Korea Annual I    South Korea Annual Inflation 2026           2026-12-31

The issue reads this as "repeats months out of order" and native's iPad walk as
"December repeated three times with byte-identical values". Neither is what is
happening. The months are not out of order and December is not repeated: the
label discarded the YEAR, so three markets a decade apart — carrying different
distributions, resolving in 2031, 2035 and 2037 — collapsed onto four
characters. It discarded the COUNTRY too, so Argentina's September inflation
wore a month slot on a card titled *CPI releases*, and its no-month fallback cut
`m.name[:20]` mid-word into `South Korea Annual I`.

THE SECOND DEFECT IS NOT VISIBLE IN ANY RENDER, AND IT IS THE BIGGER ONE. The
query feeding this page carries no `ORDER BY` and the list is cut
`cpi_releases[:6]`, so which six of 56 candidates a reader sees was decided by
row order. That is why comment 3 reports "a reader cannot reach Oct or Nov at
all": the next actual print (September CPI, 2026-10-14) and every October and
November market lost their slots to three markets from the 2030s — each of which
was then badged `NEXT`.

What this file pins:

  1. the specimens REPRODUCE the defect under the old derivation, which is
     inlined here as `_old_label`. Every other assertion is about behaviour that
     did not exist before this ship, so without this class "it fails before the
     fix" would only ever be an ImportError;
  2. the label keeps the year, and the three Dec markets therefore get three
     DISTINCT labels. Asserted as distinctness, not as three string equalities:
     a mutant returning `m.name` satisfies the equalities' intent and is not
     what shipped;
  3. the blocks are ordered by the release they price, and the slice therefore
     SELECTS. Pinned by naming the three markets that must be absent, not only
     the six that must be present — an ordering change that merely reshuffled
     the same six would satisfy a presence-only assertion;
  4. `upcoming` IS STILL TRUE ON EVERY BLOCK. This is the load-bearing control,
     and it is a control over a surface this lane does not own: iOS gates the
     whole CPI section on `releases.filter { $0.upcoming == true }` and then
     `if !upcoming.isEmpty`, and draws its section count from the same filter.
     Narrowing that field to the single next release — the obvious way to fix
     the badge — would cut native's card row from six cards to one. The badge
     reads `is_next` instead, and if a later edit "tidies" the two fields into
     one, this test is what says no;
  5. exactly one block claims to be next, and it is the soonest one;
  6. the wiring: that the sort happens BEFORE the `[:6]`, by source scan with an
     anti-strawman control. Every assertion in 3 passes on a payload of six
     markets whether or not the slice is downstream of the sort.

Prices are plausible rather than stored — this ship moves no number, and the
`brackets` a block carries are built by helpers that are not being changed.
Names, ids and resolution dates are the production rows, read by `db-query` in
the same minute as the payload above.
"""

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from app.routes import economics as econ
from app.routes.economics import _cpi_release_label, _cpi_release_sort_key

from .test_route_economics import _market, _outcome, _query_result


# --- The production specimens ----------------------------------------------
# (market_id, name, resolution_date) exactly as stored.

DEC_2036 = (57774192, "US headline CPI inflation in December 2036", "2037-02-01")
DEC_2034 = (57774198, "US headline CPI inflation in December 2034", "2035-02-01")
DEC_2030 = (57774209, "US headline CPI inflation in December 2030", "2031-02-01")
ARGENTINA = (60760395, "Argentina Monthly Inflation - September", "2026-10-13")
US_SEP = (60760502, "September Inflation US - Monthly", "2026-10-15")
SOUTH_KOREA = (128704, "South Korea Annual Inflation 2026", "2026-12-31")

# The three that LOST their slots to the markets from the 2030s. `CPI in
# September` is the next actual US print; October and November are the two
# months comment 3 reports a reader cannot reach.
US_SEP_CPI = (364212, "CPI in September", "2026-10-14")
US_OCT_CPI = (363921, "CPI in October", "2026-11-10")
US_NOV_CPI = (363886, "CPI in November", "2026-12-10")

THE_2030S = {DEC_2030[0], DEC_2034[0], DEC_2036[0]}


def _old_label(name: str) -> str:
    """The derivation this ship replaces, verbatim from `economics.py`."""
    match = re.search(
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\b",
        name or "",
        re.IGNORECASE,
    )
    return match.group(0).title()[:3] if match else name[:20]


def _at(day: str) -> datetime:
    return datetime.fromisoformat(day).replace(tzinfo=timezone.utc)


def _cpi_market(spec, *, source="kalshi"):
    """A CPI market the route's inflation branch will build a block from.

    Three brackets, none extreme, so `should_exclude_from_featured` keeps it and
    `len(outcomes) >= 3` is satisfied. No `above` rung, so the branch takes the
    partition path rather than the cumulative one — which is the path all six
    production specimens take.
    """
    market_id, name, resolves = spec
    return _market(
        market_id=market_id,
        name=name,
        external_id=f"kxcpi-{market_id}",
        source=source,
        resolution_date=_at(resolves),
        outcomes=[
            _outcome("2.0 to 2.2%", 0.45, outcome_id=market_id * 10, rank=1),
            _outcome("2.3 to 2.5%", 0.33, outcome_id=market_id * 10 + 1, rank=2),
            _outcome("2.6%+", 0.22, outcome_id=market_id * 10 + 2, rank=3),
        ],
    )


ALL_NINE = [
    DEC_2036, DEC_2034, DEC_2030, ARGENTINA, US_SEP, SOUTH_KOREA,
    US_SEP_CPI, US_OCT_CPI, US_NOV_CPI,
]


async def _blocks(client, mock_db, specs=None):
    mock_db.execute.return_value = _query_result(
        [_cpi_market(s) for s in (specs if specs is not None else ALL_NINE)]
    )
    body = (await client.get("/api/economics")).json()
    return body["themes"]["inflation"]["cpi_releases"]


class TestTheDefectTheseSpecimensReproduce:
    """The old derivation, run over the production names."""

    def test_three_decades_collapsed_onto_one_label(self):
        assert [_old_label(n) for _, n, _ in (DEC_2036, DEC_2034, DEC_2030)] == [
            "Dec", "Dec", "Dec",
        ]

    def test_argentina_reached_the_card_as_a_bare_month(self):
        assert _old_label(ARGENTINA[1]) == "Sep"
        assert _old_label(US_SEP[1]) == "Sep"

    def test_the_no_month_fallback_cut_mid_word(self):
        assert _old_label(SOUTH_KOREA[1]) == "South Korea Annual I"

    def test_the_old_month_pattern_also_matched_words_that_are_not_months(self):
        # `\b(Mar|May|...)\w*\b` accepts any word that merely starts like a
        # month. Not a production specimen — the reason the replacement is
        # anchored rather than copied.
        assert _old_label("Maybe inflation rises in 2027") == "May"
        assert _old_label("Marginal CPI change 2026") == "Mar"


class TestTheLabel:
    def test_keeps_the_year_so_the_dec_family_is_three_labels_not_one(self):
        labels = [_cpi_release_label(n) for _, n, _ in (DEC_2036, DEC_2034, DEC_2030)]
        assert len(set(labels)) == 3, labels
        assert labels == ["Dec 2036", "Dec 2034", "Dec 2030"]

    def test_a_month_with_no_year_is_still_just_the_month(self):
        # `CPI in September` carries no year, and inventing one would be worse
        # than the short label. Unchanged from before the ship.
        assert _cpi_release_label(US_SEP_CPI[1]) == "Sep"

    def test_the_no_month_fallback_stops_at_a_word_boundary(self):
        assert _cpi_release_label(SOUTH_KOREA[1]) == "South Korea Annual"

    def test_a_short_name_is_left_whole(self):
        assert _cpi_release_label("Eurozone CPI") == "Eurozone CPI"

    def test_the_narrowed_pattern_no_longer_reads_a_month_out_of_a_word(self):
        assert _cpi_release_label("Maybe inflation rises in 2027") == "Maybe inflation"
        assert _cpi_release_label("Marginal CPI change 2026") == "Marginal CPI change"

    def test_long_month_spellings_and_sept_are_all_read(self):
        assert _cpi_release_label("Inflation in November 2026 (CPI YoY)") == "Nov 2026"
        assert _cpi_release_label("Sept 2026 CPI print") == "Sep 2026"

    def test_an_empty_name_yields_no_label_rather_than_a_substitute(self):
        assert _cpi_release_label("") == ""
        assert _cpi_release_label(None) == ""


class TestTheOrderingKey:
    def test_sorts_by_the_release_it_prices(self):
        keys = [_cpi_release_sort_key(_cpi_market(s)) for s in (DEC_2036, ARGENTINA)]
        assert keys[1] < keys[0]

    def test_an_undated_market_sorts_last_not_first(self):
        # A null is not "imminent". Ordered against the furthest real date in
        # the set, so the assertion cannot pass by accident of sign.
        undated = _cpi_release_sort_key(SimpleNamespace(resolution_date=None))
        assert undated > _cpi_release_sort_key(_cpi_market(DEC_2036))

    def test_a_naive_datetime_is_read_rather_than_raising(self):
        # `resolution_date` yields naive and aware datetimes from different
        # writers, and sorting those against each other raises TypeError — which
        # would be a 500 on the page, not a mis-order.
        naive = SimpleNamespace(resolution_date=datetime(2026, 10, 13, 15, 59))
        aware = _cpi_market(DEC_2036)
        assert _cpi_release_sort_key(naive) < _cpi_release_sort_key(aware)

    def test_a_market_with_no_such_attribute_is_tolerated(self):
        assert _cpi_release_sort_key(SimpleNamespace()) == (1, 0.0)


class TestTheServedCard:
    async def test_every_block_names_its_own_question(self, client, mock_db):
        blocks = await _blocks(client, mock_db)
        by_id = {m: n for m, n, _ in ALL_NINE}
        for block in blocks:
            assert block["q"] == by_id[block["market_id"]]

    async def test_no_two_blocks_share_a_heading(self, client, mock_db):
        blocks = await _blocks(client, mock_db)
        headings = [b["q"] for b in blocks]
        assert len(set(headings)) == len(headings), headings

    async def test_the_slice_drops_the_markets_from_the_2030s(self, client, mock_db):
        # The half a presence-only assertion cannot see: a reshuffle of the same
        # six would satisfy "September is shown" and change nothing.
        blocks = await _blocks(client, mock_db)
        assert THE_2030S.isdisjoint({b["market_id"] for b in blocks})

    async def test_the_months_a_reader_could_not_reach_are_now_on_the_card(
        self, client, mock_db
    ):
        blocks = await _blocks(client, mock_db)
        served = {b["market_id"] for b in blocks}
        assert {US_SEP_CPI[0], US_OCT_CPI[0], US_NOV_CPI[0]} <= served

    async def test_the_blocks_run_soonest_first(self, client, mock_db):
        blocks = await _blocks(client, mock_db)
        resolves = {m: _at(d) for m, _, d in ALL_NINE}
        dates = [resolves[b["market_id"]] for b in blocks]
        assert dates == sorted(dates), dates

    async def test_exactly_one_block_claims_to_be_next(self, client, mock_db):
        blocks = await _blocks(client, mock_db)
        assert sum(1 for b in blocks if b["is_next"]) == 1

    async def test_the_block_that_claims_it_is_the_soonest_one(self, client, mock_db):
        blocks = await _blocks(client, mock_db)
        # 2026-10-13, the earliest resolution date in the set.
        assert [b["market_id"] for b in blocks if b["is_next"]] == [ARGENTINA[0]]

    async def test_upcoming_stays_true_on_every_block_for_the_ios_gate(
        self, client, mock_db
    ):
        # iOS renders `releases.filter { $0.upcoming == true }` and shows the
        # section only `if !upcoming.isEmpty`. Six true here is six cards there.
        # If this ever reads 1, native's card row silently lost five.
        blocks = await _blocks(client, mock_db)
        assert [b["upcoming"] for b in blocks] == [True] * len(blocks)
        assert len(blocks) == 6

    async def test_the_two_fields_are_not_the_same_field(self, client, mock_db):
        # The mutant this file exists to catch: `is_next = upcoming`. Both are
        # bools on every block and agree on exactly one of them.
        blocks = await _blocks(client, mock_db)
        assert [b["is_next"] for b in blocks] != [b["upcoming"] for b in blocks]

    async def test_the_sort_key_does_not_reach_the_payload(self, client, mock_db):
        blocks = await _blocks(client, mock_db)
        assert all("_sort_key" not in b for b in blocks)

    async def test_the_rest_of_the_block_contract_is_unchanged(
        self, client, mock_db
    ):
        blocks = await _blocks(client, mock_db)
        for block in blocks:
            assert isinstance(block["brackets"], list) and block["brackets"]
            assert isinstance(block["peakIs"], int)
            assert isinstance(block["mo"], str)

    async def test_a_single_release_still_carries_the_badge(self, client, mock_db):
        # The degenerate case: one block must still be next, not zero.
        blocks = await _blocks(client, mock_db, specs=[US_SEP_CPI])
        assert [b["is_next"] for b in blocks] == [True]


class TestTheWiring:
    """The sort must be upstream of the slice.

    Every assertion in `TestTheServedCard` about WHICH markets appear passes on
    a nine-market payload only because the slice is downstream. Re-order after
    `[:6]` and the card is six correctly-ordered markets from the 2030s.
    """

    def _source(self) -> str:
        return Path(econ.__file__).read_text()

    def test_the_releases_are_sorted_before_they_are_sliced(self):
        source = self._source()
        sorted_at = source.index("cpi_releases.sort(")
        sliced_at = source.index('"cpi_releases": cpi_releases[:6]')
        assert sorted_at < sliced_at

    def test_the_scan_is_not_vacuous(self):
        # The anti-strawman control: both anchors must be real, distinct places
        # in the file. If the slice literal ever changes shape, the assertion
        # above starts passing on `-1 < -1` rather than on an ordering.
        source = self._source()
        assert source.count("cpi_releases.sort(") == 1
        assert source.count('"cpi_releases": cpi_releases[:6]') == 1

    def test_the_block_builder_carries_the_question(self):
        source = self._source()
        start = source.index("# --- Inflation section ---")
        end = source.index("# --- Jobs section ---", start)
        assert re.search(r'(?<!\w)"q": m\.name', source[start:end])

    def test_the_question_scan_is_not_vacuous(self):
        # `"q": m.name` is the idiom of EVERY row builder on this page, so
        # "absent from another section" is not available as a control — the
        # thing that can go wrong is the region silently spanning the file and
        # the scan passing on some other section's copy of the idiom. So: the
        # region is bounded, it is a small fraction of the file, and it holds
        # the inflation branch's own distinctive call rather than a neighbour's.
        source = self._source()
        start = source.index("# --- Inflation section ---")
        end = source.index("# --- Jobs section ---", start)
        section = source[start:end]
        assert 0 < len(section) < len(source) / 4
        assert "_cpi_release_label(" in section
        assert "_oil_row(" not in section
