---
description: Explicit read-only invocation with a pull request URL. The skill handles issues only and must not treat a PR as one.
expected_outcome: The reply says the URL is a pull request, not an issue, and stops without a verdict or any change.
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
---

/devflow:resolve-github-issue https://github.com/example-org/example-repo/pull/57 Evaluate only; do not modify anything.
