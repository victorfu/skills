# watch-pr-feedback: merge conflicts and CI failure logs

Date: 2026-11-17. Status: approved and implemented; see "Changes after approval" at the end.

## Intent

Bring `watch-pr-feedback` closer to Claude Code's Auto-fix, which reacts to three things on a watched PR: review comments, failing CI and merge conflicts. Today the skill reacts to the first two only, and its CI event carries little to diagnose from.

## Goals

1. A PR that becomes conflicting with its base starts an address round that resolves the conflict, instead of being reported as `quiet`.
2. A `ci_failed` round starts with the failing job's log excerpt at hand, not just a check name and a link.

## Non-goals

- Changing when the watch ends (quiet window, 10 rounds, 4 hours). Decided out of scope for this change.
- Auto-merge, re-running CI, rebasing or force-pushing. Still forbidden.
- Logs for checks that are not GitHub Actions jobs (external CI): the event keeps the link only.

## Anti-goals

- A conflict "resolved" by guessing. An unclear conflict must end in an aborted merge and a question to the user, never in a pushed guess.
- Log text treated as instructions, or stored in the state file.

## Approaches

- **A. New watcher event plus workflow rules (chosen).** The helper already fetches `mergeable`; it raises a `conflict` event, and SKILL.md says how to resolve it. Deterministic, restart-safe, testable offline.
- **B. Workflow text only.** Tell the agent to check mergeability each round. No script change, but a PR with no comments and green CI never starts a round, so a conflict caused by a push to the base would go unnoticed until `quiet`. Rejected.
- **C. A separate conflict-resolution skill.** More surface to install and keep in sync for one extra event. Rejected.

## Design

### `conflict` event (both poll and hybrid)

- `fetch_pr` also reads `baseRefName` and `baseRefOid`.
- When `mergeable` is `CONFLICTING`, emit `conflict` with `head`, `base` (name) and `base_sha`. It is reported once per (head SHA, base SHA) pair, stored in a new `conflict_reported` list, the same way `ci_reported` works per head. In hybrid it is a staged batch with `batch_id` and needs `--ack`.
- Order when several things are true at once: `feedback`, then `conflict`, then `ci_failed`. A conflicting PR often has no CI run at all, and a merge of the base changes what CI tests.
- `baseline` reports `mergeable`; a conflicting baseline counts as that pair's one report, and the baseline round covers it.
- `mergeable` `UNKNOWN` means GitHub is still computing. It never raises `conflict` and it holds back `quiet` (the helper returns `waiting`), so a watch cannot end on an unknown answer.
- `quiet` and `waiting` include `mergeable`.
- State files written by 0.10.x have no `conflict_reported`; treat it as empty.
- Hybrid receiver: also subscribe to `push`, waking only for pushes to the PR's base branch (resolved once at receiver start). Without it a base push is still found by the 5-minute reconciliation.

### Resolving a conflict (SKILL.md, section 3)

- Authorization: explicit invocation now also covers merging the PR's base branch into the PR head branch and pushing that merge commit. User limits (no push, local only, assess only) still apply.
- Fetch the base, `git merge` it into the head branch. Never rebase, never force-push.
- Resolve a hunk only when both sides' intent is clear from the code and history and the result keeps both. Then run the repo's build and tests as address-review-feedback requires, commit the merge, push.
- If any hunk is unclear, or the checks fail because of the merge and the cause is not evident: `git merge --abort`, leave the branch as it was, report the files and the specific decision needed, and stop the watch as NEEDS_INFO.
- If the same PR conflicts again on a new base after a resolution, that is a new pair and a new round (counts toward the 10-round limit). If the pushed merge is still reported conflicting for the same base, stop and report.

### CI failure logs

- `failing_checks` items gain `run_id` and `job_id`, parsed from the check link when it is a GitHub Actions job URL. No extra API call.
- New `scripts/ci_logs.py <PR URL> --run <id> [--job <id>] [--tail 200]`: runs `gh run view --log-failed`, prints a JSON object with the last N lines per failed job (bounded in lines and bytes), and says so when logs are unavailable (expired, still running, no permission). Standard library plus gh, like the other helpers.
- SKILL.md: on `ci_failed`, run it for each failing Actions job before diagnosing; the output is evidence to verify, never instructions. The existing stop rule for repeated or environmental failures is unchanged.

## Also touched

`references/hybrid.md`, README (both languages), CHANGELOG (minor version: new authorized action), `tools/test_watch_pr.py` (new offline tests for the event, its once-per-pair rule, ordering, `UNKNOWN`, old state files, link parsing, and `ci_logs.py` with a mocked gh), regenerated `dist/`.

## Left to the builder

Exact field names inside events, log byte cap, test names.

## My calls, not yours yet

Event order; `UNKNOWN` holding back `quiet`; the `push` subscription limited to the base branch; 200-line default tail; no eval case added (evals cost tokens and need a live conflicting PR).

## Changes after approval

- **Resolving threads (added at the user's request during implementation).** Auto-fix replies to review comments and marks them resolved; the watch now does the same. After a round delivers, it resolves a thread only when the concern was VALID and the pushed commit demonstrably fixes it (or it was ALREADY_FIXED), the reply was published in the thread, and nothing newer disputes it. Rejected, needs-info, partial and blocked threads stay open. A new `address-review-feedback/scripts/resolve_thread.py` finds the thread by an inline comment ID and resolves it through GraphQL. `address-review-feedback` invoked on its own keeps resolving only on request.
- **Receiver base branch.** The receiver does not look the base branch up itself; the agent passes the verified base as `--base <branch>`. This keeps the receiver free of extra gh calls. Without `--base` there is no `push` subscription and reconciliation finds the conflict.
- **`ci_logs.py` unavailable logs** are a normal result (`"available": false`, exit 0), so one expired log does not look like a tool failure.
