# 驗證紀錄

日期：2026-10-26（Asia/Taipei）。前半為初版建置時的查證紀錄，當時範圍僅限 repo 內開發，未執行安裝、解除安裝、遠端寫入、release、tag 或使用者設定修改；最後一節記錄初版 commit 審查後的修正與重新驗證。

## Checkout 與原始來源

- cwd：本 repo 根目錄。
- `origin` fetch／push：`https://github.com/victorfu/skills`。
- 初始工作樹乾淨、目錄空白，`master` 為尚無 commit 的分支。唯讀 `git ls-remote --symref origin HEAD` 沒有 HEAD；`gh repo view victorfu/skills --json nameWithOwner,url,defaultBranchRef,isEmpty` 確認 canonical repo 相符、isEmpty=true、遠端尚無預設分支。
- 兩份原始 skill 都是一般目錄。Claude 有 `SKILL.md`、`references/github-workflow.md`；Codex 另有 `agents/openai.yaml`；兩邊無 `scripts/`。
- references 位元組一致；frontmatter 一致且只有 name／description；兩邊無 `$ARGUMENTS`。
- 正文差異與使用者提供清單一致：API key 敘述、CLAUDE.md／工作目錄、分支預設，以及最後換行。沒有其他實質差異。
- Codex 原始 skill 的 implicit policy 為 true；原始 plugin 與 skill 顯示名稱為舊名。本 repo 不修改這些原檔。
- 建置前後對 Claude skill 與整個舊 Codex plugin 的所有 6 個檔案計算 SHA-256，檔案清單及內容均一致。共同 reference 也與兩平台產物位元組一致。
- 原始 reference 最後一行以 CRLF 結尾；審查後已改為 LF（見最後一節），因此本 repo 的 reference 與原始檔只差這一個位元組。

## 官方文件所支持的設計

| 項目 | 已確認依據與採用方式 |
| --- | --- |
| Skill frontmatter | [Codex](https://learn.chatgpt.com/docs/build-skills) 要求 name、description；[Claude](https://code.claude.com/docs/en/skills) 說明 disable-model-invocation 是其擴充。未找到 Codex 官方對此擴充欄位的相容承諾，採生成適配。 |
| Codex metadata | agents/openai.yaml 的 interface 與 policy.allow_implicit_invocation；設定 false 保留明確叫用。 |
| Plugin manifest | [Codex packaging](https://developers.openai.com/plugins/build/plugins) 已提供 portable root plugin.json，也明示 .codex-plugin/plugin.json 仍受支援。此 repo 採後者及 skills 路徑；[Claude](https://code.claude.com/docs/en/plugins-reference) 使用 .claude-plugin/plugin.json，name 必填、version／description／author 一併提供，skills 使用標準目錄。 |
| Catalog | [Codex](https://developers.openai.com/plugins/build/plugins) 為 .agents/plugins/marketplace.json，含 name、interface、plugins 的 source／policy／category；[Claude](https://code.claude.com/docs/en/plugins/marketplace-reference) 為 .claude-plugin/marketplace.json，含 name、owner、plugins。兩份皆由同一生成器產生，不承諾任意 schema 互換。 |
| Local loading | [兩邊 skills 文件](https://code.claude.com/docs/en/skills) 與 [Codex 文件](https://learn.chatgpt.com/docs/build-skills) 均說明 standalone symlink 支援。Claude --plugin-dir 官方支援當次 session；[plugin loading](https://code.claude.com/docs/en/plugins/loading) 有 plugin 路徑 containment，發布包不依賴外部連結。 |
| Updates | [Claude hosting](https://code.claude.com/docs/en/plugins/host-marketplace) 支援 #ref，版本變更才換快取；[管理文件](https://code.claude.com/docs/en/discover-plugins) 區分 marketplace refresh／plugin update／reload。Codex 官方文件提供 --ref、marketplace upgrade、cache 複本與重啟方式，未據此假設某固定自動更新週期。 |
| Isolation | [Claude environment](https://code.claude.com/docs/en/env-vars) 支援 CLAUDE_CONFIG_DIR；Codex -c 的單次程序 override 經本機 help 核對。這些不是實際執行過的安裝測試。 |

## 初版實際執行

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
| Git whitespace／來源 hash | 來源 hash 通過，原始 6 個檔案沒有變更。whitespace 結果不成立：當時 `git diff --check` 沒有涵蓋尚未追蹤的新檔；對初版 commit 執行 `git diff --check <empty-tree> HEAD` 會回報 reference 第 101 行（CRLF）trailing whitespace，已於審查後修正。 |

Claude 驗證器另外顯示公共 plugin directory 的 LICENSE_MISSING 與 ICON_MISSING；這不影響上面的本地 manifest 驗證結果，但代表尚未符合該公共目錄上架條件。未擅自授予授權、不為未要求的商店上架產生圖示。沒有執行 `--profile directory` 並宣稱通過。

第一次打包測試揭露 macOS 系統 `/var` symlink 被過度拒絕；已將檢查限制在輸出 repo 範圍內，再完整重跑 6 項通過。這也避免將正常系統暫存路徑誤判成輸出逃逸。

## 尚未驗證及使用者下一步

- Linux／Windows：build `--check` 與單元測試已在 GitHub Actions 通過（見下一節）。若 Windows 環境沒有建立 symlink 的權限，該項測試會 skip 並顯示原因，其餘打包不依賴 symlink。
- 未實際啟動模型 session 或安裝 plugin；明確叫用控制、namespaced 顯示、managed settings、熱載入與同名來源選取仍需客戶端 smoke test。
- 未跑 GitHub marketplace 安裝／升版／回退端到端測試，因新包及 tag 尚未發布，且初版作業範圍不含安裝與遠端發布。
- Codex snapshot refresh 是否立即刷新該版本的 plugin cache，需在使用者實際客戶端核對；不保證 `git pull` 更新已安裝包。
- GitHub issue 副作用未測。建議先驗證：未叫用只貼 URL 不啟動、明確叫用唯讀不寫入、單一編號缺 repo 時釐清、URL 指向 PR 時拒絕。完整修復流程再使用經授權的測試 repo。
- 正式發布前由維護者決定 repo 授權條款、執行 smoke test、驗證目標分支，提交與發布對應版本 tag。公共 plugin directory 上架需另行處理。

## 審查後修正與重新驗證（2026-10-26）

初版 commit 推送後，GitHub Actions 的 windows-latest job 在 `python tools/build.py --check` 失敗（`Generated files stale: dist/codex/BUILD.json, dist/claude/BUILD.json`），macOS／Ubuntu 通過。原因是 Windows 的 Path 排序不分大小寫，BUILD.json 的 hash 順序因此改變。審查同時找到其他問題，修正如下：

- BUILD.json 的 hash 依路徑文字排序，輸出與平台無關；hash 改記錄各平台實際出貨的位元組。
- 測試改以位元組寫入 LF，避免 Windows `write_text` 產生 CRLF。
- reference 最後一行改為 LF，`.gitattributes` 只保留 `* text=auto eol=lf`。
- 以 `.` 開頭的來源檔（例如 `.DS_Store`）不打包；`.gitignore` 加入 `.DS_Store`。
- frontmatter／YAML 不是 mapping 時回報 `FAIL:`，不再印 traceback。
- 移除過期產物時一併刪除變空的目錄；建置只改寫內容有變的檔案。
- Claude 包不再包含只有 Codex 使用的 `agents/`。
- reference 補上 PUSH_REMOTE／HEAD_OWNER 定義、`worktree add --no-track`、label 名稱不分大小寫；SKILL.md 允許在沒有 label 權限時記錄原因後繼續。
- CI 移除不會失敗的 `git diff --exit-code`，matrix 加入 Python 3.10。

| 驗證 | 結果 |
| --- | --- |
| `python tools/build.py`（macOS、Python 3.12.4） | 產生 13 個檔案（Claude 包少了 `agents/openai.yaml`），移除 1 個過期產物及其空目錄。 |
| `python tools/build.py --check`（Python 3.12.4 與 3.10.19） | 通過。 |
| `python -m unittest discover -s tools -p test_build.py -v`（Python 3.12.4 與 3.10.19） | 10 項通過；新增 BUILD.json hash 順序與出貨內容、Claude 不含 `agents/`、忽略隱藏檔、拒絕空 frontmatter。 |
| 以不分大小寫的 Path 排序模擬 Windows 執行 `expected_files()` | 產物位元組與一般排序完全相同。 |
| `git diff --check` | 通過。 |
| `claude plugin validate dist/claude --strict`、`claude plugin validate .claude-plugin/marketplace.json --strict` | 皆通過。 |

GitHub Actions：推送修正及 CI action 升級（`actions/checkout@v7`、`actions/setup-python@v7`，Node 24）後，[run 40261949089](https://github.com/victorfu/skills/actions/runs/40261949089)（commit `e293397`）的 6 個 job 全部通過，涵蓋 ubuntu-latest、macos-latest、windows-latest 各搭配 Python 3.10 與 3.12。每個 job 的 `build.py --check` 都輸出 `PASS: 13 generated files`，10 項單元測試均為 `OK`；Windows 上的 symlink 測試實際執行並通過，沒有被略過。原本失敗的 windows-latest 已經通過；annotations 與完整 log 都不再出現 Node.js 20 淘汰警告。

## 隔離客戶端實測（2026-10-26）

本輪獲授權在隔離環境執行安裝、叫用與更新測試，取代前文「尚未安裝」的狀態；不代表前文所有未測項目已完成。

### 環境與隔離邊界

- 執行環境：macOS 27.0.1 ARM64；Codex CLI 0.164.0；Claude Code CLI 2.1.310。
- GitHub 安裝：Codex 固定 commit `e293397e805baf818314e26be122b1091b7ed39b`；Claude 追蹤預設分支，實際 clone 為 `da979ba625f31af1c5f944e695a5cceed0795d3d`。兩者的 skill／manifest 同為 `0.1.0`；後者只新增 CI 驗證紀錄。
- 在系統暫存目錄建立四個全新 profile：兩個測 GitHub 安裝，兩個測更新。每個 Codex 子程序使用自己的 `CODEX_HOME`，Claude 子程序使用自己的 `CLAUDE_CONFIG_DIR`；cwd 是新的暫存工作目錄，不是使用者 repo。
- 使用環境變數白名單，不繼承模型 API key、token 或 App bridge 環境變數；不複製既有 auth／設定。Codex 設定 `cli_auth_credentials_store = "file"`。Git 不讀取 global／system config。
- 每個客戶端測試子程序均經 macOS `sandbox-exec` 啟動，額外禁止寫入原使用者家目錄。另在純暫存 canary 驗證相同 deny rule 確實回報 `Operation not permitted`；沒有用原使用者檔案做寫入試驗。
- 模型叫用只要求對缺少 repo 的 issue 編號做唯讀評估。Claude 禁用所有 tools／外部 MCP；Codex 使用 read-only sandbox。未登入造成失敗後，不嘗試讀取、移植或更新現有憑證。
- 安裝輸出的 `scope: user` 指該隔離 profile 的使用者範圍；所有已核對的安裝路徑都在暫存目錄內。

官方隔離依據：[Codex CODEX_HOME](https://learn.chatgpt.com/docs/config-file/environment-variables)、[Claude CLAUDE_CONFIG_DIR](https://code.claude.com/docs/en/env-vars)。這些是子程序設定，不是修改 shell profile 或原使用者設定。

### 實際結果

| 項目 | Codex CLI | Claude Code CLI |
| --- | --- | --- |
| GitHub marketplace 註冊 | 通過；固定指定 commit | 通過；預設分支 |
| plugin 安裝 | 通過；0.1.0 | 通過；0.1.0 |
| 安裝清單 | enabled=true；正確 plugin id | enabled=true；正確 plugin id |
| 新程序載入 | app-server `skills/list` 找到目標，errors=[] | CLI `system/init` 的 plugins、skills、slash_commands 包含目標 |
| 名稱 | runtime name=`victorfu-skills:resolve-github-issue`；displayName=`resolve-github-issue` | slash command=`victorfu-skills:resolve-github-issue` |
| 明確唯讀叫用 | 嘗試後失敗：401，缺少認證 | 嘗試後失敗：Not logged in，API token usage=0 |
| Git fixture 更新 0.1.0 → 0.1.1 | `marketplace upgrade` 通過 | `marketplace update` 後 `plugin update` 通過 |
| 更新後載入與內容 | 新 app-server 指向 0.1.1 cache；標記與 BUILD hash 一致 | 新 CLI init 回報 0.1.1 cache；相同 slash command；標記與 BUILD hash 一致 |

`skills/list` 回應沒有輸出 implicit policy，不能由該回應宣稱已驗證 policy 生效；安裝包內仍可靜態確認 `allow_implicit_invocation: false`。Claude 產物的 `disable-model-invocation: true` 也已保留，但模型行為同樣未通過登入後驗證。

### 已執行的命令與更新方法

以下每一行都由上述隔離 runner 啟動；**不可直接在原使用者 profile 照貼**。`TEST_GIT_URL` 是只綁定 `127.0.0.1` 的暫存 Git server，並非 GitHub 發布來源。

```text
codex plugin marketplace add victorfu/skills --ref e293397e805baf818314e26be122b1091b7ed39b --json
codex plugin add victorfu-skills@victorfu-skills --json
codex plugin list --marketplace victorfu-skills --json
claude plugin marketplace add victorfu/skills --json
claude plugin install victorfu-skills@victorfu-skills
claude plugin list --json

# 在另兩個全新 profile 安裝同一份 0.1.0 本機 Git fixture：
codex plugin marketplace add TEST_GIT_URL --ref master --json
codex plugin add victorfu-skills@victorfu-skills --json
claude plugin marketplace add TEST_GIT_URL --json
claude plugin install victorfu-skills@victorfu-skills

# 只修改 fixture 的 release.json 為 0.1.1，加入測試內容標記並重新 build；
# commit/push 的唯一目標是暫存 bare repo，不是原 checkout 或 GitHub。
codex plugin marketplace upgrade victorfu-skills --json
claude plugin marketplace update victorfu-skills
claude plugin update victorfu-skills@victorfu-skills --json
```

Codex 的載入檢查使用該版本 `app-server generate-json-schema` 輸出的 protocol：`initialize`、`initialized`、`skills/list`（`forceReload: true`）。Claude 使用 `--print --verbose --output-format stream-json` 讀取 `system/init`，`plugins` 回報實際版本／路徑，`slash_commands` 含目標名稱。兩邊都以新程序檢查更新，未測執行中 session 的熱重載。

Git fixture 起初採簡單 HTTP server：Codex 成功，但 Claude 的 shallow clone 回報 `dumb http transport does not support shallow capabilities`；本機 `file://` marketplace URL 也被此 Claude CLI 拒絕。改用 `git http-backend` 提供 smart HTTP 後成功。這是測試 transport 差異，不是 GitHub 安裝失敗。兩個 loopback 測試 server 已在測試完成後停止。

### 原始狀態檢查

測試前後針對兩份原始 skill／舊 Codex plugin 的 6 個檔案，以及兩邊的設定與 Claude plugin 登錄共 11 個路徑記錄 SHA-256／是否存在。原始 6 個檔案、Codex config、Claude settings 與兩份 plugin 登錄均未改變。

唯一觀察到 hash 變更的是原使用者 `.claude.json`。觀察期間工作區也有其他並行修改；本輪測試程序有禁止寫入原家目錄的 OS sandbox，因此不能把整個使用者環境的並行狀態宣稱為完全不變，也不據此猜測變更來源或回寫該檔案。測試沒有解除安裝／修改原 plugin、修改原設定或將隔離設定合併回去。

### 未測與不能從本次結果推論的項目

- 登入後的模型叫用、隱式叫用禁止、唯讀範圍遵循，以及完整 issue → PR 行為：隔離 profile 未登入。要驗證須在該隔離 profile 自行登入；不用複製原始 auth 檔。
- 兩個 Desktop App 的 GUI 安裝、picker、叫用及更新：本輪沒有啟動原 App 或操作原設定，CLI／app-server 的成功不能冒充 GUI 成功。
- Windows／Ubuntu 的真實 CLI 或 App：本機只有 macOS；六組 CI 只涵蓋打包與單元測試。
- 已登入的權限／企業 managed settings／不同 CPU 架構，以及 Claude Desktop WSL plugins（官方目前不支援）。
- 真實 GitHub tag 升版、回退、背景自動更新、正在執行中的 session reload：本輪僅測 GitHub 初次安裝及 loopback Git fixture 手動升版，不發布 tag／release。
- `0.1.1` 是暫存測試版本，repo 的 `release.json` 與產物版本仍為 `0.1.0`。
