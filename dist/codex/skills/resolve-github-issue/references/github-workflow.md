# GitHub 操作參考

適用於沒有合適 connector 時，以 gh 與 git 完成流程。下列大寫代號是待替換的已核對參數，不能直接照貼；每個有依賴的命令都先檢查前一步結果。

## URL 與 repo 身分

解析 HTTPS URL 的 host、owner、repo 與 issue number，拒絕 username/password、非預期 port、控制字元、dot segments、URL 編碼的路徑分隔符與非 issues 路徑。只接受 github.com；Enterprise 須使用者明確指定且 gh 已設定該 host。忽略 query／fragment 後重新組合 canonical URL。不要把原始 URL、issue 內容、標題當 shell 程式碼。

gh 的 --repo 使用 HOST/OWNER/REPO，避免目前工作目錄或 GH_HOST 指向別處。gh api 使用 --hostname HOST。GitHub REST 的 issue 回應若包含 pull_request 欄位，就是 PR，應停止此 issue 流程。若 repo 轉移導致 canonical URL 改變，重新核對後再進行任何寫入。

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

最後兩個 API 需解析所有頁面，不因第一頁沒有證據就認定不存在。重複 issue／PR 檢查需讀實際內容與分支 diff；文字提及不是修復證據。不輸出 auth token、含 token 的 remote URL 或私密設定。

## in progress 標籤

先讀 issue 原有 labels，保存 label_preexisting。列出所有 repo labels，避免只查第一頁；GitHub label 名稱不分大小寫，核對時也不分大小寫。若已有 In Progress 等同名 label，下列指令的 "in progress" 一律換成它的實際名稱：

~~~text
gh api --hostname HOST --paginate repos/OWNER/REPO/labels
~~~

**只有不分大小寫比對後仍不存在時**才建立。遇到同時被他人建立的錯誤，重新讀取確認，再繼續，不使用 --force 覆寫：

~~~text
gh label create "in progress" --repo HOST/OWNER/REPO --color "FBCA04" --description "Issue investigation or implementation is in progress"
gh issue edit NUMBER --repo HOST/OWNER/REPO --add-label "in progress"
gh issue view NUMBER --repo HOST/OWNER/REPO --json labels
~~~

只在確認本次新增後記錄 label_added_by_this_run。發生網路錯誤時先讀狀態再判定。中止且未建 PR 時，只有本次新增的 label 才執行：

~~~text
gh issue edit NUMBER --repo HOST/OWNER/REPO --remove-label "in progress"
gh issue view NUMBER --repo HOST/OWNER/REPO --json labels
~~~

不以 gh issue edit --add-project 代替 label；那不會把 Projects 的 Status 欄位設為 In Progress。若使用者改用 Projects，需讀取指定 project 的 item、Status field、single-select options 的真實 ID，僅更新指定 item 並重新確認，不猜 ID 或同時修改其他 projects。

## Worktree、commit 與 push

REMOTE 是核對 URL 後的 remote 名稱，BASE 是明確指定或 API 查得的目標分支，BRANCH 是本任務分支，WORKTREE 是新的絕對路徑。PUSH_REMOTE 是推送修正分支的 remote：對目標 repo 有寫入權限時就是 REMOTE，否則是已核對屬於目前帳號的 fork remote。HEAD_OWNER 是 PUSH_REMOTE 所屬的 owner；同 repo 時就是 OWNER。在正確 repo 執行：

~~~text
git fetch REMOTE
git worktree add --no-track -b BRANCH WORKTREE REMOTE/BASE
~~~

--no-track 避免新分支把 REMOTE/BASE 當成 upstream；首次 push 時才以 --set-upstream 設定。

之後把每個 shell 操作的工作目錄設定為 WORKTREE。讀取該分支下適用的 repo 規範。在恢復既有任務時核對 branch ownership，不重新建立 worktree。私人 repo 內容不可推送到不同或可見性更寬的 repo。

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

上面省略的驗證與審查必須依 SKILL.md 在 commit 前完成。PATH1、PATH2 必須是實際審查過的檔案；需要刪除或移動時遵守目前環境的檔案權限。不要用自動 stash、reset --hard、git clean、--no-verify 或 force push 清除障礙。

## PR 與不確定結果恢復

PR 的 repo 永遠明確指定為 issue 的目標 repo；fork 使用已驗證的 HEAD_OWNER:BRANCH 指定 head。查詢既有 PR 時以 head/base 限縮後，再核對 headRepository、headRepositoryOwner 與 headRefOid，不只比對分支名稱。gh pr list 預設最多 30 筆；結果達上限時增加 limit 或用分頁 API 確認，不能把截斷結果當完整清單。核對 OPEN／MERGED／CLOSED 狀態後，依 SKILL.md 決定恢復方式。

~~~text
gh pr list --repo HOST/OWNER/REPO --state all --head BRANCH --base BASE --json number,url,state,headRefName,headRefOid,headRepository,headRepositoryOwner,baseRefName
~~~

寫入 PR 內文至 UTF-8 的暫存 Markdown 檔，放在 tracked source 之外；使用檔案工具或安全的字面字串寫入，不把 Markdown 直接插入 shell。遵循 repo 的 PR template，必要內容包括問題證據、修正、測試及 review 結果。PR title 也須安全傳參，不使用 eval、Invoke-Expression 或組字串再交另一層 shell 執行。

~~~text
gh pr create --repo HOST/OWNER/REPO --base BASE --head HEAD_OWNER:BRANCH --title "PR_TITLE" --body-file BODY_FILE
gh pr view PR_NUMBER --repo HOST/OWNER/REPO --json url,state,isDraft,baseRefName,headRefName,headRefOid,body,statusCheckRollup
gh pr checks PR_NUMBER --repo HOST/OWNER/REPO
~~~

一般同 repo PR 也可明確使用 BRANCH 作 head。若 fork owner 語法不被目前 CLI 支援，查核 CLI／官方支援方式，不能默默改推到別的 repo。

gh pr create 若逾時或回應遺失，先依精確 head repo／branch 與 base 找是否已建立；存在則讀取該 PR，不再次 create。git push 若回應遺失，以 git ls-remote PUSH_REMOTE refs/heads/BRANCH 比對本地 SHA。gh pr checks 尚無檢查或 pending 要記錄為未完成，不能報告全數通過；不以無限等待阻止交付，除非使用者或 repo 必須等 CI。

## 官方依據

- [GitHub CLI：修改 issue labels](https://cli.github.com/manual/gh_issue_edit)
- [GitHub CLI：建立 PR 與 body-file](https://cli.github.com/manual/gh_pr_create)
- [GitHub：PR 與 issue 連結／關閉條件](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue)

若目前安裝版本不接受範例中的旗標，先讀該命令 --help，再調整，不能宣稱未成功的操作已完成。
