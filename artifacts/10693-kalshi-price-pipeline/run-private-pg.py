"""Finite owned UNIX-only PG gate; never touches the shared server."""

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
cluster = Path(tempfile.mkdtemp(prefix="kalshi10693-pg-"))
sock = cluster / "socket"
sock.mkdir()
python_bin = cluster / "python-bin"
python_bin.mkdir()
(python_bin / "python").symlink_to(sys.executable)
port = "55534"
started = False
receipt = {
    "started_at": time.time(),
    "cluster": str(cluster),
    "port": port,
    "listen_addresses": "",
    "gates": [],
}
try:
    with (OUT / "pg-lifecycle.log").open("a") as log:
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
                f"-k {sock} -p {port} -h '' -c shared_buffers=16MB -c max_connections=30",
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
        SEARCH_TEST_DATABASE_URL=f"postgresql+asyncpg://@/postgres?host={sock}&port={port}",
    )
    targets = [
        (
            "unit-pg-startup.txt",
            [
                "tests/test_kalshi_price_pipeline_10693.py",
                "tests/integration/test_kalshi_price_pipeline_10693_pg.py",
                "tests/test_startup.py",
            ],
        ),
        (
            "source-affected.txt",
            [
                "tests/test_kalshi_price_statement_10689.py",
                "tests/test_price_change_stamp.py",
                "tests/test_ci_postgres_groups.py",
                "tests/test_price_stamp_writer_scan_4958.py",
                "tests/test_futures_rank_field_wide_6598.py",
                "tests/test_ws_market_change_hooks_9484.py",
                "tests/test_ws_open_contract_prices_9484.py",
                "tests/test_ws_kalshi_linked_first_10640.py",
                "tests/integration/test_ws_quote_moved_9484_pg.py",
                "tests/integration/test_kalshi_price_statement_10689_pg.py",
            ],
        ),
    ]
    if sys.argv[1:] == ["--ci-only"]:
        targets = []
    elif sys.argv[1:]:
        raise ValueError("only --ci-only is supported")
    for name, files in targets:
        with (OUT / name).open("w") as log:
            result = subprocess.run(
                ["python3", "-m", "pytest", *files, "-v", "-rs"],
                cwd=ROOT / "backend",
                env=env,
                stdout=log,
                stderr=log,
                timeout=240,
            )
        receipt["gates"].append({"log": name, "exit_code": result.returncode})
        print(name, result.returncode, flush=True)
        if result.returncode:
            raise SystemExit(result.returncode)
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    step = next(
        step
        for step in workflow["jobs"]["database-integration"]["steps"]
        if step.get("name")
        == "#10693 guarded Kalshi pipeline supported floor (real Postgres)"
    )
    with (OUT / "ci-floor-command.txt").open("w") as log:
        result = subprocess.run(
            ["bash", "-eu", "-c", step["run"]],
            cwd=ROOT / "backend",
            env=env,
            stdout=log,
            stderr=log,
            timeout=240,
        )
    receipt["gates"].append(
        {"log": "ci-floor-command.txt", "exit_code": result.returncode}
    )
    print("ci-floor-command.txt", result.returncode, flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)
finally:
    if started:
        with (OUT / "pg-lifecycle.log").open("a") as log:
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
            receipt["stop_exit"] = stop.returncode
    shutil.rmtree(cluster)
    receipt["removed"] = not cluster.exists()
    receipt["ended_at"] = time.time()
    encoded = json.dumps(receipt, indent=2) + "\n"
    (OUT / "pg-lifecycle.json").write_text(encoded)
    (OUT / f"pg-lifecycle-{int(receipt['started_at'])}.json").write_text(encoded)
