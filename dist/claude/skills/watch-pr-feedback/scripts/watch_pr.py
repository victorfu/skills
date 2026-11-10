#!/usr/bin/env python3
"""Wait for new review feedback or CI results on a GitHub pull request.

Polls with the authenticated gh CLI and prints exactly one JSON event, then exits:

  baseline  First run for this state file: existing feedback was recorded as seen.
  feedback  New review comments, reviews or PR conversation comments appeared.
  ci_failed CI finished on the current head SHA with failing checks (reported once per SHA).
  quiet     No new feedback for --quiet seconds since the last head change or event,
            and no CI check on the current head is pending or failing.
  closed    The PR is no longer open.
  waiting   --max-wait elapsed first; run again with the same state file to continue.

Exit status is 0 for every event and 1 for errors (message on stderr).
Uses only the Python standard library; runs on Windows, macOS and Linux.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

PR_URL = re.compile(r'https://([^/\s]+)/([^/\s]+)/([^/\s]+)/pull/(\d+)/?(?:[?#].*)?$')
EXCERPT = 300


class GhError(Exception):
    pass


def gh(*args, ok_codes=(0,)):
    result = subprocess.run(['gh', *args], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode not in ok_codes:
        raise GhError(f"gh {' '.join(args[:3])} failed ({result.returncode}): {result.stderr.strip()[:500]}")
    return result.stdout


def gh_lines(path, jq, host):
    out = gh('api', '--hostname', host, '--paginate', path, '--jq', jq)
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def excerpt(text):
    text = (text or '').strip()
    return text if len(text) <= EXCERPT else text[:EXCERPT] + '…'


def parse_target(args):
    match = PR_URL.match(args.pr)
    if match:
        host, owner, repo, number = match.groups()
        return host, f'{owner}/{repo}', int(number)
    if not args.repo or not re.fullmatch(r'#?\d+', args.pr):
        raise ValueError('Pass a PR URL, or a PR number together with --repo OWNER/REPO')
    return args.host, args.repo, int(args.pr.lstrip('#'))


def fetch_feedback(host, repo, number, ignored):
    items = []
    base = f'repos/{repo}'
    for c in gh_lines(f'{base}/pulls/{number}/comments?per_page=100',
                      '.[] | {id, user: .user.login, created_at, path, line, in_reply_to_id, html_url, body}', host):
        items.append({'key': f"review_comment:{c['id']}", 'kind': 'review_comment', **c})
    for r in gh_lines(f'{base}/pulls/{number}/reviews?per_page=100',
                      '.[] | {id, user: .user.login, state, submitted_at, html_url, body}', host):
        # Inline comments are tracked individually; a review counts when it carries its own text or verdict.
        if (r.get('body') or '').strip() or r.get('state') == 'CHANGES_REQUESTED':
            items.append({'key': f"review:{r['id']}", 'kind': 'review', **r})
    for c in gh_lines(f'{base}/issues/{number}/comments?per_page=100',
                      '.[] | {id, user: .user.login, created_at, html_url, body}', host):
        items.append({'key': f"issue_comment:{c['id']}", 'kind': 'issue_comment', **c})
    kept = []
    for item in items:
        if (item.get('user') or '').lower() in ignored:
            continue
        item['body'] = excerpt(item.get('body'))
        kept.append(item)
    return kept


def fetch_pr(host, repo, number):
    out = gh('pr', 'view', str(number), '--repo', f'{host}/{repo}', '--json', 'state,headRefOid,url,mergeable')
    return json.loads(out)


def fetch_checks(host, repo, number):
    # gh exits 8 while checks are pending and 1 when some fail; both still print JSON.
    try:
        out = gh('pr', 'checks', str(number), '--repo', f'{host}/{repo}',
                 '--json', 'name,state,bucket,link,workflow', ok_codes=(0, 1, 8))
    except GhError as error:
        if 'no checks reported' in str(error).lower():
            return []
        raise
    try:
        return json.loads(out) if out.strip() else []
    except json.JSONDecodeError:
        if 'no checks reported' in out.lower():
            return []
        raise GhError(f'Unexpected gh pr checks output: {out[:300]}')


def summarize_checks(checks):
    buckets = {}
    for check in checks:
        buckets.setdefault(check.get('bucket') or 'unknown', []).append(check)
    failing = buckets.get('fail', []) + buckets.get('cancel', [])
    status = 'none' if not checks else 'pending' if buckets.get('pending') else 'failing' if failing else 'passing'
    return status, failing, buckets


def load_state(path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.watch-pr-', suffix='.json')
    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
        json.dump(state, handle, indent=2)
    os.replace(tmp, path)


def emit(event, **fields):
    print(json.dumps({'event': event, **fields}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('pr', help='PR URL, or PR number with --repo')
    parser.add_argument('--repo', help='OWNER/REPO when pr is a number')
    parser.add_argument('--host', default='github.com', help='GitHub host when pr is a number')
    parser.add_argument('--state', required=True, help='JSON state file kept between runs')
    parser.add_argument('--interval', type=int, default=60, help='seconds between polls (default 60)')
    parser.add_argument('--quiet', type=int, default=600, help='quiet seconds required to finish (default 600)')
    parser.add_argument('--settle', type=int, default=60, help='seconds to keep collecting after new feedback (default 60)')
    parser.add_argument('--max-wait', type=int, default=540, help='seconds before this run returns "waiting" (default 540)')
    parser.add_argument('--ignore-author', action='append', default=[], help='login whose comments are ignored; repeatable')
    parser.add_argument('--include-self', action='store_true', help='do not ignore comments by the authenticated gh user')
    args = parser.parse_args()
    for name in ('interval', 'quiet', 'settle', 'max_wait'):
        if getattr(args, name) < (1 if name == 'interval' else 0):
            raise ValueError(f'--{name.replace("_", "-")} is out of range')

    host, repo, number = parse_target(args)
    state_path = Path(args.state)
    state = load_state(state_path)
    ignored = {login.lower() for login in args.ignore_author}
    if not args.include_self:
        ignored.add(gh('api', '--hostname', host, 'user', '--jq', '.login').strip().lower())
    target = {'host': host, 'repo': repo, 'pr': number}

    pr = fetch_pr(host, repo, number)
    feedback = fetch_feedback(host, repo, number, ignored)
    now = time.time()
    if state is None or state.get('target') != target:
        status, failing, _ = summarize_checks(fetch_checks(host, repo, number))
        save_state(state_path, {'target': target, 'seen': sorted(i['key'] for i in feedback),
                                'head': pr['headRefOid'], 'quiet_since': now, 'ci_reported': []})
        emit('baseline', url=pr['url'], pr_state=pr['state'], head=pr['headRefOid'], mergeable=pr.get('mergeable'),
             existing_feedback=len(feedback), ci=status, failing_checks=failing, ignored_authors=sorted(ignored))
        return

    started = now
    pending_new = None
    last_new_at = None
    while True:
        if pr['state'] != 'OPEN':
            emit('closed', url=pr['url'], pr_state=pr['state'], head=pr['headRefOid'])
            return
        if pr['headRefOid'] != state['head']:
            # A push (ours or someone else's) restarts the quiet window and resets per-SHA CI reporting.
            state['head'] = pr['headRefOid']
            state['quiet_since'] = now
            save_state(state_path, state)

        seen = set(state['seen'])
        fresh = [i for i in feedback if i['key'] not in seen]
        if fresh:
            if pending_new is None or len(fresh) > len(pending_new):
                last_new_at = now
            pending_new = fresh
            if now - last_new_at >= args.settle:
                state['seen'] = sorted(seen | {i['key'] for i in fresh})
                state['quiet_since'] = now
                save_state(state_path, state)
                emit('feedback', url=pr['url'], head=pr['headRefOid'], items=fresh)
                return

        checks = fetch_checks(host, repo, number)
        status, failing, buckets = summarize_checks(checks)
        if not fresh and status == 'failing' and state['head'] not in state['ci_reported']:
            state['ci_reported'].append(state['head'])
            state['quiet_since'] = now
            save_state(state_path, state)
            emit('ci_failed', url=pr['url'], head=pr['headRefOid'], failing_checks=failing)
            return
        if not fresh and status != 'pending' and now - state['quiet_since'] >= args.quiet:
            emit('quiet', url=pr['url'], head=pr['headRefOid'], ci=status, failing_checks=failing,
                 quiet_seconds=int(now - state['quiet_since']))
            return
        if now - started >= args.max_wait:
            emit('waiting', url=pr['url'], head=pr['headRefOid'], ci=status,
                 pending_checks=[c['name'] for c in buckets.get('pending', [])],
                 quiet_seconds=int(now - state['quiet_since']), unsettled_feedback=len(fresh))
            return

        time.sleep(args.interval)
        now = time.time()
        pr = fetch_pr(host, repo, number)
        feedback = fetch_feedback(host, repo, number, ignored)


if __name__ == '__main__':
    try:
        main()
    except (GhError, ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        print(f'watch_pr: {type(error).__name__}: {error}', file=sys.stderr)
        sys.exit(1)
