"""Deterministic runtime-selection checks. Does not execute a binary or socket."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from runtime_selection import validate_runtime_contract, verify_owned_runtime_version, RUNTIME_MATRIX

class RuntimeSelection(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.binary=Path(self.temp.name)/'fixture-redis'
        self.binary.write_bytes(b'non-executable test contents, never run\n');self.binary.chmod(0o700)
        self.sha=hashlib.sha256(self.binary.read_bytes()).hexdigest()
        self.no_process=patch('subprocess.Popen',side_effect=AssertionError('no process allowed'));self.no_process.start();self.addCleanup(self.no_process.stop)
        self.no_socket=patch('socket.socket.connect',side_effect=AssertionError('no socket allowed'));self.no_socket.start();self.addCleanup(self.no_socket.stop)
    def valid(self,version='7.2.16'):
        return validate_runtime_contract(str(self.binary),version,self.sha)
    def test_explicit_primary_contract_records_bytes_path_and_platform(self):
        c=self.valid();self.assertEqual(c['actual_binary_sha256'],self.sha);self.assertEqual(c['expected_sha256'],self.sha)
        self.assertEqual(c['binary_path'],str(self.binary.resolve()));self.assertIn('machine',c['platform'])
    def test_62_is_explicit_compatibility_not_72_evidence(self):
        c=self.valid('6.2.14');self.assertIn('NOT Redis 7.2.16',c['evidence_scope']);self.assertEqual(verify_owned_runtime_version(c,{'redis_version':'6.2.14'}),'6.2.14')
    def test_unknown_or_missing_versions_rejected(self):
        for v in [None,'','7.2','7.2.17','6.2.14 ',[],{}]:
            with self.subTest(version=v),self.assertRaises(ValueError):validate_runtime_contract(self.binary,v,self.sha)
    def test_missing_malformed_or_noncanonical_hash_rejected(self):
        for sha in [None,'','a'*63,'g'*64,self.sha.upper(),' '+self.sha]:
            with self.subTest(sha=sha),self.assertRaises(ValueError):validate_runtime_contract(self.binary,'7.2.16',sha)
    def test_hash_mismatch_rejected_without_running_binary(self):
        with self.assertRaises(ValueError):validate_runtime_contract(self.binary,'7.2.16','0'*64)
    def test_relative_path_rejected(self):
        with self.assertRaises(ValueError):validate_runtime_contract('fixture-redis','7.2.16',self.sha)
    def test_missing_path_rejected(self):
        for p in [None,'']:
            with self.subTest(path=p),self.assertRaises(ValueError):validate_runtime_contract(p,'7.2.16',self.sha)
    def test_nonexistent_path_rejected(self):
        with self.assertRaises(FileNotFoundError):validate_runtime_contract(self.binary.with_name('absent'),'7.2.16',self.sha)
    def test_directory_rejected(self):
        with self.assertRaises(ValueError):validate_runtime_contract(self.binary.parent,'7.2.16',self.sha)
    def test_nonexecutable_file_rejected(self):
        self.binary.chmod(0o600)
        with self.assertRaises(ValueError):self.valid()
    def test_symlink_resolves_to_hashed_executable_before_launch(self):
        link=self.binary.with_name('link');link.symlink_to(self.binary)
        c=validate_runtime_contract(link,'7.2.16',self.sha);self.assertEqual(c['binary_path'],str(self.binary.resolve()))
    def test_owned_info_mismatch_or_missing_rejected(self):
        for info in [{},{'redis_version':'6.2.14'},{'redis_version':'7.2.16 extra'}]:
            with self.subTest(info=info),self.assertRaises(ValueError):verify_owned_runtime_version(self.valid(),info)
    def test_matrix_is_explicit_not_any_binary_version(self):
        self.assertEqual(set(RUNTIME_MATRIX),{'7.2.16','6.2.14'})

if __name__=='__main__':unittest.main(verbosity=2)
