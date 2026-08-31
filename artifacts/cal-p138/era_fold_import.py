"""Import CAL-P137's ``era-fold.py`` under a name Python will accept.

The file is named with a hyphen, so it is not importable as a module, and the
alternative to this six-line loader is copying ``_min_flips`` into this queue —
which is exactly the drift ``self_check`` exists to rule out. Loading the real
file means the self-check compares against the function that produced CAL-P137's
published histogram, not against a copy of it that has already diverged.
"""
import importlib.util
import os

_PATH = os.path.join(os.path.dirname(__file__), "..", "cal-p137", "era-fold.py")
_spec = importlib.util.spec_from_file_location("cal_p137_era_fold", _PATH)
era_fold = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(era_fold)

min_flips = era_fold._min_flips
