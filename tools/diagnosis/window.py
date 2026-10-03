"""Open or reuse the diagnosis Terminal view without duplicating the worker."""
import fcntl
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path.home() / "bainluck-diagnosis"
TITLE = "TBH diagnosis"
SCRIPT = """
on run argv
    set commandText to item 1 of argv
    set windowTitle to item 2 of argv
    tell application "Terminal"
        repeat with w in windows
            repeat with t in tabs of w
                if custom title of t is windowTitle then
                    if not busy of t then do script commandText in t
                    set index of w to 1
                    activate
                    return "Diagnosis window reused."
                end if
            end repeat
        end repeat
        set t to do script commandText
        set custom title of t to windowTitle
        activate
        return "Diagnosis window opened."
    end tell
end run
"""


def main():
    ROOT.mkdir(exist_ok=True)
    with (ROOT / "window.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        subprocess.run([sys.executable, str(Path(__file__).with_name("service.py")), "start"], check=True)
        command = shlex.join([sys.executable, "-u", str(Path(__file__).with_name("monitor.py"))])
        subprocess.run(["osascript", "-", command, TITLE], input=SCRIPT, text=True, check=True)


if __name__ == "__main__":
    main()
