"""LAT-P071 (#1609): censusing a celery queue from BOTH ends, with its coverage.

The defect this replaces is not a crash. ``celery-debug`` reads
``lrange(queue, 0, 19)`` under the comment "Sample first 20 tasks from background
queue to see what's piled up", and that sentence is wrong twice:

* **Wrong end.** Kombu's redis transport publishes with ``lpush`` and consumes
  with ``rpop`` (verified against the installed kombu). Index 0 is therefore the
  newest ARRIVAL. The messages a starved beat is stuck behind are at the other
  end, and nothing in this tree had ever looked at them.
* **Wrong denominator.** 20 of 2,842 is a window at one end of an ordered list,
  not a sample. LAT-P066 said so in prose; the payload still just said
  ``{"warm_typeahead": 18}``, and a bare histogram gets read as a proportion.

So the tests below care about the coverage contract most: the census must always
be able to say how much of the queue it actually saw, and must never present a
partial read as a whole one.
"""

import json

import pytest

from app.routes.admin_celery import celery_queue_census


class _FakeRedis:
    """List semantics only — llen and lrange, exactly as the census uses them."""

    def __init__(self, lists):
        self.lists = lists

    def llen(self, key):
        return len(self.lists.get(key, []))

    def lrange(self, key, start, end):
        items = self.lists.get(key, [])
        if not items:
            return []
        # Redis lrange is inclusive of `end`, and -1 means the last element.
        n = len(items)
        s = start if start >= 0 else max(0, n + start)
        e = end if end >= 0 else n + end
        return items[s:e + 1]


def _msg(task):
    return json.dumps({"headers": {"task": task}, "body": ""})


def _run(lists, **kwargs):
    """Call the coroutine directly, with FastAPI's defaults supplied by hand.

    Calling a route function outside FastAPI leaves unbound params as their
    ``Query(...)`` objects, so every argument the body does arithmetic on must be
    passed explicitly or the test fails on a TypeError that has nothing to do
    with what it is testing.
    """
    from unittest.mock import patch

    import asyncio

    kwargs.setdefault("cap", 1000)
    r = _FakeRedis(lists)
    with patch("app.tasks.redis_state.get_redis_client", return_value=r), \
         patch("app.routes.admin_celery._check_admin_secret", return_value=None):
        return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            celery_queue_census(request=None, secret="x", **kwargs)
        )


class TestCoverageIsAlwaysStated:
    def test_a_truncated_read_says_so_and_reports_its_percentage(self):
        # The whole point. A histogram over 200 of 1,000 messages must not be
        # readable as a description of the queue.
        lists = {"background": [_msg("app.tasks.warm_typeahead")] * 1000}
        out = _run(lists, queue="background", cap=200)
        assert out["depth"] == 1000
        assert out["coverage"]["truncated"] is True
        assert out["coverage"]["complete"] is False
        assert out["coverage"]["examined"] == 200
        assert out["coverage"]["pct"] == 20.0

    def test_a_cap_above_the_depth_is_complete_not_double_counted(self):
        # Both slices overlap once cap exceeds depth. Summing them would report
        # 120% coverage, which is the kind of number that discredits a surface.
        lists = {"background": [_msg("app.tasks.a")] * 30}
        out = _run(lists, queue="background", cap=1000)
        assert out["coverage"]["complete"] is True
        assert out["coverage"]["examined"] == 30
        assert out["coverage"]["pct"] == 100.0
        assert out["coverage"]["truncated"] is False

    def test_a_cap_exactly_equal_to_the_depth_is_complete(self):
        # Found by mutation: every other coverage test used a cap far above the
        # depth, so `cap >= depth` and `cap > depth` were indistinguishable.
        # The boundary is where a census either admits it saw everything or
        # under-reports itself by one message forever.
        lists = {"background": [_msg("app.tasks.a")] * 30}
        out = _run(lists, queue="background", cap=30)
        assert out["coverage"]["complete"] is True
        assert out["coverage"]["examined"] == 30
        assert out["coverage"]["truncated"] is False

    def test_an_empty_queue_reports_no_coverage_rather_than_100_percent(self):
        # Gotcha #53: an empty read is a shape, not a fact. "100% examined" on a
        # queue with nothing in it is a claim about a population that does not
        # exist.
        out = _run({"background": []}, queue="background")
        assert out["depth"] == 0
        assert out["coverage"]["pct"] is None
        assert out["coverage"]["truncated"] is False
        assert out["next_to_be_served"] is None


class TestBothEnds:
    def _mixed(self):
        # Oldest (served next) at the tail; newest arrivals at the head.
        return {"background":
                [_msg("app.tasks.warm_typeahead")] * 40   # newest arrivals
                + [_msg("app.tasks.turbo_collapse_futures")] * 20}  # the wall

    def test_the_two_ends_are_reported_separately(self):
        out = _run(self._mixed(), queue="background", cap=20)
        assert out["newest_end"] == {"app.tasks.warm_typeahead": 10}
        assert out["oldest_end"] == {"app.tasks.turbo_collapse_futures": 10}

    def test_next_to_be_served_is_the_tail_not_the_head(self):
        # rpop. If this ever reports the head, every conclusion drawn about who
        # a starved beat is waiting behind inverts.
        #
        # Found by mutation: with a UNIFORM tail slice, `oldest_names[0]` and
        # `oldest_names[-1]` name the same task, so swapping them changed
        # nothing and the assertion proved only that the tail exists. The very
        # last element must therefore be distinct from the rest of its own
        # slice, or this test cannot tell the two ends of the SLICE apart —
        # which is a different question from telling the two ends of the QUEUE
        # apart, and the one that actually has a wrong answer available.
        lists = {"background":
                 [_msg("app.tasks.warm_typeahead")] * 40
                 + [_msg("app.tasks.turbo_collapse_futures")] * 9
                 + [_msg("app.tasks.the_actual_next_one")]}
        out = _run(lists, queue="background", cap=20)
        assert out["next_to_be_served"] == "app.tasks.the_actual_next_one"
        assert out["oldest_end"]["app.tasks.turbo_collapse_futures"] == 9

    def test_a_uniform_queue_looks_uniform_from_both_ends(self):
        lists = {"background": [_msg("app.tasks.warm_typeahead")] * 500}
        out = _run(lists, queue="background", cap=100)
        assert out["oldest_end"] == out["newest_end"]


class TestDepthAccounting:
    def test_priority_sibling_keys_are_counted_into_the_depth(self):
        # An under-count here reads as "the backlog cleared".
        lists = {
            "background": [_msg("app.tasks.a")] * 10,
            "background\x06\x163": [_msg("app.tasks.b")] * 5,
        }
        out = _run(lists, queue="background", cap=1000)
        assert out["depth"] == 15
        assert len(out["depth_by_key"]) == 2

    def test_composition_is_only_claimed_for_the_base_key(self):
        # The sibling's contents are NOT folded into the histograms — they are
        # reported as a depth. Guessing a priority queue's composition from the
        # base key's would be inventing the number this endpoint exists to stop
        # inventing.
        lists = {
            "background": [_msg("app.tasks.a")] * 10,
            "background\x06\x163": [_msg("app.tasks.b")] * 5,
        }
        out = _run(lists, queue="background", cap=1000)
        assert "app.tasks.b" not in out["oldest_end"]
        assert "app.tasks.b" not in out["newest_end"]
        # ...and because it is not folded in, the read is NOT complete.
        assert out["coverage"]["examined"] == 10
        assert out["coverage"]["of_depth"] == 15


class TestUnparseableMessages:
    def test_a_bad_body_is_counted_not_dropped(self):
        # A census whose denominator moves is not a census.
        lists = {"background": [_msg("app.tasks.a"), "{not json", _msg("app.tasks.a")]}
        out = _run(lists, queue="background", cap=1000)
        assert out["newest_end"]["parse_error"] == 1
        assert sum(out["newest_end"].values()) == 3

    def test_a_body_with_no_task_header_is_unknown_not_dropped(self):
        lists = {"background": [json.dumps({"headers": {}, "body": ""})]}
        out = _run(lists, queue="background", cap=1000)
        assert out["newest_end"] == {"unknown": 1}


class TestBounds:
    @pytest.mark.parametrize("bad", [10, 5000])
    def test_the_cap_is_bounded_by_the_signature(self, bad):
        # FastAPI enforces ge/le at the boundary; assert the declared bounds so
        # a future widening is a deliberate edit and not a default drifting.
        import inspect
        sig = inspect.signature(celery_queue_census)
        bounds = {}
        for c in sig.parameters["cap"].default.metadata:
            for name in ("ge", "le"):
                if hasattr(c, name):
                    bounds[name] = getattr(c, name)
        assert bounds == {"ge": 20, "le": 4000}
        assert not (bounds["ge"] <= bad <= bounds["le"])
