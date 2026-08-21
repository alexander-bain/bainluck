"""Queue 390 — the four findings ``C-2063-REVIEW`` BLOCKED on, one specimen each.

Every test in this file was written to FAIL against `3e7cd3eb` and was observed
failing before the corresponding fix existed. That ordering is the whole point:
a security test written after its fix proves the fix is *present*, never that it
is *load-bearing*. Three of these four passed trivially in an earlier draft
precisely because they asserted the shape of the fix rather than the behaviour of
the defect, and were rewritten.

The findings, in the reviewer's severity order:

* **[P1] logout replay** — the admin bearer captured at mount outlives the
  session that justified it (frontend; specimen in
  ``frontend/__tests__/components/adminAuthProviderLogout.test.tsx``, because the
  defect lives in React state that no Python test can reach).
* **[P1] role revocation** — ``users.is_admin = false`` cannot revoke the one
  row the feature was built for, because the legacy allowlist is OR-ed after it.
* **[P2] reviewer spoofing** — an identity caller can name any ``reviewer`` it
  likes and the row keeps it.
* **[P2] token-path drift** — the shared-token write re-enters identity
  verification, disproving the PR's own "no JWT parse on the lane path" claim.

The two P2s share a root cause — authorization is resolved as a *boolean* and
then re-derived for attribution — so they share a fix (``_resolve_admin_principal``)
and are asserted separately anyway, since a shared fix that regresses one of them
must not be able to hide behind the other.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from starlette.requests import Request

from app.routes.admin_utils import _check_admin_auth, _user_is_admin

# ``_resolve_admin_principal`` is imported INSIDE the tests that need it, not at
# module scope. A module-level import of a symbol the fix has not added yet turns
# the whole file into a COLLECTION ERROR — pytest exit code 2 — and gotcha #54 is
# explicit that only exit 1 is a result: a 2 says the harness could not check,
# which is precisely not the red these specimens are supposed to produce. Lazy
# imports let every other specimen execute and fail on its own defect.

BASE_TOKEN = "base-admin-token"
ADMIN_JWT = "admin.session.jwt"
ADMIN_UID = "firebase-uid-alex"
ADMIN_EMAIL = "alex@example.com"


class FakeUser:
    """A ``users`` row.

    ``is_admin`` is deliberately three-valued here, mirroring the column after
    this queue: pass ``True``/``False`` for an explicit decision, or ``None`` for
    *no decision recorded* — which is both "column not loaded by this SELECT" and
    "column is SQL NULL". Those two collapse to the same reading on purpose; see
    ``_user_is_admin``'s docstring.
    """

    def __init__(self, *, id: int, email: str | None, is_admin: bool | None = None):
        self.id = id
        self.email = email
        if is_admin is not None:
            self.is_admin = is_admin


class _Result:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class FakeDB:
    def __init__(self):
        self.queries = 0
        self.next_row: FakeUser | None = None

    async def execute(self, _stmt):
        self.queries += 1
        return _Result(self.next_row)


def _request(*, bearer: str | None = None) -> Request:
    headers = []
    if bearer is not None:
        headers.append((b"authorization", f"Bearer {bearer}".encode()))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/admin/ranking-judgments",
            "query_string": b"",
            "headers": headers,
        }
    )


@pytest.fixture
def tokens(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", BASE_TOKEN)
    monkeypatch.setenv("ADMIN_USER_IDS", "")
    monkeypatch.setenv("ADMIN_USER_EMAILS", "")
    return BASE_TOKEN


@pytest.fixture
def counting_verifier(monkeypatch):
    """Stub ``verify_id_token`` that RECORDS every token handed to it.

    The recording is the evidence for the token-path-drift specimen. The reviewer
    caught that defect exactly this way — ``verify_calls=['shared-capability']``
    on a request that had already authorized by token.
    """
    calls: list[str] = []
    claims = {ADMIN_JWT: {"uid": ADMIN_UID, "email": ADMIN_EMAIL}}

    def fake_verify(token, allow_session_token=True):
        calls.append(token)
        return claims.get(token)

    monkeypatch.setattr("app.services.firebase_auth.verify_id_token", fake_verify)
    return calls


# --------------------------------------------------------------------------
# [P1] Finding 2 — an explicit `is_admin = false` must REVOKE
# --------------------------------------------------------------------------


class TestExplicitFalseRevokes:
    """``UPDATE users SET is_admin = false`` is the advertised revocation.

    Before this queue it did nothing to the one row it was built for:
    ``DEFAULT_ADMIN_USER_IDS = {364}`` was OR-ed *after* the column, so the
    documented revoke statement left a compromised session admin until someone
    shipped code. The reviewer executed this — a civilian JWT mapped to row
    ``id=364, is_admin=False`` got ``200 {is_admin: true, via: "identity"}``.
    """

    def test_explicit_false_beats_the_hardcoded_default_id(self, monkeypatch):
        """THE specimen. Row 364 is exactly the id the feature was built for."""
        monkeypatch.setattr(
            "app.routes.admin_utils.DEFAULT_ADMIN_USER_IDS", {364}
        )
        monkeypatch.setattr("app.routes.admin_utils.DEFAULT_ADMIN_EMAILS", set())
        monkeypatch.setenv("ADMIN_USER_IDS", "")
        monkeypatch.setenv("ADMIN_USER_EMAILS", "")

        revoked = FakeUser(id=364, email="alex@example.com", is_admin=False)
        assert _user_is_admin(revoked) is False, (
            "users.is_admin = false did not revoke. The legacy allowlist is "
            "OR-ed after the column, so the documented revocation statement is "
            "decorative for the only row it was written for."
        )

    def test_explicit_false_beats_the_env_email_allowlist(self, monkeypatch):
        """The same hole, reached through the other legacy arm."""
        monkeypatch.setattr("app.routes.admin_utils.DEFAULT_ADMIN_USER_IDS", set())
        monkeypatch.setattr("app.routes.admin_utils.DEFAULT_ADMIN_EMAILS", set())
        monkeypatch.setenv("ADMIN_USER_IDS", "")
        monkeypatch.setenv("ADMIN_USER_EMAILS", "alex@example.com")

        revoked = FakeUser(id=999, email="Alex@Example.com", is_admin=False)
        assert _user_is_admin(revoked) is False

    # ---- the other direction (gotcha #43): the fallback must SURVIVE ----

    def test_no_decision_recorded_still_falls_back_to_the_allowlist(
        self, monkeypatch
    ):
        """The rollout window this fix must not close.

        A column that denies when it holds *no decision* would lock Alex out
        between the release and the grant — the exact failure the PR author
        avoided by keeping the allowlists. ``None``/absent means "nothing was
        recorded", not "denied".
        """
        monkeypatch.setattr(
            "app.routes.admin_utils.DEFAULT_ADMIN_USER_IDS", {364}
        )
        monkeypatch.setattr("app.routes.admin_utils.DEFAULT_ADMIN_EMAILS", set())
        monkeypatch.setenv("ADMIN_USER_IDS", "")
        monkeypatch.setenv("ADMIN_USER_EMAILS", "")

        ungranted = FakeUser(id=364, email="alex@example.com", is_admin=None)
        assert _user_is_admin(ungranted) is True, (
            "The rollout fallback broke: a row with no recorded decision must "
            "still reach the legacy allowlist, or the release locks out the "
            "person holding the SQL."
        )

    def test_true_still_grants_without_any_allowlist(self, monkeypatch):
        monkeypatch.setattr("app.routes.admin_utils.DEFAULT_ADMIN_USER_IDS", set())
        monkeypatch.setattr("app.routes.admin_utils.DEFAULT_ADMIN_EMAILS", set())
        monkeypatch.setenv("ADMIN_USER_IDS", "")
        monkeypatch.setenv("ADMIN_USER_EMAILS", "")

        granted = FakeUser(id=1, email="new-admin@example.com", is_admin=True)
        assert _user_is_admin(granted) is True

    def test_the_column_is_nullable_so_ungranted_and_revoked_are_distinguishable(
        self,
    ):
        """Without three states the fix above is unimplementable.

        ``BOOLEAN NOT NULL DEFAULT false`` makes every pre-existing row read
        ``false`` on the release, so "explicit false denies" and "the allowlist
        still works during rollout" cannot both hold. The migration has never run
        in production (``users.is_admin`` is ``undefined_column`` there, checked
        by command), so it was amended rather than superseded.
        """
        from app.models.models import User

        assert User.__table__.c.is_admin.nullable is True, (
            "users.is_admin is NOT NULL, so a never-granted row and a revoked "
            "row are the same value and revocation cannot be expressed."
        )


# --------------------------------------------------------------------------
# [P2] Finding 4 — the shared-token path must not re-enter the verifier
# --------------------------------------------------------------------------


class TestTokenPathDoesNotParseJWTs:
    """"Lanes keep tokens, zero change to their path" — mechanically, not as prose.

    ``_check_admin_auth`` always short-circuited correctly; the *write* then
    called ``_resolve_admin_email`` with the same bearer and re-entered Firebase
    verification. Authorization returned a boolean, so attribution had no way to
    know which arm had won and simply asked again.
    """

    @pytest.mark.asyncio
    async def test_shared_token_never_reaches_the_verifier(
        self, tokens, counting_verifier
    ):
        from app.routes.admin_utils import _resolve_admin_principal

        db = FakeDB()
        principal = await _resolve_admin_principal(None, _request(bearer=BASE_TOKEN), db)

        assert principal is not None and principal.via == "token"
        assert counting_verifier == [], (
            "The shared-token path invoked the identity verifier "
            f"({counting_verifier}). A dozen lanes hold this token; every "
            "label write should not become auth-service and log work."
        )
        assert db.queries == 0, "The token path touched the database."

    @pytest.mark.asyncio
    async def test_the_token_principal_carries_no_email(self, tokens, counting_verifier):
        """Absence is the honest encoding — the token identifies a capability."""
        from app.routes.admin_utils import _resolve_admin_principal

        db = FakeDB()
        principal = await _resolve_admin_principal(None, _request(bearer=BASE_TOKEN), db)
        assert principal.email is None
        assert principal.user is None

    @pytest.mark.asyncio
    async def test_identity_still_resolves_once_and_carries_its_user(
        self, tokens, counting_verifier
    ):
        from app.routes.admin_utils import _resolve_admin_principal

        db = FakeDB()
        db.next_row = FakeUser(id=1, email=ADMIN_EMAIL, is_admin=True)

        principal = await _resolve_admin_principal(None, _request(bearer=ADMIN_JWT), db)

        assert principal is not None and principal.via == "identity"
        assert principal.email == ADMIN_EMAIL
        assert principal.user is not None
        assert counting_verifier == [ADMIN_JWT], (
            "The identity path verified more than once — the double resolution "
            f"this fix removes is still present: {counting_verifier}"
        )

    @pytest.mark.asyncio
    async def test_check_admin_auth_still_answers_the_same_booleans(
        self, tokens, counting_verifier
    ):
        """The refactor must not move the gate it is factored out of."""
        db = FakeDB()
        assert await _check_admin_auth(None, _request(bearer=BASE_TOKEN), db) is True
        assert await _check_admin_auth(None, _request(bearer="wrong"), db) is False
        assert await _check_admin_auth(None, _request(bearer=None), db) is False

    def test_the_write_path_resolves_authorization_exactly_once(self):
        """Structural, because the unit tests above cannot see the wiring.

        ``create_judgment`` authorized with one helper and then attributed with
        another. Both fixes are pointless if a future edit re-adds the second
        call, and no behavioural test in this file would notice.
        """
        source = (
            Path(__file__).resolve().parents[1] / "app/routes/admin_judgments.py"
        ).read_text()
        tree = ast.parse(source)

        target = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == "create_judgment":
                    target = node
        assert target is not None, "create_judgment vanished — fix this scanner."

        called = [
            (getattr(c.func, "id", None) or getattr(c.func, "attr", None))
            for c in ast.walk(target)
            if isinstance(c, ast.Call)
        ]
        assert "_resolve_admin_email" not in called, (
            "create_judgment still calls _resolve_admin_email after authorizing. "
            "That is the second resolution: it re-verifies the bearer the gate "
            "already judged, and on the token path it parses a JWT that is not one."
        )
        assert called.count("_resolve_admin_principal") == 1, (
            "create_judgment must resolve the principal exactly once and carry "
            f"the result; saw {called.count('_resolve_admin_principal')}."
        )


# --------------------------------------------------------------------------
# [P2] Finding 3 — an identity write attributes to the authenticated principal
# --------------------------------------------------------------------------


class TestIdentityCannotForgeTheReviewer:
    """The reviewer executed this: an identity caller posted
    ``reviewer="victim@example.com"`` and the committed row kept it, while
    metadata separately recorded the real author. The gold tier was right and the
    operational reviewer — the field reviewed-state and dedup key on — was
    caller-controlled.
    """

    def test_identity_write_overrides_an_explicit_foreign_reviewer(self):
        from app.routes.admin_judgments import reviewer_for_write

        value = reviewer_for_write(
            via="identity", admin_email=ADMIN_EMAIL, requested="victim@example.com"
        )
        assert value == ADMIN_EMAIL, (
            "An identity-authenticated write attributed the row to a reviewer "
            "the caller named. reviewed-state and dedup key on this field."
        )

    def test_identity_write_still_overrides_the_generic_surface_names(self):
        from app.routes.admin_judgments import reviewer_for_write

        for surface in ("native", "web", "alex", "admin", "ios"):
            assert (
                reviewer_for_write(
                    via="identity", admin_email=ADMIN_EMAIL, requested=surface
                )
                == ADMIN_EMAIL
            )

    def test_token_write_preserves_an_explicit_delegated_reviewer(self):
        """The other direction. The kid ``/play`` surface names its reviewer on
        purpose, and it authenticates with the shared token — that delegation is
        real and must survive."""
        from app.routes.admin_judgments import reviewer_for_write

        assert (
            reviewer_for_write(
                via="token", admin_email=None, requested="kid-surface-reviewer"
            )
            == "kid-surface-reviewer"
        )

    def test_token_write_keeps_the_generic_surface_name_it_was_given(self):
        from app.routes.admin_judgments import reviewer_for_write

        assert (
            reviewer_for_write(via="token", admin_email=None, requested="web") == "web"
        )


# --------------------------------------------------------------------------
# The route-level specimens — what the reviewer actually executed
# --------------------------------------------------------------------------
#
# The unit specimens above are the right granularity for the FIX, but three of
# the four findings were found by driving the real handler and inspecting the
# committed row, and a fix should have to survive the same treatment. These call
# `create_judgment` directly (every parameter has a default, so no TestClient and
# no app wiring is needed) against a recording session.


class RecordingDB:
    """A write session that keeps the row instead of persisting it."""

    def __init__(self, row=None):
        self.added = []
        self.committed = False
        self.queries = 0
        self.next_row = row

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = 1

    async def execute(self, _stmt):
        self.queries += 1
        return _Result(self.next_row)


#: Every ``Query(None)`` parameter on ``create_judgment``. Calling the handler
#: directly does not run FastAPI's dependency resolution, so these defaults
#: arrive as ``Query`` OBJECTS rather than ``None`` and get merged into the row
#: (the first draft of these specimens failed with "'Query' object is not
#: iterable" — a harness error wearing a test failure's clothes). Passing them
#: explicitly is what makes the specimen fail on its DEFECT.
_QUERY_PARAMS = (
    "secret surface rank_seen item_type market_id event_id market_name label "
    "reason_tags better_than worse_than notes score_at_review category_at_review "
    "archetype_at_review quality_class_at_review headline_at_review "
    "feed_request_id fixable_interesting repair_type repair_target_entity "
    "repair_note reviewer"
).split()


async def _post_label(*, bearer, db, reviewer, admin_row=None):
    from app.routes.admin_judgments import RankingJudgmentCreate, create_judgment

    db.next_row = admin_row
    return await create_judgment(
        request=_request(bearer=bearer),
        payload=RankingJudgmentCreate(label="good", reviewer=reviewer),
        db=db,
        **{name: None for name in _QUERY_PARAMS},
    )


class TestRouteLevelSpecimens:
    @pytest.mark.asyncio
    async def test_identity_caller_cannot_name_a_foreign_reviewer(
        self, tokens, counting_verifier
    ):
        """[P2] finding 3, as executed: posted ``reviewer="victim@example.com"``
        and the committed row kept it."""
        db = RecordingDB()
        await _post_label(
            bearer=ADMIN_JWT,
            db=db,
            reviewer="victim@example.com",
            admin_row=FakeUser(id=1, email=ADMIN_EMAIL, is_admin=True),
        )

        assert db.committed and len(db.added) == 1
        row = db.added[0]
        assert row.reviewer == ADMIN_EMAIL, (
            f"The committed row is attributed to {row.reviewer!r}, which the "
            "CALLER chose, on a request authenticated as "
            f"{ADMIN_EMAIL!r}. reviewed-state and dedup key on this field."
        )
        # The metadata key was already correct before this queue; it must stay so.
        assert row.label_metadata.get("reviewer_identity") == ADMIN_EMAIL

    @pytest.mark.asyncio
    async def test_shared_token_write_does_not_verify_a_jwt(
        self, tokens, counting_verifier
    ):
        """[P2] finding 4, as executed: the token write recorded
        ``verify_calls=['shared-capability']``."""
        db = RecordingDB()
        await _post_label(bearer=BASE_TOKEN, db=db, reviewer="web")

        assert db.committed and len(db.added) == 1
        assert counting_verifier == [], (
            "A shared-ADMIN_TOKEN label write handed the token to the identity "
            f"verifier: {counting_verifier}. Before this feature the web "
            "writer's reviewer='web' never invoked identity resolution."
        )
        assert db.queries == 0, (
            "The shared-token write queried the database for a user row."
        )

    @pytest.mark.asyncio
    async def test_shared_token_write_keeps_its_surface_reviewer_and_gets_no_identity(
        self, tokens, counting_verifier
    ):
        """The other direction: absence is the honest encoding for the token."""
        db = RecordingDB()
        await _post_label(bearer=BASE_TOKEN, db=db, reviewer="web")

        row = db.added[0]
        assert row.reviewer == "web"
        assert "reviewer_identity" not in (row.label_metadata or {})
