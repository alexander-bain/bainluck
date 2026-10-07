"""Finite source gates against one owned UNIX PostgreSQL; no timing corpus."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PG = Path('/opt/homebrew/opt/postgresql@17/bin')
temp = Path(tempfile.mkdtemp(prefix='kalshi-source10689-', dir='/tmp'))
data, sock = temp/'data', temp/'s'
sock.mkdir()
life = dict(temp=str(temp), port=55531, stopped=False)
result = 1
try:
    subprocess.run([str(PG/'initdb'), '-D', str(data), '-A', 'trust', '--no-locale'], check=True, stdout=subprocess.DEVNULL)
    subprocess.run([str(PG/'pg_ctl'), '-D', str(data), '-l', str(temp/'postgres.log'), '-o', f"-k {sock} -h '' -p 55531 -c shared_buffers=16MB -c max_connections=30", '-w', 'start'], check=True, stdout=subprocess.DEVNULL)
    life['pid'] = int((data/'postmaster.pid').read_text().splitlines()[0])
    env = dict(os.environ, DATABASE_URL='postgresql+asyncpg://localhost/private_unused', SEARCH_TEST_DATABASE_URL=f'postgresql+asyncpg://@/postgres?host={sock}&port=55531')
    commands = {
        'source-final': [sys.executable, '-m', 'pytest',
            'tests/test_kalshi_price_statement_10689.py', 'tests/test_price_change_stamp.py',
            'tests/test_price_stamp_writer_scan_4958.py', 'tests/test_futures_rank_field_wide_6598.py',
            'tests/integration/test_kalshi_price_statement_10689_pg.py',
            'tests/test_ci_postgres_groups.py', 'tests/test_startup.py', '-q', '-rs'],
    }
    if '--postgres-only' in sys.argv:
        commands = {'source-postgres-final': [sys.executable, '-m', 'pytest', 'tests/test_kalshi_price_statement_10689.py', 'tests/integration/test_kalshi_price_statement_10689_pg.py', 'tests/test_startup.py', '-q', '-rs']}
    life['gates'] = []
    for name, command in commands.items():
        log = OUT/(name+'.txt')
        with log.open('w') as output:
            gate = subprocess.run(command, cwd=ROOT/'backend', env=env, stdout=output, stderr=subprocess.STDOUT)
        body = log.read_text()
        skipped = bool(re.search(r'\b[0-9]+ skipped\b', body))
        life['gates'].append(dict(name=name, exit=gate.returncode, skipped=skipped, command=command))
        print(f'{name}: exit={gate.returncode}; skipped={skipped}', flush=True)
        print('\n'.join(body.splitlines()[-25:]), flush=True)
        if gate.returncode or skipped:
            result = gate.returncode or 1
            break
    else:
        result = 0
finally:
    if (data/'postmaster.pid').exists():
        subprocess.run([str(PG/'pg_ctl'), '-D', str(data), '-m', 'fast', '-w', 'stop'], check=True, stdout=subprocess.DEVNULL)
    life['stopped'] = not (data/'postmaster.pid').exists()
    (OUT/'source-lifecycle.json').write_text(json.dumps(life, indent=2)+'\n')
    if life['stopped']:
        shutil.rmtree(temp)
sys.exit(result)
