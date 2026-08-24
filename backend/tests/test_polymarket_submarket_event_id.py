"""Queue 390 Item 2a — the sub-market loop throws away an event id it is holding.

`C-INGEST-EID-AUDIT-1` (CODEX-REPORT.md:26915) measured this as a LIVE leak, not a
historical one: of 7,815 Polymarket rows minted in a 48h window, **5,065 (64.8%)
are bare-hex `no_eid`** — no `polymarket_event_id` and no `container_group` in
`market_metadata`. ~2,500/day, ~900k/year on pace.

The cause is two lines wide. In the Gamma event loop the PARENT row is built with
`poly_metadata["polymarket_event_id"] = event.id`, and those are exactly the 2,750
rows that DO carry the key. Each sub-market is then upserted from inside the same
iteration — `event.id` and `market.condition_id` are both in hand, in the same
scope, from the same response — and its metadata is built as
`{"matchup_title": ...}` or `None`. The mapping exists at mint time and is
discarded for the sub-row, leaving `group_id` as the only surviving link.

That matters because `group_id` is not the contract anyone reads. The canonical
path is `market_metadata->>'polymarket_event_id'`, which is what
`repair_polymarket_evidence`, `precompute_calibration` and the settlement-truth
lineage use — so all of them see a miss on 64.8% of fresh rows and fall back to
parsing a column that was never promised to them.

Specimens are the two most recent rows from the audit:

  59391990  0x0d88ae7e…  "Set Handicap: Matsuda (-1.5) vs Plipuech (+1.5)"
            market_metadata={'matchup_title': 'Plipuech vs. Matsuda'}
            group_id=polymarket:885204
  59391729  0x44a41c24…  "Agustín Ramírez: Home Runs O/U 1.5"
            market_metadata={'shape': {...,'container_group':'polymarket:885545'}}
            group_id=polymarket:885469

The Ramírez row is the more instructive of the two: it carries a
`container_group` NESTED under `shape`, and the census's `?` operator tests
TOP-LEVEL keys only, so it is `no_eid` despite appearing to hold a container. A
nested key is not the key.
"""

from __future__ import annotations

from app.tasks.polymarket import sub_market_metadata


class TestMintTimeEventIdIsStamped:
    def test_the_matsuda_shape_gets_the_event_id(self):
        """Specimen 1: a matchup sub-market. Before the fix this was
        `{"matchup_title": "Plipuech vs. Matsuda"}` and nothing else."""
        meta = sub_market_metadata(
            event_id="885204", matchup_title="Plipuech vs. Matsuda"
        )
        assert meta is not None
        assert meta["polymarket_event_id"] == "885204"
        # The existing key must survive — this is additive, not a replacement.
        assert meta["matchup_title"] == "Plipuech vs. Matsuda"

    def test_the_ramirez_shape_gets_the_event_id_with_no_matchup(self):
        """Specimen 2: no `vs` sibling, so there is no matchup title. Before the
        fix this branch produced `None` — the row minted with NO metadata at all."""
        meta = sub_market_metadata(event_id="885469", matchup_title=None)
        assert meta is not None
        assert meta["polymarket_event_id"] == "885469"
        assert "matchup_title" not in meta

    def test_the_key_is_top_level_not_nested(self):
        """The census tests TOP-LEVEL keys with `?`. A nested key reads as absent.

        This is exactly how the Ramírez row looked like it had a container group
        and was still counted `no_eid`.
        """
        meta = sub_market_metadata(event_id="885469", matchup_title=None)
        assert "polymarket_event_id" in meta
        assert not any(
            isinstance(v, dict) and "polymarket_event_id" in v for v in meta.values()
        )

    def test_the_event_id_is_stringified(self):
        """`group_id` is `polymarket:{event.id}` and the backfill parses it back
        out with `split_part(...,':',2)` — a string. The minted key must be the
        same type, or the two halves of the same population compare unequal."""
        meta = sub_market_metadata(event_id=885204, matchup_title=None)
        assert meta["polymarket_event_id"] == "885204"
        assert isinstance(meta["polymarket_event_id"], str)

    # ---- the other direction (gotcha #43) ----

    def test_no_event_id_means_no_key_invented(self):
        """Absence stays absence. Stamping a placeholder would be worse than the
        bug: a null/empty `polymarket_event_id` satisfies the `?` census while
        pointing at nothing, converting a COUNTABLE gap into an invisible one."""
        meta = sub_market_metadata(event_id=None, matchup_title="A vs. B")
        assert meta == {"matchup_title": "A vs. B"}
        assert "polymarket_event_id" not in meta

    def test_nothing_at_all_still_returns_none(self):
        """The pre-existing contract: `None`, not `{}`. The insert passes this
        straight to the column, and `{}` would overwrite a populated
        `market_metadata` with an empty object on re-ingest."""
        assert sub_market_metadata(event_id=None, matchup_title=None) is None

    def test_empty_string_event_id_is_treated_as_absent(self):
        assert sub_market_metadata(event_id="", matchup_title=None) is None
