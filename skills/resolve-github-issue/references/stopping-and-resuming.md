# Stopping and resuming

Read this when the run ends without opening its own PR, when an operation's result is uncertain, or when picking up interrupted work.

## The in progress label

- After a PR is opened, the label stays, meaning the fix awaits merge. GitHub Projects fields stay as they are, no background monitoring is set up, and nothing promises the label will clear after merge.
- When the verdict is INVALID, ALREADY_FIXED or NEEDS_INFO, when another PR already covers the issue, or when a blocker stops the run before its PR, remove the label this run added. If work can resume immediately, keep it until you stop or open the PR.
- A label that was already on the issue stays. When the task record is lost, investigate who added it; if that cannot be confirmed, keep it and report.
- Removal applies to this issue's label only. The repo's shared label definition stays, even when this run created it.

## Uncertain results

- Re-read the state before retrying an operation whose result is unknown.
- On missing permissions or a state conflict, report the actual state and the unfinished steps. Keep the worktree, commits, PR and any other recovery information in place.

## Resuming

Reconcile labels, branches, commits and PRs against the task record first, then continue from the last completed stage. Existing side effects are reused, never created a second time.
