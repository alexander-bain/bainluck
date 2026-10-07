"""Exact CI command replay and source gates on one owned UNIX-only PG."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import yaml

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BIN = Path("/opt/homebrew/opt/postgresql@17/bin")
sdk = Path(json.loads((OUT / "owned-env.json").read_text())["path"])
cluster = Path(tempfile.mkdtemp(prefix="kalshi10693-prod-pg-"))
sock = cluster / "socket"
sock.mkdir()
python_bin = cluster / "python-bin"
python_bin.mkdir()
(python_bin / "python").symlink_to(sys.executable)
receipt = {
    "started_at": time.time(),
    "cluster": str(cluster),
    "sdk_env": str(sdk),
    "listen_addresses": "",
    "gates": [],
}
started = False
try:
    with (OUT / "lifecycle-log.txt").open("w") as log:
        subprocess.run(
            [
                str(BIN / "initdb"),
                "-D",
                str(cluster / "data"),
                "-A",
                "trust",
                "--no-locale",
                "-E",
                "UTF8",
            ],
            stdout=log,
            stderr=log,
            check=True,
        )
        subprocess.run(
            [
                str(BIN / "pg_ctl"),
                "-D",
                str(cluster / "data"),
                "-l",
                str(cluster / "server.log"),
                "-o",
                f"-k {sock} -p 55534 -h '' -c shared_buffers=16MB -c max_connections=30",
                "-w",
                "start",
            ],
            stdout=log,
            stderr=log,
            check=True,
        )
        started = True
    env = dict(
        os.environ,
        PATH=str(python_bin) + os.pathsep + os.environ["PATH"],
        DATABASE_URL="postgresql+asyncpg://localhost/private_unused",
        SEARCH_TEST_DATABASE_URL=f"postgresql+asyncpg://@/postgres?host={sock}&port=55534",
    )
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["database-integration"]["steps"]
    for pair, name in [
        (
            "production",
            "#10693 guarded Kalshi pipeline production pair (real Postgres)",
        ),
        ("floor", "#10693 guarded Kalshi pipeline supported floor (real Postgres)"),
    ]:
        step = next(step for step in steps if step.get("name") == name)
        with (OUT / f"ci-{pair}.txt").open("w") as log:
            run = subprocess.run(
                ["bash", "-eu", "-c", step["run"]],
                cwd=ROOT / "backend",
                env=env,
                stdout=log,
                stderr=log,
                timeout=240,
            )
        receipt["gates"].append({"log": f"ci-{pair}.txt", "exit_code": run.returncode})
        print(pair, run.returncode, flush=True)
        if run.returncode:
            raise SystemExit(run.returncode)
    files = [
        "tests/test_kalshi_price_statement_10689.py",
        "tests/test_price_change_stamp.py",
        "tests/integration/test_kalshi_price_statement_10689_pg.py",
        "tests/test_ci_postgres_groups.py",
        "tests/test_startup.py",
    ]
    with (OUT / "production-source-affected.txt").open("w") as log:
        run = subprocess.run(
            [str(sdk / "bin/python"), "-m", "pytest", *files, "-v", "-rs"],
            cwd=ROOT / "backend",
            env=env,
            stdout=log,
            stderr=log,
            timeout=240,
        )
    receipt["gates"].append(
        {"log": "production-source-affected.txt", "exit_code": run.returncode}
    )
    print("production-source-affected", run.returncode, flush=True)
    if run.returncode:
        raise SystemExit(run.returncode)
finally:
    if started:
        with (OUT / "lifecycle-log.txt").open("a") as log:
            stop = subprocess.run(
                [
                    str(BIN / "pg_ctl"),
                    "-D",
                    str(cluster / "data"),
                    "-m",
                    "immediate",
                    "-w",
                    "stop",
                ],
                stdout=log,
                stderr=log,
                timeout=30,
            )
            receipt["pg_stop_exit"] = stop.returncode
    shutil.rmtree(cluster)
    shutil.rmtree(sdk)
    receipt["cluster_removed"] = not cluster.exists()
    receipt["sdk_env_removed"] = not sdk.exists()
    receipt["ended_at"] = time.time()
    (OUT / "lifecycle.json").write_text(json.dumps(receipt, indent=2) + "\n")
