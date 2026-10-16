"""#683 forecast half: archive intervals as a calibration closing line. OFF.

PILLAR: TRUTH. SHIP: a settled Kalshi question with missing history gains its
real pre-resolution journey, and its forecast eligibility is honest. A
reader-only interval never becomes a graded forecast.

This module is the ONLY place calibration may read the archive store. A static
guard (``tests/test_kalshi_archive_store_683.py``) fails if any other
calibration, Accuracy or snapshot-consumer module names the archive tables.

WHY IT IS OFF, AND WHY THE SWITCH IS CODE AND NOT CONFIG. Turning it on changes
which rows can enter the published Accuracy curve. That is a population change
of the kind ruling 103 puts in front of review first, and Root's storage
decision keeps activation separate until two things are paid: independent
row-level time/identity/price/eligibility evidence (Measurement) and a
methodological review. A config var could be flipped without either, so
activation is a reviewed one-line diff of :data:`KALSHI_ARCHIVE_FORECAST_ENABLED`.
While it is ``False`` the calibration SQL is byte-identical to its parent. The
guard test pins that digest.

WHAT ACTIVATION WOULD NOT DO ON ITS OWN. The curve's population CTEs and their
capture-age exclusions (``calibration_price_provenance``: ``after_resolution``,
``no_capture_ts``) are unchanged and still decide whether such a row is curved
at all. Those rules belong to the methodological review, not to this switch.

WHAT THE LATERAL ADMITS, re-checked at consumption and not inherited:

* only intervals the apply admitted as ``forecast``, whose WHOLE interval ends
  at or before the evidence's ``forecast_cutoff_ts`` AND at or before the
  closing-line boundary Part A already uses;
* only while the event the cutoff was decided on still has the same id, the
  same start and the same start provenance. A moved start voids the evidence;
* only from an import that finished (``applied`` / ``partial``), never one
  still ``applying``;
* never for a Kalshi threshold prop. That arm requires a bid-backed live quote
  (Queue #167), and the archive has no equivalent proof yet.
"""

from __future__ import annotations

#: The switch. Reviewed code change only; see the module doc.
KALSHI_ARCHIVE_FORECAST_ENABLED = False


def archive_forecast_lateral_sql(*, outcome_id: str, boundary: str) -> str:
    """``(SELECT probability …)`` for ``LEFT JOIN LATERAL … archive ON true``."""
    return f"""(
                                SELECT k.probability
                                FROM kalshi_archive_intervals k
                                JOIN kalshi_archive_outcome_evidence ev
                                  ON ev.id = k.evidence_id
                                JOIN kalshi_archive_imports ki ON ki.id = k.import_id
                                JOIN futures_outcomes afo ON afo.id = k.outcome_id
                                JOIN futures_markets afm ON afm.id = afo.market_id
                                JOIN events ae ON ae.id = afm.event_id
                                WHERE k.outcome_id = {outcome_id}
                                  AND k.admission_at_apply = 'forecast'
                                  AND ki.status IN ('applied', 'partial')
                                  AND ev.forecast_cutoff_ts IS NOT NULL
                                  AND k.interval_end <= ev.forecast_cutoff_ts
                                  AND k.interval_end <= {boundary}
                                  AND ae.id = (ev.cutoff_inputs->>'event_id')::int
                                  AND ae.commence_time
                                      = (ev.cutoff_inputs->>'commence_time')::timestamptz
                                  AND ae.commence_time_source
                                      IS NOT DISTINCT FROM
                                      ev.cutoff_inputs->>'commence_time_source'
                                ORDER BY k.interval_end DESC
                                LIMIT 1
                            )"""


def archive_closing_value_sql() -> str:
    """The archive's contribution to Part A's value, refusing threshold props."""
    return "CASE WHEN nc.is_threshold THEN NULL ELSE archive.probability END"
