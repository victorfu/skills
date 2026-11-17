#!/usr/bin/env python3
"""Mark the review thread that holds a given review comment as resolved, with authenticated gh.

  resolve_thread.py <PR URL> --comment <review comment ID>

Finds the thread by the numeric ID of any inline review comment in it, then
resolves it. A thread that is already resolved is left alone. PR conversation
comments and review summaries are not threads and cannot be resolved.

Prints {"thread_id", "resolved": true, "already_resolved": bool} as JSON; exit 1 on errors.
Uses only the Python standard library; runs on Windows, macOS and Linux.
"""
import argparse
import json
import re
import subprocess
import sys

PR_URL = re.compile(r'https://([^/\s]+)/([^/\s]+)/([^/\s]+)/pull/(\d+)/?(?:[?#].*)?$')

THREADS = '''
query($owner: String!, $repo: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      reviewThreads(first: 50, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { id isResolved comments(first: 100) { nodes { databaseId } } }
      }
    }
  }
}'''
RESOLVE = '''
mutation($thread: ID!) {
  resolveReviewThread(input: {threadId: $thread}) { thread { id isResolved } }
}'''


def graphql(host, query, **variables):
    command = ['gh', 'api', 'graphql', '--hostname', host, '-f', f'query={query}']
    for name, value in variables.items():
        if value is None:
            continue
        # -F sends numbers as numbers; -f keeps strings such as cursors verbatim.
        command += ['-F' if isinstance(value, int) else '-f', f'{name}={value}']
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode != 0:
        raise RuntimeError(f'gh api graphql failed ({result.returncode}): '
                           f'{(result.stderr.strip() or result.stdout.strip())[:500]}')
    return json.loads(result.stdout)['data']


def find_thread(host, owner, repo, number, comment_id):
    cursor = None
    while True:
        data = graphql(host, THREADS, owner=owner, repo=repo, number=number, cursor=cursor)
        pull = (data.get('repository') or {}).get('pullRequest')
        if not pull:
            raise ValueError('Pull request not found')
        threads = pull['reviewThreads']
        for thread in threads['nodes']:
            if any(comment.get('databaseId') == comment_id for comment in thread['comments']['nodes']):
                return thread
        if not threads['pageInfo']['hasNextPage']:
            raise ValueError(f'No review thread on this PR holds review comment {comment_id}')
        cursor = threads['pageInfo']['endCursor']


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('pr', help='PR URL')
    parser.add_argument('--comment', type=int, required=True, help='ID of an inline review comment in the thread')
    args = parser.parse_args()
    match = PR_URL.match(args.pr)
    if not match:
        raise ValueError('Pass a PR URL such as https://github.com/OWNER/REPO/pull/123')
    host, owner, repo, number = match.groups()
    thread = find_thread(host, owner, repo, int(number), args.comment)
    already = bool(thread['isResolved'])
    if not already:
        resolved = graphql(host, RESOLVE, thread=thread['id'])['resolveReviewThread']['thread']
        if not resolved['isResolved']:
            raise RuntimeError('GitHub did not mark the thread as resolved')
    print(json.dumps({'thread_id': thread['id'], 'resolved': True, 'already_resolved': already}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, RuntimeError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f'resolve_thread: {type(error).__name__}: {error}', file=sys.stderr)
        sys.exit(1)
