"""Contract tests for admin event endpoints."""

from types import SimpleNamespace

import pytest


class TestEventAdminAuthGuards:
    """Event admin endpoints reject invalid secrets."""

    @pytest.mark.parametrize(
        "path",
        [
            "/api/admin/schedule/accuracy?secret=bad",
        ],
    )
    async def test_get_rejects_bad_secret(self, client, path):
        resp = await client.get(path)
        assert resp.status_code == 403


class TestScheduleAccuracyLinkage:
    """schedule/accuracy reports TRUE source linkage, not commence_time_source.

    Regression guard for the admin Matching page metric artifact: the `sources`
    object must count events carrying each source's id column (external_id /
    espn_id / statpal_fixture_id), NOT the distribution of commence_time_source
    (which mislabels every ESPN-covered league as ~0% Odds API).
    """

    def _result(self, rows):
        from unittest.mock import MagicMock

        r = MagicMock()
        r.all.return_value = rows
        return r

    async def test_sources_are_linkage_not_commence_time_source(
        self, client, mock_db, monkeypatch
    ):
        monkeypatch.setenv("ADMIN_TOKEN", "s3cret")

        # Dimension 1: TRUE linkage. NFL is fully Odds-API-linked (159/159) even
        # though (Dimension 2) ESPN won the commence_time_source race for all 159.
        linkage_rows = [
            SimpleNamespace(
                key="americanfootball_nfl", total=159, odds_api=159, espn=158, statpal=0
            ),
            SimpleNamespace(
                key="baseball_mlb", total=172, odds_api=113, espn=146, statpal=172
            ),
        ]
        # Dimension 2: commence_time_source provenance — odds_api is 0 for both
        # because ESPN/StatPal outrank it on the time write.
        cts_rows = [
            SimpleNamespace(
                key="americanfootball_nfl", commence_time_source="espn", count=159
            ),
            SimpleNamespace(
                key="baseball_mlb", commence_time_source="espn", count=109
            ),
            SimpleNamespace(
                key="baseball_mlb", commence_time_source="statpal", count=63
            ),
        ]
        mock_db.execute.side_effect = [
            self._result(linkage_rows),
            self._result(cts_rows),
        ]

        resp = await client.get("/api/admin/schedule/accuracy?days=14", headers={"Authorization": "Bearer s3cret"})
        assert resp.status_code == 200
        data = resp.json()

        nfl = data["sports"]["americanfootball_nfl"]
        # The bug: this used to be 0 (commence_time_source). It must be 159 now.
        assert nfl["sources"]["odds_api"] == 159
        assert nfl["sources"]["espn"] == 158
        assert nfl["total"] == 159
        assert nfl["odds_api_linked_pct"] == 100.0
        assert nfl["reliability"] == "HIGH"
        # Provenance is preserved but clearly separated.
        assert nfl["commence_time_sources"]["espn"] == 159

        mlb = data["sports"]["baseball_mlb"]
        assert mlb["sources"]["odds_api"] == 113  # genuine 66% partial gap, not 0%
        assert mlb["sources"]["statpal"] == 172
        assert mlb["odds_api_linked_pct"] == 65.7
        assert mlb["reliability"] == "MEDIUM"
        # Odds API never wins the commence_time_source race for MLB (ESPN/StatPal outrank it).
        assert mlb["commence_time_sources"].get("odds_api", 0) == 0
