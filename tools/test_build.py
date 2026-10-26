"""Packaging regressions run only in temporary copies, never installed caches."""
import contextlib
import io
from pathlib import Path
import shutil
import tempfile
import unittest

import build


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original_root = build.ROOT
        shutil.copytree(build.ROOT / 'skills', self.root / 'skills')
        shutil.copyfile(build.ROOT / 'release.json', self.root / 'release.json')
        build.ROOT = self.root
        self.addCleanup(setattr, build, 'ROOT', self.original_root)

    def run_build(self, check=False):
        with contextlib.redirect_stdout(io.StringIO()):
            build.build(check)

    def test_reproducible_and_parity(self):
        self.run_build()
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.run_build()
        self.run_build(check=True)
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        for platform in ('codex', 'claude'):
            original = (self.root / 'skills/resolve-github-issue/SKILL.md').read_bytes()
            adapted = (self.root / f'dist/{platform}/skills/resolve-github-issue/SKILL.md').read_bytes()
            if platform == 'claude':
                adapted = adapted.replace(b'disable-model-invocation: true\n', b'', 1)
            self.assertEqual(original, adapted)

    def test_drift_check_is_read_only(self):
        self.run_build()
        output = self.root / 'dist/claude/skills/resolve-github-issue/SKILL.md'
        output.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.run_build(check=True)
        self.assertEqual(output.read_bytes(), b'changed')

    def test_new_and_removed_skill(self):
        source = self.root / 'skills/resolve-github-issue'
        new = self.root / 'skills/another-workflow'
        shutil.copytree(source, new)
        for p in (new / 'SKILL.md', new / 'agents/openai.yaml'):
            p.write_text(p.read_text(encoding='utf-8').replace('resolve-github-issue', 'another-workflow'), encoding='utf-8')
        self.run_build()
        self.assertTrue((self.root / 'dist/codex/skills/another-workflow/SKILL.md').is_file())
        shutil.rmtree(new)
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.run_build(check=True)
        self.run_build()
        self.run_build(check=True)
        self.assertFalse((self.root / 'dist/claude/skills/another-workflow/SKILL.md').exists())

    def test_reject_implicit_invocation(self):
        path = self.root / 'skills/resolve-github-issue/agents/openai.yaml'
        path.write_text(path.read_text(encoding='utf-8').replace('false', 'true'), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Explicit invocation'):
            self.run_build()

    def test_reject_missing_reference(self):
        (self.root / 'skills/resolve-github-issue/references/github-workflow.md').unlink()
        with self.assertRaisesRegex(ValueError, 'Broken reference'):
            self.run_build()

    def test_reject_output_symlink(self):
        outside = self.root / 'outside'
        outside.mkdir()
        try:
            (self.root / 'dist').symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('OS does not permit symlink creation')
        with self.assertRaisesRegex(ValueError, 'Symlink output refused'):
            self.run_build()
        self.assertEqual(list(outside.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
