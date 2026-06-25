# Copyright (C) 2026 MESH Research
#
# kc-knowledge-base-sync is free software; you can redistribute it and/or modify
# it under the terms of the MIT License; see LICENSE file for more details.

"""CLI entry point for publishing KCWorks docs to the knowledge-base."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from knowledge_base_sync.config import SyncConfig, load_config
from knowledge_base_sync.extract import extract_how_tos_from_file
from knowledge_base_sync.format import format_deterministic, output_path_for_section
from knowledge_base_sync.lm_studio import format_with_lm_studio
from knowledge_base_sync.publish import (
    WrittenArticle,
    create_pull_request,
    default_branch_name,
    git_commit,
    git_create_branch,
    git_current_branch,
    rebuild_indexes,
    write_article,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract how-to sections from KCWorks docs/source markdown and "
            "publish them to the MESH knowledge-base repository."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("docs/knowledge_base_sync/config.yaml"),
        help=(
            "YAML config file "
            "(default: docs/knowledge_base_sync/config.yaml relative to cwd)"
        ),
    )
    parser.add_argument(
        "--kcworks-root",
        type=Path,
        default=None,
        help="Override kcworks_root from the config file",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Format articles with LM Studio instead of the deterministic converter",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned outputs without writing files or touching git",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing knowledge-base articles",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Create a git branch, rebuild indexes, and commit in the knowledge-base repo",
    )
    parser.add_argument(
        "--branch",
        default=None,
        help="Branch name for --commit (default: kb-sync/YYYY-MM-DD)",
    )
    parser.add_argument(
        "--pr",
        action="store_true",
        help="After --commit, push and open a GitHub pull request (requires gh)",
    )
    parser.add_argument(
        "--pr-title",
        default=None,
        help="Pull request title (default: derived from changed articles)",
    )
    return parser


def _format_section(
    section,
    *,
    config: SyncConfig,
    page_intro: str,
    mapping_extra_keywords: tuple[str, ...],
    use_llm: bool,
) -> str:
    if use_llm:
        return format_with_lm_studio(
            section,
            config=config.lm_studio,
            knowledge_base_root=config.knowledge_base_root,
            page_intro=page_intro,
        )
    return format_deterministic(
        section,
        audience=config.audience,
        owner=config.owner,
        extra_keywords=list(mapping_extra_keywords),
        page_intro=page_intro,
    )


def run_sync(args: argparse.Namespace) -> int:
    """Execute one publish run."""
    config = load_config(args.config, kcworks_root=args.kcworks_root)
    if not config.knowledge_base_root.is_dir():
        print(
            f"Knowledge-base path not found: {config.knowledge_base_root}",
            file=sys.stderr,
        )
        return 1

    planned: list[tuple[str, str, str]] = []
    written: list[WrittenArticle] = []

    for mapping in config.sources:
        for docs_path in mapping.docs_paths:
            if not docs_path.is_file():
                print(f"Skipping missing source: {docs_path}", file=sys.stderr)
                continue
            document = extract_how_tos_from_file(docs_path)
            for section in document.how_tos:
                rel_path = output_path_for_section(
                    section,
                    mapping.kb_topic,
                    filename_prefix=mapping.filename_prefix,
                )
                content = _format_section(
                    section,
                    config=config,
                    page_intro=document.intro,
                    mapping_extra_keywords=mapping.extra_keywords,
                    use_llm=args.use_llm,
                )
                planned.append((rel_path, section.kb_title, content))
                if args.dry_run:
                    print(f"[dry-run] would write {rel_path} — {section.kb_title}")
                    continue
                written.append(
                    write_article(
                        config.knowledge_base_root,
                        rel_path,
                        content,
                        force=args.force,
                    )
                )
                status = "created" if written[-1].created else "updated"
                if written[-1].skipped:
                    status = "unchanged"
                print(f"{status}: {rel_path} — {section.kb_title}")

    if args.dry_run:
        print(f"\n{len(planned)} article(s) would be written.")
        return 0

    changed_paths = [w.relative_path for w in written if not w.skipped]
    readme_paths = _readme_paths_to_stage(config, changed_paths)

    if args.commit and changed_paths:
        branch = args.branch or default_branch_name(config.branch_prefix)
        current = git_current_branch(config.knowledge_base_root)
        if current != branch:
            try:
                git_create_branch(config.knowledge_base_root, branch)
            except Exception:
                subprocess.run(
                    ["git", "checkout", branch],
                    cwd=config.knowledge_base_root,
                    check=True,
                )
        rebuild_indexes(config.knowledge_base_root)
        stage_paths = sorted(set(changed_paths + readme_paths))
        commit_msg = _commit_message(written)
        git_commit(config.knowledge_base_root, commit_msg, stage_paths)
        print(f"Committed on branch {branch}: {commit_msg}")

        if args.pr:
            pr_title = args.pr_title or commit_msg.split("\n", 1)[0]
            pr_body = _pr_body(written)
            url = create_pull_request(
                config.knowledge_base_root,
                title=pr_title,
                body=pr_body,
                base=config.pr_base,
            )
            print(f"Pull request: {url}")

    elif changed_paths and not args.commit:
        print(
            "\nFiles written. Run with --commit to rebuild indexes and commit, "
            "or run `uv run python scripts/build_index.py` in the knowledge-base repo."
        )

    return 0


def _readme_paths_to_stage(config: SyncConfig, changed_paths: list[str]) -> list[str]:
    readmes: set[str] = {"README.md"}
    for rel in changed_paths:
        parts = Path(rel).parts
        if not parts:
            continue
        readmes.add(f"{parts[0]}/README.md")
        if len(parts) >= 2:
            readmes.add(f"{parts[0]}/{parts[1]}/README.md")
    return sorted(p for p in readmes if (config.knowledge_base_root / p).exists())


def _commit_message(written: list[WrittenArticle]) -> str:
    titles = [w.title for w in written if not w.skipped]
    if len(titles) == 1:
        summary = f"Add KCWorks runbook: {titles[0]}"
    else:
        summary = f"Add {len(titles)} KCWorks runbooks from admin docs"
    bullets = "\n".join(f"- {t}" for t in titles[:20])
    return f"{summary}\n\n{bullets}"


def _pr_body(written: list[WrittenArticle]) -> str:
    lines = [
        "## Summary",
        "",
        "Sync KCWorks administrator how-tos from `kcworks-next/docs/source` into the knowledge base.",
        "",
        "## Articles",
        "",
    ]
    for article in written:
        if article.skipped:
            continue
        lines.append(f"- `{article.relative_path}` — {article.title}")
    lines.extend(
        [
            "",
            "## Test plan",
            "",
            "- [ ] Spot-check formatting and commands in GitHub preview",
            "- [ ] Confirm index README links updated",
            "- [ ] Verify no secrets were introduced",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI main."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.pr and not args.commit:
        parser.error("--pr requires --commit")
    return run_sync(args)
