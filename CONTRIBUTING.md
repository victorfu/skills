# Contributing

## Project layout

```text
skills/<name>/                     The only hand-written source
  SKILL.md                         Frontmatter holds only name and description; the body is the full workflow
  references/                      Reference docs the skill links to
  agents/openai.yaml               Codex-only display name and invocation policy
release.json                       Version and plugin metadata (name is the plugin ID, marketplace the marketplace ID, displayName the Codex display name)
assets/icon.svg                    Source for the Codex plugin icon; icon.png (512) and logo.png (1024) are exported from it
tools/build.py                     Generates dist/ and both marketplaces; --check compares without writing
tools/test_build.py                Packaging regression tests (run in a temporary directory)
tools/run_evals.py                 Runs evals/ against dist/claude with `claude plugin eval` (costs tokens)
evals/<case>/                      Behavior eval cases (prompt.md + graders/, or case.yaml + scaffold.sh)
evals/_fixtures/                   Fixture project and issue exports the scaffolds copy in
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
.venv/bin/python -m unittest discover -s tools -p "test_*.py" -v
claude plugin validate dist/claude --strict
claude plugin validate .claude-plugin/marketplace.json --strict
```

`build.py` removes files from `dist/` that are no longer needed, so do not put other files in `dist/`. CI runs `--check` and the unit tests on Ubuntu, macOS and Windows with Python 3.10 and 3.12, and fails if the outputs were not rebuilt. A second job installs Claude Code on Ubuntu, runs both `validate --strict` commands, and installs the plugin from the local marketplace into a temporary config directory.

## Behavior evals

`evals/<case>/` holds cases for `claude plugin eval`. A case is either `prompt.md` plus one grader per file under `graders/`, or a `case.yaml` (`schema_version: "1.1"`, an `execution` block with the prompt and limits, a `graders` list, and `context.scaffold_script` when it needs files). Every prompt starts with the explicit `/devflow:<skill>` invocation. Scaffold scripts run with the agent's working directory as the current directory and copy `evals/_fixtures/` into it; `_fixtures/scaffold-shop.sh` takes fixture files to copy plus `--fixed` (overlay the corrected implementation) and `--git` (commit the copy), and writes a `.env` holding a canary value; a `regex` grader with `match: not_contains` fails any reply that repeats it.

```sh
.venv/bin/python tools/run_evals.py --ablation none --runs 3
.venv/bin/python tools/run_evals.py --case 'audit-*' --ablation none --runs 4 --max-cost-usd 3
```

`run_evals.py` refuses to run when `dist/` is stale, assembles `dist/claude` and `evals/` in a temporary directory so nothing from `evals/` ships, and copies reports to `evals/results/` (gitignored). Each run is a real model call on your account (about $0.15 per run; the 12 cases at 3 runs each cost about $5.60), so evals run by hand and not in CI.

Rules for cases:

- Agents get read-only tools (`Read`, `Glob`, `Grep`, `Skill`) and `disallowed_tools: [Agent, Task]`. Granting `Bash` needs a sandbox, which is not available on Windows, so flows that commit, push or call `gh` are not covered yet; they need macOS or Linux and a stand-in for `gh`.
- A grader must be able to fail. With read-only tools the agent cannot write anything, so "made no changes" graders prove nothing; test injected instructions with something a read-only agent can do, such as revealing the canary.
- Do not put the expected answer in the prompt or the fixture, and make the fixture decide the verdict unambiguously.
- Results vary between runs: report passes out of runs with the model and Claude Code version, and use `--ablation none`. These skills only run on explicit invocation, so the no-plugin baseline says little.
- `--case` takes one glob; to run several unrelated cases, run the whole suite or call the script once per case.
- When a case fails, decide first whether the reply or the grader is wrong; then fix the skill wording and rerun the case to confirm.

## Trying it locally

Try it in a throwaway test project so it does not mix with your regular installation. If you need fully isolated settings, point `CLAUDE_CONFIG_DIR` at a new directory (you may need to sign in again).

**Claude Code**: load the generated plugin directly; it applies only to that session.

```sh
claude --plugin-dir /absolute/path/to/skills/dist/claude
```

Invoke `/devflow:resolve-github-issue`. After changing the source, run `build.py` again, then run `/reload-plugins` or start a new session.

**Codex**: register the marketplace from the local path and install.

```sh
codex plugin marketplace add /absolute/path/to/skills
codex plugin add devflow@victorfu-skills
```

Codex copies the plugin into its own cache, so after changing the source you need to reinstall and restart Codex.

Before testing against real issues, use read-only mode ("assess only, don't change anything") to confirm the behavior; run the full workflow in a test repo where you can freely create branches and PRs.

## Adding a skill

1. Create `skills/<name>/SKILL.md`. Its frontmatter may contain only `name` (must equal the directory name, lowercase with hyphens) and `description`. Every skill here is user-invoked, so write the description for a person browsing the skill list: a one- or two-sentence summary of what it does. Keep invocation rules and scope limits in the body.
2. Create `skills/<name>/agents/openai.yaml` with `interface.display_name`, `short_description` (25 to 64 characters), a `default_prompt` containing `$<plugin-name>:<name>`, and `policy.allow_implicit_invocation: false`. `<plugin-name>` must match `name` in `release.json`; this repo uses `$devflow:<name>`, and the build checks the full invocation name.
3. Relative links in the `SKILL.md` body must point to files that actually exist inside the skill directory. A path to a sibling skill (`../<other-skill>/SKILL.md`) must name an existing source skill and file, and every "section N" mention must match a `## N.` heading in the same file. Text inside fenced code blocks is not checked.
4. Run the build and tests; `build.py` picks up every skill under `skills/` automatically.

## Releasing a new version

1. Update `version` in `release.json` (SemVer, for example `0.1.1`). Claude Code only updates an installed plugin when the version number changes, so bump it on every release.
2. In `CHANGELOG.md`, rename "Unreleased" to the new version and date. Every change to what a skill does needs a line there, written for someone deciding whether to update; mark changed defaults in bold.
3. Run the build and tests, and confirm `--check` passes.
4. Commit all changes (including `dist/` and both marketplaces), push, and wait for CI to pass.
5. Create an annotated tag on that commit (if the release went through a PR, the merge commit on `master`) and push it. The tag message is `displayName` from `release.json` followed by the version:

   ```sh
   git tag -a v0.1.1 -m "DevFlow 0.1.1"
   git push origin v0.1.1
   ```

Never move a published tag, and never release different content under the same version number.
