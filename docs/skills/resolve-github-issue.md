# resolve-github-issue

## What it does

Takes one GitHub issue from report to an open pull request: it checks that the problem is real, fixes it on its own branch, tests it, has the fix reviewed and opens the PR.

It verifies before it fixes. An issue that turns out to be untrue, already fixed or missing information ends with a report and no code change.

## When to reach for it

You invoke it by name; pasting an issue URL on its own starts nothing.

```text
/devflow:resolve-github-issue https://github.com/OWNER/REPO/issues/123     # Claude Code
$devflow:resolve-github-issue https://github.com/OWNER/REPO/issues/123     # Codex
```

| Your situation | What to do |
| --- | --- |
| You want the issue fixed and a PR opened | Invoke it with the issue URL or `OWNER/REPO#123` |
| You only want to know whether the issue is real | Invoke it and add "assess only, don't change anything" |
| The PR already exists and has review comments | Use [address-review-feedback](address-review-feedback.md) |

## Prerequisites

- GitHub access: a signed-in `gh`, or a GitHub connector in your client.
- Push access to the repo, or your own fork of it.
- Permission to label issues is optional. Without it the skill skips the label and says so.

## The verdict

Every run ends its investigation with exactly one verdict, and only one of them leads to code:

| Verdict | Meaning | What happens |
| --- | --- | --- |
| `VALID` | The problem exists in the current version | Fix, test, review, PR |
| `INVALID` | The report is untrue, or the behavior is as designed | Report with counter-evidence |
| `ALREADY_FIXED` | The current version no longer has it | Report with the fixing commit |
| `NEEDS_INFO` | A fact or decision is missing | Report what is missing |

## Common questions

**Will it merge the PR or close the issue?** No. It stops at an open, ready-for-review PR. Merging, closing and commenting on the issue stay with you.

**A different version of the skill ran.** A standalone skill with the same name is installed. Use the plugin-qualified name shown above.

## It's working if

- The first thing you see is evidence about the issue, not a code change.
- The issue carries an `in progress` label while the work runs, and loses it again if no PR results.
- Your own uncommitted work is untouched; the fix sits on a `fix/issue-<number>-…` branch in a separate worktree.
- The PR body shows the same check failing before and passing after.
- The final message lists what was not verified, when anything was not.

## Where it fits

The first step of the chain: `resolve-github-issue` opens the PR, then [address-review-feedback](address-review-feedback.md) handles what reviewers and CI say about it, once or repeatedly through [watch-pr-feedback](watch-pr-feedback.md).
