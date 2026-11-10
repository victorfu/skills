# watch-pr-feedback

## What it does

Watches one pull request and runs [address-review-feedback](address-review-feedback.md) each time new review comments or a failing CI check appear, until the PR goes quiet.

It runs unattended between rounds, and it always has a stop limit: by default 10 rounds or 4 hours, whichever comes first.

## When to reach for it

You invoke it by name with a PR URL. Reach for it when reviews arrive in several waves and you would otherwise invoke `address-review-feedback` again each time. For a single pass over the comments that are already there, use `address-review-feedback` directly.

Any limit you state (assess only, no push, no replies) applies to every round.

## Prerequisites

- A signed-in `gh` for the PR's host.
- Python 3 for the polling script. Without it the skill polls with `gh` directly.
- A local checkout or worktree on the PR's head branch, with no unrelated uncommitted work.

## The quiet window

The watch ends when nothing new has arrived for 10 minutes after the last push or handled comment, and no CI run is pending. A push restarts the window. You can change the poll interval, the quiet window and the round and time limits when you invoke it.

It ignores comments from your own GitHub account, because its replies are posted from that account and would otherwise trigger another round.

## Common questions

**Will it merge when everything is green?** No. It reports the final state and leaves the merge to you and the reviewers.

**The same check keeps failing.** It stops instead of looping when a check fails again after a fix aimed at it, or when the failure comes from infrastructure.

## It's working if

- Each new batch of comments leads to one round, not one round per comment.
- Its own replies do not start a new round.
- The final message says why the watch ended and lists, per round, what was fixed, rejected or left for you.

## Where it fits

The last step of the chain: [resolve-github-issue](resolve-github-issue.md) opens the PR, [address-review-feedback](address-review-feedback.md) handles one batch of feedback, and this skill repeats that until the PR is quiet.
