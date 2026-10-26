# victorfu-skills

給 [Claude Code](https://code.claude.com) 與 [Codex](https://developers.openai.com/codex) 使用的開發工作流程 skills，以 plugin 形式安裝。

| Skill | 用途 |
| --- | --- |
| `resolve-github-issue` | 給它一個 GitHub issue，它會先驗證問題是否成立，再修正、測試、審查，最後開 PR。 |

## 需求

- Claude Code 或 Codex（CLI 或 desktop 皆可）
- `git`
- GitHub 存取：已登入的 [GitHub CLI](https://cli.github.com)（`gh auth login`），或客戶端內可用的 GitHub connector
- 要開 PR 的 repo 需有 push 權限；沒有的話，使用你自己的 fork

不需要 Python 或額外的 API key。

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
- **叫用尚未通過模型驗證**：已確認 Codex `skills/list` 及 Claude 啟動事件能找到正確 skill；實際送出唯讀叫用時，空白登入環境分別回報 401／`Not logged in`。未複製現有登入或 API key，因此不能宣稱模型已遵守流程或已實測隱式叫用禁止。
- **名稱一致**：skill 與顯示名稱為 `resolve-github-issue`；plugin／marketplace 為 `victorfu-skills`。兩個 CLI 的 plugin 載入清單均以 `victorfu-skills:resolve-github-issue` 識別 skill，集合前綴不是另一個 skill 名稱。

官方依據：[Claude CLI 環境](https://code.claude.com/docs/en/setup)、[Claude Desktop plugins／WSL 限制](https://code.claude.com/docs/en/desktop#install-plugins)、[Claude Linux beta](https://code.claude.com/docs/en/desktop-linux)、[Codex CLI](https://learn.chatgpt.com/docs/codex/cli)、[Codex plugins](https://learn.chatgpt.com/docs/plugins)、[Codex Linux preview](https://learn.chatgpt.com/docs/linux/linux-app)。隔離方法、測試命令與尚未驗證項目見 [實測紀錄](docs/verification.md#隔離客戶端實測2026-10-26)。

## 安裝

### Claude Code

```sh
claude plugin marketplace add victorfu/skills
claude plugin install victorfu-skills@victorfu-skills
```

也可以在 Claude Code 對話中執行 `/plugin marketplace add victorfu/skills`，再執行 `/plugin install victorfu-skills@victorfu-skills`。安裝後重新啟動 Claude Code，或執行 `/reload-plugins`。

### Codex

```sh
codex plugin marketplace add victorfu/skills
codex plugin add victorfu-skills@victorfu-skills
```

安裝後重新啟動 Codex。Codex desktop 也可以從 Plugins 目錄安裝。

### 固定版本

上面的指令會追蹤預設分支。發布版本 tag 之後，可以改成釘選特定版本：

```sh
claude plugin marketplace add "victorfu/skills#v0.1.0"
codex plugin marketplace add victorfu/skills --ref v0.1.0
```

## 使用

Skill 只會在你明確叫用時執行；單純貼上 issue 網址不會觸發。

```text
# Claude Code
/victorfu-skills:resolve-github-issue https://github.com/OWNER/REPO/issues/123

# Codex plugin（或從 skill picker 選取對應項目）
$victorfu-skills:resolve-github-issue https://github.com/OWNER/REPO/issues/123
```

若是 standalone 安裝，Codex 仍使用 `$resolve-github-issue`；上述帶前綴的名稱對應本次已核對的 plugin 載入結果，模型叫用仍待登入後驗證。

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

## 更新

```sh
# Claude Code
claude plugin marketplace update victorfu-skills
claude plugin update victorfu-skills@victorfu-skills

# Codex
codex plugin marketplace upgrade victorfu-skills
```

更新後重新啟動客戶端。Claude Code 只有在 plugin 版本號改變時才會換成新內容。

## 移除

```sh
# Claude Code
claude plugin uninstall victorfu-skills@victorfu-skills
claude plugin marketplace remove victorfu-skills

# Codex
codex plugin remove victorfu-skills@victorfu-skills
codex plugin marketplace remove victorfu-skills
```

## 疑難排解

- **叫用到另一個版本的 skill**：你的環境裡可能已有同名的 standalone skill（例如 `~/.claude/skills/resolve-github-issue/`）。在 Claude Code 中改用帶 namespace 的 `/victorfu-skills:resolve-github-issue`。
- **更新後仍是舊版**：重新啟動客戶端或開新 session；Claude Code 需要版本號改變才會更新快取。
- **Codex 沒有 `plugin add` 指令**：Codex 版本太舊，請先升級，或改從 desktop 的 Plugins 目錄安裝。
- **`gh` 權限錯誤**：執行 `gh auth status` 確認已登入，且帳號對目標 repo 有存取權。

## 參與開發

`skills/` 是唯一的手寫來源，`dist/` 與兩份 marketplace 檔案由 `tools/build.py` 產生。建置、測試、本機試用與發布流程見 [CONTRIBUTING.md](CONTRIBUTING.md)。
