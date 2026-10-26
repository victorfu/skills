# 參與開發

## 專案結構

```text
skills/<name>/                     唯一手寫的來源
  SKILL.md                         frontmatter 只放 name、description，正文是完整流程
  references/                      skill 引用的參考文件
  agents/openai.yaml               Codex 專用的顯示名稱與叫用政策
release.json                       版本與 plugin metadata
tools/build.py                     產生 dist/ 與兩份 marketplace；--check 只比對不寫入
tools/test_build.py                打包回歸測試（在暫存目錄執行）
dist/claude/、dist/codex/          產生的 plugin（要 commit，不要手改）
.claude-plugin/marketplace.json    產生的 Claude Code marketplace
.agents/plugins/marketplace.json   產生的 Codex marketplace
docs/verification.md               查證與驗證紀錄
```

兩個平台的產物只有兩處不同：

- **Claude Code**：`SKILL.md` frontmatter 多一行 `disable-model-invocation: true`，並且不含 `agents/`。
- **Codex**：以 `agents/openai.yaml` 的 `policy.allow_implicit_invocation: false` 限制只能明確叫用。

正文與 references 在兩邊位元組一致。`skills/` 下以 `.` 開頭的檔案（例如 `.DS_Store`）不會被打包。

## 環境設定

需要 Git 與 Python 3.10 以上。

macOS／Linux：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

Windows PowerShell（不需啟用 venv）：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

以下指令以 macOS／Linux 為例；Windows 請把 `.venv/bin/python` 換成 `.\.venv\Scripts\python.exe`。

## 建置與測試

每次修改 `skills/`、`release.json` 或 `tools/` 後：

```sh
.venv/bin/python tools/build.py
.venv/bin/python tools/build.py --check
.venv/bin/python -m unittest discover -s tools -p test_build.py -v
claude plugin validate dist/claude --strict
claude plugin validate .claude-plugin/marketplace.json --strict
```

`build.py` 會移除 `dist/` 中不再需要的檔案，不要把其他檔案放進 `dist/`。CI 會在 Ubuntu、macOS、Windows 搭配 Python 3.10 與 3.12 執行 `--check` 與單元測試，產物沒有重新建置就會失敗。

## 本機試用

建議在一個暫存的測試專案中試用，避免和你平常的安裝混在一起。需要完全隔離設定時，可以把 `CLAUDE_CONFIG_DIR` 指向新的目錄（可能需要重新登入）。

**Claude Code**：直接載入產生的 plugin，只對該次 session 生效。

```sh
claude --plugin-dir /absolute/path/to/skills/dist/claude
```

叫用 `/victorfu-skills:resolve-github-issue`。修改來源後重新執行 `build.py`，再執行 `/reload-plugins` 或開新 session。

**Codex**：從本機路徑註冊 marketplace 並安裝。

```sh
codex plugin marketplace add /absolute/path/to/skills
codex plugin add victorfu-skills@victorfu-skills
```

Codex 會把 plugin 複製到自己的 cache，修改來源後要重新安裝，並重新啟動 Codex。

用真實 issue 測試前，先用「只評估，不要修改」的唯讀模式確認行為；完整流程請在可以隨意建立分支與 PR 的測試 repo 上進行。

## 新增 skill

1. 建立 `skills/<name>/SKILL.md`，frontmatter 只能有 `name`（必須等於目錄名稱，小寫加連字號）與 `description`。
2. 建立 `skills/<name>/agents/openai.yaml`，設定 `interface.display_name`、`short_description`（25 到 64 字）、包含 `$<plugin-name>:<name>` 的 `default_prompt`，以及 `policy.allow_implicit_invocation: false`。`<plugin-name>` 必須與 `release.json` 的 `name` 相同；本 repo 使用 `$victorfu-skills:<name>`，建置會檢查完整叫用名稱。
3. `SKILL.md` 正文中的相對連結必須指向 skill 目錄內實際存在的檔案。
4. 執行建置與測試；`build.py` 會自動納入 `skills/` 下的所有 skill。

## 發布新版本

1. 更新 `release.json` 的 `version`（SemVer，例如 `0.1.1`）。Claude Code 只有在版本號改變時才會更新已安裝的 plugin，所以每次發布都要升版。
2. 執行建置與測試，確認 `--check` 通過。
3. Commit 所有變更（包含 `dist/` 與兩份 marketplace），push 並等 CI 通過。
4. 在該 commit 建立 tag 並 push：

   ```sh
   git tag -a v0.1.1 -m "victorfu-skills 0.1.1"
   git push origin v0.1.1
   ```

不要移動已發布的 tag，也不要用同一個版本號發布不同內容。
