# GitHub operations reference

Read this before the first remote operation on a PR. With a connector that offers the same operation, use the connector; the rules still apply.

## Mergeability and build health

- Check mergeability against the latest base, and build/CI results for the current head SHA. Record the base and head revisions that were checked.
- With a checkout available, also inspect local unmerged paths and conflict markers.
- When remote mergeability is unknown, run a non-mutating merge check or use an isolated worktree with current refs. If neither is possible, report mergeability as unknown; unknown is not conflict-free.
- Find the repo's documented build commands and required CI jobs. Separate failures that existed before from regressions the fixes introduced.
- Results from an older head SHA say nothing about the delivered one. Local checks say nothing about remote CI or approval to merge.

## Failing CI checks

- Read the failing check's logs and record the failing step and error as the claim.
- A failure from infrastructure, missing secrets or flakiness outside the repo's code is recorded and reported as such. Re-running, skipping or disabling a check needs the user's request.
- A CI concern has no review thread. Report it in the final reply; post a PR comment only where a reviewer asked about it in a thread.

## Replies

- An inline comment is answered in its original review thread; a top-level comment in the PR conversation.
- With gh, an inline reply is `POST repos/{owner}/{repo}/pulls/{pr}/comments/{comment_id}/replies`, using the verified root review-comment ID. An issue-comment ID or a GraphQL thread ID is the wrong identifier.
- Pass multiline text as structured body arguments or a UTF-8 body file.
- After an uncertain result, re-read before retrying, so a reply or push is published once. Before retrying a push, look for an equivalent commit on the remote.
- Re-read to confirm each remote action. On a missing permission, report it; accounts and credentials stay as the user set them.
