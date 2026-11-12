# DevFlow

**English** | [繁體中文](README.zh-TW.md)

Development workflow skills for [Claude Code](https://code.claude.com) and [Codex](https://developers.openai.com/codex), installed as a plugin.

| Skill | Purpose |
| --- | --- |
| `resolve-github-issue` | Give it a GitHub issue: it first verifies the problem is real, then fixes, tests, and reviews it, and finally opens a PR. |
| `address-review-feedback` | Verify review feedback and failing CI against current code before applying justified fixes; explain rejected, already-fixed and blocked concerns. |
| `watch-pr-feedback` | Watch a PR with `gh` and run `address-review-feedback` on each new batch of review comments or failing CI, until no new feedback arrives. |
| `audit-repository` | Audit a complete repository for verified bugs, with a coverage ledger and discussion before any fixes. |

## Requirements

- Claude Code or Codex (CLI or desktop)
- `git`
- For GitHub workflows, GitHub access: a signed-in [GitHub CLI](https://cli.github.com) (`gh auth login`), or a GitHub connector available in your client
- For workflows that open or update PRs, push access to the repo you want to open a PR against; if you don't have it, use your own fork

No extra API keys are required. `watch-pr-feedback` also needs `gh` and Python 3 (standard library only) for its watch helpers; hybrid forwarding also needs the `cli/gh-webhook` extension and repository webhook access. If the extension is missing, the watch uses polling fallback without installing it unless explicitly authorized; `audit-repository` uses Python 3.10+ (standard library only) for its coverage ledger, with manual Git-based accounting as a fallback. The ledger helper refuses to build an inventory when Git cannot inspect the repository or a directory cannot be listed, so a partial listing is never reported as complete coverage. Auditing a local repository needs no GitHub login or push permission.

## Installation

### Claude Code

```sh
claude plugin marketplace add victorfu/skills
claude plugin install devflow@victorfu-skills
```

You can also run `/plugin marketplace add victorfu/skills` and then `/plugin install devflow@victorfu-skills` inside a Claude Code conversation. After installing, restart Claude Code or run `/reload-plugins`.

### Codex

```sh
codex plugin marketplace add victorfu/skills
codex plugin add devflow@victorfu-skills
```

Restart Codex after installing. Codex desktop can also install it from the Plugins directory.

### Pinning a version

The commands above track the default branch. Once release tags are published, you can pin a specific version instead:

```sh
claude plugin marketplace add "victorfu/skills#v0.1.0"
codex plugin marketplace add victorfu/skills --ref v0.1.0
```

## App / CLI / OS support and testing

The table separates what each client officially supports from what this repo has actually tested; not every cell has been verified end to end. Last checked: 2026-10-26.

| Client | macOS | Windows (native) | Ubuntu (native) |
| --- | --- | --- | --- |
| Claude Code CLI | Officially supported; install, load, and update tested in isolation | Officially supported; this plugin not tested on the CLI | Officially supported (20.04+); this plugin not tested on the CLI |
| Claude Code App (local Code sessions in Desktop) | Plugins officially supported; GUI not tested | Plugins officially supported; GUI not tested | Linux beta (22.04+); GUI not tested |
| Codex CLI | Officially supported; install, load, and update tested in isolation | Officially supported; this plugin not tested on the CLI | Officially supported; this plugin not tested on the CLI |
| Codex App (called Codex in ChatGPT Desktop in newer docs) | Plugins officially supported; GUI not tested | Plugins officially supported; GUI not tested | Linux preview (24.04 / 26.04 LTS); GUI not tested |

- **WSL is separate**: Claude Desktop's WSL sessions are officially listed as not supporting plugins, so the native Windows column does not apply to them. This does not mean the Claude CLI inside WSL lacks support. Cloud and Cowork sessions are also outside this local Code session matrix.
- **The three-OS CI covers packaging tests**: Ubuntu 24.04, macOS 26 ARM64, and Windows Server 2025, each with Python 3.10 and 3.12. All six combinations pass the build-output checks and 10 unit tests. This does not mean Windows 10/11, every CPU architecture, or GUI/model execution has been tested. [CI run](https://github.com/victorfu/skills/actions/runs/40261949089)
- **macOS CLI test scope**: macOS 27.0.1 ARM64, Codex 0.164.0, Claude Code 2.1.310. Both clients installed `0.1.0` from GitHub, and a `0.1.0 → 0.1.1` update was tested against a local Git fixture, confirming the new process's load path, version, and content hash. `0.1.1` existed only in the isolated fixture and was not published.
- **Codex passed a signed-in, read-only invocation**: Codex CLI 0.164.0, using an existing ChatGPT sign-in, invoked `$dev-workflow-kit:resolve-github-issue` (the plugin's former ID; see [Migrating from `dev-workflow-kit`](#migrating-from-dev-workflow-kit)); the model read the correct plugin's `SKILL.md` and asked for more information when no repo was given. Claude's isolated invocation still fails because it is not signed in. Neither client has been verified on the full issue → PR flow or on blocking implicit invocation. See the [invocation verification log](docs/verification.md#codex-登入後叫用驗證2026-10-26) (in Traditional Chinese).
- **Consistent naming**: the skill is `resolve-github-issue`, shown in Codex as "Resolve GitHub Issue"; the plugin ID is `devflow` on both CLIs (Codex displays it as "DevFlow"), and the marketplace ID is `victorfu-skills`. Both CLIs list the skill as `devflow:resolve-github-issue`; the prefix is the plugin namespace, not another skill name.

Official sources: [Claude CLI setup](https://code.claude.com/docs/en/setup), [Claude Desktop plugins / WSL limits](https://code.claude.com/docs/en/desktop#install-plugins), [Claude Linux beta](https://code.claude.com/docs/en/desktop-linux), [Codex CLI](https://learn.chatgpt.com/docs/codex/cli), [Codex plugins](https://learn.chatgpt.com/docs/plugins), [Codex Linux preview](https://learn.chatgpt.com/docs/linux/linux-app). For the isolation method, test commands, and what remains unverified, see the [test log](docs/verification.md#隔離客戶端實測2026-10-26) (in Traditional Chinese).

## Usage

In Codex, select **DevFlow** with `@`, then choose **Resolve GitHub Issue**, **Address Review Feedback**, **Watch PR Feedback**, or **Audit Repository**. In Claude Code, the plugin list shows **devflow**.

The skill runs only when you invoke it explicitly; pasting an issue URL on its own does not trigger it.

```text
# Claude Code
/devflow:resolve-github-issue https://github.com/OWNER/REPO/issues/123

# Codex plugin (or pick the matching entry from the skill picker)
$devflow:resolve-github-issue https://github.com/OWNER/REPO/issues/123
```

This repo ships as a plugin, so Codex invocations and the `default_prompt` in `agents/openai.yaml` both use `$devflow:resolve-github-issue`, which has been tested in a signed-in CLI. The fully qualified name distinguishes it from same-named skills in other plugins. If you install it as a standalone skill instead, change both the invocation and `default_prompt` to `$resolve-github-issue`.

To get an assessment without any changes, add "evaluate only, don't modify anything" after the command; it will then only read and analyze.

You can also pass just an issue reference, such as `OWNER/REPO#123`. If you leave out the repo, it must be uniquely determinable from the current working directory; otherwise the skill asks you first.

### What the full workflow does

1. Reads the issue and the relevant code, and classifies it as `VALID`, `INVALID`, `ALREADY_FIXED`, or `NEEDS_INFO`.
2. Adds an `in progress` label to the issue; without permission to add labels, it skips this and tells you at the end.
3. Fixes the root cause in a separate git worktree and branch (for example `fix/issue-123-short-slug`), and adds a regression test.
4. Runs the tests and reviews the full diff.
5. Commits and pushes the fix branch, then opens a ready-for-review PR linked to the issue.

For any result other than `VALID`, it changes no code, opens no PR, and removes the label it added.

It **does not**: merge the PR, close or reopen the issue, comment on the issue, force push, or push directly to the default branch.

It also does not turn on auto-fix for the PR itself; once the PR is open, it tells you how to enable it in the client you are using.

### Addressing review feedback

Use `address-review-feedback` with a PR URL or pasted feedback. Both skills require explicit invocation; review notifications and pasted URLs alone do not start work.

```text
# Claude Code: assess without editing or posting
/devflow:address-review-feedback https://github.com/OWNER/REPO/pull/123 Assess the feedback only; do not modify or post anything.

# Codex: verify and fix locally
$devflow:address-review-feedback Check the feedback below and apply justified local fixes with relevant tests. Do not commit, push or post replies.

# Either client: use its invocation above, followed by
https://github.com/OWNER/REPO/pull/123 Verify the feedback, fix valid concerns, test, commit and push to my existing PR branch. Do not post replies or resolve threads.
```

Failing CI checks on the PR head are treated as concerns too, even when there are no review comments; infrastructure or flaky failures are reported rather than patched around.

It checks the latest code, requirements, callers and supported platforms, then classifies each concern as `VALID`, `INVALID`, `ALREADY_FIXED` or `NEEDS_INFO`. It verifies the proposed fix separately from the concern and checks public or dynamic entry points before deleting apparently unused code. When one item needs clarification, only that item and its dependents wait; independent authorized fixes continue.

Invoking this skill defaults to verifying feedback, applying justified fixes, checking merge conflicts and builds, committing and pushing to the existing PR, and publishing replies to review comments. Each published reply ends with a one-line note that an AI agent wrote it on your behalf; ask for it to be left out if you do not want it. Explicit limits such as assessment-only, local-only, no push or no replies override those defaults. Asking for a reply draft does not publish it. Resolving threads still requires an explicit request; the workflow does not merge PRs or force-push.

The skill's package is checked locally; full client invocation remains unverified.

### Watching a PR until feedback stops

Use `watch-pr-feedback` with a PR URL. It watches the PR with `gh` (hybrid mode by default) and, for each new batch of review comments, reviews, PR conversation comments or failing CI on the head SHA, runs the full `address-review-feedback` workflow. It stops when nothing new arrives for a 10-minute quiet window with no CI pending, the PR closes, or it reaches 10 rounds or 4 hours.

```text
/devflow:watch-pr-feedback https://github.com/OWNER/REPO/pull/123
$devflow:watch-pr-feedback https://github.com/OWNER/REPO/pull/123 Use poll mode every 2 minutes, stop after 1 hour, do not post replies.
```

Default `hybrid` mode uses a local `gh webhook forward` receiver to wake the helper, with full reconciliation every 5 minutes and 60-second polling fallback when the receiver is unavailable. It persists settling and unacknowledged batches for restart recovery. Ask for `poll` mode or no webhook setup to skip the receiver and extension installation. See [hybrid setup and lifecycle](skills/watch-pr-feedback/references/hybrid.md). The forwarding extension is for local development/testing, not production hosting.

Comments you post with your own `gh` account count as feedback, so you can review your own PR with it. Replies the workflow posts carry a hidden `<!-- devflow:agent-reply -->` marker and are skipped, so they do not trigger new rounds; ask it to ignore your account entirely to get the old behavior. Limits you give apply to every round. It never merges, force-pushes or re-runs CI. The packaged polling script was tested against a real merged PR and with mocked events. Hybrid scheduling and recovery have offline tests; real webhook forwarding and a complete agent-driven watch are not established by those tests.

### Audit a repository before fixing bugs

Explicitly invoke `audit-repository` with a local path, a Git repository URL, or no target to use the current repository:

```text
/devflow:audit-repository /path/to/repository
$devflow:audit-repository https://github.com/OWNER/REPO
$devflow:audit-repository
```

It inventories tracked and untracked, non-ignored files, reviews the full first-party scope, and double-checks each candidate against callers, contracts and supported versions. The report separates confirmed bugs from potential issues and states coverage and verification limits. Reports are written in the language of your request unless you ask for another one.

This skill is read-only: it does not fix code, create branches, commit, push, open issues or PRs, or automatically start another skill. Audit metadata and reproductions stay outside the target repository. A later explicit request is needed to implement fixes. Failure evidence is investigated first, but the full audit continues unless you explicitly narrow the scope.

The helper and both packages are tested locally; complete model-driven audits in both clients have not yet been validated. Installing this plugin does not replace an existing standalone `repo-debugger`; use the qualified invocation above to select this skill.

## Updating

```sh
# Claude Code
claude plugin marketplace update victorfu-skills
claude plugin update devflow@victorfu-skills

# Codex
codex plugin marketplace upgrade victorfu-skills
```

Restart the client after updating. Claude Code only switches to new content when the plugin version number changes. [CHANGELOG.md](CHANGELOG.md) lists what each version changed, including changed defaults.

## Migrating from `dev-workflow-kit`

Versions up to 0.4.0 used the plugin ID `dev-workflow-kit` (shown in Codex as "Dev Workflow Kit"). The plugin is now `devflow` ("DevFlow"). Because the ID changed, `plugin update` will not pick up the new name; remove the old plugin and install the new one:

```sh
# Claude Code
claude plugin marketplace update victorfu-skills
claude plugin uninstall dev-workflow-kit@victorfu-skills
claude plugin install devflow@victorfu-skills

# Codex
codex plugin marketplace upgrade victorfu-skills
codex plugin remove dev-workflow-kit@victorfu-skills
codex plugin add devflow@victorfu-skills
```

Restart the client afterwards. The skills themselves are unchanged; only the invocation prefix changes, for example `/dev-workflow-kit:resolve-github-issue` becomes `/devflow:resolve-github-issue` (and `$dev-workflow-kit:…` becomes `$devflow:…` in Codex). Update any saved prompts, aliases or docs that use the old prefix.

## Uninstalling

```sh
# Claude Code
claude plugin uninstall devflow@victorfu-skills
claude plugin marketplace remove victorfu-skills

# Codex
codex plugin remove devflow@victorfu-skills
codex plugin marketplace remove victorfu-skills
```

## Troubleshooting

- **A different version of the skill runs**: your environment may already have a standalone skill with the same name (for example `~/.claude/skills/resolve-github-issue/`). In Claude Code, use the namespaced `/devflow:resolve-github-issue` instead.
- **Still on the old version after updating**: restart the client or start a new session; Claude Code only refreshes its cache when the version number changes.
- **Codex has no `plugin add` command**: your Codex version is too old. Upgrade it first, or install from the Plugins directory in the desktop app.
- **`gh` permission errors**: run `gh auth status` to confirm you are signed in and that the account can access the target repo.

## Contributing

`skills/` is the only hand-written source; `dist/` and both marketplace files are generated by `tools/build.py`. For building, testing, trying it locally, and releasing, see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE).
