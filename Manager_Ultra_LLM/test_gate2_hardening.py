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
