# A shared, model-invoked skill for the verdict rules

`resolve-github-issue` and `address-review-feedback` both carry the VALID / INVALID / ALREADY_FIXED / NEEDS_INFO table and the same evidence rules. They will not be extracted into a third skill that the other two call.

## Why this is out of scope

A skill can be called by another skill only when it is model-invoked, and a model-invoked skill can also start on its own. That conflicts with [implicit-invocation.md](implicit-invocation.md). The two tables also differ where it matters: one judges an issue, the other judges one review concern and holds its dependents.

When one skill needs another's workflow, it reads that skill's file directly, as `watch-pr-feedback` does with `address-review-feedback`.

## Prior requests

- 2026-11-10: raised while comparing this repo with mattpocock/skills, and set aside for the reason above.
