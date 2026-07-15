import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

REPORT_PATH = Path("reports/report.html")
WORKTREE_DIR = Path(".gh-pages-worktree")
BRANCH = os.getenv("GITHUB_PAGES_BRANCH", "gh-pages")
REMOTE = os.getenv("GITHUB_PAGES_REMOTE", "origin")


def _is_enabled() -> bool:
    return os.getenv("GITHUB_PAGES_PUBLISH", "1").lower() not in ("0", "false", "no", "off")


def _run(args: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"{' '.join(args)}\n{stderr}")
    return result


def _repo_root() -> Path:
    result = _run(["git", "rev-parse", "--show-toplevel"])
    return Path(result.stdout.strip())


def _ref_exists(ref: str, cwd: Path | None = None) -> bool:
    result = _run(["git", "rev-parse", "--verify", ref], cwd=cwd, check=False)
    return result.returncode == 0


def _guess_pages_url(repo_root: Path) -> str:
    result = _run(["git", "remote", "get-url", REMOTE], cwd=repo_root, check=False)
    remote = (result.stdout or "").strip()
    match = re.search(r"github\.com[:/]([^/]+)/([^/.]+?)(?:\.git)?$", remote)
    if not match:
        return "https://<user>.github.io/<repo>/"
    user, repo = match.groups()
    return f"https://{user}.github.io/{repo}/"


def _ensure_worktree(repo_root: Path) -> Path:
    worktree = repo_root / WORKTREE_DIR
    if worktree.exists():
        return worktree

    _run(["git", "fetch", REMOTE], cwd=repo_root, check=False)

    if _ref_exists(f"{REMOTE}/{BRANCH}", cwd=repo_root) or _ref_exists(BRANCH, cwd=repo_root):
        _run(["git", "worktree", "add", str(worktree), BRANCH], cwd=repo_root)
        return worktree

    _run(
        ["git", "worktree", "add", "-b", BRANCH, "--orphan", str(worktree)],
        cwd=repo_root,
    )
    return worktree


def _clean_deploy_dir(deploy_dir: Path) -> None:
    for item in deploy_dir.iterdir():
        if item.name == ".git":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def publish_report(report_path: Path | str = REPORT_PATH) -> bool:
    """Публикует HTML-отчёт на GitHub Pages (ветка gh-pages)."""
    if not _is_enabled():
        print("GitHub Pages: публикация отключена (GITHUB_PAGES_PUBLISH=0)")
        return False

    report = Path(report_path)
    if not report.exists():
        print("GitHub Pages: отчёт не найден")
        return False

    try:
        repo_root = _repo_root()
        deploy_dir = _ensure_worktree(repo_root)
        _clean_deploy_dir(deploy_dir)

        shutil.copy(report, deploy_dir / "index.html")
        (deploy_dir / ".nojekyll").touch()

        _run(["git", "add", "index.html", ".nojekyll"], cwd=deploy_dir)

        status = _run(["git", "status", "--porcelain"], cwd=deploy_dir)
        if not status.stdout.strip():
            print("GitHub Pages: изменений нет, публикация не требуется")
            return True

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _run(["git", "commit", "-m", f"Update performance report ({timestamp})"], cwd=deploy_dir)
        _run(["git", "push", REMOTE, f"HEAD:{BRANCH}"], cwd=deploy_dir)

        pages_url = _guess_pages_url(repo_root)
        print(f"GitHub Pages: отчёт опубликован - {pages_url}")
        return True
    except Exception as exc:
        print(f"GitHub Pages: не удалось опубликовать — {exc}")
        return False