# Changelog

What changed for people who use the plugin, newest first. Add a line under **Unreleased** in the same change that alters a skill, the packaging or the install steps. A release renames **Unreleased** to the new version and date; `tools/build.py` fails when the version in `release.json` has no heading here.

## Unreleased

- All skill descriptions are now short summaries for a person browsing the skill list. Invocation and scope rules stay in each skill body.
- `resolve-github-issue` and `address-review-feedback` are shorter and phrased as what to do. Rules that apply only to some runs (stopping early, resuming, GitHub command mechanics, auto-fix pointers) moved to reference files the skill reads on demand.
- `resolve-github-issue` hands its fix to a fresh-context subagent for review, and falls back to a self-review on clients without a subagent tool.
- `resolve-github-issue` writes PR bodies from a template: Problem, Change, Evidence, Impact, Review, Merge risk.
- Added this changelog and `.out-of-scope/`, the record of ideas this repo decided against.
- Each skill has a user-facing page under `docs/skills/`: when to reach for it, and how to tell it is working.

## 0.6.0 (2026-11-10)

- New skill `watch-pr-feedback`: watches a PR and runs `address-review-feedback` on each new batch of review comments or failing CI.
- `address-review-feedback` treats each failing CI check on the PR head as a concern of its own.
- Python bytecode caches no longer end up in the packaged builds.

## 0.5.1 (2026-11-06)

- `address-review-feedback` now defaults to the complete workflow on invocation: fix, check merge conflicts and builds, commit, push and reply. Explicit limits still narrow it.

## 0.5.0 (2026-11-06)

- **Plugin renamed to `devflow` ("DevFlow").** `plugin update` does not follow an ID change: uninstall `dev-workflow-kit` and install `devflow`. Invocations change from `/dev-workflow-kit:…` to `/devflow:…`. See "Migrating from `dev-workflow-kit`" in the README.

## 0.4.0 (2026-11-06)

- Codex uses `dev-workflow-kit` as the plugin ID, matching Claude Code.

## 0.3.0 (2026-11-06)

- Claude Code uses the kebab-case plugin ID `dev-workflow-kit`.

## 0.2.1 (2026-11-05)

- New skill `address-review-feedback`, adapted from the Superpowers `receiving-code-review` skill.

## 0.1.6 (2026-10-27)

- `resolve-github-issue` records an impact analysis (who is affected, what changes, how it is checked) before editing.

## 0.1.5 (2026-10-26)

- `resolve-github-issue` is written in English.

## 0.1.4 (2026-10-26)

- Plugin branded as "Dev Workflow Kit".

## 0.1.3 (2026-10-26)

- Codex shows the skill as "Resolve GitHub Issue".

## 0.1.2 (2026-10-26)

- Plugin icons for Claude Code and Codex.

## 0.1.1 (2026-10-26)

- After opening a PR, `resolve-github-issue` tells the user how to turn on PR auto-fix.
- Codex invocations use the plugin-qualified skill name.

## 0.1.0 (2026-10-26)

- First release: `resolve-github-issue`, packaged for Claude Code and Codex from one source.
