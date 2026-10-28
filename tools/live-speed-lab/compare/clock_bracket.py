"""Lab-only retained PM target adapter; no network, source policy, or generic scorer."""
import math


def eligible_interval(target, run, received_at, uncertainty, *, stable_backend_clock=False):
    def unknown(reason):
        return {'status': 'timing_unknown', 'reason': reason}
    def finite(x):
        return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
    if not isinstance(target, dict) or not isinstance(run, dict):
        return unknown('invalid target/run evidence')
    if stable_backend_clock is not True:
        return unknown('explicit stable backend clock assumption required')
    if target.get('source') != 'polymarket' or target.get('mono') != run.get('target_sent_mono'):
        return unknown('target identity/anchor mismatch')
    values = [target.get('mono'), run.get('target_sent_mono'), run.get('target_sent_wall_ms'), received_at, uncertainty]
    if not all(finite(x) for x in values) or uncertainty < 0:
        return unknown('invalid numeric clock evidence')
    frames = target.get('frames')
    if not isinstance(frames, list) or len(frames) != 2:
        return unknown('expected frozen two-leg PM input')
    stamps = []
    for frame in frames:
        if not isinstance(frame, dict):
            return unknown('invalid frame evidence')
        value = frame.get('timestamp')
        if frame.get('event_type') != 'best_bid_ask' or not isinstance(value, str) or not value.isascii() or not value.isdigit():
            return unknown('missing integer pre-send wire clock')
        stamp = int(value)
        if stamp <= 0 or stamp > run['target_sent_wall_ms']:
            return unknown('invalid/inverted clock bracket')
        stamps.append(stamp)
    delta = run['target_sent_wall_ms'] - max(stamps)
    # Do not clip at sample start: crossing the boundary is unsupported by the
    # existing score contract and must not silently narrow the uncertainty.
    earliest, latest = received_at - uncertainty - delta, received_at + uncertainty
    if earliest < 0:
        return unknown('clock interval crosses sample start')
    return {'status': 'conditional_interval', 'at_ms': [earliest, latest],
            'anchor_lateness_ms': [0, delta],
            'assumption': 'no backend wall-clock step; stable wall/monotonic mapping over the used interval'}
