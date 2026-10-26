# victorfu-skills

供 Codex 與 Claude Code 使用的共用工作流程來源。目前提供 **resolve-github-issue**：明確叫用後驗證 issue、標記進度、修正、測試、審查、commit、push 並建立 PR；唯讀要求仍只做唯讀工作。

Skill 名稱、標題與 Codex skill 顯示名稱都是 `resolve-github-issue`。**`victorfu-skills` 是 plugin 集合與 marketplace 名稱**，可持續加入其他 skills，不是 skill 的別名。Claude plugin 叫用會帶集合 namespace。

目前 `0.1.0` 是尚待發布的初始版本。下列 GitHub 安裝指令須等維護者提交檔案並發布對應 tag 後才能使用。本次建置沒有安裝、解除安裝、push、建立 release 或修改既有使用者設定。

## 單一來源與架構

```text
skills/resolve-github-issue/         唯一手動維護的 workflow
  SKILL.md                         共通 name、description 與完整流程
  references/github-workflow.md    保留原始共同文件的位元組
  agents/openai.yaml               Codex 顯示與 explicit-only policy
release.json                       唯一版本／集合 metadata 來源
requirements-dev.txt               建置相依套件
tools/build.py                    可重現產生與 --check
tools/test_build.py                暫存目錄內的回歸測試
dist/codex/                       產生的 Codex plugin
  .codex-plugin/plugin.json
  skills/、BUILD.json、GENERATED.md
dist/claude/                      產生的 Claude plugin
  .claude-plugin/plugin.json
  skills/、BUILD.json、GENERATED.md
.agents/plugins/marketplace.json  產生的 Codex catalog
.claude-plugin/marketplace.json    產生的 Claude catalog
.github/workflows/validate.yml    三種 OS 的建置／漂移檢查
docs/verification.md             查證與實際驗證紀錄
```

`dist/` 與兩份 marketplace 都須提交，**不要手改**。產生器自動列舉 `skills/`，同一 release 會包含全部 skills。新增 skill 時提供共通 frontmatter、`agents/openai.yaml` 及必要資源，再建置即可；目前整個集合採 explicit-only 政策。沒有空的 `scripts/`，`tools/` 只是 repo 建置工具，不是 skill 執行相依。

Claude 版僅在 frontmatter 增加 `disable-model-invocation: true`；正文、references 及其他資源保持位元組一致。Codex 以 `policy.allow_implicit_invocation: false` 控制。官方沒有保證 Codex 接受 Claude 專用欄位，因此不把「可能忽略未知欄位」當相容性契約。[Codex skills](https://learn.chatgpt.com/docs/build-skills)、[Claude skills](https://code.claude.com/docs/en/skills)

Codex 使用官方仍支援的 `.codex-plugin/plugin.json` 相容格式與 `skills: "./skills/"`；Claude 使用 `.claude-plugin/plugin.json` 與預設 `skills/`。雖然 Codex 文件提及 legacy Claude marketplace 支援，本 repo 使用兩份產生的 catalog，避免將不同平台的欄位／載入優先序當成可互換保證。沒有把根目錄 `plugin.json` 假設成兩邊通用。[Codex packaging](https://developers.openai.com/plugins/build/plugins)、[Claude manifest](https://code.claude.com/docs/en/plugins-reference)、[Claude marketplace](https://code.claude.com/docs/en/plugins/marketplace-reference)

## 開發與驗證（macOS／Linux／Windows）

需要 Git、Python 3.10+；Windows 建議 Python launcher 與 PowerShell 7。安裝後使用 skill 只需要客戶端、本機 git、可用的 GitHub connector 或已登入的 `gh`，不需要 Python 或額外模型 API key。Windows 需先依客戶端官方要求準備 shell／Git；WSL 與原生 Windows 是不同安裝環境。

macOS／Linux，於 repo 根目錄：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python tools/build.py
.venv/bin/python tools/build.py --check
.venv/bin/python -m unittest discover -s tools -p test_build.py -v
claude plugin validate dist/claude --strict
claude plugin validate .claude-plugin/marketplace.json --strict
git diff --check
```

Windows PowerShell，於 repo 根目錄；不用啟用 venv，也不用更改 execution policy：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe tools/build.py
.\.venv\Scripts\python.exe tools/build.py --check
.\.venv\Scripts\python.exe -m unittest discover -s tools -p test_build.py -v
claude plugin validate dist/claude --strict
claude plugin validate .claude-plugin/marketplace.json --strict
git diff --check
```

產生器不存時間戳或絕對路徑，`--check` 唯讀比對所有產物、額外殘留檔、版本、名稱、資源路徑、YAML 及叫用政策。`BUILD.json` 記錄來源 SHA-256，可辨認同一版本被不當重用的情形。`.gitattributes` 固定文字 LF，原始共用 reference 則保留其包含最後 CRLF 的原始位元組。執行建置會移除 `dist/` 中過期的產生檔；不要把個人檔案放在該目錄。

## 隔離的本機 symlink 測試

以下只在新建暫存專案建立連結，**不寫入 `~/.claude/skills`、`~/.codex/plugins/cache` 或原有兩份來源**。Claude 必須連向產生的 Claude 版，不能直接連到共通來源，否則缺少 explicit-only 欄位。

macOS／Linux，從本 repo 根目錄開始：

```sh
repo_path="$PWD"
trial_dir="$(mktemp -d)"
git init "$trial_dir"
mkdir -p "$trial_dir/.agents/skills" "$trial_dir/.claude/skills"
ln -s "$repo_path/skills/resolve-github-issue" "$trial_dir/.agents/skills/resolve-github-issue"
ln -s "$repo_path/dist/claude/skills/resolve-github-issue" "$trial_dir/.claude/skills/resolve-github-issue"
cd "$trial_dir"
# 新的設定目錄與 project-only 來源；可能需要在隔離環境重新登入。
CLAUDE_CONFIG_DIR="$trial_dir/claude-config" claude --setting-sources project
# 本次程序停用已知舊 plugin；仍須在 /skills 核對來源路徑。
codex -c 'plugins."github-issue-to-pr@personal".enabled=false'
```

Windows PowerShell，使用新的終端視窗，從 repo 根目錄開始：

```powershell
$repoPath = (Get-Location).Path
$trialPath = Join-Path ([System.IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $trialPath | Out-Null
git init $trialPath
New-Item -ItemType Directory -Path "$trialPath\.agents\skills", "$trialPath\.claude\skills" | Out-Null
New-Item -ItemType SymbolicLink -Path "$trialPath\.agents\skills\resolve-github-issue" -Target "$repoPath\skills\resolve-github-issue"
New-Item -ItemType SymbolicLink -Path "$trialPath\.claude\skills\resolve-github-issue" -Target "$repoPath\dist\claude\skills\resolve-github-issue"
Set-Location $trialPath
$env:CLAUDE_CONFIG_DIR = Join-Path $trialPath "claude-config"
claude --setting-sources project
codex -c 'plugins."github-issue-to-pr@personal".enabled=false'
```

Windows 建立 symbolic link 可能需要 Developer Mode 或管理權限；不自動修改系統設定。若被拒絕，將這兩個 `New-Item ... SymbolicLink` 改成 `Copy-Item -Recurse -Path <同一 Target> -Destination <同一 Path>`，但這是快照，每次修改後需在**新的測試目錄**重複複製。包本身不依賴 symlink。兩邊官方均支援 standalone skill 目錄 symlink；插件內跨根目錄連結另有邊界，故發布包不使用它。

上述 Claude 命令使用新的 `CLAUDE_CONFIG_DIR`，不沿用原本使用者目錄；Windows 的變數只在這個新終端程序生效，測試後關閉該視窗。受管設定仍可能加入其他 skill，須在 Claude `/skills`／`/context` 檢查。若仍有衝突，使用乾淨測試帳號，不複製憑證。Codex 的 session override 只排除上述已知舊 plugin，其他 user／admin skills 仍可能載入；請以 `/skills` 選擇新測試路徑，若無法分辨就用乾淨 OS 帳號，不以名稱猜測。不要在衝突尚未解決時測試寫入流程。

Codex 的來源變更通常自動偵測，未出現時重啟；Claude 的 standalone skill 變更可用 `/reload-skills`，symlink target 的熱更新與 references 變更一律以新 session 驗證較可靠。Claude 產生版每次來源修改後都須重跑 build。[Codex skills](https://learn.chatgpt.com/docs/build-skills)、[Claude skills](https://code.claude.com/docs/en/skills)、[Claude environment](https://code.claude.com/docs/en/env-vars)

## Plugin 完整載入測試

Standalone 測試不代表 manifest、namespace 或 marketplace 已驗證。Claude 可在新暫存專案從新 session 載入：

```sh
plugin_trial="$(mktemp -d)"
git init "$plugin_trial"
cd "$plugin_trial"
CLAUDE_CONFIG_DIR="$plugin_trial/claude-config" claude --setting-sources project --plugin-dir "$repo_path/dist/claude"
```

PowerShell 先以同樣的 GUID／`New-Item`／`git init` 步驟建立另一個沒有 `.claude/skills` 的測試專案，切換到該目錄，讓 `$env:CLAUDE_CONFIG_DIR` 指向其新的 `claude-config` 子目錄，再執行 `claude --setting-sources project --plugin-dir "$repoPath\dist\claude"`。只載入該次 session，無須註冊 marketplace；用 `/victorfu-skills:resolve-github-issue` 避免裸名稱撞到舊 standalone skill。內容變更後重新 build，再 `/reload-plugins` 或開新 session。

Codex 沒有在本次 CLI help 中提供等價的 `--plugin-dir`。完整測試需由你在乾淨帳號／測試環境選擇執行下列**會註冊並安裝**的指令（本次未執行）：

```sh
codex plugin marketplace add /absolute/path/to/skills
codex plugin add victorfu-skills@victorfu-skills
```

Windows 同樣以引號包住絕對路徑。也可透過 desktop Plugins Directory 選取 repo marketplace 安裝，然後開新 session；某些 desktop 版本需重啟應用程式。Codex 本機 plugin 會載入 cache 複本，不能當成來源 symlink 的即時更新。上述 CLI install 語法已用本機 `codex-cli 0.164.0 --help` 核對；實際安裝／刷新仍待驗證。[Codex packaging](https://developers.openai.com/plugins/build/plugins)、[Claude loading](https://code.claude.com/docs/en/plugins/loading)

## 從 GitHub marketplace 安裝

等待 `v0.1.0` 實際發布後，在你選擇的正式或隔離環境執行。以下是一般 shell 指令，PowerShell 亦適用；`#` 所在來源需加引號：

```sh
codex plugin marketplace add victorfu/skills --ref v0.1.0
codex plugin add victorfu-skills@victorfu-skills

claude plugin marketplace add "victorfu/skills#v0.1.0"
claude plugin install victorfu-skills@victorfu-skills
```

Codex 若版本尚無 `plugin add`，先查 `codex plugin --help`，使用官方 desktop plugin browser 完成安裝。不要改成手寫 cache／安裝登錄。不要使用 sparse checkout 只下載 catalog：catalog 引用的 `dist/` 必須一起取得。也不要用 raw marketplace JSON URL 安裝 Claude 本地相對路徑包。

明確叫用範例（在聊天輸入，不是 shell）：

```text
Codex：$resolve-github-issue 完整處理 https://github.com/OWNER/REPO/issues/123
Claude plugin：/victorfu-skills:resolve-github-issue 完整處理 https://github.com/OWNER/REPO/issues/123
Claude standalone：/resolve-github-issue 完整處理 OWNER/REPO 的 issue #123
唯讀：明確叫用上面的 skill，僅評估 issue #123，不修改程式或 GitHub 狀態。
```

Codex 若 picker 顯示集合前綴，選取 `victorfu-skills` 中的 `resolve-github-issue`，核對來源後使用其插入的 mention。編號必須有唯一且已核對的 repo 上下文；URL 必須核對 host、repo 與 issue 身分。貼 URL 不應自動啟動，完整叫用後則在授權範圍內連續完成。每次測試先用唯讀情境，不用真實 issue 驗證標籤／push 副作用。

## 日常修改、版本與發布

1. 只改 `skills/` 中的流程／資源；包 metadata 改 `release.json`，產生邏輯改 `tools/build.py`。修改生成器後也要跑測試。
2. 發布前更新 `release.json.version`（例如 `0.1.1`），重建、`--check`、單元測試、兩項 Claude 官方驗證及 `git diff --check`。檢查 diff 中兩平台正文一致。
3. 提交明確檔案，包括來源、`dist/`、兩份 catalog、工具、README 與驗證資料。檢查 staged diff、`git diff --cached --check`；不要夾帶 venv、暫存測試專案或使用者設定。
4. 三 OS CI 通過並完成實際客戶端 smoke test 後，才由維護者在該 commit 建立 `v<version>` tag。範例：`git tag -a v0.1.0 -m "victorfu-skills 0.1.0"`。以 `git show v0.1.0:release.json` 核對 tag 與版本一致。
5. 維護者明確選擇發布時才 push 該分支及 tag；GitHub Release 可選，不是 marketplace 必需。本次不 commit／tag／push。不要移動已發布 tag，也不要用同一版本發布不同內容。

建議一般使用者 **固定不可變 release tag**：catalog 與兩平台包都在同一 commit，容易重現與回退。branch 適合測試者，但可能拿到未驗證內容；每次可安裝更新仍需升版。commit pin 最精確但不易閱讀，且需 host 可取得該 SHA；tag 不是密碼學不可變保證，必要時另記完整 commit SHA。catalog 內的相對路徑不再另設 ref，避免 catalog 與 plugin 指向不同發布。

## 取得更新與回退

**追蹤 branch 的安裝**，當維護者已提高版本且發布：

```sh
codex plugin marketplace upgrade victorfu-skills
codex plugin list

claude plugin marketplace update victorfu-skills
claude plugin update victorfu-skills@victorfu-skills
claude plugin list --json
```

Codex `upgrade` 官方 CLI help 保證刷新 Git marketplace snapshot；官方文件也說刷新可更新已配置 plugin，但不同客戶端是否立即換用包仍須實測。開新 session／重啟 desktop，核對實際載入版本；若仍舊版，從官方 Plugins Directory 更新或重新選取安裝，再核對。不保證自動更新週期，不宣稱僅 `git pull` 或 `upgrade` 就完成載入切換。

Claude `marketplace update` 更新 catalog，另跑 `plugin update` 才明確更新指定 plugin。執行中的 session 用 `/reload-plugins` 或重啟。第三方 marketplace 自動更新預設關閉，可由使用者在 `/plugin` 的 Marketplaces 頁啟用；已釘選 tag 的 auto-update 不會跳到新 tag。manifest 版本未變時，遠端 commit 變更也不刷新既有 cache。[Claude updates](https://code.claude.com/docs/en/discover-plugins)、[Claude versions](https://code.claude.com/docs/en/plugins/loading)

**固定 tag 的安裝更新／回退**需要切換 marketplace ref，單純 refresh 不會改 ref。先記下現有版本、ref 與必要設定；此集合無 MCP／hooks／資料服務。CLI 對同名 marketplace 重新 add 的取代行為未在本次實測，因此採明確移除、重新註冊與安裝流程，僅限本新集合：

```sh
# Codex：選擇切換時才執行；移除本集合會移除其安裝 cache。
codex plugin remove victorfu-skills@victorfu-skills
codex plugin marketplace remove victorfu-skills
codex plugin marketplace add victorfu/skills --ref v0.1.1
codex plugin add victorfu-skills@victorfu-skills

# Claude：remove marketplace 會解除安裝該 marketplace 的所有 plugins。
claude plugin marketplace remove victorfu-skills
claude plugin marketplace add "victorfu/skills#v0.1.1"
claude plugin install victorfu-skills@victorfu-skills
```

回退時把兩個 ref 換成先前已發布且驗證的 tag，例如 `v0.1.0`；不修改來源中的版本或 cache。若你的客戶端提供直接編輯 marketplace ref 的官方 UI，可用該方式後更新／重載，仍須核對版本。上述是使用者未來操作說明，本次沒有執行。

**確認目前使用版本**：先 `codex plugin marketplace list`／`claude plugin marketplace list` 核對來源與 ref，接著在 plugin list 或 UI 核對 `victorfu-skills` 版本；從 skill picker／session 診斷查實際載入路徑，唯讀查看該包 manifest 與 `BUILD.json` 的版本／hash。cache 目錄名不一定等於發布版本（Codex 本地包可能叫 `local`）。開新 session 再確認，不能只看開發 checkout 的 `release.json`。若客戶端不顯示 ref／載入路徑，須使用其診斷功能，不能推測已更新。

symlink 開發讀取來源，`git pull` 改到該來源後可重載（Claude 需先重新 build）；GitHub 安裝則是客戶端管理的 snapshot／cache，開發 checkout 的 `git pull` 不會改它。Claude 本地 `--plugin-dir`／本地路徑 marketplace 可原地載入；Codex 本地 plugin 依官方文件會複製到 cache，更新後重啟並驗證，不能直接改 cache。

## 舊版遷移與重複載入

本 repo 不操作這兩個受保護目錄，也不以解除安裝舊 plugin 來清除它們：

- `~/.claude/skills/resolve-github-issue/`
- `~/.codex/plugins/cache/personal/github-issue-to-pr/0.1.0/`

先完成隔離測試，再自行選擇正式遷移。Claude 可先用 namespaced `/victorfu-skills:resolve-github-issue` 分辨新包；舊 standalone 仍可能被隱式選取，因此名稱前綴本身不是完全停用。若要求兩份來源永久保持原位且不修改設定，就用隔離帳號／設定目錄，無法同時保證預設使用者環境不發現舊版。若日後另行允許設定變更，可依 Claude 官方 `skillOverrides` 將 standalone `resolve-github-issue` 設為 `off` 並驗證；該設定不影響 plugin skills；不要改舊 `SKILL.md` 或搬走來源。

Codex 日後可透過官方 plugin 管理介面 **停用** `github-issue-to-pr@personal`（不解除安裝以免刪 cache），再安裝新集合。檢查 repo／user／admin 設定是否另行啟用舊 plugin。若目前只做測試，使用前述 session `-c` override。新 plugin 不會自動繼承舊 plugin 的註冊、cache 或設定。

排查時列出所有同名 skill 的來源路徑、plugin id、marketplace、版本；Codex 同名技能不合併，Claude standalone 有優先序而 plugin 有 namespace。保留原始來源及必要設定紀錄；不要 `rm -rf` cache、不要手改安裝登錄、不要把其他版本內容覆蓋進 `0.1.0`。

## 官方依據與驗證限制

查閱日期：2026-10-26。完整證據、工具版本與未測範圍見 [驗證紀錄](docs/verification.md)。核心官方文件：

- [Codex skills／symlink／openai.yaml](https://learn.chatgpt.com/docs/build-skills)
- [Codex plugin／marketplace／cache](https://developers.openai.com/plugins/build/plugins)
- [Claude skills／frontmatter／explicit-only／symlink](https://code.claude.com/docs/en/skills)
- [Claude manifest 與官方驗證器](https://code.claude.com/docs/en/plugins-reference)
- [Claude marketplace schema](https://code.claude.com/docs/en/plugins/marketplace-reference)
- [Claude marketplace hosting／ref／版本](https://code.claude.com/docs/en/plugins/host-marketplace)
- [Claude 安裝與更新](https://code.claude.com/docs/en/discover-plugins)
- [Claude loading／cache／名稱衝突](https://code.claude.com/docs/en/plugins/loading)
- [Claude 環境變數與隔離設定目錄](https://code.claude.com/docs/en/env-vars)

目前僅在 macOS 執行靜態驗證及打包測試。Linux／Windows CI 已配置但尚未在遠端執行；沒有真實安裝、模型叫用、GitHub 寫入或更新／回退端到端測試。官方 schema／CLI help 相符不等於客戶端行為已驗證。未決事項包含 managed settings、不同版本熱載入、Windows symlink 權限、Codex marketplace snapshot 到 plugin cache 的更新時機。官方公共 plugin directory 的授權／圖示／審核要求不屬於此 GitHub marketplace 交付，未自行決定 repo 授權條款。
