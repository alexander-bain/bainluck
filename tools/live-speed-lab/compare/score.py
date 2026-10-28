"""Interval-valued display debt. Inputs are eligible blend states, never raw ticks."""
import math

SURFACES = ("headline", "chart")


def interval(value):
    if (not isinstance(value, list) or len(value) != 2
            or any(isinstance(x, bool) or not isinstance(x, (int, float))
                   or not math.isfinite(x) for x in value) or value[0] > value[1]):
        raise ValueError("expected finite [earliest, latest] milliseconds")
    return value


def union_ms(ranges):
    total, end = 0.0, -math.inf
    for start, stop in sorted(ranges):
        if stop > max(start, end):
            total += stop - max(start, end)
        end = max(end, stop)
    return total


def score(trace):
    """Union outstanding intervals: overlapping/superseded work counts once.

    A displayed successor covers predecessors ONLY through explicit supersedes
    edges supplied by the real selection/reader adapter. Equal values do not
    imply coverage. Unknown coverage is never scored as zero delay or a pass.
    """
    start, end = interval(trace["window_ms"])
    obligations = trace["eligible"]
    by_id = {o["id"]: o for o in obligations}
    if len(by_id) != len(obligations):
        raise ValueError("duplicate eligible identity")
    for o in obligations:
        a, b = interval(o["at_ms"])
        if a < start or b > end:
            raise ValueError("eligible identity outside measured window")
        if not o.get("evidence"):
            raise ValueError("eligibility needs evidence")
        if not o.get("stream"):
            raise ValueError("eligibility needs a stream identity")
    for display in trace["displays"]:
        if display["surface"] not in SURFACES:
            raise ValueError("unknown display surface")
    def predecessors(identity, seen=None):
        seen = set() if seen is None else seen
        if identity not in by_id or identity in seen:
            raise ValueError("unknown or cyclic supersession")
        o = by_id[identity]
        covered = {identity}
        for prior in o.get("supersedes", []):
            if by_id.get(prior, {}).get("stream") != o.get("stream"):
                raise ValueError("supersession crosses event/source authority")
            if by_id.get(prior, {}).get("at_ms", [math.inf])[0] > o["at_ms"][0]:
                raise ValueError("supersession moves backwards")
            covered |= predecessors(prior, seen | {identity})
        return covered
    closure = {identity: predecessors(identity) for identity in by_id}
    violations = list(trace.get("violations", []))
    result = {"coverage": trace["coverage"], "checks": trace["checks"],
              "violations": violations, "surfaces": {}}
    for surface in SURFACES:
        seen = {}
        for d in sorted(trace["displays"], key=lambda x: x["at_ms"][1]):
            lo, hi = interval(d["at_ms"])
            if d["surface"] != surface:
                continue
            if lo < start or hi > end:
                raise ValueError("display outside measured window")
            for identity in d["covers"]:
                if identity not in closure:
                    raise ValueError("display names unknown eligible state")
                for prior in closure[identity]:
                    if hi < by_id[prior]["at_ms"][0]:
                        raise ValueError("display precedes eligible input")
                    if prior in seen:
                        first_lo, first_hi, via = seen[prior]
                        # Sorted by hi: retain the earliest proven upper bound
                        # and its witness, but overlapping records can widen lo.
                        seen[prior] = (min(lo, first_lo), first_hi, via)
                    else:
                        seen[prior] = (lo, hi, identity)
        lower, upper, delays = [], [], []
        missing, coalesced = [], []
        within, over, uncertain = 0, 0, 0
        for identity, o in by_id.items():
            arrival_lo, arrival_hi = o["at_ms"]
            display_lo, display_hi, via = seen.get(identity, (end, end, None))
            lower.append((arrival_hi, max(arrival_hi, display_lo)))
            upper.append((arrival_lo, max(arrival_lo, display_hi)))
            bounds = [max(0, display_lo-arrival_hi), max(0, display_hi-arrival_lo)]
            if via is None:
                missing.append(identity)
                disposition = "unresolved_at_end"
            elif via != identity:
                coalesced.append(identity)
                disposition = "covered_by_successor"
            else:
                disposition = "displayed"
            # Count coalesced states separately, not as additional rendered updates.
            if via == identity:
                if bounds[1] < 1000:
                    within += 1
                elif bounds[0] >= 1000:
                    over += 1
                else:
                    uncertain += 1
            elif via is None:
                if bounds[0] >= 1000:
                    over += 1
                else:
                    uncertain += 1
            delays.append({"id": identity, "delay_ms": bounds, "via": via,
                           "disposition": disposition})
        denominator = len(obligations)-len(coalesced)
        result["surfaces"][surface] = {
            "worst_delay_ms": [max((x["delay_ms"][i] for x in delays), default=0)
                               for i in (0, 1)] if obligations else None,
            "cumulative_trailing_ms": [union_ms(lower), union_ms(upper)] if obligations else None,
            "under_one_second": {"definite": within, "over": over, "uncertain": uncertain,
                                 "denominator": denominator,
                                 "percent_bounds": [100*within/denominator,
                                                    100*(within+uncertain)/denominator]
                                 if denominator else None},
            "unresolved_at_end": missing, "coalesced": coalesced, "updates": delays,
        }
    # Both must catch up. Union across surfaces avoids charging the same wait twice.
    joint_lower, joint_upper = [], []
    for o in obligations:
        a, b = o["at_ms"]
        delays = [next(x for x in result["surfaces"][s]["updates"] if x["id"] == o["id"])
                  for s in SURFACES]
        joint_lower.append((b, b+max(x["delay_ms"][0] for x in delays)))
        joint_upper.append((a, a+max(x["delay_ms"][1] for x in delays)))
    result["both_surfaces_cumulative_trailing_ms"] = (
        [union_ms(joint_lower), union_ms(joint_upper)] if obligations else None)
    result["worst_is_lower_bound"] = any(result["surfaces"][s]["unresolved_at_end"] for s in SURFACES)
    return result


def decide(baseline, candidate, valid=True):
    if not valid:
        return "experiment_invalid"
    if candidate["violations"]:
        return "no_improvement_or_regression"
    # A shorter recording cannot manufacture a gain by censoring a late state.
    # Retain the debt score, but require completed matched cohorts to decide.
    if baseline["worst_is_lower_bound"] or candidate["worst_is_lower_bound"]:
        return "experiment_invalid"
    for surface in SURFACES:
        if {x["id"] for x in baseline["surfaces"][surface]["updates"]} != {
            x["id"] for x in candidate["surfaces"][surface]["updates"]
        }:
            return "experiment_invalid"
    gains, regressions = [], []
    for surface in SURFACES:
        for metric in ("worst_delay_ms", "cumulative_trailing_ms"):
            b = baseline["surfaces"][surface][metric]
            c = candidate["surfaces"][surface][metric]
            if b is None or c is None:
                return "experiment_invalid"
            gains.append(c[1] < b[0])
            regressions.append(c[0] > b[1])
    if any(regressions):
        return "no_improvement_or_regression"
    if any(gains):
        return "improvement_supported"
    return "no_improvement_demonstrated"
