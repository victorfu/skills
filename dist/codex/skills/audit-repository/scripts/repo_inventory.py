#!/usr/bin/env python3
"""Create and maintain a deterministic review ledger for repository bug audits.

This helper never edits the target repository. It inventories tracked and untracked,
non-ignored files for Git repositories, classifies review scope, and records which
files were actually reviewed or explicitly excluded after confirmation.

Anything that could hide a file from the audit is either fatal (a Git failure, a
directory that cannot be listed) or an entry that blocks completion (a dependency,
build-output or cache directory skipped in non-Git mode, text in an unexpected
encoding, an empty inventory). Only version-control metadata (.git, .hg, .svn) is
skipped without an entry.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

LEDGER_VERSION = 1
LEDGER_FILE = "ledger.json"

SOURCE_EXTENSIONS = {
    ".asm", ".astro", ".bash", ".bat", ".c", ".cc", ".cfg", ".clj",
    ".cljs", ".cmake", ".cmd", ".conf", ".cpp", ".cs", ".css", ".cu",
    ".cuh", ".cxx", ".dart", ".el", ".erl", ".ex", ".exs", ".fish",
    ".fs", ".fsx", ".go", ".gql", ".graphql", ".groovy", ".h", ".hcl",
    ".hh", ".hpp", ".hrl", ".html", ".htm", ".ini", ".java", ".jl",
    ".js", ".jsx", ".json", ".json5", ".kt", ".kts", ".less", ".lua",
    ".m", ".mm", ".mjs", ".mts", ".nix", ".php", ".pl", ".pm", ".proto",
    ".ps1", ".py", ".pyi", ".r", ".rb", ".rs", ".sass", ".scala", ".sc",
    ".scss", ".sh", ".sol", ".sql", ".svelte", ".swift", ".tf", ".tfvars",
    ".thrift", ".toml", ".ts", ".tsx", ".vue", ".xml", ".xsl", ".xslt",
    ".yaml", ".yml", ".zig", ".zsh",
}

CONTEXT_EXTENSIONS = {
    ".adoc", ".md", ".mdx", ".rst",
}

BINARY_EXTENSIONS = {
    ".7z", ".a", ".avi", ".bin", ".bmp", ".class", ".db", ".dll", ".dmg",
    ".doc", ".docx", ".eot", ".exe", ".gif", ".gz", ".ico", ".jar", ".jpeg",
    ".jpg", ".lib", ".lockb", ".mov", ".mp3", ".mp4", ".o", ".obj", ".otf",
    ".parquet", ".pdf", ".png", ".pyc", ".pyo", ".rar", ".so", ".sqlite",
    ".sqlite3", ".tar", ".tgz", ".ttf", ".wasm", ".webm", ".webp", ".woff",
    ".woff2", ".xls", ".xlsx", ".xz", ".zip",
}

SPECIAL_REVIEW_FILENAMES = {
    "build.gradle", "build.gradle.kts", "build.sbt", "CMakeLists.txt", "Containerfile",
    "Dockerfile", "Gemfile", "GNUmakefile", "Jenkinsfile", "Justfile", "Makefile",
    "Podfile", "Procfile", "Rakefile", "Tiltfile", "Vagrantfile", "WORKSPACE",
    "WORKSPACE.bazel", "meson.build", "package.json", "pyproject.toml", "setup.cfg",
    "setup.py", "tox.ini",
}

LOCKFILE_NAMES = {
    "bun.lock", "bun.lockb", "Cargo.lock", "composer.lock", "Gemfile.lock",
    "go.sum", "gradle.lockfile", "npm-shrinkwrap.json", "package-lock.json",
    "Pipfile.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock", "yarn.lock",
}

VENDOR_DIR_NAMES = {
    ".bundle", ".m2", ".pnpm-store", ".venv", "bower_components", "carthage",
    "deps", "node_modules", "pods", "third_party", "third-party", "vendor", "venv",
    "__pypackages__",
}

GENERATED_DIR_NAMES = {
    ".cache", ".gradle", ".next", ".nuxt", ".parcel-cache", ".svelte-kit",
    "build", "coverage", "dist", "generated", "gen", "htmlcov", "out", "target",
}

VCS_DIR_NAMES = {".git", ".hg", ".svn"}

NON_GIT_PRUNE_DIRS = VENDOR_DIR_NAMES | GENERATED_DIR_NAMES | VCS_DIR_NAMES | {"__pycache__"}

# Checked against the first non-empty lines only; a phrase deeper in a file is prose or data.
GENERATED_PATTERN = re.compile(
    r"@generated\b|auto-?generated|automatically generated|code generated (?:by|from)"
    r"|generated (?:by|from|file)\b|\bdo not edit\b",
    re.IGNORECASE,
)
GENERATED_HEADER_LINES = 5

MINIFIED_SUFFIXES = (".min.js", ".min.css", ".bundle.js", ".bundle.css", ".map")

# UTF-32 first: its little-endian BOM starts with the UTF-16 one.
TEXT_BOMS = (
    (b"\xff\xfe\x00\x00", "utf-32"),
    (b"\x00\x00\xfe\xff", "utf-32"),
    (b"\xff\xfe", "utf-16"),
    (b"\xfe\xff", "utf-16"),
)

# Coverage is complete only when every entry has one of these; anything else blocks.
TERMINAL_STATUSES = {"reviewed", "excluded-confirmed", "context-reviewed", "context", "excluded"}
OPEN_STATUSES = {"pending", "pending-decision", "unreadable"}

LIST_FILES = {
    "review-list.txt": lambda item: item["status"] == "pending",
    "decision-list.txt": lambda item: item["status"] == "pending-decision",
    "unreadable-list.txt": lambda item: item["status"] == "unreadable",
    "context-list.txt": lambda item: item["scope"] == "context",
    "excluded-list.txt": lambda item: item["status"] == "excluded",
}

# Paths are stored as text; surrogateescape round-trips names that are not valid UTF-8.
PATH_ERRORS = "surrogateescape"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def notice(message: str) -> None:
    print(message, file=sys.stderr)


# Inherited from a hook or `rebase --exec`, these would point Git at another repository or index.
GIT_REDIRECT_VARIABLES = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_PREFIX")


def git_environment() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key not in GIT_REDIRECT_VARIABLES}
    # LC_ALL=C keeps Git's messages in English, so they can be told apart below.
    # GIT_OPTIONAL_LOCKS=0 stops `git status` from refreshing .git/index in the target.
    env.update({"LC_ALL": "C", "LANGUAGE": "C", "GIT_OPTIONAL_LOCKS": "0"})
    return env


def run_git(repo: Path, args: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
        env=git_environment(),
    )


def same_directory(first: Path, second: Path) -> bool:
    # Identity, not spelling: on a case-insensitive filesystem two spellings name one directory.
    try:
        return os.path.samefile(first, second)
    except OSError:
        return False


def git_text(data: bytes) -> str:
    # Git prints paths as bytes, normally UTF-8. os.fsdecode would raise on Windows for anything else.
    return data.decode("utf-8", errors=PATH_ERRORS)


def git_stderr(exc: subprocess.CalledProcessError) -> str:
    return git_text(exc.stderr or b"").strip()


def has_git_marker(path: Path) -> bool:
    return any((candidate / ".git").exists() for candidate in (path, *path.parents))


def git_root(path: Path) -> Path | None:
    """Return the work-tree root, or None only when the path is plainly not in a Git repository.

    Every other Git failure is fatal: falling back to a directory walk would drop
    .gitignore handling and skip whole directories without anyone noticing.
    """
    try:
        result = run_git(path, ["rev-parse", "--show-toplevel"])
    except FileNotFoundError:
        if has_git_marker(path):
            raise SystemExit("git is not available, but the target is inside a Git repository; put git on PATH and retry")
        return None
    except subprocess.CalledProcessError as exc:
        message = git_stderr(exc)
        if "not a git repository" in message.lower() and not has_git_marker(path):
            return None
        raise SystemExit(f"git could not inspect the target, so no inventory was created: {message or exc}")
    return Path(git_text(result.stdout).strip()).resolve()


def resolve_target(requested: Path) -> tuple[Path, bool]:
    """Decide which directory is inventoried and whether Git lists its files."""
    top = git_root(requested)
    if top is None:
        return requested, False
    if same_directory(top, requested):
        return top, True
    # Ask Git where the request sits inside the work tree; comparing path strings
    # breaks when the request is spelled in another letter case or Unicode form.
    prefix = git_text(run_git(requested, ["rev-parse", "--show-prefix"]).stdout).strip().rstrip("/")
    if not prefix:
        raise SystemExit(f"git reports the work tree {top}, which does not contain {requested}; no inventory was created")
    if run_git(top, ["check-ignore", "-q", "--", prefix], check=False).returncode == 0:
        notice(f"note: {requested} is ignored by the enclosing Git repository {top}; inventorying it as a non-Git directory")
        return requested, False
    notice(f"note: --repo is inside a Git repository; inventorying its root {top}")
    return top, True


def is_within(child: Path, parent: Path) -> bool:
    """True when child is parent or lies under it; child need not exist yet."""
    return any(same_directory(candidate, parent) for candidate in (child, *child.parents))


def git_paths(root: Path) -> tuple[list[str], list[str]]:
    result = run_git(root, ["ls-files", "-z", "--cached", "--others", "--exclude-standard"])
    paths = sorted({git_text(item) for item in result.stdout.split(b"\0") if item})
    warnings = [line for line in git_text(result.stderr).splitlines() if line.strip()]
    # Git exits 0 but only warns when it cannot open a directory while looking for
    # untracked files. An incomplete traversal must not produce a ledger.
    unlisted = [line for line in warnings if "could not open directory" in line]
    if unlisted:
        raise SystemExit("git could not list every directory, so no inventory was created:\n  " + "\n  ".join(unlisted))
    return paths, warnings


def non_git_paths(root: Path) -> tuple[list[str], list[dict[str, str]]]:
    files: list[str] = []
    pruned: list[dict[str, str]] = []

    def fail_on_scan_error(error: OSError) -> None:
        # An incomplete traversal must not produce a successful coverage ledger.
        raise error

    for current, dirs, names in os.walk(root, topdown=True, followlinks=False, onerror=fail_on_scan_error):
        current_path = Path(current)
        kept_dirs: list[str] = []
        for dirname in sorted(dirs):
            full = current_path / dirname
            rel = full.relative_to(root).as_posix()
            if full.is_symlink():
                files.append(rel)
            elif dirname.lower() in NON_GIT_PRUNE_DIRS:
                pruned.append({"path": rel + "/", "reason": "dependency, generated-output, cache, or VCS directory"})
            else:
                kept_dirs.append(dirname)
        dirs[:] = kept_dirs
        for name in sorted(names):
            full = current_path / name
            files.append(full.relative_to(root).as_posix())
    return sorted(files), pruned


def pruned_directory_entry(pruned: dict[str, str]) -> dict[str, Any] | None:
    """Every skipped directory needs a decision, except version-control metadata."""
    name = pruned["path"].rstrip("/").rsplit("/", 1)[-1].lower()
    if name in VCS_DIR_NAMES:
        return None
    return {
        "path": pruned["path"],
        "bytes": None,
        "kind": "pruned-directory",
        "scope": "decision",
        "status": "pending-decision",
        "reason": "directory was not inventoried in non-Git mode; confirm it is third-party, generated or cache "
                  "output, or review its files, before marking it",
    }


def probe_file(path: Path) -> tuple[bytes | None, OSError | None]:
    try:
        with path.open("rb") as handle:
            return handle.read(8192), None
    except OSError as exc:
        return None, exc


def text_bom(sample: bytes) -> str | None:
    for bom, encoding in TEXT_BOMS:
        if sample.startswith(bom):
            return encoding
    return None


def looks_like_wide_text(sample: bytes) -> bool:
    """UTF-16/32 text without a BOM: NUL bytes fill one byte position and not the other."""
    even, odd = sample[0::2], sample[1::2]
    if not even or not odd:
        return False
    ratios = sorted((even.count(0) / len(even), odd.count(0) / len(odd)))
    # Zero-filled or mostly-zero binary data has NULs in both positions.
    return ratios[1] >= 0.6 and ratios[0] <= 0.55


def has_text_name(name: str, suffix: str) -> bool:
    lower = name.lower()
    return (suffix in SOURCE_EXTENSIONS or suffix in CONTEXT_EXTENSIONS or name in SPECIAL_REVIEW_FILENAMES
            or lower.startswith(("dockerfile", "makefile")))


def generated_header(sample: bytes) -> bool:
    text = sample.decode("utf-8", errors="ignore")
    lines = [line for line in text.splitlines() if line.strip()][:GENERATED_HEADER_LINES]
    return any(GENERATED_PATTERN.search(line) for line in lines)


def path_has_dir(path: Path, names: set[str]) -> bool:
    return any(part.lower() in names for part in path.parts[:-1])


def classify(root: Path, rel_path: str) -> dict[str, Any]:
    full = root / rel_path
    rel = Path(rel_path)
    name = rel.name
    lower_name = name.lower()
    suffix = rel.suffix.lower()

    try:
        info = full.lstat()
    except OSError as exc:
        return {
            "path": rel_path,
            "bytes": None,
            "kind": "unreadable",
            "scope": "review",
            "status": "unreadable",
            "reason": f"lstat failed: {exc}",
        }

    if stat.S_ISLNK(info.st_mode):
        try:
            target = os.readlink(full)
        except OSError:
            target = "<unreadable>"
        return {
            "path": rel_path,
            "bytes": info.st_size,
            "kind": "symlink",
            "scope": "decision",
            "status": "pending-decision",
            "reason": f"symlink target not followed automatically: {target}",
        }

    if full.is_dir():
        kind = "submodule" if (full / ".git").exists() else "directory-entry"
        return {
            "path": rel_path,
            "bytes": 0,
            "kind": kind,
            "scope": "decision",
            "status": "pending-decision",
            "reason": "Git index entry resolves to a directory; inspect before excluding",
        }

    if not stat.S_ISREG(info.st_mode):
        return {
            "path": rel_path,
            "bytes": info.st_size,
            "kind": "special-file",
            "scope": "excluded",
            "status": "excluded",
            "reason": "not a regular file",
        }

    record: dict[str, Any] = {"path": rel_path, "bytes": info.st_size}
    sample, read_error = probe_file(full)
    if read_error is not None or sample is None:
        record.update({
            "kind": "unreadable",
            "scope": "review",
            "status": "unreadable",
            "reason": f"read failed: {read_error}",
        })
        return record

    is_context_doc = suffix in CONTEXT_EXTENSIONS
    encoding = text_bom(sample)
    # UTF-16/32 source contains NUL bytes. Keep BOM-marked files visible for an
    # explicit encoding/scope decision instead of silently excluding them.
    if encoding is not None and suffix not in BINARY_EXTENSIONS:
        record.update({
            "kind": "encoded-text",
            "scope": "decision",
            "status": "pending-decision",
            "encoding": encoding,
            "reason": f"{encoding.upper()} BOM detected; decode and confirm review scope before excluding",
        })
        return record
    if suffix in BINARY_EXTENSIONS:
        record.update({
            "kind": "binary",
            "scope": "excluded",
            "status": "excluded",
            "reason": "binary file; record presence but do not line-review",
        })
        return record
    if b"\0" in sample:
        # UTF-16 or UTF-32 text without a BOM also contains NUL bytes, so neither a text
        # name nor the byte pattern of wide text is excluded on that evidence alone.
        if has_text_name(name, suffix) or looks_like_wide_text(sample):
            record.update({
                "kind": "binary-or-encoded-text",
                "scope": "decision",
                "status": "pending-decision",
                "reason": "contains NUL bytes but has a text name or the byte pattern of UTF-16/UTF-32 text "
                          "without a BOM. Inspect before excluding",
            })
        else:
            record.update({
                "kind": "binary",
                "scope": "excluded",
                "status": "excluded",
                "reason": "binary file; record presence but do not line-review",
            })
        return record

    if path_has_dir(rel, VENDOR_DIR_NAMES):
        record.update({
            "kind": "vendored-or-dependency",
            "scope": "decision",
            "status": "pending-decision",
            "reason": "path appears vendored; confirm whether it is authoritative/shipped before excluding",
        })
        return record

    # Before the generated check: lockfile headers say "autogenerated", and they are context.
    if name in LOCKFILE_NAMES:
        record.update({
            "kind": "lockfile",
            "scope": "context",
            "status": "context",
            "reason": "version/context evidence; inspect relevant entries rather than line-reviewing as source",
        })
        return record

    # Documentation quotes these phrases; only code and config headers count as evidence.
    header_says_generated = not is_context_doc and generated_header(sample)
    if path_has_dir(rel, GENERATED_DIR_NAMES) or lower_name.endswith(MINIFIED_SUFFIXES) or header_says_generated:
        record.update({
            "kind": "generated-or-built",
            "scope": "decision",
            "status": "pending-decision",
            "reason": "path/header appears generated or built; confirm source-of-truth and shipping role before excluding",
        })
        return record

    parts_lower = {part.lower() for part in rel.parts}
    if ".github" in parts_lower and ("workflows" in parts_lower or "actions" in parts_lower):
        kind = "ci"
    elif any(part in {"test", "tests", "spec", "specs", "__tests__"} for part in parts_lower):
        kind = "test"
    elif any(part in {"migration", "migrations", "schema", "schemas", "db"} for part in parts_lower):
        kind = "migration-or-schema"
    elif name in SPECIAL_REVIEW_FILENAMES:
        kind = "build-or-manifest"
    elif lower_name.startswith("dockerfile") or lower_name.startswith("makefile"):
        kind = "build-or-manifest"
    elif suffix in SOURCE_EXTENSIONS:
        kind = "source-or-config"
    elif is_context_doc or lower_name in {"license", "notice", "readme", "changelog"}:
        record.update({
            "kind": "documentation-or-context",
            "scope": "context",
            "status": "context",
            "reason": "use for intended behavior and setup context; not counted as executable-code coverage",
        })
        return record
    else:
        kind = "unknown-text"

    record.update({
        "kind": kind,
        "scope": "review",
        "status": "pending",
        "reason": "first-party text file that may affect runtime, tests, build, deployment, or data behavior",
    })
    return record


def git_metadata(root: Path) -> tuple[dict[str, Any], list[str]]:
    """Describe the checkout. A value Git could not report is None, never a plausible default."""
    problems: list[str] = []

    def text(args: Sequence[str]) -> str | None:
        try:
            return git_text(run_git(root, args).stdout).strip() or None
        except subprocess.CalledProcessError as exc:
            problems.append(f"git {' '.join(args)} failed: {git_stderr(exc) or exc}")
            return None

    # An unborn branch has no commit yet; that is a state, not a failure.
    has_commit = run_git(root, ["rev-parse", "--verify", "-q", "HEAD"], check=False).returncode == 0
    dirty: bool | None = None
    entries: int | None = None
    try:
        status = run_git(root, ["status", "--porcelain=v1", "-z"]).stdout
        dirty = bool(status)
        entries = len([part for part in status.split(b"\0") if part])
    except subprocess.CalledProcessError as exc:
        problems.append(f"git status failed, so the working-tree state is unknown: {git_stderr(exc) or exc}")

    metadata = {
        "is_git_repository": True,
        "commit": text(["rev-parse", "HEAD"]) if has_commit else None,
        "branch": text(["branch", "--show-current"]),
        "dirty": dirty,
        "status_entry_count": entries,
    }
    return metadata, problems


def write_text(path: Path, text: str) -> None:
    # newline="\n" keeps the files identical on every platform.
    with path.open("w", encoding="utf-8", errors=PATH_ERRORS, newline="\n") as handle:
        handle.write(text)


def write_text_lists(out: Path, ledger: dict[str, Any]) -> None:
    for filename, belongs in LIST_FILES.items():
        write_text(out / filename, "".join(f"{item['path']}\n" for item in ledger["files"] if belongs(item)))


def save_ledger(out: Path, ledger: dict[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    target = out / LEDGER_FILE
    temp = out / (LEDGER_FILE + ".tmp")
    try:
        write_text(temp, json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    write_text_lists(out, ledger)


def load_ledger(out: Path) -> dict[str, Any]:
    target = out / LEDGER_FILE
    if not target.is_file():
        raise SystemExit(f"ledger not found: {target}")
    try:
        ledger = json.loads(target.read_text(encoding="utf-8", errors=PATH_ERRORS))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot read ledger: {exc}") from exc
    if not isinstance(ledger, dict) or ledger.get("version") != LEDGER_VERSION:
        version = ledger.get("version") if isinstance(ledger, dict) else None
        raise SystemExit(f"unsupported ledger version: {version!r}")
    return ledger


def discard_previous_ledger(out: Path) -> None:
    """Remove an earlier ledger first, so a failed create cannot leave it reporting complete coverage.

    Only a directory that holds a ledger this helper wrote is touched: a file that merely
    shares the name, for instance inside a target repository, is left alone.
    """
    previous = out / LEDGER_FILE
    try:
        ledger = json.loads(previous.read_text(encoding="utf-8", errors=PATH_ERRORS))
    except (OSError, ValueError):
        return
    if not (isinstance(ledger, dict) and ledger.get("version") == LEDGER_VERSION and "repo_root" in ledger):
        return
    notice(f"note: replacing the existing ledger in {out}; its marks are discarded")
    for name in (LEDGER_FILE, *LIST_FILES):
        (out / name).unlink(missing_ok=True)


def status_summary(ledger: dict[str, Any]) -> dict[str, Any]:
    files = ledger["files"]
    statuses = Counter(item["status"] for item in files)
    scopes = Counter(item["scope"] for item in files)
    kinds = Counter(item["kind"] for item in files)
    pending = statuses.get("pending", 0) + statuses.get("pending-decision", 0)
    incomplete = sum(count for status, count in statuses.items() if status not in TERMINAL_STATUSES)
    review = [item for item in files if item["scope"] == "review"]
    return {
        "total_inventory_entries": len(files),
        "by_status": dict(sorted(statuses.items())),
        "by_scope": dict(sorted(scopes.items())),
        "by_kind": dict(sorted(kinds.items())),
        "pending_review_or_decision": pending,
        "unreadable": statuses.get("unreadable", 0),
        "unknown_statuses": sorted(set(statuses) - TERMINAL_STATUSES - OPEN_STATUSES),
        # Excluding a review-scope file is allowed with a note, and stays visible here.
        "review_scope": {
            "total": len(review),
            "reviewed": sum(item["status"] == "reviewed" for item in review),
            "excluded_confirmed": sum(item["status"] == "excluded-confirmed" for item in review),
        },
        "empty_inventory": not files,
        # An inventory with no entries is a failed inventory, never a finished audit.
        "coverage_complete": bool(files) and incomplete == 0,
    }


def command_create(args: argparse.Namespace) -> int:
    requested = Path(args.repo).expanduser().resolve()
    if not requested.exists() or not requested.is_dir():
        raise SystemExit(f"repository directory does not exist: {requested}")

    out = Path(args.out).expanduser().resolve()
    # Before anything that can fail: the old ledger must not outlive a failed inventory.
    discard_previous_ledger(out)
    root, is_git = resolve_target(requested)
    if is_within(out, root):
        raise SystemExit("--out must be outside the target repository to preserve read-only auditing")

    warnings: list[str] = []
    pruned: list[dict[str, str]] = []
    extra: list[dict[str, Any]] = []
    if is_git:
        paths, warnings = git_paths(root)
        metadata, problems = git_metadata(root)
        warnings += problems
    else:
        paths, pruned = non_git_paths(root)
        extra = [entry for entry in map(pruned_directory_entry, pruned) if entry]
        metadata = {"is_git_repository": False, "commit": None, "branch": None, "dirty": None}

    files = sorted([classify(root, rel_path) for rel_path in paths] + extra, key=lambda item: item["path"])
    ledger: dict[str, Any] = {
        "version": LEDGER_VERSION,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "repo_root": str(root),
        "git": metadata,
        "inventory_warnings": warnings,
        "non_git_pruned_directories": pruned,
        "files": files,
    }
    save_ledger(out, ledger)

    notice(f"repository root: {root}")
    notice(f"inventory mode: {'git' if is_git else 'non-git directory walk (.gitignore is not applied)'}")
    for line in warnings:
        notice(f"git warning: {line}")
    if pruned:
        notice("directories not inventoried: " + ", ".join(item["path"] for item in pruned))
    if not files:
        notice("warning: the inventory is empty; status will report incomplete coverage")
    print(json.dumps(status_summary(ledger), ensure_ascii=False, indent=2))
    return 0


def split_lines(text: str) -> list[str]:
    # Only LF and CRLF end a path; str.splitlines would also split on form feeds and similar.
    return [line for line in (raw.rstrip("\r") for raw in text.split("\n")) if line]


def read_paths(args: argparse.Namespace) -> list[str]:
    paths: list[str] = list(args.path or [])
    if args.paths_file:
        paths.extend(split_lines(Path(args.paths_file).read_text(encoding="utf-8", errors=PATH_ERRORS)))
    if args.stdin:
        # Read bytes: the locale's default encoding would garble non-ASCII paths.
        paths.extend(split_lines(sys.stdin.buffer.read().decode("utf-8", errors=PATH_ERRORS)))
    # Preserve order while removing duplicates.
    return list(dict.fromkeys(paths))


def read_failure(root: Path, item: dict[str, Any]) -> str | None:
    full = root / item["path"]
    try:
        if full.is_dir():
            os.listdir(full)
        else:
            with full.open("rb") as handle:
                handle.read(1)
    except OSError as exc:
        return str(exc)
    return None


# One mark on these stands for every file underneath, none of which is in the ledger.
DIRECTORY_KINDS = {"pruned-directory", "submodule", "directory-entry"}


def mark_problem(root: Path, item: dict[str, Any], status: str, note: str | None) -> str | None:
    """Return why this status cannot be recorded for this entry, or None when it can."""
    has_note = bool(note and note.strip())
    if status == "excluded-confirmed" and not has_note:
        return "excluded-confirmed needs --note with the file-specific reason"
    if status == "context-reviewed" and item["scope"] != "context":
        return f"context-reviewed applies to context entries only; this entry's scope is {item['scope']}"
    if status == "reviewed":
        if item["kind"] in DIRECTORY_KINDS and not has_note:
            return "reviewed on a directory entry needs --note naming what was read under it"
        # Checked on every mark, whatever the entry's current status: what cannot be read now was not reviewed.
        failure = read_failure(root, item)
        if failure:
            return f"cannot be read ({failure}), so it cannot have been reviewed"
    return None


def command_mark(args: argparse.Namespace) -> int:
    out = Path(args.out).expanduser().resolve()
    ledger = load_ledger(out)
    paths = read_paths(args)
    if not paths:
        raise SystemExit("no paths supplied; use --path, --paths-file, or --stdin")

    by_path = {item["path"]: item for item in ledger["files"]}
    unknown = [path for path in paths if path not in by_path]
    if unknown:
        notice("unknown inventory paths:")
        for path in unknown:
            notice(f"  {path}")
        return 2

    # Validate the whole batch before changing anything, so a rejection leaves the ledger as it was.
    root = Path(ledger["repo_root"])
    problems = [(path, mark_problem(root, by_path[path], args.status, args.note)) for path in paths]
    problems = [(path, problem) for path, problem in problems if problem]
    if problems:
        notice("ledger not updated:")
        for path, problem in problems:
            notice(f"  {path}: {problem}")
        return 2

    for path in paths:
        item = by_path[path]
        item["status"] = args.status
        # A note explains one status; drop the old one when the status is set again without it.
        if args.note:
            item["review_note"] = args.note
        else:
            item.pop("review_note", None)
        item["reviewed_at"] = utc_now()

    ledger["updated_at"] = utc_now()
    save_ledger(out, ledger)
    print(json.dumps(status_summary(ledger), ensure_ascii=False, indent=2))
    return 0


def command_status(args: argparse.Namespace) -> int:
    out = Path(args.out).expanduser().resolve()
    ledger = load_ledger(out)
    summary = status_summary(ledger)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.show_pending:
        for item in ledger["files"]:
            if item["status"] not in TERMINAL_STATUSES:
                print(f"{item['status']}\t{item['kind']}\t{item['path']}")

    return 0 if summary["coverage_complete"] else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="inventory a repository and create a review ledger")
    create.add_argument("--repo", required=True, help="target repository or source directory")
    create.add_argument("--out", required=True, help="audit-state directory outside the target repo")
    create.set_defaults(func=command_create)

    mark = subparsers.add_parser("mark", help="mark exact inventory paths after review or exclusion confirmation")
    mark.add_argument("--out", required=True, help="audit-state directory containing ledger.json")
    mark.add_argument(
        "--status",
        required=True,
        choices=("reviewed", "excluded-confirmed", "context-reviewed", "unreadable"),
    )
    mark.add_argument("--path", action="append", help="exact repository-relative path; repeat as needed")
    mark.add_argument("--paths-file", help="UTF-8 file containing one exact repository-relative path per line")
    mark.add_argument("--stdin", action="store_true", help="read one exact UTF-8 path per line from standard input")
    mark.add_argument("--note", help="short evidence note stored in the ledger; required for excluded-confirmed")
    mark.set_defaults(func=command_mark)

    status = subparsers.add_parser("status", help="show coverage status; exits 2 while coverage is incomplete")
    status.add_argument("--out", required=True, help="audit-state directory containing ledger.json")
    status.add_argument("--show-pending", action="store_true", help="list every entry without a completed disposition")
    status.set_defaults(func=command_status)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    # Paths can hold any character; a legacy console code page must not turn one into a crash.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        notice("interrupted")
        return 130
    except subprocess.CalledProcessError as exc:
        notice(f"error: {exc}: {git_stderr(exc)}")
        return 1
    except OSError as exc:
        notice(f"error: {exc}")
        return 1
    except (KeyError, TypeError, AttributeError) as exc:
        notice(f"error: malformed ledger: {exc!r}")
        return 1
    except ValueError as exc:
        notice(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
