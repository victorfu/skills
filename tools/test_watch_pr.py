"""Offline regression tests: no GitHub credentials, pushes or live webhooks."""
import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
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


def state():
    return {'mode': 'hybrid', 'target': TARGET, 'head': 'abc', 'seen_versions': {},
            'ci_reported': [], 'quiet_since': 0, 'settling': {}}


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
        hybrid.acknowledge(value, event['batch_id'], 1)
        event2 = hybrid.evaluate(value, PR, [changed], [], 2, 600, 0)
        self.assertEqual(event2['event'], 'feedback')
        self.assertNotEqual(event['batch_id'], event2['batch_id'])

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
                patch.object(api, 'fetch_feedback', return_value=[]), \
                patch.object(api, 'fetch_checks', side_effect=[FAIL, []]):
            pr, _, checks = hybrid.snapshot('github.com', 'o/r', 1, set())
        self.assertEqual(pr['headRefOid'], 'def')
        self.assertEqual(checks, [])
        self.assertEqual(api.EXCERPT, 300)

    def test_signal_health_and_target(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'signal.json'
            self.assertEqual(hybrid.signal_status(path, TARGET, 10), (None, False))
            api.save_state(path, dict(target=TARGET, active=True, heartbeat=10, generation='a'))
            self.assertEqual(hybrid.signal_status(path, TARGET, 11), ('a', True))
            self.assertEqual(hybrid.signal_status(path, TARGET, 26), (None, False))
            self.assertEqual(hybrid.signal_status(path, dict(TARGET, pr=2), 11), (None, False))

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
                    ack=None, include_self=True, ignore_author=[], interval=60, quiet=quiet,
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
                ack=None, include_self=True, ignore_author=[], interval=60, quiet=600,
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
                ack=None, include_self=True, ignore_author=[], interval=60, quiet=600,
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


if __name__ == '__main__':
    unittest.main()
