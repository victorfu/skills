#!/usr/bin/env python3
"""Run evals/ against the generated Claude package with `claude plugin eval`.

Every run is a real model call on your account, so this is run by hand, never in CI.
Extra arguments go to the CLI, for example: --case 'bare-*' --runs 3 --model <id>.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main(extra):
    claude = shutil.which('claude')
    if not claude:
        sys.exit('FAIL: claude CLI not found on PATH')
    # Evaluate what would ship: refuse a dist/ that is out of date with skills/.
    if subprocess.run([sys.executable, str(ROOT / 'tools' / 'build.py'), '--check']).returncode:
        sys.exit('FAIL: dist/ is stale; run tools/build.py first')
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        # The CLI looks for cases below the plugin directory, and build.py removes anything it
        # did not generate from dist/, so assemble package and cases in a throwaway copy.
        plugin = Path(temp) / 'devflow'
        shutil.copytree(ROOT / 'dist' / 'claude', plugin)
        shutil.copytree(ROOT / 'evals', plugin / 'evals', ignore=shutil.ignore_patterns('results', '__pycache__'))
        code = subprocess.run([claude, 'plugin', 'eval', str(plugin), '--no-publish', '--trust-plugin', '--scaffold', *extra]).returncode
        try:
            results = plugin / 'evals' / 'results'
            if results.is_dir():
                shutil.copytree(results, ROOT / 'evals' / 'results', dirs_exist_ok=True)
                print(f'Reports copied to {ROOT / "evals" / "results"}')
        except OSError as error:
            # Keep the CLI's exit code even when the reports cannot be copied back.
            print(f'WARN: could not copy reports: {error}', file=sys.stderr)
    return code

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
