# 驗證紀錄

日期：2026-10-26（Asia/Taipei）。範圍僅限 repo 內開發；未執行安裝、解除安裝、遠端寫入、release、commit、tag 或使用者設定修改。

## Checkout 與原始來源

- cwd：`/Users/victor/Codebase/skills`。
- `origin` fetch／push：`https://github.com/victorfu/skills`。
- 初始工作樹乾淨、目錄空白，`master` 為尚無 commit 的分支。唯讀 `git ls-remote --symref origin HEAD` 沒有 HEAD；`gh repo view victorfu/skills --json nameWithOwner,url,defaultBranchRef,isEmpty` 確認 canonical repo 相符、isEmpty=true、遠端尚無預設分支。
- 兩份原始 skill 都是一般目錄。Claude 有 `SKILL.md`、`references/github-workflow.md`；Codex 另有 `agents/openai.yaml`；兩邊無 `scripts/`。
- references 位元組一致；frontmatter 一致且只有 name／description；兩邊無 `$ARGUMENTS`。
- 正文差異與使用者提供清單一致：API key 敘述、CLAUDE.md／工作目錄、分支預設，以及最後換行。沒有其他實質差異。
- Codex 原始 skill 的 implicit policy 為 true；原始 plugin 與 skill 顯示名稱為舊名。本 repo 不修改這些原檔。
- 建置前後對 Claude skill 與整個舊 Codex plugin 的所有 6 個檔案計算 SHA-256，檔案清單及內容均一致。共同 reference 也與兩平台產物位元組一致。

## 官方文件所支持的設計

| 項目 | 已確認依據與採用方式 |
| --- | --- |
| Skill frontmatter | [Codex](https://learn.chatgpt.com/docs/build-skills) 要求 name、description；[Claude](https://code.claude.com/docs/en/skills) 說明 disable-model-invocation 是其擴充。未找到 Codex 官方對此擴充欄位的相容承諾，採生成適配。 |
| Codex metadata | agents/openai.yaml 的 interface 與 policy.allow_implicit_invocation；設定 false 保留明確叫用。 |
| Plugin manifest | [Codex packaging](https://developers.openai.com/plugins/build/plugins) 已提供 portable root plugin.json，也明示 .codex-plugin/plugin.json 仍受支援。此 repo 採後者及 skills 路徑；[Claude](https://code.claude.com/docs/en/plugins-reference) 使用 .claude-plugin/plugin.json，name 必填、version／description／author 一併提供，skills 使用標準目錄。 |
| Catalog | [Codex](https://developers.openai.com/plugins/build/plugins) 為 .agents/plugins/marketplace.json，含 name、interface、plugins 的 source／policy／category；[Claude](https://code.claude.com/docs/en/plugins/marketplace-reference) 為 .claude-plugin/marketplace.json，含 name、owner、plugins。兩份皆由同一生成器產生，不承諾任意 schema 互換。 |
| Local loading | [兩邊 skills 文件](https://code.claude.com/docs/en/skills) 與 [Codex 文件](https://learn.chatgpt.com/docs/build-skills) 均說明 standalone symlink 支援。Claude --plugin-dir 官方支援當次 session；[plugin loading](https://code.claude.com/docs/en/plugins/loading) 有 plugin 路徑 containment，發布包不依賴外部連結。 |
| Updates | [Claude hosting](https://code.claude.com/docs/en/plugins/host-marketplace) 支援 #ref，版本變更才換快取；[管理文件](https://code.claude.com/docs/en/discover-plugins) 區分 marketplace refresh／plugin update／reload。Codex 官方文件提供 --ref、marketplace upgrade、cache 複本與重啟方式，未據此假設某固定自動更新週期。 |
| Isolation | [Claude environment](https://code.claude.com/docs/en/env-vars) 支援 CLAUDE_CONFIG_DIR；Codex -c 的本次程序 override 經本機 help 核對。這些不是本次執行過的安裝測試。 |

## 實際執行

環境：macOS、Python 3.12、隔離暫存 venv 的 PyYAML 6.0.3；`codex-cli 0.164.0`、Claude Code `2.1.310`。

| 驗證 | 結果 |
| --- | --- |
| `python tools/build.py` | 產生 14 個檔案，兩包及兩 catalog；未接觸既有安裝。 |
| `python tools/build.py --check` | 通過。檢查 YAML、名稱、policy、版本格式、default prompt、reference 路徑及所有產生檔精確位元組。 |
| `python -m unittest discover -s tools -p test_build.py -v` | 6 項通過：重建相同與正文 parity、漂移偵測且 check 不寫入、新增／移除 skill、拒絕 implicit policy、拒絕斷鏈、拒絕 output symlink。均在暫存 copy 測試。 |
| 內建 skill-creator `quick_validate.py skills/resolve-github-issue` | 通過。 |
| `claude plugin validate dist/claude --strict --json` | success=true；manifest errors／warnings 都為空。 |
| `claude plugin validate .claude-plugin/marketplace.json --strict --json` | success=true；manifest errors／warnings 都為空。 |
| Codex CLI help | 已讀 plugin add／remove、marketplace add／upgrade；此版沒有獨立 validate 子命令，未用 install 代替驗證。 |
| Git whitespace／來源 hash | 通過；原始 6 個檔案沒有變更。 |

Claude 驗證器另外顯示公共 plugin directory 的 LICENSE_MISSING 與 ICON_MISSING；這不影響上面的本地 manifest 驗證結果，但代表尚未符合該公共目錄上架條件。本次不擅自授予授權、不為未要求的商店上架產生圖示。沒有執行 `--profile directory` 並宣稱通過。

第一次打包測試揭露 macOS 系統 `/var` symlink 被過度拒絕；已將檢查限制在輸出 repo 範圍內，再完整重跑 6 項通過。這也避免將正常系統暫存路徑誤判成輸出逃逸。

## 尚未驗證及使用者下一步

- Linux／Windows：已加入 GitHub Actions 三 OS matrix；尚未 push，因此 CI 尚未跑。Windows symlink 若無權限，該項測試會 skip 並顯示原因，其餘打包不依賴 symlink。
- 未實際啟動模型 session 或安裝 plugin；明確叫用控制、namespaced 顯示、managed settings、熱載入與同名來源選取仍需客戶端 smoke test。
- 未跑 GitHub marketplace 安裝／升版／回退端到端測試，因新包及 tag 尚未發布，且本次禁止安裝與遠端發布。
- Codex snapshot refresh 是否立即刷新該版本的 plugin cache，需在使用者實際客戶端核對；不保證 `git pull` 更新已安裝包。
- GitHub issue 副作用未測。建議先驗證：未叫用只貼 URL 不啟動、明確叫用唯讀不寫入、單一編號缺 repo 時釐清、URL 指向 PR 時拒絕。完整修復流程再使用經授權的測試 repo。
- 正式發布前由維護者決定 repo 授權條款、執行 smoke test、驗證目標分支，提交與發布對應版本 tag。公共 plugin directory 上架需另行處理。
