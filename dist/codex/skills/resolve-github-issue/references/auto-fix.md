# Turning on PR auto-fix

Read this after opening a PR. Tell the user how to turn auto-fix on in their client; do not turn it on yourself.

- Claude Code desktop: Auto-fix in the ⋮ menu next to the PR.
- Claude Code web/mobile: the PR's Auto-fix toggle, or ask Claude to watch the PR.
- Claude Code CLI: run `/autofix-pr`; it creates a cloud session and requires the Claude GitHub App to be installed on the repo.
- Codex: choose Fix under the PR's Checks, submitting manually each time; or comment `@codex fix the CI failures` on the PR on GitHub, which requires the repo to be connected to Codex.
