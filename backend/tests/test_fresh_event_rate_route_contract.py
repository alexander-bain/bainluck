"""#9365 / #9349: real event routes must retain their bounded fresh-read budget.

Adapted from Shopper's offered TestTheBoundaryMatchesTheRealRouteTable guard at
6aab858456. The behavior tests mount small routes; these checks bind that policy
to the production route table without making any requests or querying a DB.
"""
import re

from fastapi.routing import APIRoute

from app.utils import rate_limit


class TestTheBoundaryMatchesTheRealRouteTable:
    @staticmethod
    def _get_routes():
        from app.main import app

        return [r for r in app.routes if isinstance(r, APIRoute) and "GET" in r.methods]

    def test_exactly_the_two_polled_routes_fall_inside_the_pattern(self):
        inside = sorted(
            {
                route.path
                for route in self._get_routes()
                if re.fullmatch(
                    rate_limit._FRESH_EVENT_PATH,
                    re.sub(r"\{[^}]+\}", "123", route.path),
                )
            }
        )
        assert inside == ["/api/events/{event_id}", "/api/events/{event_id}/history"]

    def test_both_polled_routes_consume_the_same_optional_boolean_fresh_query(self):
        by_path = {route.path: route for route in self._get_routes()}
        for path in ("/api/events/{event_id}", "/api/events/{event_id}/history"):
            params = {p.name: p for p in by_path[path].dependant.query_params}
            assert "fresh" in params, f"{path} no longer takes `fresh`"
            fresh = params["fresh"]
            assert fresh.field_info.annotation is bool, path
            assert fresh.alias == "fresh", path
            assert fresh.default is False and not fresh.field_info.is_required(), path
