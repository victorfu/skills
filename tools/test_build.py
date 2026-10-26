"""Packaging regressions run only in temporary copies, never installed caches."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import build


def write_lf(path, text):
    # write_text would emit CRLF on Windows, which the generator rejects.
    path.write_bytes(text.encode('utf-8'))


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
        original = (self.root / 'skills/resolve-github-issue/SKILL.md').read_bytes()
        for platform in ('codex', 'claude'):
            adapted = (self.root / f'dist/{platform}/skills/resolve-github-issue/SKILL.md').read_bytes()
            if platform == 'claude':
                adapted = adapted.replace(b'disable-model-invocation: true\n', b'', 1)
            self.assertEqual(original, adapted)

    def test_codex_only_metadata_stays_out_of_claude(self):
        self.run_build()
        self.assertTrue((self.root / 'dist/codex/skills/resolve-github-issue/agents/openai.yaml').is_file())
        self.assertFalse((self.root / 'dist/claude/skills/resolve-github-issue/agents').exists())

    def test_build_hashes_match_shipped_files_in_stable_order(self):
        self.run_build()
        for platform in ('codex', 'claude'):
            package = self.root / f'dist/{platform}'
            hashes = json.loads((package / 'BUILD.json').read_text(encoding='utf-8'))['sha256']
            self.assertEqual(list(hashes), sorted(hashes))
            shipped = {p.relative_to(package).as_posix() for p in (package / 'skills').rglob('*') if p.is_file()}
            self.assertEqual(set(hashes), shipped)
            for name, digest in hashes.items():
                self.assertEqual(hashlib.sha256((package / name).read_bytes()).hexdigest(), digest)

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
            write_lf(p, p.read_text(encoding='utf-8').replace('resolve-github-issue', 'another-workflow'))
        self.run_build()
        self.assertTrue((self.root / 'dist/codex/skills/another-workflow/SKILL.md').is_file())
        shutil.rmtree(new)
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.run_build(check=True)
        self.run_build()
        self.run_build(check=True)
        for platform in ('codex', 'claude'):
            self.assertFalse((self.root / f'dist/{platform}/skills/another-workflow').exists())

    def test_hidden_files_are_not_packaged(self):
        (self.root / 'skills/.DS_Store').write_bytes(b'junk')
        (self.root / 'skills/resolve-github-issue/.DS_Store').write_bytes(b'junk')
        self.run_build()
        self.run_build(check=True)
        self.assertEqual([p for p in (self.root / 'dist').rglob('.DS_Store')], [])

    def test_reject_implicit_invocation(self):
        path = self.root / 'skills/resolve-github-issue/agents/openai.yaml'
        write_lf(path, path.read_text(encoding='utf-8').replace('false', 'true'))
        with self.assertRaisesRegex(ValueError, 'Explicit invocation'):
            self.run_build()

    def test_reject_wrong_invocation_target(self):
        path = self.root / 'skills/resolve-github-issue/agents/openai.yaml'
        original = path.read_text(encoding='utf-8')
        invocation = '$victorfu-skills:resolve-github-issue'
        for target in ('$resolve-github-issue', '$other-plugin:resolve-github-issue', invocation + '-other'):
            with self.subTest(target=target):
                write_lf(path, original.replace(invocation, target))
                with self.assertRaisesRegex(ValueError, 'Missing plugin-qualified invocation name'):
                    self.run_build()

    def test_reject_empty_frontmatter(self):
        write_lf(self.root / 'skills/resolve-github-issue/SKILL.md', '---\n\n---\nbody\n')
        with self.assertRaisesRegex(ValueError, 'YAML mapping'):
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
