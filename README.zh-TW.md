# DevFlow

[English](README.md) | **繁體中文**

給 [Claude Code](https://code.claude.com) 與 [Codex](https://developers.openai.com/codex) 使用的開發工作流程 skills，以 plugin 形式安裝。

| Skill | 用途 |
| --- | --- |
| `resolve-github-issue` | 給它一個 GitHub issue，它會先驗證問題是否成立，再修正、測試、審查，最後開 PR。 |
| `address-review-feedback` | 先對照目前程式碼驗證 review 意見與失敗的 CI，再處理成立的修改；說明不成立、已修正及待釐清的項目。 |
| `watch-pr-feedback` | 用 `gh` 監看 PR，每有新的 review comments 或 CI 失敗就執行 `address-review-feedback`，直到不再有新意見。 |
| `audit-repository` | 完整審查 repository，雙重驗證 Bug 並記錄覆蓋率，先討論再修正。 |

## 需求

- Claude Code 或 Codex（CLI 或 desktop 皆可）
- `git`
- GitHub 工作流程需要 GitHub 存取：已登入的 [GitHub CLI](https://cli.github.com)（`gh auth login`），或客戶端內可用的 GitHub connector
- 要開啟或更新 PR 的 repo 需有 push 權限；沒有的話，使用你自己的 fork

不需要額外的 API key。`watch-pr-feedback` 另需 `gh` 與 Python 3（只用標準函式庫）執行監看腳本；hybrid 轉送另需 `cli/gh-webhook` extension 與 repository webhook 權限。缺少 extension 時會使用輪詢備援，只有明確授權才會安裝。`audit-repository` 的覆蓋率腳本使用 Python 3.10 以上版本（只用標準函式庫），沒有 Python 時可改用 Git 手動記錄。Git 無法檢查該 repository 或有目錄無法列出時，這個腳本會直接失敗而不建立清單，避免把不完整的清單回報成覆蓋完成。審查本機 repository 不需要 GitHub 登入或 push 權限。

## 安裝

### Claude Code

```sh
claude plugin marketplace add victorfu/skills
claude plugin install devflow@victorfu-skills
```

也可以在 Claude Code 對話中執行 `/plugin marketplace add victorfu/skills`，再執行 `/plugin install devflow@victorfu-skills`。安裝後重新啟動 Claude Code，或執行 `/reload-plugins`。

### Codex

```sh
codex plugin marketplace add victorfu/skills
codex plugin add devflow@victorfu-skills
```

安裝後重新啟動 Codex。Codex desktop 也可以從 Plugins 目錄安裝。

### 固定版本

上面的指令會追蹤預設分支。發布版本 tag 之後，可以改成釘選特定版本：

```sh
claude plugin marketplace add "victorfu/skills#v0.1.0"
codex plugin marketplace add victorfu/skills --ref v0.1.0
```

## App／CLI／OS 支援與實測

下表區分「客戶端官方支援」與「本 repo 已實測」，不是所有格子都已完成端到端驗證。查證日期：2026-10-26。

| 客戶端 | macOS | Windows 原生 | Ubuntu 原生 |
| --- | --- | --- | --- |
| Claude Code CLI | 官方支援；已隔離測試安裝、載入與更新 | 官方支援；本包 CLI 未實測 | 官方支援（20.04+）；本包 CLI 未實測 |
| Claude Code App（Desktop 的 Code 本機 session） | 官方支援 plugins；GUI 未實測 | 官方支援 plugins；GUI 未實測 | Linux beta（22.04+）；GUI 未實測 |
| Codex CLI | 官方支援；已隔離測試安裝、載入與更新 | 官方支援；本包 CLI 未實測 | 官方支援；本包 CLI 未實測 |
| Codex App（新版文件稱 ChatGPT Desktop 的 Codex） | 官方支援 plugins；GUI 未實測 | 官方支援 plugins；GUI 未實測 | Linux preview（24.04／26.04 LTS）；GUI 未實測 |

- **WSL 另算**：Claude Desktop 的 WSL session 官方明列不支援 plugins，不能套用 Windows 原生欄；這不等同於 WSL 裡的 Claude CLI 不支援。Cloud／Cowork 也不在此本機 Code session 矩陣內。
- **三 OS CI 已通過的是打包測試**：Ubuntu 24.04、macOS 26 ARM64、Windows Server 2025，搭配 Python 3.10／3.12，共六組均通過產物檢查與 10 項單元測試。它不代表 Windows 10／11、所有 CPU 架構或 GUI／模型執行都測過。[CI 結果](https://github.com/victorfu/skills/actions/runs/40261949089)
- **macOS CLI 實測範圍**：macOS 27.0.1 ARM64、Codex 0.164.0、Claude Code 2.1.310。兩邊均從 GitHub 安裝 `0.1.0`，並以本機 Git fixture 測試 `0.1.0 → 0.1.1`；已核對新程序的載入路徑、版本及內容 hash。`0.1.1` 只存在隔離 fixture，並未發布。
- **Codex 已通過登入後的唯讀叫用**：Codex CLI 0.164.0 以既有 ChatGPT 登入實測 `$dev-workflow-kit:resolve-github-issue`（plugin 舊識別碼，見[從 `dev-workflow-kit` 遷移](#從-dev-workflow-kit-遷移)），模型讀取正確 plugin 的 `SKILL.md`，並在缺少 repo 時要求補充資訊。Claude 的隔離叫用仍因未登入而失敗；兩邊均未驗證完整 issue → PR 流程或隱式叫用禁止。詳見[叫用驗證紀錄](docs/verification.md#codex-登入後叫用驗證2026-10-26)。
- **名稱一致**：skill 名稱為 `resolve-github-issue`，Codex 顯示名稱為「Resolve GitHub Issue」；兩個 CLI 的 plugin 識別碼皆為 `devflow`（Codex 顯示為「DevFlow」），marketplace 識別碼為 `victorfu-skills`。兩邊均以 `devflow:resolve-github-issue` 識別 skill，前綴是 plugin namespace，不是另一個 skill 名稱。

官方依據：[Claude CLI 環境](https://code.claude.com/docs/en/setup)、[Claude Desktop plugins／WSL 限制](https://code.claude.com/docs/en/desktop#install-plugins)、[Claude Linux beta](https://code.claude.com/docs/en/desktop-linux)、[Codex CLI](https://learn.chatgpt.com/docs/codex/cli)、[Codex plugins](https://learn.chatgpt.com/docs/plugins)、[Codex Linux preview](https://learn.chatgpt.com/docs/linux/linux-app)。隔離方法、測試命令與尚未驗證項目見 [實測紀錄](docs/verification.md#隔離客戶端實測2026-10-26)。

## 使用

Codex 的 `@` 選單選取 **DevFlow**，再選 **Resolve GitHub Issue**、**Address Review Feedback**、**Watch PR Feedback** 或 **Audit Repository**。Claude Code 的 plugin 清單顯示 **devflow**。

Skill 只會在你明確叫用時執行；單純貼上 issue 網址不會觸發。

```text
# Claude Code
/devflow:resolve-github-issue https://github.com/OWNER/REPO/issues/123

# Codex plugin（或從 skill picker 選取對應項目）
$devflow:resolve-github-issue https://github.com/OWNER/REPO/issues/123
```

本 repo 以 plugin 發布，Codex 叫用與 `agents/openai.yaml` 的 `default_prompt` 統一使用 `$devflow:resolve-github-issue`，已在登入的 CLI 實測。此完整名稱可區別其他 plugin 中的同名 skill；若自行改為 standalone 安裝，須將叫用及 `default_prompt` 一併改成 `$resolve-github-issue`。

只想評估、不要改任何東西時，在指令後面加上「只評估，不要修改」，它就只會讀取與分析。

也可以只給 issue 編號，例如 `OWNER/REPO#123`；沒寫 repo 時，必須能從目前的工作目錄唯一判斷出目標 repo，否則它會先問你。

### 完整流程會做什麼

1. 讀取 issue 與相關程式碼，判定為 `VALID`、`INVALID`、`ALREADY_FIXED` 或 `NEEDS_INFO`。
2. 在 issue 加上 `in progress` label；沒有 label 權限時略過，並在最後告訴你。
3. 在獨立的 git worktree 與分支（例如 `fix/issue-123-short-slug`）修正根因，並加入回歸測試。
4. 執行測試，並審查完整 diff。
5. Commit、push 修正分支，開一個 ready for review 的 PR，並連結 issue。

判定為 `VALID` 以外的結果時，不會修改程式碼或開 PR，並移除它自己加上的 label。

它**不會**：merge PR、關閉或重開 issue、在 issue 留言、force push，或直接 push 到 default branch。

它也不會自行開啟 PR 的 auto-fix；PR 建立後，會依你使用的客戶端告訴你怎麼開。

### 處理 code review 意見

叫用 `address-review-feedback` 並提供 PR 網址或貼上 review 意見。兩個 skill 都需要明確叫用；收到 review 通知或單純貼網址不會啟動流程。

```text
# Claude Code：只評估，不修改或發送
/devflow:address-review-feedback https://github.com/OWNER/REPO/pull/123 只評估 review 意見，不修改或發送任何內容。

# Codex：先驗證，再修正本機程式碼
$devflow:address-review-feedback 驗證下方 review 意見，修正成立的項目並執行相關測試。不要 commit、push 或回覆留言。

# 任一客戶端：以上方對應的叫用指令加上
https://github.com/OWNER/REPO/pull/123 驗證 review 意見，修正成立的項目、測試、commit 並 push 到我的既有 PR 分支。不要回覆留言或 resolve threads。
```

PR head 上失敗的 CI checks 也會當作待處理的意見，即使沒有任何 review comment；基礎設施或不穩定（flaky）造成的失敗只回報，不繞過。

它會核對最新程式碼、需求、呼叫端及支援平台，將各項意見判定為 `VALID`、`INVALID`、`ALREADY_FIXED` 或 `NEEDS_INFO`。意見成立與建議修法是否正確會分開驗證；刪除看似未使用的程式碼前，也會檢查公開 API 或動態呼叫。有一項需要釐清時，只暫停該項及其相依修改，其他已驗證且已授權的項目會繼續。

明確叫用後，預設會驗證意見、修復成立的問題、檢查合併衝突與 build、commit 並 push 更新既有 PR，最後回覆 review comments。每則發布的回覆結尾會附一行說明，表示這是 AI agent 代你撰寫的；不需要時請在叫用時說明。使用者明確要求只驗證、只修改本機、不 push 或不回覆時，會依限制執行；要求回覆草稿不會直接發送。Resolve threads 仍需明確要求，流程不會 merge PR 或 force push。

此 skill 已在本機檢查打包，完整客戶端叫用尚未驗證。

### 持續監看 PR 直到沒有新意見

叫用 `watch-pr-feedback` 並提供 PR 網址。它用 `gh` 監看 PR（預設 hybrid 模式），每當 head SHA 出現新的 review comments、reviews、PR 對話留言或 CI 失敗，就執行完整的 `address-review-feedback` 流程。在 10 分鐘的安靜期內沒有新意見且沒有 CI 尚在執行、PR 關閉，或達到 10 輪／4 小時上限時停止。

```text
/devflow:watch-pr-feedback https://github.com/OWNER/REPO/pull/123
$devflow:watch-pr-feedback https://github.com/OWNER/REPO/pull/123 使用 poll 模式，每 2 分鐘檢查一次，1 小時後停止，不要回覆留言。
```

預設使用 `hybrid` 模式：使用本機 `gh webhook forward` 接收事件喚醒 helper，每 5 分鐘完整補查；接收器不可用時退回每 60 秒輪詢。評論合併等待與未確認批次會持久保存，支援中斷後復原。要求使用 `poll` 模式，或要求不設定 webhook 時，會跳過接收器設定。設定與停止步驟見 [hybrid 操作說明](skills/watch-pr-feedback/references/hybrid.md)。此轉送方式適用本機開發與測試，不是正式環境 webhook hosting。

你用自己 `gh` 帳號留的意見也會觸發新一輪，所以可以用同一個帳號 review 自己的 PR。workflow 發出的回覆帶有隱藏標記 `<!-- devflow:agent-reply -->` 並會被略過，不會再觸發新一輪；若要沿用舊行為，可要求它完全忽略你的帳號。你指定的限制會套用到每一輪。它不會 merge、force push 或重新執行 CI。輪詢腳本已對實際已合併的 PR 及模擬事件測試。Hybrid 排程與復原有離線測試；這些測試不代表已驗證實際 webhook 轉送或完整的 agent 監看流程。

### 完整審查 repository，先討論再修正

明確叫用 `audit-repository`，可提供本機路徑、Git repository URL，或省略目標以使用目前 repository：

```text
/devflow:audit-repository /path/to/repository
$devflow:audit-repository https://github.com/OWNER/REPO
$devflow:audit-repository
```

它會盤點 tracked 與未被忽略的 untracked 檔案、完整審查第一方範圍，再對照呼叫端、行為契約與支援版本雙重驗證每個候選問題。報告區分 Confirmed Bugs 與 Potential Issues，並列出覆蓋率和驗證限制；報告使用你提出請求時的語言，也可以另外指定。

此 skill 僅進行唯讀審查，不會修正程式碼、建立分支、commit、push、開 issue 或 PR，也不會自動啟動其他 skill。審查記錄與重現資料放在目標 repo 外；實作修正需要後續明確要求。若提供錯誤資訊，會優先調查該路徑，再繼續完整審查，除非你明確縮小範圍。

Helper 與兩套打包產物已於本機測試；兩個客戶端中由模型執行完整審查的流程尚未驗證。安裝 plugin 不會取代既有 standalone `repo-debugger`，請使用上方帶 namespace 的名稱選取此 skill。

## 更新

```sh
# Claude Code
claude plugin marketplace update victorfu-skills
claude plugin update devflow@victorfu-skills

# Codex
codex plugin marketplace upgrade victorfu-skills
```

更新後重新啟動客戶端。Claude Code 只有在 plugin 版本號改變時才會換成新內容。各版本的變更（包含預設行為的改變）列在 [CHANGELOG.md](CHANGELOG.md)（英文）。

## 從 `dev-workflow-kit` 遷移

0.4.0 以前的 plugin 識別碼為 `dev-workflow-kit`（Codex 顯示為「Dev Workflow Kit」），現已改為 `devflow`（「DevFlow」）。識別碼改變後 `plugin update` 不會換到新名稱，須移除舊 plugin 再安裝新的：

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

完成後重新啟動客戶端。Skill 內容不變，只有叫用前綴改變，例如 `/dev-workflow-kit:resolve-github-issue` 改為 `/devflow:resolve-github-issue`（Codex 的 `$dev-workflow-kit:…` 改為 `$devflow:…`）。請一併更新已存的提示、別名或文件中的舊前綴。

## 移除

```sh
# Claude Code
claude plugin uninstall devflow@victorfu-skills
claude plugin marketplace remove victorfu-skills

# Codex
codex plugin remove devflow@victorfu-skills
codex plugin marketplace remove victorfu-skills
```

## 疑難排解

- **叫用到另一個版本的 skill**：你的環境裡可能已有同名的 standalone skill（例如 `~/.claude/skills/resolve-github-issue/`）。在 Claude Code 中改用帶 namespace 的 `/devflow:resolve-github-issue`。
- **更新後仍是舊版**：重新啟動客戶端或開新 session；Claude Code 需要版本號改變才會更新快取。
- **Codex 沒有 `plugin add` 指令**：Codex 版本太舊，請先升級，或改從 desktop 的 Plugins 目錄安裝。
- **`gh` 權限錯誤**：執行 `gh auth status` 確認已登入，且帳號對目標 repo 有存取權。

## 參與開發

`skills/` 是唯一的手寫來源，`dist/` 與兩份 marketplace 檔案由 `tools/build.py` 產生。建置、測試、本機試用與發布流程見 [CONTRIBUTING.md](CONTRIBUTING.md)（英文）。

## 授權

[MIT](LICENSE)。
