"""Offline regression tests: no GitHub credentials, pushes or live webhooks."""
import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/watch-pr-feedback/scripts'
sys.path.insert(0, str(SCRIPTS))
import watch_pr as api
import hybrid_watch as hybrid
import webhook_receiver as receiver

PR = {'state': 'OPEN', 'headRefOid': 'abc', 'url': 'https://github.com/o/r/pull/1'}
TARGET = {'host': 'github.com', 'repo': 'o/r', 'pr': 1}
ITEM = {'key': 'review_comment:1', 'body': 'fix this', 'user': 'reviewer'}
FAIL = [{'name': 'test', 'bucket': 'fail'}]
MARKER = api.AGENT_MARKER


def setUpModule():
    # Every run resolves the gh account; keep the suite offline.
    patcher = patch.object(api, 'current_login', return_value='me')
    patcher.start()
    unittest.addModuleCleanup(patcher.stop)


def state():
    return {'mode': 'hybrid', 'target': TARGET, 'head': 'abc', 'seen_versions': {},
            'ci_reported': [], 'quiet_since': 0, 'settling': {}}


class PollTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'state.json'
        self.now = 0
        self.write_state()

    def write_state(self, **extra):
        # No poll_settling by default: that is what a state file from before the timer looks like.
        api.save_state(self.path, {'target': TARGET, 'head': 'abc', 'seen': [],
                                   'quiet_since': 0, 'ci_reported': [], **extra})

    def saved(self):
        return api.load_state(self.path)

    def invoke(self, items, max_wait=0, pr=PR, polls=None, checks=()):
        # polls: one feedback list per fetch, the last repeating, for changes within a single run.
        remaining = list(polls or [])

        def feedback(*_, **__):
            if not remaining:
                return items
            return remaining.pop(0) if len(remaining) > 1 else remaining[0]

        argv = ['watch_pr.py', PR['url'], '--state', str(self.path),
                '--interval', '1', '--settle', '3', '--max-wait', str(max_wait)]

        def sleep(seconds):
            self.now += seconds

        with patch.object(sys, 'argv', argv), patch.object(api, 'fetch_pr', return_value=pr), \
                patch.object(api, 'fetch_feedback', side_effect=feedback), \
                patch.object(api, 'fetch_checks', return_value=list(checks)), \
                patch.object(api.time, 'time', side_effect=lambda: self.now), \
                patch.object(api.time, 'sleep', side_effect=sleep), redirect_stdout(io.StringIO()) as output:
            api.main()
        return json.loads(output.getvalue())

    def test_settle_survives_waiting_and_delivers_once(self):
        event = self.invoke([ITEM], max_wait=1)
        self.assertEqual(event['event'], 'waiting')
        self.assertEqual(event['unsettled_feedback'], 1)
        self.assertEqual(self.invoke([ITEM], max_wait=1)['event'], 'waiting')
        event = self.invoke([ITEM], max_wait=1)
        self.assertEqual(event['event'], 'feedback')
        self.assertEqual(event['items'], [ITEM])
        self.assertEqual(self.now, 3)
        self.assertEqual(self.invoke([ITEM])['event'], 'waiting')

    def test_new_comment_restarts_persisted_settle(self):
        self.assertEqual(self.invoke([ITEM])['event'], 'waiting')
        other = dict(ITEM, key='review_comment:2')
        self.now = 2
        self.assertEqual(self.invoke([ITEM, other])['event'], 'waiting')
        self.now = 3
        self.assertEqual(self.invoke([ITEM, other])['event'], 'waiting')
        self.now = 5
        event = self.invoke([ITEM, other])
        self.assertEqual(event['event'], 'feedback')
        self.assertEqual(event['items'], [ITEM, other])

    def test_replaced_comment_restarts_settle_at_the_same_count(self):
        other = dict(ITEM, key='review_comment:2')
        self.assertEqual(self.invoke([ITEM])['event'], 'waiting')
        self.now = 2
        self.assertEqual(self.invoke([other])['event'], 'waiting')
        self.now = 3
        self.assertEqual(self.invoke([other])['event'], 'waiting')
        self.now = 5
        event = self.invoke([other])
        self.assertEqual(event['event'], 'feedback')
        self.assertEqual(event['items'], [other])

    def test_partly_disappeared_batch_keeps_its_timer(self):
        other = dict(ITEM, key='review_comment:2')
        self.assertEqual(self.invoke([ITEM, other])['event'], 'waiting')
        self.now = 2
        self.assertEqual(self.invoke([ITEM])['event'], 'waiting')
        self.now = 3
        event = self.invoke([ITEM])
        self.assertEqual(event['event'], 'feedback')
        self.assertEqual(event['items'], [ITEM])

    def test_comment_that_returns_after_disappearing_restarts_settle(self):
        other = dict(ITEM, key='review_comment:2')
        self.assertEqual(self.invoke([ITEM, other])['event'], 'waiting')
        self.now = 1
        self.assertEqual(self.invoke([ITEM])['event'], 'waiting')
        self.now = 2
        self.assertEqual(self.invoke([ITEM, other])['event'], 'waiting')
        self.now = 3
        self.assertEqual(self.invoke([ITEM, other])['event'], 'waiting')
        self.now = 5
        self.assertEqual(self.invoke([ITEM, other])['event'], 'feedback')

    def test_comment_arriving_within_one_run_restarts_settle(self):
        other = dict(ITEM, key='review_comment:2')
        event = self.invoke(None, max_wait=10, polls=[[ITEM], [ITEM], [ITEM, other]])
        self.assertEqual(event['event'], 'feedback')
        self.assertEqual(event['items'], [ITEM, other])
        self.assertEqual(self.now, 5)

    def test_delivery_records_the_batch_and_clears_the_timer(self):
        self.assertEqual(self.invoke([ITEM])['event'], 'waiting')
        self.assertEqual(self.saved()['poll_settling'], {'keys': [ITEM['key']], 'since': 0})
        self.now = 3
        self.assertEqual(self.invoke([ITEM])['event'], 'feedback')
        saved = self.saved()
        self.assertEqual(saved['seen'], [ITEM['key']])
        self.assertEqual(saved['quiet_since'], 3)
        self.assertNotIn('poll_settling', saved)

    def test_push_during_settle_does_not_restart_it(self):
        pushed = dict(PR, headRefOid='def')
        self.assertEqual(self.invoke([ITEM])['event'], 'waiting')
        self.now = 2
        self.assertEqual(self.invoke([ITEM], pr=pushed)['event'], 'waiting')
        self.assertEqual(self.saved()['head'], 'def')
        self.now = 3
        self.assertEqual(self.invoke([ITEM], pr=pushed)['event'], 'feedback')

    def test_unreadable_timer_restarts_settle(self):
        key = ITEM['key']
        for bad in ({}, [], 'soon', {'keys': [key]}, {'since': 0}, {'keys': None, 'since': 0},
                    {'keys': [key], 'since': None}, {'keys': [key], 'since': 'x'},
                    {'keys': [key], 'since': True}, {'keys': [1], 'since': 0}):
            with self.subTest(poll_settling=bad):
                self.write_state(poll_settling=bad)
                self.now = 10
                self.assertEqual(self.invoke([ITEM])['event'], 'waiting')
                self.assertEqual(self.saved()['poll_settling'], {'keys': [key], 'since': 10})
                self.now = 13
                self.assertEqual(self.invoke([ITEM])['event'], 'feedback')

    def test_timer_from_the_future_waits_one_settle_window(self):
        self.write_state(poll_settling={'keys': [ITEM['key']], 'since': 1000})
        self.now = 10
        self.assertEqual(self.invoke([ITEM])['event'], 'waiting')
        self.assertEqual(self.saved()['poll_settling']['since'], 10)
        self.now = 13
        self.assertEqual(self.invoke([ITEM])['event'], 'feedback')

    def run_with_push_during_checks(self, checks, max_wait=0):
        # The remote head moves from abc to def after the PR query, before the checks query.
        remote = dict(PR)

        def push_then_checks(*_):
            remote['headRefOid'] = 'def'
            return checks

        argv = ['watch_pr.py', PR['url'], '--state', str(self.path),
                '--interval', '1', '--max-wait', str(max_wait)]
        with patch.object(sys, 'argv', argv), \
                patch.object(api, 'fetch_pr', side_effect=lambda *_: dict(remote)), \
                patch.object(api, 'fetch_feedback', return_value=[]), \
                patch.object(api, 'fetch_checks', side_effect=push_then_checks), \
                patch.object(api.time, 'time', side_effect=lambda: self.now), \
                redirect_stdout(io.StringIO()) as output:
            api.main()
        return json.loads(output.getvalue())

    def test_push_during_a_poll_restarts_quiet_instead_of_reporting_old_head(self):
        self.now = 1000
        event = self.run_with_push_during_checks([])
        self.assertEqual(event['event'], 'waiting')
        self.assertEqual(event['head'], 'def')
        self.assertEqual(event['quiet_seconds'], 0)
        saved = self.saved()
        self.assertEqual((saved['head'], saved['quiet_since']), ('def', 1000))

    def test_push_during_a_poll_does_not_charge_failing_checks_to_old_head(self):
        self.now = 1000
        event = self.run_with_push_during_checks(FAIL)
        self.assertEqual(event['event'], 'ci_failed')
        self.assertEqual(event['head'], 'def')
        self.assertEqual(self.saved()['ci_reported'], ['def'])

    def test_poll_gives_up_when_the_head_keeps_moving(self):
        heads = iter(range(100))
        argv = ['watch_pr.py', PR['url'], '--state', str(self.path), '--max-wait', '0']
        with patch.object(sys, 'argv', argv), \
                patch.object(api, 'fetch_pr', side_effect=lambda *_: dict(PR, headRefOid=str(next(heads)))), \
                patch.object(api, 'fetch_feedback', return_value=[]), \
                patch.object(api, 'fetch_checks', return_value=[]), \
                redirect_stdout(io.StringIO()) as output, self.assertRaises(api.GhError):
            api.main()
        self.assertEqual(output.getvalue(), '')
        self.assertEqual(self.saved()['head'], 'abc')

    def test_disappeared_batch_does_not_leave_an_old_timer(self):
        self.assertEqual(self.invoke([ITEM])['event'], 'waiting')
        self.now = 2
        self.assertEqual(self.invoke([])['event'], 'waiting')
        self.assertNotIn('poll_settling', self.saved())
        self.now = 4
        self.assertEqual(self.invoke([ITEM])['event'], 'waiting')
        self.now = 7
        self.assertEqual(self.invoke([ITEM])['event'], 'feedback')

    def test_baseline_ci_failure_is_not_reported_again_for_the_same_head(self):
        self.path.unlink()
        event = self.invoke([], checks=FAIL)
        self.assertEqual((event['event'], event['ci']), ('baseline', 'failing'))
        self.assertEqual(self.saved()['ci_reported'], ['abc'])
        self.assertEqual(self.invoke([], checks=FAIL)['event'], 'waiting')
        event = self.invoke([], checks=FAIL, pr=dict(PR, headRefOid='def'))
        self.assertEqual((event['event'], event['head']), ('ci_failed', 'def'))

    def test_baseline_without_ci_failure_leaves_the_head_reportable(self):
        self.path.unlink()
        self.assertEqual(self.invoke([])['ci'], 'none')
        self.assertEqual(self.saved()['ci_reported'], [])
        self.assertEqual(self.invoke([], checks=FAIL)['event'], 'ci_failed')


class HybridTests(unittest.TestCase):
    def test_batch_survives_restart_and_ack_is_idempotent(self):
        value = state()
        self.assertIsNone(hybrid.evaluate(value, PR, [ITEM], [], 10, 600, 60))
        value = json.loads(json.dumps(value))
        event = hybrid.evaluate(value, PR, [ITEM], [], 70, 600, 60)
        self.assertEqual(event['event'], 'feedback')
        value = json.loads(json.dumps(value))
        self.assertEqual(hybrid.evaluate(value, PR, [ITEM], [], 80, 600, 60), event)
        hybrid.acknowledge(value, event['batch_id'], 90)
        hybrid.acknowledge(value, event['batch_id'], 100)
        self.assertIsNone(hybrid.evaluate(value, PR, [ITEM], [], 100, 600, 60))
        with self.assertRaises(ValueError):
            hybrid.acknowledge(value, 'wrong', 100)

    def test_edit_after_excerpt_and_edit_during_pending_are_not_lost(self):
        original = dict(ITEM, body='x' * 400 + 'a')
        changed = dict(ITEM, body='x' * 400 + 'b')
        value = state()
        event = hybrid.evaluate(value, PR, [original], [], 0, 600, 0)
        self.assertLess(len(event['items'][0]['body']), 400)
        # Edited while the batch is still pending: the batch replays, the edit follows the ack.
        self.assertEqual(hybrid.evaluate(value, PR, [changed], [], 1, 600, 0), event)
        hybrid.acknowledge(value, event['batch_id'], 1)
        event2 = hybrid.evaluate(value, PR, [changed], [], 2, 600, 0)
        self.assertEqual(event2['event'], 'feedback')
        self.assertNotEqual(event['batch_id'], event2['batch_id'])

    def test_moved_or_outdated_comment_is_not_new_feedback(self):
        comment = dict(ITEM, path='a.py', line=10)
        value = state()
        event = hybrid.evaluate(value, PR, [comment], [], 0, 600, 0)
        hybrid.acknowledge(value, event['batch_id'], 1)
        pushed = dict(PR, headRefOid='def')
        for line in (14, None):
            self.assertIsNone(hybrid.evaluate(value, pushed, [dict(comment, line=line)], [], 2, 600, 0))
        review = {'key': 'review:1', 'body': '', 'state': 'COMMENTED'}
        event = hybrid.evaluate(value, pushed, [comment, review], [], 3, 600, 0)
        hybrid.acknowledge(value, event['batch_id'], 4)
        verdict = hybrid.evaluate(value, pushed, [comment, dict(review, state='CHANGES_REQUESTED')], [], 5, 600, 0)
        self.assertEqual([item['key'] for item in verdict['items']], ['review:1'])

    def test_state_from_before_the_hash_change_does_not_redeliver(self):
        comment = dict(ITEM, path='a.py', line=10)
        whole_item = hybrid.hashlib.sha256(json.dumps(comment, sort_keys=True).encode()).hexdigest()
        value = state()
        value['seen_versions'] = {comment['key']: whole_item}
        self.assertIsNone(hybrid.evaluate(value, PR, [comment], [], 1, 600, 0))
        self.assertEqual(value['seen_versions'], hybrid.versions([comment]))
        # A batch staged by the old code is acknowledged with old-format hashes.
        value = state()
        value['pending'] = {'event': {'event': 'feedback', 'batch_id': 'old'},
                            'versions': {comment['key']: whole_item}, 'ci_head': None}
        hybrid.acknowledge(value, 'old', 1)
        self.assertIsNone(hybrid.evaluate(value, PR, [comment], [], 2, 600, 0))
        edited = hybrid.evaluate(value, PR, [dict(comment, body='changed')], [], 3, 600, 0)
        self.assertEqual(edited['event'], 'feedback')

    def test_equal_count_changed_batch_restarts_settle(self):
        value = state()
        hybrid.evaluate(value, PR, [ITEM], [], 0, 600, 60)
        changed = dict(ITEM, body='changed')
        self.assertIsNone(hybrid.evaluate(value, PR, [changed], [], 59, 600, 60))
        self.assertIsNone(hybrid.evaluate(value, PR, [changed], [], 60, 600, 60))
        self.assertEqual(hybrid.evaluate(value, PR, [changed], [], 119, 600, 60)['event'], 'feedback')

    def test_ci_ack_once_per_head_and_old_head_discarded(self):
        value = state()
        event = hybrid.evaluate(value, PR, [], FAIL, 1, 600, 60)
        self.assertEqual(event['event'], 'ci_failed')
        hybrid.acknowledge(value, event['batch_id'], 2)
        self.assertIsNone(hybrid.evaluate(value, PR, [], FAIL, 3, 600, 60))
        new_pr = dict(PR, headRefOid='def')
        next_event = hybrid.evaluate(value, new_pr, [], FAIL, 4, 600, 60)
        self.assertNotEqual(event['batch_id'], next_event['batch_id'])
        self.assertIsNone(hybrid.evaluate(value, dict(PR, headRefOid='ghi'), [], [], 5, 600, 60))

    def test_closed_overrides_pending_and_pending_ci_blocks_quiet(self):
        value = state()
        self.assertIsNone(hybrid.evaluate(value, PR, [], [{'bucket': 'pending'}], 700, 600, 60))
        hybrid.evaluate(value, PR, [ITEM], [], 701, 600, 0)
        self.assertEqual(hybrid.evaluate(value, dict(PR, state='CLOSED'), [], [], 702, 600, 0)['event'], 'closed')

    def test_snapshot_retries_head_race(self):
        newer = dict(PR, headRefOid='def')
        with patch.object(api, 'fetch_pr', side_effect=[PR, newer, newer, newer]), \
                patch.object(api, 'fetch_feedback', return_value=[]) as fetch, \
                patch.object(api, 'fetch_checks', side_effect=[FAIL, []]):
            pr, _, checks = hybrid.snapshot('github.com', 'o/r', 1, set())
        self.assertEqual(pr['headRefOid'], 'def')
        self.assertEqual(checks, [])
        # Edit detection depends on unexcerpted bodies.
        self.assertTrue(all(call.kwargs.get('full') for call in fetch.call_args_list))

    def test_fetch_feedback_truncates_unless_full(self):
        long = [{'id': 1, 'user': 'reviewer', 'body': 'x' * 400}]
        for full, length in ((True, 400), (False, api.EXCERPT + 1)):
            with patch.object(api, 'gh_lines', side_effect=[long, [], []]):
                items = api.fetch_feedback('github.com', 'o/r', 1, set(), full=full)
            self.assertEqual(len(items[0]['body']), length)

    def test_failed_checks_query_is_not_reported_as_no_ci(self):
        def result(code, out='', err=''):
            return subprocess.CompletedProcess([], code, out, err)
        cases = [
            (result(1, json.dumps(FAIL)), FAIL),
            (result(8, '[{"bucket": "pending"}]'), [{'bucket': 'pending'}]),
            (result(1, err="no checks reported on the 'x' branch"), []),
        ]
        for completed, expected in cases:
            with patch.object(api.subprocess, 'run', return_value=completed):
                self.assertEqual(api.fetch_checks('github.com', 'o/r', 1), expected)
        for completed in (result(1, err='HTTP 502: Bad Gateway'), result(1), result(4, err='auth required')):
            with patch.object(api.subprocess, 'run', return_value=completed), self.assertRaises(api.GhError):
                api.fetch_checks('github.com', 'o/r', 1)

    def test_save_state_retries_a_locked_target_and_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'signal.json'
            replace, attempts = api.os.replace, []
            def busy_twice(source, target):
                attempts.append(1)
                if len(attempts) < 3:
                    raise PermissionError(13, 'Access is denied')
                replace(source, target)
            with patch.object(api.os, 'replace', side_effect=busy_twice), patch.object(api.time, 'sleep'):
                api.save_state(path, {'value': 1})
            self.assertEqual(api.load_state(path), {'value': 1})
            with patch.object(api.os, 'replace', side_effect=PermissionError(13, 'Access is denied')), \
                    patch.object(api.time, 'sleep'), self.assertRaises(PermissionError):
                api.save_state(path, {'value': 2})
            self.assertEqual(api.load_state(path), {'value': 1})
            self.assertEqual([entry.name for entry in Path(folder).iterdir()], ['signal.json'])

    def test_events_with_emoji_survive_a_legacy_console_encoding(self):
        code = ('import sys; sys.path.insert(0, sys.argv[1]); import watch_pr as api\n'
                'api.configure_output(); api.emit("feedback", body="\\u2705 \\u4fee\\u6b63")')
        env = dict(api.os.environ, PYTHONIOENCODING='ascii')
        result = subprocess.run([sys.executable, '-c', code, str(SCRIPTS)], capture_output=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout.decode('utf-8'))['body'], '✅ 修正')

    def test_signal_health_and_target(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'signal.json'
            self.assertEqual(hybrid.signal_status(path, TARGET, 10), (None, False))
            api.save_state(path, dict(target=TARGET, active=True, heartbeat=10, generation='a'))
            self.assertEqual(hybrid.signal_status(path, TARGET, 11), ('a', True))
            self.assertEqual(hybrid.signal_status(path, TARGET, 26), (None, False))
            self.assertEqual(hybrid.signal_status(path, dict(TARGET, pr=2), 11), (None, False))
            self.assertEqual(hybrid.signal_status(path, TARGET, 9), (None, False))
            self.assertIn('stale', hybrid.signal_problem(path, TARGET, 26)[1])
            api.save_state(path, dict(target=TARGET, active=False, heartbeat=10, generation='a', reason='gh exited (1)'))
            self.assertEqual(hybrid.signal_status(path, TARGET, 11), (None, False))
            self.assertEqual(hybrid.signal_problem(path, TARGET, 11)[1], 'gh exited (1)')
            path.write_text('{"target"', encoding='utf-8')
            self.assertEqual(hybrid.signal_status(path, TARGET, 11), (None, False))
            self.assertIn('unreadable', hybrid.signal_problem(path, TARGET, 11)[1])

    def test_settle_progress_survives_a_waiting_run(self):
        with tempfile.TemporaryDirectory() as folder:
            args = argparse.Namespace(pr=PR['url'], repo=None, host='github.com',
                state=str(Path(folder) / 'state'), signal=str(Path(folder) / 'signal'),
                ack=None, ignore_self=False, ignore_author=[], interval=60, quiet=600,
                settle=60, max_wait=30, reconcile=300)
            api.save_state(Path(args.state), state())
            clock = [0]
            def sleep(seconds):
                clock[0] += seconds
            def invoke():
                with patch.object(hybrid.time, 'time', side_effect=lambda: clock[0]), \
                        patch.object(hybrid.time, 'monotonic', side_effect=lambda: clock[0]), \
                        patch.object(hybrid.time, 'sleep', side_effect=sleep), \
                        patch.object(hybrid, 'snapshot', return_value=(PR, [ITEM], [])), \
                        redirect_stdout(io.StringIO()) as output:
                    hybrid.run(args)
                return json.loads(output.getvalue())
            waiting = invoke()
            self.assertEqual((waiting['event'], waiting['unsettled_feedback']), ('waiting', 1))
            self.assertFalse(waiting['receiver_active'])
            self.assertIn('not started', waiting['receiver_reason'])
            # The settle window started in the first run; a restart must not begin it again.
            self.assertEqual(invoke()['event'], 'feedback')
            self.assertEqual(clock[0], 60)

    def test_os_lock_releases_and_excludes_second_process(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state.json'
            code = 'import sys; sys.path.insert(0,sys.argv[1]); from watch_pr import state_lock; from pathlib import Path\nwith state_lock(Path(sys.argv[2])): pass'
            with api.state_lock(path):
                result = subprocess.run([sys.executable, '-c', code, str(SCRIPTS), str(path)], capture_output=True)
                self.assertNotEqual(result.returncode, 0)
            with api.state_lock(path):
                pass

    def test_scheduler_reconcile_fallback_settle_and_quiet(self):
        # Fake time verifies deadlines without sleeping or making network requests.
        for active, quiet, settle, items, expected in [
                (True, 1000, 60, [], [0, 300, 540]),
                (False, 1000, 60, [], list(range(0, 541, 60))),
                (True, 1000, 60, [ITEM], [0, 60]),
                (True, 100, 60, [], [0, 100])]:
            with self.subTest(active=active, quiet=quiet, items=items), tempfile.TemporaryDirectory() as folder:
                args = argparse.Namespace(pr=PR['url'], repo=None, host='github.com',
                    state=str(Path(folder) / 'state'), signal=str(Path(folder) / 'signal'),
                    ack=None, ignore_self=False, ignore_author=[], interval=60, quiet=quiet,
                    settle=settle, max_wait=540, reconcile=300)
                api.save_state(Path(args.state), state())
                clock, calls = [0], []
                def snap(*unused):
                    calls.append(clock[0])
                    return PR, items, []
                def sleep(seconds):
                    clock[0] += seconds
                with patch.object(hybrid.time, 'time', side_effect=lambda: clock[0]), \
                        patch.object(hybrid.time, 'monotonic', side_effect=lambda: clock[0]), \
                        patch.object(hybrid.time, 'sleep', side_effect=sleep), \
                        patch.object(hybrid, 'signal_status', return_value=('a', active)), \
                        patch.object(hybrid, 'snapshot', side_effect=snap), redirect_stdout(io.StringIO()):
                    hybrid.run(args)
                self.assertEqual(calls, expected)

    def test_receiver_http_filter_and_deduplicate(self):
        wakes = []
        server = receiver.HTTPServer(('127.0.0.1', 0), receiver.make_handler(TARGET, '/secret', lambda: wakes.append(1)))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            def post(payload, event='issue_comment', delivery='one', route='/secret'):
                request = Request(f'http://127.0.0.1:{server.server_port}{route}',
                    data=json.dumps(payload).encode(), headers={'X-GitHub-Event': event, 'X-GitHub-Delivery': delivery})
                with urlopen(request, timeout=2) as response:
                    return response.status
            payload = {'repository': {'full_name': 'o/r'}, 'issue': {'number': 1, 'pull_request': {}}}
            self.assertEqual(post(payload), 202)
            post(payload)
            post(dict(payload, issue={'number': 2, 'pull_request': {}}), delivery='two')
            self.assertEqual(len(wakes), 1)
            post({'repository': {'full_name': 'other/repo'}}, event='check_run', delivery='three')
            self.assertEqual(len(wakes), 1)
            with self.assertRaises(HTTPError):
                post(payload, route='/wrong')
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    def test_webhook_wakes_before_reconciliation_and_refetches(self):
        with tempfile.TemporaryDirectory() as folder:
            args = argparse.Namespace(pr=PR['url'], repo=None, host='github.com',
                state=str(Path(folder) / 'state'), signal=str(Path(folder) / 'signal'),
                ack=None, ignore_self=False, ignore_author=[], interval=60, quiet=600,
                settle=0, max_wait=540, reconcile=300)
            api.save_state(Path(args.state), state())
            clock, calls = [0], []
            def snap(*unused):
                calls.append(clock[0])
                return PR, [ITEM] if clock[0] >= 2 else [], []
            def sleep(seconds):
                clock[0] += seconds
            with patch.object(hybrid.time, 'time', side_effect=lambda: clock[0]), \
                    patch.object(hybrid.time, 'monotonic', side_effect=lambda: clock[0]), \
                    patch.object(hybrid.time, 'sleep', side_effect=sleep), \
                    patch.object(hybrid, 'signal_status', side_effect=lambda *a: ('new' if clock[0] >= 2 else 'old', True)), \
                    patch.object(hybrid, 'snapshot', side_effect=snap), redirect_stdout(io.StringIO()) as output:
                hybrid.run(args)
            self.assertEqual(calls, [0, 2])
            self.assertEqual(json.loads(output.getvalue())['event'], 'feedback')

    def test_baseline_replayed_and_ack_advances(self):
        with tempfile.TemporaryDirectory() as folder:
            args = argparse.Namespace(pr=PR['url'], repo=None, host='github.com',
                state=str(Path(folder) / 'state'), signal=str(Path(folder) / 'signal'),
                ack=None, ignore_self=False, ignore_author=[], interval=60, quiet=600,
                settle=0, max_wait=0, reconcile=300)
            def invoke():
                with patch.object(hybrid, 'snapshot', return_value=(PR, [ITEM], [])), redirect_stdout(io.StringIO()) as output:
                    hybrid.run(args)
                return json.loads(output.getvalue())
            baseline = invoke()
            self.assertEqual(baseline['event'], 'baseline')
            self.assertEqual(invoke(), baseline)
            args.ack = baseline['batch_id']
            self.assertEqual(invoke()['event'], 'waiting')
            self.assertEqual(invoke()['event'], 'waiting')

    def test_poll_default_preserves_legacy_events(self):
        with tempfile.TemporaryDirectory() as folder:
            argv = ['watch_pr.py', PR['url'], '--state', str(Path(folder) / 'state'),
                    '--include-self', '--settle', '0', '--max-wait', '0']
            with patch.object(sys, 'argv', argv), patch.object(api, 'fetch_pr', return_value=PR), \
                    patch.object(api, 'fetch_feedback', return_value=[]), \
                    patch.object(api, 'fetch_checks', return_value=[]), redirect_stdout(io.StringIO()) as output:
                api.main()
                baseline = json.loads(output.getvalue())
                self.assertEqual(baseline['event'], 'baseline')
                self.assertNotIn('batch_id', baseline)
            with patch.object(sys, 'argv', argv), patch.object(api, 'fetch_pr', return_value=PR), \
                    patch.object(api, 'fetch_feedback', return_value=[ITEM]), \
                    patch.object(api, 'fetch_checks', return_value=[]), redirect_stdout(io.StringIO()) as output:
                api.main()
                self.assertEqual(json.loads(output.getvalue())['event'], 'feedback')

    def test_receiver_owns_forwarder_and_cleans_up_on_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            signal = Path(folder) / 'signal.json'
            stop = signal.with_suffix('.json.stop')
            argv = ['webhook_receiver.py', PR['url'], '--signal', str(signal)]
            with patch.object(sys, 'argv', argv), patch.object(receiver, 'HTTPServer') as server_class, \
                    patch.object(receiver.subprocess, 'Popen') as popen:
                server = server_class.return_value
                server.server_port = 12345
                server.handle_request.side_effect = lambda: stop.touch()
                process = popen.return_value
                process.poll.return_value = None
                receiver.main()
                command = popen.call_args.args[0]
                self.assertEqual(command[:3], ['gh', 'webhook', 'forward'])
                self.assertIn('--repo=o/r', command)
                self.assertEqual(popen.call_args.kwargs['env']['GH_HOST'], 'github.com')
                process.terminate.assert_called_once()
                process.wait.assert_called_once()
                server.server_close.assert_called_once()
            self.assertFalse(api.load_state(signal)['active'])

    def run_receiver(self, folder, popen_setup, save=None):
        signal = Path(folder) / 'signal.json'
        argv = ['webhook_receiver.py', PR['url'], '--signal', str(signal)]
        with patch.object(sys, 'argv', argv), patch.object(receiver, 'HTTPServer') as server_class, \
                patch.object(receiver.subprocess, 'Popen') as popen, \
                patch.object(receiver, 'save_state', side_effect=save or api.save_state), \
                redirect_stderr(io.StringIO()) as errors:
            server_class.return_value.server_port = 12345
            popen_setup(popen, signal, server_class.return_value)
            try:
                receiver.main()
                code = 0
            except SystemExit as stop:
                code = stop.code
        return code, signal, popen.return_value, errors.getvalue()

    def test_forwarder_failure_is_reported_not_exit_zero(self):
        def dies(popen, signal, server):
            def launch(command, **kwargs):
                kwargs['stderr'].write(b'another forwarding session is active')
                return popen.return_value
            popen.side_effect = launch
            popen.return_value.poll.side_effect = [None, 1, 1]
        def missing(popen, signal, server):
            popen.side_effect = FileNotFoundError('gh')
        with tempfile.TemporaryDirectory() as folder:
            code, signal, process, errors = self.run_receiver(folder, dies)
            saved = api.load_state(signal)
            self.assertEqual(code, 1)
            self.assertFalse(saved['active'])
            self.assertIn('exited (1): another forwarding session is active', saved['reason'])
            self.assertIn(saved['reason'], errors)
            process.terminate.assert_not_called()
        with tempfile.TemporaryDirectory() as folder:
            code, signal, _, errors = self.run_receiver(folder, missing)
            self.assertEqual(code, 1)
            self.assertIn('could not start', api.load_state(signal)['reason'])

    def test_forwarder_is_stopped_even_when_signal_writes_fail(self):
        def stops(popen, signal, server):
            server.handle_request.side_effect = lambda: signal.with_suffix('.json.stop').touch()
            popen.return_value.poll.return_value = None
        with tempfile.TemporaryDirectory() as folder:
            code, _, process, errors = self.run_receiver(
                folder, stops, save=PermissionError(13, 'Access is denied'))
            self.assertEqual(code, 0)
            process.terminate.assert_called_once()
            self.assertIn('signal write failed', errors)

    def test_delivery_reaches_the_watcher_through_the_signal_file(self):
        with tempfile.TemporaryDirectory() as folder:
            signal = Path(folder) / 'signal.json'
            argv = ['webhook_receiver.py', PR['url'], '--signal', str(signal)]
            started = threading.Event()
            with patch.object(sys, 'argv', argv), patch.object(receiver.subprocess, 'Popen') as popen:
                popen.side_effect = lambda *a, **k: (started.set(), popen.return_value)[1]
                popen.return_value.poll.return_value = None
                worker = threading.Thread(target=receiver.main, daemon=True)
                worker.start()
                try:
                    self.assertTrue(started.wait(30))
                    url = next(part for part in popen.call_args.args[0] if part.startswith('--url=')).split('=', 1)[1]
                    self.assertIn('check_run', next(part for part in popen.call_args.args[0] if part.startswith('--events=')))
                    deadline = time.time() + 30
                    while hybrid.signal_status(signal, TARGET, time.time())[1] is False and time.time() < deadline:
                        time.sleep(0.05)
                    before, active = hybrid.signal_status(signal, TARGET, time.time())
                    self.assertTrue(active)
                    payload = {'repository': {'full_name': 'o/r'}, 'pull_request': {'number': 1}}
                    request = Request(url, data=json.dumps(payload).encode(),
                        headers={'X-GitHub-Event': 'pull_request_review', 'X-GitHub-Delivery': 'one'})
                    with urlopen(request, timeout=5) as response:
                        self.assertEqual(response.status, 202)
                    after, active = hybrid.signal_status(signal, TARGET, time.time())
                    self.assertTrue(active)
                    self.assertNotEqual(before, after)
                finally:
                    signal.with_suffix('.json.stop').touch()
                    worker.join(10)
            self.assertFalse(worker.is_alive())
            self.assertEqual(api.load_state(signal)['reason'], 'receiver stopped on request')



class OwnReplyTests(unittest.TestCase):
    def fetch(self, comments, ignored=(), self_login='me', reviews=(), issue_comments=()):
        def lines(path, jq, host):
            if '/reviews' in path:
                return [dict(r) for r in reviews]
            if '/issues/' in path:
                return [dict(c) for c in issue_comments]
            return [dict(c) for c in comments]

        with patch.object(api, 'gh_lines', side_effect=lines):
            return api.fetch_feedback('github.com', 'o/r', 1, set(ignored), self_login=self_login)

    def test_own_comment_without_marker_is_feedback(self):
        items = self.fetch([{'id': 1, 'user': 'Me', 'body': 'please rename this'}])
        self.assertEqual([i['key'] for i in items], ['review_comment:1'])

    def test_own_marked_reply_is_skipped_in_every_kind(self):
        reply = f'Fixed in abc123.\n\n_Written by an AI agent._\n{MARKER}'
        items = self.fetch([{'id': 1, 'user': 'me', 'body': reply}],
                           reviews=[{'id': 2, 'user': 'me', 'state': 'COMMENTED', 'body': reply}],
                           issue_comments=[{'id': 3, 'user': 'me', 'body': reply}])
        self.assertEqual(items, [])

    def test_marker_past_the_excerpt_still_counts(self):
        reply = 'x' * (api.EXCERPT * 2) + MARKER
        self.assertEqual(self.fetch([{'id': 1, 'user': 'me', 'body': reply}]), [])

    def test_marker_from_someone_else_is_still_feedback(self):
        items = self.fetch([{'id': 1, 'user': 'reviewer', 'body': f'quoting: {MARKER} still broken'}])
        self.assertEqual([i['key'] for i in items], ['review_comment:1'])

    def test_unknown_login_skips_nothing(self):
        items = self.fetch([{'id': 1, 'user': 'me', 'body': MARKER}], self_login='')
        self.assertEqual(len(items), 1)

    def test_ignore_self_restores_the_old_filter(self):
        argv = ['watch_pr.py', PR['url'], '--state', 'unused', '--ignore-self', '--max-wait', '0']
        seen = {}

        def snapshot(host, repo, number, ignored, **kwargs):
            seen.update(ignored=ignored, **kwargs)
            raise api.GhError('stop')

        for flags, expected in ((['--ignore-self'], {'me'}), ([], set())):
            seen.clear()
            with patch.object(sys, 'argv', argv[:4] + flags + argv[5:]), \
                    patch.object(api, 'snapshot', side_effect=snapshot), \
                    patch.object(api, 'load_state', return_value=None), self.assertRaises(api.GhError):
                api.main()
            self.assertEqual(seen, {'ignored': expected, 'self_login': 'me'})


if __name__ == '__main__':
    unittest.main()
