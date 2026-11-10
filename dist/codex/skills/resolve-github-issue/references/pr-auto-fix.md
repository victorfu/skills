# PR auto-fix pointers

Read this after opening a PR, to tell the user how to turn on auto-fix. Match the user's current client; when it cannot be determined, list them all. Add that commits pushed by auto-fix do not pass through this workflow's testing and review.

- Claude Code desktop: Auto-fix in the ⋮ menu next to the PR.
- Claude Code web/mobile: the PR's Auto-fix toggle, or ask Claude to watch the PR.
- Claude Code CLI: run `/autofix-pr`; it creates a cloud session and requires the Claude GitHub App to be installed on the repo.
- Codex: choose Fix under the PR's Checks, submitting manually each time; or comment `@codex fix the CI failures` on the PR on GitHub, which requires the repo to be connected to Codex.
