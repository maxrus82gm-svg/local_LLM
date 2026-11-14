"""Synthetic Gate 2 acceptance tests + nonempty CI runner. Never contacts LIVE.

Exercises existing delivery validators with injected Test-only paths and fake
git provenance. Requirement regressions remain RED until separately approved
production fixes; they are not expectedFailure/skip or converted into PASS.
"""
import argparse
from collections import Counter
from contextlib import redirect_stdout
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'Documents/Reports/CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001'
TASK = 'CODEX-UL-R5-CI-GATE2-HARDEN-20261114-001'
EXACT_SHA = 'ba4ebf65af7a0693cf4dce045eb08254434a4475fd4f79e031424c905d661ce2'


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, REPORT / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)  # __main__ and all server entry points stay OFF.
    return value


def fixture_acl():
    return {'owner_sid': 'S-1-5-32-544', 'group_sid': 'S-1-5-21-1-2-3-513',
            'protected': False, 'canonical': True, 'rules': [
                {'sid': sid, 'type': 'Allow', 'rights': 'FullControl', 'inherited': True,
                 'inheritance': 'None', 'propagation': 'None'}
                for sid in ('S-1-5-18', 'S-1-5-32-544', 'S-1-5-21-1-2-3-1001')]}


class ScratchTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / 'Test' / TASK
        base.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.TemporaryDirectory(prefix='case-', dir=base)
        self.root = Path(tmp.name).resolve()
        self.assertTrue(self.root.is_relative_to(base.resolve()))
        self.addCleanup(tmp.cleanup)


class SnapshotGuardTests(ScratchTests):
    def setUp(self):
        super().setUp()
        self.guard = module('gate2_subject', 'stage_b_complete_readonly.py')
        self.serial = 0

    def fixture(self):
        self.serial += 1
        folder = self.root / str(self.serial)
        folder.mkdir()
        names = re.findall(r"\bCheck '([^']+)'", (REPORT / 'stage_b_server_preflight_v3.ps1').read_text(encoding='utf-8-sig'))
        self.assertEqual(len(set(names)), 24)
        baseline = {'status': 'PREFLIGHT_READONLY_PASS', 'checks': dict.fromkeys(names, True),
                    'task': {'xml_sha256': 'a' * 64, 'state': 'Running'},
                    'python_audit': {'metadata': {'config_sha256': 'b' * 64, 'tls_peer_sha256': 'c' * 64,
                        'owner_go': False, 'client_count': 1, 'control_models_granted_count': 0,
                        'pairing_admin_count': 0, 'slot_count': 3,
                        'unauth_snapshot_http': 403, 'unauth_snapshot_error': 'source_not_permitted'}},
                    'public_code': [{'name': 'synthetic.py', 'sha256': 'd' * 64}]}
        for i, role in enumerate(('manager', 'qwen_gateway', 'qwen_engine', 'valheim')):
            baseline[role] = {'pid': 100 + i, 'created_utc': '2026-11-14T00:00:00.0000000Z',
                              'owner_sid': 'S-1-5-21-1-2-3-1001', 'exe': 'C:/SYNTHETIC/' + role + '.exe'}
        baseline['manager_listener'] = {'address': '192.0.2.10', 'port': 8443, 'pid': 100}
        acl = fixture_acl()
        diagnostic = {'exit_code': 0, 'records': [
            {'summary': {'status': 'BACKUP_STAGING_PREPARED', 'stage_files': 21, 'zip_sha256': EXACT_SHA,
                         'code_files': 26, 'state_files': 4},
             'unsafe_new_tree_items': 0, 'checked_new_tree_items': 112,
             'source_acl': acl, 'probe_acl': copy.deepcopy(acl)}, copy.deepcopy(baseline)]}
        pinned = folder / 'pinned_public_record.bin'
        pinned.write_bytes(b'EXPECTED SNAPSHOT')
        resume = {'previous_files': {pinned.name: hashlib.sha256(pinned.read_bytes()).hexdigest()}, 'head': '1' * 40}
        return folder, baseline, diagnostic, resume

    def run_fixture(self, fixture, *, current_head=None):
        folder, baseline, diagnostic, resume = fixture
        for filename, data in (('stage_b_server_preflight_ready.json', {'result': baseline}),
                               ('stage_b_acl_readonly_diagnostic.json', diagnostic),
                               ('stage_b_resume_baseline_20261114.json', resume)):
            (folder / filename).write_text(json.dumps(data), encoding='utf-8')
        self.guard.OUT = folder
        self.guard.ROOT = folder
        def git_only(command, **kwargs):
            if command != ['git', 'rev-parse', 'HEAD']:
                raise RuntimeError('Unexpected subprocess forbidden in synthetic guard')
            return (current_head or resume['head']).encode()
        with patch.object(self.guard.subprocess, 'check_output', side_effect=git_only), redirect_stdout(io.StringIO()):
            self.guard.main()

    def rejected(self, fixture, exception=AssertionError, **kwargs):
        with self.assertRaises(exception):
            self.run_fixture(fixture, **kwargs)
        self.assertFalse((fixture[0] / 'stage_b_completion.json').exists())

    def test_good_synthetic_fixture_accepts(self):
        fixture = self.fixture()
        self.run_fixture(fixture)
        self.assertIn('B PASS', json.loads((fixture[0] / 'stage_b_completion.json').read_text())['status'])

    def test_pid_creation_owner_and_executable_changes_fail_closed(self):
        for role in ('manager', 'qwen_gateway', 'qwen_engine', 'valheim'):
            for field, value in (('pid', 999), ('created_utc', 'STALE'), ('owner_sid', 'FOREIGN'), ('exe', 'FOREIGN.exe')):
                fixture = self.fixture()
                fixture[2]['records'][1][role][field] = value
                with self.subTest(role=role, field=field):
                    self.rejected(fixture)

    def test_missing_protected_process_is_rejected_without_ready_artifact(self):
        for role in ('qwen_gateway', 'qwen_engine', 'valheim'):
            fixture = self.fixture()
            del fixture[2]['records'][1][role]
            with self.subTest(role=role):
                self.rejected(fixture, KeyError)

    def test_task_config_tls_and_grant_drift_fail_closed(self):
        for field in ('task', 'config_sha256', 'tls_peer_sha256', 'owner_go', 'control_models_granted_count'):
            fixture = self.fixture()
            post = fixture[2]['records'][1]
            if field == 'task':
                post['task']['xml_sha256'] = 'e' * 64
            else:
                post['python_audit']['metadata'][field] = 'CHANGED'
            with self.subTest(field=field):
                self.rejected(fixture)

    def test_empty_incomplete_or_false_guard_set_is_rejected(self):
        for mode in ('empty', 'incomplete', 'false'):
            fixture = self.fixture()
            checks = fixture[2]['records'][1]['checks']
            if mode == 'empty':
                checks.clear()
            elif mode == 'incomplete':
                checks.pop(next(iter(checks)))
            else:
                checks[next(iter(checks))] = False
            with self.subTest(mode=mode):
                self.rejected(fixture)

    def test_foreign_pinned_record_and_stale_git_provenance_are_rejected(self):
        fixture = self.fixture()
        (fixture[0] / 'pinned_public_record.bin').write_bytes(b'FOREIGN  SNAPSHOT')
        self.rejected(fixture)
        self.rejected(self.fixture(), current_head='2' * 40)

    def test_partial_restore_and_wrong_release_are_not_ready(self):
        for key, value in (('status', 'INCOMPLETE'), ('stage_files', 20), ('zip_sha256', 'f' * 64)):
            fixture = self.fixture()
            fixture[2]['records'][0]['summary'][key] = value
            with self.subTest(key=key):
                self.rejected(fixture)

    def test_changed_listener_must_fail_closed(self):
        fixture = self.fixture()
        fixture[2]['records'][1]['manager_listener']['pid'] = 999
        self.rejected(fixture)  # Requirement regression: current evaluator accepts it.

    def test_truthy_non_boolean_guard_must_fail_closed(self):
        fixture = self.fixture()
        checks = fixture[2]['records'][1]['checks']
        checks[next(iter(checks))] = 'false'
        self.rejected(fixture)  # Requirement regression, not expectedFailure.

    def test_arbitrary_403_must_not_be_access_denial_pass(self):
        fixture = self.fixture()
        fixture[2]['records'][1]['python_audit']['metadata']['unauth_snapshot_error'] = 'unrelated_forbidden'
        self.rejected(fixture)  # Requirement regression: cannot trust a coarse PASS flag.

    def test_listener_address_port_missing_fields_and_relative_pid_are_rejected(self):
        for field, value in (('address', '192.0.2.99'), ('port', 9443), ('pid', True),
                             ('port', True), ('port', 0), ('address', ''), ('address', None)):
            fixture = self.fixture()
            fixture[2]['records'][1]['manager_listener'][field] = value
            with self.subTest(field=field, value=value): self.rejected(fixture)
        for field in ('address', 'port', 'pid', 'manager_listener'):
            fixture = self.fixture()
            post = fixture[2]['records'][1]
            del (post if field == 'manager_listener' else post['manager_listener'])[field]
            with self.subTest(missing=field): self.rejected(fixture, (AssertionError, KeyError))
        fixture = self.fixture()
        for snapshot in (fixture[1], fixture[2]['records'][1]):
            snapshot['manager_listener']['pid'] = 999
        self.rejected(fixture)  # Matching sources still contradict Manager identity.

    def test_guard_contract_is_exact_and_strict_in_both_sources(self):
        expected = set(re.findall(r"\bCheck '([^']+)'", (REPORT / 'stage_b_server_preflight_v3.ps1').read_text(encoding='utf-8-sig')))
        self.assertEqual(self.guard.EXPECTED_CHECKS, expected)
        for source in ('baseline', 'post'):
            for mode in ('one', 'null', 'extra', 'renamed', 'false'):
                fixture = self.fixture()
                checks = (fixture[1] if source == 'baseline' else fixture[2]['records'][1])['checks']
                key = next(iter(checks))
                if mode == 'extra': checks['unknown_guard'] = True
                elif mode == 'renamed': checks['unknown_guard'] = checks.pop(key)
                else: checks[key] = {'one': 1, 'null': None, 'false': False}[mode]
                with self.subTest(source=source, mode=mode): self.rejected(fixture)

    def test_http_status_reason_and_missing_metadata_fail_closed(self):
        for source in ('baseline', 'post', 'both'):
            for status, reason in ((401, 'unauthorized'), (403, ''), (403, None),
                                   (403.0, 'source_not_permitted'), ('403', 'source_not_permitted'),
                                   (200, 'source_not_permitted')):
                fixture = self.fixture()
                snapshots = {'baseline': [fixture[1]], 'post': [fixture[2]['records'][1]],
                             'both': [fixture[1], fixture[2]['records'][1]]}[source]
                for snapshot in snapshots:
                    snapshot['python_audit']['metadata'].update(unauth_snapshot_http=status, unauth_snapshot_error=reason)
                with self.subTest(source=source, status=status, reason=reason): self.rejected(fixture)
        for field in ('unauth_snapshot_http', 'unauth_snapshot_error'):
            fixture = self.fixture()
            del fixture[2]['records'][1]['python_audit']['metadata'][field]
            with self.subTest(missing=field): self.rejected(fixture, KeyError)

    def test_optimized_python_keeps_acceptance_guards_active(self):
        # Run the actual main under -O with injected synthetic paths/Git only.
        script = '''
import sys
sys.path.insert(0, 'Manager_Ultra_LLM')
from test_gate2_hardening import SnapshotGuardTests
case = SnapshotGuardTests('test_good_synthetic_fixture_accepts')
case.setUp()
try:
    case.run_fixture(case.fixture())
    for mode in ('listener', 'guard', 'http', 'identity', 'provenance'):
        fixture = case.fixture()
        post = fixture[2]['records'][1]
        kwargs = {}
        if mode == 'listener': post['manager_listener']['port'] = 9443
        elif mode == 'guard': post['checks'][next(iter(post['checks']))] = 1
        elif mode == 'http': post['python_audit']['metadata']['unauth_snapshot_error'] = 'other'
        elif mode == 'identity': post['valheim']['pid'] = 999
        else: kwargs['current_head'] = '2' * 40
        try: case.run_fixture(fixture, **kwargs)
        except AssertionError: pass
        else: raise RuntimeError('Optimized checker accepted ' + mode)
        if (fixture[0] / 'stage_b_completion.json').exists():
            raise RuntimeError('Rejected evidence created completion')
    print('OPTIMIZED_GUARDS_PASS')
finally: case.doCleanups()
'''
        result = subprocess.run([sys.executable, '-O', '-B', '-c', script], cwd=ROOT,
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))
        self.assertIn(b'OPTIMIZED_GUARDS_PASS', result.stdout)


class ACLAndBackupTests(ScratchTests):
    def test_interrupted_restore_cannot_verify_as_complete_and_source_is_intact(self):
        helper = module('restore_subject', 'stage_b_prepare_server.py')
        source = self.root / 'source'
        source.mkdir()
        for name in ('config.bin', 'auth.bin', 'tls.bin'):
            (source / name).write_bytes(b'SYNTHETIC ORIGINAL')
        entries = helper.inventory(source)
        manifest = helper.copy_snapshot(source, self.root / 'complete', entries)
        target = self.root / 'interrupted'
        real_open = Path.open
        def fail_one_file(path, *args, **kwargs):
            mode = args[0] if args else kwargs.get('mode', 'r')
            if path == target / 'tls.bin' and mode == 'xb':
                raise OSError('SYNTHETIC restore write failure')
            return real_open(path, *args, **kwargs)
        with patch.object(Path, 'open', new=fail_one_file):
            with self.assertRaisesRegex(OSError, 'SYNTHETIC restore write failure'):
                helper.copy_snapshot(source, target, entries)
        self.assertTrue((target / 'auth.bin').is_file())
        self.assertFalse((target / 'tls.bin').exists())
        with self.assertRaisesRegex(ValueError, 'Backup inventory mismatch'):
            helper.verify_snapshot(target, manifest)
        for path in source.iterdir():
            self.assertEqual(path.read_bytes(), b'SYNTHETIC ORIGINAL')

    def test_acl_permutations_preserve_rights_but_expansions_are_rejected(self):
        gate = module('acl_subject', 'stage_b_complete_readonly.py')
        source = fixture_acl()
        permuted = copy.deepcopy(source)
        permuted['rules'].reverse()
        self.assertTrue(gate.acl_equivalent(source, permuted))
        for mode in ('foreign_sid', 'owner', 'rights', 'expanded', 'deny'):
            bad = copy.deepcopy(permuted)
            if mode == 'owner': bad['owner_sid'] = 'FOREIGN'
            elif mode == 'foreign_sid': bad['rules'][0]['sid'] = 'FOREIGN'
            elif mode == 'rights': bad['rules'][0]['rights'] = 'Read'
            elif mode == 'expanded': bad['rules'].append({**bad['rules'][0], 'sid': 'FOREIGN'})
            else: bad['rules'][0]['type'] = 'Deny'
            with self.subTest(mode=mode): self.assertFalse(gate.acl_equivalent(source, bad))

    def test_same_length_tls_auth_config_corruption_and_incomplete_backup_are_rejected(self):
        helper = module('backup_subject', 'stage_b_prepare_server.py')
        source = self.root / 'source'
        source.mkdir()
        for name in ('config.bin', 'auth.bin', 'tls.bin'):
            (source / name).write_bytes(b'SYNTHETIC EXPECTED BYTES')
        self.assertEqual(len(b'SYNTHETIC EXPECTED BYTES'), len(b'SYNTHETIC ALTERED  BYTES'))
        entries = helper.inventory(source)
        for name in ('config.bin', 'auth.bin', 'tls.bin', 'missing'):
            target = self.root / ('copy-' + name)
            manifest = helper.copy_snapshot(source, target, entries)
            if name == 'missing': (target / 'config.bin').unlink()
            else: (target / name).write_bytes(b'SYNTHETIC ALTERED  BYTES')
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'Backup (verification|inventory)'):
                helper.verify_snapshot(target, manifest)


class BackupProvenanceTests(ScratchTests):
    def setUp(self):
        super().setUp()
        import backup_provenance
        self.verifier = backup_provenance
        self.helper = module('provenance_legacy_subject', 'stage_b_prepare_server.py')
        self.serial = 0

    def write_manifest(self, backup, manifest):
        raw = (json.dumps(manifest, indent=2) + '\n').encode('utf-8')
        (backup / self.verifier.MANIFEST).write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def fixture(self):
        self.serial += 1
        folder = self.root / str(self.serial)
        folder.mkdir()
        backup = folder / 'backup'
        backup.mkdir()
        manifest = {'scope': 'SYNTHETIC FULL code/state', 'code_source': 'SYNTHETIC/code',
                    'state_source': 'SYNTHETIC/state', 'security': 'SYNTHETIC SDDL metadata',
                    'sqlite_wal': 'SYNTHETIC NOT PRESENT'}
        for tree in ('code', 'state'):
            source = folder / ('source-' + tree)
            source.mkdir()
            if tree == 'code': (source / 'main.py').write_bytes(b"raise RuntimeError('NEVER EXECUTE')\n")
            else:
                (source / 'private').mkdir()
                (source / 'private/auth.bin').write_bytes(b'SYNTHETIC PRIVATE AUTH ORIGINAL')
                (source / 'private/tls.bin').write_bytes(b'SYNTHETIC PRIVATE TLS ORIGINAL')
            with patch.object(self.helper, 'security_descriptor', return_value='SYNTHETIC SDDL'):
                manifest[tree] = self.helper.copy_snapshot(source, backup / tree, self.helper.inventory(source))
        xml = '<Task><Description>SYNTHETIC TASK</Description></Task>'
        task_raw = xml.encode('utf-16')
        (backup / 'task_original.xml').write_bytes(task_raw)
        manifest['task_xml_file_sha256'] = hashlib.sha256(task_raw).hexdigest()
        manifest['task_xml_canonical_utf8_sha256'] = hashlib.sha256(xml.encode('utf-8')).hexdigest()
        pin = self.write_manifest(backup, manifest)  # Retained outside the backup, before any tamper.
        return backup, manifest, pin

    def verify(self, fixture, pin=None):
        return self.verifier.verify_backup(fixture[0], trusted_manifest_sha256=fixture[2] if pin is None else pin)

    def rejected(self, fixture, reason, pin=None):
        with self.assertRaisesRegex(self.verifier.VerificationError, '^' + reason + '$'):
            self.verify(fixture, pin=pin)

    def test_good_pinned_backup_is_read_only_and_exports_only_safe_counts(self):
        fixture = self.fixture()
        before = self.verifier._inventory(fixture[0])
        bytes_before = {p.relative_to(fixture[0]).as_posix(): p.read_bytes()
                        for p in fixture[0].rglob('*') if p.is_file()}
        result = self.verify(fixture)
        self.assertEqual(result, {'status': 'PASS', 'manifest_sha256': fixture[2],
            'code_files': 1, 'state_files': 2, 'task_xml': 'PASS', 'read_only': True,
            'initial_authenticity': 'NOT PROVEN'})
        self.assertEqual(before, self.verifier._inventory(fixture[0]))
        self.assertEqual(bytes_before, {p.relative_to(fixture[0]).as_posix(): p.read_bytes()
                                       for p in fixture[0].rglob('*') if p.is_file()})
        self.assertNotIn('PRIVATE AUTH', json.dumps(result))

    def test_joint_backup_and_manifest_replacement_passes_legacy_but_fails_external_pin(self):
        fixture = self.fixture()
        backup, manifest, original_pin = fixture
        target = backup / 'state/private/auth.bin'
        target.write_bytes(b'SYNTHETIC ATTACKER REPLACEMENT')
        row = manifest['state']['private/auth.bin']
        row.update(bytes=target.stat().st_size, sha256=hashlib.sha256(target.read_bytes()).hexdigest())
        replaced_pin = self.write_manifest(backup, manifest)
        self.assertNotEqual(original_pin, replaced_pin)
        # Real old helper accepts the internally consistent forged backup.
        self.helper.verify_snapshot(backup / 'code', manifest['code'])
        self.helper.verify_snapshot(backup / 'state', manifest['state'])
        self.rejected(fixture, 'trusted_manifest_mismatch')

    def test_one_private_file_or_manifest_only_tampering_fails(self):
        fixture = self.fixture()
        (fixture[0] / 'state/private/auth.bin').write_bytes(b'SYNTHETIC PRIVATE AUTH REPLACED')
        self.rejected(fixture, 'file_hash_mismatch')
        fixture = self.fixture()
        fixture[1]['scope'] = 'SYNTHETIC REPLACED MANIFEST'
        self.write_manifest(fixture[0], fixture[1])
        self.rejected(fixture, 'trusted_manifest_mismatch')

    def test_missing_malformed_or_wrong_trusted_pin_cannot_be_inferred(self):
        fixture = self.fixture()
        for pin in (None, '', 'x' * 64, 1):
            with self.subTest(pin=pin), patch.object(self.verifier, '_checked_stat', side_effect=AssertionError('No filesystem access')):
                with self.assertRaisesRegex(self.verifier.VerificationError, '^trusted_pin_required$'):
                    self.verifier.verify_backup(fixture[0], trusted_manifest_sha256=pin)
        self.rejected(fixture, 'trusted_manifest_mismatch', pin='0' * 64)
        self.assertEqual(self.verify(fixture, pin=fixture[2].upper())['status'], 'PASS')

    def test_missing_extra_and_type_swapped_members_fail_closed(self):
        for mode in ('missing', 'extra', 'extra_directory', 'type', 'manifest_missing'):
            fixture = self.fixture()
            target = fixture[0] / 'state/private/auth.bin'
            if mode in ('missing', 'type'):
                target.unlink()
                if mode == 'type': target.mkdir()
            elif mode == 'extra': (fixture[0] / 'extra.bin').write_bytes(b'SYNTHETIC EXTRA')
            elif mode == 'extra_directory': (fixture[0] / 'extra').mkdir()
            else: (fixture[0] / self.verifier.MANIFEST).unlink()
            with self.subTest(mode=mode):
                self.rejected(fixture, 'manifest_missing' if mode == 'manifest_missing' else 'backup_inventory_mismatch')

    def test_unsafe_manifest_paths_are_rejected_even_with_matching_pin(self):
        for path in ('../escape', '/absolute', 'C:/escape', 'private\\auth.bin', 'private//auth.bin',
                     'private/./auth.bin', 'private/../auth.bin', 'private/auth.bin:stream',
                     'private/auth.bin.', 'private/CON', 'private/LPT1.txt'):
            fixture = self.fixture()
            fixture[1]['state'][path] = fixture[1]['state'].pop('private/auth.bin')
            pin = self.write_manifest(fixture[0], fixture[1])
            with self.subTest(path=path): self.rejected(fixture, 'unsafe_manifest_path', pin=pin)

    def test_manifest_schema_duplicates_types_and_nonfinite_values_fail(self):
        for mode in ('empty', 'missing', 'unknown', 'bool_size', 'hash', 'directory', 'parent', 'case_collision'):
            fixture = self.fixture()
            data = fixture[1]
            row = data['state']['private/auth.bin']
            if mode == 'empty': data = {}
            elif mode == 'missing': del data['task_xml_file_sha256']
            elif mode == 'unknown': data['unknown'] = True
            elif mode == 'bool_size': row['bytes'] = True
            elif mode == 'hash': row['sha256'] = 'invalid'
            elif mode == 'directory': data['state']['.']['directory'] = 1
            elif mode == 'parent': del data['state']['private']
            else: data['state']['PRIVATE/AUTH.BIN'] = copy.deepcopy(row)
            pin = self.write_manifest(fixture[0], data)
            with self.subTest(mode=mode): self.rejected(fixture, 'manifest_schema', pin=pin)
        for raw in (b'{"code":{},"code":{}}', b'{"code": NaN}', b'[]', b'{', b'\xff'):
            fixture = self.fixture()
            (fixture[0] / self.verifier.MANIFEST).write_bytes(raw)
            with self.subTest(raw=raw): self.rejected(fixture, 'manifest_schema', pin=hashlib.sha256(raw).hexdigest())

    def test_task_raw_canonical_hashes_and_wellformedness_are_checked(self):
        fixture = self.fixture()
        (fixture[0] / 'task_original.xml').write_bytes('<Task>CHANGED</Task>'.encode('utf-16'))
        self.rejected(fixture, 'task_hash_mismatch')
        fixture = self.fixture()
        fixture[1]['task_xml_canonical_utf8_sha256'] = '0' * 64
        self.rejected(fixture, 'task_hash_mismatch', pin=self.write_manifest(fixture[0], fixture[1]))
        fixture = self.fixture()
        raw = '<Task>BROKEN'.encode('utf-16')
        (fixture[0] / 'task_original.xml').write_bytes(raw)
        fixture[1]['task_xml_file_sha256'] = hashlib.sha256(raw).hexdigest()
        self.rejected(fixture, 'task_xml_invalid', pin=self.write_manifest(fixture[0], fixture[1]))

    def test_read_errors_are_fail_closed_without_private_path_disclosure(self):
        fixture = self.fixture()
        with patch.object(self.verifier.os, 'open', side_effect=PermissionError('SYNTHETIC PRIVATE SECRET PATH')):
            self.rejected(fixture, 'backup_unreadable')

    def test_file_changes_during_read_or_after_read_are_rejected(self):
        for mode in ('before_read', 'open_race', 'mid_read', 'after_read'):
            fixture = self.fixture()
            target = fixture[0] / 'state/private/auth.bin'
            actual_read = self.verifier._read_verified
            actual_open = self.verifier.os.open
            actual_fstat = self.verifier.os.fstat
            actual_fdopen = self.verifier.os.fdopen
            hits = []
            def change():
                target.write_bytes(b'SYNTHETIC PRIVATE AUTH REPLACED')
            def read(path, *args, **kwargs):
                if path == target and mode == 'before_read': change()
                result = actual_read(path, *args, **kwargs)
                if path == target and mode == 'after_read': change()
                return result
            def opened(path, flags):
                fd = actual_open(path, flags)
                if Path(path) == target: hits.append(fd)
                return fd
            def fstat(fd):
                if hits and fd == hits[-1] and mode == 'open_race':
                    hits.clear()
                    change()
                return actual_fstat(fd)
            def fdopen(fd, *args, **kwargs):
                stream = actual_fdopen(fd, *args, **kwargs)
                if mode != 'mid_read' or not hits or fd != hits[-1]: return stream
                hits.clear()
                class ChangingReader:
                    changed = False
                    def __enter__(self): return self
                    def __exit__(self, *exc): return stream.__exit__(*exc)
                    def fileno(self): return stream.fileno()
                    def read(self, size):
                        chunk = stream.read(size)
                        if chunk and not self.changed:
                            self.changed = True
                            change()
                        return chunk
                return ChangingReader()
            with self.subTest(mode=mode), patch.object(self.verifier, '_read_verified', side_effect=read), \
                 patch.object(self.verifier.os, 'open', side_effect=opened), \
                 patch.object(self.verifier.os, 'fdopen', side_effect=fdopen), patch.object(self.verifier.os, 'fstat', side_effect=fstat):
                self.rejected(fixture, 'backup_changed' if mode == 'after_read' else 'file_changed')

    def test_new_member_added_during_verification_is_rejected(self):
        fixture = self.fixture()
        actual_read = self.verifier._read_verified
        def changed(path, *args, **kwargs):
            result = actual_read(path, *args, **kwargs)
            if path.name == 'task_original.xml': (fixture[0] / 'extra.bin').write_bytes(b'SYNTHETIC NEW')
            return result
        with patch.object(self.verifier, '_read_verified', side_effect=changed):
            self.rejected(fixture, 'backup_changed')

    def test_junction_and_hardlink_are_rejected_without_following(self):
        fixture = self.fixture()
        external = self.root / 'outside'
        external.mkdir()
        (external / 'sentinel').write_bytes(b'SYNTHETIC NEVER READ')
        junction = fixture[0] / 'redirect'
        result = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(junction), str(external)],
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))
        try:
            self.rejected(fixture, 'unsafe_link')
            with self.assertRaisesRegex(self.verifier.VerificationError, '^unsafe_link$'):
                self.verifier.verify_backup(junction, trusted_manifest_sha256=fixture[2])
        finally: junction.rmdir()  # This known junction only, never recursive removal.
        fixture = self.fixture()
        os.link(external / 'sentinel', fixture[0] / 'hardlink')
        self.rejected(fixture, 'unsafe_hardlink')
        self.assertEqual((external / 'sentinel').read_bytes(), b'SYNTHETIC NEVER READ')

    def test_symlink_metadata_is_rejected_before_opening(self):
        fixture = self.fixture()
        real_stat = self.verifier._checked_stat
        target = fixture[0] / self.verifier.MANIFEST
        def linked(path):
            if path == target: raise self.verifier.VerificationError('unsafe_link')
            return real_stat(path)
        with patch.object(self.verifier, '_checked_stat', side_effect=linked): self.rejected(fixture, 'unsafe_link')
        # Directly exercise the reparse/symlink classifier without symlink privilege.
        from types import SimpleNamespace
        for info in (SimpleNamespace(st_mode=0o120777, st_file_attributes=0),
                     SimpleNamespace(st_mode=0o100644, st_file_attributes=0x400)):
            with patch.object(Path, 'lstat', return_value=info):
                with self.assertRaisesRegex(self.verifier.VerificationError, '^unsafe_link$'):
                    real_stat(target)

    def test_cli_has_sanitized_output_exit_codes_and_needs_explicit_pin(self):
        fixture = self.fixture()
        cli = ROOT / 'Manager_Ultra_LLM/backup_provenance.py'
        for flags in (['-B'], ['-O', '-B']):
            command = [sys.executable, *flags, str(cli), '--backup-root', str(fixture[0])]
            for pin, expected in ((fixture[2], 0), ('0' * 64, 1), (None, 2)):
                args = command + (['--trusted-manifest-sha256', pin] if pin else [])
                result = subprocess.run(args, capture_output=True, timeout=15)
                with self.subTest(flags=flags, pin=pin):
                    self.assertEqual(result.returncode, expected)
                    self.assertNotIn(b'PRIVATE AUTH', result.stdout + result.stderr)
                    if pin: self.assertEqual(json.loads(result.stdout)['status'], 'PASS' if expected == 0 else 'FAIL')


class CollectionError(ValueError):
    pass


def require_collection(suite, minimum):
    if minimum < 1 or suite.countTestCases() < minimum:
        raise CollectionError('Nonempty suite/minimum count requirement failed')


class HarnessTests(unittest.TestCase):
    def test_empty_collection_cannot_report_pass(self):
        with self.assertRaises(CollectionError): require_collection(unittest.TestSuite(), 1)


class EvidenceResult(unittest.TextTestResult):
    """Preserve every started testcase, not just failure entries, for JUnit."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = {}

    def startTest(self, test):
        super().startTest(test)
        self.records[str(test)] = {'status': 'pass', 'trace': ''}

    def mark(self, test, status, error=None):
        self.records[str(test)] = {'status': status, 'trace': self._exc_info_to_string(error, test) if error else ''}

    def addFailure(self, test, err):
        super().addFailure(test, err); self.mark(test, 'failure', err)

    def addError(self, test, err):
        super().addError(test, err); self.mark(test, 'error', err)

    def addSkip(self, test, reason):
        super().addSkip(test, reason); self.records[str(test)] = {'status': 'skipped', 'trace': reason}

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err); self.mark(test, 'expected_failure', err)

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test); self.mark(test, 'unexpected_success')

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err: self.mark(test, 'failure', err)


def run_suite(suite, output, minimum):
    start = time.perf_counter()
    try:
        require_collection(suite, minimum)
    except CollectionError as error:
        record = {'status': 'COLLECTION_ERROR', 'tests': 0, 'exception': type(error).__name__, 'exit_code': 3}
        result = None
    else:
        result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
        good = result.wasSuccessful() and not result.expectedFailures
        record = {'status': 'PASS' if good else 'FAIL', 'tests': result.testsRun,
                  'failures': len(result.failures), 'errors': len(result.errors), 'skips': len(result.skipped),
                  'expected_failures': len(result.expectedFailures), 'unexpected_successes': len(result.unexpectedSuccesses),
                  'exit_code': 0 if good else 1,
                  'failure_details': [{'test': str(t), 'traceback': trace} for t, trace in result.failures + result.errors]}
    record['seconds'] = round(time.perf_counter() - start, 3)
    record['scope'] = 'OFFLINE SOURCE / synthetic; no LIVE/EXE/LLM'
    record['base_head'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, timeout=10).decode().strip()
    record['github_sha'] = os.environ.get('GITHUB_SHA')
    record['github_run_id'] = os.environ.get('GITHUB_RUN_ID')
    record['python'] = sys.version.split()[0]
    record['tested_runner_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with output.open('x', encoding='utf-8') as stream: json.dump(record, stream, indent=2); stream.write('\n')
    records = result.records if result else {'collection': {'status': 'error', 'trace': 'CollectionError: empty/insufficient suite'}}
    xml = ET.Element('testsuite', {'tests': str(len(records)),
        'failures': str(sum(row['status'] in ('failure', 'expected_failure', 'unexpected_success') for row in records.values())),
        'errors': str(sum(row['status'] == 'error' for row in records.values())),
        'skipped': str(sum(row['status'] == 'skipped' for row in records.values()))})
    for name, row in records.items():
        case = ET.SubElement(xml, 'testcase', name=name)
        if row['status'] != 'pass':
            tag = row['status'] if row['status'] in ('error', 'skipped') else 'failure'
            ET.SubElement(case, tag, type=row['status']).text = row['trace']
    ET.ElementTree(xml).write(output.with_suffix('.xml'), encoding='utf-8', xml_declaration=True)
    print(json.dumps(record))
    return record['exit_code']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=('Manager_Ultra_LLM', 'Client_Ultra_LLM'))
    parser.add_argument('--minimum', type=int, default=1)
    parser.add_argument('--probe', choices=('pass', 'fail', 'error', 'empty'))
    parser.add_argument('--negative-controls', action='store_true')
    parser.add_argument('--exact-zip', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / 'Test').resolve()) or output.exists():
        raise ValueError('Evidence must be a NEW file under workspace/Test')
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.parent / 'temp'
    temp.mkdir(exist_ok=True)
    for name in ('TMP', 'TEMP', 'TMPDIR', 'LOCALAPPDATA'): os.environ[name] = str(temp)
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    tempfile.tempdir = str(temp)
    if args.exact_zip:
        import manager_release
        actual = hashlib.sha256(args.exact_zip.read_bytes()).hexdigest()
        if actual != EXACT_SHA: raise ValueError('EXACT ZIP SHA mismatch; do not rebuild')
        payload = manager_release.read_package(args.exact_zip)
        with output.open('x') as stream: json.dump({'status': 'EXACT ZIP PASS', 'sha256': actual, 'files': len(payload), 'rebuild': False}, stream)
        return 0
    if args.negative_controls:
        rows = []
        for mode, expected in (('pass', 0), ('fail', 1), ('error', 1), ('empty', 3)):
            child = output.with_name(output.stem + '-' + mode + '.json')
            command = [sys.executable, '-B', str(Path(__file__)), '--probe', mode, '--output', str(child)]
            result = subprocess.run(command, capture_output=True, timeout=20)
            data = json.loads(child.read_text())
            junit = ET.parse(child.with_suffix('.xml')).getroot()
            if int(junit.attrib['tests']) != len(junit.findall('testcase')):
                raise RuntimeError('JUnit testcase collection is incomplete')
            if result.returncode != expected or data['exit_code'] != expected:
                raise RuntimeError('Negative control did not produce the exact expected verdict')
            if mode == 'fail' and (data['failures'], data['errors']) != (1, 0): raise RuntimeError('Wrong RED type')
            if mode == 'error' and (data['failures'], data['errors']) != (0, 1): raise RuntimeError('Wrong ERROR type')
            if mode == 'empty' and data.get('exception') != 'CollectionError': raise RuntimeError('Empty-suite false PASS')
            rows.append({'mode': mode, 'observed_exit': result.returncode, 'expected_exit': expected, 'status': data['status']})
        bad_zip = output.with_suffix('.synthetic-zip')
        bad_zip.write_bytes(b'SYNTHETIC WRONG ZIP, NEVER THE AUTHORITATIVE RELEASE')
        wrong_output = output.with_name(output.stem + '-wrong-zip.json')
        wrong = subprocess.run([sys.executable, '-B', str(Path(__file__)), '--exact-zip', str(bad_zip), '--output', str(wrong_output)],
                               capture_output=True, timeout=20)
        if wrong.returncode != 1 or wrong_output.exists() or b'EXACT ZIP SHA mismatch' not in wrong.stderr:
            raise RuntimeError('Wrong authoritative ZIP did not fail at the expected hash guard')
        rows.append({'mode': 'wrong-exact-zip', 'observed_exit': wrong.returncode, 'expected_exit': 1, 'status': 'EXPECTED HASH REJECTION'})
        with output.open('x') as stream: json.dump({'status': 'NEGATIVE CONTROLS PASS', 'controls': rows}, stream, indent=2)
        return 0
    if args.probe:
        class Probe(unittest.TestCase):
            def runTest(self):
                if args.probe == 'error': raise RuntimeError('SYNTHETIC injected runtime error')
                self.assertEqual(args.probe, 'pass', 'SYNTHETIC deliberate broken result')
        suite = unittest.TestSuite([] if args.probe == 'empty' else [Probe()])
    elif args.suite:
        suite = unittest.TestLoader().discover(str(ROOT / args.suite), pattern='test_*.py')
    else:
        parser.error('Choose suite, probe, negative-controls or exact-zip')
    return run_suite(suite, output, args.minimum)


if __name__ == '__main__':
    raise SystemExit(main())
