#!/usr/bin/env python3
"""Publish one reply on a GitHub pull request with authenticated gh.

The body is read as UTF-8 from --body-file (or stdin with "-"). The script
appends the agent-reply marker, an HTML comment GitHub does not render, so
watch-pr-feedback can tell this workflow's own replies from the user's
comments posted with the same account.

  --reply-to ID  reply in the thread of review comment ID (inline comment)
  (omitted)      post a top-level comment in the PR conversation

Prints {"id", "html_url"} of the created comment as JSON; exit 1 on errors.
Uses only the Python standard library; runs on Windows, macOS and Linux.
"""
import argparse
import json
import re
import subprocess
import sys

# Keep identical to AGENT_MARKER in watch-pr-feedback/scripts/watch_pr.py.
AGENT_MARKER = '<!-- devflow:agent-reply -->'
PR_URL = re.compile(r'https://([^/\s]+)/([^/\s]+)/([^/\s]+)/pull/(\d+)/?(?:[?#].*)?$')


def with_marker(body):
    body = body.rstrip()
    if not body:
        raise ValueError('Reply body is empty')
    return body if body.endswith(AGENT_MARKER) else f'{body}\n\n{AGENT_MARKER}'


def endpoint(repo, number, reply_to):
    if reply_to is None:
        return f'repos/{repo}/issues/{number}/comments'
    return f'repos/{repo}/pulls/{number}/comments/{reply_to}/replies'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('pr', help='PR URL')
    parser.add_argument('--body-file', required=True, help='UTF-8 file holding the reply, or - for stdin')
    parser.add_argument('--reply-to', type=int, help='root review comment ID for an inline thread reply')
    args = parser.parse_args()
    match = PR_URL.match(args.pr)
    if not match:
        raise ValueError('Pass a PR URL such as https://github.com/OWNER/REPO/pull/123')
    host, owner, repo, number = match.groups()
    if args.body_file == '-':
        body = sys.stdin.buffer.read().decode('utf-8')
    else:
        with open(args.body_file, encoding='utf-8') as handle:
            body = handle.read()
    payload = json.dumps({'body': with_marker(body)}, ensure_ascii=False).encode('utf-8')
    result = subprocess.run(
        ['gh', 'api', '--hostname', host, '--method', 'POST', endpoint(f'{owner}/{repo}', number, args.reply_to),
         '--input', '-', '--jq', '{id, html_url}'],
        input=payload, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"gh api failed ({result.returncode}): "
                           f"{result.stderr.decode('utf-8', 'replace').strip()[:500]}")
    sys.stdout.write(result.stdout.decode('utf-8', 'replace'))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, RuntimeError, UnicodeDecodeError) as error:
        print(f'post_reply: {type(error).__name__}: {error}', file=sys.stderr)
        sys.exit(1)
