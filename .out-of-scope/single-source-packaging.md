# Single-source packaging (dropping `dist/`)

The plugin keeps its generated `dist/claude` and `dist/codex` packages. The repo root will not become the plugin that both clients install.

## Why this is out of scope

It works, and it was tested, but it gives up what the build provides.

Tested on 2026-11-10 with a throwaway tree holding `skills/`, `assets/` and a single `.claude-plugin/plugin.json` (a `skills` array, no `.codex-plugin/`), with `disable-model-invocation: true` written into each source `SKILL.md`:

- Codex CLI 0.167.0, isolated `CODEX_HOME`: `plugin marketplace add` and `plugin add` succeeded, and app-server `skills/list` returned all three skills with `errors=[]`. Codex fell back to `.claude-plugin/plugin.json` and accepted the extra frontmatter key.
- Claude Code 2.1.322: `claude plugin validate` accepted the plugin manifest with the `skills` array. An install from that tree was not run.

What it would cost:

- **A clean package.** Codex copied the whole marketplace root into its cache, `.git` included for a local source. From this repo that would also ship `tools/`, `docs/` and both READMEs. `dist/` ships skills, the manifest and icons only.
- **`BUILD.json`.** The per-file hashes that let an installed copy be compared with the release exist only because the package is generated.
- **Per-client packages.** Claude Code currently gets no `agents/` directory, and Codex gets its own manifest with display name, brand color and icons. The fallback manifest returned none of those (`brandColor`, icons: null).
- **The parity check.** CI proves the two packages differ only where intended. With one tree there is nothing to compare.

The gain would be one less build step for contributors. `tools/build.py --check` already makes a forgotten rebuild a CI failure, so the step is cheap.

Revisit if either client starts rejecting generated packages, or if a third client needs a layout the generator cannot produce.

## Prior requests

- 2026-11-10: raised while comparing this repo with mattpocock/skills, which ships its promoted skills straight from the source tree.
