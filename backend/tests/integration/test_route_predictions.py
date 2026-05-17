"""Contract tests for prediction stats endpoints."""

from types import SimpleNamespace

from app.dependencies.auth import get_optional_user
from app.routes.predictions import _identity_filter


class _Result:
    def __init__(self, one=None, all_rows=None):
        self._one = one
        self._all_rows = all_rows or []

    def one(self):
        return self._one

    def all(self):
        return self._all_rows


class _Session:
    def __init__(self):
        self.statements = []
        self._results = [
            _Result(one=SimpleNamespace(total=2, correct=1)),
            _Result(all_rows=[SimpleNamespace(cat="sports", total=2, correct=1)]),
            _Result(all_rows=[]),
            _Result(all_rows=[SimpleNamespace(correct=True), SimpleNamespace(correct=False)]),
            _Result(all_rows=[]),
        ]

    async def execute(self, statement):
        self.statements.append(str(statement))
        return self._results.pop(0)


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


async def test_detailed_stats_uses_authenticated_user_without_session_id(client, monkeypatch):
    """Signed-in native users should not need the anonymous session id to see stats."""
    from app.main import app
    from app.routes import predictions

    user = SimpleNamespace(id=42)
    session = _Session()

    async def _mock_get_optional_user():
        return user

    try:
        app.dependency_overrides[get_optional_user] = _mock_get_optional_user
        monkeypatch.setattr(predictions, "get_session", lambda: _SessionContext(session))

        resp = await client.get("/api/predictions/detailed-stats")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["correct"] == 1
        assert body["by_category"]["sports"]["total"] == 2
        assert session.statements
        assert all("user_predictions.user_id" in statement for statement in session.statements)
        assert all("user_predictions.id <" not in statement for statement in session.statements)
    finally:
        app.dependency_overrides.pop(get_optional_user, None)


def test_prediction_identity_filter_keeps_current_session_for_signed_in_user():
    statement = str(_identity_filter(user_id=42, session_id="native-session"))

    assert "user_predictions.user_id" in statement
    assert "user_predictions.session_id" in statement
    assert " OR " in statement
