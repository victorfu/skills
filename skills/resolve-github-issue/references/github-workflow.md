# GitHub operations reference

Use this when no suitable connector is available and the workflow runs through gh and git. The uppercase placeholders below are verified parameters to substitute, not text to paste as is; check the previous step's result before every dependent command.

## URL and repo identity

Parse the HTTPS URL's host, owner, repo and issue number; reject username/password, unexpected ports, control characters, dot segments, URL-encoded path separators and non-issues paths. Accept only github.com; Enterprise must be explicitly specified by the user and configured in gh for that host. Ignore query/fragment and rebuild the canonical URL. Never treat the raw URL, issue content or title as shell code.

For gh, pass --repo as HOST/OWNER/REPO so the current working directory or GH_HOST cannot point elsewhere. For gh api, use --hostname HOST. If the GitHub REST issue response includes a pull_request field, it is a PR; stop this issue workflow. If a repo transfer changes the canonical URL, re-verify before any write.

~~~text
gh auth status --hostname HOST
gh api --hostname HOST repos/OWNER/REPO/issues/NUMBER
gh repo view HOST/OWNER/REPO --json nameWithOwner,url,defaultBranchRef,isArchived,viewerPermission
gh issue view NUMBER --repo HOST/OWNER/REPO --json number,url,title,body,state,labels,assignees,comments
gh api --hostname HOST --paginate repos/OWNER/REPO/issues/NUMBER/comments
gh api --hostname HOST --paginate repos/OWNER/REPO/issues/NUMBER/timeline
git status --short
git remote -v
~~~

Parse every page of the last two APIs; do not conclude evidence is absent because the first page lacks it. Duplicate issue/PR checks must read the actual content and branch diff; a text mention is not evidence of a fix. Never print auth tokens, remote URLs containing tokens or private settings.

## The in progress label

First read the issue's existing labels and save label_preexisting. List all repo labels rather than only the first page; GitHub label names are case-insensitive, so compare case-insensitively too. If a label such as In Progress already exists, replace "in progress" in the commands below with its actual name:

~~~text
gh api --hostname HOST --paginate repos/OWNER/REPO/labels
~~~

Create it **only if it still does not exist after the case-insensitive comparison**. If you hit an error because someone else created it at the same time, re-read to confirm and then continue; do not overwrite with --force:

~~~text
gh label create "in progress" --repo HOST/OWNER/REPO --color "FBCA04" --description "Issue investigation or implementation is in progress"
gh issue edit NUMBER --repo HOST/OWNER/REPO --add-label "in progress"
gh issue view NUMBER --repo HOST/OWNER/REPO --json labels
~~~

Record label_added_by_this_run only after confirming this run added it. On network errors, read the state before deciding. When stopping without a PR, run the following only for a label this run added:

~~~text
gh issue edit NUMBER --repo HOST/OWNER/REPO --remove-label "in progress"
gh issue view NUMBER --repo HOST/OWNER/REPO --json labels
~~~

Do not substitute gh issue edit --add-project for the label; that does not set the Projects Status field to In Progress. If the user switches to Projects, read the real IDs of the specified project's item, Status field and single-select options, update only the specified item and re-confirm; never guess IDs or modify other projects at the same time.

## Worktree, commit and push

REMOTE is the remote name after verifying its URL, BASE is the explicitly specified or API-derived target branch, BRANCH is this task's branch and WORKTREE is a new absolute path. PUSH_REMOTE is the remote the fix branch is pushed to: REMOTE when you have write access to the target repo, otherwise a verified fork remote owned by the current account. HEAD_OWNER is the owner of PUSH_REMOTE; for the same repo it is OWNER. Run in the correct repo:

~~~text
git fetch REMOTE
git worktree add --no-track -b BRANCH WORKTREE REMOTE/BASE
~~~

--no-track keeps the new branch from using REMOTE/BASE as its upstream; set the upstream with --set-upstream on the first push.

From then on, set the working directory of every shell operation to WORKTREE. Read the repo guidelines that apply on that branch. When resuming an existing task, verify branch ownership and do not recreate the worktree. Never push private repo content to a different repo or one with wider visibility.

~~~text
git diff --check
git diff REMOTE/BASE
git add -- PATH1 PATH2
git diff --cached --check
git diff --cached
git commit -m "REPO_CONVENTIONAL_MESSAGE"
git status --short
git rev-parse HEAD
git show --stat --oneline HEAD
git push --set-upstream PUSH_REMOTE BRANCH
~~~

The verification and review omitted above must be completed before the commit, as SKILL.md describes. PATH1 and PATH2 must be files that were actually reviewed; for deletions or moves, respect the current environment's file permissions. Never use auto-stash, reset --hard, git clean, --no-verify or force push to clear obstacles.

## PRs and recovering from uncertain results

Always specify the PR's repo explicitly as the issue's target repo; for forks, specify head as the verified HEAD_OWNER:BRANCH. When looking for existing PRs, narrow by head/base and then check headRepository, headRepositoryOwner and headRefOid, not just the branch name. gh pr list returns at most 30 results by default; when results hit the limit, raise the limit or use the paginated API to confirm, and never treat a truncated result as the full list. After checking the OPEN/MERGED/CLOSED state, decide how to resume according to SKILL.md.

~~~text
gh pr list --repo HOST/OWNER/REPO --state all --head BRANCH --base BASE --json number,url,state,headRefName,headRefOid,headRepository,headRepositoryOwner,baseRefName
~~~

Write the PR body to a UTF-8 temporary Markdown file outside tracked sources, using a file tool or a safe literal string; never interpolate Markdown directly into the shell. Follow the repo's PR template; required content includes the problem evidence, the fix, the impact scope and how it was confirmed, tests and review results. Pass the PR title safely as well; never use eval, Invoke-Expression or build a string to hand to another shell layer.

~~~text
gh pr create --repo HOST/OWNER/REPO --base BASE --head HEAD_OWNER:BRANCH --title "PR_TITLE" --body-file BODY_FILE
gh pr view PR_NUMBER --repo HOST/OWNER/REPO --json url,state,isDraft,baseRefName,headRefName,headRefOid,body,statusCheckRollup
gh pr checks PR_NUMBER --repo HOST/OWNER/REPO
~~~

A regular same-repo PR may also use BRANCH as head explicitly. If the current CLI does not support the fork owner syntax, look up the CLI's officially supported way; never silently push to a different repo.

If gh pr create times out or its response is lost, first look for an existing PR by the exact head repo/branch and base; if one exists, read it and do not create again. If the git push response is lost, compare git ls-remote PUSH_REMOTE refs/heads/BRANCH against the local SHA. When gh pr checks has no checks yet or they are pending, record them as incomplete; never report everything as passing. Do not block delivery by waiting indefinitely, unless the user or repo requires waiting for CI.

## Official sources

- [GitHub CLI: editing issue labels](https://cli.github.com/manual/gh_issue_edit)
- [GitHub CLI: creating PRs and body-file](https://cli.github.com/manual/gh_pr_create)
- [GitHub: linking PRs to issues and closing conditions](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue)

If the installed version does not accept a flag in the examples, read that command's --help first and adjust; never claim an unsuccessful operation succeeded.
