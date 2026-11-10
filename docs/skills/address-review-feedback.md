# address-review-feedback

## What it does

Works through the review comments and failing CI checks on an existing pull request: it checks each one against the current code, fixes the ones that hold, pushes to the same PR and replies to the reviewers.

It verifies each comment before acting on it. A reviewer being senior, a bot being confident or you agreeing does not make a comment correct; a comment that does not hold gets a reply with the evidence instead of a change.

## When to reach for it

You invoke it by name; a review notification or a pasted PR URL on its own starts nothing.

| Your situation | What to say after the invocation |
| --- | --- |
| Handle everything and update the PR | The PR URL |
| You want to see the assessment first | The PR URL, plus "assess only; do not modify or post anything" |
| Fix locally, you will push yourself | "Apply justified fixes locally. Do not commit, push or post replies." |
| The feedback is not on GitHub | Paste the feedback text |
| You want it to keep handling new comments | Use [watch-pr-feedback](watch-pr-feedback.md) |

## Prerequisites

- GitHub access: a signed-in `gh`, or a GitHub connector in your client.
- Push access to the PR's branch, unless you limit it to assessing or local fixes.

## One verdict per comment

Each concern gets its own verdict: `VALID` (fixed), `INVALID` (answered with counter-evidence), `ALREADY_FIXED` (answered with the fixing change) or `NEEDS_INFO` (waits for you). A comment that needs your decision holds only itself and the changes that depend on it; the rest of the batch continues.

It also checks merge conflicts and the build on every run, whether or not a reviewer mentioned them.

## Common questions

**Will it resolve the review threads?** Only when you ask. By default it replies and leaves each thread open for the reviewer.

**Will it re-run or skip a failing CI check?** No. A failure caused by the code is fixed; one caused by infrastructure or missing secrets is reported.

## It's working if

- Every review comment ends up in one of four groups in the final message: fixed, rejected, already fixed or blocked.
- A rejected comment comes with concrete evidence, not a restatement of the code.
- Replies appear in the original review threads, after the fix they describe was pushed.
- The final message states merge-conflict status and CI status for the pushed commit, or says why either is unknown.

## Where it fits

The middle of the chain. [resolve-github-issue](resolve-github-issue.md) opens a PR, this skill answers its reviews, and [watch-pr-feedback](watch-pr-feedback.md) runs this skill again each time new feedback arrives.
