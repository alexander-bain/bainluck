"""Explicit local runtime contract. No subprocess, download, socket or service."""
import hashlib
import os
from pathlib import Path
import platform
import re

RUNTIME_MATRIX = {
    '7.2.16': 'primary Redis 7.2.16 validation; platform/build still recorded',
    '6.2.14': 'Redis 6.2.14 compatibility only; NOT Redis 7.2.16 validation',
}

def validate_runtime_contract(binary, expected_version, expected_sha256):
    """Expectations must be supplied independently by the approving operator."""
    if not isinstance(expected_version, str) or expected_version not in RUNTIME_MATRIX:
        raise ValueError('An explicitly reviewed Redis version is required')
    if not isinstance(expected_sha256, str) or re.fullmatch(r'[0-9a-f]{64}', expected_sha256) is None:
        raise ValueError('An independent canonical SHA256 is required')
    if not isinstance(binary, (str, Path)) or not str(binary):
        raise ValueError('An explicit absolute local binary path is required')
    path = Path(binary)
    if not path.is_absolute():
        raise ValueError('Runtime path must be absolute')
    path = path.resolve(strict=True)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError('Runtime must be a regular executable file')
    actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError('Selected runtime bytes do not match the operator SHA256')
    return {
        'binary_path': str(path),
        'expected_version': expected_version,
        'expected_sha256': expected_sha256,
        'actual_binary_sha256': actual_sha256,
        'evidence_scope': RUNTIME_MATRIX[expected_version],
        'platform': {'system': platform.system(), 'machine': platform.machine(), 'release': platform.release()},
    }

def verify_owned_runtime_version(contract, info):
    """Call only after the fixture verifies INFO process_id == owned Popen.pid."""
    actual = info.get('redis_version')
    if actual != contract['expected_version']:
        raise ValueError(f"Owned runtime version {actual!r} differs from explicit expected version {contract['expected_version']!r}")
    return actual
