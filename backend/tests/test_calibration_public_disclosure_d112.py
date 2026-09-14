"""A method change is disclosed to the reader, and disclosing it never costs the bank.

D112 (#997, CAL-P1190) landed on 2026-09-13 while the accuracy page was mid-rebuild
with 53 of 128 units banked. Two facts collided:

* the method history (``docs/calibration/METHODOLOGY-LEDGER.md``) is a REPO file —
  merging it establishes no reader-visible disclosure at all. What a reader sees is
  the corrections panel, fed by :data:`CALIBRATION_CORRECTIONS` in the payload — and
  on the WEB that panel prints the date, the title and the row count only, because
  #4067 / CERT-2295 took the server's paragraph off the page (the app still prints
  it). So the title has to carry the change by itself; and
* ``precompute_calibration.py`` is ruling-009-frozen while a bank is climbing,
  because an edit that moves :func:`_main_input_fingerprint` discards every banked
  unit and costs another dark day.

The second fact reads as a blanket ban on touching the file, which would mean a
method change could not be disclosed until after it published. It is not: the digest
hashes the SOURCE TEXT of five named functions plus a short list of values, and the
corrections list is neither. That is the property this module pins, so that nobody
has to re-derive it under time pressure the next time, and — more importantly — so
that the day somebody adds the corrections list to the digest's inputs (a natural
looking change; it is served in the payload, after all) this fails loudly instead of
silently making every future disclosure cost a rebuild.

The first test carries its own positive control. ``_main_input_fingerprint`` does not
read the corrections list, so "mutate it and assert the digest held" passes for free
and would keep passing if the digest were hardcoded, broken, or constant. The control
mutates an input that IS hashed and asserts the digest MOVES, in the same test, so a
green row means the instrument was live when it reported.
"""

import pytest

from app.tasks import precompute_calibration as pc


class TestDisclosureIsFreeButNotUnwatched:
    def test_appending_a_corrections_row_does_not_move_the_input_fingerprint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A disclosure row is publishable mid-climb; a hashed value is not."""
        before = pc._main_input_fingerprint()

        new_row = {
            "date": "2099-01-01",
            "title": "A row that exists only inside this test",
            "rows": None,
            "description": "If appending this moves the digest, every future "
            "disclosure costs the in-flight bank.",
        }
        monkeypatch.setattr(
            pc, "CALIBRATION_CORRECTIONS", [*pc.CALIBRATION_CORRECTIONS, new_row]
        )

        assert pc._main_input_fingerprint() == before, (
            "Appending a corrections row moved the input fingerprint. Every unit "
            "banked by the running rebuild is now unresumable, and disclosing a "
            "method change has become something that can only be done while the "
            "page is already dark. If this was deliberate, the disclosure workflow "
            "in the module docstring has to change with it."
        )

        # POSITIVE CONTROL, same test: an input that IS hashed must move the digest,
        # or the assertion above proved nothing about a live instrument.
        monkeypatch.setattr(pc, "CALIBRATION_POPULATION_VERSION", "q999-not-a-version")
        assert pc._main_input_fingerprint() != before, (
            "The digest did not move when the population version changed, so it is "
            "not reading its inputs and the invariance asserted above is vacuous."
        )

    def test_d112_is_disclosed_where_a_reader_can_see_it(self) -> None:
        """The method history is a repo file; this list is the public channel."""
        rows = [c for c in pc.CALIBRATION_CORRECTIONS if c["date"] == "2026-09-13"]
        assert len(rows) == 1, (
            "D112 landed on 2026-09-13 and changed which results are scored. It has "
            "an entry in docs/calibration/METHODOLOGY-LEDGER.md, but that file is "
            "not served to anyone — the corrections panel is. A method change the "
            "reader cannot see is not disclosed."
        )
        (row,) = rows

        assert row["rows"] is None, (
            "This row's count must stay absent until a rebuild under the new rule "
            "publishes one. The only figure available beforehand (~3,046) is a "
            "population upper bound, and this panel states measured counts or "
            "nothing — the same rule the method history's 'what it affected' row "
            "is holding to."
        )

    def test_the_title_carries_the_change_because_the_web_prints_nothing_else(
        self,
    ) -> None:
        """On the web the title IS the disclosure; ``description`` never renders.

        #4067 / CERT-2295 removed this panel's server prose from
        bainluck.com/calibration — the page renders the date, the title and the
        row count, and a jest suite renders the whole page to keep it that way
        (``supplierWordsFromCalibrationPayloadDoNotReachRenderedPage4067``). The
        app is the only surface that prints ``description``. This row also
        carries no count, so for a web reader the title is the entire message:
        it has to say what changed, not just name the class it changed.

        The channel half of this claim — the title reaches a rendered web page
        and the paragraph does not — is asserted against real markup in
        ``frontend/__tests__/components/d112DisclosureReachesAWebReader997.test.tsx``;
        this arm is the content half.
        """
        (row,) = [c for c in pc.CALIBRATION_CORRECTIONS if c["date"] == "2026-09-13"]
        title = row["title"].lower()

        assert "scored" in title, (
            "The title does not say what changed. A web reader sees this row as "
            "a date and this one line — no paragraph, and no row count on this "
            "row — so a title that only names the affected markets leaves the "
            "method change undisclosed on the surface most people read. Say the "
            "new state in the title; the paragraph is for the app and the API."
        )

    def test_the_disclosure_speaks_to_a_reader_not_to_a_reviewer(self) -> None:
        """Notices 19/33/34: plain English, no supplier words, no internal jargon."""
        (row,) = [c for c in pc.CALIBRATION_CORRECTIONS if c["date"] == "2026-09-13"]
        text = f"{row['title']} {row['description']}".lower()

        for banned in (
            "bookmaker",
            "per-bookmaker",
            "population version",
            "q271",
            "fingerprint",
            "predicate",
            "cert-",
        ):
            assert banned not in text, (
                f"The corrections panel is a reader's screen, and {banned!r} is "
                "either a supplier word (notice 33) or our own jargon (notice 34). "
                "It belongs in the method history, the PR or the ledger."
            )
