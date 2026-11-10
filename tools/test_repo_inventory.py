"""Exercise the shipped audit helper against isolated Git repositories."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'skills/audit-repository/scripts/repo_inventory.py'
SPEC = importlib.util.spec_from_file_location('repo_inventory', HELPER)
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        self.out = self.base / 'audit'
        # A developer's global ignore file or hooks must not change what these repositories contain.
        config = self.base / 'gitconfig'
        config.write_bytes(b'')
        self.git_env = {**os.environ, 'GIT_CONFIG_GLOBAL': str(config), 'GIT_CONFIG_NOSYSTEM': '1'}
        self.git('init')
        for name, content in {
            'tracked.py': b'print(1)\n',
            'untracked.py': b'print(2)\n',
            'dist/app.js': b'export default 1;\n',
            'README.md': b'Example project\n',
            'image.png': b'\x00binary',
            '.gitignore': b'ignored.py\n',
            'ignored.py': b'ignored\n',
        }.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.git('add', 'tracked.py', '.gitignore')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, timeout=15, env=self.git_env).stdout

    def run_helper(self, *args, expected=0, helper=HELPER, env=None, stdin=None):
        result = subprocess.run([sys.executable, str(helper), *args], capture_output=True,
                                timeout=15, env={**self.git_env, **(env or {})}, input=stdin)
        # The helper always writes UTF-8, whatever the platform's default encoding is.
        result.stdout = result.stdout.decode('utf-8')
        result.stderr = result.stderr.decode('utf-8')
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def ledger(self):
        return json.loads((self.out / 'ledger.json').read_text(encoding='utf-8'))

    def records(self, repo=None):
        self.run_helper('create', '--repo', str(repo or self.repo), '--out', str(self.out))
        return {item['path']: item for item in self.ledger()['files']}

    def mark(self, status, *paths, note=None, expected=0):
        args = ['mark', '--out', str(self.out), '--status', status]
        for path in paths:
            args += ['--path', path]
        if note:
            args += ['--note', note]
        return self.run_helper(*args, expected=expected)

    def plain_directory(self, files):
        source = (self.base / 'plain').resolve()
        for name, content in files.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        return source

    def create(self, helper=HELPER):
        self.run_helper('create', '--repo', str(self.repo), '--out', str(self.out), helper=helper)
        return json.loads((self.out / 'ledger.json').read_text(encoding='utf-8'))

    def test_inventory_and_completion_preserve_target(self):
        before_status = self.git('status', '--porcelain=v1', '-z')
        before = {p.relative_to(self.repo): p.read_bytes() for p in self.repo.rglob('*') if p.is_file()}
        ledger = self.create()
        records = {item['path']: item for item in ledger['files']}
        self.assertNotIn('ignored.py', records)
        self.assertEqual(records['tracked.py']['status'], 'pending')
        self.assertEqual(records['untracked.py']['status'], 'pending')
        self.assertEqual(records['dist/app.js']['status'], 'pending-decision')
        self.assertEqual(records['README.md']['scope'], 'context')
        self.assertEqual(records['image.png']['status'], 'excluded')
        result = self.run_helper('status', '--out', str(self.out), '--show-pending', expected=2)
        self.assertIn('dist/app.js', result.stdout)
        for item in ledger['files']:
            if item['status'] in {'pending', 'pending-decision'}:
                self.run_helper('mark', '--out', str(self.out), '--path', item['path'], '--status', 'reviewed')
        result = self.run_helper('status', '--out', str(self.out))
        self.assertTrue(json.loads(result.stdout)['coverage_complete'])
        self.assertEqual(before_status, self.git('status', '--porcelain=v1', '-z'))
        self.assertEqual(before, {p.relative_to(self.repo): p.read_bytes() for p in self.repo.rglob('*') if p.is_file()})

    def test_refuses_output_inside_target(self):
        output = self.repo / 'audit'
        result = self.run_helper('create', '--repo', str(self.repo), '--out', str(output), expected=1)
        self.assertIn('outside the target repository', result.stderr)
        self.assertFalse(output.exists())

    def test_unicode_bom_source_requires_review_decision(self):
        for encoding, bom in (
            ('utf-16-le', b'\xff\xfe'), ('utf-16-be', b'\xfe\xff'),
            ('utf-32-le', b'\xff\xfe\x00\x00'), ('utf-32-be', b'\x00\x00\xfe\xff'),
        ):
            with self.subTest(encoding=encoding):
                source = self.repo / 'deploy.ps1'
                source.write_bytes(bom + ('Write-Output "hello"\n' * 1000).encode(encoding))
                ledger = self.create()
                record = next(item for item in ledger['files'] if item['path'] == 'deploy.ps1')
                self.assertEqual(record['status'], 'pending-decision')
                # Complete every other entry; this script must still prevent completion.
                others = [item['path'] for item in ledger['files']
                          if item['path'] != 'deploy.ps1' and item['status'].startswith('pending')]
                for path in others:
                    self.run_helper('mark', '--out', str(self.out), '--path', path, '--status', 'reviewed')
                result = self.run_helper('status', '--out', str(self.out), '--show-pending', expected=2)
                self.assertIn('deploy.ps1', result.stdout)

    def test_directory_scan_errors_fail_creation(self):
        source = (self.base / 'source').resolve()
        source.mkdir()
        nested = source / 'src'
        nested.mkdir()
        (nested / 'app.py').write_text('print(1)\n', encoding='utf-8')
        real_scandir = inventory.os.scandir
        for denied in (source, nested):
            with self.subTest(denied=denied):
                def scandir(path):
                    if Path(path) == denied:
                        raise PermissionError(13, 'Permission denied', str(path))
                    return real_scandir(path)

                stderr = io.StringIO()
                with mock.patch.object(inventory, 'git_root', return_value=None), \
                        mock.patch.object(inventory.os, 'scandir', side_effect=scandir), \
                        contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
                    result = inventory.main(['create', '--repo', str(source), '--out', str(self.out)])
                self.assertEqual(result, 1)
                self.assertIn(str(denied), stderr.getvalue())
                self.assertFalse((self.out / 'ledger.json').exists())

    def test_git_failure_never_falls_back_to_directory_walk(self):
        # Without git on PATH a repository used to be walked as a plain directory,
        # which skipped dist/ entirely and reported complete coverage.
        empty = self.base / 'empty-path'
        empty.mkdir()
        result = self.run_helper('create', '--repo', str(self.repo), '--out', str(self.out),
                                 expected=1, env={'PATH': str(empty)})
        self.assertIn('git is not available', result.stderr)
        self.assertFalse((self.out / 'ledger.json').exists())

    def test_broken_repository_is_fatal(self):
        broken = self.plain_directory({'src/app.py': b'print(1)\n'})
        (broken / '.git').mkdir()
        result = self.run_helper('create', '--repo', str(broken), '--out', str(self.out), expected=1)
        self.assertIn('git could not inspect the target', result.stderr)
        self.assertFalse((self.out / 'ledger.json').exists())

    def test_non_git_skipped_directories_block_completion(self):
        source = self.plain_directory({
            'src/app.py': b'print(1)\n', 'build/deploy.py': b'print(2)\n',
            'vendor/lib/patched.py': b'print(3)\n', '__pycache__/app.pyc': b'\x00',
        })
        result = self.run_helper('create', '--repo', str(source), '--out', str(self.out))
        self.assertIn('non-git', result.stderr)
        self.assertIn('build/', result.stderr)
        records = {item['path']: item for item in self.ledger()['files']}
        self.assertEqual(set(records), {'src/app.py', 'build/', 'vendor/'})
        for skipped in ('build/', 'vendor/'):
            self.assertEqual(records[skipped]['status'], 'pending-decision')
        self.mark('reviewed', 'src/app.py')
        result = self.run_helper('status', '--out', str(self.out), '--show-pending', expected=2)
        self.assertIn('pruned-directory\tbuild/', result.stdout)
        self.assertEqual((self.out / 'decision-list.txt').read_text(encoding='utf-8'), 'build/\nvendor/\n')
        self.mark('excluded-confirmed', 'build/', 'vendor/', note='third-party and build output, checked by hand')
        self.run_helper('status', '--out', str(self.out))

    def test_ignored_target_inside_another_repository_is_inventoried_itself(self):
        (self.repo / '.gitignore').write_bytes(b'ignored.py\nscratch/\n')
        target = self.repo / 'scratch' / 'target'
        (target / 'src').mkdir(parents=True)
        (target / 'src' / 'real.py').write_bytes(b'print(1)\n')
        result = self.run_helper('create', '--repo', str(target), '--out', str(self.out))
        self.assertIn('ignored by the enclosing Git repository', result.stderr)
        ledger = self.ledger()
        self.assertEqual(Path(ledger['repo_root']), target.resolve())
        self.assertEqual([item['path'] for item in ledger['files']], ['src/real.py'])

    def test_subdirectory_of_a_repository_resolves_to_its_root(self):
        (self.repo / 'pkg').mkdir()
        (self.repo / 'pkg' / 'mod.py').write_bytes(b'print(1)\n')
        result = self.run_helper('create', '--repo', str(self.repo / 'pkg'), '--out', str(self.out))
        self.assertIn('inventorying its root', result.stderr)
        self.assertIn('tracked.py', {item['path'] for item in self.ledger()['files']})

    def test_nul_bytes_exclude_only_files_without_a_text_extension(self):
        (self.repo / 'query.sql').write_bytes('SELECT 1;\n'.encode('utf-16-le'))
        (self.repo / 'blob.dat').write_bytes(b'\x00\x01\x02')
        records = self.records()
        self.assertEqual(records['query.sql']['status'], 'pending-decision')
        self.assertEqual(records['query.sql']['kind'], 'binary-or-encoded-text')
        self.assertEqual(records['blob.dat']['status'], 'excluded')

    def test_empty_inventory_is_not_complete(self):
        empty = self.base / 'empty-repo'
        empty.mkdir()
        subprocess.run(['git', '-C', str(empty), 'init'], check=True, capture_output=True, timeout=15, env=self.git_env)
        result = self.run_helper('create', '--repo', str(empty), '--out', str(self.out))
        self.assertIn('inventory is empty', result.stderr)
        result = self.run_helper('status', '--out', str(self.out), expected=2)
        self.assertFalse(json.loads(result.stdout)['coverage_complete'])

    def test_each_open_or_unknown_status_blocks_completion(self):
        for status in ('pending', 'pending-decision', 'unreadable', 'todo'):
            with self.subTest(status=status):
                self.records()
                ledger = self.ledger()
                for item in ledger['files']:
                    item['status'] = 'reviewed'
                ledger['files'][0]['status'] = status
                (self.out / 'ledger.json').write_text(json.dumps(ledger), encoding='utf-8')
                result = self.run_helper('status', '--out', str(self.out), '--show-pending', expected=2)
                self.assertIn(f"{status}\t", result.stdout)

    def test_mark_rejects_dispositions_without_evidence(self):
        self.records()
        before = (self.out / 'ledger.json').read_bytes()
        result = self.mark('excluded-confirmed', 'tracked.py', expected=2)
        self.assertIn('needs --note', result.stderr)
        result = self.mark('context-reviewed', 'README.md', 'tracked.py', expected=2)
        self.assertIn('context entries only', result.stderr)
        self.assertEqual(before, (self.out / 'ledger.json').read_bytes())

        self.mark('context-reviewed', 'README.md')
        result = self.mark('excluded-confirmed', 'tracked.py', note='generated from tracked.in')
        self.assertEqual(json.loads(result.stdout)['review_scope']['excluded_confirmed'], 1)
        records = {item['path']: item for item in self.ledger()['files']}
        self.assertEqual(records['tracked.py']['review_note'], 'generated from tracked.in')
        # Reviewing it afterwards must not keep the exclusion's rationale.
        self.mark('reviewed', 'tracked.py')
        records = {item['path']: item for item in self.ledger()['files']}
        self.assertEqual(records['tracked.py']['status'], 'reviewed')
        self.assertNotIn('review_note', records['tracked.py'])

    def test_unreadable_entry_cannot_be_marked_reviewed(self):
        self.git('add', 'untracked.py')
        (self.repo / 'untracked.py').unlink()
        records = self.records()
        self.assertEqual(records['untracked.py']['status'], 'unreadable')
        self.assertEqual((self.out / 'unreadable-list.txt').read_text(encoding='utf-8'), 'untracked.py\n')
        result = self.mark('reviewed', 'untracked.py', expected=2)
        self.assertIn('still unreadable', result.stderr)
        self.mark('excluded-confirmed', 'untracked.py', note='deleted in the working tree')

    def test_generated_marker_counts_only_in_a_code_header(self):
        (self.repo / 'api.pb.go').write_bytes(b'// Code generated by protoc-gen-go. DO NOT EDIT.\npackage api\n')
        (self.repo / 'rules.py').write_bytes(b'x = 1\n' * 20 + b'MARKERS = ("do not edit", "@generated")\n')
        (self.repo / 'GUIDE.md').write_bytes(b'# Guide\n\nFiles under dist/ are generated. Do not edit them.\n')
        records = self.records()
        self.assertEqual(records['api.pb.go']['kind'], 'generated-or-built')
        self.assertEqual(records['rules.py']['status'], 'pending')
        self.assertEqual(records['GUIDE.md']['scope'], 'context')

    def test_non_ascii_paths_survive_a_legacy_console_encoding(self):
        (self.repo / '\u6e2c\u8a66.py').write_bytes(b'print(1)\n')
        legacy = {'PYTHONIOENCODING': 'cp1252'}
        self.run_helper('create', '--repo', str(self.repo), '--out', str(self.out), env=legacy)
        # Take the name from the ledger: Git may report it in a different Unicode normal form.
        name = next(item['path'] for item in self.ledger()['files'] if item['path'].endswith('.py')
                    and not item['path'].isascii())
        result = self.run_helper('status', '--out', str(self.out), '--show-pending', expected=2, env=legacy)
        self.assertIn(name, result.stdout)
        self.run_helper('mark', '--out', str(self.out), '--status', 'reviewed', '--stdin',
                        env=legacy, stdin=(name + '\r\n').encode('utf-8'))
        paths_file = self.base / 'paths.txt'
        paths_file.write_bytes(b'tracked.py\nuntracked.py\n')
        self.run_helper('mark', '--out', str(self.out), '--status', 'reviewed', '--paths-file', str(paths_file))
        statuses = {item['path']: item['status'] for item in self.ledger()['files']}
        self.assertEqual({statuses[name], statuses['tracked.py'], statuses['untracked.py']}, {'reviewed'})
        self.assertNotIn(name, (self.out / 'review-list.txt').read_text(encoding='utf-8'))

    @unittest.skipUnless(os.name == 'posix', 'needs a byte-string argument to name a non-UTF-8 path')
    def test_path_that_is_not_utf8_does_not_crash_create(self):
        blob = self.git('hash-object', '-w', 'tracked.py').strip()
        subprocess.run([b'git', b'-C', os.fsencode(self.repo), b'update-index', b'--add', b'--cacheinfo',
                        b'100644,' + blob + b',caf\xe9.py'], check=True, capture_output=True, timeout=15, env=self.git_env)
        self.run_helper('create', '--repo', str(self.repo), '--out', str(self.out))
        self.assertFalse((self.out / 'ledger.json.tmp').exists())
        self.run_helper('status', '--out', str(self.out), '--show-pending', expected=2)
        raw = (self.out / 'unreadable-list.txt').read_bytes()
        self.assertIn(b'caf\xe9.py', raw)

    @unittest.skipUnless(os.name == 'posix' and os.geteuid() != 0, 'needs POSIX permissions and a non-root user')
    def test_git_directory_that_cannot_be_listed_fails_creation(self):
        locked = self.repo / 'locked'
        locked.mkdir()
        (locked / 'new.py').write_bytes(b'print(1)\n')
        locked.chmod(0)
        self.addCleanup(locked.chmod, 0o755)
        result = self.run_helper('create', '--repo', str(self.repo), '--out', str(self.out), expected=1)
        self.assertIn('could not open directory', result.stderr)
        self.assertFalse((self.out / 'ledger.json').exists())

    def test_unknown_path_does_not_partially_update_ledger(self):
        self.create()
        before = (self.out / 'ledger.json').read_bytes()
        self.run_helper('mark', '--out', str(self.out), '--status', 'reviewed',
                        '--path', 'tracked.py', '--path', 'missing.py', expected=2)
        self.assertEqual(before, (self.out / 'ledger.json').read_bytes())

    def test_packaged_helpers_are_identical_and_runnable(self):
        for platform in ('codex', 'claude'):
            with self.subTest(platform=platform):
                helper = ROOT / f'dist/{platform}/skills/audit-repository/scripts/repo_inventory.py'
                self.assertEqual(HELPER.read_bytes(), helper.read_bytes())
                self.create(helper=helper)
                self.run_helper('status', '--out', str(self.out), expected=2, helper=helper)


if __name__ == '__main__':
    unittest.main()
