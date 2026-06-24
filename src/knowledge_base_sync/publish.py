# Copyright (C) 2026 MESH Research
#
# kc-knowledge-base-sync is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.

"""Write articles to the knowledge-base repo, rebuild indexes, commit, and open PRs."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True, slots=True)
class WrittenArticle:
    """One markdown file written to the knowledge-base repo."""

    relative_path: str
    title: str
    created: bool
    updated: bool
    skipped: bool


def write_article(
    knowledge_base_root: Path,
    relative_path: str,
    content: str,
    *,
    force: bool = False,
) -> WrittenArticle:
    """Write one article if missing or when ``force`` is True.

    Args:
        knowledge_base_root: Root of the cloned knowledge-base repository.
        relative_path: Destination path relative to the repo root.
        content: Full markdown file contents.
        force: Overwrite an existing file when True.

    Returns:
        Metadata about the write operation.
    """
    dest = knowledge_base_root / relative_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    title = _title_from_markdown(content)
    if dest.exists() and not force:
        if dest.read_text(encoding="utf-8") == content:
            return WrittenArticle(relative_path, title, False, False, True)
        raise FileExistsError(
            f"{relative_path} already exists; pass --force to overwrite."
        )
    created = not dest.exists()
    dest.write_text(content, encoding="utf-8")
    return WrittenArticle(relative_path, title, created, not created, False)


def _title_from_markdown(content: str) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "(untitled)"


def rebuild_indexes(knowledge_base_root: Path) -> None:
    """Run the knowledge-base ``build_index.py`` script."""
    script = knowledge_base_root / "scripts/build_index.py"
    if not script.is_file():
        raise FileNotFoundError(f"Index builder not found: {script}")
    subprocess.run(
        ["uv", "run", "python", str(script)],
        cwd=knowledge_base_root,
        check=True,
    )


def git_current_branch(knowledge_base_root: Path) -> str:
    """Return the current git branch name."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=knowledge_base_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def git_has_changes(knowledge_base_root: Path) -> bool:
    """Return True when the knowledge-base working tree has changes."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=knowledge_base_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(result.stdout.strip())


def git_create_branch(knowledge_base_root: Path, branch: str) -> None:
    """Create and checkout a new branch."""
    subprocess.run(
        ["git", "checkout", "-b", branch],
        cwd=knowledge_base_root,
        check=True,
    )


def git_commit(knowledge_base_root: Path, message: str, paths: list[str]) -> None:
    """Stage and commit the given paths."""
    subprocess.run(["git", "add", *paths], cwd=knowledge_base_root, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=knowledge_base_root, check=True)


def default_branch_name(prefix: str = "kb-sync") -> str:
    """Suggest a branch name for today's sync."""
    return f"{prefix}/{date.today().isoformat()}"


def create_pull_request(
    knowledge_base_root: Path,
    *,
    title: str,
    body: str,
    base: str = "main",
) -> str:
    """Push the current branch and open a GitHub pull request.

    Returns:
        The PR URL printed by ``gh pr create``.
    """
    branch = git_current_branch(knowledge_base_root)
    subprocess.run(
        ["git", "push", "-u", "origin", branch],
        cwd=knowledge_base_root,
        check=True,
    )
    result = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--base",
            base,
        ],
        cwd=knowledge_base_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()
