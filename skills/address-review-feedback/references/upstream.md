# Upstream provenance

This workflow is adapted from Jesse Vincent's Superpowers skill:

- Repository: https://github.com/obra/superpowers
- Source: https://github.com/obra/superpowers/blob/3fb75974186ea7fada621d8ab77b3b02169baf57/skills/receiving-code-review/SKILL.md
- Source revision: `3fb75974186ea7fada621d8ab77b3b02169baf57`
- License: MIT, Copyright (c) 2025 Jesse Vincent. The full notice is in [LICENSE](../LICENSE).

## Integration choices

- Publish the adapted skill as `address-review-feedback`; the pinned upstream skill remains named `receiving-code-review`.

- Retain verification before implementation, evidence-based technical pushback, compatibility checks, minimal scope, testing and replies in the original review thread.
- Follow this repo's explicit-invocation contract and share the same workflow body across Claude Code and Codex.
- Replace the upstream rule that any unclear item stops all work with dependency-aware handling: hold the uncertain item and its dependents while completing independent authorized work.
- Separate the validity of a concern from the correctness of its proposed fix; distinguish invalid feedback, already-fixed feedback and missing evidence.
- Require evidence before deleting apparently unused public or dynamic entry points.
- Default explicit invocation to verification, justified fixes, conflict/build checks, PR delivery and published review replies; honor explicit scope limits and require a separate request for thread resolution.
- Keep replies factual without copying the upstream's blanket ban on gratitude or its references to an unspecified human partner's personal rules.

This is an adapted workflow, not a verbatim upstream copy or a dependency on installing the rest of Superpowers. Compare later upstream changes against the pinned revision and retain the local scope and authorization contract.
