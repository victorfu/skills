# Changelog

Behavior changes to the skills and the plugin package, newest first. These skills commit, push and post on your behalf, so read the entries between your installed version and the new one before updating. Docs-only and CI-only changes are left out.

## Unreleased

- `resolve-github-issue` uses a repo's existing work-in-progress label (such as `wip` or `status: in progress`) as the progress label instead of creating a new `in progress` label.
- `resolve-github-issue` and `address-review-feedback` redact secrets, tokens and credentials from command output and CI logs quoted in PR bodies and review replies.
- The build now rejects a skill that points to a missing sibling skill file or to a numbered section that does not exist, and no longer lints text inside fenced code blocks.

## 0.6.0 (2026-11-10)

- Added `watch-pr-feedback`: polls a PR with `gh` and runs `address-review-feedback` for each new batch of review comments or failing CI until the PR goes quiet, closes or reaches a round or time limit.
- `address-review-feedback` treats each failing CI check on the PR head as a concern of its own, even when there are no review comments.
- Python bytecode caches are no longer packaged.

## 0.5.1 (2026-11-06)

- **Default changed:** invoking `address-review-feedback` now runs the complete workflow (verify, fix, commit, push to the existing PR and publish replies to review comments). It previously defaulted to assessment only. Limits such as assessment-only, local-only, no push or no replies still override the default.
- `address-review-feedback` checks merge conflicts and build/CI status for the current head even when no comment mentions them, and reports both in the final reply.

## 0.5.0 (2026-11-06)

- **Plugin renamed** to `devflow` ("DevFlow"). `plugin update` does not follow the rename; see "Migrating from `dev-workflow-kit`" in the README. Invocations change from `/dev-workflow-kit:…` to `/devflow:…`.

## 0.3.0 and 0.4.0 (2026-11-06)

- Plugin ID changed to `dev-workflow-kit`, first on Claude Code (0.3.0), then on Codex (0.4.0).

## 0.2.1 (2026-11-05)

- Added `address-review-feedback` (first added as `receiving-code-review`, renamed in this release).

## 0.1.6 (2026-10-27)

- `resolve-github-issue` records an impact analysis (who is affected, what changes, how it is checked) before editing and compares the final diff against it during review.

## 0.1.1 to 0.1.5 (2026-10-26)

- `resolve-github-issue` was translated to English, tells you how to enable PR auto-fix after opening a PR, and uses one plugin-qualified invocation name on Codex.
- Added plugin icons, brand color and the Codex display name.

## 0.1.0 (2026-10-26)

- First release: `resolve-github-issue` packaged for Claude Code and Codex from one source.
