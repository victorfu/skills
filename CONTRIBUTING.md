# Contributing

## Project layout

```text
skills/<name>/                     The only hand-written source
  SKILL.md                         Frontmatter holds only name and description; the body is the full workflow
  references/                      Reference docs the skill links to
  agents/openai.yaml               Codex-only display name and invocation policy
release.json                       Version and plugin metadata (name is the stable ID, displayName the display name)
assets/icon.svg                    Source for the Codex plugin icon; icon.png (512) and logo.png (1024) are exported from it
tools/build.py                     Generates dist/ and both marketplaces; --check compares without writing
tools/test_build.py                Packaging regression tests (run in a temporary directory)
dist/claude/, dist/codex/          Generated plugins (commit them; do not edit by hand)
.claude-plugin/marketplace.json    Generated Claude Code marketplace
.agents/plugins/marketplace.json   Generated Codex marketplace
docs/verification.md               Research and verification notes
```

The two platforms' outputs differ in only two places:

- **Claude Code**: the `SKILL.md` frontmatter gets an extra `disable-model-invocation: true` line, and `agents/` is left out.
- **Codex**: `policy.allow_implicit_invocation: false` in `agents/openai.yaml` restricts the skill to explicit invocation.

The body and references are byte-identical on both sides. Files under `skills/` whose names start with `.` (such as `.DS_Store`) are not packaged.

## Setup

You need Git and Python 3.10 or later.

macOS/Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

Windows PowerShell (no need to activate the venv):

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

The commands below use macOS/Linux paths; on Windows, replace `.venv/bin/python` with `.\.venv\Scripts\python.exe`.

## Building and testing

After every change to `skills/`, `assets/`, `release.json` or `tools/`:

```sh
.venv/bin/python tools/build.py
.venv/bin/python tools/build.py --check
.venv/bin/python -m unittest discover -s tools -p test_build.py -v
claude plugin validate dist/claude --strict
claude plugin validate .claude-plugin/marketplace.json --strict
```

`build.py` removes files from `dist/` that are no longer needed, so do not put other files in `dist/`. CI runs `--check` and the unit tests on Ubuntu, macOS and Windows with Python 3.10 and 3.12, and fails if the outputs were not rebuilt.

## Trying it locally

Try it in a throwaway test project so it does not mix with your regular installation. If you need fully isolated settings, point `CLAUDE_CONFIG_DIR` at a new directory (you may need to sign in again).

**Claude Code**: load the generated plugin directly; it applies only to that session.

```sh
claude --plugin-dir /absolute/path/to/skills/dist/claude
```

Invoke `/victorfu-skills:resolve-github-issue`. After changing the source, run `build.py` again, then run `/reload-plugins` or start a new session.

**Codex**: register the marketplace from the local path and install.

```sh
codex plugin marketplace add /absolute/path/to/skills
codex plugin add victorfu-skills@victorfu-skills
```

Codex copies the plugin into its own cache, so after changing the source you need to reinstall and restart Codex.

Before testing against real issues, use read-only mode ("assess only, don't change anything") to confirm the behavior; run the full workflow in a test repo where you can freely create branches and PRs.

## Adding a skill

1. Create `skills/<name>/SKILL.md`. Its frontmatter may contain only `name` (must equal the directory name, lowercase with hyphens) and `description`.
2. Create `skills/<name>/agents/openai.yaml` with `interface.display_name`, `short_description` (25 to 64 characters), a `default_prompt` containing `$<plugin-name>:<name>`, and `policy.allow_implicit_invocation: false`. `<plugin-name>` must match `name` in `release.json`; this repo uses `$victorfu-skills:<name>`, and the build checks the full invocation name.
3. Relative links in the `SKILL.md` body must point to files that actually exist inside the skill directory.
4. Run the build and tests; `build.py` picks up every skill under `skills/` automatically.

## Releasing a new version

1. Update `version` in `release.json` (SemVer, for example `0.1.1`). Claude Code only updates an installed plugin when the version number changes, so bump it on every release.
2. Run the build and tests, and confirm `--check` passes.
3. Commit all changes (including `dist/` and both marketplaces), push, and wait for CI to pass.
4. Create a tag on that commit and push it:

   ```sh
   git tag -a v0.1.1 -m "victorfu-skills 0.1.1"
   git push origin v0.1.1
   ```

Never move a published tag, and never release different content under the same version number.
