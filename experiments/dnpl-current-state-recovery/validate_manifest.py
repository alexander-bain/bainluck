"""Verify the exact evidence-only packet. No network, scripts or source imports."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parent
manifest=json.loads((ROOT/'MANIFEST.json').read_text())
actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and not p.is_symlink() and '.work' not in p.parts and '__pycache__' not in p.parts and 'node_modules' not in p.parts}
expected={x['path'] for x in manifest['files']}|{'MANIFEST.json'}
assert actual==expected, {'extra':sorted(actual-expected),'missing':sorted(expected-actual)}
for entry in manifest['files']:
 p=ROOT/entry['path'];assert p.stat().st_size==entry['bytes'];assert hashlib.sha256(p.read_bytes()).hexdigest()==entry['sha256'],entry['path']
assert not any(x in actual for x in ['monotonic-candidate/EventPage.tsx','monotonic-candidate/install_route.py','atomic-numeric-encoding/authority.baseline.lua'])
assert not (ROOT/'producer-chain-metadata/composition/authority.lua').exists()
assert (ROOT/'producer-chain-metadata/retention_input.py').read_text().find("ROOT.parent/'atomic-numeric-encoding/adapter.py'")>=0
print(f'PASS: {len(expected)} exact files; {sum(x["bytes"] for x in manifest["files"])} manifested bytes; no dependency/generated trees')
