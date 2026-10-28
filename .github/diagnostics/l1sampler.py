"""#11681 diagnostic-only host sampler (branch diag/10090-11681-hosted-timing). DIAGNOSTIC ONLY, DO NOT MERGE.

Every 100 ms it appends one CSV row: epoch, the aggregate /proc/stat cpu fields
(including iowait and steal), /proc/pressure/cpu "some"/"full" stall totals (µs),
load1, and the postgres service container's cgroup cpu.stat usage/throttled
(µs) when that file is found. Usage: l1sampler.py OUT.csv CGROUP_CPU_STAT|- MAX_S
"""

import sys
import time

out, cgroup, max_s = sys.argv[1], sys.argv[2], float(sys.argv[3])


def read(path):
    try:
        with open(path) as fh:
            return fh.read()
    except OSError:
        return ""


def pressure(text, kind):
    for line in text.splitlines():
        if line.startswith(kind):
            return line.rsplit("total=", 1)[-1]
    return ""


def cg(text, key):
    for line in text.splitlines():
        name, _, value = line.partition(" ")
        if name == key:
            return value
    return ""


stop = time.monotonic() + max_s
with open(out, "w", buffering=1) as fh:
    fh.write(
        "epoch,user,nice,system,idle,iowait,irq,softirq,steal,"
        "psi_some_us,psi_full_us,load1,pg_usage_us,pg_throttled_us\n"
    )
    while time.monotonic() < stop:
        cpu = read("/proc/stat").split("\n", 1)[0].split()[1:9]
        psi = read("/proc/pressure/cpu")
        cgt = read(cgroup) if cgroup != "-" else ""
        fh.write(
            ",".join(
                [f"{time.time():.3f}", *cpu, pressure(psi, "some"), pressure(psi, "full"),
                 read("/proc/loadavg").split(" ", 1)[0],
                 cg(cgt, "usage_usec"), cg(cgt, "throttled_usec")]
            )
            + "\n"
        )
        time.sleep(0.1)
