"""Fresh interpreter regression: driver selects its own candidate, no import order."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def test_direct_driver_startup_and_async_callback_without_alias_preload():
    code = '''
import asyncio
from pathlib import Path
import socket

def refuse_network(*args, **kwargs):
    raise AssertionError('Direct driver regression must not open a connection')
socket.socket.connect = refuse_network
socket.socket.connect_ex = refuse_network
from producer_driver import ProducerDriver, blend_preview, lbr
assert '/candidate/' in str(Path(blend_preview.__file__).resolve())
assert '/reference/' in str(Path(lbr.__file__).resolve())
async def run():
    captured = []
    async def callback(frame, metadata):
        await asyncio.sleep(0)
        captured.append((frame, metadata))
    with ProducerDriver(on_frame=callback) as driver:
        for time in (0, 2, 4):
            await driver.step(time, locked=time != 4)
        assert len(captured) == len(driver.frames) > 0
        blends = [frame for frame, _ in captured if frame.get('preview', {}).get('kind') == 'blend']
        assert len(blends) == 3
        assert [f['preview']['ttl_ms'] for f in blends] == [60000, 58000, 56000]
        assert len({f['preview']['lease_id'] for f in blends}) == 1
        assert len({f['preview']['original_expires_at_ms'] for f in blends}) == 1
        assert driver.frames[-1]['kind'] == 'committed'
asyncio.run(run())
'''
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run([sys.executable, '-c', code], cwd=ROOT,
                            env=env, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr

def test_loader_rejects_switching_variant_in_same_process():
    code = '''
from current_source import load
candidate = load(candidate=True)
assert load(candidate=True) is candidate
try:
    load(candidate=False)
except RuntimeError:
    pass
else:
    raise AssertionError('Source variant switch must require a fresh interpreter')
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=ROOT,
        env=dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE='1'),
        text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
