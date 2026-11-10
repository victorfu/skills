"""Exercise the shipped audit helper against isolated Git repositories."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'skills/audit-repository/scripts/repo_inventory.py'


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        self.out = self.base / 'audit'
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
                              capture_output=True, timeout=15).stdout

    def run_helper(self, *args, expected=0, helper=HELPER):
        result = subprocess.run([sys.executable, str(helper), *args],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

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
