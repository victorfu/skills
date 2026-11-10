#!/usr/bin/env python3
"""Local development receiver for gh webhook forward; stores wakeups, not work."""
import argparse
import http.server
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import secrets
import socketserver
import subprocess
import sys
import time

from watch_pr import save_state, parse_target

EVENTS = 'pull_request,pull_request_review,pull_request_review_comment,issue_comment,check_run,check_suite,status,workflow_run'


class HTTPServer(http.server.HTTPServer):
    def server_bind(self):
        # The stock server resolves its own host name while binding, which can
        # take several seconds on macOS; a loopback receiver has no use for it.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def log_tail(path):
    try:
        text = path.read_text(encoding='utf-8', errors='replace').strip()
    except OSError:
        text = ''
    return text[-500:] or 'no error output'


def relevant(event, payload, repo, number):
    if payload.get('repository', {}).get('full_name', '').lower() != repo.lower():
        return False
    if event == 'issue_comment':
        issue = payload.get('issue', {})
        return issue.get('number') == number and 'pull_request' in issue
    if event in ('pull_request', 'pull_request_review', 'pull_request_review_comment'):
        return payload.get('pull_request', {}).get('number') == number
    # CI payloads can omit PR associations (especially forks). Wake conservatively;
    # the consumer always reads checks for the current PR head, never this payload.
    return event in ('check_run', 'check_suite', 'status', 'workflow_run')


def make_handler(target, route, wake):
    deliveries = set()
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def do_POST(self):
            if self.path != route:
                self.send_error(404)
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 2 * 1024 * 1024:
                    self.send_error(413)
                    return
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError('Expected object')
                if relevant(self.headers.get('X-GitHub-Event'), payload,
                            target['repo'], target['pr']):
                    delivery = self.headers.get('X-GitHub-Delivery')
                    if not delivery or delivery not in deliveries:
                        wake()
                        if len(deliveries) >= 1024:
                            deliveries.clear()
                        if delivery:
                            deliveries.add(delivery)
            except (ValueError, TypeError, AttributeError):
                self.send_error(400)
                return
            self.send_response(202)
            self.end_headers()

        def log_message(self, *args):
            pass
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pr')
    parser.add_argument('--repo')
    parser.add_argument('--host', default='github.com')
    parser.add_argument('--signal', required=True)
    parser.add_argument('--lifetime', type=int, default=14400)
    args = parser.parse_args()
    if args.lifetime < 1:
        parser.error('--lifetime must be positive')
    host, repo, number = parse_target(args)
    target = {'host': host, 'repo': repo, 'pr': number}
    path = Path(args.signal)
    path.parent.mkdir(parents=True, exist_ok=True)
    # OS lock is released on crash; do not overwrite another receiver's heartbeat.
    from watch_pr import state_lock
    with state_lock(path):
        path.with_suffix(path.suffix + '.stop').unlink(missing_ok=True)
        data = {'target': target, 'generation': secrets.token_hex(16), 'active': False, 'heartbeat': 0}
        def write():
            # A failed write must not end the receiver; the next tick retries it.
            stamp = time.time()
            try:
                save_state(path, dict(data, heartbeat=stamp))
            except OSError as error:
                print(f'webhook_receiver: signal write failed: {error}', file=sys.stderr)
                return
            data['heartbeat'] = stamp
        def wake():
            data['generation'] = secrets.token_hex(16)
            write()
        route = '/' + secrets.token_hex(24)
        server = HTTPServer(('127.0.0.1', 0), make_handler(target, route, wake))
        server.timeout = 1
        process = None
        failure = None
        log_path = path.with_suffix(path.suffix + '.log')
        write()
        try:
            env = dict(os.environ, GH_HOST=host)
            try:
                # The forwarder's stderr is the only place gh explains a refusal; keep it.
                with log_path.open('wb') as log:
                    process = subprocess.Popen([
                        'gh', 'webhook', 'forward', '--repo=' + repo, '--events=' + EVENTS,
                        '--url=http://127.0.0.1:' + str(server.server_port) + route],
                        env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log)
            except OSError as error:
                failure = f'could not start gh webhook forward: {error}'
            else:
                data['active'] = True
                write()
                deadline = time.monotonic() + args.lifetime
                while True:
                    code = process.poll()
                    if code is not None:
                        failure = f'gh webhook forward exited ({code}): {log_tail(log_path)}'
                        break
                    if time.monotonic() >= deadline:
                        data['reason'] = 'receiver lifetime limit reached'
                        break
                    server.handle_request()
                    if time.time() - data['heartbeat'] >= 5:
                        write()
                    # Consumer requests shutdown when the watch ends.
                    if path.with_suffix(path.suffix + '.stop').exists():
                        data['reason'] = 'receiver stopped on request'
                        break
        finally:
            # Stop the forwarder first: it holds the repository's only forwarding
            # slot, so no later cleanup step may be able to skip this one.
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            server.server_close()
            data['active'] = False
            if failure:
                data['reason'] = failure
            write()
    if failure:
        # A dead forwarder must not look like a requested stop to the caller.
        print(f'webhook_receiver: {failure}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        print(f'webhook_receiver: {type(error).__name__}: {error}', file=sys.stderr)
        sys.exit(1)
