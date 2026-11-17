"""Offline tests for address-review-feedback/scripts/resolve_thread.py: gh is never run."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/address-review-feedback/scripts'))
import resolve_thread

URL = 'https://github.com/o/r/pull/7'


def page(threads, cursor=None):
    return {'data': {'repository': {'pullRequest': {'reviewThreads': {
        'pageInfo': {'hasNextPage': cursor is not None, 'endCursor': cursor},
        'nodes': [{'id': thread_id, 'isResolved': resolved,
                   'comments': {'nodes': [{'databaseId': comment} for comment in comments]}}
                  for thread_id, resolved, comments in threads]}}}}}


RESOLVED = {'data': {'resolveReviewThread': {'thread': {'id': 'T2', 'isResolved': True}}}}


class ResolveThreadTests(unittest.TestCase):
    def run_script(self, comment, responses):
        replies = [subprocess.CompletedProcess([], 0, json.dumps(r), '') if isinstance(r, dict) else r
                   for r in responses]
        with patch.object(sys, 'argv', ['resolve_thread.py', URL, '--comment', str(comment)]), \
                patch.object(resolve_thread.subprocess, 'run', side_effect=replies) as run, \
                redirect_stdout(io.StringIO()) as output:
            resolve_thread.main()
        return [call.args[0] for call in run.call_args_list], json.loads(output.getvalue())

    def test_finds_the_thread_on_a_later_page_and_resolves_it(self):
        commands, result = self.run_script(42, [page([('T1', False, [1, 2])], cursor='next'),
                                                page([('T2', False, [41, 42])]), RESOLVED])
        self.assertEqual(result, {'thread_id': 'T2', 'resolved': True, 'already_resolved': False})
        self.assertEqual(commands[0][:5], ['gh', 'api', 'graphql', '--hostname', 'github.com'])
        self.assertIn('number=7', commands[0])
        self.assertEqual(commands[0][commands[0].index('number=7') - 1], '-F')
        self.assertNotIn('cursor=next', commands[0])
        self.assertIn('cursor=next', commands[1])
        self.assertIn('resolveReviewThread', commands[2][commands[2].index('-f') + 1])
        self.assertIn('thread=T2', commands[2])

    def test_already_resolved_thread_is_left_alone(self):
        commands, result = self.run_script(42, [page([('T2', True, [42])])])
        self.assertEqual(len(commands), 1)
        self.assertTrue(result['already_resolved'])

    def test_comment_that_is_in_no_thread_is_an_error(self):
        with self.assertRaises(ValueError):
            self.run_script(99, [page([('T1', False, [1])])])

    def test_gh_failure_and_unconfirmed_resolution_are_errors(self):
        failed = subprocess.CompletedProcess([], 1, '', 'Resource not accessible by integration')
        with self.assertRaisesRegex(RuntimeError, 'not accessible'):
            self.run_script(42, [page([('T2', False, [42])]), failed])
        unconfirmed = {'data': {'resolveReviewThread': {'thread': {'id': 'T2', 'isResolved': False}}}}
        with self.assertRaises(RuntimeError):
            self.run_script(42, [page([('T2', False, [42])]), unconfirmed])

    def test_non_pr_url_is_refused(self):
        with patch.object(sys, 'argv', ['resolve_thread.py', 'https://github.com/o/r/issues/7', '--comment', '1']), \
                self.assertRaises(ValueError):
            resolve_thread.main()


if __name__ == '__main__':
    unittest.main()
