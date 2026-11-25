"""Run the Factory tests and require every executable collect.py line."""

import dis
from pathlib import Path
import sys
import threading
from types import CodeType
import unittest


def executable_lines(code):
    lines = {
        instruction.starts_line
        for instruction in dis.get_instructions(code)
        if instruction.starts_line and instruction.opname not in {"RESUME", "RETURN_GENERATOR"}
    }
    for value in code.co_consts:
        if isinstance(value, CodeType):
            lines.update(executable_lines(value))
    return lines


def main():
    root = Path(__file__).resolve().parent
    source = root / "collect.py"
    filename = str(source)
    expected = executable_lines(compile(source.read_text(), filename, "exec"))
    seen = set()

    def trace(frame, event, arg):
        if frame.f_code.co_filename != filename:
            return None
        if event == "line":
            seen.add(frame.f_lineno)
        return trace

    threading.settrace(trace)
    sys.settrace(trace)
    try:
        tests = unittest.defaultTestLoader.discover(str(root / "tests"))
        result = unittest.TextTestRunner().run(tests)
    finally:
        sys.settrace(None)
        threading.settrace(None)

    missed = sorted(expected - seen)
    if missed:
        print("Uncovered collect.py lines:", ", ".join(map(str, missed)), file=sys.stderr)
    if not result.wasSuccessful() or missed:
        return 1
    print(f"Covered all {len(expected)} executable collect.py lines.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
