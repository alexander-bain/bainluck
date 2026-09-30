"""#9171 — the /politics Gubernatorial section stops listing federal-government
markets as governor races.

THE READER'S VIEW (bainluck.com/politics at 390px, 2026-09-27 16:19Z): the
second and third cards under "Gubernatorial · 10 shown · 140 total" were "How
much government spending will Trump cut before 2027?" (108579) and "…before
his term ends?" (108315).

THE CAUSE: `_classify_theme` labels any ticker starting `kxgov` as
gubernatorial, and `KXGOV` also starts Kalshi's federal-GOVERNMENT family
(`KXGOVT*`). Those rows are tagged `politics`, so the category arm fetches them
and #9165's query change could not reach them — only the label is wrong.

THE TRAP THE FIX MUST NOT FALL INTO: `KXGOVTXNOMD` is the Texas governor
nominee, and a Tennessee race would be `KXGOVTN`. A `kxgovt` carve-out moves
both out of Gubernatorial, so the non-governor series are named one by one.
`TestGovernorRacesStayGubernatorial` is the control that catches that widening.
"""

from types import SimpleNamespace

import pytest

from app.routes.politics import _THEME_BY_TICKER_CLASSIFY_ONLY, _classify_theme


def _market(external_id: str, name: str = "Some market"):
    """Only what `_classify_theme` reads. The default name matches no
    `_THEME_BY_NAME` pattern, so a theme below comes from the TICKER."""
    return SimpleNamespace(external_id=external_id, name=name)


# Real open Kalshi tickers and names, read from production 2026-09-27 16:22Z.
_FEDERAL_SERIES = [
    ("KXGOVTCUTS-26", "How much government spending will Trump cut before 2027?"),
    ("KXGOVTCUTS-29", "How much government spending will Trump cut before his term ends?"),
    ("KXGOVTSHUTDOWN-26DEC12", "Government shutdown on Dec 12, 2026?"),
    ("KXGOVTSHUTLENGTH-26", "How long will the government shutdown last?"),
    ("KXGOVTFUNDSVOTES-26", "How many Senators will vote for the next government funding bill?"),
    ("KXGOVTSPEND-26", "Government spending increase in 2026"),
    ("KXGOVAIKILLSWITCH-27", "When will the U.S. authorize a government AI kill switch?"),
    ("KXGOVBAL-26-CHN", "China’s government budget balance in 2026"),
]

_GOVERNOR_RACES = [
    ("KXGOVAK-26", "Alaska Governor winner? (Person)"),
    ("KXGOVCA-26", "California Governor winner? (Person)"),
    ("KXGOVCAPRIMARY-26", "California Governor primary advancers? (Person)"),
    ("KXGOVARNOMD-26", "Arkansas Democratic Governor nominee?"),
    ("KXGOVOHNOMR-26", "Ohio Republican Governor nominee?"),
    ("KXGOVTXNOMD-26", "Texas Democratic Governor nominee?"),
    ("KXGOVTN-26", "Tennessee Governor winner?"),
    ("KXGOVPARTYAK-26", "Alaska Governor winner? (Party)"),
    ("KXGOVSENDIFF-26", "How many states will elect a governor and senator from different parties in 2026?"),
    ("KXGOVWINS-26", "Who will hold more governorships after the midterms?"),
]


class TestFederalSeriesLeaveGubernatorial:
    @pytest.mark.parametrize("external_id, name", _FEDERAL_SERIES)
    def test_not_filed_as_a_governor_race(self, external_id, name):
        assert _classify_theme(_market(external_id, name)) != "gubernatorial", (
            f"{external_id} {name!r} is not a governor race (#9171)"
        )

    @pytest.mark.parametrize("external_id, name", _FEDERAL_SERIES[:6])
    def test_spending_shutdown_and_funding_are_policy(self, external_id, name):
        assert _classify_theme(_market(external_id, name)) == "policy"

    def test_the_specimen_by_ticker_alone(self):
        """The label must come from the ticker carve-out, not the name: with a
        neutral name the old table said gubernatorial."""
        assert _classify_theme(_market("KXGOVTCUTS-26")) == "policy"

    def test_strawman_the_bare_prefix_files_every_specimen_as_gubernatorial(self):
        """If the bare `kxgov` arm alone no longer claims these tickers, the
        tests above measure nothing."""
        for external_id, _ in _FEDERAL_SERIES:
            assert external_id.lower().startswith("kxgov")
        bare = [(p, t) for p, t in _THEME_BY_TICKER_CLASSIFY_ONLY if p == "kxgov"]
        assert bare == [("kxgov", "gubernatorial")]


class TestGovernorRacesStayGubernatorial:
    """The control: every real governor series keeps its theme — including the
    two a `kxgovt` prefix carve-out would steal."""

    @pytest.mark.parametrize("external_id, name", _GOVERNOR_RACES)
    def test_theme_is_gubernatorial(self, external_id, name):
        assert _classify_theme(_market(external_id)) == "gubernatorial"
        assert _classify_theme(_market(external_id, name)) == "gubernatorial"

    def test_no_carve_out_is_a_bare_govt_prefix(self):
        prefixes = [p for p, _ in _THEME_BY_TICKER_CLASSIFY_ONLY]
        assert "kxgovt" not in prefixes
        for p in prefixes:
            if p.startswith("kxgov") and p != "kxgov":
                assert len(p) > len("kxgovtx"), (
                    f"carve-out {p!r} is short enough to swallow a state code"
                )

    def test_carve_outs_sit_ahead_of_the_governor_arm(self):
        """First match wins in `_classify_theme`, so a carve-out listed after
        `kxgov` is dead."""
        prefixes = [p for p, _ in _THEME_BY_TICKER_CLASSIFY_ONLY]
        gov = prefixes.index("kxgov")
        for i, p in enumerate(prefixes):
            if p.startswith("kxgov") and p != "kxgov":
                assert i < gov, p
