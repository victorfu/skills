---
description: Explicit read-only invocation with a bare issue number and no repo context. The skill must ask for the repo instead of guessing.
expected_outcome: A request for the full issue URL or OWNER/REPO, with no verdict and no GitHub or file changes.
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
---

/devflow:resolve-github-issue #123 Evaluate only; do not modify anything.
