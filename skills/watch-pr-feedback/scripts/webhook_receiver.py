#!/usr/bin/env python3
"""Local development receiver for gh webhook forward; stores wakeups, not work."""
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

from watch_pr import save_state, parse_target

EVENTS = 'pull_request,pull_request_review,pull_request_review_comment,issue_comment,check_run,check_suite,status,workflow_run'


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
        data = {'target': target, 'generation': secrets.token_hex(16), 'active': False}
        def write():
            data['heartbeat'] = time.time()
            save_state(path, data)
        def wake():
            data['generation'] = secrets.token_hex(16)
            write()
        route = '/' + secrets.token_hex(24)
        server = HTTPServer(('127.0.0.1', 0), make_handler(target, route, wake))
        server.timeout = 1
        process = None
        write()
        try:
            env = dict(os.environ, GH_HOST=host)
            process = subprocess.Popen([
                'gh', 'webhook', 'forward', '--repo=' + repo, '--events=' + EVENTS,
                '--url=http://127.0.0.1:' + str(server.server_port) + route],
                env=env, stdout=subprocess.DEVNULL)
            data['active'] = True
            write()
            deadline = time.monotonic() + args.lifetime
            while process.poll() is None and time.monotonic() < deadline:
                server.handle_request()
                if time.time() - data['heartbeat'] >= 5:
                    write()
                # Consumer requests shutdown when the watch ends.
                if path.with_suffix(path.suffix + '.stop').exists():
                    break
        finally:
            data['active'] = False
            write()
            server.server_close()
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == '__main__':
    main()
