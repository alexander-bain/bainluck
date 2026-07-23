"""L2-171 — cockpit 'Waiting on you' row copy polish.

Ops files needs-user issues titled '[Waiting on you] <literal step>'. The panel
is already headed 'Waiting on you', so the row action should read as the concrete
step, not echo the bracket prefix.
"""

from app.routes.admin_cockpit import _clean_waiting_action


class TestCleanWaitingAction:
    def test_strips_bracket_prefix(self):
        assert (
            _clean_waiting_action(
                "[Waiting on you] Pull-to-refresh on native Discover — confirm feed parity (closes #1221)"
            )
            == "Pull-to-refresh on native Discover — confirm feed parity (closes #1221)"
        )

    def test_case_insensitive_and_trailing_punct(self):
        assert _clean_waiting_action("[waiting on you]: Do one signed-in search") == (
            "Do one signed-in search"
        )
        assert _clean_waiting_action("[Waiting On You] - Try the flow") == (
            "Try the flow"
        )

    def test_keeps_context_suffixes(self):
        # (L2-164), (closes #NNN) etc. are context, not chrome — kept intact.
        assert (
            _clean_waiting_action(
                "[Waiting on you] Celtics team page — tap-to-zoom + division spacing visual check (L2-164)"
            )
            == "Celtics team page — tap-to-zoom + division spacing visual check (L2-164)"
        )

    def test_untitled_prefixed_falls_back_to_raw(self):
        # Stripping everything would leave nothing -> keep the raw title.
        assert _clean_waiting_action("[Waiting on you]") == "[Waiting on you]"

    def test_no_prefix_unchanged(self):
        assert _clean_waiting_action("Set GITHUB_TOKEN on Heroku") == (
            "Set GITHUB_TOKEN on Heroku"
        )

    def test_empty_safe(self):
        assert _clean_waiting_action("") == ""
