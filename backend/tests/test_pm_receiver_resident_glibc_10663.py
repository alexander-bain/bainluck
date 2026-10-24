"""#10663 — the receiver child's resident memory, measured on the production allocator.

The deciding control for ``test_pm_receiver_resident_state_10663``'s changes.
Both arms run ``_pm_receiver_memory_rig_10663.py`` at production size (67,926
ids over ~136 TLS sockets, a full book per id at subscribe, live frames), at
the same time on the same runner:

* parent: the child's three files as production runs them (``d39b3bcfbf``,
  #11448, the last commit to touch any of them before this change);
* candidate: this tree.

The reading is the child's own ``heap trim: arm=polymarket_open_receiver ...
rss=a->b`` line, the line production logs every ~61 s, plus its VmRSS at the
end. Fidelity is checked first: an arm that served fewer ids or delivered far
fewer prices could hold less for that reason alone, so it fails here instead.
The numbers are stated on a green run too (CI prints the warnings summary).
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import warnings

import pytest

GLIBC = sys.platform.startswith("linux") and os.confstr("CS_GNU_LIBC_VERSION") is not None
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(BACKEND)
RIG = os.path.join(BACKEND, "tests", "_pm_receiver_memory_rig_10663.py")
PARENT_SHA = "d39b3bcfbf79681cf405e77b18687ecb58a44d76"
CHILD_FILES = (
    "backend/app/services/polymarket_ws.py",
    "backend/app/services/polymarket_ws_process.py",
    "backend/app/utils/heap_trim.py",
)
SECONDS, IDS = 135, 67_926
TRIM = re.compile(
    r"heap trim: arm=polymarket_open_receiver released=([0-9.]+)MB "
    r"rss=([0-9.]+)->([0-9.]+)MB"
)


def _parent_tree(directory):
    for path in CHILD_FILES:
        shown = subprocess.run(["git", "-C", REPO, "show", f"{PARENT_SHA}:{path}"],
                               capture_output=True)
        # A missing parent is a failed lab, never a skip.
        assert shown.returncode == 0, (path, shown.stderr.decode()[-300:])
        target = os.path.join(directory, path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(shown.stdout)
    return os.path.join(directory, "backend")


def _start(backend):
    return subprocess.Popen(
        [sys.executable, RIG, "arm", backend, str(SECONDS), str(IDS)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )


def _finish(proc):
    out, err = proc.communicate(timeout=SECONDS + 240)
    assert proc.returncode == 0, err[-3000:]
    result = json.loads(out.strip().splitlines()[-1])
    result["trims"] = [tuple(float(x) for x in m) for m in TRIM.findall(err)]
    return result


@pytest.mark.skipif(not GLIBC, reason="the production allocator is glibc's")
def test_the_receiver_child_holds_less_at_the_same_coverage():
    with tempfile.TemporaryDirectory() as tmp:
        parent_backend = _parent_tree(tmp)
        arms = {"parent": _start(parent_backend), "candidate": _start(BACKEND)}
        parent, candidate = (_finish(arms[k]) for k in ("parent", "candidate"))

    def line(r):
        return (f"post-trim rss MB={[t[2] for t in r['trims']]} released MB="
                f"{[t[0] for t in r['trims']]} end={r['end']} samples={r['rss_samples']}"
                f" served={r['served']}/{r['n']} shards={r['shards_connected']}/"
                f"{r['shards']} prices={r['prices']} msgs={r['messages']}")

    summary = f"parent({PARENT_SHA[:10]}): {line(parent)} | candidate: {line(candidate)}"
    warnings.warn(f"#10663 receiver child glibc control: {summary}")

    # Fidelity first: the same coverage and comparable delivery in both arms.
    for arm in (parent, candidate):
        assert arm["served"] == arm["n"] == IDS, summary
        assert arm["shards_connected"] == arm["shards"] > 100, summary
        assert arm["trims"], summary  # the production reading exists
    assert abs(candidate["prices"] - parent["prices"]) < 0.15 * parent["prices"], summary

    # The claim: the child's post-trim resident memory, the production line.
    parent_rss, candidate_rss = parent["trims"][-1][2], candidate["trims"][-1][2]
    assert candidate_rss < parent_rss - 25, summary
    assert candidate["end"]["VmRSS"] < parent["end"]["VmRSS"] - 25, summary
