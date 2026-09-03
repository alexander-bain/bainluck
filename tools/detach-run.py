#!/usr/bin/env python3
"""detach-run.py — run a command so it outlives this session. The macOS stand-in for `setsid nohup`.

Standing notice 17 says anything that must outlive a session is `setsid nohup`'d. **There is no
`setsid` on macOS** — `which setsid` is empty on this Mac — so that line cannot be typed literally,
and a lane that types it gets `command not found` and an unarmed watcher it believes is armed.

This does what the notice means: double-fork, `os.setsid()` between the forks so the child leads a new
session with no controlling terminal, redirect stdio to a log, and let the grandchild be reparented to
init. SIGHUP at session teardown cannot reach it, and it is not in the launching shell's process group,
so a process-group kill of the agent session leaves it running.

    python3 tools/detach-run.py /tmp/x/out.log bash tools/watch-migration-deploy.sh

Prints the detached pid on stdout. Check it later with `ps -p <pid>`.
"""
import os
import sys

if len(sys.argv) < 3:
    sys.exit("usage: detach-run.py <logfile> <command> [args...]")

logfile, argv = sys.argv[1], sys.argv[2:]
os.makedirs(os.path.dirname(logfile) or ".", exist_ok=True)

read_fd, write_fd = os.pipe()  # the grandchild's pid has to get back to the caller somehow

if os.fork() > 0:
    os.close(write_fd)
    with os.fdopen(read_fd) as r:
        print(r.read().strip())
    os.wait()  # reap the intermediate child immediately; it exits at once
    sys.exit(0)

os.close(read_fd)
os.setsid()  # new session, no controlling terminal — this is the part `nohup &` alone does not do

pid = os.fork()
if pid > 0:
    os.write(write_fd, str(pid).encode())
    os._exit(0)  # intermediate parent dies here, so the grandchild is reparented to init

os.close(write_fd)
# 0o600: the log can carry whatever the detached command prints, which for a watcher includes
# response bodies. Owner-only, not world-readable.
fd = os.open(logfile, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
devnull = os.open(os.devnull, os.O_RDONLY)
os.dup2(devnull, 0)
os.dup2(fd, 1)
os.dup2(fd, 2)
# The dup2'd copies are what the exec'd process inherits; the originals are surplus descriptors.
os.close(fd)
os.close(devnull)
os.execvp(argv[0], argv)
