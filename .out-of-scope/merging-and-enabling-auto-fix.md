# Merging PRs and turning on auto-fix

The workflows stop at an open PR. They do not merge it, close the issue, or turn on PR auto-fix or any other monitoring by themselves.

## Why this is out of scope

Merging is the reviewers' and maintainers' decision, and a commit pushed by auto-fix does not pass through the skill's own testing and review. `resolve-github-issue` therefore ends by telling the user how to turn auto-fix on in their client, and leaves the choice to them.

Watching a PR is available as its own explicit step: `watch-pr-feedback`, which the user starts and which has stop limits.

## Prior requests

- None recorded.
