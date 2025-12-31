"""Git operations for device registry."""

from pathlib import Path
from typing import Optional

from git import Repo, InvalidGitRepositoryError
from git.exc import GitCommandError

from .config import REGISTRY_DIR


def is_git_repo() -> bool:
    """Check if registry is a git repo."""
    try:
        Repo(REGISTRY_DIR)
        return True
    except InvalidGitRepositoryError:
        return False


def init_registry(remote_url: Optional[str] = None) -> Repo:
    """Initialize or clone registry repo."""
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)

    if remote_url:
        # Clone from remote
        return Repo.clone_from(remote_url, REGISTRY_DIR)
    else:
        # Initialize new repo
        repo = Repo.init(REGISTRY_DIR)
        # Create initial structure
        (REGISTRY_DIR / "devices.toml").write_text("[device]\n")
        (REGISTRY_DIR / "hosts").mkdir(exist_ok=True)
        (REGISTRY_DIR / "udev").mkdir(exist_ok=True)
        repo.index.add(["devices.toml"])
        repo.index.commit("Initial registry")
        return repo


def get_repo() -> Optional[Repo]:
    """Get repo if it exists."""
    try:
        return Repo(REGISTRY_DIR)
    except InvalidGitRepositoryError:
        return None


def sync(message: str = "Update devices") -> tuple[bool, str]:
    """Commit changes and sync with remote."""
    repo = get_repo()
    if not repo:
        return False, "Registry is not a git repository"

    # Add all changes
    repo.index.add("*")

    # Check if there are changes to commit
    if repo.is_dirty() or repo.untracked_files:
        repo.index.commit(message)

    # Try to push/pull if remote exists
    try:
        if repo.remotes:
            origin = repo.remotes.origin
            origin.pull()
            origin.push()
            return True, "Synced with remote"
        return True, "Committed locally (no remote configured)"
    except GitCommandError as e:
        return False, f"Sync failed: {e}"


def status() -> dict:
    """Get git status."""
    repo = get_repo()
    if not repo:
        return {"initialized": False}

    return {
        "initialized": True,
        "dirty": repo.is_dirty(),
        "untracked": repo.untracked_files,
        "branch": repo.active_branch.name if not repo.head.is_detached else "detached",
        "has_remote": bool(repo.remotes),
        "remote_url": repo.remotes.origin.url if repo.remotes else None,
    }
