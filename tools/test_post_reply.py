"""Offline tests for address-review-feedback/scripts/post_reply.py: gh is never run."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/address-review-feedback/scripts'))
sys.path.insert(0, str(ROOT / 'skills/watch-pr-feedback/scripts'))
import post_reply
import watch_pr

URL = 'https://github.com/o/r/pull/7'


class PostReplyTests(unittest.TestCase):
    def test_marker_matches_the_watcher(self):
        # The skills ship separately, so each keeps its own copy of the marker.
        self.assertEqual(post_reply.AGENT_MARKER, watch_pr.AGENT_MARKER)

    def test_marker_is_appended_once(self):
        body = post_reply.with_marker('Fixed in abc123.\n')
        self.assertEqual(body, f'Fixed in abc123.\n\n{post_reply.AGENT_MARKER}')
        self.assertEqual(post_reply.with_marker(body), body)

    def test_empty_body_is_refused(self):
        with self.assertRaises(ValueError):
            post_reply.with_marker(' \n')

    def post(self, *flags, body='已修正，見 abc123。'):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'reply.md'
            path.write_text(body, encoding='utf-8')
            done = subprocess.CompletedProcess([], 0, stdout=b'{"id":9,"html_url":"u"}\n', stderr=b'')
            argv = ['post_reply.py', URL, '--body-file', str(path), *flags]
            with patch.object(sys, 'argv', argv), \
                    patch.object(post_reply.subprocess, 'run', return_value=done) as run, \
                    redirect_stdout(io.StringIO()) as output:
                post_reply.main()
        command, kwargs = run.call_args.args[0], run.call_args.kwargs
        return command, json.loads(kwargs['input'].decode('utf-8'))['body'], json.loads(output.getvalue())

    def test_thread_reply_uses_the_replies_endpoint(self):
        command, body, result = self.post('--reply-to', '42')
        self.assertIn('repos/o/r/pulls/7/comments/42/replies', command)
        self.assertEqual(command[command.index('--hostname') + 1], 'github.com')
        self.assertTrue(body.startswith('已修正') and body.endswith(post_reply.AGENT_MARKER))
        self.assertEqual(result, {'id': 9, 'html_url': 'u'})

    def test_top_level_reply_uses_the_conversation(self):
        command, _, _ = self.post()
        self.assertIn('repos/o/r/issues/7/comments', command)

    def test_gh_failure_is_reported(self):
        failed = subprocess.CompletedProcess([], 1, stdout=b'', stderr=b'HTTP 404')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'reply.md'
            path.write_text('ok', encoding='utf-8')
            with patch.object(sys, 'argv', ['post_reply.py', URL, '--body-file', str(path)]), \
                    patch.object(post_reply.subprocess, 'run', return_value=failed), \
                    self.assertRaisesRegex(RuntimeError, 'HTTP 404'):
                post_reply.main()

    def test_non_pr_url_is_refused(self):
        with patch.object(sys, 'argv', ['post_reply.py', 'https://github.com/o/r/issues/7', '--body-file', '-']), \
                self.assertRaises(ValueError):
            post_reply.main()


if __name__ == '__main__':
    unittest.main()
