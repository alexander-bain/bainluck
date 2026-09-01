"""CAL-P190 probe v2 — three digests at one commit, JSON on one line.

wide   : `_main_input_fingerprint()`  — what invalidates the bank TODAY.
sql    : md5 of the whole emitted frozen statement — what actually shapes a
         banked unit's rows.
cols   : md5 of the emitted statement's FINAL SELECT LIST, comments stripped and
         whitespace collapsed — what shapes the banked row's SHAPE, i.e. the
         thing a consumer written after the pin could find missing.

Every failure is named. A commit that cannot answer is a hole in the sweep, never
a silent "no change".
"""
import hashlib
import json
import re
import sys

out = {"wide": None, "sql": None, "cols": None, "ncols": None, "error": None}


def _md5(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()


try:
    from app.tasks import precompute_calibration as pc

    out["wide"] = pc._main_input_fingerprint()
    try:
        sql = pc._main_futures_sql(frozen=True)
        out["sql"] = _md5(sql)
        i = sql.rfind("SELECT bucket_idx")
        if i < 0:
            out["error"] = "cols:no_final_select"
        else:
            tail = sql[i:]
            j = tail.find("GROUP BY")
            select_list = tail[:j] if j > 0 else tail
            # Comments are prose; a docstring edit inside the SELECT list must
            # not read as a row-shape change.
            select_list = re.sub(r"--[^\n]*", "", select_list)
            select_list = re.sub(r"\s+", " ", select_list).strip()
            out["cols"] = _md5(select_list)
            out["ncols"] = len(re.findall(r"\bAS [a-zA-Z_]", select_list))
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"sql:{type(exc).__name__}:{exc}"[:200]
except Exception as exc:  # noqa: BLE001
    out["error"] = f"import:{type(exc).__name__}:{exc}"[:200]

print(json.dumps(out))
